import pytest
import persistence
import time

pytestmark = pytest.mark.unit


def test_record_and_summarize_empty(tmp_path):
    s = persistence.summarize(tenant_id=f"empty-{tmp_path.name}")
    assert s["n_calls"] == 0
    assert s["total_cost_usd"] == 0


def test_records_and_aggregates(tmp_path):
    tid = f"acme-{tmp_path.name}"
    persistence.record({
        "ts": time.time(), "tenant": tid, "tier": "cheap",
        "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001,
        "baseline_cost_usd": 0.005, "model_returned": "haiku",
    })
    persistence.record({
        "ts": time.time(), "tenant": tid, "tier": "balanced",
        "input_tokens": 200, "output_tokens": 100, "cost_usd": 0.003,
        "baseline_cost_usd": 0.003, "model_returned": "sonnet",
        "cache_hit": "semantic",
    })
    s = persistence.summarize(tenant_id=tid)
    assert s["n_calls"] == 2
    assert s["total_cost_usd"] == pytest.approx(0.004)
    assert s["total_baseline_usd"] == pytest.approx(0.008)
    assert s["savings_usd"] == pytest.approx(0.004)
    assert s["cache_hits"] == 1
    assert s["tier_distribution"] == {"cheap": 1, "balanced": 1}
