#!/usr/bin/env python3
"""
3-judge ensemble quality eval for VIREN gateway vs baseline.

Judges: claude-sonnet-4-6 (Anthropic), gpt-4o (OpenAI), claude-opus-4-7 (Anthropic)
Each judge sees independently randomised A/B order.
Majority verdict (2-of-3) is the headline metric.

Usage:
  ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python3 scripts/judge_ensemble.py \
      [--results path/to/eval_results.jsonl] [--label v0.2]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
except ImportError:
    print("pip install anthropic openai", file=sys.stderr)
    sys.exit(1)

HERE   = Path(__file__).parent
REPO   = HERE.parent
JUDGE_PROMPT_PATH = REPO / "shadow-eval" / "judge_prompt.txt"
VERDICTS_PATH     = HERE / "ensemble_verdicts.jsonl"
REPORT_PATH       = HERE / "quality_ensemble_report.html"

JUDGES = [
    ("sonnet", "claude-sonnet-4-6",  "anthropic"),
    ("gpt4o",  "gpt-4o",             "openai"),
    ("opus",   "claude-opus-4-7",    "anthropic"),
]
CONCURRENCY = 3   # per-judge semaphore


def fill_prompt(template: str, user_prompt: str, a: str, b: str) -> str:
    return (template
            .replace("<<<USER_PROMPT>>>", user_prompt)
            .replace("<<<RESPONSE_A>>>", a)
            .replace("<<<RESPONSE_B>>>", b))


async def call_judge(sem: asyncio.Semaphore, provider: str, model: str,
                     anth: AsyncAnthropic, oai: AsyncOpenAI,
                     filled: str) -> tuple[dict, float]:
    async with sem:
        t0 = time.perf_counter()
        try:
            if provider == "anthropic":
                resp = await anth.messages.create(
                    model=model, max_tokens=256, temperature=0.0,
                    messages=[{"role": "user", "content": filled}],
                )
                raw = resp.content[0].text.strip()
            else:
                resp = await oai.chat.completions.create(
                    model=model, max_tokens=256, temperature=0.0,
                    messages=[{"role": "user", "content": filled}],
                )
                raw = resp.choices[0].message.content.strip()
            latency = (time.perf_counter() - t0) * 1000
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            verdict = json.loads(raw)
            return verdict, latency
        except Exception as e:
            return {"winner": "TIE", "axis": "error", "reason": str(e)}, 0.0


async def judge_row(sem: asyncio.Semaphore, anth: AsyncAnthropic, oai: AsyncOpenAI,
                    template: str, row: dict, seed_base: int) -> dict:
    gw_ans = (row.get("gateway") or {}).get("answer", "")
    bl_ans = (row.get("baseline") or {}).get("answer", "")
    prompt_text = row.get("prompt", "")

    if not gw_ans or not bl_ans:
        per_judge = {name: {"winner": "TIE", "axis": "n/a",
                             "reason": "missing answer", "gw_side": "A",
                             "gw_result": "tie"} for name, _, _ in JUDGES}
        return {"id": row.get("id"), "prompt": prompt_text,
                "gw_model": (row.get("gateway") or {}).get("model", "?"),
                "gw_answer": gw_ans, "bl_answer": bl_ans,
                "per_judge": per_judge, "majority": "tie",
                "strict_agreement": True, "error": "missing answer"}

    # Fire all 3 judges concurrently; each gets its own A/B flip
    async def run_one(idx: int, name: str, model: str, provider: str):
        rng = random.Random(seed_base + idx)
        if rng.random() < 0.5:
            side_a, side_b, gw_side = gw_ans, bl_ans, "A"
        else:
            side_a, side_b, gw_side = bl_ans, gw_ans, "B"
        filled = fill_prompt(template, prompt_text, side_a, side_b)
        verdict, latency = await call_judge(sem, provider, model, anth, oai, filled)
        winner = verdict.get("winner", "TIE")
        if winner == "TIE":
            gw_result = "tie"
        elif winner == gw_side:
            gw_result = "win"
        else:
            gw_result = "loss"
        return name, {**verdict, "gw_side": gw_side, "gw_result": gw_result,
                       "latency_ms": latency}

    tasks = [run_one(idx, name, model, provider)
             for idx, (name, model, provider) in enumerate(JUDGES)]
    judge_results = dict(await asyncio.gather(*tasks))

    # Majority vote
    counts = Counter(j["gw_result"] for j in judge_results.values())
    majority = counts.most_common(1)[0][0]
    # If all three differ (WIN+TIE+LOSS each once) → conservative TIE
    if len(counts) == 3:
        majority = "tie"
    strict_agreement = (len(counts) == 1)

    return {
        "id": row.get("id"),
        "prompt": prompt_text,
        "gw_model": (row.get("gateway") or {}).get("model", "?"),
        "gw_answer": gw_ans,
        "bl_answer": bl_ans,
        "per_judge": judge_results,
        "majority": majority,
        "strict_agreement": strict_agreement,
    }


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _badge(result: str) -> str:
    colors = {"win": "#22c55e", "tie": "#64748b", "loss": "#ef4444"}
    labels = {"win": "WIN", "tie": "TIE", "loss": "REGRESSION"}
    c = colors.get(result, "#999")
    l = labels.get(result, result.upper())
    return (f'<span style="background:{c};color:#fff;padding:2px 7px;'
            f'border-radius:4px;font-size:11px;font-weight:700">{l}</span>')


def write_html(results: list[dict], report_path: Path, label: str) -> None:
    n = len(results)
    judge_names = [name for name, _, _ in JUDGES]

    def wt(name):
        vals = [r["per_judge"][name]["gw_result"] for r in results
                if name in r.get("per_judge", {})]
        return sum(1 for v in vals if v in ("win", "tie")) / len(vals) * 100 if vals else 0

    maj_wt = sum(1 for r in results if r["majority"] in ("win", "tie")) / n * 100
    strict_pct = sum(1 for r in results if r["strict_agreement"]) / n * 100
    disagree_count = sum(1 for r in results
                         if len(set(r["per_judge"][j]["gw_result"]
                                    for j in judge_names)) > 1)

    kpi_html = ""
    for name in judge_names:
        kpi_html += (f'<div class="kpi"><div class="v">{wt(name):.1f}%</div>'
                     f'<div class="l">{name} W-T</div></div>')
    kpi_html += (f'<div class="kpi" style="border:2px solid #2563eb">'
                 f'<div class="v" style="color:#2563eb">{maj_wt:.1f}%</div>'
                 f'<div class="l">MAJORITY W-T</div></div>')

    rows_html = ""
    for r in results:
        pj = r.get("per_judge", {})
        judge_cells = "".join(
            f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center">'
            f'{_badge(pj.get(name, {}).get("gw_result", "tie"))}</td>'
            for name in judge_names
        )
        rows_html += (
            f'<tr>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;color:#555;font-size:12px">'
            f'{_esc(r.get("id","?"))}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:12px">'
            f'{_esc(r.get("prompt","")[:100])}{"…" if len(r.get("prompt",""))>100 else ""}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:11px;color:#555">'
            f'{_esc(r.get("gw_model","?").split("/")[-1][:22])}</td>'
            f'{judge_cells}'
            f'<td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center">'
            f'{_badge(r["majority"])}'
            f'{"🔒" if r["strict_agreement"] else ""}</td>'
            f'</tr>'
        )

    regressions = [r for r in results if r["majority"] == "loss"]
    reg_html = ""
    if regressions:
        for r in regressions:
            pj = r.get("per_judge", {})
            reasons = " | ".join(
                f'{name}: {_esc(pj.get(name,{}).get("reason","?")[:80])}'
                for name in judge_names
            )
            reg_html += (
                f'<div style="border:1px solid #fecaca;border-radius:8px;'
                f'padding:14px;margin-bottom:10px;background:#fff5f5">'
                f'<div style="font-weight:600;margin-bottom:4px">'
                f'#{_esc(r.get("id","?"))}: {_esc(r.get("prompt","")[:120])}</div>'
                f'<div style="font-size:12px;color:#666">{reasons}</div>'
                f'</div>'
            )
    else:
        reg_html = '<p style="color:#22c55e;font-weight:600">No majority regressions.</p>'

    th = "".join(f'<th>{n}</th>' for n in judge_names)
    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>VIREN Ensemble Quality — {label}</title>
<style>
body{{font-family:-apple-system,Inter,system-ui;max-width:1200px;margin:30px auto;
     color:#111;padding:0 20px}}
h1{{font-size:26px;margin:0 0 6px}}
.sub{{color:#666;margin-bottom:24px;font-size:14px}}
.kpis{{display:grid;grid-template-columns:repeat({len(judge_names)+1},1fr);
       gap:12px;margin:20px 0}}
.kpi{{background:#f6f7fb;border-radius:8px;padding:14px}}
.kpi .v{{font-size:28px;font-weight:700;line-height:1}}
.kpi .l{{font-size:12px;color:#666;margin-top:3px}}
.stats{{display:flex;gap:24px;margin:16px 0;font-size:13px;color:#555}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
th{{text-align:left;padding:8px;background:#f1f5f9;font-size:12px;
    color:#555;border-bottom:2px solid #e2e8f0}}
</style></head><body>
<h1>VIREN — Ensemble Quality Report ({label})</h1>
<div class="sub">3-judge pairwise · {n} prompts · independent A/B randomisation per judge</div>
<div class="kpis">{kpi_html}</div>
<div class="stats">
  <span>🔒 All-3-agree: <b>{strict_pct:.1f}%</b> ({sum(1 for r in results if r["strict_agreement"])}/{n})</span>
  <span>⚡ Any-judge-disagrees: <b>{disagree_count}</b> prompts</span>
  <span>3-way split: <b>{sum(1 for r in results if len(set(r["per_judge"][j]["gw_result"] for j in judge_names))==3)}</b> prompts</span>
</div>
<h2>Per-Prompt Verdicts</h2>
<table><thead><tr>
  <th>#</th><th>Prompt</th><th>GW model</th>{th}<th>MAJORITY 🗳</th>
</tr></thead><tbody>{rows_html}</tbody></table>
<h2>Majority Regressions ({len(regressions)})</h2>
{reg_html}
</body></html>"""
    report_path.write_text(html)


async def amain() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", default=str(HERE / "eval_results.jsonl"))
    p.add_argument("--label",   default="v0.2.2")
    p.add_argument("--out-report", default=str(REPORT_PATH))
    p.add_argument("--out-verdicts", default=str(VERDICTS_PATH))
    args = p.parse_args()

    anth_key = os.environ.get("ANTHROPIC_API_KEY", "")
    oai_key  = os.environ.get("OPENAI_API_KEY", "")
    if not anth_key:
        print("ERROR: set ANTHROPIC_API_KEY", file=sys.stderr); return 1
    if not oai_key:
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr); return 1

    template = JUDGE_PROMPT_PATH.read_text()
    rows = [json.loads(l) for l in Path(args.results).read_text().splitlines() if l.strip()]
    print(f"Ensemble judging {len(rows)} rows [{args.label}]")
    print(f"  Judges: {', '.join(m for _, m, _ in JUDGES)}")
    print()

    anth = AsyncAnthropic(api_key=anth_key)
    oai  = AsyncOpenAI(api_key=oai_key)
    sem  = asyncio.Semaphore(CONCURRENCY)

    results = []
    tasks = [judge_row(sem, anth, oai, template, row, seed_base=i*100)
             for i, row in enumerate(rows)]
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        pj = r.get("per_judge", {})
        icons = {"win": "✓", "tie": "~", "loss": "✗"}
        per = " ".join(f'{name}:{icons[pj.get(name,{}).get("gw_result","tie")]}'
                       for name, _, _ in JUDGES)
        maj_icon = icons[r["majority"]]
        print(f"  [{len(results):2d}/{len(rows)}] {per}  majority:{maj_icon}  "
              f"{r.get('prompt','')[:55]}")

    results.sort(key=lambda r: r.get("id") or 0)

    # Summary
    n = len(results)
    judge_names = [name for name, _, _ in JUDGES]
    for name in judge_names:
        wt = sum(1 for r in results
                 if r["per_judge"].get(name, {}).get("gw_result") in ("win", "tie"))
        print(f"  {name:10s}  W-T: {wt}/{n}  ({wt/n*100:.1f}%)")
    maj_wt = sum(1 for r in results if r["majority"] in ("win", "tie"))
    strict  = sum(1 for r in results if r["strict_agreement"])
    print(f"\n  MAJORITY   W-T: {maj_wt}/{n}  ({maj_wt/n*100:.1f}%)")
    print(f"  All-3-agree:    {strict}/{n}  ({strict/n*100:.1f}%)")

    # Write outputs
    Path(args.out_verdicts).write_text(
        "\n".join(json.dumps(r, default=str) for r in results) + "\n"
    )
    write_html(results, Path(args.out_report), args.label)
    print(f"\nReport:   {args.out_report}")
    print(f"Verdicts: {args.out_verdicts}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
