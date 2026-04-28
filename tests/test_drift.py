"""Meta-tests: ReleaseGuard testing itself."""

from __future__ import annotations

from releaseguard.drift import check_drift
from releaseguard.targets import Local, TargetSpec


def test_env_present_and_correct(monkeypatch):
    monkeypatch.setenv("RG_TEST_FOO", "bar")
    spec = TargetSpec(name="local", expected_env={"RG_TEST_FOO": "bar"})
    rep = check_drift(Local(extra_env={"RG_TEST_FOO": "bar"}), spec)
    assert not rep.has_failures
    env_check = next(c for c in rep.checks if c.name == "env.RG_TEST_FOO")
    assert env_check.status == "ok"


def test_env_missing_is_failure():
    spec = TargetSpec(name="local", expected_env={"RG_TEST_DOES_NOT_EXIST": "x"})
    rep = check_drift(Local(), spec)
    assert rep.has_failures


def test_env_value_mismatch_is_failure(monkeypatch):
    spec = TargetSpec(name="local", expected_env={"RG_TEST_VAL": "expected"})
    rep = check_drift(Local(extra_env={"RG_TEST_VAL": "actual"}), spec)
    assert rep.has_failures
    bad = next(c for c in rep.checks if c.name == "env.RG_TEST_VAL")
    assert bad.status == "fail"
    assert "mismatch" in bad.detail.lower()


def test_package_pinned_match():
    # pytest must be installed for the test runner to work; assert
    # we can at least find it. Don't pin the version — too brittle.
    spec = TargetSpec(name="local", expected_packages=["pytest"])
    rep = check_drift(Local(), spec)
    pkg = next(c for c in rep.checks if c.name == "package.pytest")
    assert pkg.status in {"ok", "warn"}, pkg


def test_package_missing_is_fail():
    spec = TargetSpec(name="local", expected_packages=["totally-not-installed-pkg-xyzzy"])
    rep = check_drift(Local(), spec)
    pkg = next(c for c in rep.checks if "totally-not-installed" in c.name)
    assert pkg.status == "fail"


def test_probe_zero_exit_passes():
    spec = TargetSpec(name="local", exec_probes=["true"])
    rep = check_drift(Local(), spec)
    assert not rep.has_failures


def test_probe_nonzero_exit_fails():
    spec = TargetSpec(name="local", exec_probes=["false"])
    rep = check_drift(Local(), spec)
    assert rep.has_failures
    bad = next(c for c in rep.checks if c.kind == "probe")
    assert bad.status == "fail"


def test_drift_report_counts():
    spec = TargetSpec(
        name="local",
        exec_probes=["true", "false", "true"],
    )
    rep = check_drift(Local(), spec)
    assert rep.fail_count == 1
    # All three probes recorded.
    assert sum(1 for c in rep.checks if c.kind == "probe") == 3
