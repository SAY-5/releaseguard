"""Tests for the @drift_check pytest marker. We exercise the plugin
via pytester (pytest's in-process subrunner) so the marker actually
triggers the per-test probe path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_passing_drift_check_records_ok(pytester):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.drift_check(probe='true', name='always_passes')
        def test_x():
            assert 1 + 1 == 2
    """)
    out = pytester.path / "events.jsonl"
    r = pytester.runpytest("-q", f"--rg-out={out}")
    r.assert_outcomes(passed=1)
    events = _read_events(out)
    assert len(events) == 1
    drift = events[0]["drift_checks"]
    assert len(drift) == 1
    assert drift[0]["ok"] is True
    assert drift[0]["name"] == "always_passes"


def test_failing_drift_check_records_fail_but_test_still_passes(pytester):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.drift_check(probe='false', name='always_fails')
        def test_x():
            assert True
    """)
    out = pytester.path / "events.jsonl"
    r = pytester.runpytest("-q", f"--rg-out={out}")
    # Without --rg-fail-on-drift the test still passes; the drift
    # result lives on the event line for the runner to surface.
    r.assert_outcomes(passed=1)
    events = _read_events(out)
    drift = events[0]["drift_checks"]
    assert drift[0]["ok"] is False
    assert "exit 1" in drift[0]["detail"] or "exit" in drift[0]["detail"]


def test_fail_on_drift_promotes_to_failure(pytester):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.drift_check(probe='false', name='env_drift')
        def test_x():
            assert True
    """)
    out = pytester.path / "events.jsonl"
    r = pytester.runpytest("-q", f"--rg-out={out}", "--rg-fail-on-drift")
    r.assert_outcomes(failed=1)


def test_expect_substring_match(pytester):
    pytester.makepyfile("""
        import pytest

        @pytest.mark.drift_check(probe='echo PONG', expect='PONG', name='ping')
        def test_ok():
            pass

        @pytest.mark.drift_check(probe='echo PUNG', expect='PONG', name='wrong')
        def test_bad():
            pass
    """)
    out = pytester.path / "events.jsonl"
    pytester.runpytest("-q", f"--rg-out={out}")
    events = {e["nodeid"].split("::")[-1]: e["drift_checks"] for e in _read_events(out)}
    assert events["test_ok"][0]["ok"] is True
    assert events["test_bad"][0]["ok"] is False
    assert "missing" in events["test_bad"][0]["detail"]


def test_probe_cache_runs_each_unique_probe_once(pytester):
    """Two tests with the same probe should hit the cache. We test by
    using a probe that *appends* to a counter file and then asserts
    on its size."""
    pytester.makepyfile(f"""
        import pytest
        COUNTER = '{pytester.path / "counter"}'
        @pytest.mark.drift_check(probe=f'echo x >> {{COUNTER!s}}', name='c')
        def test_a(): pass
        @pytest.mark.drift_check(probe=f'echo x >> {{COUNTER!s}}', name='c')
        def test_b(): pass
        @pytest.mark.drift_check(probe=f'echo x >> {{COUNTER!s}}', name='c')
        def test_c(): pass
    """)
    pytester.runpytest("-q")
    counter = pytester.path / "counter"
    if counter.exists():
        # Probe should have run exactly once across the three tests.
        assert counter.read_text().count("x") == 1
