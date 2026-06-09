#!/usr/bin/env python3
"""
Flush the VIREN semantic cache namespace from Redis.

Use when:
  - Cache has been poisoned with bad/empty responses (v0.3.7 incident)
  - Schema or pricing changes mean prior cached responses are stale
  - You want a clean baseline before an eval run

Usage:
    REDIS_URL=redis://localhost:6379 python scripts/cache_flush.py
    # or
    python scripts/cache_flush.py --redis-url redis://other:6379 --dry-run

Output: count of keys scanned + deleted, broken down by prefix.
"""
from __future__ import annotations
import argparse
import os
import sys
from collections import Counter

try:
    import redis
except ImportError:
    print("pip install redis", file=sys.stderr)
    sys.exit(1)


KEY_PREFIX = "semcache:"  # mirrors gateway/router/semantic_cache.py


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379"))
    p.add_argument("--prefix", default=KEY_PREFIX,
                   help="Key prefix to flush (default: semcache:)")
    p.add_argument("--dry-run", action="store_true",
                   help="Count and list keys but don't delete.")
    p.add_argument("--batch", type=int, default=500, help="DELETE batch size.")
    args = p.parse_args()

    r = redis.Redis.from_url(args.redis_url, decode_responses=False)

    try:
        r.ping()
    except Exception as e:
        print(f"ERROR: cannot reach Redis at {args.redis_url}: {e}", file=sys.stderr)
        return 1

    print(f"Connected to {args.redis_url}")
    print(f"Scanning for keys matching '{args.prefix}*'...")

    seen: Counter = Counter()
    to_delete: list[bytes] = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, match=args.prefix + "*", count=1000)
        for key in keys:
            ks = key.decode("utf-8", errors="replace") if isinstance(key, bytes) else str(key)
            # Bucket by sub-prefix: semcache:exact:... vs semcache:sem:...
            try:
                bucket = ks.split(":", 2)[1] if ks.count(":") >= 2 else "other"
            except Exception:
                bucket = "other"
            seen[bucket] += 1
            to_delete.append(key)
        if cursor == 0:
            break

    total = sum(seen.values())
    print(f"\nFound {total} keys:")
    for bucket, n in sorted(seen.items(), key=lambda x: -x[1]):
        print(f"  {bucket:15s} {n:>6d}")

    if total == 0:
        print("\nNothing to flush.")
        return 0

    if args.dry_run:
        print(f"\n[dry-run] would delete {total} keys (use without --dry-run to actually delete)")
        return 0

    print(f"\nDeleting {total} keys in batches of {args.batch}...")
    deleted = 0
    for i in range(0, len(to_delete), args.batch):
        batch = to_delete[i:i + args.batch]
        deleted += r.delete(*batch)
        print(f"  deleted {deleted}/{total}", end="\r")
    print()

    # The RediSearch index (semcache_idx) is fine to leave — the HSET entries
    # it indexes are gone, so it'll show empty results until new entries land.
    # Re-creating the index is unnecessary and would interrupt service.
    print(f"\nFlushed {deleted} keys. The semcache_idx RediSearch index is intact "
          "and will index new entries normally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
