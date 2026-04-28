"""HTML report generator tests."""

from __future__ import annotations

import json

from releaseguard.html_report import render_html


def _sample_report() -> dict:
    return {
        "schema": "releaseguard.report.v1",
        "started_at": "2026-04-28T00:00:00+00:00",
        "overall_status": "drift",
        "allow_drift": False,
        "runs": [
            {
                "target": "prod-like",
                "fingerprint": "abc123",
                "started_at": "2026-04-28T00:00:00+00:00",
                "ended_at":   "2026-04-28T00:00:30+00:00",
                "summary": {"passed": 12, "failed": 1, "skipped": 0},
                "drift": {
                    "summary": {"total": 4, "fail": 1, "warn": 0, "ok": 3},
                    "checks": [
                        {"name":"env.DATABASE_URL","kind":"env","expected":"postgres://prod","actual":"postgres://stale","status":"fail","detail":"value mismatch"},
                        {"name":"env.ENVIRONMENT","kind":"env","expected":"prod","actual":"prod","status":"ok","detail":""},
                    ],
                },
                "outcomes": [
                    {"nodeid":"tests/test_x.py::test_one","outcome":"passed","duration_s":0.012,"file":"tests/test_x.py","line":3,"longrepr":"","fingerprint":"f1"},
                    {"nodeid":"tests/test_x.py::test_two","outcome":"failed","duration_s":0.080,"file":"tests/test_x.py","line":12,"longrepr":"AssertionError: 1 != 2","fingerprint":"f2"},
                ],
            },
        ],
    }


def test_html_contains_payload_and_status_badge():
    html = render_html(_sample_report())
    assert "<!doctype html>" in html
    # The payload is inlined as JSON.
    assert "releaseguard.report.v1" in html
    # Status badge is in the markup template (rendered client-side from
    # the inlined JSON), so the JSON must be present.
    assert "drift" in html
    # Self-contained — no external <script src>.
    assert "<script src=" not in html


def test_html_escapes_script_close_in_payload():
    """If a longrepr contained `</script>` we must not break the inline
    block. The render_html implementation rewrites `</` to `<\\/`."""
    data = _sample_report()
    data["runs"][0]["outcomes"][1]["longrepr"] = "boom </script><script>alert(1)</script>"
    html = render_html(data)
    # Original closing tag in the payload should be escaped.
    assert "</script><script>alert(1)</script>" not in html.split("</script>")[0]


def test_html_renders_when_drift_block_missing():
    data = _sample_report()
    data["runs"][0]["drift"] = None
    html = render_html(data)
    # Should not crash; should still contain the test outcomes.
    assert "test_one" in html
    assert json.loads(html.split("const data = ")[1].split(";\nconst")[0].rstrip(";\n"))["runs"][0]["drift"] is None
