"""
Conversation memory — v0.3.4.

Two pieces of "remembering across turns of one conversation":

1. TIER STICKINESS (default ON, pure safety):
   Once a conversation escalates to a higher tier, keep it there. A multi-turn
   agent that started on Opus shouldn't suddenly drop to Haiku mid-loop and
   hallucinate a tool name. Stickiness only ever routes UP — it can never
   degrade a turn — so it's safe to enable by default.

2. SESSION SUMMARIZATION (default OFF, opt-in per tenant):
   When a conversation's input grows past a threshold, summarize the oldest
   turns with a cheap model to cut input tokens. This changes semantics (drops
   verbatim history), so it's off unless a tenant explicitly enables it.

State lives in Redis keyed by conversation id, short TTL. Fail-open: no Redis
or any error -> no stickiness, never raise.
"""
from __future__ import annotations
import hashlib
import logging
import os

LOG = logging.getLogger("gateway.conversation")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CONV_TTL = int(os.environ.get("CONVERSATION_TTL_SECONDS", "3600"))
TIER_ORDER = {"cheap": 0, "balanced": 1, "frontier": 2}
ORDER_TIER = {v: k for k, v in TIER_ORDER.items()}

_redis = None
_redis_tried = False


def _r():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    try:
        import redis
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _redis.ping()
    except Exception:
        LOG.warning("conversation memory: Redis unavailable, stickiness disabled")
        _redis = None
    return _redis


def conversation_id(header_id: str | None, messages: list[dict]) -> str:
    """Stable id for a conversation. Prefer the client-supplied header; else
    hash the first two message contents (stable across turns of the same chat)."""
    if header_id:
        return "conv:" + hashlib.sha256(header_id.encode()).hexdigest()[:16]
    seed_parts = []
    for m in messages[:2]:
        c = m.get("content")
        seed_parts.append(c if isinstance(c, str) else str(c))
    seed = "||".join(seed_parts)
    return "conv:" + hashlib.sha256(seed.encode()).hexdigest()[:16]


def get_max_tier(conv_id: str) -> str | None:
    r = _r()
    if r is None:
        return None
    try:
        return r.get(conv_id + ":maxtier")
    except Exception:
        return None


def bump_max_tier(conv_id: str, tier: str) -> None:
    r = _r()
    if r is None:
        return
    try:
        cur = r.get(conv_id + ":maxtier")
        cur_rank = TIER_ORDER.get(cur, -1) if cur else -1
        if TIER_ORDER.get(tier, 0) > cur_rank:
            r.setex(conv_id + ":maxtier", CONV_TTL, tier)
        else:
            # refresh TTL even if not higher
            r.expire(conv_id + ":maxtier", CONV_TTL)
    except Exception:
        pass


def apply_stickiness(tier: str, conv_id: str) -> tuple[str, str | None]:
    """
    Floor `tier` at the highest tier this conversation has used.
    Returns (effective_tier, reason_or_None). Then records the effective tier.
    """
    prior = get_max_tier(conv_id)
    effective = tier
    reason = None
    if prior and TIER_ORDER.get(prior, 0) > TIER_ORDER.get(tier, 0):
        effective = prior
        reason = f"conversation stickiness: floored to {prior} (was {tier})"
    bump_max_tier(conv_id, effective)
    return effective, reason


def estimate_input_chars(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            total += sum(len(b.get("text", "")) for b in c if isinstance(b, dict))
    return total


async def summarize_if_long(router, messages: list[dict], threshold_chars: int = 24000):
    """
    If the conversation is long, replace all-but-last-2 turns with a cheap-model
    summary. Returns (messages, summarized:bool). Off unless caller invokes it.
    ~24000 chars ≈ 6000 tokens.
    """
    if estimate_input_chars(messages) < threshold_chars or len(messages) <= 4:
        return messages, False
    # Keep system messages + last 2 turns; summarize the middle.
    system = [m for m in messages if m.get("role") == "system"]
    convo = [m for m in messages if m.get("role") != "system"]
    if len(convo) <= 2:
        return messages, False
    to_summarize = convo[:-2]
    keep = convo[-2:]
    transcript = "\n".join(
        f"{m.get('role')}: {m.get('content') if isinstance(m.get('content'), str) else ''}"
        for m in to_summarize
    )
    try:
        r = await router.acompletion(
            model="tier-cheap",
            messages=[{"role": "user",
                       "content": "Summarize this conversation so far in <=150 "
                                  "words, preserving any facts, names, numbers, "
                                  "and decisions a later turn would need:\n\n" + transcript[:8000]}],
            max_tokens=250, temperature=0.0,
        )
        rd = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        summary = (rd.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not summary:
            return messages, False
        new_messages = system + [
            {"role": "system", "content": "[Earlier conversation summary]: " + summary}
        ] + keep
        return new_messages, True
    except Exception:
        LOG.exception("summarization failed; keeping full history")
        return messages, False
