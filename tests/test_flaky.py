"""v3: flaky-test detection + retry-classify."""

from __future__ import annotations

import json
from pathlib import Path

pytest_plugins = ["pytester"]


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_pass_first_try_is_not_flaky(pytester):
    pytester.makepyfile("def test_x(): assert 1 + 1 == 2\n")
    out = pytester.path / "events.jsonl"
    pytester.runpytest("-q", f"--rg-out={out}", "--rg-flaky-retries=2")
    events = _read(out)
    assert events[0]["outcome"] == "passed"
    assert events[0]["flaky"] is False
    assert events[0]["attempts"] == 1


def test_passes_on_retry_is_flagged_flaky(pytester):
    """A test that fails once then passes is recorded as outcome='flaky'.
    Pytest's exit status still reflects the final pass."""
    pytester.makepyfile(f"""
        from pathlib import Path
        COUNTER = Path('{pytester.path}/counter')
        def test_x():
            n = int(COUNTER.read_text()) if COUNTER.exists() else 0
            COUNTER.write_text(str(n + 1))
            assert n >= 1, f'attempt {{n+1}} - intentional first-try failure'
    """)
    out = pytester.path / "events.jsonl"
    r = pytester.runpytest("-q", f"--rg-out={out}", "--rg-flaky-retries=2")
    # Final pytest outcome: passed (we retried until green).
    r.assert_outcomes(passed=1)
    events = _read(out)
    assert events[0]["outcome"] == "flaky"
    assert events[0]["flaky"] is True
    assert events[0]["attempts"] == 2  # initial + 1 retry


def test_still_failing_after_retries_is_failed(pytester):
    pytester.makepyfile("def test_x(): assert False, 'always fails'\n")
    out = pytester.path / "events.jsonl"
    r = pytester.runpytest("-q", f"--rg-out={out}", "--rg-flaky-retries=2")
    r.assert_outcomes(failed=1)
    events = _read(out)
    assert events[0]["outcome"] == "failed"
    assert events[0]["flaky"] is False


def test_runner_summary_counts_flaky_separately(tmp_path):
    """RunReport.summary() collapses 'flaky' into the 'passed' bucket
    AND surfaces it as its own count, so dashboards see both."""
    from releaseguard.report import TargetRun, TestOutcome
    tr = TargetRun(target="t", fingerprint="x", started_at="now")
    tr.outcomes = [
        TestOutcome(nodeid="t::a", outcome="passed", duration_s=0.01,
                    file="x.py", line=1),
        TestOutcome(nodeid="t::b", outcome="flaky", duration_s=0.03,
                    file="x.py", line=2, attempts=2, flaky=True),
        TestOutcome(nodeid="t::c", outcome="failed", duration_s=0.02,
                    file="x.py", line=3),
    ]
    s = tr.summary()
    # Flaky is visible AND counted as passed (it eventually passed).
    assert s["passed"] == 2
    assert s["flaky"] == 1
    assert s["failed"] == 1


def test_no_retry_flag_means_no_retries(pytester):
    """Without --rg-flaky-retries (default 0), failing tests stay
    failed — no implicit re-runs."""
    pytester.makepyfile("def test_x(): assert False\n")
    out = pytester.path / "events.jsonl"
    pytester.runpytest("-q", f"--rg-out={out}")
    events = _read(out)
    assert events[0]["outcome"] == "failed"
    assert events[0]["attempts"] == 1
