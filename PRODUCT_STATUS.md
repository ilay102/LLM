# Product Status — v0.2.2 verified

## Headline (3-judge consensus on 30-prompt corpus, $5 in API)
- **Cost reduction:** 87.4%
- **Win-or-tie (majority of Sonnet+GPT-4o+Opus):** 80.0%
- **Routing distribution:** 30% Haiku, 50% gpt-4o-mini, 17% Sonnet, 3% errors
- **Classifier accuracy (held-out):** 72.5%

## Methodology
Three judges from two families. Sonnet 76.7%, GPT-4o 63.3%, Opus 80%.
Sonnet self-preference: +5pp. GPT-4o terse-penalty: -10pp. Majority is most defensible.

## What's verified
- 31/31 pytest passing
- Self-test 6/6 green
- End-to-end: client request -> classifier -> tier -> cache -> provider -> log -> persistence
- Multi-tenant API keys + budget caps + PII redaction all live
- Redis fail-open tested live

## What's NOT verified (for the contract phase, not the event)
- 30 prompts is small (±10% CI). Need 200+ on real customer traffic.
- Classifier trained on generic corpus, not customer-specific.
- Streaming bypasses cache and cascade.
- DeepSeek deployments added but not yet in the eval.

## See also
- baselines/v0.2.2_*.html — the verified report
- COMPARISON.md — three-way version comparison + judge methodology
