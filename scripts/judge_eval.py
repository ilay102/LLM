#!/usr/bin/env python3
"""
Pairwise quality judge for VIREN gateway vs baseline.

Loads scripts/eval_results.jsonl (produced by eval_corpus.py), runs
the shadow-eval/judge_prompt.txt judge via gpt-4o on each row,
randomises A/B order to remove position bias, then writes
scripts/quality_report.html.
"""
from __future__ import annotations
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

try:
    from openai import AsyncOpenAI
except ImportError:
    print("pip install openai", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).parent
REPO = HERE.parent

RESULTS_PATH  = HERE / "eval_results.jsonl"
JUDGE_PROMPT  = REPO / "shadow-eval" / "judge_prompt.txt"
REPORT_PATH   = HERE / "quality_report.html"
LOG_PATH      = HERE / "judge_output.log"

JUDGE_MODEL   = "gpt-4o"
CONCURRENCY   = 4


def fill_judge_prompt(template: str, user_prompt: str, resp_a: str, resp_b: str) -> str:
    return (template
            .replace("<<<USER_PROMPT>>>", user_prompt)
            .replace("<<<RESPONSE_A>>>", resp_a)
            .replace("<<<RESPONSE_B>>>", resp_b))


async def judge_one(sem: asyncio.Semaphore, client: AsyncOpenAI,
                    template: str, row: dict) -> dict:
    prompt_text = row["prompt"]
    gw_answer   = (row.get("gateway") or {}).get("answer", "")
    bl_answer   = (row.get("baseline") or {}).get("answer", "")

    if not gw_answer or not bl_answer:
        return {**row, "judge": {"winner": "TIE", "axis": "n/a",
                                  "reason": "missing answer"}, "gw_side": "A",
                "gateway_result": "tie", "error": "missing answer"}

    # Randomise which side is A
    if random.random() < 0.5:
        side_a, side_b, gw_side = gw_answer, bl_answer, "A"
    else:
        side_a, side_b, gw_side = bl_answer, gw_answer, "B"

    filled = fill_judge_prompt(template, prompt_text, side_a, side_b)

    async with sem:
        t0 = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=JUDGE_MODEL,
                max_tokens=256,
                temperature=0.0,
                messages=[{"role": "user", "content": filled}],
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            raw = resp.choices[0].message.content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1].lstrip("json").strip()
            verdict = json.loads(raw)
        except Exception as e:
            return {**row, "judge": {"winner": "TIE", "axis": "error",
                                      "reason": str(e)},
                    "gw_side": gw_side, "gateway_result": "tie",
                    "latency_ms": 0, "error": str(e)}

    winner = verdict.get("winner", "TIE")
    if winner == "TIE":
        gw_result = "tie"
    elif winner == gw_side:
        gw_result = "win"
    else:
        gw_result = "loss"

    return {
        "id": row.get("id"),
        "prompt": prompt_text,
        "gw_side": gw_side,
        "judge": verdict,
        "gateway_result": gw_result,
        "latency_ms": latency_ms,
        "gw_model": (row.get("gateway") or {}).get("model", "?"),
        "gw_answer": gw_answer,
        "bl_answer": bl_answer,
    }


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def write_html(results: list[dict], path: Path) -> None:
    wins   = sum(1 for r in results if r["gateway_result"] == "win")
    ties   = sum(1 for r in results if r["gateway_result"] == "tie")
    losses = sum(1 for r in results if r["gateway_result"] == "loss")
    n      = len(results)
    win_tie_pct = (wins + ties) / n * 100 if n else 0

    def badge(result: str) -> str:
        colors = {"win": "#22c55e", "tie": "#64748b", "loss": "#ef4444"}
        labels = {"win": "WIN", "tie": "TIE", "loss": "REGRESSION"}
        return (f'<span style="background:{colors[result]};color:#fff;'
                f'padding:2px 8px;border-radius:4px;font-size:12px;'
                f'font-weight:700">{labels[result]}</span>')

    rows_html = ""
    for r in results:
        verdict = r.get("judge", {})
        rows_html += f"""
<tr>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;color:#555;font-size:13px">{_esc(str(r.get("id","?")))}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:13px">{_esc(r.get("prompt","")[:120])}{"…" if len(r.get("prompt",""))>120 else ""}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#555">{_esc(r.get("gw_model","?").split("/")[-1][:25])}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0">{badge(r["gateway_result"])}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#555">{_esc(verdict.get("axis","?"))}</td>
  <td style="padding:8px;border-bottom:1px solid #e2e8f0;font-size:13px">{_esc(verdict.get("reason",""))}</td>
</tr>"""

    regressions = [r for r in results if r["gateway_result"] == "loss"]
    reg_html = ""
    if regressions:
        for r in regressions:
            reg_html += f"""
<div style="border:1px solid #fecaca;border-radius:8px;padding:16px;margin-bottom:12px;background:#fff5f5">
  <div style="font-weight:600;margin-bottom:6px">Prompt #{r.get("id","?")}: {_esc(r.get("prompt","")[:150])}</div>
  <div style="font-size:13px;color:#555;margin-bottom:8px"><b>Judge reason:</b> {_esc(r.get("judge",{}).get("reason",""))}</div>
  <details><summary style="cursor:pointer;font-size:12px;color:#888">Show answers</summary>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px">
    <div><b>Gateway ({_esc(r.get("gw_model","?").split("/")[-1][:20])}):</b><pre style="font-size:11px;background:#f8f8f8;padding:8px;border-radius:4px;white-space:pre-wrap">{_esc(r.get("gw_answer","")[:800])}</pre></div>
    <div><b>Baseline (claude-sonnet-4-6):</b><pre style="font-size:11px;background:#f8f8f8;padding:8px;border-radius:4px;white-space:pre-wrap">{_esc(r.get("bl_answer","")[:800])}</pre></div>
  </div></details>
</div>"""
    else:
        reg_html = '<p style="color:#22c55e;font-weight:600">No regressions — gateway matched or beat baseline on every prompt.</p>'

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>VIREN Quality Report — Pairwise Judge</title>
<style>
body{{font-family:-apple-system,Inter,system-ui;max-width:1100px;margin:30px auto;color:#111;padding:0 20px}}
h1{{font-size:28px;margin:0 0 6px}}
.sub{{color:#666;margin-bottom:28px;font-size:15px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}}
.kpi{{background:#f6f7fb;border-radius:10px;padding:18px}}
.kpi .v{{font-size:36px;font-weight:700;line-height:1}}
.kpi .l{{font-size:13px;color:#666;margin-top:4px}}
table{{width:100%;border-collapse:collapse;margin:16px 0}}
th{{text-align:left;padding:10px 8px;background:#f1f5f9;font-size:13px;color:#555;border-bottom:2px solid #e2e8f0}}
</style>
</head><body>
<h1>VIREN — Quality Report</h1>
<div class="sub">Pairwise judge: {JUDGE_MODEL} · {n} prompts · A/B order randomised</div>

<div class="kpis">
  <div class="kpi"><div class="v" style="color:#16a34a">{win_tie_pct:.1f}%</div><div class="l">Win-or-Tie (headline)</div></div>
  <div class="kpi"><div class="v" style="color:#22c55e">{wins}</div><div class="l">Wins (gateway better)</div></div>
  <div class="kpi"><div class="v" style="color:#64748b">{ties}</div><div class="l">Ties (equivalent)</div></div>
  <div class="kpi"><div class="v" style="color:#ef4444">{losses}</div><div class="l">Regressions (baseline better)</div></div>
</div>

<h2>Per-Prompt Audit</h2>
<table>
<thead><tr>
  <th>#</th><th>Prompt</th><th>GW Model</th><th>Result</th><th>Axis</th><th>Reason</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>

<h2>Regressions ({len(regressions)})</h2>
{reg_html}
</body></html>"""

    path.write_text(html)


async def amain() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr)
        return 1

    template = JUDGE_PROMPT.read_text()
    rows = [json.loads(l) for l in RESULTS_PATH.read_text().splitlines() if l.strip()]

    print(f"Judging {len(rows)} prompt pairs with {JUDGE_MODEL}")
    print(f"  A/B order randomised per-row to eliminate position bias")
    print()

    client = AsyncOpenAI(api_key=api_key)
    sem    = asyncio.Semaphore(CONCURRENCY)
    tasks  = [judge_one(sem, client, template, row) for row in rows]

    results = []
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        icon = {"win": "✓", "tie": "~", "loss": "✗"}[r["gateway_result"]]
        print(f"  [{len(results):2d}/{len(rows)}] {icon} {r['gateway_result']:4s}  "
              f"{r.get('judge',{}).get('axis','?'):18s}  "
              f"{r.get('prompt','')[:60]}")

    # Sort back by original id for stable report order
    results.sort(key=lambda r: r.get("id") or 0)

    wins   = sum(1 for r in results if r["gateway_result"] == "win")
    ties   = sum(1 for r in results if r["gateway_result"] == "tie")
    losses = sum(1 for r in results if r["gateway_result"] == "loss")
    n      = len(results)
    win_tie_pct = (wins + ties) / n * 100 if n else 0

    summary = f"""
==========================================
VIREN — Quality Verdict on {n} prompts
==========================================
Win-or-Tie:   {wins + ties:3d} / {n}  ({win_tie_pct:.1f}%)
  Wins  (gw better):   {wins:3d}
  Ties  (equivalent):  {ties:3d}
  Loss  (regression):  {losses:3d}
==========================================
"""
    print(summary)

    write_html(results, REPORT_PATH)
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
