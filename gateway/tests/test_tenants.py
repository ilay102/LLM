import pytest
import tenants

pytestmark = pytest.mark.unit


def test_create_and_lookup_tenant(tmp_path, monkeypatch):
    # Use a unique tenant_id per test to avoid collisions
    tid = f"acme-{tmp_path.name}"
    key = tenants.create_tenant(tid, name="Acme Inc", monthly_budget_usd=500)
    assert key.startswith("viren_")
    t = tenants.lookup_by_key(key)
    assert t is not None
    assert t.id == tid
    assert t.name == "Acme Inc"
    assert t.monthly_budget_usd == 500


def test_invalid_key_returns_none(tmp_path):
    assert tenants.lookup_by_key("viren_does-not-exist") is None
    assert tenants.lookup_by_key("") is None


def test_revoke_key_invalidates(tmp_path):
    tid = f"globex-{tmp_path.name}"
    key = tenants.create_tenant(tid, name="Globex")
    assert tenants.lookup_by_key(key) is not None
    assert tenants.revoke_key(key) is True
    assert tenants.lookup_by_key(key) is None


def test_usage_increments(tmp_path):
    tid = f"foo-{tmp_path.name}"
    key = tenants.create_tenant(tid, name="Foo")
    tenants.record_usage(tid, 0.10)
    tenants.record_usage(tid, 0.25)
    u = tenants.get_usage(tid)
    assert u["calls"] == 2
    assert abs(u["cost_usd"] - 0.35) < 1e-9


def test_over_budget_detection(tmp_path):
    tid = f"bar-{tmp_path.name}"
    key = tenants.create_tenant(tid, name="Bar", monthly_budget_usd=1.0)
    t = tenants.lookup_by_key(key)
    over, spent, cap = tenants.over_budget(t)
    assert over is False  # nothing spent yet
    tenants.record_usage(tid, 1.5)
    over, spent, cap = tenants.over_budget(t)
    assert over is True
    assert cap == 1.0
