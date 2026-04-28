"""Pytest plugin: write per-test outcomes as JSONL.

Activate with `-p releaseguard.plugin --rg-out=path/to/events.jsonl`.
The runner reads the file back to assemble the structured report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--rg-out", default="", help="ReleaseGuard JSONL output path",
    )


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):  # type: ignore[no-untyped-def]
    outcome = yield
    rep = outcome.get_result()
    rep._rg_item = item


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    out: dict[str, Any] = {
        "nodeid": report.nodeid,
        "outcome": report.outcome,
        "duration": report.duration,
        "longrepr": str(report.longrepr) if report.failed else "",
        "file": str(getattr(report, "fspath", "") or ""),
        "line": int(getattr(report, "lineno", 0) or 0),
    }
    sink = getattr(pytest_runtest_logreport, "_sink", None)
    if sink is None:
        return
    with open(sink, "a") as f:
        f.write(json.dumps(out) + "\n")


def pytest_configure(config: pytest.Config) -> None:
    sink = config.getoption("--rg-out")
    if sink:
        # Truncate so re-runs aren't appended to the prior file.
        Path(sink).parent.mkdir(parents=True, exist_ok=True)
        Path(sink).write_text("")
        pytest_runtest_logreport._sink = sink  # type: ignore[attr-defined]


def _example_marker() -> None:
    """Reserved: a `drift_check` marker that emits an exec probe.

    Documented for v2; not wired in v1 to keep the plugin trivial.
    """
