# DeepSeek Integration

## Why we added it

DeepSeek released two models that materially change the cost/quality curve:

- **DeepSeek V3 (`deepseek-chat`)** — $0.27/$1.10 per 1M tokens.
  Cheaper than Anthropic Haiku ($0.80/$4.00) and OpenAI gpt-4o-mini ($0.15/$0.60)
  on output cost, with quality comparable to Sonnet on code, math, and
  structured-output tasks.

- **DeepSeek R1 (`deepseek-reasoner`)** — $0.55/$2.19 per 1M tokens.
  A dedicated reasoning model. Benchmarks competitive with o1 / Opus on math
  and complex code at ~4% of the price.

Net effect on a typical SaaS pilot:
- Cheap-tier $/call drops ~30-50%
- Frontier-tier $/call drops 90-95%

## How it fits the gateway

DeepSeek deployments live in `gateway/litellm_config.yaml`:

- `tier-cheap`: includes both gpt-4o-mini, Haiku, AND DeepSeek V3.
  LiteLLM rotates between them; you can weight via routing strategy.
- `tier-balanced`: includes Sonnet and DeepSeek V3. DeepSeek wins on code-heavy
  prompts at ~1/10 the cost.
- `tier-frontier`: DeepSeek R1 listed FIRST (default for cost-sensitive
  tenants), Opus retained as the high-quality fallback for tenants who
  explicitly want it.

## The honest trade-off — China hosting

DeepSeek inference runs in China. For most B2B SaaS this is fine. For some,
it is not:

| Vertical | DeepSeek OK? | Why |
|---|---|---|
| AI customer support (US/EU SMB) | ✅ | Low PII; common pattern |
| AI dev tools, copilots | ✅ | Code is rarely PII |
| AI marketing/content | ✅ | Public-facing content |
| Healthcare (HIPAA) | ❌ | PHI cannot leave US |
| Financial services (PCI) | ❌ | Vendor approval required |
| EU GDPR-strict (telco, public sector) | ⚠️ | Need explicit DPO sign-off |
| US Federal / DoD | ❌ | Hard no |

**How we enforce per-tenant control:**

Each tenant has an `allowed_models` field in the SQLite tenant store. When
set, the gateway filters the model_list at request time to only deployments
matching the allowlist. To exclude DeepSeek for a sensitive tenant:

```bash
# Via the admin API:
curl -X PATCH /admin/tenants/healthcare-co \
  -H "Authorization: Bearer $MASTER" \
  -d '{"allowed_models_json": "[\"openai/*\", \"anthropic/*\"]"}'
```

The gateway then uses only OpenAI + Anthropic deployments for that tenant.

## Sales positioning

DO:
- "DeepSeek opens up a 90% cost reduction on reasoning tasks compared to Opus."
- "If your security review allows non-US infrastructure, DeepSeek is the
  single biggest savings lever."
- "We can disable DeepSeek per-tenant with one config change."

DON'T:
- Lead with DeepSeek to compliance-sensitive buyers
- Hide the China-hosting fact during security questionnaires (it WILL come up)
- Assume the buyer knows what "DeepSeek" is — many engineering leads don't

## Setup

1. Sign up at https://platform.deepseek.com
2. Buy credit ($5 is enough for development)
3. API Keys → create one
4. Add to Codespace secrets / `.env`:
   ```
   DEEPSEEK_API_KEY=sk-...
   ```
5. Restart the gateway. DeepSeek deployments will activate.

If `DEEPSEEK_API_KEY` is not set, LiteLLM marks those deployments as
unavailable and falls back to OpenAI/Anthropic. The gateway continues
working without DeepSeek.

## Testing

After adding DeepSeek, re-run the verified savings eval to see the new
numbers:

```bash
GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY=$GATEWAY_MASTER_KEY \
  ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  python3 scripts/eval_corpus.py --limit 30
```

Compare the new `eval_report.html` against the pre-DeepSeek baseline in
`baselines/`. Expected uplift: 10-25% additional cost reduction, depending
on traffic mix.
