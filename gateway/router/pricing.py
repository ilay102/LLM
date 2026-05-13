"""
Cost computation. We don't trust the SDK's reported $; we compute server-side
using the prices declared in litellm_config.yaml's model_info section.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CostBreakdown:
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int  # tokens served from provider-native prompt cache
    input_cost: float
    output_cost: float
    total_cost: float


def compute_cost(
    response: dict,
    input_cost_per_token: float,
    output_cost_per_token: float,
    cached_input_discount: float = 0.10,  # Anthropic prompt-cache reads are ~10% of base
) -> CostBreakdown:
    usage = response.get("usage") or {}
    in_t = usage.get("prompt_tokens", 0) or 0
    out_t = usage.get("completion_tokens", 0) or 0
    # Anthropic exposes cache_read_input_tokens via litellm
    cached = usage.get("cache_read_input_tokens", 0) or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0

    fresh_in = max(in_t - cached, 0)
    in_cost = fresh_in * input_cost_per_token + cached * input_cost_per_token * cached_input_discount
    out_cost = out_t * output_cost_per_token

    return CostBreakdown(
        model=response.get("model", "unknown"),
        input_tokens=in_t,
        output_tokens=out_t,
        cached_input_tokens=cached,
        input_cost=in_cost,
        output_cost=out_cost,
        total_cost=in_cost + out_cost,
    )
