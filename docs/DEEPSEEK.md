# DeepSeek Integration — V4 Re-Tier

## What we tested and why we re-architected

### First attempt (v0.2.3): DeepSeek V4-Flash in cheap tier
**Result:** savings dropped from 87.4% → 64.7%. V4-Flash gave verbose answers
on simple classification/extraction prompts. Got picked 36.7% of the time but
generated 5-10x more tokens than Haiku/4o-mini, eating the per-token cost
advantage.

**Lesson:** V4-Flash is smarter than Haiku — but cheap-tier tasks don't reward
"smarter," they reward "terser." Wrong fit.

### Re-tier (v0.2.4): V4-Pro to BALANCED, R1 to FRONTIER, drop V4-Flash
The V4-Pro placement is the real bet — at $0.435/$0.87 per 1M tokens, it's
**7x cheaper than Sonnet** and the docs claim Sonnet-grade quality on technical
tasks. If true, balanced-tier cost drops 70-85% with no quality loss.

## Current tier configuration

| Tier | Models (LiteLLM rotates) | $/1M tokens | When picked |
|---|---|---|---|
| Cheap | Haiku 4.5, gpt-4o-mini | $0.15-$4.00 | Classification, short extraction, single-fact Q&A |
| Balanced | Sonnet 4.6, **DeepSeek V4-Pro** | $0.435-$15.00 | Summarization, code, structured output |
| Frontier | Opus 4.7, **DeepSeek R1** | $0.435-$75.00 | Reasoning, architecture, multi-step planning |

## Pricing context (per 1M tokens)

| Model | Input | Output | vs. Sonnet |
|---|---|---|---|
| gpt-4o-mini | $0.15 | $0.60 | 20-25x cheaper |
| DeepSeek V4-Flash | $0.14 | $0.28 | 20-50x cheaper (but verbose) |
| Haiku 4.5 | $0.80 | $4.00 | 4x cheaper |
| **DeepSeek V4-Pro** | **$0.435** | **$0.87** | **7-17x cheaper** |
| DeepSeek R1 | $0.435 | $0.87 | Same as V4-Pro |
| Sonnet 4.6 | $3.00 | $15.00 | baseline |
| Opus 4.7 | $15.00 | $75.00 | 5x more |

V4-Pro at balanced-tier prices is the most asymmetric bet in the lineup.

## max_tokens caps (defensive)

To prevent verbosity blowups (the V4-Flash failure mode), we cap output:
- Cheap tier: 500 tokens
- Balanced tier: 1500 tokens
- Frontier tier: 3000 tokens

Clients can override per-request. The defaults match typical SaaS workloads.

## The China-hosting trade-off

DeepSeek inference runs in China. For sensitive verticals — healthcare,
financial services (PCI), EU GDPR-strict — exclude `deepseek/*` via the
per-tenant `allowed_models` field:

```bash
curl -X PATCH http://localhost:8000/admin/tenants/healthcare-co \
  -H "Authorization: Bearer $MASTER" \
  -d '{"allowed_models_json": "[\"openai/*\", \"anthropic/*\"]"}'
```

Gateway then uses only OpenAI + Anthropic for that tenant.

## Honest sales positioning

DO:
- "V4-Pro is the real win — Sonnet-grade quality for ~14% of the cost on technical workloads."
- "We tested V4-Flash on cheap-tier; it was verbose and lost savings. Our data caught it before customers did."
- "R1 hasn't been stress-tested yet — needs a reasoning-heavy corpus."

DON'T:
- Pretend V4 is a universal cost win — wrong tier placement kills it
- Push DeepSeek on regulated buyers without compliance review
- Hide the China-hosting fact during security questionnaires

## Setup

1. https://platform.deepseek.com → API Keys → create one
2. Load $5 credit
3. Add to Codespace secrets / `.env`:
   ```
   DEEPSEEK_API_KEY=sk-...
   ```
4. Restart gateway. V4-Pro will activate in balanced tier and R1 in frontier.

If `DEEPSEEK_API_KEY` is empty, LiteLLM marks those deployments unavailable
and falls back to Anthropic/OpenAI only. Gateway stays functional.

## Re-eval after re-tier

```bash
docker compose -f gateway/docker-compose.yml exec redis redis-cli FLUSHDB
docker compose -f gateway/docker-compose.yml restart gateway
sleep 30

GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY=$GATEWAY_MASTER_KEY \
  ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  python3 scripts/eval_corpus.py --limit 30 2>&1 | tee scripts/eval_v0.2.4.log

ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY OPENAI_API_KEY=$OPENAI_API_KEY \
  python3 scripts/judge_ensemble.py 2>&1 | tee scripts/judge_v0.2.4.log
```

Expected: savings rebound to **80-90%** (V4-Pro replaces some Sonnet calls),
W-T holds at 78-82% or improves (V4-Pro quality close to Sonnet on technical
work). If V4-Pro still verbose, raise max_tokens cap to 1000 in cheap tier
and 2000 in balanced.
