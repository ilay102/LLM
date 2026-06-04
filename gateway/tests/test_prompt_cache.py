import pytest
import prompt_cache as pc

pytestmark = pytest.mark.unit

BIG = "You are a helpful assistant. " * 400   # ~11k chars > 2048-token min
SMALL = "You are helpful."


def test_provider_detection():
    assert pc.provider_of("anthropic/claude-sonnet-4-6") == "anthropic"
    assert pc.provider_of("claude-haiku-4-5") == "anthropic"
    assert pc.provider_of("deepseek/deepseek-v4-pro") == "deepseek"
    assert pc.provider_of("openai/gpt-4o-mini") == "openai"
    assert pc.provider_of("gpt-4o") == "openai"
    assert pc.provider_of("mistral-large") == "other"


def test_non_anthropic_unchanged():
    msgs = [{"role": "system", "content": BIG}, {"role": "user", "content": "hi"}]
    assert pc.inject_cache_breakpoints(msgs, "deepseek") == msgs
    assert pc.inject_cache_breakpoints(msgs, "openai") == msgs


def test_already_has_cache_control_unchanged():
    msgs = [{"role": "system", "content": [
        {"type": "text", "text": BIG, "cache_control": {"type": "ephemeral"}}]},
        {"role": "user", "content": "hi"}]
    assert pc.inject_cache_breakpoints(msgs, "anthropic") == msgs


def test_small_prefix_no_breakpoint():
    msgs = [{"role": "system", "content": SMALL}, {"role": "user", "content": "hi"}]
    out = pc.inject_cache_breakpoints(msgs, "anthropic")
    # below the token minimum -> unchanged (string stays a string)
    assert out[0]["content"] == SMALL


def test_big_prefix_gets_breakpoint():
    msgs = [{"role": "system", "content": BIG}, {"role": "user", "content": "what's up"}]
    out = pc.inject_cache_breakpoints(msgs, "anthropic")
    sys_content = out[0]["content"]
    assert isinstance(sys_content, list)
    assert sys_content[-1].get("cache_control") == {"type": "ephemeral"}
    # the volatile user turn is untouched
    assert out[1]["content"] == "what's up"


def test_breakpoint_lands_before_final_user_turn():
    # system + a few-shot user/assistant pair + final user turn
    msgs = [
        {"role": "system", "content": BIG},
        {"role": "user", "content": "example q"},
        {"role": "assistant", "content": "example a"},
        {"role": "user", "content": "real question"},
    ]
    out = pc.inject_cache_breakpoints(msgs, "anthropic")
    # boundary = message before the last user turn = the assistant few-shot (idx 2)
    assert isinstance(out[2]["content"], list)
    assert out[2]["content"][-1].get("cache_control") == {"type": "ephemeral"}
    assert out[3]["content"] == "real question"


def test_empty_messages():
    assert pc.inject_cache_breakpoints([], "anthropic") == []


def test_stable_prefix_index():
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    # final user turn is index 3 -> prefix ends at 3
    assert pc.stable_prefix_index(msgs) == 3
