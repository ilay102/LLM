"""
Regression tests for the v0.3.8 DeepSeek reasoning-budget cascade.

The v0.3.8 retry (after cache flush) revealed 10/30 failures with the
exact same shape:

    {
      "finish_reason": "length",
      "message": {"content": "", ...},
      "usage": {
        "completion_tokens": 1500,
        "completion_tokens_details": {"reasoning_tokens": 1500}
      }
    }

DeepSeek-V4-Pro/Flash thinking mode burned the entire max_tokens budget
on internal reasoning_tokens before generating any visible output. Same
prompts work fine on Sonnet, which doesn't have a separate reasoning
budget consuming the output allowance.

main._content_consumed_by_reasoning() detects this exact shape so we
can cascade to a Sonnet-only fallback alias instead of serving the
empty response.
"""
import sys
from unittest.mock import MagicMock

import pytest

if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

import main as gateway_main  # noqa: E402

pytestmark = pytest.mark.unit


def _resp(content="", finish_reason="length",
          completion_tokens=1500, reasoning_tokens=1500):
    """Build the exact shape we observed from DeepSeek-V4-Flash."""
    return {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {"role": "assistant", "content": content,
                        "refusal": None, "tool_calls": None},
            "index": 0,
        }],
        "usage": {
            "completion_tokens": completion_tokens,
            "prompt_tokens": 50,
            "total_tokens": 50 + completion_tokens,
            "completion_tokens_details": {
                "reasoning_tokens": reasoning_tokens,
            },
        },
        "model": "deepseek/deepseek-v4-flash",
    }


# ---- Positive cases (cascade SHOULD trigger) -------------------------------

def test_detects_exact_v038_failure_shape():
    """The literal shape from the debug dump: finish=length, content='',
    completion_tokens=1500, reasoning_tokens=1500."""
    rd = _resp(content="", finish_reason="length",
               completion_tokens=1500, reasoning_tokens=1500)
    assert gateway_main._content_consumed_by_reasoning(rd) is True


def test_detects_when_reasoning_is_95pct_of_budget():
    """The threshold is 95% — reasoning slightly less than full budget still
    counts (model produced a tiny bit of output then ran out)."""
    rd = _resp(content="", finish_reason="length",
               completion_tokens=1500, reasoning_tokens=1430)  # 95.3%
    assert gateway_main._content_consumed_by_reasoning(rd) is True


def test_detects_whitespace_only_content_as_empty():
    """Content with only whitespace is effectively empty."""
    rd = _resp(content="   \n\t  ", finish_reason="length",
               completion_tokens=1500, reasoning_tokens=1500)
    assert gateway_main._content_consumed_by_reasoning(rd) is True


# ---- Negative cases (cascade SHOULD NOT trigger) ---------------------------

def test_skips_when_content_is_present():
    """Real content present — no cascade needed regardless of reasoning_tokens."""
    rd = _resp(content="A real answer here.", finish_reason="length",
               completion_tokens=1500, reasoning_tokens=1500)
    assert gateway_main._content_consumed_by_reasoning(rd) is False


def test_skips_when_finish_reason_is_stop():
    """finish_reason=stop means model finished naturally — empty content is
    a different problem (model genuinely returned nothing), not budget
    exhaustion. Don't waste a Sonnet re-fire on that."""
    rd = _resp(content="", finish_reason="stop",
               completion_tokens=10, reasoning_tokens=10)
    assert gateway_main._content_consumed_by_reasoning(rd) is False


def test_skips_when_no_reasoning_tokens():
    """Anthropic/OpenAI responses don't have reasoning_tokens. If a response
    has finish_reason=length and empty content but no reasoning_tokens,
    it's a different failure mode (real truncation) and not what this
    cascade is for."""
    rd = {
        "choices": [{"finish_reason": "length",
                     "message": {"content": ""}}],
        "usage": {"completion_tokens": 1500, "completion_tokens_details": {}},
    }
    assert gateway_main._content_consumed_by_reasoning(rd) is False


def test_skips_when_reasoning_is_small_fraction():
    """If reasoning was modest (e.g. 200 of 1500 tokens), the rest WAS the
    answer — content should be non-empty. If it IS empty here, something
    else is wrong; cascade won't help."""
    rd = _resp(content="", finish_reason="length",
               completion_tokens=1500, reasoning_tokens=200)
    assert gateway_main._content_consumed_by_reasoning(rd) is False


def test_skips_when_completion_tokens_is_zero():
    """Edge case: usage reports 0 completion tokens — can't divide."""
    rd = {
        "choices": [{"finish_reason": "length",
                     "message": {"content": ""}}],
        "usage": {"completion_tokens": 0,
                  "completion_tokens_details": {"reasoning_tokens": 0}},
    }
    assert gateway_main._content_consumed_by_reasoning(rd) is False


# ---- Robustness ------------------------------------------------------------

def test_handles_malformed_responses_safely():
    """Never raise on weird input."""
    for bad in [None, {}, {"choices": None}, {"choices": []},
                {"choices": [None]}, {"choices": [{}]},
                {"choices": [{"message": None}]},
                {"choices": [{"message": "not a dict"}]},
                "string instead of dict",
                42]:
        try:
            result = gateway_main._content_consumed_by_reasoning(bad)
        except Exception as e:
            pytest.fail(f"raised on {bad!r}: {e}")
        assert isinstance(result, bool)


def test_combined_with_recover_empty_content():
    """If reasoning_content has the actual answer, recovery should fix it
    first and the cascade should not fire (no longer empty)."""
    rd = {
        "choices": [{
            "finish_reason": "length",
            "message": {"role": "assistant", "content": "",
                        "reasoning_content": "Recovered answer."},
        }],
        "usage": {"completion_tokens": 1500,
                  "completion_tokens_details": {"reasoning_tokens": 1500}},
    }
    # First run recovery
    gateway_main._recover_empty_content(rd, "balanced")
    # Now content is non-empty, cascade should NOT fire
    assert gateway_main._content_consumed_by_reasoning(rd) is False
    assert rd["choices"][0]["message"]["content"] == "Recovered answer."
