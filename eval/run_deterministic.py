#!/usr/bin/env python3
"""
Deterministic eval — checks gateway answers against expected_behavior rules
WITHOUT any judge LLM call. Free, fast, and 100% reproducible.

For corpus rows that carry an `expected_behavior`, this verifies the gateway's
answer satisfies a machine-checkable rule (contains a string, is valid JSON,
matches a regex). This is the cheapest quality signal and runs in CI.

It reads the gateway answers from a results file produced by
scripts/eval_corpus.py (eval_results.jsonl), joined to the corpus by id.

Usage:
  python eval/run_deterministic.py \
      --corpus eval/corpus_v1.jsonl \
      --results scripts/eval_results.jsonl

Exit code 0 if pass-rate >= --min-pass (default 0.90), else 1 (CI gate).
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def check(behavior: dict, answer: str) -> tuple[bool, str]:
    t = behavior.get("type")
    a = answer or ""
    if t == "contains":
        v = behavior["value"]
        return (v.lower() in a.lower(), f"expected substring {v!r}")
    if t == "contains_any":
        vals = behavior["values"]
        return (any(v.lower() in a.lower() for v in vals),
                f"expected any of {vals}")
    if t == "regex":
        return (re.search(behavior["value"], a) is not None,
                f"expected regex {behavior['value']!r}")
    if t == "valid_json":
        stripped = a.strip()
        if stripped.startswith("```"):
            parts = stripped.split("```")
            stripped = parts[1] if len(parts) > 1 else stripped
            if stripped.startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.strip()
        try:
            obj = json.loads(stripped)
        except Exception:
            return False, "not valid JSON"
        for field in behavior.get("fields", []):
            if isinstance(obj, dict) and field not in obj:
                return False, f"JSON missing field {field!r}"
        return True, "valid JSON"
    return True, "no check"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="eval/corpus_v1.jsonl")
    p.add_argument("--results", default="scripts/eval_results.jsonl")
    p.add_argument("--min-pass", type=float, default=0.90)
    args = p.parse_args()

    corpus = {r["id"]: r for r in load_jsonl(Path(args.corpus))}
    results = {r["id"]: r for r in load_jsonl(Path(args.results))}

    checked = passed = 0
    failures = []
    for cid, row in corpus.items():
        behavior = row.get("expected_behavior")
        if not behavior:
            continue
        res = results.get(cid)
        if not res:
            continue  # not in this eval run (e.g. --limit)
        answer = (res.get("gateway") or {}).get("answer", "")
        ok, why = check(behavior, answer)
        checked += 1
        if ok:
            passed += 1
        else:
            failures.append((cid, why, (answer or "")[:80]))

    if checked == 0:
        print("No deterministic-check rows in this results set "
              "(did you run eval_corpus.py on corpus_v1?).")
        return 0

    rate = passed / checked
    print(f"Deterministic checks: {passed}/{checked} passed ({rate:.1%})")
    if failures:
        print("\nFailures:")
        for cid, why, excerpt in failures:
            print(f"  #{cid}: {why}  — got: {excerpt!r}")

    if rate < args.min_pass:
        print(f"\nFAIL: pass-rate {rate:.1%} < threshold {args.min_pass:.0%}")
        return 1
    print(f"\nPASS: pass-rate {rate:.1%} >= threshold {args.min_pass:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
