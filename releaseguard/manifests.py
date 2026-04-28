"""Loader for targets.yaml.

We accept a tiny subset of YAML — enough for the manifests we care
about. Stays a pure-Python module without yanking in PyYAML for the
default install. (PyYAML is in the optional `[yaml]` extra for richer
manifests; the default takes a simple JSON or JSON-with-comments file.)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from releaseguard.targets import TargetSpec


def load_manifest(path: Path) -> list[TargetSpec]:
    text = path.read_text()
    data = _parse_jsonish(text) if path.suffix == ".json" else _parse_yaml(text)
    raw_targets = data.get("targets", [])
    specs = [_to_spec(t) for t in raw_targets]
    return _resolve_inheritance(specs)


def _to_spec(d: dict) -> TargetSpec:
    return TargetSpec(
        name=d["name"],
        image=d.get("image", ""),
        inherit_from=d.get("inherit_from"),
        expected_env=dict(d.get("expected_env", {})),
        expected_packages=list(d.get("expected_packages", [])),
        expected_files=list(d.get("expected_files", [])),
        exec_probes=list(d.get("exec_probes", [])),
        pytest_args=list(d.get("pytest_args", ["-q"])),
    )


def _resolve_inheritance(specs: list[TargetSpec]) -> list[TargetSpec]:
    by_name = {s.name: s for s in specs}
    out: list[TargetSpec] = []
    for s in specs:
        if not s.inherit_from:
            out.append(s)
            continue
        parent = by_name.get(s.inherit_from)
        if parent is None:
            raise ValueError(f"target {s.name!r} inherits from unknown {s.inherit_from!r}")
        out.append(s.merged_with(parent))
    return out


def _parse_jsonish(text: str) -> dict:
    # Strip // comments before parsing.
    no_comments = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return json.loads(no_comments)


def _parse_yaml(text: str) -> dict:
    """Minimal YAML parser supporting the subset we use:
    `key: value`, lists with `-`, simple nesting via two-space indent."""
    lines = [ln.rstrip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    return _parse_block(lines, 0, 0)[0]


def _parse_block(lines: list[str], idx: int, indent: int):
    out: dict | list = {}
    while idx < len(lines):
        line = lines[idx]
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent < indent:
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            if not isinstance(out, list):
                out = []
            item_text = stripped[2:]
            if ":" in item_text and not item_text.startswith('"'):
                # an inline key on the same line as the dash; rewrite as block
                rewritten = [item_text] + lines[idx + 1:]
                # Indent of the block under the dash is indent+2
                # We treat dash item as an isolated block.
                # Find the next item at same indent (dash) or shallower
                end = idx + 1
                while end < len(lines):
                    ln = lines[end]
                    li = len(ln) - len(ln.lstrip())
                    if li < cur_indent + 2:
                        break
                    end += 1
                sub_lines = [item_text] + [ln[2:] for ln in lines[idx + 1:end]]
                d, _ = _parse_block(sub_lines, 0, 0)
                out.append(d)
                idx = end
                continue
            out.append(_parse_scalar(item_text))
            idx += 1
            continue
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                if not isinstance(out, dict):
                    out = {}
                out[key] = _parse_scalar(val)
                idx += 1
            else:
                # Nested block
                if not isinstance(out, dict):
                    out = {}
                sub, idx = _parse_block(lines, idx + 1, cur_indent + 2)
                out[key] = sub
        else:
            idx += 1
    return out, idx


def _parse_scalar(s: str):
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s == "true":  return True
    if s == "false": return False
    if s == "null":  return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s
