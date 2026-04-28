"""Top-level orchestration: per-target drift check + pytest run."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from releaseguard.drift import check_drift, fingerprint
from releaseguard.report import RunReport, TargetRun, TestOutcome
from releaseguard.targets import Local, Target, TargetSpec


def _python() -> str:
    return shutil.which("python") or shutil.which("python3") or sys.executable


def run_target(spec: TargetSpec, target: Target,
               work_dir: Path) -> TargetRun:
    """Run one target's drift checks + pytest. Returns a TargetRun."""
    work_dir.mkdir(parents=True, exist_ok=True)
    rg_out = work_dir / f"{spec.name}.events.jsonl"

    target.setup()
    try:
        started = datetime.now(UTC).isoformat()
        drift = check_drift(target, spec)
        # Run pytest with the plugin so we get structured per-test events.
        # The plugin auto-loads via the pytest11 entry point; we just
        # supply --rg-out so it knows where to write events.
        pytest_cmd = [_python(), "-m", "pytest",
                      "--rg-out", str(rg_out), *spec.pytest_args]
        target.run(pytest_cmd, env={k: v for k, v in spec.expected_env.items() if v})
        outcomes = _read_outcomes(rg_out)
        ended = datetime.now(UTC).isoformat()
    finally:
        target.teardown()

    return TargetRun(
        target=spec.name,
        fingerprint=fingerprint(spec),
        started_at=started,
        ended_at=ended,
        drift=drift,
        outcomes=outcomes,
    )


def _read_outcomes(path: Path) -> list[TestOutcome]:
    if not path.exists():
        return []
    out: list[TestOutcome] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        o = TestOutcome(
            nodeid=r.get("nodeid", ""),
            outcome=r.get("outcome", "unknown"),
            duration_s=float(r.get("duration", 0.0)),
            file=r.get("file", ""),
            line=int(r.get("line", 0)),
            longrepr=r.get("longrepr", ""),
        )
        o.fill_fingerprint()
        out.append(o)
    return out


def run_all(specs: list[TargetSpec], work_dir: Path,
            allow_drift: bool = False) -> RunReport:
    """Run every target sequentially. Returns the aggregated report."""
    report = RunReport(allow_drift=allow_drift)
    for spec in specs:
        target = _make_target(spec)
        report.runs.append(run_target(spec, target, work_dir))
    return report


def _make_target(spec: TargetSpec) -> Target:
    if spec.image:
        # Lazy import — Docker driver pulls in subprocess plumbing.
        from releaseguard.targets import Docker
        return Docker(name=spec.name, image=spec.image)
    return Local(name=spec.name)
