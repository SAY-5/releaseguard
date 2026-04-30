from __future__ import annotations

from releaseguard.canary import (
    CanaryAction,
    CanaryMetrics,
    CanaryPolicy,
)


def test_holds_below_min_samples() -> None:
    p = CanaryPolicy(min_canary_samples=1000)
    d = p.decide(CanaryMetrics(10000, 100), CanaryMetrics(50, 0))
    assert d.action == CanaryAction.HOLD


def test_promotes_when_canary_matches_active() -> None:
    p = CanaryPolicy(min_canary_samples=100)
    d = p.decide(CanaryMetrics(10000, 100), CanaryMetrics(2000, 22))
    # active=1%, canary=1.1%, delta=0.1pp <= promote_delta(0.5pp)
    assert d.action == CanaryAction.PROMOTE


def test_rolls_back_on_significant_regression() -> None:
    p = CanaryPolicy(min_canary_samples=100)
    d = p.decide(CanaryMetrics(10000, 100), CanaryMetrics(2000, 100))
    # active=1%, canary=5%, delta=4pp > rollback_delta(2pp)
    assert d.action == CanaryAction.ROLLBACK


def test_holds_in_grey_zone() -> None:
    p = CanaryPolicy(min_canary_samples=100)
    # active=1%, canary=2.5%, delta=1.5pp - between promote(0.5) and rollback(2)
    d = p.decide(CanaryMetrics(10000, 100), CanaryMetrics(2000, 50))
    assert d.action == CanaryAction.HOLD


def test_zero_active_requests_treats_as_zero_error_rate() -> None:
    p = CanaryPolicy(min_canary_samples=100)
    d = p.decide(CanaryMetrics(0, 0), CanaryMetrics(2000, 0))
    # both error rates are 0; delta is 0 → promote.
    assert d.action == CanaryAction.PROMOTE
