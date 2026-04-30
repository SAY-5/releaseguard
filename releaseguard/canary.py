"""v4: canary rollout integration.

Releaseguard (v1-v3) detects regressions vs a baseline. v4 wires
that detection into a canary-rollout decision: given the current
canary's metric vs the active version's, decide whether to:

- PROMOTE the canary (it's at least as healthy as active),
- ROLLBACK (canary regressed beyond the budget),
- HOLD (still in burn-in; not enough data).

The decision is rule-based; production overlays statistical
significance (the same z-test logic as modeldeploy v4). v4
sticks to threshold rules for transparency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CanaryAction(StrEnum):
    PROMOTE = "promote"
    ROLLBACK = "rollback"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class CanaryMetrics:
    requests: int
    errors: int

    @property
    def error_rate(self) -> float:
        return 0.0 if self.requests == 0 else self.errors / self.requests


@dataclass(frozen=True, slots=True)
class CanaryDecision:
    action: CanaryAction
    rationale: str


@dataclass
class CanaryPolicy:
    min_canary_samples: int = 1000
    rollback_delta: float = 0.02   # canary error rate > active + 2pp → rollback
    promote_delta: float = 0.005   # canary error rate <= active + 0.5pp → promote

    def decide(self, active: CanaryMetrics, canary: CanaryMetrics) -> CanaryDecision:
        if canary.requests < self.min_canary_samples:
            return CanaryDecision(
                action=CanaryAction.HOLD,
                rationale=f"canary at {canary.requests} samples (< {self.min_canary_samples})",
            )
        delta = canary.error_rate - active.error_rate
        if delta > self.rollback_delta:
            return CanaryDecision(
                action=CanaryAction.ROLLBACK,
                rationale=(
                    f"canary error rate {canary.error_rate:.3f} > active "
                    f"{active.error_rate:.3f} by {delta:.3f} (> {self.rollback_delta:.3f})"
                ),
            )
        if delta <= self.promote_delta:
            return CanaryDecision(
                action=CanaryAction.PROMOTE,
                rationale=(
                    f"canary {canary.error_rate:.3f} within "
                    f"{self.promote_delta:.3f} of active {active.error_rate:.3f}"
                ),
            )
        return CanaryDecision(
            action=CanaryAction.HOLD,
            rationale=f"delta {delta:.3f} between thresholds; gather more samples",
        )
