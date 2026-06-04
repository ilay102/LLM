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
