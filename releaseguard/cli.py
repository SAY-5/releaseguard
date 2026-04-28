"""`rg` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from releaseguard.drift import check_drift
from releaseguard.manifests import load_manifest
from releaseguard.runner import run_all
from releaseguard.targets import Local, TargetSpec


def cmd_run(args: argparse.Namespace) -> int:
    specs = load_manifest(Path(args.manifest))
    report = run_all(specs, Path(args.work), allow_drift=args.allow_drift)
    out_path = Path(args.out)
    report.write(out_path)
    print(json.dumps({
        "out": str(out_path),
        "status": report.overall_status,
        "targets": [r.target for r in report.runs],
    }, indent=2))
    return 0 if report.overall_status == "passed" else 1


def cmd_drift(args: argparse.Namespace) -> int:
    specs = load_manifest(Path(args.manifest))
    rc = 0
    for spec in specs:
        # Drift command always runs against Local — useful in CI to
        # validate the runner *itself*, not a bunch of containers.
        rep = check_drift(Local(name=spec.name), spec)
        print(f"=== {spec.name} ===")
        for c in rep.checks:
            mark = {"ok": "✓", "warn": "!", "fail": "✗"}.get(c.status, "?")
            print(f"  {mark} {c.kind:8s} {c.name:32s} expected={c.expected!r} actual={c.actual!r}")
        if rep.has_failures:
            rc = 1
    return rc


def cmd_report(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.report).read_text())
    if args.html:
        from releaseguard.html_report import write as write_html
        out = Path(args.html)
        write_html(Path(args.report), out)
        print(f"wrote {out}")
        return 0
    print(json.dumps(data, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rg",
        description="ReleaseGuard — CI/CD test infrastructure with drift detection.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="Run all targets in the manifest.")
    pr.add_argument("--manifest", default="targets.yaml")
    pr.add_argument("--out", default="runs/report.json")
    pr.add_argument("--work", default="runs")
    pr.add_argument("--allow-drift", action="store_true")
    pr.set_defaults(fn=cmd_run)

    pd = sub.add_parser("drift", help="Run only the drift checks (Local target).")
    pd.add_argument("--manifest", default="targets.yaml")
    pd.set_defaults(fn=cmd_drift)

    pp = sub.add_parser("report", help="Pretty-print or render a saved report JSON.")
    pp.add_argument("report")
    pp.add_argument("--html", help="Write self-contained HTML report to PATH")
    pp.set_defaults(fn=cmd_report)

    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    return args.fn(args)


# Tiny re-export for tests that import the unused symbols.
_ = TargetSpec


if __name__ == "__main__":
    raise SystemExit(main())
