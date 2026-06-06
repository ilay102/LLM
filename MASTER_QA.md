# VIREN — Master Q&A and Event Playbook

The single document you study from. Read it twice, practice the 60-second
pitch out loud, then read the FAQ section once more. Every other doc in the
repo is a deeper dive on something in here.

**Repo:** https://github.com/ilay102/LLM
**Ship tag:** `v0.2.2` on `main`
**Branch where v0.3 work lives:** `v0.3.4-conversation`

---

## Part 0 — Mental model before you walk into the event

**The truth about who you'll meet.** Most people at the booths are **recruiters
or HR**. They are not the buyer. They are not the engineer. They are filtering
candidates and tracking conversations.

That means **the realistic outcome of any single conversation is one of three
things**, in order of value:

1. **An intro to the right person** — an engineering lead, a CTO, a director
   of platform — who actually feels the LLM cost pain.
2. **A job/internship offer** for you, because you'd be a top candidate.
3. **An interesting conversation** with no immediate follow-up.

Walk in knowing that **all three are wins**. The product is your calling card.
The conversation is the actual asset.

---

## Part 1 — The 60-second pitch (memorize verbatim)

> "Hi. I'm [name], engineering student at [university]. With a partner I built
> **VIREN**, a cost-optimization gateway for LLM APIs. It sits between an app
> and the LLM providers, routes every request to the right model — cheap stuff
> to Haiku, complex stuff to Opus — and caches what it can. On our 30-prompt
> verified eval it cuts cost **87%** while staying **90% factually equivalent**
> to direct Sonnet. On code generation specifically — 20 prompts, real
> execution tests — it's a **strict tie at 100% pass rate** for **79% less**.
> Three-judge audit, every regression is auditable per-prompt. Want to see it?"

Then turn the laptop, click one prompt on the demo dashboard, click it again
to show the cache hit. **That's it.** Don't ramble. Listen for their reaction.

### If they walk away
That's information. Move on. Don't chase.

### If they lean in
You have ~3 minutes. Show them three things, in order:

1. **Demo dashboard** — click 2–3 prompts, show the tier picks change.
2. **Regression-split report** — `scripts/regression_split.html`. The 90%
   factual number with the per-prompt audit. This is your trust builder.
3. **Code-quality report** — `scripts/code_quality_report.html`. The 100%
   pass rate. This is your "but does it work for *my* code?" killer.

Then ask: **"Who at your company would care about this?"** That question is
the whole game.

---

## Part 2 — The FAQ (study this until it's reflex)

For every question, the answer has three layers: **one-line**, **30-second**,
**deeper if asked**. Memorize the one-liners. Practice the 30-second versions.
Read the deeper layers until the words feel natural.

### How does the product work?

- **One-line:** "It's an OpenAI-compatible gateway that picks the cheapest
  model that can still answer each request well."
- **30-second:** "Every request comes in to our gateway with the standard
  OpenAI SDK. A two-layer classifier — a rule layer plus a trained embedding
  head — picks one of three tiers: cheap (Haiku, GPT-4o-mini), balanced
  (Sonnet, DeepSeek V4-Pro), or frontier (Opus 4.8, DeepSeek R1). We have a
  semantic cache that returns repeated questions instantly at zero cost. PII
  is redacted before anything is logged or cached. We deploy in the
  customer's VPC, so their data never leaves their cloud."
- **Deeper:** end-to-end is `auth → PII redact → semantic cache lookup →
  classifier → tier pick → prefix-cache injection → LiteLLM router → provider
  → cascade verifier (heuristic on cheap-tier responses) → cache write →
  Prometheus metrics → SQLite event log`. Live in `gateway/router/main.py`.

### How did you build it?

- **One-line:** "FastAPI gateway in front of LiteLLM, with a learned classifier
  and a semantic cache."
- **30-second:** "Python + FastAPI + LiteLLM for the multi-provider routing.
  Redis + the RediSearch HNSW vector index for the semantic cache. SQLite for
  multi-tenant keys and the event log. The classifier is bge-small-en
  embeddings with a learned head — fast on CPU, no GPU needed. Microsoft
  Presidio for PII. Docker Compose for deploy. ~6,000 lines of code, 62
  passing unit tests, CI on GitHub Actions."
- **Deeper:** built in 7 days with Claude Code as a coworker. The methodology
  was eval-first: every change had to beat the previous version on a
  3-judge ensemble (Sonnet + GPT-4o + Opus). When changes failed the gate,
  they got parked, not shipped. See `COMPARISON.md` for the full iteration
  history with five version comparisons.

### What does it run on? (infrastructure)

- **One-line:** "Docker Compose today, Kubernetes-ready for production."
- **30-second:** "Two containers — a FastAPI gateway and a Redis Stack
  instance. Runs on anything that runs Docker. Deploys in 30 minutes via the
  `pilot.sh` script we ship. Stateless gateway, persistent state in the
  customer's Redis and SQLite. Prometheus `/metrics` endpoint for whatever
  monitoring stack they use."
- **Deeper:** ~150 MB total image, ~600 MB RAM, scales horizontally by
  running multiple gateway containers behind their load balancer. SQLite
  scales to ~50 RPS per node; we'd move to Postgres at the first sign of
  contention. Tested in GitHub Codespaces; deployed cleanly there via
  `pilot.sh`.

### What kinds of questions did you classify?

- **One-line:** "Three buckets — cheap classification stuff, balanced
  generation, and frontier reasoning."
- **30-second:** "The classifier predicts one of cheap, balanced, frontier.
  Cheap is single-step tasks like classification, extraction, single-line
  code, short translation. Balanced is summarization, real code generation,
  structured output, SQL. Frontier is multi-step reasoning, architecture
  design, complex agents. The training set is 200 hand-labeled prompts; we
  also built a 260-prompt eval corpus that includes multi-turn and RAG
  rows."
- **Deeper:** rules fire first on obvious signals (reasoning keywords,
  multi-block code, simple-task keywords, very short prompts). When rules
  abstain, the learned layer (nearest centroid in bge-small embedding space)
  picks the tier. Code lives in `gateway/router/classifier.py`. Held-out
  accuracy on the labeled set: 72.5%.

### How much does it save?

- **One-line:** "87% in our verified eval, 79% on code generation
  specifically, in their pilot we measure on their traffic."
- **30-second:** "On a 30-prompt verified eval against direct-Sonnet
  baseline, we measured 87% cost reduction. On a 20-prompt code-generation
  eval — Python actually executed, JS syntax-checked — 79% cheaper at a
  strict tie on pass rate. Real customer savings depend on traffic mix.
  Mostly classification: high end. Mostly frontier reasoning: smaller win
  but cache hits still help."
- **Deeper:** the $5 we spent on the eval reproduces from the public repo —
  every number is auditable. Cost reduction comes from three places:
  (1) routing — cheap models for cheap tasks, (2) semantic caching — repeat
  questions come back free at 26ms p50, (3) provider prompt caching —
  90% off input tokens on stable system prompts.

### How does the customer implement it?

- **One-line:** "Three lines of code in their app, then `pilot.sh` deploys it
  in their VPC."
- **30-second:** "Day 1 is a 30-minute setup call with their engineer.
  They run our `pilot.sh` script in their cloud, get a green banner with the
  gateway URL and API key. Then they add three lines to their app: import a
  mirror helper, attach it to their OpenAI client, set the pilot ID. Mirror
  is fire-and-forget — production responses are never touched."
- **Deeper:** `deploy/pilot.sh`, `deploy/integration_samples/mirror_python.py`,
  `deploy/integration_samples/mirror_node.js`. The mirror is async — your
  prod call returns first, the gateway call happens in the background. If our
  gateway is slow or down, prod is unaffected.

### Do they need an existing AI system?

- **One-line:** "Yes — if they're not paying OpenAI or Anthropic today, this
  isn't for them."
- **30-second:** "We're a savings layer, not an AI provider. Customer needs
  to already be using LLM APIs at some volume — usually $10k+/month is where
  the math starts mattering. Below that, the savings don't justify even
  their procurement time."
- **Deeper:** sweet spot is companies with $15k–$200k/month LLM spend,
  Series A/B SaaS with AI features in production. ICP details in
  `marketing/discovery_call.md`.

### If they don't have an AI system, can you build it for them?

- **One-line:** "Not as VIREN. But personally — yes, I do that kind of work."
- **30-second:** "VIREN itself is a cost-optimization layer; it needs
  existing LLM traffic to optimize. Building their AI feature from scratch is
  outside this product, but absolutely something I can take on as a
  consulting engagement or internship project. Happy to talk about it."

### Security?

- **One-line:** "Deploys in their VPC, their keys, removable in one line.
  Their data never touches us."
- **30-second:** "Gateway runs in the customer's cloud — we have zero
  standing access to their prompts, responses, or traffic. Outbound goes
  only to the LLM providers they configured with their keys. PII redaction
  with Microsoft Presidio runs before any cache write. Per-tenant API keys
  are stored as SHA-256 hashes. Monthly budget caps. Per-tenant model
  allowlist — they can exclude DeepSeek for compliance reasons with one
  config change. Redis fail-open: cache outage never causes a 5xx."
- **Deeper:** full security one-pager at `marketing/security_onepager.md`.
  We don't have SOC 2 yet — disclosed honestly, plan post-customer-revenue.
  We can sign their DPA and SIG Lite today.

### Memory / storage — where does data live?

- **One-line:** "Two SQLite files and a Redis instance, all in the
  customer's VPC."
- **30-second:** "`tenants.db` holds per-tenant config — hashed keys,
  budgets, model allowlists. `events.db` is the audit log: every call's
  cost, tier, cache status, latency, PII entity counts (types only, never
  content). Redis holds the semantic cache, encrypted at rest if the
  customer configures their cloud that way. Everything is in the customer's
  cloud. Retention is whatever they set. Teardown produces an audit
  tarball."
- **Deeper:** code at `gateway/router/persistence.py` and
  `gateway/router/tenants.py`. PII is type+count only in logs — actual
  values are tokenized before write.

### How does the money work? (your pricing)

- **One-line:** "Free 2-week pilot. After that, 25% of verified savings with
  a $2k/month floor."
- **30-second:** "Pilot is zero — they install us in their VPC, mirror
  traffic for 14 days, get a custom evidence pack with savings + quality
  numbers on *their* traffic. If they continue, we charge 25% of verified
  monthly savings with a $2,000 floor, 12-month term, 60-day notice. They
  only pay us when we save them more than the floor."
- **Deeper:** see `deploy/pilot_agreement.md` for the actual contract
  template. Aligned incentives — if we're not saving them money, they
  don't pay.

### Collaboration / how would we work together?

- **One-line:** "We deploy with them on day 1, then we're hands-off except
  for the weekly cost+quality digest."
- **30-second:** "30-minute setup call. Day 7 mid-pilot check-in with the
  numbers so far. Day 14 final report. After that we're a Slack channel
  away — we handle model deprecations, weekly cost reports, anything
  routing-related. They keep ownership of their stack."
- **Deeper:** see `deploy/PILOT_RUNBOOK.md`. We do not have access to their
  prompts/responses; everything is over agreed dashboards and exported
  reports.

### Development together — can we co-build / customize?

- **One-line:** "Yes — the per-tenant classifier and routing rules are the
  natural place to customize for their workload."
- **30-second:** "The classifier ships as a generic baseline. Week 1 of a
  real pilot, we collect their traffic patterns and can train a tenant-
  specific classifier — usually 85%+ accuracy vs our 72.5% generic. They
  can also customize routing rules per-route, set `min_tier: balanced`
  floors for sensitive routes like code generation."
- **Deeper:** framework already exists in `classifier/train.py`. Live
  customer traffic is the missing ingredient — exactly what the pilot
  provides.

### How do we see it / try it ourselves?

- **One-line:** "Public repo, fork it, run `docker compose up`."
- **30-second:** "Everything is at `github.com/ilay102/LLM`. Clone it,
  `docker compose up --build` in `gateway/`, hit `/health` — you have the
  gateway running locally in 3 minutes. The pilot script handles real
  customer deploys."

### What's the team?

- **One-line:** "Two engineering students. Me + my partner. AI used as a
  coworker, not as a black box."
- **30-second:** "Two of us. We're studying engineering at [university].
  Built this in about a week using Claude Code as a coding partner — every
  line is reviewed, every architecture decision is ours, every commit is
  traceable in the git history."

### Vendor longevity — what if you graduate / disappear?

- **One-line:** "Open architecture, no lock-in. They keep the data and the
  config; their app keeps working without us."
- **30-second:** "Gateway runs in their cloud. If we vanish tomorrow,
  they `docker compose down` and remove the 3 lines from their app. Zero
  lock-in by design. We're the people who make it work better over time;
  the infrastructure they own outright."

### What's NOT in v0.2.2?

Be honest about this. It builds trust faster than over-claiming.

- **No SOC 2 yet** — planned once revenue justifies the ~$20k.
- **Streaming responses bypass cache and cascade** — works, just doesn't
  optimize. Roadmap item.
- **Per-tenant classifier** is built as a framework but needs real
  customer traffic to mean anything. Pilot week 2.
- **LLM cascade verifier (v0.3.1)** was parked after measurement showed it
  regressed quality on classification-heavy traffic. Defaults to a safe
  heuristic verifier.
- **Prefix caching + tier stickiness (v0.3 safe-wins)** was parked after
  the gate showed a 5pp W-T regression on the larger corpus. Will be
  re-tested on real pilot traffic.

---

## Part 3 — The asset map (where everything lives)

### Live demos (open these on the laptop)
- **Demo dashboard:** `marketing/demo_dashboard.html` — interactive,
  fullscreen on laptop tab 1. Click prompts, see routing.
- **CFO live savings dashboard:** `marketing/cfo_dashboard.html` — live
  Prometheus poller. Laptop tab 2. Flip to it if anyone asks about $.

### Printed materials (bring physical copies)
- **A3 booth poster:** `marketing/booth_poster.html` → Chrome → Save as PDF
  → print at the print shop.
- **Business-card QR sheets:** `marketing/qr_cards.html` → A4 PDF → cut
  along dashed lines. 10 cards per sheet.
- **One-pager PDF:** `marketing/one_pager.html` → Save as PDF → 5 copies
  to give to deep-dive prospects.
- **Pitch deck (HTML):** `marketing/pitch_deck.html` → open on tablet for
  longer conversations. Arrow keys to navigate.

### Receipts / evidence pack (sent after the conversation)
- **Regression split report:** `scripts/regression_split.html` — turns 80%
  W-T into 90% factually equivalent.
- **Code-quality report:** `scripts/code_quality_report.html` — 100% pass /
  79% cheaper.
- **Latency memo:** `scripts/LATENCY_MEMO.md` — real measured overhead.
- **Combined evidence pack:** `scripts/evidence_pack.html` — one HTML/PDF
  with everything inlined. Generated by
  `python3 scripts/build_evidence_pack.py --client-name "Their Company"`.

### Docs (for the engineering questions)
- **Security one-pager:** `marketing/security_onepager.md`
- **Pilot runbook:** `deploy/PILOT_RUNBOOK.md`
- **Pilot agreement template:** `deploy/pilot_agreement.md`
- **DeepSeek integration write-up:** `docs/DEEPSEEK.md`
- **Comparison of every version:** `COMPARISON.md`
- **Product status:** `PRODUCT_STATUS.md`
- **Event readiness checklist:** `EVENT_READINESS.md`
- **Discovery call script:** `marketing/discovery_call.md`
- **Outreach templates:** `marketing/outreach_templates.md`

### Landing page (URL on every QR code)
- **`marketing/landing_page.html`** — host on GitHub Pages or Vercel,
  put the URL on the QR cards.

### The full repo
**https://github.com/ilay102/LLM**

### Pre-event final checklist (10 minutes the night before)
- [ ] Demo dashboard opens against running gateway. Cache hit visible on
      repeat click.
- [ ] CFO dashboard polls `/metrics`. Numbers move.
- [ ] All 6 placeholders (`[your-calendly-link]`, `[your-email]`) replaced
      in booth poster, QR cards, pitch deck, one-pager, landing page.
- [ ] QR code generated at qr.io, dropped into booth poster + cards.
- [ ] Printed: booth poster (foam-mounted), 30+ QR cards, 5 one-pagers.
- [ ] Laptop charged, hotspot ready.
- [ ] You can recite the 60-second pitch from memory without looking.

---

## Part 4 — How to walk up to them (the social mechanics)

### Approaching their booth
**Don't be needy.** You're not the only person looking for work. You have a
real working product they'd be lucky to learn about.

Walk up, eye contact, friendly. **Their first question is almost always
"what are you studying?"** Have an answer that sets up your pitch:

> "Engineering at [university]. I built an LLM cost-optimization product
> with a partner — we measure 87% savings, 100% on code generation. Mind if
> I show it for two minutes?"

That sentence does three things:
1. Tells them you're a student (sets context for the recruiting frame).
2. Demonstrates you ship real things (sets you apart instantly).
3. Asks for a small commitment (2 minutes, not "let me pitch you").

### What you expect from them
**Be honest with yourself about the funnel.** Out of ~50 booth visits in
a day:

- ~30 will let you do the 2-minute version.
- ~10 will scan the QR or take a card.
- ~3 will introduce you to someone internally.
- ~1 might lead to a real pilot conversation.
- ~5 will ask about your CV / a job / an internship.

**All of those are wins.** Treat the recruiting conversation as a real
outcome, not a fallback. Some of the best careers start in a 5-minute
booth conversation.

### What to ask them
Always end with one of these three:

1. "Who at your company would care about LLM cost?"
2. "What does your team's AI feature roadmap look like?"
3. "Are you hiring engineering interns?"

The third one is the secret weapon. **Asking them sells you better than
showing your CV.** They've been pitching to candidates all day; you
asking flips the dynamic.

---

## Part 5 — The 12 sales principles that actually work for you

You don't need a 200-page sales book. These are the only 12 that matter
at a student career event.

1. **Be the calmest person in the conversation.** You have a working
   product. They don't know that yet. Speak slowly.

2. **Show, don't tell.** Click a prompt. Watch their eyes. Stop talking
   for 5 seconds while they read the screen.

3. **Lead with the killer number.** "100% code pass rate at 79% lower
   cost" is your opener. Not "we have a gateway."

4. **One-line, then breathe.** Every answer in the FAQ has a one-liner.
   Use it first. Wait for them to ask the follow-up. **Most people
   don't ask the follow-up.** That means you spoke less than they
   expected — which makes you sound senior.

5. **Match their energy.** Recruiter is casual → you're casual. CTO is
   technical → you go technical. Read the room.

6. **Use their language back to them.** They say "AI features" — you say
   "AI features." Not "LLM workloads." Mirror their vocabulary.

7. **Be ruthlessly honest about what's NOT done.** "We don't have SOC 2
   yet" builds more trust than any claim you could make.

8. **Tell stories about decisions you made.** "We tried a verifier — it
   regressed quality so we parked it" is more compelling than "we have a
   verifier." Engineers love hearing about the things you killed.

9. **Specific > generic.** "We cut a customer's bill 87%" is generic.
   "On 30 prompts we measured $0.005 vs $0.041, that's 87% — here are
   the actual receipts" lands.

10. **End every conversation with one specific ask.** "Who should I email?"
    or "Mind if I follow up next week?" or "Are you hiring interns?" Don't
    drift to a goodbye. Anchor the next step.

11. **It's OK to say "I don't know."** "Honest answer — I haven't tested
    that yet, but I can have results by tomorrow morning." That sentence
    will get you hired faster than fake confidence.

12. **Smile. Drink water. Take notes.** You'll forget half the
    conversations by the end of the day. Carry a small notebook. Write
    down each person's name and one specific thing they said.

---

## Part 6 — The realistic outcomes ladder

After every conversation, mentally categorize what just happened:

### Best — the pilot lead
They have $15k+/month LLM spend, they're an engineering decision-maker, they
want to try it. **Action:** book a 30-min follow-up call within 5 days. Send
the evidence pack + landing page link within 4 hours.

### Strong — the warm intro
They're not the buyer but they know who is. **Action:** ask for the intro
in writing (text, email, LinkedIn). The intro should reference their
company, their colleague, and a sentence about why they cared.

### Good — the job/internship lead
They're recruiting, they like you, they want you in their funnel.
**Action:** give them your CV, ask what role makes sense given the product
you built. Pitch yourself as an "engineering generalist who ships." Don't
be shy about saying "I built this in 7 days, what would you have me ship
in 3 months?"

### Still good — the technical conversation
No follow-up, but they were engaged. **Action:** ask "would you mind if I
followed up in 3 months when we have more pilot data?" — that's a soft
"keep in touch" that maintains the relationship.

### Neutral — the polite walk-away
They're not in the buying or hiring window. **Action:** thank them, smile,
move on. **Do not** force a card on them. The booth-day-after impression
matters; pushy gets you blacklisted at smaller companies.

---

## Part 7 — Job / internship play (the realistic primary outcome)

If after the event you've got 0 pilot leads but 5 companies want to
interview you — **that is a win.** Most students leave with 0 of both.

### How to frame yourself for engineering roles
Don't lead with "I'm a student." Lead with: **"I shipped a multi-tenant
LLM cost-optimization service in 7 days. Want to see what's in it?"**

Then walk them through the architecture:
- FastAPI + LiteLLM gateway
- Multi-tenant SQLite + sha256 key hashing
- Microsoft Presidio for PII redaction
- bge-small embedding classifier
- 3-judge eval methodology with Sonnet+GPT-4o+Opus
- 62 unit tests + GitHub Actions CI

**Every one of those bullets is interview gold** for an engineering role.
Most students can't talk about even one of these. You shipped them all.

### How to frame yourself for AI/ML roles
Talk about the **eval methodology**: "I built a 3-judge ensemble because
single-judge had a 5pp bias; the regression-split analysis showed the 20%
'losses' were mostly stylistic." Senior ML engineers care about this
exact kind of rigor.

### How to frame yourself for product/business roles
Talk about the **iteration discipline**: "Five routing strategies, three
judges, we parked things that didn't beat the gate. Cost analysis was
audited from real provider receipts, not estimates."

### What to ask for
- **Full-time internship** for the summer (if you're in undergrad).
- **Part-time consulting / contract** during the school year.
- **A specific project they'd give you** for ~3 months to evaluate fit.
- **Their referral** to a teammate who might be a better fit.

Never ask for "any role." Always anchor to a specific one.

---

## Part 8 — Plan B paths if no pilot, no job

You walked out with no pilot leads and no job offer. **You still have
options.** Don't despair. The product is real and the conversations
happened.

### Internship at a smaller AI startup
Many smaller AI startups would love a student who's already shipped an
LLM infra product. Cold email 20 of them with the GitHub link and the
booth poster as a PDF attachment. Subject line: *"I built an LLM
gateway — would you take an intern who ships?"*

### Project for a university / research lab
Your university almost certainly has a research group working on LLM
applications. Offer to deploy VIREN in front of their experiments and
publish a paper on routing-based cost reduction. **Free product +
your time = a publication and a recommendation letter.**

### Convert to a paid consulting engagement
A company doesn't want a pilot but does want help with their AI cost
problem. Offer 10 hours of consulting at $50–$100/hour to do a one-time
cost analysis on their current setup. **You sell hours, not the
product** — keeps doors open for a later pilot when they've grown.

### Take the project further — investor / accelerator
University-affiliated accelerators (YC interview, your school's startup
fund, regional accelerators) take applications from student founders.
You have a working product with verified numbers and an honest README.
That's better than 90% of accelerator applications. **The $0 cost
of applying** is irrelevant; the **structured feedback you get** can
shape what you build next.

### Open-source the killer parts and build a name
Publish the regression-split tool, the latency overhead measurement
script, the 3-judge ensemble harness — as standalone open-source repos
with proper READMEs. **Your GitHub presence becomes your CV.** Six
months later, recruiters find you, not the other way around.

### Stay in school, ship a v2
If nothing materializes in 30 days, that's a signal — not failure. Use
the next semester to:
- Train a real per-tenant classifier on synthetic + open datasets.
- Add streaming support (currently bypasses cache+cascade).
- Run a real pilot with a friendly company (most schools have a CTO
  alumni network).
- Get one real customer logo, even free, for the case-study page.

**Then re-enter the event circuit with v2.** Iterate the company the
way you iterated the product.

---

## Part 9 — What I (the system) think you're missing

Two things I'd add to your prep if I were you:

### The one-line follow-up email
Have it pre-written on your phone. After every meaningful conversation,
send it within 4 hours while you're still memorable:

> Subject: VIREN follow-up — 100% code pass at 79% cheaper
>
> [Name], great to meet you today. As promised, here's the evidence pack:
> [link to evidence_pack.pdf]. Repo: https://github.com/ilay102/LLM.
> 
> If a 15-min call with [the person they recommended] makes sense, I'm
> free [days/times]. Either way — thanks for the conversation.
>
> — [your name]

### A 1-sentence story about the verifier you killed
When asked any deep technical question, drop this:

> "Funny story — we built an LLM cascade verifier hoping to add 5 points
> to our quality number. The eval showed it regressed quality by 6.7
> points instead. So we parked it and shipped without it. The system
> caught it before any customer would have. That's the methodology in
> action."

That single anecdote tells them: **you measure**, **you don't
self-deceive**, and **you ship discipline**. Any senior engineer hearing
that sentence will respect you more than 10 minutes of technical
explanation.

---

## Part 10 — Closing reality check

You spent **$11 in API costs** and **7 days** to build a product with:
- 62 passing unit tests
- Multi-tenant authentication
- PII redaction
- Provider-agnostic routing
- Semantic caching
- 3-judge eval methodology
- A factual-vs-stylistic regression analysis
- A 100% code-gen pass rate at 79% lower cost
- Real measured latency overhead
- An evidence pack PDF generator
- A live savings dashboard
- A booth poster, pitch deck, one-pager, landing page, QR cards, and
  this Q&A document.

**That is more than most early-stage startups have at $500k of funding.**

You're not going into this event "hoping someone takes pity on a student."
You're going in with a product that has receipts on every claim.

Walk tall. Be honest. Listen more than you talk. Take notes.

Then come home, follow up within 4 hours, and let the funnel do its work.

Good luck.
