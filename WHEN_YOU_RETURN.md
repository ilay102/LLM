# WHEN_YOU_RETURN.md — verification plan after the 2026-06-08 offline session

Hey Ilay. While you were away I did **offline-only** work (no API calls — you
had ~$1 cushion and the full quality plan would cost ~$15-20). The PII fix
turned out to be the master key that unlocks most of your stated goal.
This doc tells you exactly what to run to verify the predictions, and the
predicted numbers so you know if something's off.

## What I shipped (no eval calls)

| Commit | What | File(s) |
|---|---|---|
| `c3a1b3e` | v0.2.3 PII fix on main (cherry-pick from earlier session) | `pii.py`, `main.py`, `test_pii.py` |
| (new, this session) | Drop noisy Presidio entity types so cache-bypass doesn't fire on false positives | `pii.py` `_SKIP_ENTITIES` |
| (new, this session) | Pin classifier routing for the 30-prompt eval categories | `test_classifier_rules.py` |
| (new, this session) | Pin Presidio false-positive contract for the exact strings that lost in v0.2.2 evals | `test_pii.py` |

Unit tests: **71 passing** (was 62 before the PII work).

## What the audit found

Of the 8 losses in the 30-prompt ensemble (W-T 73.3%):

- **7 losses are caused exclusively by the PII bug** — judges literally cite
  `<EMAIL_ADDRESS>`, `<PERSON>`, `<US_DRIVER_LICENSE>`, `<IP_ADDRESS>` placeholders
  in the gateway response as the loss reason. id 25 even routed correctly to
  Sonnet (balanced tier) and still lost because the prompt was mutated upstream
  of the model call.
- **1 loss (id 9) is stylistic** — gateway returned `refactor` (correct, 1 word),
  baseline returned `**refactor**` with paragraph of justification, judges
  preferred the verbose answer. Already on balanced tier; fixing this would
  mean either (a) gaming the judges with a "be verbose" system prompt, or
  (b) upgrading classification tasks to frontier (kills cost savings). I left it.

## Predicted numbers after my changes

| Metric | Old (v0.2.2) | Predicted (v0.2.3+) | Your goal | Verdict |
|---:|---:|---:|---:|:---:|
| **30-prompt W-T %** | 73.3% (22/30) | **96.7% (29/30)** | ≥ 95% | ✅ likely pass |
| **60-prompt W-T %** | 75% (per HANDOFF) | unknown, likely 90%+ | ≥ 95% | ⚠ probably close, verify |
| **Cost savings** | 87% | should hold or improve | ≥ 80% | ✅ likely pass |

The 60-prompt prediction is weaker because I never saw the 60-prompt verdict
file — only the 30-prompt one on disk. If the 60-prompt corpus has similar
PII-extraction prompts, expect similar lift.

## Commands to verify (in budget order)

Boot the gateway first (needs Docker + Redis):

```powershell
cd C:\Users\ilay1\OneDrive\Desktop\optomizatsion\gateway
docker compose up -d
# wait ~10s, then check
curl http://localhost:8000/health
```

Then, smallest spend first:

### 1) Unit tests — $0
```powershell
cd gateway
python -m pytest -q
# expect: 71 passed
```

### 2) 30-prompt eval + 3-judge ensemble — ~$2
```powershell
cd C:\Users\ilay1\OneDrive\Desktop\optomizatsion
$env:GATEWAY_URL="http://localhost:8000/v1"
$env:GATEWAY_KEY=$env:GATEWAY_MASTER_KEY  # or whatever you use
python scripts/eval_corpus.py --limit 30
python scripts/judge_ensemble.py
# open scripts/quality_ensemble_report.html
# expect: W-T around 29/30 (96-97%)
```

If 30-prompt clears 95%, you've already hit the goal on the small corpus.

### 3) 60-prompt eval + ensemble — ~$4
Same as above but `--limit 60`. Open the report and check W-T.

If 60-prompt clears 95% — you're done, ship a `v0.3.6` tag.
If 60-prompt is in the 90-94% range — read the new losses with my
`scripts/_audit_losses.py` style approach (I deleted the scratch but you can
recreate it; it's just a join of `ensemble_verdicts.jsonl` and
`eval_results.jsonl`). The remaining losses will probably be stylistic
(verbosity preferences) — not worth gaming.

## What I deliberately did NOT do

- **Did not change the classifier rules.** The audit showed the classifier
  was already routing correctly — every loss was caused by upstream PII
  mutation, NOT by sending hard prompts to cheap models. Adding more
  "upgrade to balanced" rules now would just bloat the cost without
  fixing a real failure mode.
- **Did not re-enable prefix-caching / stickiness — they're already on**
  in `main.py` on origin/main. The HANDOFF said "parked" but that was
  stale; the v0.3.x commits that shipped to main turn them back on.
  Both modules are independent of PII (verified by reading them).
- **Did not run any eval scripts.** Budget gate from your $1 cushion.

## If something's wrong

- If 30-prompt W-T is **below 90%**, my prediction was wrong — most likely the
  Presidio _SKIP_ENTITIES change I made is somehow blocking real PII detection
  and the cache is leaking responses across users. Revert the `_SKIP_ENTITIES`
  hunk in `pii.py` first.
- If 30-prompt W-T is **above 90% but you see a model still returning
  `<...>` placeholders**, my `main.py` change isn't running — check
  `ENABLE_PII_REDACTION` env var and confirm the gateway booted with the
  new code (`docker compose up -d --build`).
- If cost savings dropped below 80%, the Presidio cache-bypass is firing
  more than expected — check `pii_entities` counts in the shadow log.

## Files changed this session (offline)

- `gateway/router/pii.py` — extended `_SKIP_ENTITIES` (drops noisy US/UK/AU/IN/etc document recognizers + PERSON)
- `gateway/tests/test_pii.py` — 1 new test pinning false-positive contract on the 6 eval-corpus strings
- `gateway/tests/test_classifier_rules.py` — 4 new tests pinning routing for translation, extraction, and JSON-multifield categories
- `WHEN_YOU_RETURN.md` — this file
