# VIREN — LLM Cost Optimization Gateway

**87% verified cost reduction. 90% factually equivalent or better.
100% code-generation pass rate at 79% lower cost.**
3-judge audit, factual-vs-stylistic split — every regression auditable.
Code answers actually *executed*, not LLM-as-judge.

OpenAI-compatible gateway that routes, caches, and proves quality —
designed for 2-week shadow pilots that close design partners.

> **Ship version:** `v0.2.2` (tagged on `main`). Active development on
> `v0.3.4-conversation` adds Prometheus metrics, prefix caching, tier
> stickiness, and a regression-split analyzer. See `EVENT_READINESS.md`
> for the single status doc.

```
                    Your app (OpenAI / Anthropic SDK)
                              │
                  ▼ — mirror — ▼
         prod path        VIREN gateway
              │              │  classify → cache → route → fallback
              ▼              ▼
     Anthropic / OpenAI    same providers, but smart
              │              │
              └──► response  └──► shadow log → pairwise eval → report.html
```

## Repo layout

```
.
├── gateway/                # The product itself
│   ├── router/             # FastAPI app + LiteLLM Router
│   ├── tests/              # Smoke + resilience tests
│   ├── docker-compose.yml
│   └── litellm_config.yaml
│
├── shadow-eval/            # Pairwise quality eval → HTML report
│   ├── run_pairwise.py
│   ├── generate_report.py
│   └── judge_prompt.txt
│
├── classifier/             # Training corpus + seed labels (v1)
│   ├── prompts_to_label.jsonl       # 200 prompts
│   ├── labels_claude.jsonl          # Claude seed labels
│   └── README.md                    # Rubric
│
├── deploy/                 # What we run at customer sites
│   ├── pilot.sh            # One-command deployer
│   ├── teardown.sh         # End-of-pilot cleanup
│   ├── daily_summary.py    # Mid-pilot snapshot
│   ├── PILOT_RUNBOOK.md    # 30-min setup call script
│   ├── pilot_agreement.md  # 1-page agreement template
│   ├── README.md
│   └── integration_samples/
│       ├── mirror_python.py
│       ├── mirror_node.js
│       └── README.md
│
├── marketing/              # Sales artifacts
│   ├── one_pager.html      # PDF leave-behind
│   ├── pricing_calculator.html
│   ├── demo_script.md      # 4-min Loom script
│   ├── outreach_templates.md
│   └── README.md
│
├── .devcontainer/          # Codespaces config
├── CONTRIBUTING.md         # Dev modes (Docker / native)
└── README.md
```

## Quick links

- **Trying it locally?** → `gateway/README.md`
- **Running a pilot?** → `deploy/README.md` + `deploy/PILOT_RUNBOOK.md`
- **Doing outreach?** → `marketing/outreach_templates.md`
- **Recording the demo?** → `marketing/demo_script.md`

## Status

| Component | Status |
|---|---|
| Gateway: routing, caching, fallbacks | ✅ Live |
| Shadow eval: pairwise judge + report | ✅ Live |
| Codespace dev environment | ✅ |
| 200-prompt classifier corpus | ✅ Seed labels by Claude |
| Redis fail-open | ✅ Merged |
| `deploy/pilot.sh` | ✅ |
| Mirror samples (Python + Node) | ✅ |
| Demo script for Loom | ✅ |
| Pricing calculator | ✅ |
| Outreach templates | ✅ |
| 4-min Loom demo recording | ✅ Script ready, recording in progress |
| Real customer pilot | ⏳ Seeking first VPC shadow pilot |

## Engineering Skills Demonstrated

This project showcases a production-ready, full-stack systems engineering architecture:
- **API Gateway Design:** Custom FastAPI reverse proxy handling multi-provider routing (OpenAI, Anthropic, DeepSeek) via LiteLLM.
- **Semantic Caching & Vector Search:** Redis Stack integration with HNSW vector index (RediSearch) for sub-30ms semantic queries.
- **Observability:** Prometheus integration scraping gateway metrics for cost-saved dashboards.
- **Data Persistence:** SQLite database handling multi-tenant keys, SHA-256 key hashing, tenant budget limits, and audit logs.
- **Security & Data Privacy:** Microsoft Presidio integration for PII redaction and VPC-native automated deployment scripting (`pilot.sh`).
- **Data Science & ML Engineering:** Learned bge-small classifier head for dynamic classification/extraction routing.
- **Testing & QA Rigor:** 31 unit tests, 3-judge pairwise LLM-as-a-judge eval framework, and code execution validation harness.

## Project Roadmap

- [ ] Add streaming response support for cache and verifier.
- [ ] Helm Chart for Kubernetes production deployments.
- [ ] Automate tenant-specific classifier retraining from mirrored shadow logs.

## License

Internal. Not open-source. Not for redistribution.
