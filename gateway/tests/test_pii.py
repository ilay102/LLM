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


def test_redact_messages_handles_structured_content():
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "Email me at carol@example.com"},
        {"type": "image_url", "image_url": "http://x"},
    ]}]
    out, ents = pii.redact_messages(msgs)
    assert "carol@example.com" not in out[0]["content"][0]["text"]
    # Non-text block preserved
    assert out[0]["content"][1] == {"type": "image_url", "image_url": "http://x"}
