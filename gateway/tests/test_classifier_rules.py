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


def test_multi_codeblock_with_large_output_goes_balanced():
    text = "```python\nprint(1)\n```\nAnd also:\n```sql\nSELECT 1;\n```"
    d = rule_decision(msg(text), requested_max_tokens=2000)
    assert d is not None
    assert d.tier == "balanced"
