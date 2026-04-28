"""Configuration-drift detection.

Each check returns a `DriftCheck` row; collected into a `DriftReport`.
The runner looks at `DriftReport.has_failures` to decide whether to
gate the release.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field

from releaseguard.targets import Target, TargetSpec


def _python() -> str:
    """Resolve a python interpreter that exists on PATH for the target.

    On macOS dev machines `python` may not exist; on slim Docker images
    only `python3` is present. We prefer `python` if installed (matches
    most CI runners), then fall back to `python3`, then to whatever
    sys.executable points at."""
    return shutil.which("python") or shutil.which("python3") or sys.executable


@dataclass
class DriftCheck:
    name: str
    kind: str            # "env" | "package" | "file" | "probe" | "python"
    expected: str
    actual: str
    status: str          # "ok" | "warn" | "fail"
    detail: str = ""


@dataclass
class DriftReport:
    target: str
    checks: list[DriftCheck] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")


def check_drift(target: Target, spec: TargetSpec) -> DriftReport:
    rep = DriftReport(target=spec.name)
    rep.checks.extend(_check_python_version(target, spec))
    rep.checks.extend(_check_env(target, spec))
    rep.checks.extend(_check_packages(target, spec))
    rep.checks.extend(_check_files(target, spec))
    rep.checks.extend(_check_probes(target, spec))
    return rep


def _check_python_version(target: Target, spec: TargetSpec) -> list[DriftCheck]:
    expected = spec.expected_env.get("PYTHON_VERSION", "")
    if not expected:
        return []
    r = target.run([_python(), "--version"])
    actual = (r.stdout + r.stderr).strip()
    return [DriftCheck(
        name="python.version", kind="python",
        expected=expected, actual=actual,
        status="ok" if expected in actual else "fail",
    )]


_PEP440_OP = re.compile(r"^(?P<name>[a-zA-Z0-9_.\-]+)\s*(?P<op>==|>=|<=|>|<|~=)?\s*(?P<ver>.+)?$")


def _check_env(target: Target, spec: TargetSpec) -> list[DriftCheck]:
    out: list[DriftCheck] = []
    for k, v in spec.expected_env.items():
        if k == "PYTHON_VERSION":
            continue
        r = target.run(["sh", "-c", f"printf %s \"${{{k}-}}\""])
        actual = r.stdout
        # Empty value in spec = "must be set, any value".
        if v == "":
            status = "ok" if actual else "fail"
            detail = "set" if actual else "missing"
        else:
            status = "ok" if actual == v else "fail"
            detail = f"value mismatch (got {actual!r})" if actual != v else ""
        out.append(DriftCheck(
            name=f"env.{k}", kind="env", expected=v or "<set>",
            actual=actual, status=status, detail=detail,
        ))
    return out


def _check_packages(target: Target, spec: TargetSpec) -> list[DriftCheck]:
    out: list[DriftCheck] = []
    for pkg_spec in spec.expected_packages:
        m = _PEP440_OP.match(pkg_spec)
        if not m:
            out.append(DriftCheck(
                name=f"package.{pkg_spec}", kind="package",
                expected=pkg_spec, actual="",
                status="warn", detail="unparseable spec",
            ))
            continue
        name = m.group("name")
        op = m.group("op") or "=="
        want = m.group("ver") or ""
        r = target.run([_python(), "-m", "pip", "show", name])
        if r.code != 0:
            out.append(DriftCheck(
                name=f"package.{name}", kind="package",
                expected=pkg_spec, actual="<not installed>",
                status="fail", detail="pip show returned non-zero",
            ))
            continue
        version = ""
        for line in r.stdout.splitlines():
            if line.startswith("Version:"):
                version = line.split(":", 1)[1].strip()
        ok = _version_matches(version, op, want)
        # A patch-level mismatch with == is a warn; major/minor mismatch is fail.
        status = "ok" if ok else _version_severity(version, want)
        out.append(DriftCheck(
            name=f"package.{name}", kind="package",
            expected=pkg_spec, actual=version,
            status=status,
        ))
    return out


def _version_matches(actual: str, op: str, want: str) -> bool:
    if not want:
        # No version constraint — presence is sufficient.
        return bool(actual)
    if not actual:
        return False
    if op == "==":
        return actual == want
    a = _ver_tuple(actual)
    w = _ver_tuple(want)
    if op == ">=":
        return a >= w
    if op == "<=":
        return a <= w
    if op == ">":
        return a > w
    if op == "<":
        return a < w
    if op == "~=":
        # Compatible release: same major.minor, patch ≥ want.
        return a[:2] == w[:2] and a >= w
    return False


def _version_severity(actual: str, want: str) -> str:
    a = _ver_tuple(actual)
    w = _ver_tuple(want)
    if not a or not w:
        return "fail"
    if a[0] != w[0] or a[1] != w[1]:
        return "fail"   # major/minor diff
    return "warn"        # patch-only diff


def _ver_tuple(s: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in re.split(r"[.+\-]", s):
        try:
            out.append(int(part))
        except ValueError:
            break
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def _check_files(target: Target, spec: TargetSpec) -> list[DriftCheck]:
    out: list[DriftCheck] = []
    for f in spec.expected_files:
        path = f.get("path", "")
        want = f.get("sha256", "")
        if not path or not want:
            continue
        r = target.run(["sh", "-c", f"sha256sum {path} 2>/dev/null | awk '{{print $1}}'"])
        actual = r.stdout.strip() or "<missing>"
        status = "ok" if actual == want else "fail"
        out.append(DriftCheck(
            name=f"file.{path}", kind="file",
            expected=want, actual=actual, status=status,
            detail="content drift" if actual != want else "",
        ))
    return out


def _check_probes(target: Target, spec: TargetSpec) -> list[DriftCheck]:
    out: list[DriftCheck] = []
    for probe in spec.exec_probes:
        r = target.run(["sh", "-c", probe])
        ok = r.code == 0
        out.append(DriftCheck(
            name="probe." + (probe.split()[0] if probe else "?"),
            kind="probe",
            expected="exit 0",
            actual=f"exit {r.code}",
            status="ok" if ok else "fail",
            detail=("" if ok else (r.stderr.strip()[:160] or r.stdout.strip()[:160])),
        ))
    return out


def fingerprint(spec: TargetSpec) -> str:
    """Stable hash of the spec — useful for the report header."""
    h = hashlib.sha256()
    for k in sorted(spec.expected_env):
        h.update(f"{k}={spec.expected_env[k]}".encode())
    for p in sorted(spec.expected_packages):
        h.update(p.encode())
    for f in spec.expected_files:
        h.update(f.get("path", "").encode())
        h.update(f.get("sha256", "").encode())
    return h.hexdigest()[:12]
