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
from typing import Any

LOG = logging.getLogger("gateway.verifier")

# Default is "heuristic" (free obvious-failure checks only — same behavior as
# the proven v0.2.2 cascade). The "llm" grader mode REGRESSED quality on
# cheap-tier-heavy traffic (v0.3 gate: -6.7pp W-T, +slow extra call), so it is
# OFF by default and only worth enabling on reasoning/code-heavy pilot traffic.
VERIFIER_MODE = os.environ.get("VERIFIER_MODE", "heuristic").lower()
VERIFIER_THRESHOLD = int(os.environ.get("VERIFIER_THRESHOLD", "3"))
VERIFIER_MODEL = os.environ.get("VERIFIER_MODEL", "tier-cheap")

_REFUSAL = re.compile(
    r"^\s*(i (can'?t|cannot|am not able|don'?t know|am unable|apologize|apologise)|"
    r"as an ai|as a large|i'?m sorry|i am sorry|sorry,? but|unfortunately)",
    re.IGNORECASE,
)

# Defense-in-depth: detect PII placeholders that leaked into a *response*.
# These are placeholders our redactor (or any upstream system's) would have
# inserted. If a model returns one of these, it never saw the literal value
# and the answer is almost certainly hallucinated. Catches the v0.2.2 bug
# class regardless of which subsystem caused it.
_LEAKED_PLACEHOLDER = re.compile(
    r"<(EMAIL_ADDRESS|PHONE_NUMBER|PERSON|IP_ADDRESS|US_SSN|US_DRIVER_LICENSE|"
    r"US_PASSPORT|CREDIT_CARD|API_KEY|URL|LOCATION|ORGANIZATION|DATE_TIME)>",
)

# Heuristic literal-preservation check: if the user's prompt contained an
# email/phone/IP/URL, the response should mention SOMETHING that looks like
# it. If not, the model dropped the literal value — escalate.
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[-.\s]?)?(?:\(\d{2,4}\)|\d{2,4})[-.\s]\d{3}[-.\s]\d{3,4}(?!\d)")
_IPV4_RE  = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_URL_RE = re.compile(r"\bhttps?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_VERSION_RE = re.compile(r"\b\d+\.\d+\.\d+\b")
_SKU_RE = re.compile(r"\b[A-Z0-9]{2,10}-[A-Z0-9]{2,10}(?:-[A-Z0-9]+)*\b", re.IGNORECASE)

_YES_NO_PROMPT_RE = re.compile(
    r"\b(yes\s*or\s*no|yes\s*/\s*no|true\s*or\s*false|true\s*/\s*false)\b",
    re.IGNORECASE
)
_ONE_WORD_PROMPT_RE = re.compile(
    r"\b(one\s*word|single\s*word|in\s*one\s*word|in\s*a\s*single\s*word|one-word)\b",
    re.IGNORECASE
)


def _ci_contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def extract_options_from_prompt(prompt: str) -> list[str]:
    """Extract allowed options/choices from the prompt text."""
    # 1. Quoted options: 'happy', 'frustrated', or 'neutral'
    quoted = re.findall(r"['\"‘“]([a-zA-Z0-9\s_-]{2,20})['\"’”]", prompt)
    if len(quoted) >= 2:
        return [q.strip() for q in quoted]

    # 2. Slash separated: comms / billing / analytics / storage
    #    Require spaces around "/" to avoid matching protocol names like HTTP/3.
    slash_match = re.search(r"\b[a-zA-Z0-9\s_-]+(?:\s+/\s+[a-zA-Z0-9\s_-]+){1,5}\b", prompt)
    if slash_match:
        parts = [p.strip() for p in slash_match.group(0).split("/")]
        if len(parts) >= 2 and all(len(p) >= 2 for p in parts):
            return parts

    # 3. Uppercase options separated by comma/or: POSITIVE, NEGATIVE, or NEUTRAL
    words = re.findall(r"\b[A-Z]{3,15}\b", prompt)
    ignored = {
        "JSON", "API", "URL", "IP", "CSV", "XML", "HTTP", "HTML", 
        "URI", "SDK", "SSL", "TLS", "LITELLM", "SaaS", "SMB", "ARR",
        "SSO", "JWT", "CRM", "CDN", "AWS", "TCP", "UDP", "S3", "CLI"
    }
    up_options = [w for w in words if w not in ignored]
    if len(up_options) >= 2:
        return up_options

    # 4. Standard "X or Y" or "X, Y, or Z" pattern
    or_match = re.search(r"\b([a-zA-Z0-9\s_-]{2,20})\s*,\s*or\s+([a-zA-Z0-9\s_-]{2,20})\b", prompt, re.IGNORECASE)
    if or_match:
        return [or_match.group(1).strip(), or_match.group(2).strip()]

    or_simple = re.search(r"\b([a-zA-Z0-9_-]{2,20})\s+or\s+([a-zA-Z0-9_-]{2,20})\b", prompt, re.IGNORECASE)
    if or_simple:
        return [or_simple.group(1).strip(), or_simple.group(2).strip()]

    return []


def extract_keys_from_prompt(prompt: str) -> list[str]:
    """Extract expected JSON keys/fields from the prompt text."""
    if not re.search(r"\bjson\b", prompt, re.IGNORECASE):
        return []
        
    quoted = re.findall(r"['\"‘“]([a-zA-Z0-9_-]{2,20})['\"’”]", prompt)
    if len(quoted) >= 2 and re.search(r"\b(keys|fields|properties|attributes)\b", prompt, re.IGNORECASE):
        return [q.strip() for q in quoted]

    # Try matching specific fields/keys/properties/attributes first (most specific keywords)
    match = re.search(r"\b(fields|keys|properties|attributes)\b\s*:?\s*\(?([a-zA-Z0-9\s_,-]{5,100})\)?", prompt, re.IGNORECASE)
    if match:
        val = match.group(2).strip()
        parts = re.split(r",|\band\b|\bor\b", val)
        clean_parts = []
        for p in parts:
            p_clean = p.strip().strip("'\"`()[]{}")
            if p_clean and re.match(r"^[a-zA-Z0-9_-]+$", p_clean) and len(p_clean) >= 2:
                clean_parts.append(p_clean)
        if len(clean_parts) >= 2:
            return clean_parts

    # Fallback to matching after with/containing keywords
    match_general = re.search(r"\b(with|containing)\b\s*:?\s*\(?([a-zA-Z0-9\s_,-]{5,100})\)?", prompt, re.IGNORECASE)
    if match_general:
        val = match_general.group(2).strip()
        parts = re.split(r",|\band\b|\bor\b", val)
        clean_parts = []
        for p in parts:
            p_clean = p.strip().strip("'\"`()[]{}")
            if p_clean and re.match(r"^[a-zA-Z0-9_-]+$", p_clean) and len(p_clean) >= 2:
                clean_parts.append(p_clean)
        if len(clean_parts) >= 2:
            return clean_parts

    # Fallback to matching after 'json' keyword
    paren_match = re.search(r"\bjson\b\s*\(?([a-zA-Z0-9\s_,-]{5,100})\)?", prompt, re.IGNORECASE)
    if paren_match:
        val = paren_match.group(1).strip()
        parts = re.split(r",|\band\b|\bor\b", val)
        clean_parts = []
        for p in parts:
            p_clean = p.strip().strip("'\"`()[]{}")
            if p_clean and re.match(r"^[a-zA-Z0-9_-]+$", p_clean) and len(p_clean) >= 2:
                clean_parts.append(p_clean)
        if len(clean_parts) >= 2:
            return clean_parts
            
    return []


def _json_contains_keys(data: Any, keys: list[str]) -> bool:
    """Check recursively if all keys exist somewhere in the JSON data."""
    if not keys:
        return True
    if isinstance(data, dict):
        found_keys = set()
        for k, v in data.items():
            if k in keys:
                found_keys.add(k)
            for key in keys:
                if key not in found_keys:
                    if isinstance(v, (dict, list)):
                        if _json_contains_keys(v, [key]):
                            found_keys.add(key)
        return len(found_keys) == len(keys)
    elif isinstance(data, list):
        found_keys = set(keys)
        for item in data:
            for key in list(found_keys):
                if _json_contains_keys(item, [key]):
                    found_keys.remove(key)
        return len(found_keys) == 0
    return False


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


def heuristic_fail(
    response: dict,
    expects_json: bool = False,
    user_prompt: str = "",
) -> tuple[bool, str]:
    """Free obvious-failure check. Returns (should_escalate, reason).

    user_prompt is optional; when provided we run literal-preservation checks
    (if the prompt had an email and the response doesn't, the literal was
    dropped — escalate).
    """
    text = _extract_text(response)
    finish = _finish_reason(response)

    if finish == "length":
        return True, "truncated (finish_reason=length)"
    if not isinstance(text, str) or len(text.strip()) == 0:
        return True, "empty response"
    if _REFUSAL.match(text.strip()):
        return True, "refusal pattern at start"

    # Defense-in-depth: PII placeholder leaked into the response. This is the
    # signature of the v0.2.2 bug and any future regression of the same shape.
    leak = _LEAKED_PLACEHOLDER.search(text)
    if leak:
        return True, f"PII placeholder leaked into response: {leak.group(0)}"

    # Literal preservation: if the user gave us an email/phone/IP/URL/version/SKU, the
    # response should echo it back (or at least an equivalent literal).
    # We only check when the prompt CONTAINS the literal AND the prompt is
    # short (< 600 chars) — long contexts often quote-but-don't-repeat.
    # SKIP for yes/no prompts: "Is this URL safe? Yes or no" expects "yes",
    # not the URL repeated back. Literal preservation is for extraction tasks.
    is_yes_no_prompt = bool(_YES_NO_PROMPT_RE.search(user_prompt)) if user_prompt else False
    if user_prompt and len(user_prompt) < 600 and not is_yes_no_prompt:
        for label, rx in (
            ("email", _EMAIL_RE),
            ("phone", _PHONE_RE),
            ("ip", _IPV4_RE),
            ("url", _URL_RE),
            ("version", _VERSION_RE),
            ("sku", _SKU_RE),
        ):
            # Case-normalize for email/url/sku so 'john@x.com' and 'JOHN@X.COM'
            # are considered the same literal. Phones/IPs/versions are digit-
            # only or already case-insensitive, but lowercasing is harmless.
            prompt_hits = {h.lower() for h in rx.findall(user_prompt)}
            if prompt_hits:
                response_hits = {h.lower() for h in rx.findall(text)}
                # If response contains ANY matching literal, fine.
                # If response contains NONE of them, the literal was dropped.
                if not (prompt_hits & response_hits):
                    return True, f"literal {label} from prompt missing in response"

    # Formatting constraint checks (always run, independent of literal preservation)
    if user_prompt and len(user_prompt) < 600:
        # Yes/No formatting constraint check
        if _YES_NO_PROMPT_RE.search(user_prompt):
            clean_start = re.sub(r"^[*_`#\s\[({]+", "", text.strip().lower())
            if not (clean_start.startswith("yes") or clean_start.startswith("no") or
                    clean_start.startswith("true") or clean_start.startswith("false")):
                return True, "yes/no requested but response did not start with yes/no/true/false"

        # One-word formatting constraint check
        if _ONE_WORD_PROMPT_RE.search(user_prompt):
            clean_text = re.sub(r"[^\w\s]", " ", text)
            words = clean_text.strip().split()
            if len(words) > 3:
                return True, f"one-word answer requested but response has {len(words)} words"

        # Options classification constraint check (skipped for translations)
        is_translation = bool(re.search(
            r"\b(translate|translation|in french|in spanish|in german|in japanese|"
            r"in italian|in portuguese|in hebrew|in dutch)\b",
            user_prompt, re.IGNORECASE
        ))
        if not is_translation:
            options = extract_options_from_prompt(user_prompt)
            if options:
                is_yes_no = any(opt.lower() in ("yes", "no", "true", "false") for opt in options)
                if is_yes_no:
                    clean_start = re.sub(r"^[*_`#\s\[({]+", "", text.strip().lower())
                    if not any(clean_start.startswith(opt.lower()) for opt in options):
                        return True, f"yes/no constraint violated: response does not start with any of {options}"
                else:
                    if not any(_ci_contains(text, opt) for opt in options):
                        return True, f"classification constraint violated: response does not contain any of {options}"


    is_json_response = False
    parsed_json = None
    stripped = text.strip()
    if stripped.startswith("```"):
        # strip code fences
        inner = stripped.split("```", 2)
        stripped = inner[1] if len(inner) > 1 else stripped
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip().rstrip("`").strip()
        
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed_json = json.loads(stripped)
            is_json_response = True
        except Exception:
            pass

    if expects_json and not is_json_response:
        return True, "JSON requested but response is not valid JSON"
        
    if is_json_response and user_prompt:
        expected_keys = extract_keys_from_prompt(user_prompt)
        if expected_keys:
            if not _json_contains_keys(parsed_json, expected_keys):
                return True, f"JSON response is missing requested keys/fields: {expected_keys}"
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
    user_prompt = _last_user_request(messages)
    fail, reason = heuristic_fail(response, expects_json=expects_json, user_prompt=user_prompt)
    if fail:
        return VerifyResult(escalate=True, reason=f"heuristic: {reason}")

    if m == "heuristic":
        return VerifyResult(escalate=False, reason="heuristic passed")

    # Stage 2: LLM grader (reuses user_prompt captured for stage 1)
    score = await llm_grade(router, response, user_prompt)
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
