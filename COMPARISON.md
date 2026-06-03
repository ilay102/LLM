# VIREN — Version Comparison

## Methodology note

We tested with three judges from two model families. Sonnet 4.6 judges
favor Sonnet-style answers (~5pp self-preference). GPT-4o judges penalize
terse-but-correct answers (~10pp). Opus 4.7 is the most lenient evaluator
and gave 100% win-or-tie across both versions tested. The majority-vote
metric is the most defensible — it requires 2 of 3 different judges to
agree before a verdict is recorded. Percentages marked (no data) indicate
the eval JSONL was not preserved for that version.

## Full comparison table

| Version | Savings | Sonnet W-T | GPT-4o W-T | Opus W-T | **MAJORITY W-T** | Routing (Haiku / 4o-mini / Sonnet / err) |
|---|---|---|---|---|---|---|
| v0.2   | 89.5% | 73.3% | 53.3% | 100.0% | **73.3%** | 57% / 40% / 3% / 0% |
| v0.2.1 | 48.2% | (no data) | (no data) | (no data) | **(no data)** | 23% / 40% / 33% / 3% |
| v0.2.2 | 87.4% | 76.7% | 60.0% | 100.0% | **80.0%** | 30% / 50% / 17% / 3% |

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

## Judge calibration notes

| Judge | v0.2 W-T | v0.2.2 W-T | Δ | Notes |
|---|---|---|---|---|
| claude-sonnet-4-6 | 73.3% | 76.7% | +3.4pp | Mild self-preference; generous on style |
| gpt-4o | 53.3% | 60.0% | +6.7pp | Strictest; penalises terse answers |
| claude-opus-4-7 | 100.0% | 100.0% | 0pp | Most lenient; rarely penalises gateway |
| **MAJORITY (2-of-3)** | **73.3%** | **80.0%** | **+6.7pp** | Most defensible metric |
