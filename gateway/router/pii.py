"""
PII redaction via Microsoft Presidio.

Lazy-loads the analyzer + anonymizer on first call so gateway boot stays fast.
If Presidio isn't installed the module degrades to a regex-only mode that
catches the most common patterns (emails, phones, credit cards, US SSNs).
Better to over-redact than to leak.

Used in two places:
  - semantic_cache.store(): redact prompt + response BEFORE writing to Redis.
  - shadow_log entries: optional, controlled by PII_REDACT_LOGS env var.

Public API:
    redact(text) -> (redacted_text, entities_found)
        entities_found: list of {entity_type, count}
"""
from __future__ import annotations
import logging
import re
import threading
from typing import Any

LOG = logging.getLogger("gateway.pii")

# --- Regex fallback (used if Presidio isn't installed) ---------------------
_PATTERNS = [
    ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE_NUMBER", re.compile(r"\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("API_KEY", re.compile(r"\b(sk-[a-zA-Z0-9_-]{20,}|viren_[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,})\b")),
]

_ANALYZER: Any = None
_ANONYMIZER: Any = None
_LOAD_TRIED = False
_LOAD_LOCK = threading.Lock()


def _try_load_presidio() -> None:
    global _ANALYZER, _ANONYMIZER, _LOAD_TRIED
    if _LOAD_TRIED:
        return
    with _LOAD_LOCK:
        if _LOAD_TRIED:
            return
        _LOAD_TRIED = True
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            _ANALYZER = AnalyzerEngine()
            _ANONYMIZER = AnonymizerEngine()
            LOG.info("Presidio loaded — PII redaction is active.")
        except ImportError:
            LOG.warning("Presidio not installed — falling back to regex-only PII redaction. "
                        "Install: pip install presidio-analyzer presidio-anonymizer")
        except Exception as e:
            LOG.exception("Presidio init failed (%s) — using regex fallback.", e)


def redact(text: str) -> tuple[str, list[dict]]:
    """Return (redacted_text, list_of_entities).

    `entities` is a list of {"entity_type": str, "count": int} suitable for logging.
    PII content itself is NEVER returned in the entities list — only the type + count.
    """
    if not text or not isinstance(text, str):
        return text, []

    _try_load_presidio()

    # --- Presidio path ------------------------------------------------------
    if _ANALYZER is not None and _ANONYMIZER is not None:
        try:
            results = _ANALYZER.analyze(text=text, language="en")
            if not results:
                return text, []
            anon = _ANONYMIZER.anonymize(text=text, analyzer_results=results)
            entities: dict[str, int] = {}
            for r in results:
                entities[r.entity_type] = entities.get(r.entity_type, 0) + 1
            return anon.text, [{"entity_type": k, "count": v} for k, v in entities.items()]
        except Exception:
            LOG.exception("presidio failed mid-call; falling back to regex")

    # --- Regex fallback -----------------------------------------------------
    entities: dict[str, int] = {}
    out = text
    for entity_type, pat in _PATTERNS:
        def _sub(m):
            entities[entity_type] = entities.get(entity_type, 0) + 1
            return f"<{entity_type}>"
        out = pat.sub(_sub, out)
    return out, [{"entity_type": k, "count": v} for k, v in entities.items()]


def redact_messages(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Redact PII in the content of every message. Returns (new_messages, entities_total)."""
    if not messages:
        return messages, []
    total: dict[str, int] = {}
    out = []
    for m in messages:
        new_m = dict(m)
        c = m.get("content")
        if isinstance(c, str):
            redacted, ents = redact(c)
            new_m["content"] = redacted
            for e in ents:
                total[e["entity_type"]] = total.get(e["entity_type"], 0) + e["count"]
        elif isinstance(c, list):
            # OpenAI/Anthropic multimodal content
            new_content = []
            for block in c:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    redacted, ents = redact(block["text"])
                    nb = dict(block); nb["text"] = redacted
                    new_content.append(nb)
                    for e in ents:
                        total[e["entity_type"]] = total.get(e["entity_type"], 0) + e["count"]
                else:
                    new_content.append(block)
            new_m["content"] = new_content
        out.append(new_m)
    return out, [{"entity_type": k, "count": v} for k, v in total.items()]
