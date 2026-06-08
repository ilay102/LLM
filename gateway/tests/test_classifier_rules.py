import pytest
from classifier import rule_decision

pytestmark = pytest.mark.unit


def msg(text):
    return [{"role": "user", "content": text}]


def test_reasoning_keywords_go_frontier():
    d = rule_decision(msg("Prove that 1+1=2 step by step."), None)
    assert d is not None
    assert d.tier == "frontier"


def test_simple_short_classification_goes_cheap():
    d = rule_decision(msg("Classify this sentiment: 'great product'"), None)
    assert d is not None
    assert d.tier == "cheap"


def test_very_short_no_signal_goes_cheap():
    d = rule_decision(msg("What is 2+2?"), None)
    assert d is not None
    assert d.tier == "cheap"


def test_medium_unmatched_returns_none():
    """Medium-length, no keywords -> rule layer abstains, learned layer decides."""
    text = "Please write a paragraph about the history of ancient Mesopotamia and the development of writing systems including cuneiform and how it influenced administrative practices in early civilizations through the second millennium BCE which is a topic of significant historical interest."
    d = rule_decision(msg(text), None)
    assert d is None


def test_non_text_content_goes_balanced():
    d = rule_decision([{"role": "user", "content": [{"type": "image_url", "url": "..."}]}], None)
    assert d is not None
    assert d.tier == "balanced"


def test_translation_of_long_phrase_goes_balanced():
    """Pin: TRANSLATION_PATTERN with content > 25 chars -> balanced.
    Eval id 25 ('Translate to Italian: ...') depends on this upgrade
    so the cheap tier doesn't butcher fluency."""
    d = rule_decision(msg("Translate to Italian: 'Forgot password? Reset it here.'"), None)
    assert d is not None
    assert d.tier == "balanced", f"translation should upgrade to balanced, got {d.tier} ({d.reason})"


def test_translation_of_short_phrase_stays_cheap():
    """Pin: short translations don't waste the balanced tier."""
    d = rule_decision(msg("Translate to French: 'Save'"), None)
    # Either matches SIMPLE_KEYWORDS (translate) -> cheap, or no rule -> None.
    # Both outcomes are acceptable. What we forbid is balanced/frontier.
    assert d is None or d.tier == "cheap"


def test_extract_short_goes_cheap_after_pii_fix():
    """Pin: short extraction prompts (id 12, 14, 15, 17, 18) should hit cheap.
    They lost in pre-v0.2.3 evals due to PII corruption, NOT routing.
    With the PII fix landed, cheap is the right tier for these — they're
    one-line extractions where Sonnet would be overkill."""
    for short_extract in [
        "Extract email and phone from: 'Reach me at sarah.k@example.org or 555-0142.'",
        "Extract product SKU from: 'Order shipped: SKU-A7-2231 (qty 3).'",
        "Find all person names in: 'Alice and Bob met with Carlos to discuss the proposal.'",
        "Pull the version number from: 'Upgraded to v3.14.2 last Tuesday.'",
        "Get the IP address from: 'Login attempt from 192.168.1.55 at 03:42 UTC.'",
    ]:
        d = rule_decision(msg(short_extract), None)
        # Short + EXTRACTION/SIMPLE keyword should route to cheap.
        # If a future change wants to send these to balanced, it must
        # justify the cost vs. quality trade explicitly.
        assert d is not None, f"rule layer abstained on short extraction: {short_extract!r}"
        assert d.tier == "cheap", (
            f"short extraction should stay cheap (post-PII-fix); got {d.tier} "
            f"on {short_extract!r} reason={d.reason}"
        )


def test_multi_field_json_extraction_goes_balanced():
    """Pin: JSON_MULTIFIELD with 3+ fields -> balanced for precision."""
    d = rule_decision(msg(
        "Convert this into a JSON object with fields name, email, phone, "
        "address, role for the contact: ..."
    ), None)
    assert d is not None
    assert d.tier == "balanced"


def test_multi_codeblock_with_large_output_goes_balanced():
    text = "```python\nprint(1)\n```\nAnd also:\n```sql\nSELECT 1;\n```"
    d = rule_decision(msg(text), requested_max_tokens=2000)
    assert d is not None
    assert d.tier == "balanced"
