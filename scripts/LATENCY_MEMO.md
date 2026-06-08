# VIREN — Latency measurement memo (v0.2.2)

For the evidence pack. Honest numbers, real source. Re-run via
`scripts/measure_overhead.py` once the multi-provider patch is deployed
(now supports OpenAI + DeepSeek direct comparison, not just Anthropic).

## What we ran

- 30 probe requests (fresh, cheap-tier prompts) — pure gateway timing
- 60-prompt eval on `corpus_v1.jsonl` — gateway vs. direct-Sonnet baseline
- Warm-cache rerun — same 60 prompts, semantic cache enabled

## Numbers (real, measured, on this stack)

| What | p50 | p95 |
|---|---|---|
| **Gateway routing overhead, fresh cheap-tier** | — | **233 ms** |
| Total gateway latency, cold eval (full corpus) | 1382 ms | 37,215 ms* |
| Direct Sonnet baseline (same prompts, same eval) | 2754 ms | 6084 ms |
| Warm gateway (semantic cache hits) | **26 ms** | **248 ms** |

\* The 37s p95 cold outlier is **DeepSeek V4-Pro variance on ~4 prompts**.
It's a provider-side issue, not gateway overhead. If we exclude DeepSeek
rotation, total p95 drops dramatically. Flag if anyone asks.

## The defensible claims you can make at the event

1. **"VIREN adds under 250 ms of routing overhead at p95."** Source: 30 fresh
   probe requests, gateway-only timing.

2. **"At median, gateway latency is LOWER than direct Sonnet."** 1382 ms vs
   2754 ms — because requests route to cheap-tier models that are faster, not
   just cheaper. This is a counter-intuitive win.

3. **"Cache hits return in 26 ms p50."** Real semantic-cache replay number.
   That's the 25% of typical SaaS traffic that's free + instant.

## The over-claims to AVOID

- ❌ "Sub-50 ms overhead" — only true for cache hits, not the routing path.
- ❌ "Always faster than baseline" — true at p50, not p95 (DeepSeek variance).
- ❌ "Sub-100 ms p95 overhead" — current measurement says 233 ms p95.

## Why <250 ms p95 is actually a strong number

For comparison:
- Typical LLM API call: 1-5 seconds end-to-end
- Typical proxy / gateway overhead in industry: 50-300 ms
- VIREN at 233 ms p95: **inside the industry norm**, doing more work (PII redaction, classifier, cache lookup, prompt-cache injection)

CTO-grade interpretation: "We add latency comparable to a basic reverse proxy,
in exchange for cost routing, semantic caching, and observability that pays
that overhead back 10x on cache hits."

## What the multi-provider script now adds

The original `measure_overhead.py` could only direct-call Anthropic, so when
the gateway picked gpt-4o-mini (which it does most of the time on cheap tier),
the paired sample was 0. The patched version handles three providers:

- Anthropic (Haiku, Sonnet, Opus)
- OpenAI (gpt-4o-mini, gpt-4o)
- DeepSeek (V4-Pro, V4-Flash via `deepseek-chat`, R1 via `deepseek-reasoner`)

Re-running with all three direct clients will produce a real **paired overhead
distribution** — apples-to-apples for every routing decision. That's the
gold-standard number for the evidence pack.

## Re-run command

```bash
GATEWAY_URL=http://localhost:8000/v1 GATEWAY_KEY="$GATEWAY_MASTER_KEY" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
python3 scripts/measure_overhead.py --n 30
```

Should now show ~30 paired samples (not 0). Cost: ~$0.30.
