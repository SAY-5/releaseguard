# ReleaseGuard — Architecture

> A CI/CD test infrastructure focused on two specific failure modes:
> tests that pass locally and fail in production-shaped environments,
> and tests that pass in CI but rely on environment configuration that
> has drifted away from what production actually has. ReleaseGuard
> sits between `pytest` and `kubectl apply`, runs the same suite
> across N target environments, and emits a single structured report
> the operator can act on.

## What problem this solves

Most CI failures decompose into two buckets:

1. **Real bugs**, caught by tests. Easy.
2. **Environment drift**: a Python version mismatch, a missing env
   var, a different Postgres extension installed in staging vs prod,
   a feature flag flipped on for one tenant only. These look like
   test failures but the test code is fine — the *environment* is the
   bug.

ReleaseGuard makes the second class explicit. It runs every test
suite across each declared target environment, fingerprints each
environment up front, and surfaces drift as its own first-class
failure type next to the test outcome. A green run isn't enough —
a green run with a `drift_detected` flag means the test passed
*despite* the environment being out of spec, which is something the
release captain wants to know before promoting.

## Stack

| Piece           | Tech |
|-----------------|------|
| Language        | Python 3.11+ |
| Test runner     | pytest |
| Target isolation| Docker (one image per target environment) |
| Drift checks    | env vars, package manifest, file checksums, exec probes |
| Reporting       | structured JSON + JUnit XML + static HTML report |
| CI orchestration| GitHub Actions (matrix over targets) |

## Layout

```
releaseguard/
├── targets.py          # Target dataclasses; Docker / Local impls
├── drift.py            # ConfigDrift detection
├── runner.py           # Orchestrates pytest + drift across targets
├── report.py           # Structured report aggregation
├── plugin.py           # pytest plugin: collects per-test metadata
├── cli.py              # `rg run`, `rg report`, `rg drift`
└── manifests.py        # Manifest loader (targets.yaml)
example_tests/          # Tests *under* ReleaseGuard
targets.yaml            # Target environment manifest
web/                    # Static report viewer
tests/                  # Meta-tests (the framework testing itself)
```

## Manifest format (targets.yaml)

```yaml
targets:
  - name: prod-like
    image: python:3.12-slim
    expected_env:
      DJANGO_SETTINGS_MODULE: app.settings.prod
      DATABASE_URL: postgres://...
    expected_packages:
      - django==5.1.0
      - psycopg2==2.9.10
    expected_files:
      - path: /etc/app/feature-flags.json
        sha256: 2b3a4c5d...
    pytest_args: ["-q", "tests/"]

  - name: staging-py311
    image: python:3.11-slim
    inherit_from: prod-like
    expected_env:
      ENVIRONMENT: staging
```

`inherit_from` lets you express "staging is prod with two overrides"
without copy-paste. The runner resolves inheritance before running.

## Drift checks

Six kinds:

1. **Python version** — `sys.version_info` reported by the target
   matches the manifest's declared version.
2. **Env var presence + value** — every key in `expected_env` is
   set and (where a value is given) matches.
3. **Pinned package versions** — `pip show <pkg>` for every entry in
   `expected_packages`. A higher patch version is a warning; a
   different minor or major is an error.
4. **File checksums** — for files listed in `expected_files`, sha256
   the on-target file and compare. Catches "config map redeployed
   without flagging the change".
5. **Exec probes** — operator-supplied shell commands the target must
   exit 0 from. Things like `nc -z db 5432`, `psql -c "SELECT 1"`.
6. **Free-form** — a `drift_check` pytest marker on individual tests
   so the test author can declare "this test relies on Redis being
   reachable" inline; the marker emits an exec probe automatically.

Drift outcomes are flagged on the report alongside test outcomes.
The exit status of `rg run` is non-zero if either tests fail OR
drift is detected (configurable via `--allow-drift`).

## Pytest plugin

`releaseguard/plugin.py` is a tiny plugin that hooks `pytest_runtest_*`
to capture per-test:

- duration
- captured stdout/stderr
- the resolved drift checks for that test (via the marker)
- the request env at test entry (so a test that mutates env var has
  before/after recorded)

The plugin writes one JSONL event per test to a file the runner picks
up. The output is also valid for any pytest invocation; you can use
the plugin standalone.

## Failure reporting

The static HTML report (`web/`) groups failures into:

- **Real failures** — test exited non-zero with a test_case stack
  trace.
- **Drift-induced** — drift checks failed; tests may or may not have
  failed, but at least one drift indicator was tripped.
- **Flaky** — tests that passed on retry; flagged regardless of
  final pass.
- **Skipped** — surfaced separately so they don't hide.

Each failure gets a fingerprint (sha256 of the file:line + first
exception class) so dashboards can dedupe across runs.

## Performance

The whole thing is meant to run inside CI; runtime budget for a
typical 200-test suite × 3 targets is under 90 seconds wall-clock on
a 2-core runner. Drift checks are cheap — a single Docker exec per
target for the env+packages bundle, plus one per file/probe.

## Non-goals

- **Test framework reinvention.** We don't replace pytest; we wrap
  it. Other runners (rspec, jest) would need their own plugins,
  modeled on the same data shape.
- **Live drift monitoring.** Continuous monitoring of running
  environments is a different product (call it RuntimeGuard).
  ReleaseGuard runs at promote-time only.
- **Automatic remediation.** When drift is detected we report; we
  don't reach into the cluster and reconcile.
