import pytest
import metrics

pytestmark = pytest.mark.unit


def test_enabled_returns_bool():
    assert isinstance(metrics.enabled(), bool)


def test_render_returns_body_and_content_type():
    body, ctype = metrics.render()
    assert isinstance(body, (bytes, bytearray))
    assert isinstance(ctype, str) and ctype


def test_record_request_never_raises():
    # Must be safe whether prometheus_client is installed or not.
    metrics.record_request(
        tier="cheap", cache_hit=None, cascaded=False,
        cost_usd=0.001, baseline_cost_usd=0.005, latency_ms=420,
        pii_entities=[{"entity_type": "EMAIL_ADDRESS", "count": 1}],
    )
    metrics.record_request(
        tier="balanced", cache_hit="semantic", cascaded=True,
        cost_usd=0.0, baseline_cost_usd=0.0, latency_ms=0, pii_entities=None,
    )


def test_record_error_never_raises():
    metrics.record_error("upstream_5xx")


def test_metrics_appear_when_enabled():
    if not metrics.enabled():
        pytest.skip("prometheus_client not installed")
    metrics.record_request(tier="frontier", cache_hit=None, cascaded=False,
                           cost_usd=0.01, baseline_cost_usd=0.05,
                           latency_ms=1200, pii_entities=None)
    body, _ = metrics.render()
    text = body.decode()
    assert "viren_requests_total" in text
    assert "viren_cost_usd_total" in text
