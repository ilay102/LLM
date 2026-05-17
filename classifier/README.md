# Classifier Training Corpus

200 prompts, distributed roughly to mirror real SaaS LLM traffic.

## The three tiers (what the classifier predicts)

### CHEAP — small model handles it fine
Simple, single-step tasks where the small/fast model (Haiku, gpt-4o-mini)
gives an answer indistinguishable from the frontier model.

**Signals:**
- < 200 chars total
- Single-fact lookup, classification, extraction, short translation
- No code blocks (or trivial one-liners)
- No multi-step reasoning required
- Output is short and well-defined (yes/no, JSON object, one sentence)

**Examples:** sentiment classification, entity extraction, format conversion,
short translation, single-line code, spelling/grammar fix.

### BALANCED — mid-tier model is enough
Real generation, code, or reasoning, but the path is clear. Mid-tier
models (Sonnet, GPT-4o) give acceptable answers reliably.

**Signals:**
- 200-2000 chars, may contain code or structured input
- Needs some judgment but no novel insight
- Output is structured but non-trivial (paragraph, code function, query)
- Mechanical multi-step but not deeply chained

**Examples:** summarize a paragraph, write a professional email, refactor
small code, generate structured output from a spec, write a moderate SQL
query, simple code review.

### FRONTIER — bet-the-output, use the best model
Deep reasoning, multi-step planning, agentic behavior, or high-stakes
output (architecture, security, customer-facing strategic comms). Use
the best model (Opus 4.7).

**Signals:**
- Often > 1000 chars, may include code AND domain context
- Multi-step reasoning where being subtly wrong is expensive
- Architecture, formal proofs, agent loop planning, complex debugging
- Open-ended strategic analysis

**Examples:** design a multi-region SaaS architecture, prove a math
statement, debug a flaky production issue with multiple hypotheses,
plan a multi-tool agent workflow.

## How to use the corpus

1. `prompts_to_label.jsonl` — 200 prompts, no labels. Source-of-truth.
2. `labels_claude.jsonl` — seed labels by Claude. v1 training data.
3. To get human labels for inter-annotator agreement, run the labeling
   UI (when built) and save to `labels_A.jsonl`, `labels_B.jsonl`.
4. Compute kappa between `labels_claude.jsonl` and human labels to
   measure if Claude's seed labels match human judgment. If kappa ≥ 0.7,
   the seed is good enough to ship a v1 classifier. If lower, hand-label
   and override.

## Distribution

| Tier | Count | % | Reflects |
|---|---|---|---|
| CHEAP | 80 | 40% | Most production traffic is simple |
| BALANCED | 80 | 40% | Bulk of real work |
| FRONTIER | 40 | 20% | The expensive minority |

## Notes

- All prompts are self-contained — no placeholder `[snippet]` text.
- No PII, no real names of real companies/people.
- Mix of length, style, vertical (SaaS, e-commerce, dev tools, etc.).
- Designed to look like prompts a real SaaS app sends in production.
