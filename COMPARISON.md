# VIREN — Version Comparison

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
| v0.2.2 | 87.4% | 76.7% | 63.3% | 80.0% | **80.0%** | 30% / 50% / 17% / 3% |
| v0.2.3 (DeepSeek) | 64.7% | 76.7% | 66.7% | 76.7% | **76.7%** | 40% Haiku / 37% DeepSeek / 13% 4o-mini / 10% Sonnet |

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

## Judge calibration notes

| Judge | v0.2 W-T | v0.2.2 W-T | v0.2.3 W-T | Notes |
|---|---|---|---|---|
| claude-sonnet-4-6 | 73.3% | 76.7% | 76.7% | Mild self-preference; generous on style |
| gpt-4o | 53.3% | 63.3% | 66.7% | Strictest; penalises terse answers |
| claude-opus-4-8 | 73.3% | 80.0% | 76.7% | Calibrated close to Sonnet; agrees on clear regressions |
| **MAJORITY (2-of-3)** | **73.3%** | **80.0%** | **76.7%** | Most defensible metric |
