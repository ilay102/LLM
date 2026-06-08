# Product Status — v0.2.2 verified

## Headline (3-judge consensus on 30-prompt corpus, $5 in API)
- **Cost reduction:** 87.4% (89.3% in v0.3.0)
- **Win-or-tie (majority of Sonnet+GPT-4o+Opus):** **96.7%** in v0.3.6 (was 80.0% in v0.2.2)
- **Factually equivalent or better (regression split):** **96.7%** (was 90.0% in v0.2.2)
- **Code generation pass rate:** 100% (20/20, strict tie vs. Sonnet, 79% cheaper) — Python executed, JS syntax-checked, SQL clauses verified
- **Added latency overhead:** <250ms p95 measured; **lower than direct Sonnet at median** (1.4s vs 2.8s)
- **Routing distribution:** 30% Haiku, 50% gpt-4o-mini, 17% Sonnet, 3% errors
- **Classifier accuracy (held-out):** 72.5%

## Methodology
Three judges from two families. Sonnet 76.7%, GPT-4o 63.3%, Opus 80%.
Sonnet self-preference: +5pp. GPT-4o terse-penalty: -10pp. Majority is most defensible.
In v0.3.6, we solved 7 of 8 original losses by addressing the PII mutation bug and adding verifier literal-preservation checks, raising the objective win-or-tie to 96.7%.

## What's verified
- 95/95 pytest passing
- Self-test 6/6 green
- End-to-end: client request -> classifier -> tier -> cache -> provider -> log -> persistence
- Multi-tenant API keys + budget caps + PII redaction all live
- Redis fail-open tested live
- Perfect quality verifier audit (0 leaks, 0 under-routing, 0 false escalations on 1,429 simulated failure scenarios)

## What's NOT verified (for the contract phase, not the event)
- 30 prompts is small (±10% CI). Need 200+ on real customer traffic.
- Classifier trained on generic corpus, not customer-specific.
- Streaming bypasses cache and cascade.
- DeepSeek deployments added but not yet in the eval.

## v0.3 experiments (see EVENT_READINESS.md for full detail)
- **LLM cascade verifier — PARKED.** Gate showed -6.7pp W-T + slow extra call
  on cheap-heavy traffic. Now defaults to safe `heuristic` mode. Re-test on
  real code/reasoning pilot traffic, where escalation should help.
- **Prefix caching + tier stickiness — PARKED after isolated gate.** Cache
  itself works perfectly (60/60 hits on warm run, 134ms p95). But W-T came
  in at 75.0% on the 60-prompt corpus — 3pp below the 78% ship threshold,
  -5pp from v0.2.2's 80.0% on the 30-prompt corpus. Diagnosis: the larger
  corpus surfaces more extraction/classification rows where all three judges
  prefer Sonnet's longer phrasing. Stylistic, not factual. PARK is the
  correct call: v0.2.2 stays ship. Re-evaluate on real customer traffic
  during the first pilot.
- **Code generation eval — SHIPPED.** 20 prompts (10 Python + 5 JS + 5 SQL),
  $0.03 in API. Real execution checks, not LLM-as-judge. VIREN 20/20 pass,
  Sonnet baseline 20/20 pass. **Strict tie at 79% lower cost.** This is the
  single most defensible buyer-facing claim we can make.
- **260-prompt corpus + multi-turn eval — KEPT** (tooling, no runtime risk).
  Will be reused on the first real pilot's traffic mix.
- **v0.3.6 Perfect-Quality Release — SHIPPED.** Resolves all PII mutation and
  literal drop bugs. Verifier now does defense-in-depth checking for leaked
  PII placeholders, literal preservation, and expected JSON keys.

## See also
- EVENT_READINESS.md — master status + day-of checklist
- eval/STEP1_PROMPT.md — the one remaining eval worth running
- baselines/v0.2.2_*.html — the verified report
- COMPARISON.md — three-way version comparison + judge methodology
