"""Aggregated test + drift report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from releaseguard.drift import DriftReport


@dataclass
class TestOutcome:
    nodeid: str
    outcome: str          # "passed" | "failed" | "skipped" | "flaky"
    duration_s: float
    file: str
    line: int = 0
    longrepr: str = ""
    fingerprint: str = ""
    attempts: int = 1     # how many tries before final state
    flaky: bool = False

    def fill_fingerprint(self) -> None:
        first_line = (self.longrepr or "").splitlines()[0] if self.longrepr else ""
        h = hashlib.sha256()
        h.update(f"{self.file}:{self.line}".encode())
        h.update(b"|")
        h.update(first_line.encode())
        self.fingerprint = h.hexdigest()[:12]


@dataclass
class TargetRun:
    target: str
    fingerprint: str
    started_at: str
    ended_at: str = ""
    drift: DriftReport | None = None
    outcomes: list[TestOutcome] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        # 'flaky' is a sub-classification of 'passed' — the test ran
        # green eventually, but only after a retry. Surface both
        # numbers so dashboards can pick the right denominator.
        s = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        for o in self.outcomes:
            if o.outcome == "flaky":
                s["passed"] += 1
                s["flaky"] += 1
            else:
                s[o.outcome] = s.get(o.outcome, 0) + 1
        return s


@dataclass
class RunReport:
    runs: list[TargetRun] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    allow_drift: bool = False

    @property
    def overall_status(self) -> str:
        for r in self.runs:
            if any(o.outcome == "failed" for o in r.outcomes):
                return "failed"
        if not self.allow_drift and any(r.drift and r.drift.has_failures for r in self.runs):
            return "drift"
        return "passed"

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "releaseguard.report.v1",
            "started_at": self.started_at,
            "overall_status": self.overall_status,
            "allow_drift": self.allow_drift,
            "runs": [
                {
                    "target": r.target,
                    "fingerprint": r.fingerprint,
                    "started_at": r.started_at,
                    "ended_at": r.ended_at,
                    "summary": r.summary(),
                    "drift": _drift_to_json(r.drift) if r.drift else None,
                    "outcomes": [asdict(o) for o in r.outcomes],
                }
                for r in self.runs
            ],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2))


def _drift_to_json(d: DriftReport) -> dict[str, Any]:
    return {
        "target": d.target,
        "summary": {
            "total": len(d.checks),
            "fail": d.fail_count,
            "warn": d.warning_count,
            "ok": sum(1 for c in d.checks if c.status == "ok"),
        },
        "checks": [asdict(c) for c in d.checks],
    }
