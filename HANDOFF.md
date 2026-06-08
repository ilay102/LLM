# HANDOFF — paste this into a new Claude chat

**Use:** copy the entire block below into the first message of a fresh Claude
conversation. Then add one line about what you want to work on next.

---

## START COPY ↓

I'm Ilay Lankin (engineering student, Ariel University). I built **VIREN** —
an LLM cost-optimization gateway — with Claude Code over the past 7 days.

**Repo:** https://github.com/ilay102/LLM
**Working dir on Windows:** `C:\Users\ilay1\OneDrive\Desktop\optomizatsion`
**Ship tag:** `v0.2.2` on `main`
**Active branch:** `v0.3.4-conversation`
**Latest commit:** `f634aa4`

## What VIREN does (one line)

OpenAI-compatible gateway that classifies each request, routes it to the right
model tier (cheap / balanced / frontier), caches semantically, redacts PII, and
proves quality with a 3-judge eval.

## Verified numbers (real, reproducible, in the repo)

- **87%** cost reduction (3-judge ensemble on 30-prompt corpus, $5 in API)
- **90%** factually equivalent or better (regression split — factual vs stylistic)
- **100%** code-gen pass rate at **79%** lower cost vs direct Sonnet
  (20 prompts: Python *actually executed*, JS syntax-checked, SQL structural)
- **<250ms** added p95 routing latency, *faster than direct Sonnet at median*
- **62/62** unit tests passing, GitHub Actions CI, self-test 6/6 green
- `pilot.sh` deploys cleanly in a fresh Codespace

## Tech stack

Python 3.11 + FastAPI + LiteLLM + Redis Stack (HNSW vector cache) + SQLite
(multi-tenant + event log) + Microsoft Presidio (PII) + bge-small embeddings
(classifier). Docker Compose. Tested in GitHub Codespaces.

## What's shipped (v0.2.2)

- Multi-tenant SQLite-backed auth (sha256 keys, per-tenant budget cap +
  min_tier floor + model allowlist)
- PII redaction before any cache write
- Semantic cache w/ fail-open on Redis outage
- Cascade verifier (heuristic — LLM verifier mode parked)
- Provider routing: Anthropic Haiku/Sonnet/Opus-4.8 + OpenAI gpt-4o-mini +
  DeepSeek V4-Flash/Pro/R1
- Prometheus `/metrics` endpoint
- Per-call structured logging (SQLite + JSONL)

## What's parked (with reasons in COMPARISON.md)

- **LLM cascade verifier** — gate showed -6.7pp W-T on cheap-heavy traffic.
  Defaults to safe heuristic mode.
- **Prefix-cache + tier stickiness (v0.3 safe-wins)** — gate showed 75% W-T
  on 60-prompt corpus, 3pp below 78% floor. Stylistic regressions, not
  factual. Will re-test on real pilot traffic.
- **Per-tenant adaptive classifier** — framework exists, needs real traffic.

## Sales asset map (all in `marketing/` unless noted)

| File | Purpose |
|---|---|
| `MASTER_QA.md` | The single study doc — 60-sec pitch, FAQ, sales principles, Plan B |
| `EVENT_READINESS.md` | Master checklist + "what to say out loud" |
| `marketing/booth_poster.html` | A3 booth poster |
| `marketing/qr_cards.html` | 10 QR cards per A4 |
| `marketing/pitch_deck.html` | 12 HTML slides, arrow-key navigation |
| `marketing/one_pager.html` | Branded PDF leave-behind |
| `marketing/landing_page.html` | Public landing page |
| `marketing/demo_dashboard.html` | Live interactive demo (laptop tab 1) |
| `marketing/cfo_dashboard.html` | Live $-savings poller (laptop tab 2) |
| `marketing/security_onepager.md` | Security & data handling explainer |
| `marketing/discovery_call.md` | 15-min qualification script |
| `marketing/outreach_templates.md` | 11 cold-message templates |
| `marketing/EVENT_PLAYBOOK.md` | Booth day-of logistics |
| `scripts/regression_split.html` | The "90% factually equivalent" receipts |
| `scripts/code_quality_report.html` | The "100% / 79%" code-gen receipts |
| `scripts/LATENCY_MEMO.md` | Real measured latency overhead |
| `scripts/evidence_pack.html` | One PDF with all receipts inlined |
| `scripts/build_evidence_pack.py` | Generates per-prospect evidence pack |
| `COMPARISON.md` | Full multi-version eval history |
| `PRODUCT_STATUS.md` | Honest "what's verified / what's not" |

## Constraints I'm working under

- **Two-person team:** me (eng + sales) + a partner (sales only, no coding)
- **Budget:** ~$11 spent on API so far, $1 cushion. Don't recommend
  expensive experiments without ROI math.
- **Time-pressure:** high-tech companies visiting my university soon — the
  pitch needs to be event-ready, not enterprise-ready.
- **My laptop is weak** — code runs in GitHub Codespaces, not locally. I
  pair with Claude Code in the Codespace for execution work.
- **No SOC 2 yet** (disclosed honestly in security one-pager).

## How I work

- Honest > optimistic. Receipts > vibes. Measurement > intuition.
- Park what doesn't beat its gate. Tag what does.
- Don't add more numbers if existing ones aren't yet proven on real
  customer traffic.

## What I need from this new chat

[Replace this line with what you actually want to work on next.]

## END COPY ↑

---

## What to do with this file

- **Don't edit it without re-syncing the numbers.** If a new eval changes
  87%/90%/100%/79%/250ms, update them here first.
- **Refresh it on each major release.** v0.3.0, v1.0, etc.
- **The new chat will not have access to this conversation's history.**
  Anything not in HANDOFF.md or the repo is lost to the new chat. So
  everything important should already be in code/docs (which it is).

## Tips for the new chat

1. **First message = this whole handoff + your specific ask.** Don't
   spread context over 5 messages — load it all at once.
2. **Reference file paths, not concepts.** "Read `MASTER_QA.md` Part 5"
   beats "the sales principles we discussed."
3. **The new chat won't know which experiments we already tried.** When
   you suggest something, it might re-propose the LLM verifier or prefix
   caching. Reference `COMPARISON.md` and `PRODUCT_STATUS.md` to show
   what's parked and why.
4. **Bring screenshots if helpful.** New chat sees what you paste, not
   what your terminal showed earlier.
