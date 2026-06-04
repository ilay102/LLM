#!/usr/bin/env python3
"""
measure_overhead.py — answer the buyer question "how much latency do you add?"
with a real number, on real infra.

Buyer view: cost doesn't matter if you add 300ms to my p95. We need a defensible
"VIREN adds < X ms p95" number, NOT just total wall-clock.

This script:
  1. Fires N requests *direct* to a provider (skipping VIREN entirely) to
     measure baseline provider RTT.
  2. Fires the same N requests through VIREN with model="auto".
  3. Computes the OVERHEAD = (VIREN latency) - (direct provider latency for
     the same model the gateway picked), per-call paired.
  4. Reports p50, p95, p99 of the OVERHEAD distribution.
  5. Writes a CTO-grade HTML report.

This is the right number to publish — total-latency comparison is misleading
because it bundles provider variance into our overhead.

Usage:
  GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY=$GATEWAY_MASTER_KEY \\
  ANTHROPIC_API_KEY=$K \\
  python3 scripts/measure_overhead.py --n 30 --concurrency 4

Cost: ~$0.20 for 30 prompts. Run it once per release.
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
DEFAULT_CORPUS = REPO / "eval" / "corpus_v1.jsonl"
if not DEFAULT_CORPUS.exists():
    DEFAULT_CORPUS = REPO / "classifier" / "prompts_to_label.jsonl"


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _to_messages(payload):
    if isinstance(payload, list):
        return payload
    return [{"role": "user", "content": payload}]


def _split_system_for_anthropic(messages):
    sys_str = "\n".join(m["content"] for m in messages
                        if m.get("role") == "system" and isinstance(m.get("content"), str))
    convo = [m for m in messages if m.get("role") != "system"]
    return (sys_str or None), convo


async def call_gateway(oai: AsyncOpenAI, messages) -> dict:
    msgs = _to_messages(messages)
    t0 = time.perf_counter()
    try:
        r = await oai.chat.completions.create(
            model="auto", messages=msgs, max_tokens=300, temperature=0.2,
        )
        dt = (time.perf_counter() - t0) * 1000
        return {
            "ok": True, "model": r.model, "ms": dt,
            "in_tokens": r.usage.prompt_tokens, "out_tokens": r.usage.completion_tokens,
        }
    except Exception as e:
        return {"ok": False, "err": str(e)[:120], "ms": (time.perf_counter() - t0) * 1000}


async def call_direct_anthropic(anth: AsyncAnthropic, model: str, messages) -> dict:
    msgs = _to_messages(messages)
    system, convo = _split_system_for_anthropic(msgs)
    kwargs = dict(model=model, max_tokens=300, temperature=0.2, messages=convo)
    if system:
        kwargs["system"] = system
    t0 = time.perf_counter()
    try:
        r = await anth.messages.create(**kwargs)
        dt = (time.perf_counter() - t0) * 1000
        return {"ok": True, "model": r.model, "ms": dt,
                "in_tokens": r.usage.input_tokens, "out_tokens": r.usage.output_tokens}
    except Exception as e:
        return {"ok": False, "err": str(e)[:120], "ms": (time.perf_counter() - t0) * 1000}


async def call_direct_openai_compat(client, model: str, messages, label: str) -> dict:
    """Direct call against an OpenAI-compatible endpoint (OpenAI itself, or
    DeepSeek's OpenAI-compatible endpoint at https://api.deepseek.com/v1)."""
    msgs = _to_messages(messages)
    t0 = time.perf_counter()
    try:
        r = await client.chat.completions.create(
            model=model, messages=msgs, max_tokens=300, temperature=0.2,
        )
        dt = (time.perf_counter() - t0) * 1000
        return {"ok": True, "model": r.model, "ms": dt,
                "in_tokens": r.usage.prompt_tokens, "out_tokens": r.usage.completion_tokens,
                "provider": label}
    except Exception as e:
        return {"ok": False, "err": str(e)[:120], "ms": (time.perf_counter() - t0) * 1000,
                "provider": label}


def classify_model(gw_model: str) -> tuple[str, str] | None:
    """Return (provider, direct_model_name) for the gateway's pick, or None
    if we can't pair (no direct client / unknown model)."""
    if not gw_model:
        return None
    m = gw_model.lower()
    if "haiku" in m:           return ("anthropic", "claude-haiku-4-5")
    if "sonnet" in m:          return ("anthropic", "claude-sonnet-4-6")
    if "opus" in m:            return ("anthropic", "claude-opus-4-8")
    if "gpt-4o-mini" in m:     return ("openai", "gpt-4o-mini")
    if "gpt-4o" in m:          return ("openai", "gpt-4o")
    if "deepseek-v4-pro" in m: return ("deepseek", "deepseek-v4-pro")
    if "deepseek-v4-flash" in m or "deepseek-chat" in m: return ("deepseek", "deepseek-chat")
    if "deepseek-reasoner" in m: return ("deepseek", "deepseek-reasoner")
    return None


async def one(sem, oai_gw, anth_direct, openai_direct, deepseek_direct,
              prompt_id, payload):
    async with sem:
        # Run through the gateway first
        g = await call_gateway(oai_gw, payload)
        # If we can pair against a direct client, do so
        cls = classify_model(g.get("model", "")) if g.get("ok") else None
        d = None
        if cls:
            provider, direct_model = cls
            if provider == "anthropic" and anth_direct is not None:
                d = await call_direct_anthropic(anth_direct, direct_model, payload)
            elif provider == "openai" and openai_direct is not None:
                d = await call_direct_openai_compat(openai_direct, direct_model, payload, "openai")
            elif provider == "deepseek" and deepseek_direct is not None:
                d = await call_direct_openai_compat(deepseek_direct, direct_model, payload, "deepseek")
        overhead_ms = None
        if g.get("ok") and d and d.get("ok"):
            overhead_ms = g["ms"] - d["ms"]
        return {
            "id": prompt_id,
            "gateway": g, "direct": d,
            "overhead_ms": overhead_ms,
        }


async def amain():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    p.add_argument("--out-html", default=str(HERE / "overhead_report.html"))
    p.add_argument("--out-jsonl", default=str(HERE / "overhead_results.jsonl"))
    args = p.parse_args()

    gw_url = os.environ.get("GATEWAY_URL", "http://localhost:8000/v1")
    gw_key = os.environ.get("GATEWAY_KEY", "")
    anth_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not gw_key:
        print("ERROR: set GATEWAY_KEY", file=sys.stderr); return 1
    if not anth_key and not openai_key:
        print("ERROR: set ANTHROPIC_API_KEY and/or OPENAI_API_KEY", file=sys.stderr); return 1

    rows = []
    with open(args.corpus, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            payload = r.get("messages") if r.get("messages") else r.get("prompt", "")
            rows.append((r["id"], payload))
            if len(rows) >= args.n:
                break

    print(f"Measuring overhead on {len(rows)} prompts. Gateway={gw_url}")
    print(f"  Direct clients: anthropic={'on' if anth_key else 'OFF'} "
          f"openai={'on' if openai_key else 'OFF'} "
          f"deepseek={'on' if deepseek_key else 'OFF'}")
    oai_gw = AsyncOpenAI(base_url=gw_url, api_key=gw_key)
    anth_direct = AsyncAnthropic(api_key=anth_key) if anth_key else None
    openai_direct = AsyncOpenAI(api_key=openai_key) if openai_key else None
    deepseek_direct = (AsyncOpenAI(base_url="https://api.deepseek.com/v1",
                                   api_key=deepseek_key) if deepseek_key else None)
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*[
        one(sem, oai_gw, anth_direct, openai_direct, deepseek_direct, pid, p)
        for pid, p in rows
    ])

    with open(args.out_jsonl, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # ---- Aggregate ----
    gw_lat = [r["gateway"]["ms"] for r in results if r["gateway"].get("ok")]
    dr_lat = [r["direct"]["ms"] for r in results if r["direct"] and r["direct"].get("ok")]
    overheads = [r["overhead_ms"] for r in results if r["overhead_ms"] is not None]
    paired = len(overheads)
    skipped = len(results) - paired
    model_dist = Counter(r["gateway"].get("model", "?") for r in results if r["gateway"].get("ok"))

    p50 = percentile(overheads, 0.5)
    p95 = percentile(overheads, 0.95)
    p99 = percentile(overheads, 0.99)
    avg = statistics.mean(overheads) if overheads else 0

    print()
    print(f"  Paired samples: {paired}   (skipped non-Anthropic: {skipped})")
    print(f"  Overhead p50: {p50:>7.0f} ms")
    print(f"  Overhead p95: {p95:>7.0f} ms")
    print(f"  Overhead p99: {p99:>7.0f} ms")
    print(f"  Overhead avg: {avg:>7.0f} ms")
    if gw_lat: print(f"  Gateway total p95: {percentile(gw_lat, 0.95):.0f} ms")
    if dr_lat: print(f"  Direct  total p95: {percentile(dr_lat, 0.95):.0f} ms")

    # ---- HTML ----
    verdict_color = "#137333" if p95 < 100 else ("#b06000" if p95 < 300 else "#b3261e")
    verdict_text = ("Excellent" if p95 < 100 else
                    "Acceptable" if p95 < 300 else "Needs attention")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>VIREN — Latency Overhead Report</title>
<style>
 body{{font-family:-apple-system,Inter,system-ui;max-width:1000px;margin:30px auto;color:#111;padding:0 20px}}
 h1{{font-size:30px;margin:0 0 4px}}
 .sub{{color:#666;margin-bottom:24px}}
 .verdict{{background:{verdict_color};color:white;border-radius:8px;padding:14px 20px;font-weight:700;font-size:16px;margin:16px 0}}
 .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
 .kpi{{background:#f6f7fb;border-radius:10px;padding:18px}}
 .kpi .v{{font-size:30px;font-weight:800;line-height:1;color:#6d63ff}}
 .kpi .l{{font-size:11px;margin-top:6px;color:#666;text-transform:uppercase;letter-spacing:1px}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:18px}}
 th,td{{border-bottom:1px solid #eee;padding:8px 10px;text-align:left}}
 th{{background:#fafafa;text-transform:uppercase;font-size:11px;letter-spacing:1px;color:#666}}
 code{{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px}}
</style></head><body>
<h1>VIREN — Latency Overhead Report</h1>
<p class="sub">Paired apples-to-apples comparison: same prompt to the gateway
(model='auto') and direct to the provider (the model the gateway picked).
Overhead = gateway latency &minus; direct latency. Sample: {paired} paired
calls.</p>

<div class="verdict">Verdict: VIREN adds {p95:.0f} ms at p95 — <b>{verdict_text}</b></div>

<div class="kpis">
  <div class="kpi"><div class="v">{p50:.0f} ms</div><div class="l">Overhead p50</div></div>
  <div class="kpi"><div class="v">{p95:.0f} ms</div><div class="l">Overhead p95</div></div>
  <div class="kpi"><div class="v">{p99:.0f} ms</div><div class="l">Overhead p99</div></div>
  <div class="kpi"><div class="v">{avg:.0f} ms</div><div class="l">Overhead avg</div></div>
</div>

<h2>What's in the overhead</h2>
<ul>
  <li>Auth + tenant lookup (SQLite, sub-ms)</li>
  <li>PII redaction (Presidio, ~10-30 ms on typical prompts)</li>
  <li>Classifier (rule layer + bge-small nearest-centroid, ~5-15 ms)</li>
  <li>Semantic cache lookup (Redis HNSW, ~5-10 ms)</li>
  <li>Prompt-cache breakpoint injection (sub-ms)</li>
  <li>LiteLLM router selection (sub-ms)</li>
</ul>
<p>Note: gateway-side overhead does NOT include provider RTT — that's
subtracted out by the paired baseline.</p>

<h2>Routing distribution (over the sample)</h2>
<table><tr><th>Model the gateway picked</th><th>Calls</th></tr>
"""
    for m, c in model_dist.most_common():
        html += f"<tr><td><code>{m or '?'}</code></td><td>{c}</td></tr>"
    html += "</table>"

    html += """
<h2>Per-prompt detail</h2>
<table><tr><th>#</th><th>Gateway model</th><th>Gateway ms</th><th>Direct ms</th><th>Overhead ms</th></tr>
"""
    for r in results:
        gw_model = (r["gateway"].get("model") or "?")
        gw_ms = f'{r["gateway"]["ms"]:.0f}' if r["gateway"].get("ok") else "ERR"
        dr_ms = (f'{r["direct"]["ms"]:.0f}' if r["direct"] and r["direct"].get("ok")
                 else "—")
        ov = (f'{r["overhead_ms"]:+.0f}' if r["overhead_ms"] is not None else "—")
        html += (f'<tr><td>{r["id"]}</td><td><code>{gw_model}</code></td>'
                 f'<td>{gw_ms}</td><td>{dr_ms}</td><td><b>{ov}</b></td></tr>')
    html += """</table>
<p style="margin-top:30px;color:#888;font-size:11px">
Apples-to-apples: each row pairs one gateway call with a direct call to the
SAME model. Skipped rows are non-Anthropic deployments we don't have a direct
client for in this script (gpt-4o-mini, deepseek/*). Total wall-clock comparisons
would bundle provider variance into our overhead and be misleading; the paired
delta is the honest number.
</p></body></html>"""
    Path(args.out_html).write_text(html, encoding="utf-8")
    print(f"\nWrote {args.out_html} and {args.out_jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
