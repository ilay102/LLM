#!/usr/bin/env python3
"""
Bucket empty-response failures from eval_results.jsonl by model, finish_reason,
and completion-token count. Tells us whether the v0.3.7 "empty answer" cluster
is truncation (finish_reason=length, completion_tokens=max), genuine empty
content (finish_reason=stop, completion_tokens=0), or upstream errors.

Usage:
    python scripts/diagnose_empty.py
    python scripts/diagnose_empty.py --results path/to/eval_results.jsonl

Output:
    - Bucketed summary printed to stdout
    - Per-id detail for every empty/missing gateway response
    - Same for baseline, for comparison
"""
from __future__ import annotations
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent


def _short_model(name: str | None) -> str:
    if not name:
        return "?"
    n = name.lower()
    if "haiku" in n: return "haiku"
    if "sonnet" in n: return "sonnet"
    if "opus" in n: return "opus"
    if "mini" in n: return "gpt-4o-mini"
    if "v4-pro" in n or "v4_pro" in n: return "deepseek-v4-pro"
    if "v4-flash" in n or "v4_flash" in n: return "deepseek-v4-flash"
    if "reasoner" in n or "r1" in n: return "deepseek-reasoner"
    if "deepseek" in n: return "deepseek-other"
    return name.split("/")[-1][:25]


def _is_empty(answer) -> bool:
    if answer is None: return True
    if not isinstance(answer, str): return True
    return len(answer.strip()) == 0


def _bucket(side: str, rows: list[dict]) -> dict:
    """Returns dict with: empties (list), by_model (Counter), by_finish (Counter),
    truncated (count), genuine_stop_empty (count), error (count)."""
    empties = []
    by_model: Counter = Counter()
    by_finish: Counter = Counter()
    by_model_finish: Counter = Counter()
    truncated = 0           # finish_reason=length
    genuine_stop_empty = 0  # finish_reason=stop, content empty (model returned nothing)
    error = 0               # call-level error (no finish_reason at all)
    avg_completion_tokens = []

    for r in rows:
        side_data = r.get(side) or {}
        ans = side_data.get("answer", "")
        if not _is_empty(ans):
            continue
        model = _short_model(side_data.get("model"))
        finish = side_data.get("finish_reason")
        if side_data.get("error"):
            error += 1
            by_finish["<error>"] += 1
            by_model_finish[(model, "<error>")] += 1
        else:
            if finish == "length":
                truncated += 1
            elif finish in (None, "stop"):
                genuine_stop_empty += 1
            by_finish[finish or "<none>"] += 1
            by_model_finish[(model, finish or "<none>")] += 1
        by_model[model] += 1
        comp = side_data.get("out_tokens") or 0
        avg_completion_tokens.append(comp)
        empties.append({
            "id": r.get("id"),
            "model": model,
            "finish": finish,
            "out_tokens": comp,
            "prompt": (r.get("prompt") or "")[:140],
            "error": side_data.get("error"),
        })
    return {
        "side": side,
        "total_empties": len(empties),
        "by_model": by_model,
        "by_finish": by_finish,
        "by_model_finish": by_model_finish,
        "truncated_count": truncated,
        "genuine_stop_empty_count": genuine_stop_empty,
        "error_count": error,
        "avg_completion_tokens": (sum(avg_completion_tokens) / len(avg_completion_tokens)
                                  if avg_completion_tokens else 0),
        "empties": empties,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", default=str(HERE / "eval_results.jsonl"))
    args = p.parse_args()

    rows = [json.loads(l) for l in open(args.results, encoding="utf-8")]
    print(f"Loaded {len(rows)} rows from {args.results}\n")

    for side in ("gateway", "baseline"):
        b = _bucket(side, rows)
        print(f"=== {side.upper()} — {b['total_empties']} empty responses out of {len(rows)} ===")
        if b["total_empties"] == 0:
            print("  (none — all rows have content)\n")
            continue
        print(f"  by finish_reason: {dict(b['by_finish'])}")
        print(f"  by model:         {dict(b['by_model'])}")
        print(f"  avg out_tokens on empties: {b['avg_completion_tokens']:.0f}")
        print(f"  truncated (length):       {b['truncated_count']}")
        print(f"  genuine empty (stop):     {b['genuine_stop_empty_count']}")
        print(f"  call errors:              {b['error_count']}")
        print(f"\n  Cross-tab (model, finish_reason):")
        for (model, finish), n in sorted(b['by_model_finish'].items(), key=lambda x: -x[1]):
            print(f"    {model:25s} {finish or '<none>':12s} : {n}")
        print(f"\n  Per-id detail:")
        for e in b["empties"]:
            err = f" ERROR={e['error'][:60]}" if e.get("error") else ""
            print(f"    id={e['id']:>3}  model={e['model']:22s} finish={(e['finish'] or '<none>'):10s} "
                  f"out_tok={e['out_tokens']:>4}{err}")
            print(f"          prompt: {e['prompt']}")
        print()


if __name__ == "__main__":
    main()
