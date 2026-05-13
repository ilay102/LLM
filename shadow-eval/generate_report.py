"""
Turn pairwise_results.jsonl into a CTO-ready HTML report.

Headlines:
  - Quality: shadow win-or-tie %  (target ≥ 98%)
  - Cost:    total saved + projected annual
  - Latency: p50 / p95 deltas
  - Routing distribution: how often each tier was picked

Includes a per-row appendix so the CTO can audit any judgment.

Usage:
  python generate_report.py --in pairwise_results.jsonl --out report.html
"""
from __future__ import annotations
import argparse
import json
import statistics as stats
from collections import Counter
from pathlib import Path

from jinja2 import Template

TEMPLATE = Template("""<!doctype html>
<html><head><meta charset="utf-8"><title>LLM Inference Optimization — Quality & Cost Report</title>
<style>
 body { font-family: -apple-system, system-ui, sans-serif; max-width: 1100px; margin: 2em auto; color:#111; }
 h1 { font-size: 1.6em; }
 h2 { margin-top: 2em; border-bottom: 1px solid #eee; padding-bottom: 4px; }
 .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1em; margin: 1.5em 0; }
 .kpi { background: #f6f8fa; border-radius: 8px; padding: 1em; }
 .kpi .v { font-size: 1.8em; font-weight: 700; }
 .kpi .l { font-size: 0.85em; color: #555; }
 .ok { color: #137333; }
 .warn { color: #b06000; }
 .bad { color: #b3261e; }
 table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
 th, td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; vertical-align: top; }
 th { background: #fafafa; }
 .pill { display:inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.8em; }
 .pill.tie { background: #eef; color:#225; }
 .pill.shadow { background: #e8f5e9; color:#137333; }
 .pill.baseline { background: #fbe9e7; color:#b3261e; }
 details { margin: 4px 0; }
 code { background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }
</style></head><body>

<h1>LLM Inference Optimization — Quality & Cost Report</h1>
<p>Generated from <code>{{ source }}</code> · {{ n }} prompts evaluated.</p>

<h2>Headline KPIs</h2>
<div class="kpis">
  <div class="kpi"><div class="v {{ 'ok' if win_or_tie >= 0.98 else ('warn' if win_or_tie >= 0.95 else 'bad') }}">{{ '%.1f' % (win_or_tie*100) }}%</div><div class="l">Shadow win-or-tie rate (target ≥ 98%)</div></div>
  <div class="kpi"><div class="v ok">${{ '%.2f' % savings_total }}</div><div class="l">$ saved across {{ n }} calls</div></div>
  <div class="kpi"><div class="v ok">{{ '%.0f' % (savings_pct*100) }}%</div><div class="l">cost reduction vs baseline</div></div>
  <div class="kpi"><div class="v">{{ '%+.0f' % latency_delta_p95 }}ms</div><div class="l">p95 latency Δ (shadow − baseline)</div></div>
</div>

<h2>Quality breakdown (pairwise judge: {{ judge_note }})</h2>
<table>
<tr><th>Verdict</th><th>Count</th><th>Share</th></tr>
<tr><td><span class="pill shadow">SHADOW wins</span></td><td>{{ wins.SHADOW }}</td><td>{{ '%.1f' % (wins.SHADOW/n*100) }}%</td></tr>
<tr><td><span class="pill tie">TIE</span></td><td>{{ wins.TIE }}</td><td>{{ '%.1f' % (wins.TIE/n*100) }}%</td></tr>
<tr><td><span class="pill baseline">BASELINE wins</span></td><td>{{ wins.BASELINE }}</td><td>{{ '%.1f' % (wins.BASELINE/n*100) }}%</td></tr>
</table>

<h2>Cost breakdown</h2>
<table>
<tr><th></th><th>Total $</th><th>$ / call</th><th>Input tokens</th><th>Output tokens</th></tr>
<tr><td>Baseline (Sonnet 4.6 direct)</td><td>${{ '%.4f' % baseline_total }}</td><td>${{ '%.5f' % (baseline_total/n) }}</td><td>{{ baseline_in_tok }}</td><td>{{ baseline_out_tok }}</td></tr>
<tr><td>Shadow (gateway routed)</td><td>${{ '%.4f' % shadow_total }}</td><td>${{ '%.5f' % (shadow_total/n) }}</td><td>{{ shadow_in_tok }}</td><td>{{ shadow_out_tok }}</td></tr>
</table>
<p>If your real volume is <b>1M calls/month</b> at this prompt mix, projected monthly savings: <b>${{ '%.0f' % (savings_total/n*1_000_000) }}</b>.</p>

<h2>Routing distribution (which tier the gateway picked)</h2>
<table>
<tr><th>Model returned</th><th>Calls</th><th>Share</th></tr>
{% for m, c in tier_dist %}
<tr><td><code>{{ m }}</code></td><td>{{ c }}</td><td>{{ '%.1f' % (c/n*100) }}%</td></tr>
{% endfor %}
</table>

<h2>Latency</h2>
<table>
<tr><th></th><th>p50</th><th>p95</th><th>p99</th></tr>
<tr><td>Baseline</td><td>{{ '%.0f' % baseline_p50 }}ms</td><td>{{ '%.0f' % baseline_p95 }}ms</td><td>{{ '%.0f' % baseline_p99 }}ms</td></tr>
<tr><td>Shadow</td><td>{{ '%.0f' % shadow_p50 }}ms</td><td>{{ '%.0f' % shadow_p95 }}ms</td><td>{{ '%.0f' % shadow_p99 }}ms</td></tr>
</table>

<h2>Regressions (shadow LOST) — {{ wins.BASELINE }} cases</h2>
{% if regressions %}
{% for r in regressions %}
<details><summary><b>{{ r.judge_axis }}</b> — {{ r.judge_reason }}</summary>
<p><b>Prompt:</b> {{ r.prompt }}</p>
<p><b>Baseline:</b><br><code>{{ r.baseline_text[:1500] }}</code></p>
<p><b>Shadow ({{ r.gateway_model }}):</b><br><code>{{ r.shadow_text[:1500] }}</code></p>
</details>
{% endfor %}
{% else %}
<p>None — no regressions in this sample.</p>
{% endif %}

<h2>Per-row audit</h2>
<table>
<tr><th>#</th><th>Verdict</th><th>Tier picked</th><th>Δ$</th><th>Prompt (excerpt)</th></tr>
{% for r in rows %}
<tr><td>{{ loop.index }}</td>
    <td><span class="pill {{ r.winner|lower }}">{{ r.winner }}</span></td>
    <td><code>{{ r.gateway_model }}</code></td>
    <td>${{ '%.5f' % (r.baseline_cost - r.shadow_cost) }}</td>
    <td>{{ r.prompt[:140] }}</td></tr>
{% endfor %}
</table>

<p style="margin-top:3em; color:#888; font-size:0.85em;">
Methodology: each prompt was sent to BOTH paths concurrently. The judge ({{ judge_note }})
saw the two answers in randomised A/B order with no provenance metadata. Ties are counted as wins
for SHADOW per the contract definition (cheaper at equal quality is preferred). Costs computed
server-side from token usage × the gateway's pricing table.
</p>

</body></html>""")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", default="pairwise_results.jsonl")
    p.add_argument("--out", default="report.html")
    p.add_argument("--judge", default="claude-sonnet-4-6")
    args = p.parse_args()

    rows: list[dict] = []
    with open(args.inp) as f:
        for line in f:
            rows.append(json.loads(line))
    n = len(rows)
    if n == 0:
        raise SystemExit("no rows in input")

    wins = Counter({"SHADOW": 0, "TIE": 0, "BASELINE": 0})
    for r in rows:
        wins[r["winner"]] += 1
    win_or_tie = (wins["SHADOW"] + wins["TIE"]) / n

    baseline_total = sum(r["baseline_cost"] for r in rows)
    shadow_total = sum(r["shadow_cost"] for r in rows)
    savings_total = baseline_total - shadow_total
    savings_pct = savings_total / baseline_total if baseline_total > 0 else 0

    tier_dist = Counter(r["gateway_model"] for r in rows).most_common()

    b_lat = [r["baseline_latency_ms"] for r in rows]
    s_lat = [r["shadow_latency_ms"] for r in rows]

    regressions = [r for r in rows if r["winner"] == "BASELINE"]

    html = TEMPLATE.render(
        source=args.inp, n=n, judge_note=args.judge,
        win_or_tie=win_or_tie, wins=wins,
        baseline_total=baseline_total, shadow_total=shadow_total,
        savings_total=savings_total, savings_pct=savings_pct,
        baseline_in_tok=sum(r["baseline_in_tokens"] for r in rows),
        baseline_out_tok=sum(r["baseline_out_tokens"] for r in rows),
        shadow_in_tok=sum(r["shadow_in_tokens"] for r in rows),
        shadow_out_tok=sum(r["shadow_out_tokens"] for r in rows),
        tier_dist=tier_dist,
        baseline_p50=percentile(b_lat, 0.5), baseline_p95=percentile(b_lat, 0.95), baseline_p99=percentile(b_lat, 0.99),
        shadow_p50=percentile(s_lat, 0.5), shadow_p95=percentile(s_lat, 0.95), shadow_p99=percentile(s_lat, 0.99),
        latency_delta_p95=percentile(s_lat, 0.95) - percentile(b_lat, 0.95),
        regressions=regressions, rows=rows,
    )
    Path(args.out).write_text(html)
    print(f"wrote {args.out}")
    print(f"  win-or-tie: {win_or_tie*100:.1f}%   savings: ${savings_total:.4f} ({savings_pct*100:.0f}%)")


if __name__ == "__main__":
    main()
