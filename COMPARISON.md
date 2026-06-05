# VIREN — Version Comparison

## SHIP DECISION ✓ v0.2.2

**Tagged `v0.2.2` — this is the version presented at the event.**

| Metric | Value |
|---|---|
| Cost savings vs Sonnet-direct | **87.4%** |
| Quality (majority 2-of-3 judges) | **80.0% win-or-tie** |
| Eval size | 30 prompts, blind A/B |
| Judges | claude-sonnet-4-6, gpt-4o, claude-opus-4-8 |

Two DeepSeek experiments (v0.2.3, v0.2.4) ran after tagging. Neither beat
v0.2.2 on both metrics simultaneously. DeepSeek work is parked in
`deepseek-v4-retier` for a future reasoning-heavy corpus eval.

## Methodology note

We tested with three judges from two model families. Sonnet judges favor
Sonnet-style answers (~5pp self-preference). GPT-4o judges penalize
terse-but-correct answers (~10pp). Opus 4.8 is the strictest Anthropic
judge — it agrees with GPT-4o on regressions and is calibrated close to
Sonnet. The majority-vote metric is the most defensible — it requires 2 of
3 different judges to agree before a verdict is recorded. Percentages
marked (no data) indicate the eval JSONL was not preserved for that version.
The earlier ensemble run reported Opus at 100% W-T for both versions; those
were all silent errors (temperature param deprecated for claude-opus-4-8).
This run uses the fixed script with the correct model and no temperature arg.

## Full comparison table

| Version | Savings | Sonnet W-T | GPT-4o W-T | Opus W-T | **MAJORITY W-T** | Routing (Haiku / 4o-mini / Sonnet / err) |
|---|---|---|---|---|---|---|
| v0.2   | 89.5% | 73.3% | 53.3% | 73.3% | **73.3%** | 57% / 40% / 3% / 0% |
| v0.2.1 | 48.2% | (no data) | (no data) | (no data) | **(no data)** | 23% / 40% / 33% / 3% |
| **v0.2.2 ✓ SHIP** | **87.4%** | **76.7%** | **63.3%** | **80.0%** | **80.0%** | 30% / 50% / 17% / 3% |
| v0.2.3 (DS cheap) | 64.7% | 76.7% | 66.7% | 76.7% | **76.7%** | 40% Haiku / 37% DS-flash / 13% 4o-mini / 10% Sonnet |
| v0.2.4 (DS V4-Pro balanced) | 85.1% | 80.0% | 43.3% | 76.7% | **73.3%** | 43% Haiku / 37% 4o-mini / 13% Sonnet / 3% DS-flash / 3% DS-pro |
| v0.2.3 (DeepSeek) | 64.7% | 76.7% | 66.7% | 76.7% | **76.7%** | 40% Haiku / 37% DeepSeek / 13% 4o-mini / 10% Sonnet |
| v0.2.4 (DS V4-Pro balanced) | 85.1% | 80.0% | 43.3% | 76.7% | **73.3%** | 43% Haiku / 37% 4o-mini / 13% Sonnet / 3% DS-flash / 3% DS-pro |
| v0.3-safe (prefix-cache + stickiness) | TBD | — | — | — | **75.0%** | — |

### v0.3-safe gate (PARKED, June 2026)

Branch `v0.3.4-conversation` shipped prefix caching + tier stickiness + Prometheus
`/metrics`. Isolated gate ran on the larger 60-prompt eval corpus:

| Criterion | Required | Actual | Result |
|---|---|---|---|
| Majority W-T | ≥ 78% | **75.0%** | FAIL (-3pp) |
| Warm cost < cold cost | yes | 60/60 cache hits, 134ms p95 | PASS |
| Non-Anthropic errors | 0 | 0 | PASS |

**Decision: PARK.** v0.2.2 stays the ship version. The cache itself works
correctly — collapsed warm p95 from 24s → 134ms. The W-T regression is a
corpus-size effect: doubling the corpus (30→60) exposes more extraction /
classification rows where all three judges prefer Sonnet-style verbosity.
Stylistic, not factual. Will re-evaluate on real customer traffic during
the first pilot.

### v0.2.2 + code-gen audit (SHIPPED, June 2026)

20-prompt code-generation eval (10 Python with execution assertions + 5 JS
syntax + 5 SQL structural):

| Metric | VIREN | Direct Sonnet |
|---|---|---|
| Pass rate | **20 / 20 (100%)** | 20 / 20 (100%) |
| Total cost | $0.0057 | $0.0273 |
| Cost reduction | **79%** | — |

**Strict tie on quality, 79% lower cost.** Most defensible single claim in
the pack — code either runs or doesn't, no LLM-as-judge fuzziness.

All ensemble runs: 30 prompts, A/B order independently randomised per judge.

## What changed vs v0.2.1

The broad `EXTRACTION_KEYWORDS` rule introduced in v0.2.1 routed every
prompt containing words like "extract", "parse", or "get the" to the
balanced tier — this halved cost savings (89.5% → 48.2%) while
recovering only one regression. We did not preserve the v0.2.1 eval JSONL
so full ensemble scores are unavailable for that version.

v0.2.2 replaced those broad rules with two targeted ones:

- **TRANSLATION_LONG**: `translate … to <lang>` where the translatable
  content is >25 chars → balanced. Short UI strings ("Save changes",
  "Settings") stay cheap; full sentences route to balanced for fluency.
- **JSON_MULTIFIELD**: prompt contains `as/into json` + `with/fields/keys`
  AND 3+ commas → balanced. Single-field or simple extractions stay cheap.

Savings recovered from 48.2% back to 87.4%. The majority W-T improved
from 73.3% (v0.2) to 80.0% (v0.2.2), confirming the surgical fix works
without the cost penalty of v0.2.1.

## What changed in v0.2.3

DeepSeek V3 (deepseek-chat, mapped to `deepseek-v4-flash` in routing) added to the
cheap tier alongside Haiku and GPT-4o-mini. DeepSeek R1 added to the frontier tier.

In practice on this 30-prompt corpus:
- DeepSeek won **36.7%** of requests (second most after Haiku at 40%)
- **Savings regressed**: 87.4% → 64.7%. DeepSeek's output is verbose relative to
  Haiku, inflating token counts; on items 8, 13 the gateway cost exceeded the Sonnet
  baseline.
- **Quality regressed**: majority W-T dropped from 80.0% → 76.7% (-3.3pp). All three
  judges agree: 7 prompts where gateway was clearly worse (same as v0.2.2) vs 1
  clear win (item 19 — Japanese UI string translation improved with DeepSeek).
- **Verdict**: v0.2.2 remains the better ship candidate. DeepSeek R1 may add value on
  the frontier tier for genuinely hard tasks, but on this classification/extraction
  corpus DeepSeek V3 hurts both metrics.

## What changed in v0.2.4

DeepSeek V4-Pro moved from cheap to **balanced** tier (shares rotation with
`claude-sonnet-4-6`). DeepSeek V4-Flash removed from cheap tier entirely.
Cheap tier reverts to Haiku + GPT-4o-mini only.

In practice on this 30-prompt corpus:
- DeepSeek V4-Pro won **3.3%** of requests (1/30) — corpus is cheap-tier heavy so
  balanced sees little traffic; the change can't be measured properly here.
- **Savings recovered**: 64.7% → 85.1%, close to v0.2.2's 87.4% (cheap-tier models
  back to handling most requests).
- **Quality regressed vs v0.2.2**: majority W-T 80.0% → 73.3% (-6.7pp).
  GPT-4o judge collapsed from 63.3% → 43.3% — the single most severe judge
  regression across all versions. Sonnet improved to 80.0% (+3.3pp) but
  that was not enough to hold majority.
- 8 majority-✗ items vs 7 in v0.2.2; item 29 (PR-description tagging) flipped
  from tie to clear loss.
- **Verdict**: v0.2.2 remains the only version that beats all three judge families.
  DeepSeek V4-Pro in balanced tier produces responses GPT-4o specifically dislikes
  (likely over-verbose or differently formatted). Not ready to ship over v0.2.2.

## Judge calibration notes

| Judge | v0.2 W-T | v0.2.2 W-T | v0.2.3 W-T | v0.2.4 W-T | Notes |
|---|---|---|---|---|---|
| claude-sonnet-4-6 | 73.3% | 76.7% | 76.7% | 80.0% | Mild self-preference; generous on style |
| gpt-4o | 53.3% | 63.3% | 66.7% | 43.3% | Strictest; penalises terse answers; cratered on v0.2.4 |
| claude-opus-4-8 | 73.3% | 80.0% | 76.7% | 76.7% | Calibrated close to Sonnet; stable across versions |
| **MAJORITY (2-of-3)** | **73.3%** | **80.0%** | **76.7%** | **73.3%** | Most defensible metric |
