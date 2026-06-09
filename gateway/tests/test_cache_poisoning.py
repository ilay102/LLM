"""
Cache-poisoning regression tests (v0.3.8).

The v0.3.7 200-prompt eval surfaced 26 cached empty responses being served
back to users every subsequent eval, all from deepseek-v4 balanced-tier
paths. Root cause: an upstream provider returned content="" once, the empty
got stored in the semantic cache, and every later semantically-similar
lookup hit it with cached=true.

Two defenses, both tested here:
  1. semantic_cache.store() refuses to write empty / whitespace-only content
  2. main.py runs _recover_empty_content on cache hits before serving them
     and busts the cache entry if still empty after recovery
"""
import sys
from unittest.mock import MagicMock

import pytest

# Stub litellm before importing main / semantic_cache (they expect it)
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()
# Stub embeddings (heavy import path)
if "embeddings" not in sys.modules:
    emb_stub = MagicMock()
    emb_stub.embed = MagicMock(return_value=MagicMock(tobytes=lambda: b""))
    emb_stub.EMBED_DIM = 384
    sys.modules["embeddings"] = emb_stub
# Stub redis so semantic_cache import doesn't try to connect
if "redis" not in sys.modules:
    redis_stub = MagicMock()
    sys.modules["redis"] = redis_stub
    sys.modules["redis.commands"] = MagicMock()
    sys.modules["redis.commands.search"] = MagicMock()
    sys.modules["redis.commands.search.field"] = MagicMock()
    sys.modules["redis.commands.search.indexDefinition"] = MagicMock()
    sys.modules["redis.commands.search.query"] = MagicMock()
    sys.modules["redis.exceptions"] = MagicMock()

import semantic_cache  # noqa: E402
import main as gateway_main  # noqa: E402

pytestmark = pytest.mark.unit


def _make_cache():
    """SemanticCache with a mocked Redis client. Tracks setex/hset calls."""
    sc = semantic_cache.SemanticCache.__new__(semantic_cache.SemanticCache)
    sc.r = MagicMock()
    sc.r.setex = MagicMock()
    sc.r.hset = MagicMock()
    sc.r.expire = MagicMock()
    sc.ttl = 86400
    sc.threshold = 0.95
    return sc


@pytest.fixture(autouse=True)
def _stub_embed(monkeypatch):
    """Replace embed() with a deterministic stub so tests don't need the real
    sentence-transformers model (which may or may not be importable depending
    on which other tests ran first)."""
    class _V:
        def tobytes(self_):  # noqa: ANN001
            return b"\x00" * 4
    monkeypatch.setattr(semantic_cache, "embed", lambda text: _V())


def _resp(content=None, **extra_msg_fields):
    msg = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    msg.update(extra_msg_fields)
    return {"choices": [{"message": msg, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


# ---- Cache STORE guard ----------------------------------------------------

def test_store_refuses_empty_content():
    """The v0.3.7 bug shape — content=='' must NOT be stored."""
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content=""),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_not_called()
    cache.r.hset.assert_not_called()


def test_store_refuses_whitespace_only_content():
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content="   \n\t  "),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_not_called()


def test_store_refuses_none_content():
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content=None),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_not_called()


def test_store_accepts_real_content():
    """Sanity: normal responses still get cached."""
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content="A perfectly good answer."),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_called_once()
    cache.r.hset.assert_called_once()


def test_store_accepts_empty_content_when_reasoning_content_present():
    """If the answer is in reasoning_content (DeepSeek thinking-mode shape),
    we still want to cache it — main.py will recover it on the way out."""
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content="", reasoning_content="The actual answer lives here."),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_called_once()


def test_store_still_skips_high_temperature():
    """Existing guard not broken by new code."""
    cache = _make_cache()
    cache.store(
        prompt_text="any prompt",
        response=_resp(content="real content"),
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.9,
    )
    cache.r.setex.assert_not_called()


def test_store_still_skips_tool_calls():
    """Existing guard not broken by new code."""
    cache = _make_cache()
    response = {"choices": [{"message": {
        "role": "assistant", "content": "", "tool_calls": [{"id": "1"}]
    }}]}
    cache.store(
        prompt_text="any prompt", response=response,
        tenant="t1", model_class="tier-balanced",
        system_hash="sys", tool_hash="notools", temperature=0.0,
    )
    cache.r.setex.assert_not_called()


# ---- Cache HIT verification (recovery + empty bust) -----------------------
# These exercise the cache-hit guard in main.py via _recover_empty_content.
# We test the recovery helper itself; the cache-bust path runs end-to-end
# in the integration eval (next live run).

def test_recover_heals_cached_empty_via_reasoning_content():
    """If a poisoned-but-recoverable response is in cache, recovery rewrites
    content from reasoning_content so the user gets a real answer."""
    cached = _resp(content="", reasoning_content="recovered answer")
    gateway_main._recover_empty_content(cached, "balanced")
    assert cached["choices"][0]["message"]["content"] == "recovered answer"


def test_recover_leaves_unrecoverable_empty_alone_for_bust():
    """If content is empty AND no fallback fields, recovery is a no-op so
    the cache-hit path in main.py can detect and bust the entry."""
    cached = _resp(content="")
    gateway_main._recover_empty_content(cached, "balanced")
    assert cached["choices"][0]["message"]["content"] == ""
