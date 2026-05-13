# Managed LLM Inference Cost Optimization — Reference Implementation

Two artifacts that together form the technical foundation of the MSP service:

```
optomizatsion/
├── gateway/        # OpenAI-compatible gateway: classify, cache, route, fallback
└── shadow-eval/    # Pairwise judge harness → CTO-ready quality + cost report
```

## End-to-end local test (today)

```bash
# 1) Bring up the gateway
cd gateway
cp .env.example .env       # fill OPENAI_API_KEY, ANTHROPIC_API_KEY
docker compose up --build  # ~60s first run

# 2) Smoke-test it
pip install openai
python tests/smoke.py

# 3) Run the shadow evaluation (separate terminal)
cd ../shadow-eval
cp .env.example .env       # fill ANTHROPIC_API_KEY, GATEWAY_KEY
pip install -r requirements.txt
python run_pairwise.py --dataset dataset.jsonl --out pairwise_results.jsonl

# 4) Generate the CTO report
python generate_report.py --in pairwise_results.jsonl --out report.html
open report.html
```

Within ~5 minutes you'll have an HTML page showing:
- **Shadow win-or-tie %** vs baseline (Sonnet 4.6 direct)
- **$ saved** + projected monthly at 1M calls
- **Routing distribution** (which tiers the gateway chose)
- **p50/p95/p99 latency** comparison
- **Audit table** of every prompt/decision

## What's in each piece

### `gateway/` — production-shaped, single-tenant

| File | Purpose |
|---|---|
| `docker-compose.yml` | Redis Stack + FastAPI gateway |
| `litellm_config.yaml` | Model deployments, prices, fallbacks |
| `router/main.py` | Request lifecycle: auth → cache → classify → route → cascade → log |
| `router/classifier.py` | Rules + lightweight learned head, returns tier |
| `router/semantic_cache.py` | 2-layer cache (exact + HNSW) on Redis Stack |
| `router/pricing.py` | Server-side cost computation including prompt-cache discount |
| `tests/smoke.py` | 5-call smoke test exercising every tier |

### `shadow-eval/` — proves quality is preserved

| File | Purpose |
|---|---|
| `promptfooconfig.yaml` | Promptfoo config for per-row rubric eval (UI-friendly) |
| `judge_prompt.txt` | Pairwise rubric — 5 axes, strict tie rules |
| `run_pairwise.py` | Concurrent baseline+shadow calls, randomized-order judge |
| `generate_report.py` | Renders `report.html` — the CTO deliverable |
| `capture_traffic.py` | Stratified sampler from gateway's `shadow_log.jsonl` |
| `dataset.jsonl` | 10-prompt seed; replace with real captured traffic for clients |

## How the pieces fit at a client

1. **Pilot week 1** — deploy gateway in passthrough mode (set `ENABLE_CLASSIFIER=false`, all traffic to baseline tier, but cache + log on). Capture `shadow_log.jsonl`.
2. **Week 2** — `capture_traffic.py` → `dataset.jsonl`. Run `run_pairwise.py` to baseline the data.
3. **Week 2** — turn on classifier + cascade. Re-run pairwise. Generate `report.html`.
4. **Week 3** — present report. Promote to canary (1% → 10% → 50% → 100%).
5. **Ongoing** — weekly auto-generated report; alert on win-or-tie rate < 98%.

## Hardening before client #1

The skeletons here are deliberately compact. Before you charge anyone:

- Multi-tenant key store (Postgres or Vault), not env-file master key
- Per-tenant Helm chart, not docker-compose
- Prometheus exporter (`prometheus-fastapi-instrumentator`)
- Trace export to Langfuse (a few lines in `_post_hook`)
- Circuit breaker on Redis (don't let cache outage kill traffic)
- PII scrubber (Microsoft Presidio) before cache write
- Re-train classifier on per-client data (the seeded one is generic)
- Streaming cascade — current skeleton bypasses cascade for streams
- SOC2 runway

## Pricing model

Recommended: **% of verified savings**, capped, with a floor.
- "Verified" = pairwise-judged win-or-tie ≥ 98% on rolling 5k-call sample
- Baseline locked to Month 0 cost-per-task
- Floor (e.g. $5k/mo) covers the work even when savings dip
