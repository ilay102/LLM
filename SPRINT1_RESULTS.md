# Sprint 1 Verification Results

## Classifier
- Accuracy: 72.5%
- Per class: {'cheap': 0.75, 'balanced': 0.625, 'frontier': 0.875}

## Self-test
```

▸ 1/6  Gateway health
  ✓ /health returns ok=true
  ✓ trained classifier weights loaded
  ✓ PII redaction active

▸ 2/6  Auth
  ✓ /v1/models with master key -> 200
  ✓ /v1/models with bogus key -> 401

▸ 3/6  Sample call routes correctly
  ✓ simple classification routed to cheap tier (gpt-4o-mini-2024-07-18)

▸ 4/6  Cache fires on repeat
  ✓ second call returned cached id: cached-8879e18577b0

▸ 5/6  PII redaction works end-to-end
  ✓ call with PII content returned 200 (check gateway logs for 'pii=N')

▸ 6/6  Unit tests
..........................
```

## Pytest
```
h PASSED                     [ 64%]
tests/test_pii.py::test_redact_messages_preserves_structure PASSED       [ 67%]
tests/test_pii.py::test_redact_messages_handles_structured_content PASSED [ 70%]
tests/test_pricing.py::test_no_usage_returns_no_cost PASSED              [ 74%]
tests/test_pricing.py::test_simple_in_and_out PASSED                     [ 77%]
tests/test_pricing.py::test_cached_tokens_apply_discount PASSED          [ 80%]
tests/test_pricing.py::test_cached_exceeds_total_clamped PASSED          [ 83%]
tests/test_tenants.py::test_create_and_lookup_tenant PASSED              [ 87%]
tests/test_tenants.py::test_invalid_key_returns_none PASSED              [ 90%]
tests/test_tenants.py::test_revoke_key_invalidates PASSED                [ 93%]
tests/test_tenants.py::test_usage_increments PASSED                      [ 96%]
tests/test_tenants.py::test_over_budget_detection PASSED                 [100%]

=============================== warnings summary ===============================
../../../home/vscode/.local/lib/python3.11/site-packages/litellm/proxy/_types.py:1422
  /home/vscode/.local/lib/python3.11/site-packages/litellm/proxy/_types.py:1422: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class UserAPIKeyAuth(

../../../home/vscode/.local/lib/python3.11/site-packages/litellm/utils.py:134
  /home/vscode/.local/lib/python3.11/site-packages/litellm/utils.py:134: DeprecationWarning: open_text is deprecated. Use files() instead. Refer to https://importlib-resources.readthedocs.io/en/latest/using.html#migrating-from-legacy for migration advice.
    with resources.open_text("litellm.llms.tokenizers", "anthropic_tokenizer.json") as f:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 31 passed, 2 warnings in 10.71s ========================

```

## Eval
```
] gw=$0.00002 baseline=$0.00178 tier=gpt-4o-mini-2024-07-
  [10/30] gw=$0.00027 baseline=$0.00026 tier=claude-haiku-4-5-202
  [11/30] gw=$0.00000 baseline=$0.00015 tier=gpt-4o-mini-2024-07-
  [12/30] gw=$0.00033 baseline=$0.00044 tier=claude-haiku-4-5-202
  [13/30] gw=$0.00002 baseline=$0.00358 tier=gpt-4o-mini-2024-07-
  [14/30] gw=$0.00000 baseline=$0.00089 tier=?
  [15/30] gw=$0.00002 baseline=$0.00276 tier=gpt-4o-mini-2024-07-
  [16/30] gw=$0.00028 baseline=$0.00057 tier=claude-haiku-4-5-202
  [17/30] gw=$0.00029 baseline=$0.00242 tier=claude-haiku-4-5-202
  [18/30] gw=$0.00001 baseline=$0.00154 tier=gpt-4o-mini-2024-07-
  [19/30] gw=$0.00013 baseline=$0.00059 tier=claude-haiku-4-5-202
  [20/30] gw=$0.00055 baseline=$0.00486 tier=claude-haiku-4-5-202
  [21/30] gw=$0.00012 baseline=$0.00142 tier=claude-haiku-4-5-202
  [22/30] gw=$0.00020 baseline=$0.00036 tier=claude-haiku-4-5-202
  [23/30] gw=$0.00028 baseline=$0.00285 tier=claude-haiku-4-5-202
  [24/30] gw=$0.00002 baseline=$0.00195 tier=gpt-4o-mini-2024-07-
  [25/30] gw=$0.00011 baseline=$0.00051 tier=claude-haiku-4-5-202
  [26/30] gw=$0.00003 baseline=$0.00179 tier=gpt-4o-mini-2024-07-
  [27/30] gw=$0.00021 baseline=$0.00115 tier=claude-haiku-4-5-202
  [28/30] gw=$0.00011 baseline=$0.00055 tier=claude-haiku-4-5-202
  [29/30] gw=$0.00035 baseline=$0.00211 tier=claude-haiku-4-5-202
  [30/30] gw=$0.00001 baseline=$0.00300 tier=gpt-4o-mini-2024-07-

==========================================
VIREN — Verified Savings on 30 prompts
==========================================
Total cost (gateway):    $0.0043
Total cost (baseline):   $0.0410
Savings:                 $0.0367  (89.5%)
Cache hits:              0
Latency (gw p50/p95):    1310ms / 22048ms
Latency (bl p50/p95):    2611ms / 5722ms

Routing distribution:
  claude-haiku-4-5-20251001         17  ( 56.7%)
  gpt-4o-mini-2024-07-18            12  ( 40.0%)
  err                                1  (  3.3%)


Report written to /workspaces/LLM/scripts/eval_report.html

```
