"""
Cascade verifier — decides whether a cheap-tier response is good enough or
needs escalation to a higher tier.

Two-stage design (cost-conscious):
  1. HEURISTIC pre-filter (free, no LLM call): obvious failures — empty,
     truncated, refusal, invalid JSON when JSON was requested. If this fires,
     escalate immediately WITHOUT paying for an LLM grader call.
  2. LLM grader (one cheap call): for responses that pass the heuristic, ask a
     small model to rate 1-5 how completely+correctly the response answers the
     user's request. Score below threshold -> escalate.

Why this beats the old heuristic-only verifier: it catches *semantic* failures
(terse-but-incomplete classification, subtly-wrong extraction) that regex can't
see. Those were the v0.2.2 regressions. We only run it on cheap-tier responses
(the risky minority), so the added latency/cost is bounded.

Config (env, overridable per-tenant):
  VERIFIER_MODE       off | heuristic | llm   (default: llm)
  VERIFIER_THRESHOLD  int 1-5                  (default: 3 — escalate if < 3)
  VERIFIER_MODEL      grader model alias       (default: tier-cheap, i.e. Haiku/mini)
"""
from __future__ import annotations
import json
import logging
import os
import re
from dataclasses import dataclass

LOG = logging.getLogger("gateway.verifier")

VERIFIER_MODE = os.environ.get("VERIFIER_MODE", "llm").lower()
VERIFIER_THRESHOLD = int(os.environ.get("VERIFIER_THRESHOLD", "3"))
VERIFIER_MODEL = os.environ.get("VERIFIER_MODEL", "tier-cheap")

_REFUSAL = re.compile(
    r"^\s*(i (can'?t|cannot|am not able|don'?t know)|as an ai|i'?m sorry)",
    re.IGNORECASE,
)


@dataclass
class VerifyResult:
    escalate: bool
    reason: str
    score: int | None = None      # LLM grade 1-5, None if heuristic-only
    grader_called: bool = False


def _extract_text(response: dict) -> str:
    choice = (response.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return msg.get("content") or ""


def _finish_reason(response: dict) -> str | None:
    choice = (response.get("choices") or [{}])[0]
    return choice.get("finish_reason")


def heuristic_fail(response: dict, expects_json: bool = False) -> tuple[bool, str]:
    """Free obvious-failure check. Returns (should_escalate, reason)."""
    text = _extract_text(response)
    finish = _finish_reason(response)

    if finish == "length":
        return True, "truncated (finish_reason=length)"
    if not isinstance(text, str) or len(text.strip()) < 4:
        return True, "empty or near-empty response"
    if _REFUSAL.match(text.strip()):
        return True, "refusal pattern at start"
    if expects_json:
        stripped = text.strip()
        if stripped.startswith("```"):
            # strip code fences
            inner = stripped.split("```", 2)
            stripped = inner[1] if len(inner) > 1 else stripped
            if stripped.startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.strip().rstrip("`").strip()
        try:
            json.loads(stripped)
        except Exception:
            return True, "JSON requested but response is not valid JSON"
    return False, ""


GRADER_PROMPT = (
    "You are a strict QA grader. Below is a user request and an AI response.\n"
    "Rate from 1 to 5 how COMPLETELY and CORRECTLY the response answers the "
    "request.\n"
    "  5 = fully correct and complete\n"
    "  4 = correct, minor omissions\n"
    "  3 = mostly correct but notable gaps\n"
    "  2 = partially wrong or significantly incomplete\n"
    "  1 = wrong, irrelevant, or refuses\n"
    "Output ONLY the single digit. No words.\n\n"
    "=== USER REQUEST ===\n{request}\n\n"
    "=== AI RESPONSE ===\n{response}\n\n"
    "Grade (1-5):"
)


async def llm_grade(router, response: dict, user_request: str) -> int | None:
    """Fire one grader call via the LiteLLM router. Returns 1-5 or None on error."""
    text = _extract_text(response)
    body = GRADER_PROMPT.format(request=user_request[:3000], response=text[:3000])
    try:
        r = await router.acompletion(
            model=VERIFIER_MODEL,
            messages=[{"role": "user", "content": body}],
            max_tokens=4,
            temperature=0.0,
        )
        rd = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        out = _extract_text(rd).strip()
        m = re.search(r"[1-5]", out)
        return int(m.group(0)) if m else None
    except Exception:
        LOG.exception("verifier grader call failed")
        return None


def _last_user_request(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


async def verify(
    router,
    response: dict,
    messages: list[dict],
    expects_json: bool = False,
    mode: str | None = None,
    threshold: int | None = None,
) -> VerifyResult:
    """
    Decide whether to escalate a cheap-tier response.
    `mode`/`threshold` override the env defaults (used for per-tenant config).
    """
    m = (mode or VERIFIER_MODE).lower()
    thr = threshold if threshold is not None else VERIFIER_THRESHOLD

    if m == "off":
        return VerifyResult(escalate=False, reason="verifier disabled")

    # Stage 1: free heuristic pre-filter (always runs)
    fail, reason = heuristic_fail(response, expects_json=expects_json)
    if fail:
        return VerifyResult(escalate=True, reason=f"heuristic: {reason}")

    if m == "heuristic":
        return VerifyResult(escalate=False, reason="heuristic passed")

    # Stage 2: LLM grader
    user_request = _last_user_request(messages)
    score = await llm_grade(router, response, user_request)
    if score is None:
        # Grader failed — fail open (don't escalate on infra error)
        return VerifyResult(escalate=False, reason="grader unavailable; passed", grader_called=True)
    escalate = score < thr
    return VerifyResult(
        escalate=escalate,
        reason=f"llm grade={score} (threshold {thr})",
        score=score,
        grader_called=True,
    )
