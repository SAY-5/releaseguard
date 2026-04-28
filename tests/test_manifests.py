from __future__ import annotations

from pathlib import Path

from releaseguard.manifests import load_manifest


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_load_simple_yaml(tmp_path):
    p = write(tmp_path, "targets.yaml", """\
targets:
  - name: prod
    image: python:3.12-slim
    expected_env:
      ENVIRONMENT: prod
    expected_packages:
      - pytest
""")
    specs = load_manifest(p)
    assert len(specs) == 1
    assert specs[0].name == "prod"
    assert specs[0].image == "python:3.12-slim"
    assert specs[0].expected_env["ENVIRONMENT"] == "prod"
    assert specs[0].expected_packages == ["pytest"]


def test_inheritance_merges(tmp_path):
    p = write(tmp_path, "targets.yaml", """\
targets:
  - name: prod
    image: python:3.12-slim
    expected_env:
      ENVIRONMENT: prod
      DATABASE_URL: postgres://prod
  - name: staging
    inherit_from: prod
    expected_env:
      ENVIRONMENT: staging
""")
    specs = load_manifest(p)
    by_name = {s.name: s for s in specs}
    assert by_name["staging"].image == "python:3.12-slim"
    assert by_name["staging"].expected_env["ENVIRONMENT"] == "staging"
    assert by_name["staging"].expected_env["DATABASE_URL"] == "postgres://prod"


def test_load_simple_json(tmp_path):
    p = write(tmp_path, "targets.json", """{
        "targets": [
            {"name": "x", "image": "alpine", "expected_env": {"A": "1"}}
        ]
    }""")
    specs = load_manifest(p)
    assert specs[0].name == "x"
    assert specs[0].expected_env == {"A": "1"}
