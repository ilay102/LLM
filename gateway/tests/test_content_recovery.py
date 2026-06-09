"""
Unit tests for the v0.3.7 defensive content-recovery helper in main.py.

The 200-prompt eval revealed 37 empty-content responses, all from DeepSeek-V4
paths, with the model billed for the full max_tokens worth of output. The
hypothesis is that the actual answer lands in a non-OpenAI-standard field
(`reasoning_content` is the prime suspect for DeepSeek-V4 / R1) while
`message.content` comes back empty.

`_recover_empty_content` walks the response choices and, when content is
empty, copies the first non-empty fallback field into content so downstream
(verifier, cache, client) sees a normal OpenAI shape.
"""
import pytest
import sys
from unittest.mock import MagicMock

# main.py imports litellm at module load; stub it
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

# These imports trigger main.py module load; need litellm stub above first
import main as gateway_main

pytestmark = pytest.mark.unit


def _resp(content=None, reasoning_content=None, other=None):
    """Build a minimal response_dict shaped like LiteLLM's model_dump output."""
    msg = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    if other:
        msg.update(other)
    return {"choices": [{"message": msg, "finish_reason": "stop"}]}


def test_recovery_from_reasoning_content_when_content_empty():
    """The exact v0.3.7 bug shape: content='', reasoning_content=<answer>."""
    rd = _resp(content="", reasoning_content="The factorial in one line is lambda n: 1 if n<=1 else n*factorial(n-1)")
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == \
        "The factorial in one line is lambda n: 1 if n<=1 else n*factorial(n-1)"


def test_recovery_when_content_is_none():
    """None content is the OpenAI SDK's representation when no text was emitted."""
    rd = _resp(content=None, reasoning_content="real answer here")
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == "real answer here"


def test_recovery_treats_whitespace_only_as_empty():
    rd = _resp(content="   \n\t  ", reasoning_content="recovered")
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == "recovered"


def test_no_recovery_when_content_is_real():
    """Don't clobber a real answer with a stale reasoning field."""
    rd = _resp(content="real answer", reasoning_content="internal reasoning trace")
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == "real answer"


def test_no_recovery_when_no_fallback_field_present():
    """Empty content + no fallback fields → leave as-is (verifier will escalate)."""
    rd = _resp(content="")
    gateway_main._recover_empty_content(rd, "cheap")
    assert rd["choices"][0]["message"]["content"] == ""


def test_recovery_walks_multiple_choices():
    """If choices has multiple items, recover each independently."""
    rd = {"choices": [
        {"message": {"role": "assistant", "content": "", "reasoning_content": "first"}, "finish_reason": "stop"},
        {"message": {"role": "assistant", "content": "second", "reasoning_content": "ignored"}, "finish_reason": "stop"},
        {"message": {"role": "assistant", "content": None, "reasoning": "third"}, "finish_reason": "stop"},
    ]}
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == "first"
    assert rd["choices"][1]["message"]["content"] == "second"  # unchanged
    assert rd["choices"][2]["message"]["content"] == "third"


def test_recovery_tries_field_order_correctly():
    """When multiple fallback fields are present, take the first one in
    _CONTENT_FALLBACK_FIELDS order (reasoning_content first)."""
    rd = _resp(content="", reasoning_content="rc-value",
               other={"text": "text-value", "reasoning": "r-value"})
    gateway_main._recover_empty_content(rd, "balanced")
    assert rd["choices"][0]["message"]["content"] == "rc-value"


def test_recovery_handles_malformed_response_safely():
    """Should never raise on weird shapes — gateway must stay up."""
    for bad in [
        None,
        {},
        {"choices": None},
        {"choices": []},
        {"choices": [None]},
        {"choices": [{"message": None}]},
        {"choices": [{"message": "not a dict"}]},
        {"choices": [{}]},
    ]:
        try:
            gateway_main._recover_empty_content(bad, "balanced")
        except Exception as e:
            pytest.fail(f"recovery raised on {bad!r}: {e}")


def test_recovery_leaves_multimodal_content_alone():
    """Multimodal content (list of blocks) should not be touched even if
    reasoning_content is present — that case is out of scope."""
    rd = {"choices": [{"message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": "..."}],
        "reasoning_content": "should not be used",
    }}]}
    gateway_main._recover_empty_content(rd, "balanced")
    # content stays as the list
    assert isinstance(rd["choices"][0]["message"]["content"], list)


def test_recovery_skips_non_string_fallback_values():
    """If reasoning_content is itself a list or dict, skip it (don't crash)."""
    rd = _resp(content="", reasoning_content={"weird": "shape"})
    rd["choices"][0]["message"]["text"] = "real text fallback"
    gateway_main._recover_empty_content(rd, "balanced")
    # Should have skipped the dict reasoning_content and picked up text
    assert rd["choices"][0]["message"]["content"] == "real text fallback"
