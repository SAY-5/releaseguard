# ReleaseGuard

A CI/CD test infrastructure focused on a specific failure mode:
**tests that pass despite the environment being out of spec.**
ReleaseGuard sits between `pytest` and `kubectl apply`, runs the same
suite across N target environments, and emits a single structured
report that surfaces drift as a first-class signal next to the test
outcome.

## What's interesting

- **Drift checks alongside tests.** Six kinds — Python version, env
  vars, pinned packages, file checksums, exec probes, and (planned)
  inline `drift_check` markers on individual tests. A green test run
  with `drift_detected` blocks the release by default; the operator
  has to explicitly `--allow-drift` to ship anyway.
- **Manifest with inheritance.** `targets.yaml` declares one entry
  per environment; `inherit_from` lets staging be "prod with two
  overrides" instead of copy-paste. The loader is hand-rolled
  (no PyYAML in the default install) and supports the subset we use.
- **Pytest plugin auto-loaded.** Registered via `pytest11` entry
  point — drop `--rg-out events.jsonl` onto any pytest invocation
  and you get structured per-test events the runner consolidates.
- **Failure fingerprints.** Each test failure gets a sha256 of
  `file:line + first exception line`. Dashboards can dedupe across
  runs without seeing the same flake counted as five distinct bugs.

## Quick start

```bash
pip install -e ".[dev]"
rg drift                   # drift checks only, against the local shell
rg run --manifest targets.yaml --out runs/report.json
cat runs/report.json | jq .overall_status
```

For the full per-target Docker run:

```bash
docker compose up -d --build
docker run --rm releaseguard:ci run --manifest /srv/targets.yaml
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the design (drift
taxonomy, manifest format, runner, plugin, reporting).

## Tests (16 green)

```
test_drift.py       env present + correct
                    env missing → fail
                    env value mismatch → fail
                    package pinned match (presence-only)
                    package missing → fail
                    probe exit=0 passes
                    probe exit≠0 fails
                    drift report counts
test_manifests.py   load simple yaml
                    inheritance merges (staging from prod)
                    load json manifest
test_runner.py      passing suite → overall passed
                    failing suite → overall failed
                    drift detected blocks release (overall=drift)
                    --allow-drift lets passing tests promote
                    report.json round-trip with v1 schema
```

## Companion projects

Part of an eleven-repo set under [github.com/SAY-5](https://github.com/SAY-5):
canvaslive, pluginforge, agentlab, payflow, queryflow, datachat,
distributedkv, jobagent, inferencegateway, ticketsearch, netprobekit,
**releaseguard**.

## License

MIT.
