"""
Tenant store — SQLite-backed multi-tenant key management.

A "tenant" represents one customer environment (one paying account, one pilot,
or one internal team). Each tenant has:
  - id, name, contact email
  - API keys (we store sha256 hashes, never plaintext)
  - per-tenant config: min_tier guardrail, monthly_budget_usd, allowed_models
  - usage counters: month-to-date spend, total calls

The DB lives at $TENANT_DB (default /app/data/tenants.db) and is created on
first import if missing. Migrations are handled inline by `_ensure_schema()`.

Why SQLite and not Postgres: zero ops cost, perfect for single-deploy gateways
running in a customer's VPC, file-based backup is trivial. Switch to Postgres
later if a tenant fans out to multiple gateway replicas.
"""
from __future__ import annotations
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("TENANT_DB", "/app/data/tenants.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK = threading.RLock()  # reentrant: create_tenant holds lock while calling conn()


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_CONN: sqlite3.Connection | None = None


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
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_email TEXT,
        min_tier TEXT DEFAULT 'cheap',          -- floor: never route below this
        monthly_budget_usd REAL DEFAULT 1000,   -- hard cap
        allowed_models_json TEXT DEFAULT '[]',  -- empty list = all
        notes TEXT,
        created_at REAL NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS tenant_keys (
        key_hash TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        label TEXT,
        created_at REAL NOT NULL,
        revoked_at REAL,
        last_used_at REAL
    );

    CREATE TABLE IF NOT EXISTS tenant_usage (
        tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        period TEXT NOT NULL,                   -- YYYY-MM
        calls INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0,
        last_updated REAL NOT NULL,
        PRIMARY KEY (tenant_id, period)
    );

    CREATE INDEX IF NOT EXISTS idx_tkeys_tenant ON tenant_keys(tenant_id);
    """)
    c.commit()


# ---------- Public API -----------------------------------------------------

@dataclass
class Tenant:
    id: str
    name: str
    contact_email: str | None
    min_tier: str
    monthly_budget_usd: float
    allowed_models: list[str]
    active: bool


def create_tenant(
    tenant_id: str,
    name: str,
    contact_email: str | None = None,
    min_tier: str = "cheap",
    monthly_budget_usd: float = 1000.0,
    notes: str | None = None,
) -> str:
    """Create a tenant and return a freshly-minted API key (shown ONCE)."""
    with _LOCK:
        c = conn()
        api_key = "viren_" + secrets.token_urlsafe(24)
        c.execute(
            "INSERT INTO tenants (id, name, contact_email, min_tier, "
            "monthly_budget_usd, notes, created_at, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (tenant_id, name, contact_email, min_tier, monthly_budget_usd,
             notes, time.time()),
        )
        c.execute(
            "INSERT INTO tenant_keys (key_hash, tenant_id, label, created_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash_key(api_key), tenant_id, "initial", time.time()),
        )
        c.commit()
    return api_key


def mint_key(tenant_id: str, label: str = "rotated") -> str:
    with _LOCK:
        c = conn()
        api_key = "viren_" + secrets.token_urlsafe(24)
        c.execute(
            "INSERT INTO tenant_keys (key_hash, tenant_id, label, created_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash_key(api_key), tenant_id, label, time.time()),
        )
        c.commit()
    return api_key


def revoke_key(api_key: str) -> bool:
    with _LOCK:
        c = conn()
        cur = c.execute(
            "UPDATE tenant_keys SET revoked_at = ? WHERE key_hash = ? AND revoked_at IS NULL",
            (time.time(), _hash_key(api_key)),
        )
        c.commit()
    return cur.rowcount > 0


def lookup_by_key(api_key: str) -> Tenant | None:
    """The hot-path call. Should be sub-millisecond on SQLite."""
    if not api_key:
        return None
    row = conn().execute(
        """
        SELECT t.id, t.name, t.contact_email, t.min_tier, t.monthly_budget_usd,
               t.allowed_models_json, t.active
        FROM tenant_keys k
        JOIN tenants t ON t.id = k.tenant_id
        WHERE k.key_hash = ? AND k.revoked_at IS NULL AND t.active = 1
        """,
        (_hash_key(api_key),),
    ).fetchone()
    if not row:
        return None
    # Best-effort last_used_at update; do not block on it
    try:
        conn().execute(
            "UPDATE tenant_keys SET last_used_at = ? WHERE key_hash = ?",
            (time.time(), _hash_key(api_key)),
        )
        conn().commit()
    except Exception:
        pass
    try:
        allowed = json.loads(row["allowed_models_json"] or "[]")
    except Exception:
        allowed = []
    return Tenant(
        id=row["id"], name=row["name"], contact_email=row["contact_email"],
        min_tier=row["min_tier"], monthly_budget_usd=row["monthly_budget_usd"],
        allowed_models=allowed, active=bool(row["active"]),
    )


def list_tenants() -> list[dict]:
    rows = conn().execute(
        "SELECT id, name, contact_email, min_tier, monthly_budget_usd, "
        "       active, created_at FROM tenants ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- Usage & budget -------------------------------------------------

def current_period() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def record_usage(tenant_id: str, cost_usd: float) -> None:
    p = current_period()
    with _LOCK:
        c = conn()
        c.execute(
            "INSERT INTO tenant_usage (tenant_id, period, calls, cost_usd, last_updated) "
            "VALUES (?, ?, 1, ?, ?) "
            "ON CONFLICT(tenant_id, period) DO UPDATE SET "
            "  calls = calls + 1, cost_usd = cost_usd + ?, last_updated = ?",
            (tenant_id, p, cost_usd, time.time(), cost_usd, time.time()),
        )
        c.commit()


def get_usage(tenant_id: str, period: str | None = None) -> dict:
    p = period or current_period()
    row = conn().execute(
        "SELECT calls, cost_usd FROM tenant_usage WHERE tenant_id = ? AND period = ?",
        (tenant_id, p),
    ).fetchone()
    return {"calls": row["calls"] if row else 0,
            "cost_usd": row["cost_usd"] if row else 0.0,
            "period": p}


def over_budget(tenant: Tenant) -> tuple[bool, float, float]:
    """Returns (is_over, current_spend, budget)."""
    usage = get_usage(tenant.id)
    return usage["cost_usd"] >= tenant.monthly_budget_usd, usage["cost_usd"], tenant.monthly_budget_usd
