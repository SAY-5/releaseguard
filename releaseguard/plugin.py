"""Pytest plugin: write per-test outcomes as JSONL, gate the run on
inline `@pytest.mark.drift_check(...)` declarations.

Activate with `--rg-out=path/to/events.jsonl`. The runner reads the
file back to assemble the structured report.

Inline drift markers
--------------------
Tests can declare a per-test drift dependency right next to the
assertion:

    @pytest.mark.drift_check(probe="redis-cli -h $REDIS_HOST PING",
                             expect="PONG")
    def test_uses_redis():
        ...

The plugin runs the probe at the start of the test session (or once
per first-encountered marker — same probe twice = one execution) and
captures its result on the per-test event line. The runner surfaces
any failed probe as a `drift_blocked` outcome.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--rg-out", default="", help="ReleaseGuard JSONL output path")
    parser.addoption(
        "--rg-fail-on-drift", action="store_true",
        help="Fail the pytest run if any drift_check probe fails",
    )
    parser.addoption(
        "--rg-flaky-retries", type=int, default=0,
        help="Re-run failed tests up to N times. A test that fails first "
             "and passes on retry is recorded as outcome='flaky' on the "
             "event line. The pytest run's exit status reflects the FINAL "
             "result (passed if it eventually passed); the JSONL captures "
             "the flake for the report.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "drift_check(probe, expect=None, name=None): "
        "shell command that must succeed (and optionally produce `expect`) "
        "for the test to be considered environmentally safe to run. Result is "
        "recorded on the event line; failed probes can fail the run.",
    )
    sink = config.getoption("--rg-out")
    if sink:
        Path(sink).parent.mkdir(parents=True, exist_ok=True)
        Path(sink).write_text("")
        pytest_runtest_logreport._sink = sink  # type: ignore[attr-defined]
    pytest_runtest_logreport._fail_on_drift = bool(  # type: ignore[attr-defined]
        config.getoption("--rg-fail-on-drift")
    )
    pytest_runtest_logreport._cache = {}  # type: ignore[attr-defined]
    pytest_runtest_logreport._flaky_retries = int(  # type: ignore[attr-defined]
        config.getoption("--rg-flaky-retries") or 0
    )
    # Per-nodeid attempt counter — distinguishes the original failure
    # from a retry pass.
    pytest_runtest_logreport._attempts = {}  # type: ignore[attr-defined]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):  # type: ignore[no-untyped-def]
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return
    drift = _evaluate_drift_markers(item)
    rep._rg_drift = drift  # type: ignore[attr-defined]
    if drift and not all(d["ok"] for d in drift):
        if getattr(pytest_runtest_logreport, "_fail_on_drift", False) and rep.passed:
            rep.outcome = "failed"
            rep.longrepr = (
                "drift_check failed: "
                + "; ".join(f"{d['name']}: {d.get('detail','')}"
                            for d in drift if not d["ok"])
            )

    # Flaky-retry hook. We track per-nodeid attempts in a session
    # counter; if this is the first failure and retries remain, we
    # rewind the test's call phase by clearing its outcome and
    # invoking it again. Subsequent passes are stamped 'flaky' on
    # the event line so the report distinguishes them from clean
    # passes.
    attempts: dict[str, int] = getattr(pytest_runtest_logreport, "_attempts", {})
    max_retries: int = getattr(pytest_runtest_logreport, "_flaky_retries", 0)
    nodeid = item.nodeid
    cur = attempts.get(nodeid, 0)
    rep._rg_attempt = cur  # 0 = first run, 1 = retry, ...
    if rep.failed and max_retries > 0 and cur < max_retries:
        # Re-execute the test in-place. Pytest's runner calls
        # `item.runtest()`; we trap any new exception and wrap a
        # fresh report so the outcome reflects the retry.
        attempts[nodeid] = cur + 1
        try:
            item.runtest()
            # Passed on retry → flaky.
            rep.outcome = "passed"
            rep.longrepr = None
            rep._rg_attempt = cur + 1
            rep._rg_flaky = True  # consumed by pytest_runtest_logreport
        except BaseException as e:  # noqa: BLE001
            # Still failing — keep the original failure surface but
            # bump attempt count.
            rep._rg_attempt = cur + 1
            rep._rg_flaky = False
            rep.longrepr = f"{rep.longrepr}\n[retry {cur+1}] also failed: {e!r}"


def _evaluate_drift_markers(item) -> list[dict]:  # type: ignore[no-untyped-def]
    """Run every drift_check marker on `item`. Cache by `(probe,expect)`
    so a probe shared across many tests only runs once per session."""
    cache: dict[tuple[str, str | None], dict] = getattr(
        pytest_runtest_logreport, "_cache", {})
    out: list[dict] = []
    for marker in item.iter_markers(name="drift_check"):
        probe = marker.kwargs.get("probe") or (marker.args[0] if marker.args else "")
        expect = marker.kwargs.get("expect")
        name = marker.kwargs.get("name") or probe.split()[0] if probe else "drift"
        key = (probe, expect)
        cached = cache.get(key)
        if cached is None:
            cached = _run_probe(probe, expect)
            cache[key] = cached
        out.append({"name": name, **cached})
    return out


def _run_probe(probe: str, expect: str | None) -> dict:
    if not probe:
        return {"ok": False, "detail": "empty probe"}
    # Expand ${VAR} from the current env so probes can reference config.
    cmd = os.path.expandvars(probe)
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", cmd],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except Exception as e:
        return {"ok": False, "detail": f"probe error: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "detail": f"exit {proc.returncode}: {proc.stderr.strip()[:200]}"}
    if expect is not None and expect not in proc.stdout:
        return {
            "ok": False,
            "detail": f"output missing {expect!r} (got {proc.stdout.strip()[:120]!r})",
        }
    _ = shlex.quote  # marker for human-readability in serialized cmds
    return {"ok": True, "detail": "ok"}


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    flaky = bool(getattr(report, "_rg_flaky", False))
    # 'flaky' becomes its own outcome on the event line for the
    # report — pytest itself still sees the test as 'passed' so the
    # exit status reflects the final state. The runner / report layer
    # collapse 'flaky' back to 'passed' in summary counts but
    # surface them separately.
    surfaced_outcome = "flaky" if flaky else report.outcome
    out: dict[str, Any] = {
        "nodeid": report.nodeid,
        "outcome": surfaced_outcome,
        "duration": report.duration,
        "longrepr": str(report.longrepr) if report.failed else "",
        "file": str(getattr(report, "fspath", "") or ""),
        "line": int(getattr(report, "lineno", 0) or 0),
        "drift_checks": getattr(report, "_rg_drift", None) or [],
        "attempts": int(getattr(report, "_rg_attempt", 0)) + 1,
        "flaky": flaky,
    }
    sink = getattr(pytest_runtest_logreport, "_sink", None)
    if sink is None:
        return
    with open(sink, "a") as f:
        f.write(json.dumps(out) + "\n")
