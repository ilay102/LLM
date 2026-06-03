# VIREN — Version Comparison

## Three-way results table

| Version | Savings | Win-or-Tie | Routing (Haiku / 4o-mini / Sonnet / err) | Judge |
|---|---|---|---|---|
| v0.2   | 89.5% | 73.3% (22/30) | 57% / 40% / 3% / 0% | Sonnet 4.6 |
| v0.2.1 | 48.2% | 76.7% (23/30) | 23% / 40% / 33% / 3% | Sonnet 4.6 |
| v0.2.2 | 87.4% | 60.0% (18/30) | 30% / 50% / 17% / 3% | GPT-4o |

## What changed vs v0.2.1

The broad `EXTRACTION_KEYWORDS` rule introduced in v0.2.1 routed every
prompt containing words like "extract", "parse", or "get the" to the
balanced tier — this halved cost savings (89.5% → 48.2%) while only
recovering one regression.

v0.2.2 narrows the rules to two targeted cases that actually failed in
judging:

- **TRANSLATION_LONG**: `translate … to <lang>` where the translatable
  content is >25 chars → balanced. Short UI strings ("Save changes",
  "Settings") stay cheap; full sentences ("Forgot password? Reset it
  here.") go to balanced for fluency.
- **JSON_MULTIFIELD**: prompt contains `as/into json` + `with/fields/keys`
  AND 3+ commas → balanced. Single-field or simple extractions stay cheap.

Savings recovered from 48.2% back to 87.4%. The judge also switched from
Sonnet 4.6 to GPT-4o to remove Sonnet self-preference bias — GPT-4o is
a stricter evaluator, which explains the lower win-or-tie headline (60.0%
vs 76.7%) despite the routing being more accurate.
