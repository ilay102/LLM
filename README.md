# VIREN — LLM Cost Optimization Gateway

OpenAI-compatible gateway that routes, caches, and proves quality —
designed for 2-week shadow pilots that close design partners.

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
| 4-min Loom demo recording | ⏳ Person A records |
| Real customer pilot | ⏳ Person B closes |

## Team split

- **Person A — Builder.** Owns gateway, deploy, demo recording.
- **Person B — Hustler.** Owns outreach, calls, pilots, customer relationship.

## Next 14 days

| Person A | Person B |
|---|---|
| Test `pilot.sh` end-to-end | Polish LinkedIn profile, set up Calendly |
| Record the 4-min Loom | Send 15 LinkedIn requests/day |
| Export `one_pager.html` to PDF | Run discovery calls (target 5-8) |
| Be ready to deploy pilot in <2 hours | Sign first pilot agreement by Day 14 |

## License

Internal. Not open-source. Not for redistribution.
