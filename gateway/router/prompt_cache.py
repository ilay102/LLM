"""
Provider prefix caching — v0.3.2.

"Memory" in the truest sense: the model remembering the KV cache of a stable
prefix so we don't pay full input price to re-process it on every call. Most
production SaaS apps send the SAME system prompt (and often the same few-shot
examples) on every single request — that entire prefix should be a cache hit
after the first call.

The economics are asymmetric:
  - Anthropic cache read:  ~90% off input  (min 1024 tokens, else no-op + a
                            25% WRITE premium on the first call — so guard it)
  - DeepSeek cache hit:    ~98% off input  ($0.0028/1M vs $0.14)  — automatic,
                            requires identical prefix ORDERING (never reorder!)
  - OpenAI:                ~50% off input  — automatic, just don't break it

So our job per provider:
  - Anthropic: place ONE cache_control breakpoint at the end of the stable
    prefix (system + leading few-shot), but ONLY if that prefix is >= the
    minimum token count, otherwise the breakpoint is wasted (or costs more).
  - DeepSeek / OpenAI: inject nothing (caching is automatic), but we must
    guarantee we never reorder the prefix anywhere in the pipeline.

This replaces the old `inject_prompt_cache` which only handled a single
>2000-char system string and ignored few-shot examples + the token minimum.

Public API:
    inject_cache_breakpoints(messages, provider, token_estimator) -> messages
    provider_of(model_name) -> "anthropic"|"deepseek"|"openai"|"other"
"""
from __future__ import annotations
import logging

LOG = logging.getLogger("gateway.prompt_cache")

# Anthropic requires a cacheable block to be >= 1024 tokens (Sonnet/Opus) or
# 2048 (Haiku) to be eligible. Use the higher bar to be safe across tiers.
ANTHROPIC_MIN_TOKENS = 2048

# Rough chars-per-token for estimation when no tokenizer is handy. Anthropic
# English text is ~3.5-4 chars/token; use 4 as a conservative (under-)estimate
# so we don't inject a breakpoint that turns out to be below the minimum.
CHARS_PER_TOKEN = 4


def provider_of(model_name: str) -> str:
    m = (model_name or "").lower()
    if "anthropic" in m or "claude" in m:
        return "anthropic"
    if "deepseek" in m:
        return "deepseek"
    if "openai" in m or "gpt" in m or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    return "other"


def _text_len(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def _already_has_cache_control(messages: list[dict]) -> bool:
    for m in messages:
        c = m.get("content")
        if isinstance(c, list) and any(isinstance(b, dict) and b.get("cache_control") for b in c):
            return True
    return False


def _estimate_tokens(text_chars: int) -> int:
    return text_chars // CHARS_PER_TOKEN


def stable_prefix_index(messages: list[dict]) -> int:
    """
    Return the index AFTER the last message of the stable prefix.
    The stable prefix = all leading system messages, plus any leading
    assistant/user few-shot pairs that come BEFORE the final user turn.

    Heuristic: walk from the start; the prefix ends at the last message before
    the final user message (the actual query). Everything up to and including
    the last system / few-shot turn is "stable" across calls.
    """
    if not messages:
        return 0
    # The final user turn is the volatile part. The prefix is everything before
    # the LAST user message.
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"),
                    default=len(messages) - 1)
    return max(last_user, 0)  # breakpoint goes at end of message[last_user-1]


def inject_cache_breakpoints(messages: list[dict], provider: str) -> list[dict]:
    """
    For Anthropic, mark the end of the stable prefix with cache_control if the
    prefix is large enough. For other providers, return unchanged (their cache
    is automatic) — but NEVER reorder messages.
    """
    if not messages or _already_has_cache_control(messages):
        return messages

    if provider != "anthropic":
        # DeepSeek/OpenAI cache automatically. We only need to NOT reorder,
        # which we don't. Nothing to inject.
        return messages

    # --- Anthropic: find the stable prefix and measure it ------------------
    prefix_end = stable_prefix_index(messages)  # index of final user turn
    if prefix_end <= 0:
        return messages  # nothing before the user turn

    prefix_chars = sum(_text_len(m.get("content")) for m in messages[:prefix_end])
    if _estimate_tokens(prefix_chars) < ANTHROPIC_MIN_TOKENS:
        # Below the minimum: a breakpoint here is wasted (and the first call
        # would pay a 25% write premium for nothing). Skip.
        LOG.debug("prefix %d est-tokens < %d min; no breakpoint",
                  _estimate_tokens(prefix_chars), ANTHROPIC_MIN_TOKENS)
        return messages

    # Place cache_control on the LAST block of the message just before the
    # final user turn (the boundary of the stable prefix).
    out = [dict(m) for m in messages]
    boundary = prefix_end - 1
    bm = out[boundary]
    content = bm.get("content")
    if isinstance(content, str):
        bm["content"] = [{"type": "text", "text": content,
                          "cache_control": {"type": "ephemeral"}}]
    elif isinstance(content, list) and content:
        # tag the last text block
        new_content = [dict(b) if isinstance(b, dict) else b for b in content]
        for b in reversed(new_content):
            if isinstance(b, dict) and "text" in b:
                b["cache_control"] = {"type": "ephemeral"}
                break
        bm["content"] = new_content
    else:
        return messages  # unexpected shape; don't touch
    LOG.info("injected Anthropic cache breakpoint at msg %d (prefix ~%d tokens)",
             boundary, _estimate_tokens(prefix_chars))
    return out
