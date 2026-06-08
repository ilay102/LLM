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


def test_literal_preservation_is_case_insensitive():
    """Regression: previously prompt 'john@x.com' vs response 'JOHN@X.COM'
    triggered a false 'literal email missing' escalation because the set
    intersection compared the strings case-sensitively. The address is the
    same — only normalisation differs. Fix: lowercase both sides."""
    prompt = "Extract the contact email from: 'reach out to john@x.com please.'"
    response = "**Email:** JOHN@X.COM"
    fail, reason = verifier.heuristic_fail(resp(response), user_prompt=prompt)
    assert not fail, f"case-normalised email match should pass; got escalation: {reason}"


def test_literal_preservation_url_case_insensitive():
    prompt = "Open this link: https://Example.COM/path?"
    response = "Sure — opening https://example.com/path now."
    fail, _ = verifier.heuristic_fail(resp(response), user_prompt=prompt)
    assert not fail


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


# ---- New Formatting & Quality Constraint Heuristics -----------------------

def test_heuristic_yes_no_constraint():
    prompt = "Is Postgres relational? Yes or no."
    
    # Valid answers starting with yes/no (possibly formatted)
    for valid in ("Yes.", "no, it is not.", "**Yes**, it is.", "[Yes] it is"):
        fail, reason = verifier.heuristic_fail(resp(valid), user_prompt=prompt)
        assert not fail, f"should pass valid yes/no: {valid}"

    # Invalid answers
    for invalid in ("Postgres is relational.", "I am not sure.", "It depends."):
        fail, reason = verifier.heuristic_fail(resp(invalid), user_prompt=prompt)
        assert fail, f"should fail invalid yes/no: {invalid}"
        assert "yes/no requested" in reason


def test_heuristic_one_word_constraint():
    prompt = "Give the sentiment in one word: 'good'"
    
    # Valid short answers
    for valid in ("Positive", "negative", "**neutral**."):
        fail, reason = verifier.heuristic_fail(resp(valid), user_prompt=prompt)
        assert not fail, f"should pass one-word: {valid}"

    # Invalid long answers
    fail, reason = verifier.heuristic_fail(resp("The sentiment of the review is positive."), user_prompt=prompt)
    assert fail
    assert "one-word answer requested" in reason


def test_heuristic_options_classification():
    prompt = "Classify intent as: CHURN / SUPPORT / BILLING / OTHER."
    
    # Contains one of the choices
    fail, _ = verifier.heuristic_fail(resp("This is for SUPPORT."), user_prompt=prompt)
    assert not fail
    
    # Missing all choices
    fail, reason = verifier.heuristic_fail(resp("Please help me reset my password."), user_prompt=prompt)
    assert fail
    assert "classification constraint violated" in reason


def test_heuristic_options_classification_quotes():
    prompt = "Tag sentiment as 'happy', 'frustrated', or 'neutral': 'broken'"
    
    # Contains one of the choices
    fail, _ = verifier.heuristic_fail(resp("The tag is frustrated."), user_prompt=prompt)
    assert not fail
    
    # Missing choices
    fail, reason = verifier.heuristic_fail(resp("Customer had a bad experience."), user_prompt=prompt)
    assert fail
    assert "classification constraint violated" in reason


def test_heuristic_options_classification_ignored_on_translations():
    """Translations contain options like 'or' or '/' in terms, but translated words
    differ from the prompt. We should ignore options checks on translations."""
    prompt = "Translate to French: 'personal or business'"
    
    # Response is French, doesn't contain English 'personal' or 'business'
    fail, _ = verifier.heuristic_fail(resp("personnel ou professionnel"), user_prompt=prompt)
    assert not fail


def test_heuristic_new_literals_preservation():
    # URL
    url_prompt = "Click here: https://example.com/verify"
    fail, reason = verifier.heuristic_fail(resp("Go to the login page."), user_prompt=url_prompt)
    assert fail and "url" in reason

    # Version
    version_prompt = "Upgraded to 3.14.2"
    fail, reason = verifier.heuristic_fail(resp("Upgraded successfully to the latest version."), user_prompt=version_prompt)
    assert fail and "version" in reason

    # SKU
    sku_prompt = "Extract SKU-A7-2231"
    fail, reason = verifier.heuristic_fail(resp("Extracted SKU code."), user_prompt=sku_prompt)
    assert fail and "sku" in reason


def test_extract_options_from_prompt_logic():
    assert verifier.extract_options_from_prompt("Classify intent as: CHURN / SUPPORT / BILLING / OTHER.") == ["CHURN", "SUPPORT", "BILLING", "OTHER"]
    assert verifier.extract_options_from_prompt("Tag sentiment as 'happy', 'frustrated', or 'neutral'.") == ["happy", "frustrated", "neutral"]
    assert verifier.extract_options_from_prompt("Is Stripe a payment provider, CRM, or hosting service?") == ["CRM", "hosting service"]
    assert verifier.extract_options_from_prompt("Should this be auto-routed to BILLING or TECHNICAL?") == ["BILLING", "TECHNICAL"]
    assert verifier.extract_options_from_prompt("personal or business") == ["personal", "business"]


def test_extract_keys_from_prompt_logic():
    assert verifier.extract_keys_from_prompt("Generate a JSON product card with fields: name, price, sku, in_stock, tags.") == ["name", "price", "sku", "in_stock", "tags"]
    assert verifier.extract_keys_from_prompt("Parse this support ticket into a JSON object with priority, category, customer_tier, summary.") == ["priority", "category", "customer_tier", "summary"]
    assert verifier.extract_keys_from_prompt("Generate JSON (name, version, license, key_dependencies).") == ["name", "version", "license", "key_dependencies"]
    assert verifier.extract_keys_from_prompt("Return a JSON object with keys 'status' and 'timestamp'.") == ["status", "timestamp"]
    assert verifier.extract_keys_from_prompt("personal or business") == []  # Not a JSON prompt


def test_heuristic_json_keys_validation():
    prompt = "Generate JSON with fields: name, price, sku"
    
    # Valid JSON with all fields
    good_json = '{"name": "Mug", "price": 9.99, "sku": "MUG-123"}'
    fail, _ = verifier.heuristic_fail(resp(good_json), user_prompt=prompt)
    assert not fail
    
    # Missing field
    bad_json = '{"name": "Mug", "price": 9.99}'
    fail, reason = verifier.heuristic_fail(resp(bad_json), user_prompt=prompt)
    assert fail
    assert "missing requested keys/fields" in reason


def test_json_contains_keys_nested():
    data = {"items": [{"name": "Mug", "price": 9.99}]}
    assert verifier._json_contains_keys(data, ["name", "price"])
    assert not verifier._json_contains_keys(data, ["name", "sku"])


def test_heuristic_accepts_short_yes_no_answers():
    """Pin: 'yes' and 'no' are valid answers to yes/no prompts and must NOT
    be rejected as 'empty or near-empty'."""
    for answer, prompt in [
        ("yes", "Is Lisbon the capital of Portugal? Answer yes or no."),
        ("no", "Is the Eiffel Tower in Berlin? Yes or no."),
        ("Yes.", "Is PostgreSQL open source? Yes or no."),
        ("No", "Does Kubernetes require Docker? Yes or no."),
    ]:
        fail, reason = verifier.heuristic_fail(resp(answer), user_prompt=prompt)
        assert not fail, (
            f"Short answer '{answer}' should pass for yes/no prompt, "
            f"but got fail=True reason='{reason}'"
        )


def test_heuristic_accepts_short_factual_answers():
    """Pin: short factual answers like '600', '1st', '3' should not be
    rejected as empty."""
    for answer in ["600", "1st", "3", "no"]:
        fail, reason = verifier.heuristic_fail(resp(answer))
        assert not fail, (
            f"Short factual answer '{answer}' should pass, "
            f"but got fail=True reason='{reason}'"
        )


def test_heuristic_still_rejects_truly_empty():
    """Sanity: truly empty and whitespace-only responses must still fail."""
    for empty in ["", "   ", "\n\t"]:
        fail, _ = verifier.heuristic_fail(resp(empty))
        assert fail, f"Empty response '{empty!r}' should be rejected"


