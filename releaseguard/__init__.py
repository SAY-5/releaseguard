"""ReleaseGuard — CI/CD test infrastructure with config-drift detection."""

from releaseguard.drift import DriftCheck, DriftReport, check_drift
from releaseguard.report import RunReport, TestOutcome
from releaseguard.targets import Target, TargetSpec

__all__ = [
    "DriftCheck",
    "DriftReport",
    "RunReport",
    "Target",
    "TargetSpec",
    "TestOutcome",
    "check_drift",
]
