PARKED: see COMPARISON.md v0.2.4 row. Needs reasoning-heavy corpus to fairly evaluate V4-Pro.

## Why parked

DeepSeek V4-Pro was evaluated on the 30-prompt classification/extraction corpus
used for v0.2.2. On that corpus:

- V4-Pro won only 3.3% of balanced-tier slots (corpus is cheap-tier heavy)
- GPT-4o judge W-T collapsed from 63.3% (v0.2.2) → 43.3% (v0.2.4)
- Majority W-T: 80.0% → 73.3% — worst quality score across all versions
- Savings recovered to 85.1% but still trail v0.2.2's 87.4%

The corpus does not contain enough reasoning-intensive prompts to exercise
the balanced tier meaningfully. A fair V4-Pro evaluation needs:

- Multi-step reasoning tasks (code, math, planning)
- Long-context extraction (>1k token inputs)
- Complex structured-output generation

## Next steps to unpark

1. Build a 30+ prompt reasoning corpus (see classifier/labels.jsonl for category ideas)
2. Run eval_corpus.py --limit 30 with that corpus
3. Run judge_ensemble.py — compare majority W-T vs v0.2.2 baseline
4. If majority W-T ≥ 80.0% AND savings ≥ 80%, merge to main as v0.2.5
