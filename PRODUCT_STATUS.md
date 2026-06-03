# Product Status — What's Real, What's Not

Honest accounting. Updated when reality changes.

## ✅ Real and tested

| Capability | Where | How verified |
|---|---|---|
| OpenAI-compatible gateway | `gateway/router/main.py` | Smoke test passes on every commit |
| Multi-provider routing (Anthropic + OpenAI) | `gateway/litellm_config.yaml` | Smoke shows Haiku/Sonnet/Opus picked |
| Semantic cache (Redis Stack + HNSW) | `gateway/router/semantic_cache.py` | Cached-* ID seen on repeat in smoke |
| Provider fallbacks on 5xx / rate-limit | LiteLLM Router config | LiteLLM behavior |
| Redis fail-open | PR #7 merged | Live 3-phase test passed |
| Rule-based tier classifier | `gateway/router/classifier.py` | Unit tests `test_classifier_rules.py` |
| Cost computation w/ prompt-cache discount | `gateway/router/pricing.py` | Unit tests `test_pricing.py` |
| Cascade verifier (cheap→balanced retry on weak output) | `main.py looks_low_quality()` | Unit tests `test_cascade_verifier.py` |
| Per-tenant API keys (SQLite-backed) | `gateway/router/tenants.py` | Unit tests `test_tenants.py` |
| Per-tenant monthly budget cap | `tenants.over_budget()` + main.py | Unit tests + over-budget returns 429 |
| Per-tenant min-tier guardrail | `main.py` | Logic in tier-decision path |
| PII redaction (Presidio + regex fallback) | `gateway/router/pii.py` | Unit tests `test_pii.py` |
| SQLite event log (queryable, persistent) | `gateway/router/persistence.py` | Unit tests `test_persistence.py` |
| Admin endpoints (create tenant, list, usage) | `main.py /admin/*` + `scripts/admin.py` | Manual curl works |
| Self-test script | `scripts/self_test.sh` | One command verifies 6 axes of correctness |
| Verified savings runner | `scripts/eval_corpus.py` | Runs all 200 prompts, generates HTML report |
| pytest suite + GitHub Actions CI | `gateway/tests/`, `.github/workflows/ci.yml` | Runs on every PR |
| Pilot deployment scripts | `deploy/pilot.sh` + `teardown.sh` | Untested end-to-end (next step) |
| Customer integration samples | `deploy/integration_samples/*` | Code written, untested with a real customer |

## ⚠️ Built but not yet verified end-to-end

These need a real run before claiming they work:

1. `deploy/pilot.sh` — written but never executed
2. `deploy/integration_samples/mirror_python.py` — never run against a real app
3. `scripts/eval_corpus.py` on the full 200 prompts — never executed (will cost ~$5-10 in API)
4. The trained classifier — `classifier/train.py` exists; weights need to be produced once
5. PII redaction with Presidio installed (regex fallback is tested; full Presidio needs `python -m spacy download en_core_web_sm`)

**Action:** Run `scripts/self_test.sh` against a fresh `pilot.sh` deploy. Whatever's red, fix.

## ❌ Honest gaps (not blockers for first 3 pilots, but eventually needed)

| Missing | Impact | When to build |
|---|---|---|
| Streaming cascade & cache | Streaming requests bypass cascade + cache | After pilot #1, if clients stream |
| Real-time per-tenant Grafana dashboards | Clients can't self-serve metrics yet | After pilot #2 |
| Helm chart for K8s deploy | Docker Compose limits us to single-node | When client #1 needs K8s |
| Postgres backend (vs. SQLite) | SQLite limits horizontal scale | When client traffic > 50 RPS |
| Prometheus `/metrics` exporter | No external metrics scraping yet | Easy add; do during pilot #1 |
| Secrets manager integration (Vault/AWS SM) | API keys in env vars currently | Before SOC2 |
| Audit log (immutable) | Per-tenant change history | Before SOC2 |
| Real classifier head trained on customer data | Centroids from 200 generic prompts only | Month 2 of pilot |
| Adversarial cache poisoning test | We trust the threshold; haven't measured false-hit rate | Before client #2 |
| Cross-tenant isolation test (automated) | Namespacing logic exists; no automated test | Before multi-tenant deploy |
| LLMLingua-2 prompt compression | Could add another 10-20% savings on long prompts | Month 3+ |
| Real golden set + nightly quality CI | Quality regressions could ship silently | When we have real customer traffic |
| SOC2, GDPR DPO, compliance | Required for enterprise | Month 6+ if traction supports it |

## How to verify the product is real (run this now)

```bash
# 1. Build + start gateway
cd gateway && docker compose up --build -d
sleep 60

# 2. Train the classifier (one-time, ~3 min)
cd ../classifier && python train.py
cd ..

# 3. Run self-test
bash scripts/self_test.sh

# 4. Run pytest
cd gateway && pytest -m unit -v

# 5. Verify savings on a 20-prompt subset
cd ../scripts && python eval_corpus.py --limit 20
```

If all four are green, the product is real. Open `scripts/eval_report.html`
in a browser — that's the report you show prospects.

## Version

- v0.1.0 — smoke working, rules-only classifier, single master key, JSONL log
- **v0.2.0 (current)** — trained classifier, multi-tenant SQLite, PII redaction, budget caps, persistent SQLite events, admin API, CI, self-test
- v0.3.0 (planned) — Helm chart, Prometheus metrics, streaming cascade
- v1.0.0 (planned) — first 5 paid clients deployed, SOC2 in progress
