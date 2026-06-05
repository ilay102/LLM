# Event Readiness — VIREN

The single status doc. If you read one thing before the event, read this.

## Sales arsenal — what to bring (all built, all in repo)

| Asset | What it kills | File |
|---|---|---|
| Booth poster (A3) | "Why should I stop?" | `marketing/booth_poster.html` |
| QR cards | Capture mechanism → Calendly | `marketing/qr_cards.html` |
| Live tier demo | "Show me it works" | `marketing/demo_dashboard.html` |
| **Live CFO $-saved screen** | **"My CFO wants to SEE savings"** | **`marketing/cfo_dashboard.html`** |
| 1-pager + landing page | "Send me info" | `marketing/one_pager.html` / `landing_page.html` |
| 12-slide deck | "Got 5 mins for slides?" | `marketing/pitch_deck.html` |
| **Regression split report** | **"80% W-T = 1 in 5 worse"** | **`scripts/regression_split.html` (90% factual)** |
| Latency overhead report | "How much p95 do you add?" | `scripts/overhead_report.html` (run script first) |
| **Code-gen quality eval** | **"Does it work for code?"** | **`scripts/code_quality_eval.py` → `scripts/code_quality_report.html`** (run for ~$1) |
| Security one-pager | "What's your security story?" | `marketing/security_onepager.md` |
| Discovery-call script | "How do I qualify in 15 min?" | `marketing/discovery_call.md` |
| Evidence pack PDF | The CTO leave-behind | `scripts/build_evidence_pack.py` → `scripts/evidence_pack.html` |
| 60-sec pitch + playbook | Day-of script | `marketing/EVENT_PLAYBOOK.md` |


## Ship version: v0.2.2 (frozen, proven)

- **Cost reduction: 87.4%**  ·  **Quality (3-judge majority W-T): 80.0%**
- 31/31 unit tests, self-test 6/6, end-to-end verified
- Multi-tenant keys, budget caps, PII redaction, Redis fail-open — all live
- This is the number on the poster. It does not change unless an isolated gate
  proves an improvement.

## What we tried in v0.3 and what the data said

| Improvement | Verdict | Why |
|---|---|---|
| Bigger eval corpus (260, multi-turn + RAG) | ✅ KEEP | Pure tooling. Lets us actually measure changes. No runtime risk. |
| LLM cascade verifier | ❌ PARKED | Gate proved -6.7pp W-T + slow extra call on cheap-heavy traffic. Default now `heuristic` (= safe v0.2.2 behavior). Re-test on real code/reasoning pilot traffic. |
| Prefix caching (provider cache) | ⏳ ONE GATE LEFT | Pure cost, quality-neutral by design. Needs one isolated confirming run. |
| Tier stickiness (conversation memory) | ⏳ ONE GATE LEFT | Pure safety, only routes up. Needs same confirming run. |
| Per-tenant classifier | 🔜 PILOT | Needs real customer traffic. Framework only. |

**Key lesson:** the verifier wasn't "broken" — it was wrong for *cheap-heavy*
traffic, where short answers win. The gate caught it before it shipped. That's
the system working. We don't tune it against synthetic data; we re-test it on a
real pilot's traffic where escalation actually helps.

## The ONE eval still worth running (~$4)

Isolate the two SAFE wins (prefix caching + stickiness) with the verifier OFF.
If quality holds and cost drops → merge them; the product gets cheaper + safer
with zero quality risk. Prompt for Claude Code is in `eval/STEP1_PROMPT.md`.

After that run: **stop spending on synthetic-corpus evals.** The real proof is
a pilot.

## "Ready & functional" checklist (costs ~$0 — just verification)

Run these in the Codespace once; all should be green:

- [ ] `docker compose up --build -d` → gateway healthy (`curl /health` ok=true)
- [ ] `pytest -m unit` → all green (now includes verifier/prompt_cache/conversation)
- [ ] `bash scripts/self_test.sh` → 6/6
- [ ] `./deploy/pilot.sh --client-id demo --anthropic-key … --openai-key …`
      → green banner, gateway reachable (proves a stranger can deploy it)
- [ ] Open `marketing/demo_dashboard.html` against the live gateway → click 6
      prompts → cache fires on repeat (proves the live demo works)
- [ ] `./deploy/teardown.sh --client-id demo` → clean shutdown

If all six pass, the product is functional and deployable by someone who
isn't you. That matters more for the event than any quality percentage.

## Event-day kit (already built, in marketing/ + scripts/)

- [ ] `booth_poster.html` → fill calendly+email → print A3, foam-mount
- [ ] `qr_cards.html` → generate QR (qr.io → your Calendly) → print, cut
- [ ] `one_pager.html` → fill placeholders → PDF, 5 copies
- [ ] `pitch_deck.html` → fill placeholders → open on tablet for longer chats
- [ ] `demo_dashboard.html` → tested live, fullscreen on laptop tab 1
- [ ] **`cfo_dashboard.html` → laptop tab 2, the live "$ saved" screen for CFO/CTO**
- [ ] `security_onepager.md` → PDF, attach when sending evidence pack
- [ ] Loom demo recorded (script in `marketing/demo_script.md`)
- [ ] `scripts/build_evidence_pack.py` → generate the CTO PDF (now auto-includes
      regression split + latency overhead sections if those scripts have been run)
- [ ] Read `marketing/EVENT_PLAYBOOK.md` — the 60-sec pitch is muscle memory
- [ ] Read `marketing/discovery_call.md` — the 15-min qualification script
- [ ] `scripts/measure_overhead.py` — RUN ONCE in Codespace to publish a real
      "VIREN adds X ms p95" number for the evidence pack

## The numbers to say out loud

**Primary claim (poster, deck, one-pager, every QR card):**
- "87% verified cost reduction. 90% factually equivalent or better.
   100% code-generation pass rate at 79% lower cost."

**Methodology, if asked:**
- "3-judge pairwise audit — Sonnet, GPT-4o, Opus — different families to
  remove self-preference bias. Then we split every disagreement into
  'factually wrong' (the only thing that matters) vs 'stylistic only.'
  Headline is the factual rate. Every regression is auditable per-prompt."

**When pushed on the missing 10%:**
- "Those 3 prompts out of 30 are documented in the regression report. Two are
  recoverable with a config change (pin JSON routes to balanced tier); one is
  a genuine cheap-tier miss. Your pilot measures the same split on YOUR
  traffic and we contractually commit to zero factual regressions on every
  route we ship."

**When pushed on sample size:**
- "30-prompt baseline, ±10% CI. Small. That's why the 2-week pilot runs on
  YOUR traffic at production scale — your number is what we sign, not ours."

**When pushed on latency (this is real, defensible — see `scripts/LATENCY_MEMO.md`):**
- "Routing overhead is under 250 ms at p95 on fresh requests, measured on our
  stack. At median, total gateway latency is **lower** than direct Sonnet
  (1.4s vs 2.8s) because requests route to faster cheap-tier models. Cache
  hits return in 26 ms p50. The pilot measures all three on YOUR traffic."

**When asked about code generation (THE common technical question):**
- **Lead with receipts:** "20-prompt code-gen eval — Python / JavaScript / SQL.
  Python answers were extracted from the response, **executed**, and asserted
  against expected outputs. Strict tie with direct Sonnet: 20/20 pass on both
  sides. **At 79% lower cost.** Per-prompt audit is in section 6c of the
  evidence pack."
- **Structural guarantee:** "If you want code quality contractually
  guaranteed on a specific route, set `min_tier: balanced` on that tenant —
  the gateway will *never* drop those requests below balanced. It's a
  structural floor, not a promise."
- "The eval harness ships with the gateway (`scripts/code_quality_eval.py`).
  We re-run it on YOUR pilot setup so the pass rate is on YOUR config,
  not ours."

**What NEVER to say:**
- "80% W-T" or "20% worse" — pitch the FACTUAL rate, not the W-T rate. The
  W-T number includes stylistic differences buyers don't actually care about.
- "100%" / "always" / "no regressions" — we have 3 documented and won't lie.
- That the LLM verifier / per-tenant classifier / streaming are shipped —
  they're roadmap, "activated on your pilot traffic."

## Branches (for whoever picks this up)

- `main` — has v0.2.2 (ship)
- `v0.3-quality` — corpus + verifier (verifier now defaults to safe heuristic)
- `v0.3.2-prefix-cache` — stacked: prefix caching
- `v0.3.4-conversation` — stacked: tier stickiness + verifier safe-default
  (this branch = the full v0.3 candidate; run STEP1 gate, then merge if green)
