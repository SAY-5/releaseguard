"""End-to-end runner tests: drive a Local target through the
real pytest plugin and assert the report contains the expected
outcomes."""

from __future__ import annotations

from pathlib import Path

from releaseguard.report import RunReport
from releaseguard.runner import run_all
from releaseguard.targets import TargetSpec


def test_runner_passing_suite(tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "test_pass.py").write_text(
        "def test_one(): assert 1 + 1 == 2\n"
        "def test_two(): assert 'abc'.upper() == 'ABC'\n"
    )
    spec = TargetSpec(
        name="local-ok",
        pytest_args=["-q", str(sample)],
    )
    report: RunReport = run_all([spec], tmp_path / "work")
    assert report.overall_status == "passed"
    run = report.runs[0]
    assert run.summary()["passed"] == 2
    assert run.summary()["failed"] == 0


def test_runner_failing_suite(tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "test_fail.py").write_text(
        "def test_should_fail(): assert 1 == 2\n"
    )
    spec = TargetSpec(
        name="local-fail",
        pytest_args=["-q", str(sample)],
    )
    report = run_all([spec], tmp_path / "work")
    assert report.overall_status == "failed"
    run = report.runs[0]
    assert run.summary()["failed"] == 1
    failed = [o for o in run.outcomes if o.outcome == "failed"][0]
    assert failed.fingerprint  # populated


def test_runner_drift_blocks_release(tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "test_pass.py").write_text("def test_x(): pass\n")
    spec = TargetSpec(
        name="drift-target",
        # A required env var that doesn't exist.
        expected_env={"RG_DEFINITELY_NOT_SET_VAR": "x"},
        pytest_args=["-q", str(sample)],
    )
    report = run_all([spec], tmp_path / "work")
    # Tests passed but drift was detected → overall is 'drift'.
    assert report.overall_status == "drift"
    assert report.runs[0].drift is not None
    assert report.runs[0].drift.has_failures


def test_allow_drift_lets_release_pass(tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "test_pass.py").write_text("def test_x(): pass\n")
    spec = TargetSpec(
        name="drift-allowed",
        expected_env={"RG_NOT_SET_EITHER": "x"},
        pytest_args=["-q", str(sample)],
    )
    report = run_all([spec], tmp_path / "work", allow_drift=True)
    assert report.overall_status == "passed"


def test_report_to_json_round_trip(tmp_path):
    sample = tmp_path / "sample"
    sample.mkdir()
    (sample / "test_pass.py").write_text("def test_x(): pass\n")
    spec = TargetSpec(name="rt", pytest_args=["-q", str(sample)])
    report = run_all([spec], tmp_path / "work")
    out = tmp_path / "report.json"
    report.write(out)
    import json
    parsed = json.loads(out.read_text())
    assert parsed["schema"] == "releaseguard.report.v1"
    assert parsed["runs"][0]["target"] == "rt"
