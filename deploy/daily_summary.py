#!/usr/bin/env python3
"""
daily_summary.py — read a client's shadow_log.jsonl, produce the metrics
Person B sends in the weekly progress email.

Usage:
    python deploy/daily_summary.py --client-id acme
    python deploy/daily_summary.py --client-id acme --csv      # also write summary.csv
    python deploy/daily_summary.py --client-id acme --since 7d # last N days

Computes:
    - total calls
    - total $ saved vs. what they'd have paid hitting their old default
    - cache hit rate (split by exact / semantic)
    - tier distribution
    - p50 / p95 / p99 latency
    - cascade rate
    - top 5 most expensive prompts (anonymized excerpt)

Designed to be safe to run during an active pilot — read-only on the log file.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def parse_since(since: str) -> timedelta | None:
    if not since:
        return None
    m = re.match(r"^(\d+)\s*([dh])$", since.strip().lower())
    if not m:
        raise SystemExit(f"--since must look like '7d' or '24h', got {since!r}")
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(days=n) if unit == "d" else timedelta(hours=n)


# Baseline cost = what the call would have cost on tier-balanced if we'd routed
# everything there (close to what most clients do today with Sonnet/GPT-4o).
BASELINE_INPUT_PER_TOKEN = 0.000003   # Sonnet input
BASELINE_OUTPUT_PER_TOKEN = 0.000015  # Sonnet output


def estimate_baseline_cost(row: dict) -> float:
    in_t = row.get("input_tokens") or 0
    out_t = row.get("output_tokens") or 0
    return (in_t or 0) * BASELINE_INPUT_PER_TOKEN + (out_t or 0) * BASELINE_OUTPUT_PER_TOKEN


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--client-id", required=True)
    p.add_argument("--log-path", help="Override default path")
    p.add_argument("--since", help="Window like '7d' or '24h' (default: all)")
    p.add_argument("--csv", action="store_true", help="Also write summary.csv next to the log")
    args = p.parse_args()

    here = Path(__file__).resolve().parent
    default_log = here / "clients" / args.client_id / "logs" / "shadow_log.jsonl"
    log_path = Path(args.log_path) if args.log_path else default_log
    if not log_path.exists():
        # Try the container's relative path (gateway writes to /app/shadow_log.jsonl
        # which is mounted into ./logs/)
        alt = here / "clients" / args.client_id / "logs" / "shadow_log.jsonl"
        if alt.exists():
            log_path = alt
        else:
            raise SystemExit(f"no log file at {log_path}")

    since_delta = parse_since(args.since) if args.since else None
    cutoff_ts = (datetime.now(timezone.utc) - since_delta).timestamp() if since_delta else 0

    rows: list[dict] = []
    with open(log_path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ts", 0) >= cutoff_ts:
                rows.append(r)

    n = len(rows)
    if n == 0:
        print(f"No log entries found for client={args.client_id}"
              f"{' since '+args.since if args.since else ''}.")
        return

    # --- Aggregate -----------------------------------------------------------
    total_cost = sum(r.get("cost_usd", 0.0) for r in rows)
    total_baseline = sum(estimate_baseline_cost(r) for r in rows)
    savings = total_baseline - total_cost
    savings_pct = (savings / total_baseline) if total_baseline > 0 else 0

    cache_hits = sum(1 for r in rows if r.get("cache_hit"))
    cache_exact = sum(1 for r in rows if r.get("cache_hit") == "exact")
    cache_semantic = sum(1 for r in rows if r.get("cache_hit") == "semantic")
    cascade_count = sum(1 for r in rows if r.get("cascade"))

    tier_dist = Counter(r.get("tier", "unknown") for r in rows)
    model_dist = Counter(r.get("model_returned", "unknown") for r in rows)

    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]

    total_in_tok = sum(r.get("input_tokens") or 0 for r in rows)
    total_out_tok = sum(r.get("output_tokens") or 0 for r in rows)

    # Top 5 most expensive
    top5 = sorted(rows, key=lambda r: -r.get("cost_usd", 0))[:5]

    # --- Print human report --------------------------------------------------
    bar = "─" * 64
    print()
    print(f"  VIREN Pilot Summary — client: {args.client_id}")
    if args.since:
        print(f"  Window: last {args.since}")
    print(f"  {bar}")
    print(f"  Total calls:           {n:,}")
    print(f"  Cost (this gateway):   ${total_cost:,.4f}")
    print(f"  Cost (baseline):       ${total_baseline:,.4f}   <- what you'd pay without routing")
    print(f"  Savings:               ${savings:,.4f}  ({savings_pct*100:5.1f}%)")
    if n > 0:
        proj_30d = (savings / n) * (n * 30 / max(1, ((rows[-1]['ts'] - rows[0]['ts']) / 86400) or 1))
        print(f"  Projected 30-day:      ${proj_30d:,.2f}")
    print(f"  {bar}")
    print(f"  Cache hit rate:        {cache_hits/n*100:5.1f}%  ({cache_exact} exact, {cache_semantic} semantic)")
    print(f"  Cascade rate:          {cascade_count/n*100:5.1f}%  ({cascade_count}/{n})")
    print(f"  {bar}")
    print(f"  Tier distribution:")
    for tier, c in tier_dist.most_common():
        print(f"    {tier:10s}  {c:6,}  ({c/n*100:5.1f}%)")
    print(f"  {bar}")
    print(f"  Model distribution (top 5):")
    for model, c in model_dist.most_common(5):
        short = model.split("/")[-1] if model else "?"
        print(f"    {short:30s}  {c:6,}  ({c/n*100:5.1f}%)")
    print(f"  {bar}")
    print(f"  Latency:  p50={percentile(latencies, 0.5):7.0f}ms   "
          f"p95={percentile(latencies, 0.95):7.0f}ms   "
          f"p99={percentile(latencies, 0.99):7.0f}ms")
    print(f"  {bar}")
    print(f"  Tokens:   in={total_in_tok:,}   out={total_out_tok:,}")
    print(f"  {bar}")
    print(f"  Top 5 most expensive prompts:")
    for i, r in enumerate(top5, 1):
        excerpt = (r.get("request_excerpt") or "")[:80]
        print(f"    {i}. ${r.get('cost_usd', 0):.5f}  tier={r.get('tier','?'):8s}  "
              f"\"{excerpt}…\"")
    print()

    # --- Optional CSV --------------------------------------------------------
    if args.csv:
        csv_path = log_path.parent / "summary.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "value"])
            w.writerow(["total_calls", n])
            w.writerow(["total_cost_usd", f"{total_cost:.6f}"])
            w.writerow(["baseline_cost_usd", f"{total_baseline:.6f}"])
            w.writerow(["savings_usd", f"{savings:.6f}"])
            w.writerow(["savings_pct", f"{savings_pct:.4f}"])
            w.writerow(["cache_hit_rate", f"{cache_hits/n:.4f}"])
            w.writerow(["cascade_rate", f"{cascade_count/n:.4f}"])
            w.writerow(["p50_ms", f"{percentile(latencies, 0.5):.0f}"])
            w.writerow(["p95_ms", f"{percentile(latencies, 0.95):.0f}"])
            w.writerow(["p99_ms", f"{percentile(latencies, 0.99):.0f}"])
            w.writerow(["input_tokens", total_in_tok])
            w.writerow(["output_tokens", total_out_tok])
            for tier, c in tier_dist.most_common():
                w.writerow([f"tier__{tier}", c])
        print(f"  CSV written: {csv_path}")


if __name__ == "__main__":
    main()
