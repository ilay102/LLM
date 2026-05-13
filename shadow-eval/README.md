# Shadow Eval Harness

Generates the indisputable quality-delta + cost-savings report for a CTO.

Pipeline:

```
Client traffic  ──►  1. capture_traffic.py    (sample real prompts -> dataset.jsonl)
                     2. promptfoo eval         (run baseline vs. gateway, judge pairwise)
                     3. generate_report.py     (HTML/PDF: $ saved, win-rate, regressions)
```

## What this proves

- **Quality is preserved.** Pairwise win/tie rate ≥ 98% target with Sonnet 4.6 as judge, ties broken in shadow's favour.
- **Cost is reduced.** Token-level $ for both paths, computed server-side.
- **Latency is comparable.** p50/p95 deltas reported.

## Quickstart (local, today)

```bash
cd shadow-eval
npm install -g promptfoo
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY, GATEWAY_KEY

# Use the provided seed dataset, or capture your own:
python capture_traffic.py --source ../gateway/shadow_log.jsonl --out dataset.jsonl --n 100

# Run the eval. Promptfoo will call:
#   - baseline:  anthropic/claude-sonnet-4-6 directly
#   - shadow:    http://localhost:8000/v1 (the gateway)
# Then judge each pair with anthropic/claude-sonnet-4-6.
promptfoo eval -c promptfooconfig.yaml

# View the verdict UI
promptfoo view

# Generate the executive PDF
python generate_report.py --results $(promptfoo list --json | jq -r '.[0].evalId') --out report.html
```

## Files

- `promptfooconfig.yaml` — providers, judge, dataset
- `judge_prompt.txt` — pairwise rubric (correctness, completeness, format, tone, safety)
- `dataset.jsonl` — seed prompts (replace with `capture_traffic.py` output)
- `capture_traffic.py` — turns `shadow_log.jsonl` into a dataset
- `generate_report.py` — builds the CTO-ready HTML report
- `requirements.txt`
