import pytest
import pii

pytestmark = pytest.mark.unit


def test_redacts_email():
    text = "Contact alice@example.com for support."
    out, ents = pii.redact(text)
    assert "alice@example.com" not in out
    assert any(e["entity_type"].upper().endswith("EMAIL") or e["entity_type"] == "EMAIL_ADDRESS"
               for e in ents)


def test_redacts_credit_card_fallback():
    text = "Card number 4532 1488 0343 6467 was charged."
    out, ents = pii.redact(text)
    assert "4532" not in out or "<CREDIT_CARD>" in out


def test_redacts_us_ssn():
    text = "SSN: 123-45-6789"
    out, ents = pii.redact(text)
    assert "123-45-6789" not in out


def test_redacts_api_keys():
    text = "Use sk-abc123def456ghi789jkl012mno345pqr678 for auth."
    out, ents = pii.redact(text)
    # The regex pattern catches sk- prefixes
    assert "sk-abc123def456ghi789jkl012mno345pqr678" not in out


def test_no_pii_passes_through():
    text = "The weather is nice today."
    out, ents = pii.redact(text)
    assert out == text
    assert ents == []


def test_redact_messages_preserves_structure():
    msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "My email is bob@example.com, please help."},
        {"role": "assistant", "content": "Sure, how can I help?"},
    ]
    out, ents = pii.redact_messages(msgs)
    assert len(out) == 3
    assert out[0]["role"] == "system"
    assert "bob@example.com" not in out[1]["content"]
    assert out[2]["content"] == "Sure, how can I help?"


def test_detect_does_not_mutate_text():
    """Regression: the live request path must not change the prompt.
    Bug: in v0.2.2 we redacted on the live path, so the model received
    `<EMAIL_ADDRESS>` and hallucinated a fake email back to the user."""
    text = "Send a confirmation to alice@example.com and call +1-415-555-0199."
    ents = pii.detect(text)
    types = {e["entity_type"] for e in ents}
    assert "EMAIL_ADDRESS" in types
    assert any("PHONE" in t for t in types)


def test_detect_messages_returns_entities_without_mutating():
    msgs = [
        {"role": "user", "content": "My email is bob@example.com, please reply."},
        {"role": "user", "content": [
            {"type": "text", "text": "Also call 415-555-0199."},
        ]},
    ]
    original_first = msgs[0]["content"]
    original_second = msgs[1]["content"][0]["text"]
    ents = pii.detect_messages(msgs)
    # Original messages untouched
    assert msgs[0]["content"] == original_first
    assert msgs[1]["content"][0]["text"] == original_second
    assert "bob@example.com" in msgs[0]["content"]
    # Entities aggregated
    type_counts = {e["entity_type"]: e["count"] for e in ents}
    assert type_counts.get("EMAIL_ADDRESS", 0) >= 1


def test_phone_regex_does_not_match_version_strings():
    """Regression: the old phone regex matched things like `1.2.345-6789`
    (version strings, invoice IDs), forcing the model to hallucinate phones."""
    for benign in [
        "Version 1.2.345-6789 released.",
        "Order 12345 shipped on 2026-06-08.",
        "The number is 42.",
        "ISBN 978-3-16-148410-0",
    ]:
        ents = pii.detect(benign)
        types = {e["entity_type"] for e in ents}
        assert not any("PHONE" in t for t in types), \
            f"phone regex over-matched on: {benign!r} -> {ents}"


def test_phone_regex_still_matches_real_phones():
    for real in [
        "Call me at 415-555-0199.",
        "My number: +1 415 555 0199",
        "Reach me on (415) 555-0199.",
    ]:
        ents = pii.detect(real)
        types = {e["entity_type"] for e in ents}
        assert any("PHONE" in t for t in types), \
            f"phone regex missed real phone in: {real!r}"


def test_redact_messages_handles_structured_content():
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "Email me at carol@example.com"},
        {"type": "image_url", "image_url": "http://x"},
    ]}]
    out, ents = pii.redact_messages(msgs)
    assert "carol@example.com" not in out[0]["content"][0]["text"]
    # Non-text block preserved
    assert out[0]["content"][1] == {"type": "image_url", "image_url": "http://x"}
