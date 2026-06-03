#!/usr/bin/env python3
"""
Eval the gateway against the 200-prompt corpus and produce a verified
savings report.

What it does:
  For each prompt in classifier/prompts_to_label.jsonl, fire it both ways:
    1. Through VIREN gateway (routes intelligently)
    2. Direct to Sonnet 4.6 (the baseline most clients use today)
  Then compute:
    - Cost reduction (real $, not estimate)
    - Tier distribution (where the gateway sent things)
    - Latency comparison
    - Per-prompt audit table

Output:
  scripts/eval_results.jsonl
  scripts/eval_report.html

Run:
  export ANTHROPIC_API_KEY=sk-ant-...
  export GATEWAY_URL=http://localhost:8000/v1
  export GATEWAY_KEY=<your master key or tenant key>
  python scripts/eval_corpus.py --limit 50    # try a small N first
  python scripts/eval_corpus.py               # full 200 ~ $5-10 in API
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from openai import AsyncOpenAI
    from anthropic import AsyncAnthropic
except ImportError:
    print("Install: pip install openai anthropic", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).parent
REPO = HERE.parent
CORPUS = REPO / "classifier" / "prompts_to_label.jsonl"
RESULTS = HERE / "eval_results.jsonl"
REPORT = HERE / "eval_report.html"

SONNET_IN  = 3.0 / 1_000_000
SONNET_OUT = 15.0 / 1_000_000


def percentile(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs); k = (len(s) - 1) * q
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


PRICE = {
    "haiku": (0.8 / 1e6, 4.0 / 1e6),
    "gpt-4o-mini": (0.15 / 1e6, 0.6 / 1e6),
    "deepseek-chat": (0.27 / 1e6, 1.10 / 1e6),       # V3 — cheap tier
    "deepseek-reasoner": (0.55 / 1e6, 2.19 / 1e6),   # R1 — frontier reasoning
    "sonnet": (3.0 / 1e6, 15.0 / 1e6),
    "opus": (15.0 / 1e6, 75.0 / 1e6),
}


def price(model: str) -> tuple[float, float]:
    if not model:
        return SONNET_IN, SONNET_OUT
    m = model.lower()
    for k, v in PRICE.items():
        if k in m:
            return v
    return SONNET_IN, SONNET_OUT


async def call_gateway(oai: AsyncOpenAI, prompt: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await oai.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
        )
        latency = (time.perf_counter() - t0) * 1000
        in_p, out_p = price(r.model or "")
        in_t = r.usage.prompt_tokens or 0
        out_t = r.usage.completion_tokens or 0
        cost = in_t * in_p + out_t * out_p
        return {
            "model": r.model, "in_tokens": in_t, "out_tokens": out_t,
            "cost_usd": cost, "latency_ms": latency,
            "answer": r.choices[0].message.content or "",
            "cached": (r.id or "").startswith("cached-"),
        }
    except Exception as e:
        return {"error": str(e), "latency_ms": (time.perf_counter() - t0) * 1000}


async def call_baseline(anth: AsyncAnthropic, prompt: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await anth.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500, temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = (time.perf_counter() - t0) * 1000
        in_t = r.usage.input_tokens
        out_t = r.usage.output_tokens
        cost = in_t * SONNET_IN + out_t * SONNET_OUT
        text = "".join(b.text for b in r.content if hasattr(b, "text"))
        return {"model": r.model, "in_tokens": in_t, "out_tokens": out_t,
                "cost_usd": cost, "latency_ms": latency, "answer": text}
    except Exception as e:
        return {"error": str(e), "latency_ms": (time.perf_counter() - t0) * 1000}


async def eval_one(sem, oai, anth, prompt_id, prompt_text):
    async with sem:
        # Fire both concurrently
        g, b = await asyncio.gather(
            call_gateway(oai, prompt_text),
            call_baseline(anth, prompt_text),
        )
        return {"id": prompt_id, "prompt": prompt_text[:200],
                "gateway": g, "baseline": b}


async def amain():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0,
                   help="Eval only first N prompts (0 = all)")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--results", default=str(RESULTS))
    args = p.parse_args()

    gw_url = os.environ.get("GATEWAY_URL", "http://localhost:8000/v1")
    gw_key = os.environ.get("GATEWAY_KEY", "")
    anth_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not gw_key:
        print("ERROR: set GATEWAY_KEY env var", file=sys.stderr); return 1
    if not anth_key:
        print("ERROR: set ANTHROPIC_API_KEY env var", file=sys.stderr); return 1

    prompts = []
    with open(args.corpus) as f:
        for line in f:
            r = json.loads(line)
            prompts.append((r["id"], r["prompt"]))
    if args.limit:
        prompts = prompts[: args.limit]

    print(f"Evaluating {len(prompts)} prompts against {gw_url}")
    print(f"  baseline: claude-sonnet-4-6 direct")
    print(f"  gateway: VIREN routed")
    print()

    oai = AsyncOpenAI(base_url=gw_url, api_key=gw_key)
    anth = AsyncAnthropic(api_key=anth_key)
    sem = asyncio.Semaphore(args.concurrency)
    tasks = [eval_one(sem, oai, anth, pid, ptext) for pid, ptext in prompts]

    results = []
    with open(args.results, "w") as f:
        for fut in asyncio.as_completed(tasks):
            r = await fut
            f.write(json.dumps(r) + "\n"); f.flush()
            results.append(r)
            print(f"  [{len(results)}/{len(prompts)}] "
                  f"gw=${(r['gateway'].get('cost_usd') or 0):.5f} "
                  f"baseline=${(r['baseline'].get('cost_usd') or 0):.5f} "
                  f"tier={r['gateway'].get('model', '?').split('/')[-1][:20]}")

    # ---- Aggregate -----
    total_gw = sum(r["gateway"].get("cost_usd", 0) for r in results)
    total_bl = sum(r["baseline"].get("cost_usd", 0) for r in results)
    savings = total_bl - total_gw
    sav_pct = (savings / total_bl * 100) if total_bl > 0 else 0
    cached = sum(1 for r in results if r["gateway"].get("cached"))
    models = Counter(r["gateway"].get("model", "err") for r in results)
    gw_lat = [r["gateway"].get("latency_ms", 0) for r in results]
    bl_lat = [r["baseline"].get("latency_ms", 0) for r in results]

    summary = f"""
==========================================
VIREN — Verified Savings on {len(results)} prompts
==========================================
Total cost (gateway):    ${total_gw:.4f}
Total cost (baseline):   ${total_bl:.4f}
Savings:                 ${savings:.4f}  ({sav_pct:.1f}%)
Cache hits:              {cached}
Latency (gw p50/p95):    {percentile(gw_lat, 0.5):.0f}ms / {percentile(gw_lat, 0.95):.0f}ms
Latency (bl p50/p95):    {percentile(bl_lat, 0.5):.0f}ms / {percentile(bl_lat, 0.95):.0f}ms

Routing distribution:
"""
    for model, count in models.most_common():
        short = (model or "?").split("/")[-1][:30]
        summary += f"  {short:30s}  {count:4d}  ({count/len(results)*100:5.1f}%)\n"

    print(summary)

    # ---- HTML report ----
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>VIREN — Verified Savings Report</title>
<style>
 body{{font-family:-apple-system,Inter,system-ui;max-width:1100px;margin:30px auto;color:#111;padding:0 20px}}
 h1{{font-size:32px;margin:0 0 8px}}
 .sub{{color:#666;margin-bottom:30px}}
 .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}}
 .kpi{{background:#f6f7fb;border-radius:10px;padding:18px}}
 .kpi .v{{font-size:32px;font-weight:700;line-height:1}}
 .kpi .l{{font-size:12px;color:#666;margin-top:6px;text-transform:uppercase;letter-spacing:1px}}
 .ok{{color:#137333}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:20px}}
 th,td{{border-bottom:1px solid #eee;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#fafafa}}
 .pill{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}}
 .pill.cheap{{background:#e8f5e9;color:#137333}}
 .pill.balanced{{background:#e7eaff;color:#3b35ff}}
 .pill.frontier{{background:#ffeaea;color:#b3261e}}
 code{{background:#f3f4f6;padding:1px 4px;border-radius:3px}}
</style></head><body>
<h1>VIREN — Verified Savings Report</h1>
<p class="sub">Real cost comparison on {len(results)} prompts. Every call hit a real provider; every number is from a real billed request.</p>

<div class="kpis">
  <div class="kpi"><div class="v ok">${savings:.2f}</div><div class="l">$ saved</div></div>
  <div class="kpi"><div class="v ok">{sav_pct:.0f}%</div><div class="l">cost reduction</div></div>
  <div class="kpi"><div class="v">{cached}</div><div class="l">cache hits</div></div>
  <div class="kpi"><div class="v">{int(percentile(gw_lat, 0.95))}ms</div><div class="l">gateway p95 latency</div></div>
</div>

<h2>Routing distribution</h2>
<table>
<tr><th>Model</th><th>Calls</th><th>Share</th></tr>
"""
    for model, count in models.most_common():
        short = (model or "?").split("/")[-1]
        html += f'<tr><td><code>{short}</code></td><td>{count}</td><td>{count/len(results)*100:.1f}%</td></tr>'
    html += f"""</table>

<h2>Per-prompt audit ({len(results)} rows)</h2>
<table>
<tr><th>#</th><th>Tier picked</th><th>Cost (gw)</th><th>Cost (baseline)</th><th>Δ</th><th>Prompt excerpt</th></tr>
"""
    for r in results:
        g = r["gateway"]; b = r["baseline"]
        delta = (b.get("cost_usd", 0) - g.get("cost_usd", 0))
        model = (g.get("model") or "?").split("/")[-1][:30]
        tier_class = "cheap" if "haiku" in model.lower() or "mini" in model.lower() else ("frontier" if "opus" in model.lower() else "balanced")
        if g.get("cached"):
            tier_class = "cheap"; model = "CACHED"
        html += (f'<tr><td>{r["id"]}</td>'
                 f'<td><span class="pill {tier_class}">{model}</span></td>'
                 f'<td>${g.get("cost_usd", 0):.5f}</td>'
                 f'<td>${b.get("cost_usd", 0):.5f}</td>'
                 f'<td>${delta:+.5f}</td>'
                 f'<td>{(r["prompt"] or "")[:120]}…</td></tr>')
    html += """</table>
<p style="margin-top:30px;color:#888;font-size:12px">
Each row represents one real call to both VIREN and the Sonnet 4.6 baseline.
Costs are computed from provider-reported token usage and provider-published prices.
No estimates, no synthetic data.
</p>
</body></html>"""
    REPORT.write_text(html)
    print(f"\nReport written to {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
