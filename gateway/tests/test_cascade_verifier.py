import sys
from unittest.mock import MagicMock

# litellm is not installed in the lightweight CI environment; stub it before
# importing main so only the pure looks_low_quality function is exercised.
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()

import pytest
from main import looks_low_quality

pytestmark = pytest.mark.unit


def make(text="OK", finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


def test_normal_response_passes():
    assert looks_low_quality(make("This is a complete and helpful answer.")) is False


def test_truncated_response_triggers_cascade():
    assert looks_low_quality(make("Partial answ", finish="length")) is True


def test_empty_response_triggers_cascade():
    assert looks_low_quality(make("")) is True


def test_refusal_pattern_triggers_cascade():
    assert looks_low_quality(make("I cannot help")) is True


def test_invalid_json_when_requested_triggers_cascade():
    bad = make("This is not JSON at all.")
    assert looks_low_quality(bad, expects_json=True) is True


def test_valid_json_when_requested_passes():
    good = make('{"name": "Alice", "age": 30}')
    assert looks_low_quality(good, expects_json=True) is False


def test_json_in_fences_handled():
    good = make('```json\n{"ok": true}\n```')
    assert looks_low_quality(good, expects_json=True) is False
