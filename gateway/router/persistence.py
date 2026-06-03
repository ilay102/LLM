"""
SQLite-backed event log. Replaces the bare shadow_log.jsonl file with a
queryable store so the daily summary, weekly report, and per-tenant
dashboards have real data.

The JSONL writer is kept as a parallel append (for grep/tail debugging),
but persistence.py is the canonical store. Schema is forward-compatible:
new columns added via `_ensure_schema()`.

Public API:
    record(event: dict) -> None
    summarize(tenant_id, since_ts) -> dict
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

LOG = logging.getLogger("gateway.persistence")
DB_PATH = Path(os.environ.get("EVENTS_DB", "/app/data/events.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        with _LOCK:
            if _CONN is None:
                _CONN = _connect()
                _ensure_schema(_CONN)
    return _CONN


def _ensure_schema(c: sqlite3.Connection) -> None:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        tenant_id TEXT,
        pilot_id TEXT,
        tier TEXT,
        tier_reason TEXT,
        tier_confidence REAL,
        model_returned TEXT,
        latency_ms REAL,
        cache_hit TEXT,
        cache_similarity REAL,
        cascade INTEGER DEFAULT 0,
        input_tokens INTEGER,
        output_tokens INTEGER,
        cached_input_tokens INTEGER,
        cost_usd REAL,
        baseline_cost_usd REAL,
        pii_entities_json TEXT,
        prompt_hash TEXT,
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_events_tenant_ts ON events(tenant_id, ts);
    CREATE INDEX IF NOT EXISTS idx_events_pilot_ts ON events(pilot_id, ts);
    """)
    c.commit()


def record(event: dict) -> None:
    """Append an event. Fails open — logs but never raises."""
    try:
        c = conn()
        c.execute(
            """
            INSERT INTO events (
                ts, tenant_id, pilot_id, tier, tier_reason, tier_confidence,
                model_returned, latency_ms, cache_hit, cache_similarity,
                cascade, input_tokens, output_tokens, cached_input_tokens,
                cost_usd, baseline_cost_usd, pii_entities_json,
                prompt_hash, error
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.get("ts", time.time()),
                event.get("tenant"), event.get("pilot_id"),
                event.get("tier"), event.get("tier_reason"),
                event.get("tier_confidence"),
                event.get("model_returned"), event.get("latency_ms"),
                event.get("cache_hit"), event.get("cache_similarity"),
                1 if event.get("cascade") else 0,
                event.get("input_tokens"), event.get("output_tokens"),
                event.get("cached_input_tokens"),
                event.get("cost_usd"), event.get("baseline_cost_usd"),
                json.dumps(event.get("pii_entities") or []),
                event.get("prompt_hash"), event.get("error"),
            ),
        )
        c.commit()
    except Exception:
        LOG.exception("event record failed")


def summarize(tenant_id: str | None = None, since_ts: float | None = None) -> dict:
    where, params = [], []
    if tenant_id:
        where.append("tenant_id = ?"); params.append(tenant_id)
    if since_ts:
        where.append("ts >= ?"); params.append(since_ts)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    c = conn()
    row = c.execute(
        f"""SELECT
            COUNT(*) AS n,
            COALESCE(SUM(cost_usd), 0) AS total_cost,
            COALESCE(SUM(baseline_cost_usd), 0) AS total_baseline,
            COALESCE(SUM(input_tokens), 0) AS in_tok,
            COALESCE(SUM(output_tokens), 0) AS out_tok,
            COALESCE(SUM(CASE WHEN cache_hit IS NOT NULL THEN 1 ELSE 0 END), 0) AS cache_hits,
            COALESCE(SUM(cascade), 0) AS cascade_count
        FROM events {where_sql}""",
        params,
    ).fetchone()

    tiers = c.execute(
        f"""SELECT tier, COUNT(*) AS c
            FROM events {where_sql}
            GROUP BY tier ORDER BY c DESC""",
        params,
    ).fetchall()

    return {
        "n_calls": row["n"],
        "total_cost_usd": row["total_cost"] or 0,
        "total_baseline_usd": row["total_baseline"] or 0,
        "savings_usd": (row["total_baseline"] or 0) - (row["total_cost"] or 0),
        "input_tokens": row["in_tok"] or 0,
        "output_tokens": row["out_tok"] or 0,
        "cache_hits": row["cache_hits"] or 0,
        "cascade_count": row["cascade_count"] or 0,
        "tier_distribution": {r["tier"]: r["c"] for r in tiers},
    }
