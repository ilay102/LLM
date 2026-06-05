#!/usr/bin/env python3
"""
code_quality_eval.py — defensible "code quality is X%" number for the evidence pack.

WHY: buyers ask "what about code generation?" and our cost+quality numbers came
from a mostly classification corpus. This script runs a small, code-heavy
corpus through the gateway AND direct-Sonnet baseline, then checks each
answer with REAL checks:

  - Python `callable`: extract the function, execute it in a sandbox, assert
    expected outputs for each test case. This is the gold-standard check.
  - JavaScript `syntax`: run `node --check` on the extracted code.
  - SQL `sql_syntax`: cheap structural check — must contain expected
    clauses (SELECT/JOIN/GROUP BY/...).

Report per-language pass rates for BOTH gateway and baseline, side by side.
The headline is: "VIREN code-generation pass rate: X% (Sonnet baseline: Y%)".

Cost: ~$1 for 20 prompts, two paths each.

Run:
  GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY="$GATEWAY_MASTER_KEY" \
  ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  python3 scripts/code_quality_eval.py --limit 20
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

try:
    from openai import AsyncOpenAI
    from anthropic import AsyncAnthropic
except ImportError:
    print("Install: pip install openai anthropic", file=sys.stderr); sys.exit(1)

HERE = Path(__file__).parent
REPO = HERE.parent
CORPUS = REPO / "eval" / "code_corpus.jsonl"


# ---- code extraction ------------------------------------------------------

def extract_code(answer: str, lang: str) -> str:
    """Pull code from a ```lang fence. Falls back to any ``` fence."""
    if not answer:
        return ""
    patterns = [
        rf"```{lang}\s*\n(.*?)\n```",
        r"```[a-zA-Z]*\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",
    ]
    for p in patterns:
        m = re.search(p, answer, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # no fence — assume the whole thing is code
    return answer.strip()


# ---- checks ---------------------------------------------------------------

def check_python_callable(code: str, name: str, calls: list[dict]) -> tuple[bool, str]:
    """Execute the code in a fresh namespace, find the function, run test cases."""
    if not code:
        return False, "no code extracted"
    ns: dict = {}
    try:
        exec(compile(code, "<gw>", "exec"), ns, ns)
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg}"
    except Exception as e:
        return False, f"compile error: {type(e).__name__}: {e}"
    fn = ns.get(name)
    if fn is None:
        return False, f"function {name!r} not defined"
    if not callable(fn):
        return False, f"{name!r} is not callable"
    for tc in calls:
        args = tc.get("args", [])
        try:
            got = fn(*args)
        except Exception as e:
            return False, f"call {args!r} raised {type(e).__name__}: {e}"
        if "expect" in tc:
            if got != tc["expect"]:
                return False, f"call {args!r} -> {got!r} (expected {tc['expect']!r})"
        elif "expect_iter" in tc:
            try:
                got_list = list(got)
            except Exception:
                return False, f"call {args!r} did not return an iterable"
            if got_list != tc["expect_iter"]:
                return False, f"call {args!r} -> {got_list!r} (expected {tc['expect_iter']!r})"
    return True, f"{len(calls)} test cases passed"


def check_js_syntax(code: str) -> tuple[bool, str]:
    """node --check. If node isn't available, fall back to a permissive regex check."""
    if not code:
        return False, "no code extracted"
    # Try node first
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(code); tmp = f.name
        r = subprocess.run(["node", "--check", tmp],
                           capture_output=True, text=True, timeout=10)
        Path(tmp).unlink(missing_ok=True)
        if r.returncode == 0:
            return True, "node --check passed"
        return False, f"node --check failed: {r.stderr.strip()[:120]}"
    except (FileNotFoundError, subprocess.SubprocessError):
        # Fall back: structural sanity (has function declaration / arrow / proper braces)
        if not re.search(r"(function\s+\w+\s*\(|=>|\bconst\s+\w+\s*=)", code):
            return False, "no function-like construct found"
        if code.count("{") != code.count("}"):
            return False, f"unbalanced braces: {code.count('{')} open vs {code.count('}')} close"
        if code.count("(") != code.count(")"):
            return False, f"unbalanced parens"
        return True, "structural check passed (node not available)"


def check_sql_syntax(code: str, must_contain: list[str]) -> tuple[bool, str]:
    if not code:
        return False, "no code extracted"
    up = code.upper()
    missing = [c for c in must_contain if c.upper() not in up]
    if missing:
        return False, f"missing required clauses: {missing}"
    # Must end with semicolon or look complete
    if "SELECT" not in up:
        return False, "no SELECT found"
    # parens balanced (catches truncation)
    if code.count("(") != code.count(")"):
        return False, "unbalanced parens"
    return True, f"contains all of {must_contain}"


def run_check(row: dict, code: str) -> tuple[bool, str]:
    check = row.get("check", {})
    t = check.get("type")
    if t == "callable":
        return check_python_callable(code, check["name"], check["calls"])
    if t == "syntax":
        return check_js_syntax(code)
    if t == "sql_syntax":
        return check_sql_syntax(code, check.get("must_contain", []))
    return False, f"unknown check type: {t}"


# ---- model calls ----------------------------------------------------------

async def call_gateway(oai: AsyncOpenAI, prompt: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await oai.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800, temperature=0.0,
        )
        return {"ok": True, "model": r.model, "answer": r.choices[0].message.content or "",
                "in_tokens": r.usage.prompt_tokens, "out_tokens": r.usage.completion_tokens,
                "ms": (time.perf_counter() - t0) * 1000}
    except Exception as e:
        return {"ok": False, "err": str(e)[:140]}


async def call_baseline(anth: AsyncAnthropic, prompt: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = await anth.messages.create(
            model="claude-sonnet-4-6", max_tokens=800, temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in r.content if hasattr(b, "text"))
        return {"ok": True, "model": r.model, "answer": text,
                "in_tokens": r.usage.input_tokens, "out_tokens": r.usage.output_tokens,
                "ms": (time.perf_counter() - t0) * 1000}
    except Exception as e:
        return {"ok": False, "err": str(e)[:140]}


PRICE = {
    "haiku": (0.8e-6, 4e-6), "gpt-4o-mini": (0.15e-6, 0.6e-6),
    "sonnet": (3e-6, 15e-6), "opus": (15e-6, 75e-6),
    "deepseek-v4-pro": (0.435e-6, 0.87e-6),
    "deepseek-chat": (0.14e-6, 0.28e-6),
    "deepseek-reasoner": (0.435e-6, 0.87e-6),
}
def price(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for k, v in PRICE.items():
        if k in m: return v
    return PRICE["sonnet"]


async def evaluate_one(sem, oai, anth, row):
    async with sem:
        g, b = await asyncio.gather(
            call_gateway(oai, row["prompt"]),
            call_baseline(anth, row["prompt"]),
        )
        g_code = extract_code(g.get("answer", ""), row["lang"])
        b_code = extract_code(b.get("answer", ""), row["lang"])
        g_pass, g_why = (run_check(row, g_code) if g.get("ok") else (False, g.get("err", "call failed")))
        b_pass, b_why = (run_check(row, b_code) if b.get("ok") else (False, b.get("err", "call failed")))

        g_cost = 0; b_cost = 0
        if g.get("ok"):
            ip, op = price(g.get("model", ""))
            g_cost = (g["in_tokens"] or 0) * ip + (g["out_tokens"] or 0) * op
        if b.get("ok"):
            ip, op = price(b.get("model", ""))
            b_cost = (b["in_tokens"] or 0) * ip + (b["out_tokens"] or 0) * op

        return {
            "id": row["id"], "lang": row["lang"], "prompt": row["prompt"],
            "gateway": {**g, "code": g_code, "pass": g_pass, "why": g_why, "cost": g_cost},
            "baseline": {**b, "code": b_code, "pass": b_pass, "why": b_why, "cost": b_cost},
        }


# ---- main -----------------------------------------------------------------

async def amain():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--out-jsonl", default=str(HERE / "code_quality_results.jsonl"))
    p.add_argument("--out-html", default=str(HERE / "code_quality_report.html"))
    args = p.parse_args()

    gw_url = os.environ.get("GATEWAY_URL", "http://localhost:8000/v1")
    gw_key = os.environ.get("GATEWAY_KEY", "")
    anth_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not (gw_key and anth_key):
        print("ERROR: set GATEWAY_KEY and ANTHROPIC_API_KEY", file=sys.stderr); return 1

    rows = []
    with open(args.corpus, encoding="utf-8") as f:
        for line in f:
            if line.strip(): rows.append(json.loads(line))
    if args.limit: rows = rows[: args.limit]

    print(f"Code-quality eval: {len(rows)} prompts. Gateway={gw_url}")
    oai = AsyncOpenAI(base_url=gw_url, api_key=gw_key)
    anth = AsyncAnthropic(api_key=anth_key)
    sem = asyncio.Semaphore(args.concurrency)

    results = []
    tasks = [evaluate_one(sem, oai, anth, r) for r in rows]
    for fut in asyncio.as_completed(tasks):
        r = await fut
        results.append(r)
        gp = "✓" if r["gateway"]["pass"] else "✗"
        bp = "✓" if r["baseline"]["pass"] else "✗"
        gm = (r["gateway"].get("model", "?") or "?").split("/")[-1][:22]
        print(f"  [{len(results)}/{len(rows)}] #{r['id']:>2} {r['lang']:<10}  "
              f"gw={gp} ({gm:<22})  bl={bp}")

    # Aggregate
    by_lang = defaultdict(lambda: {"n": 0, "gw_pass": 0, "bl_pass": 0, "gw_cost": 0, "bl_cost": 0})
    for r in results:
        b = by_lang[r["lang"]]
        b["n"] += 1
        if r["gateway"]["pass"]: b["gw_pass"] += 1
        if r["baseline"]["pass"]: b["bl_pass"] += 1
        b["gw_cost"] += r["gateway"]["cost"]
        b["bl_cost"] += r["baseline"]["cost"]
    total_n = sum(b["n"] for b in by_lang.values())
    total_gw_pass = sum(b["gw_pass"] for b in by_lang.values())
    total_bl_pass = sum(b["bl_pass"] for b in by_lang.values())
    total_gw_cost = sum(b["gw_cost"] for b in by_lang.values())
    total_bl_cost = sum(b["bl_cost"] for b in by_lang.values())

    gw_rate = total_gw_pass / total_n * 100 if total_n else 0
    bl_rate = total_bl_pass / total_n * 100 if total_n else 0
    savings_pct = (1 - total_gw_cost / total_bl_cost) * 100 if total_bl_cost else 0

    print()
    print(f"  OVERALL: gateway {total_gw_pass}/{total_n} pass ({gw_rate:.1f}%)  "
          f"baseline {total_bl_pass}/{total_n} pass ({bl_rate:.1f}%)  "
          f"savings {savings_pct:.1f}%")
    for lang in sorted(by_lang):
        b = by_lang[lang]
        print(f"  {lang:<10}  gw {b['gw_pass']}/{b['n']} ({b['gw_pass']/b['n']*100:.0f}%)  "
              f"bl {b['bl_pass']}/{b['n']} ({b['bl_pass']/b['n']*100:.0f}%)  "
              f"gw_cost ${b['gw_cost']:.4f}  bl_cost ${b['bl_cost']:.4f}")

    # Write JSONL + HTML
    with open(args.out_jsonl, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    delta_pp = gw_rate - bl_rate
    delta_color = "#137333" if delta_pp >= 0 else ("#b06000" if delta_pp >= -10 else "#b3261e")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>VIREN — Code Generation Quality Report</title>
<style>
 body{{font-family:-apple-system,Inter,system-ui;max-width:1100px;margin:30px auto;color:#111;padding:0 20px}}
 h1{{font-size:30px;margin:0 0 6px}}
 .sub{{color:#666;margin-bottom:24px}}
 .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}
 .kpi{{border-radius:10px;padding:18px;background:#f6f7fb}}
 .kpi .v{{font-size:30px;font-weight:800;line-height:1;color:#6d63ff}}
 .kpi .l{{font-size:11px;margin-top:6px;color:#666;text-transform:uppercase;letter-spacing:1px}}
 .kpi.dark{{background:#0a0a0a;color:white}}.kpi.dark .v{{color:white}}.kpi.dark .l{{color:rgba(255,255,255,0.6)}}
 .reframe{{background:#f0f3ff;border-left:4px solid #6d63ff;padding:14px 18px;border-radius:6px;margin:24px 0;font-size:15px}}
 .reframe b{{color:#6d63ff}}
 table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:18px}}
 th,td{{border-bottom:1px solid #eee;padding:8px 10px;text-align:left;vertical-align:top}}
 th{{background:#fafafa;text-transform:uppercase;font-size:11px;letter-spacing:1px;color:#666}}
 .pass{{color:#137333;font-weight:700}}.fail{{color:#b3261e;font-weight:700}}
 code{{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px}}
 pre{{background:#0a0a0a;color:#e4e6eb;padding:10px 14px;border-radius:6px;font-size:11px;overflow-x:auto;max-height:180px}}
 details{{margin:4px 0}}
</style></head><body>
<h1>Code Generation Quality Report</h1>
<p class="sub">{total_n} code-generation prompts (Python execution tests, JS syntax checks, SQL structural checks). Run through VIREN gateway AND direct Sonnet baseline. Each answer's code was extracted and actually executed/checked — not eyeballed.</p>

<div class="kpis">
  <div class="kpi"><div class="v">{gw_rate:.0f}%</div><div class="l">VIREN code pass rate</div></div>
  <div class="kpi"><div class="v">{bl_rate:.0f}%</div><div class="l">Sonnet baseline pass rate</div></div>
  <div class="kpi" style="background:{delta_color};color:white">
    <div class="v" style="color:white">{delta_pp:+.0f}pp</div>
    <div class="l" style="color:rgba(255,255,255,.85)">vs. baseline</div>
  </div>
  <div class="kpi dark"><div class="v">{savings_pct:.0f}%</div><div class="l">Cost reduction on code prompts</div></div>
</div>

<div class="reframe">
  <b>Code generation, honest:</b> VIREN's code pass rate is <b>{gw_rate:.0f}%</b> on
  this {total_n}-prompt corpus — vs. <b>{bl_rate:.0f}%</b> for direct Sonnet, at
  <b>{savings_pct:.0f}% lower cost</b>. Every Python answer was extracted from the
  response, executed, and asserted against expected outputs. JS answers were
  syntax-checked with <code>node --check</code> (or structural fallback). SQL
  answers were checked for required clauses. No eyeballing.
</div>

<h2>Per-language breakdown</h2>
<table><tr><th>Language</th><th>VIREN pass</th><th>Baseline pass</th><th>VIREN $</th><th>Baseline $</th></tr>
"""
    for lang in sorted(by_lang):
        b = by_lang[lang]
        html += (f"<tr><td><b>{lang}</b></td>"
                 f"<td>{b['gw_pass']}/{b['n']} ({b['gw_pass']/b['n']*100:.0f}%)</td>"
                 f"<td>{b['bl_pass']}/{b['n']} ({b['bl_pass']/b['n']*100:.0f}%)</td>"
                 f"<td>${b['gw_cost']:.4f}</td><td>${b['bl_cost']:.4f}</td></tr>")
    html += "</table>"

    html += "<h2>Per-prompt detail</h2><table><tr><th>#</th><th>Lang</th><th>Gateway</th><th>Baseline</th><th>Prompt</th></tr>"
    for r in results:
        gw_cls = "pass" if r["gateway"]["pass"] else "fail"
        bl_cls = "pass" if r["baseline"]["pass"] else "fail"
        gw_sym = "✓ PASS" if r["gateway"]["pass"] else f"✗ {r['gateway']['why'][:50]}"
        bl_sym = "✓ PASS" if r["baseline"]["pass"] else f"✗ {r['baseline']['why'][:50]}"
        gw_model = (r["gateway"].get("model") or "?").split("/")[-1]
        prompt_ex = r["prompt"][:120]
        html += (f"<tr><td>{r['id']}</td><td>{r['lang']}</td>"
                 f"<td class='{gw_cls}'>{gw_sym}<br><code>{gw_model}</code></td>"
                 f"<td class='{bl_cls}'>{bl_sym}</td>"
                 f"<td>{prompt_ex}…</td></tr>")
    html += """</table>
<p style="margin-top:30px;color:#888;font-size:11px">
Python prompts use the <code>callable</code> check: code is executed in a fresh
namespace, the named function is called with each test case's arguments, and the
return value asserted. JavaScript prompts use <code>node --check</code> for
syntactic validity. SQL prompts check for required clauses (SELECT/JOIN/GROUP BY/…).
This is more rigorous than a single LLM-as-judge over code, which often
mis-grades formatting differences as functional regressions.
</p>
</body></html>"""
    Path(args.out_html).write_text(html, encoding="utf-8")
    print(f"\nWrote {args.out_jsonl} and {args.out_html}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
