# MSP LLM Gateway

OpenAI-compatible gateway that classifies, caches, routes, and falls back —
designed to drop in front of a client's app with one line of config:

```python
client = OpenAI(base_url="http://your-gateway/v1", api_key="<tenant-key>")
```

## Quickstart (local, today)

```bash
cd gateway
cp .env.example .env
# edit .env: set OPENAI_API_KEY, ANTHROPIC_API_KEY, GATEWAY_MASTER_KEY
docker compose up --build
```

Wait ~60s for the first run (downloads bge-small embedding model). Then:

```bash
pip install openai
python tests/smoke.py
```

You should see 5 calls with different tier picks, then a 6th call returning
in <50ms because the semantic cache hit.

Watch live decisions:
```bash
docker compose logs -f gateway
tail -f shadow_log.jsonl   # one JSON record per call
```

Inspect the cache: open http://localhost:8001 (RedisInsight UI).

## Architecture

```
Client SDK ──► FastAPI gateway (router/main.py)
                  │
                  ├── auth (bearer = tenant key)
                  ├── cache lookup ──► Redis Stack (vector index)
                  ├── classifier ──► tier: cheap | balanced | frontier
                  ├── prompt-cache injection (Anthropic ephemeral cache_control)
                  ├── LiteLLM Router  ──► OpenAI / Anthropic / etc.
                  │     └── built-in fallback chain on 5xx / rate-limit
                  ├── cascade verifier (retry weak cheap responses on balanced)
                  ├── cache write
                  └── post-hook: shadow_log.jsonl  +  metrics
```

## Request headers (per-tenant control plane)

| Header | Purpose |
|---|---|
| `Authorization: Bearer <key>` | Tenant API key |
| `x-min-tier: balanced` | Forbid downgrade below this tier (per-route) |
| `x-route-hint: classification` | Optional hint to the classifier |
| `x-no-cache: 1` | Bypass semantic cache for this call |

## Files

- `litellm_config.yaml` — model list, prices, fallback chain
- `router/main.py` — FastAPI app + lifecycle
- `router/classifier.py` — rules + learned tier picker
- `router/semantic_cache.py` — Redis Stack vector cache
- `router/pricing.py` — server-side cost computation
- `router/embeddings.py` — bge-small loader
- `tests/smoke.py` — end-to-end smoke test

## Production hardening checklist

- [ ] Replace `GATEWAY_MASTER_KEY` with per-tenant keys in a database
- [ ] Mount TLS cert (mTLS preferred for inside-VPC deploys)
- [ ] Set up Langfuse env vars for trace export
- [ ] Train the classifier head on real shadow traffic (see `shadow-eval/`)
- [ ] Add per-tenant rate limits (LiteLLM supports this)
- [ ] Wire shadow_log.jsonl → Loki or your warehouse
- [ ] Add Prometheus exporter (`/metrics`) — trivial with `prometheus-fastapi-instrumentator`
