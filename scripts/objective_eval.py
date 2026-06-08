#!/usr/bin/env python3
"""
Judge-free objective evaluator.

Reads a results file (default: scripts/eval_results.jsonl) and scores each
prompt against the deterministic ground-truth in eval/expected_answers.jsonl.

Why this exists:
  - The 3-judge LLM ensemble costs ~$2 per 30-prompt cycle, dominated by
    the Opus judge ($0.05/judgment). For the extraction/translation/
    classification subset of our corpus there's an OBJECTIVE answer —
    no judgment call needed. Scoring those deterministically is free,
    measurement-precise, and bypasses LLM-judge bias toward verbosity.

  - It also runs on the data you ALREADY have. No API calls. You can
    re-score a months-old eval_results.jsonl and see how the new gateway
    code would have changed the outcomes.

Scoring types:
  sentiment      response contains one of `accept` labels (case-insensitive),
                 doesn't contain any `forbid` label
  contains_all   response contains every literal in `accept`
  contains_any   response contains at least one literal in `accept`
  regex          response matches at least one regex in `patterns`
  yes_no         response starts with the expected yes/no word
  translation    response contains at least one expected target-language token
                 AND doesn't contain a `forbid` source-language phrase
  forbid_placeholders (any type): if true, the response containing a
                 PII-placeholder pattern (e.g. `<EMAIL_ADDRESS>`) auto-fails.
                 This is THE check that would have caught all 7 PII-bug
                 losses in the v0.2.2 ensemble.

Usage:
  python scripts/objective_eval.py \
      [--results scripts/eval_results.jsonl] \
      [--expected eval/expected_answers.jsonl] \
      [--side gateway|baseline|both]   # default: both

Output:
  - per-prompt verdict to stdout
  - summary: pass-rate per side, and the W/T/L breakdown vs baseline
  - scripts/objective_report.html with a per-prompt table
"""
from __future__ import annotations
import argparse
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent

PLACEHOLDER_RE = re.compile(
    r"<(EMAIL_ADDRESS|PHONE_NUMBER|PERSON|IP_ADDRESS|US_SSN|US_DRIVER_LICENSE|"
    r"US_PASSPORT|CREDIT_CARD|API_KEY|URL|LOCATION|ORGANIZATION|DATE_TIME)>"
)


def _ci_contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def score_one(answer: str, spec: dict) -> tuple[bool, str]:
    """Returns (pass, reason)."""
    if not answer or not isinstance(answer, str):
        return False, "empty answer"

    if spec.get("forbid_placeholders", False):
        m = PLACEHOLDER_RE.search(answer)
        if m:
            return False, f"placeholder leaked: {m.group(0)}"

    forbid = spec.get("forbid", []) or []
    for f in forbid:
        if _ci_contains(answer, f):
            return False, f"contains forbidden phrase: {f!r}"

    t = spec["type"]

    if t == "sentiment" or t == "contains_any":
        accept = spec.get("accept", [])
        if not accept:
            return True, "no acceptance criteria"
        for a in accept:
            if _ci_contains(answer, a):
                return True, f"matched {a!r}"
        return False, f"none of {accept} present"

    if t == "contains_all":
        accept = spec.get("accept", [])
        missing = [a for a in accept if not _ci_contains(answer, a)]
        if missing:
            return False, f"missing literal(s): {missing}"
        return True, "all literals present"

    if t == "regex":
        patterns = spec.get("patterns", [])
        for p in patterns:
            if re.search(p, answer):
                return True, f"matched regex {p!r}"
        return False, f"none of {patterns} matched"

    if t == "yes_no":
        want = (spec.get("accept") or "").lower()
        head = answer.strip().lower()
        # accept "yes", "yes,", "yes.", "yes — ...", "**yes**", etc.
        head = re.sub(r"^[*_`#\s]+", "", head)[:6]
        if head.startswith(want):
            return True, f"starts with {want!r}"
        return False, f"answer didn't start with {want!r} (got {answer[:40]!r})"

    if t == "translation":
        must = spec.get("must_contain_any", []) or []
        for a in must:
            if a in answer:  # CASE-SENSITIVE — accented / script characters matter
                return True, f"contains target-language token {a!r}"
        return False, f"no expected target-language tokens; tried {must}"

    return False, f"unknown spec type: {t}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", default=str(HERE / "eval_results.jsonl"))
    p.add_argument("--expected", default=str(REPO / "eval" / "expected_answers.jsonl"))
    p.add_argument("--side", choices=("gateway", "baseline", "both"), default="both")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    results = [json.loads(l) for l in open(args.results, encoding="utf-8")]
    expected = {row["id"]: row for row in (json.loads(l) for l in open(args.expected, encoding="utf-8"))}

    sides = ["gateway", "baseline"] if args.side == "both" else [args.side]

    rows = []
    counts = {s: Counter() for s in sides}
    head_to_head = Counter()  # W/T/L for gateway vs baseline (objective-defined)

    for r in results:
        pid = r["id"]
        spec = expected.get(pid)
        prompt = r.get("prompt", "")
        row = {"id": pid, "prompt": prompt[:120]}
        outcomes = {}
        if spec is None:
            outcomes = {s: ("skip", "no ground truth") for s in sides}
        else:
            for s in sides:
                ans = (r.get(s) or {}).get("answer", "")
                ok, reason = score_one(ans, spec)
                outcomes[s] = ("pass" if ok else "fail", reason)
                counts[s][outcomes[s][0]] += 1
        row["outcomes"] = outcomes

        # Head-to-head only when both sides scored
        if args.side == "both" and spec is not None:
            g_ok = outcomes["gateway"][0] == "pass"
            b_ok = outcomes["baseline"][0] == "pass"
            if g_ok and b_ok:
                verdict = "tie"
            elif g_ok and not b_ok:
                verdict = "win"
            elif not g_ok and b_ok:
                verdict = "loss"
            else:
                verdict = "both_fail"
            row["h2h"] = verdict
            head_to_head[verdict] += 1
        rows.append(row)

    # --- print
    if not args.quiet:
        print(f"Scored {len(rows)} prompts from {args.results}")
        for s in sides:
            c = counts[s]
            tot = c["pass"] + c["fail"]
            pr = c["pass"] / tot * 100 if tot else 0
            print(f"  {s:10s}  pass={c['pass']:>3}  fail={c['fail']:>3}  skip={c['skip']:>2}   pass-rate={pr:.1f}%")

        if args.side == "both":
            tot = sum(head_to_head.values())
            if tot:
                W, T, L, BF = head_to_head["win"], head_to_head["tie"], head_to_head["loss"], head_to_head["both_fail"]
                wt = (W + T) / tot * 100
                print(f"\n  H2H (objective): W={W} T={T} L={L} both_fail={BF}    W-T%={wt:.1f}")

        print("\n=== Per-prompt failures (gateway) ===")
        for row in rows:
            g = row["outcomes"].get("gateway")
            if g and g[0] == "fail":
                h = row.get("h2h", "?")
                print(f"  id={row['id']:>3} [{h:>4}]  {g[1]}")
                print(f"          prompt: {row['prompt']}")

    # --- HTML report
    html = ["<!doctype html><meta charset='utf-8'><title>VIREN — Objective Eval</title>",
            "<style>body{font-family:-apple-system,Inter,system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#111}"
            "table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #eee;padding:6px 8px;text-align:left;vertical-align:top}"
            ".pass{background:#e6f4ea;color:#137333}.fail{background:#fce8e6;color:#b3261e}.tie{background:#fff4d6;color:#7a5300}"
            ".pill{padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600}</style>",
            f"<h1>Objective eval — {len(rows)} prompts</h1>",
            "<p>Deterministic scoring against <code>eval/expected_answers.jsonl</code>. No LLM judges.</p>"]
    for s in sides:
        c = counts[s]
        tot = c["pass"] + c["fail"]
        pr = c["pass"] / tot * 100 if tot else 0
        html.append(f"<p><b>{s}</b> pass-rate: {pr:.1f}% ({c['pass']}/{tot}, {c['skip']} skipped)</p>")
    if args.side == "both" and head_to_head:
        tot = sum(head_to_head.values())
        W, T, L, BF = head_to_head["win"], head_to_head["tie"], head_to_head["loss"], head_to_head["both_fail"]
        html.append(f"<p><b>H2H</b>: W={W} T={T} L={L} both_fail={BF} — <b>W-T% = {(W+T)/tot*100:.1f}</b></p>")
    html.append("<table><tr><th>#</th><th>prompt</th>")
    for s in sides:
        html.append(f"<th>{s}</th>")
    if args.side == "both":
        html.append("<th>H2H</th>")
    html.append("</tr>")
    for row in rows:
        html.append(f"<tr><td>{row['id']}</td><td>{row['prompt']}</td>")
        for s in sides:
            o = row["outcomes"].get(s, ("?", ""))
            html.append(f"<td class='{o[0]}'>{o[0]} — {o[1]}</td>")
        if args.side == "both":
            h = row.get("h2h", "")
            cls = {"win": "pass", "tie": "tie", "loss": "fail", "both_fail": "fail"}.get(h, "")
            html.append(f"<td class='{cls}'>{h}</td>")
        html.append("</tr>")
    html.append("</table>")
    (HERE / "objective_report.html").write_text("\n".join(html), encoding="utf-8")
    if not args.quiet:
        print(f"\nReport: {HERE / 'objective_report.html'}")


if __name__ == "__main__":
    main()
