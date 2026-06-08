"""
Upstream-failure injection tests.

Mock the LiteLLM router to simulate provider outages and verify:
  - Cascade verifier doesn't crash on malformed responses
  - Verifier fails open when grader is unavailable (doesn't escalate on infra error)
  - Response shape stays OpenAI-compatible even when downstream errors
  - No PII placeholders leak through error paths

These complement test_verifier.py (which mocks normal flows) — these test
ABNORMAL flows. All offline (no API).
"""
import asyncio
import pytest
import sys
from unittest.mock import MagicMock, AsyncMock

if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

import verifier
from verifier import heuristic_fail, verify, VerifyResult

pytestmark = pytest.mark.unit


def _resp(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


# ---- Verifier resilience to malformed responses ----------------------------

def test_verifier_no_choices_key():
    """Provider returned a payload missing 'choices' entirely."""
    fail, _ = heuristic_fail({})
    assert fail, "empty-dict response should escalate (treat as failure)"


def test_verifier_choices_is_empty_list():
    """Choices array is empty (some providers return this on filter trigger)."""
    fail, _ = heuristic_fail({"choices": []})
    assert fail


def test_verifier_message_is_missing():
    """Choice has no message field at all."""
    fail, _ = heuristic_fail({"choices": [{"finish_reason": "stop"}]})
    assert fail


def test_verifier_content_is_none():
    """message.content is explicitly None (some APIs return this on tool-call-only)."""
    fail, _ = heuristic_fail({"choices": [{"message": {"content": None}}]})
    assert fail


def test_verifier_content_is_non_string():
    """message.content is a list (multi-modal) or dict — verifier should not crash."""
    for weird_content in ([], {}, [{"type": "text", "text": "hi"}], 42):
        try:
            fail, reason = heuristic_fail({"choices": [{"message": {"content": weird_content}}]})
        except Exception as e:
            pytest.fail(f"verifier crashed on content={weird_content!r}: {e}")
        # Result varies; just must not raise
        assert isinstance(fail, bool)


# ---- LLM grader resilience -------------------------------------------------

class _CrashingRouter:
    """Router that raises on every call (provider outage)."""
    async def acompletion(self, **kwargs):
        raise RuntimeError("upstream 503: all providers down")


class _MalformedGraderRouter:
    """Grader returns content the verifier can't parse as a 1-5 grade."""
    def __init__(self, content):
        self._content = content
    async def acompletion(self, **kwargs):
        m = MagicMock()
        m.model_dump = lambda: {"choices": [{"message": {"content": self._content}}]}
        return m


@pytest.mark.asyncio
async def test_grader_crashes_fails_open():
    """Grader exception → fail open (don't escalate; user gets the cheap response)."""
    router = _CrashingRouter()
    r = await verify(router, _resp("a decent answer"),
                     [{"role": "user", "content": "q"}],
                     mode="llm", threshold=3)
    assert r.escalate is False, "grader crash should NOT escalate (fail open)"
    assert r.score is None
    assert "unavailable" in r.reason.lower() or "passed" in r.reason.lower()


@pytest.mark.asyncio
async def test_grader_returns_garbage_fails_open():
    """Grader returns non-numeric content → score None → fail open."""
    for garbage in ("banana", "", "the answer is fine", "🚀", None):
        router = _MalformedGraderRouter(garbage or "")
        r = await verify(router, _resp("an answer"),
                         [{"role": "user", "content": "q"}],
                         mode="llm", threshold=3)
        assert r.escalate is False, f"garbage grader output {garbage!r} should fail open"


@pytest.mark.asyncio
async def test_grader_returns_out_of_range_number():
    """Grader returns '7' (out of 1-5 range) — first digit IS in [1-5] so '7'
    won't match; we look for [1-5] specifically. So 7 → no match → score None
    → fail open."""
    router = _MalformedGraderRouter("7")
    r = await verify(router, _resp("answer"),
                     [{"role": "user", "content": "q"}], mode="llm", threshold=3)
    # The regex [1-5] won't match '7'; score is None
    assert r.score is None
    assert r.escalate is False  # fail open


@pytest.mark.asyncio
async def test_grader_score_at_threshold_doesnt_escalate():
    """Score == threshold should NOT escalate (escalate only when score < threshold)."""
    router = _MalformedGraderRouter("3")
    r = await verify(router, _resp("answer"),
                     [{"role": "user", "content": "q"}], mode="llm", threshold=3)
    assert r.score == 3
    assert r.escalate is False, "score AT threshold should pass, not escalate"


@pytest.mark.asyncio
async def test_grader_score_just_below_threshold_escalates():
    router = _MalformedGraderRouter("2")
    r = await verify(router, _resp("answer"),
                     [{"role": "user", "content": "q"}], mode="llm", threshold=3)
    assert r.score == 2
    assert r.escalate is True


# ---- Mode-off bypass — every other check must be skipped -------------------

@pytest.mark.asyncio
async def test_mode_off_skips_all_checks_even_with_placeholder_in_response():
    """When mode='off', the verifier MUST return no-escalate regardless of content.
    This is the explicit-disable path — operator turned it off on purpose."""
    text_with_leak = "Email: <EMAIL_ADDRESS>"
    r = await verify(None, _resp(text_with_leak),
                     [{"role": "user", "content": "q"}], mode="off")
    assert r.escalate is False
    assert r.grader_called is False


# ---- Refusal patterns at the edge ------------------------------------------

def test_verifier_recognises_extended_refusal_patterns():
    """Confirm the v0.3.x extended refusal regex catches common variants."""
    for refusal in [
        "I cannot help with that request.",
        "I'm sorry, I can't assist.",
        "As an AI language model, I don't have access to...",
        "I am unable to provide that information.",
        "I apologize, but that's outside my scope.",
        "Unfortunately, I can't do that.",
        "Sorry, but I'm not able to help here.",
    ]:
        fail, reason = heuristic_fail(_resp(refusal))
        assert fail, f"missed refusal: {refusal!r}"
        assert "refusal" in reason.lower()


def test_verifier_doesnt_misread_non_refusal_starting_with_i():
    """Sentences starting with 'I' but not refusals should pass."""
    for ok in [
        "Italy is a country in Europe.",
        "I think the answer is 42.",          # benign opinion, not a refusal
        "It looks like the issue is X.",
        "Identifying the cause: ...",
    ]:
        fail, _ = heuristic_fail(_resp(ok))
        assert not fail, f"false refusal positive on: {ok!r}"


# ---- Pipeline shape: response stays OpenAI-compatible after escalation -----

def test_verify_result_dataclass_is_serializable():
    """VerifyResult should be safe to put into log records / responses."""
    r = VerifyResult(escalate=True, reason="test", score=3, grader_called=True)
    # dataclass field access
    assert r.escalate is True
    assert r.reason == "test"
    assert r.score == 3
    # Should also stringify cleanly for logging
    s = str(r)
    assert "escalate" in s and "test" in s
