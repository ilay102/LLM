import sys
from unittest.mock import MagicMock, AsyncMock

# litellm not installed in lightweight CI — stub before importing verifier's deps
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

import pytest
import verifier

pytestmark = pytest.mark.unit


def resp(text="OK", finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


# ---- Heuristic pre-filter (free, no LLM) ----------------------------------

def test_heuristic_truncated():
    fail, reason = verifier.heuristic_fail(resp("partial", finish="length"))
    assert fail and "truncated" in reason


def test_heuristic_empty():
    fail, _ = verifier.heuristic_fail(resp(""))
    assert fail


def test_heuristic_refusal():
    fail, _ = verifier.heuristic_fail(resp("I cannot help with that."))
    assert fail


def test_heuristic_invalid_json_when_expected():
    fail, _ = verifier.heuristic_fail(resp("not json at all"), expects_json=True)
    assert fail


def test_heuristic_valid_json_passes():
    fail, _ = verifier.heuristic_fail(resp('{"a": 1}'), expects_json=True)
    assert not fail


def test_heuristic_good_answer_passes():
    fail, _ = verifier.heuristic_fail(resp("This is a complete, correct answer."))
    assert not fail


# ---- Defense-in-depth: PII placeholder leak + literal drop ----------------

def test_heuristic_escalates_on_leaked_pii_placeholder():
    """Regression: the v0.2.2 PII bug let `<EMAIL_ADDRESS>` reach the model
    and back through the response. Even after fixing the input mutation,
    the verifier should catch any placeholder that appears in a response —
    it's a strong signal the model never saw the literal value."""
    for placeholder in ("<EMAIL_ADDRESS>", "<PERSON>", "<PHONE_NUMBER>",
                        "<US_DRIVER_LICENSE>", "<IP_ADDRESS>", "<API_KEY>"):
        text = f"Here is the extracted data:\n\n**Email:** {placeholder}"
        fail, reason = verifier.heuristic_fail(resp(text))
        assert fail, f"verifier missed placeholder {placeholder}"
        assert "placeholder" in reason.lower()


def test_heuristic_passes_when_placeholder_is_just_a_word_in_brackets():
    """Don't false-positive on benign angle-bracket content like <html> or
    <T> generics. Only the specific PII-shaped names trigger the escalation."""
    for benign in ("Use <T> as a type parameter.",
                   "Render the <div> tag.",
                   "Compare A <B or B<A.",
                   "Email: alice@x.com"):
        fail, _ = verifier.heuristic_fail(resp(benign))
        assert not fail, f"false escalation on {benign!r}"


def test_heuristic_escalates_when_email_literal_dropped():
    """Prompt asks to extract email but response doesn't contain it -> escalate."""
    prompt = "Extract email and phone from: 'Reach me at sarah.k@example.org or 555-0142.'"
    # Response that dropped the email entirely (would have been the cheap
    # model's behaviour before v0.2.3 if PII was redacted to nothing).
    fail, reason = verifier.heuristic_fail(
        resp("Sorry, I could not find any contact info."),
        user_prompt=prompt,
    )
    assert fail and "email" in reason.lower()


def test_heuristic_passes_when_email_preserved():
    prompt = "Extract email from: 'Reach me at sarah.k@example.org.'"
    fail, _ = verifier.heuristic_fail(
        resp("**Email:** sarah.k@example.org"),
        user_prompt=prompt,
    )
    assert not fail


def test_heuristic_escalates_when_ip_literal_dropped():
    prompt = "Get the IP address from: 'Login attempt from 192.168.1.55 at 03:42 UTC.'"
    fail, reason = verifier.heuristic_fail(
        resp("To extract the IP, use a regex like `\\d+\\.\\d+\\.\\d+\\.\\d+`."),
        user_prompt=prompt,
    )
    assert fail and "ip" in reason.lower()


def test_heuristic_passes_when_long_prompt_skips_literal_check():
    """Literal-preservation is only enforced for short prompts (< 600 chars).
    Long contexts often reference but don't echo literals — a verbatim
    requirement would generate false positives."""
    long_prompt = "Here is a long support log: " + "x" * 700 + " contact alice@x.com"
    fail, _ = verifier.heuristic_fail(
        resp("I've reviewed the support log and suggest these next steps..."),
        user_prompt=long_prompt,
    )
    assert not fail


# ---- Mode gating -----------------------------------------------------------

@pytest.mark.asyncio
async def test_mode_off_never_escalates():
    r = await verifier.verify(None, resp(""), [{"role": "user", "content": "hi"}], mode="off")
    assert r.escalate is False


@pytest.mark.asyncio
async def test_heuristic_mode_escalates_on_obvious_fail():
    r = await verifier.verify(None, resp("", finish="length"),
                              [{"role": "user", "content": "hi"}], mode="heuristic")
    assert r.escalate is True
    assert r.grader_called is False  # heuristic mode never calls the grader


@pytest.mark.asyncio
async def test_heuristic_mode_passes_good_answer():
    r = await verifier.verify(None, resp("A solid complete answer."),
                              [{"role": "user", "content": "hi"}], mode="heuristic")
    assert r.escalate is False


# ---- LLM grader path (mock the router) ------------------------------------

class FakeRouter:
    def __init__(self, grade_text):
        self._grade = grade_text
    async def acompletion(self, **kwargs):
        m = MagicMock()
        m.model_dump = lambda: {"choices": [{"message": {"content": self._grade}}]}
        return m


@pytest.mark.asyncio
async def test_llm_grader_low_score_escalates():
    router = FakeRouter("2")
    r = await verifier.verify(router, resp("meh terse answer"),
                              [{"role": "user", "content": "explain X in detail"}],
                              mode="llm", threshold=3)
    assert r.escalate is True
    assert r.score == 2
    assert r.grader_called is True


@pytest.mark.asyncio
async def test_llm_grader_high_score_passes():
    router = FakeRouter("5")
    r = await verifier.verify(router, resp("great complete answer"),
                              [{"role": "user", "content": "explain X"}],
                              mode="llm", threshold=3)
    assert r.escalate is False
    assert r.score == 5


@pytest.mark.asyncio
async def test_llm_grader_failure_fails_open():
    # Grader returns garbage -> score None -> fail open (don't escalate on infra error)
    router = FakeRouter("banana")
    r = await verifier.verify(router, resp("answer"),
                              [{"role": "user", "content": "q"}],
                              mode="llm", threshold=3)
    assert r.escalate is False
    assert r.score is None
