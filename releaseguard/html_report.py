"""Static HTML report generator.

Takes a `RunReport` (or a JSON file produced by one) and writes a
single self-contained HTML file. No JS dependencies, no fetch — the
data is inlined as JSON; the page is opened from the filesystem and
rendered by a small inline `<script>`. CI uploads this as an artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_html(data: dict[str, Any]) -> str:
    """Return a single self-contained HTML document for the given report."""
    payload = json.dumps(data).replace("</", "<\\/")  # avoid premature </script>
    return _TEMPLATE.replace("__PAYLOAD__", payload)


def write(report_json: Path, out: Path) -> None:
    data = json.loads(report_json.read_text())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data))


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>ReleaseGuard · Run Report</title>
<style>
:root {
  --bg:#0d1014; --bg2:#13181f; --line:#1e2530; --line2:#2a3340;
  --fg:#e2e6ec; --fg-dim:#9aa3b0; --fg-mute:#5b6470;
  --ok:#7be08a; --warn:#f5c542; --err:#ff6b6b; --info:#6dd9ff; --drift:#ff8a4c;
  --mono:"JetBrains Mono", ui-monospace, monospace;
  --sans:"Inter", system-ui, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin:0; padding:0; background:var(--bg); color:var(--fg); font-family:var(--sans); font-size:14px; }
header { padding:20px 28px; border-bottom:1px solid var(--line); background:var(--bg2); display:flex; gap:18px; align-items:baseline; }
header h1 { margin:0; font-size:20px; letter-spacing:-0.01em; font-weight:700; }
header .badge { font-family:var(--mono); font-size:11px; letter-spacing:0.18em; text-transform:uppercase; padding:3px 10px; border-radius:3px; }
header .badge.passed { background:var(--ok); color:#0a1410; }
header .badge.failed { background:var(--err); color:#1a0707; }
header .badge.drift  { background:var(--drift); color:#1a0900; }
header .meta { margin-left:auto; font-family:var(--mono); font-size:11px; color:var(--fg-mute); letter-spacing:0.06em; }

.target { border-bottom:1px solid var(--line); padding:18px 28px; }
.target h2 { margin:0 0 12px; font-size:18px; font-weight:600; }
.target .summary { display:flex; gap:20px; margin-bottom:14px; font-family:var(--mono); font-size:12px; }
.target .summary span { color:var(--fg-dim); }
.target .summary b { color:var(--fg); font-weight:600; padding-left:6px; font-variant-numeric:tabular-nums; }
.target .summary b.passed { color:var(--ok); }
.target .summary b.failed { color:var(--err); }
.target .summary b.skipped { color:var(--fg-mute); }
.target .summary b.drift   { color:var(--drift); }

.section-title { font-family:var(--mono); font-size:10.5px; letter-spacing:0.22em; text-transform:uppercase; color:var(--fg-mute); margin:18px 0 8px; }

table { width:100%; border-collapse:collapse; font-size:12.5px; }
th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); }
th { font-family:var(--mono); font-size:9.5px; letter-spacing:0.22em; text-transform:uppercase; color:var(--fg-mute); font-weight:700; border-bottom:1px solid var(--line2); }
td.nodeid { font-family:var(--mono); font-size:11px; color:var(--fg-dim); }
td.outcome.passed  { color:var(--ok); font-family:var(--mono); font-size:10.5px; letter-spacing:0.18em; text-transform:uppercase; }
td.outcome.failed  { color:var(--err); font-family:var(--mono); font-size:10.5px; letter-spacing:0.18em; text-transform:uppercase; }
td.outcome.skipped { color:var(--fg-mute); font-family:var(--mono); font-size:10.5px; letter-spacing:0.18em; text-transform:uppercase; }
td.fp { font-family:var(--mono); font-size:10.5px; color:var(--fg-mute); }
td.dur { text-align:right; font-family:var(--mono); font-variant-numeric:tabular-nums; color:var(--fg-dim); }
.long { white-space:pre-wrap; font-family:var(--mono); font-size:11.5px; color:var(--err); background:var(--bg2); padding:8px 12px; border-left:3px solid var(--err); margin-top:6px; }

.drift td.status.ok   { color:var(--ok); }
.drift td.status.warn { color:var(--warn); }
.drift td.status.fail { color:var(--err); }

footer { padding:18px 28px; color:var(--fg-mute); font-family:var(--mono); font-size:10.5px; letter-spacing:0.06em; }
</style>
</head>
<body>
<div id="root"></div>
<script>
const data = __PAYLOAD__;
const root = document.getElementById("root");
function el(t,a={},...c){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==="class")e.className=v;else if(k==="html")e.innerHTML=v;else if(v!=null)e.setAttribute(k,v);}for(const x of c.flat()){if(x==null)continue;e.append(typeof x==="string"||typeof x==="number"?document.createTextNode(String(x)):x);}return e;}

function render() {
  const status = data.overall_status || "unknown";
  root.append(el("header", {},
    el("h1", {}, "ReleaseGuard"),
    el("span", {class:"badge "+status}, status.toUpperCase()),
    el("div", {class:"meta"}, "started " + (data.started_at||"—") + " · " + (data.runs?.length||0) + " target(s)"),
  ));
  for (const r of (data.runs || [])) {
    root.append(renderTarget(r));
  }
  root.append(el("footer", {}, "ReleaseGuard v0.1 · self-contained report — no network calls."));
}

function renderTarget(r) {
  const s = r.summary || {passed:0,failed:0,skipped:0};
  const sec = el("section", {class:"target"},
    el("h2", {}, r.target),
    el("div", {class:"summary"},
      el("span", {}, "passed",  el("b", {class:"passed"},  s.passed||0)),
      el("span", {}, "failed",  el("b", {class:"failed"},  s.failed||0)),
      el("span", {}, "skipped", el("b", {class:"skipped"}, s.skipped||0)),
      r.drift ? el("span", {}, "drift", el("b", {class:"drift"}, r.drift.summary?.fail||0)) : null,
      el("span", {}, "fingerprint", el("b", {}, r.fingerprint||"—")),
    ),
  );
  if (r.drift && r.drift.checks?.length) {
    sec.append(el("div", {class:"section-title"}, "Drift checks"));
    sec.append(renderDriftTable(r.drift.checks));
  }
  if (r.outcomes?.length) {
    sec.append(el("div", {class:"section-title"}, "Tests"));
    sec.append(renderTestTable(r.outcomes));
  }
  return sec;
}

function renderDriftTable(checks) {
  const t = el("table", {class:"drift"});
  t.append(el("tr", {},
    ["check","kind","expected","actual","detail"].map(h => el("th", {}, h))));
  for (const c of checks) {
    t.append(el("tr", {},
      el("td", {class:"nodeid"}, c.name),
      el("td", {class:"nodeid"}, c.kind),
      el("td", {class:"nodeid"}, c.expected),
      el("td", {class:"nodeid"}, c.actual),
      el("td", {class:"status "+c.status}, (c.status||"").toUpperCase() + (c.detail ? " · "+c.detail : "")),
    ));
  }
  return t;
}

function renderTestTable(outcomes) {
  const t = el("table");
  t.append(el("tr", {},
    ["nodeid","outcome","duration","fingerprint","drift"].map(h => el("th", {}, h))));
  for (const o of outcomes) {
    const driftBad = (o.drift_checks || []).filter(d => !d.ok);
    const tr = el("tr", {},
      el("td", {class:"nodeid"}, o.nodeid),
      el("td", {class:"outcome "+(o.outcome||"")}, o.outcome||""),
      el("td", {class:"dur"}, (o.duration_s ?? o.duration ?? 0).toFixed(3)+"s"),
      el("td", {class:"fp"}, o.fingerprint || ""),
      el("td", {class:"status "+(driftBad.length ? "fail" : "ok")},
         driftBad.length ? driftBad.map(d => d.name).join(", ") : ((o.drift_checks||[]).length ? "ok" : "—")),
    );
    t.append(tr);
    if (o.outcome === "failed" && o.longrepr) {
      const wide = el("tr", {},
        el("td", {colspan:"5"}, el("div", {class:"long"}, o.longrepr.slice(0,2000))),
      );
      t.append(wide);
    }
  }
  return t;
}

render();
</script>
</body>
</html>"""
