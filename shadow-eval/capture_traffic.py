"""
Convert the gateway's shadow_log.jsonl into a Promptfoo dataset.jsonl.

For a real client engagement you'd run this against logs collected during
Phase 1 (read-only logging mode). Sample stratified by route/length so the
eval covers easy + hard prompts.

Usage:
  python capture_traffic.py --source ../gateway/shadow_log.jsonl --out dataset.jsonl --n 200
"""
from __future__ import annotations
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def length_bucket(n_chars: int) -> str:
    if n_chars < 200:
        return "tiny"
    if n_chars < 1000:
        return "short"
    if n_chars < 4000:
        return "medium"
    return "long"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--out", default="dataset.jsonl")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    rng = random.Random(args.seed)
    buckets: dict[str, list[dict]] = defaultdict(list)
    with open(args.source) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = rec.get("request_excerpt") or ""
            if not text.strip():
                continue
            buckets[length_bucket(len(text))].append(rec)

    if not buckets:
        raise SystemExit("no usable rows in source log")

    # Stratified sample: equal across buckets, fall back to whatever exists
    per_bucket = max(args.n // len(buckets), 1)
    chosen: list[dict] = []
    for b, rows in buckets.items():
        rng.shuffle(rows)
        chosen.extend(rows[:per_bucket])
    rng.shuffle(chosen)
    chosen = chosen[: args.n]

    with open(args.out, "w") as f:
        for rec in chosen:
            f.write(json.dumps({"vars": {"prompt": rec["request_excerpt"]}}) + "\n")
    print(f"wrote {len(chosen)} rows to {args.out}")


if __name__ == "__main__":
    main()
