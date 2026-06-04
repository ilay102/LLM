"""
Prometheus metrics — v0.3.5.

Answers the "how do we monitor it?" question every engineering buyer asks.
Exposes a /metrics endpoint (wired in main.py) in Prometheus text format.

Import-safe: if prometheus_client isn't installed, every function here becomes
a no-op and /metrics returns a short notice instead of crashing the gateway.
Same defensive pattern as pii.py (Presidio) — a missing optional dep never
takes the gateway down.

Metrics exposed:
  viren_requests_total{tier, cache_hit, cascaded}   counter
  viren_cost_usd_total{tier}                          counter
  viren_baseline_cost_usd_total                       counter  (what they'd pay direct)
  viren_cache_hits_total{source}                      counter  (exact|semantic)
  viren_cascade_total                                 counter
  viren_errors_total{kind}                            counter
  viren_request_latency_seconds{tier}                 histogram
  viren_pii_entities_total{entity_type}               counter
"""
from __future__ import annotations
import logging

LOG = logging.getLogger("gateway.metrics")

_ENABLED = False
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    _ENABLED = True
except Exception:  # pragma: no cover - exercised only when dep missing
    LOG.warning("prometheus_client not installed — /metrics will return a notice. "
                "Install: pip install prometheus-client")
    CONTENT_TYPE_LATEST = "text/plain"

if _ENABLED:
    REQUESTS = Counter("viren_requests_total", "Total chat requests",
                       ["tier", "cache_hit", "cascaded"])
    COST = Counter("viren_cost_usd_total", "Total cost in USD", ["tier"])
    BASELINE_COST = Counter("viren_baseline_cost_usd_total",
                            "Baseline cost if all traffic went to balanced tier")
    CACHE_HITS = Counter("viren_cache_hits_total", "Cache hits", ["source"])
    CASCADE = Counter("viren_cascade_total", "Cascade escalations")
    ERRORS = Counter("viren_errors_total", "Errors", ["kind"])
    LATENCY = Histogram("viren_request_latency_seconds", "Request latency", ["tier"],
                        buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32))
    PII = Counter("viren_pii_entities_total", "PII entities redacted", ["entity_type"])


def record_request(tier: str, cache_hit: str | None, cascaded: bool,
                   cost_usd: float, baseline_cost_usd: float,
                   latency_ms: float, pii_entities: list[dict] | None) -> None:
    """Called from the post-hook for every request. Never raises."""
    if not _ENABLED:
        return
    try:
        ch = cache_hit or "none"
        REQUESTS.labels(tier=tier or "unknown", cache_hit=ch,
                        cascaded=str(bool(cascaded)).lower()).inc()
        COST.labels(tier=tier or "unknown").inc(max(cost_usd or 0.0, 0.0))
        BASELINE_COST.inc(max(baseline_cost_usd or 0.0, 0.0))
        if cache_hit:
            CACHE_HITS.labels(source=cache_hit).inc()
        if cascaded:
            CASCADE.inc()
        LATENCY.labels(tier=tier or "unknown").observe(max((latency_ms or 0) / 1000.0, 0))
        for e in (pii_entities or []):
            PII.labels(entity_type=e.get("entity_type", "unknown")).inc(e.get("count", 1))
    except Exception:
        LOG.exception("metrics record failed (non-fatal)")


def record_error(kind: str) -> None:
    if not _ENABLED:
        return
    try:
        ERRORS.labels(kind=kind).inc()
    except Exception:
        pass


def render() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    if not _ENABLED:
        return (b"# prometheus_client not installed; metrics disabled.\n",
                "text/plain")
    return generate_latest(), CONTENT_TYPE_LATEST


def enabled() -> bool:
    return _ENABLED
