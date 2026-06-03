import pytest
from pricing import compute_cost

pytestmark = pytest.mark.unit


def make_resp(in_tok=0, out_tok=0, cached=0, model="x"):
    return {
        "model": model,
        "usage": {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "cache_read_input_tokens": cached,
        },
    }


def test_no_usage_returns_no_cost():
    # If response has no usage, caller wraps in `if response.get('usage')` — so
    # compute_cost is only called with usage present. But guard the math.
    r = make_resp(0, 0)
    c = compute_cost(r, input_cost_per_token=0.000003, output_cost_per_token=0.000015)
    assert c.total_cost == 0


def test_simple_in_and_out():
    r = make_resp(1000, 500)
    c = compute_cost(r, input_cost_per_token=0.000003, output_cost_per_token=0.000015)
    # 1000 * 3e-6 = 0.003; 500 * 15e-6 = 0.0075; total 0.0105
    assert c.input_cost == pytest.approx(0.003, rel=1e-9)
    assert c.output_cost == pytest.approx(0.0075, rel=1e-9)
    assert c.total_cost == pytest.approx(0.0105, rel=1e-9)


def test_cached_tokens_apply_discount():
    # 1000 input, 500 of them cached (90% discount = pay 10%)
    r = make_resp(1000, 0, cached=500)
    c = compute_cost(r, input_cost_per_token=0.000003, output_cost_per_token=0.000015,
                     cached_input_discount=0.10)
    # Fresh: 500 * 3e-6 = 0.0015
    # Cached: 500 * 3e-6 * 0.10 = 0.00015
    assert c.input_cost == pytest.approx(0.0015 + 0.00015)


def test_cached_exceeds_total_clamped():
    # Provider sometimes reports cached > prompt_tokens (edge case)
    r = make_resp(100, 0, cached=200)
    c = compute_cost(r, input_cost_per_token=0.000001, output_cost_per_token=0)
    # fresh = max(100 - 200, 0) = 0
    assert c.input_cost == pytest.approx(200 * 0.000001 * 0.10)
