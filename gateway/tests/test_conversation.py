import pytest
import conversation as conv

pytestmark = pytest.mark.unit


class FakeRedis:
    def __init__(self):
        self.store = {}
    def get(self, k):
        return self.store.get(k)
    def setex(self, k, ttl, v):
        self.store[k] = v
    def expire(self, k, ttl):
        return True
    def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(conv, "_redis", fr)
    monkeypatch.setattr(conv, "_redis_tried", True)
    return fr


def test_conversation_id_from_header_is_stable():
    a = conv.conversation_id("sess-123", [])
    b = conv.conversation_id("sess-123", [{"role": "user", "content": "x"}])
    assert a == b  # header wins, independent of messages


def test_conversation_id_from_messages_is_stable():
    msgs1 = [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}]
    msgs2 = [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"},
             {"role": "assistant", "content": "later turn"}]
    # same first 2 messages -> same id across turns
    assert conv.conversation_id(None, msgs1) == conv.conversation_id(None, msgs2)


def test_stickiness_floors_up(fake_redis):
    cid = conv.conversation_id("s1", [])
    # First turn escalates to frontier
    eff, reason = conv.apply_stickiness("frontier", cid)
    assert eff == "frontier"
    # Next turn classified cheap -> should be floored back up to frontier
    eff2, reason2 = conv.apply_stickiness("cheap", cid)
    assert eff2 == "frontier"
    assert reason2 and "stickiness" in reason2


def test_stickiness_never_routes_down(fake_redis):
    cid = conv.conversation_id("s2", [])
    conv.apply_stickiness("cheap", cid)
    # escalation is allowed (routes up)
    eff, _ = conv.apply_stickiness("balanced", cid)
    assert eff == "balanced"
    # and then it sticks
    eff2, _ = conv.apply_stickiness("cheap", cid)
    assert eff2 == "balanced"


def test_fail_open_without_redis(monkeypatch):
    # No redis -> stickiness is a no-op, returns tier unchanged, never raises
    monkeypatch.setattr(conv, "_redis", None)
    monkeypatch.setattr(conv, "_redis_tried", True)
    eff, reason = conv.apply_stickiness("cheap", "conv:abc")
    assert eff == "cheap"
    assert reason is None


def test_estimate_input_chars():
    msgs = [{"role": "system", "content": "abc"},
            {"role": "user", "content": "defg"}]
    assert conv.estimate_input_chars(msgs) == 7
    # multimodal blocks
    msgs2 = [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    assert conv.estimate_input_chars(msgs2) == 5
