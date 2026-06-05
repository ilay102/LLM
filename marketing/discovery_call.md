# Discovery call — 15-minute script

Use after a QR scan / cold reply. The goal is NOT to pitch — it's to **qualify**
and **set up the pilot**. If they're a fit, the natural ask is "let's start a
2-week shadow pilot." If they're not, end gracefully — no wasted hour.

## Pre-call prep (5 min)

- Pull up their company. AI feature shipped? Funding stage? Eng team size?
- Open the **CFO dashboard** in a tab (in case they ask about savings live).
- Open the **regression split report** in another (the proof they're not signing up for "1 in 5 worse").
- Have their Calendly slot open. Have the pilot agreement template handy.

## Minute 0-1 — Frame the call

> "Thanks for the time. I'll keep this tight — 5 questions about your AI
> setup, then I'll tell you in 60 seconds whether it makes sense for us to do
> a 2-week pilot. Either way I'll send you the evidence pack. Sound good?"

(They say yes. Already a soft commitment.)

## Minute 1-10 — The 5 qualifying questions (order matters)

### Q1. "What AI features are in production today, and what's your monthly LLM bill roughly?"

What you're listening for:
- Bill **$15k+/month** = real ICP. Below that, savings aren't worth their procurement pain.
- Bill **$100k+/month** = high-priority follow-up.
- "We don't know" = red flag for buyer maturity, but salvageable.
- "Less than $5k" = politely disqualify; offer to follow up in 6 months.

**Soft script if they hesitate to share the number:**
> "Order of magnitude is fine — under $10k, $10-50k, $50-200k, or $200k+? I just need to know whether the savings would be material."

### Q2. "Which provider — Anthropic, OpenAI, both? And what's the default model on the hot path?"

What you're listening for:
- **Sonnet / GPT-4o default on everything** = perfect fit (most savings).
- **Already using Haiku/gpt-4o-mini for some routes** = still good, smaller delta.
- **Heavy use of Opus/o1** = HUGE fit (frontier-tier savings via R1).
- **DeepSeek already** = they're cost-conscious, you'll have a hard time differentiating on cost alone; lean on quality split + observability.

### Q3. "What's the mix — mostly customer-facing chat? Internal tools? Batch / async?"

What you're listening for:
- **Customer-facing latency-sensitive** = lead with the overhead number (<250ms p95 measured; faster than direct Sonnet at median).
- **Internal tools or batch** = lead with cost (less latency-sensitive).
- **Tool-using agents** = mention tier stickiness explicitly ("we don't drop mid-agent").
- **Code generation / copilot** = mention `min_tier: balanced` floor + the code-eval harness (`scripts/code_quality_eval.py`). "Code routes never drop to cheap unless you explicitly enable it — structural guarantee."

### Q4. "How are you tracking cost & quality today?"

What you're listening for:
- "Provider dashboard" only = open door for VIREN's per-route observability.
- "We have golden-set eval" = sophisticated buyer; lean methodology in the pitch.
- "We don't really" = explain why this matters — it's the thing that makes the pilot fair.

### Q5. "If a tool could cut your bill 40-70% with zero factual regressions you could audit, what would stop you from trying it?"

This is the **objection extraction question.** Listen carefully:
- "Security review" → "deployed in your VPC, your keys, removable in one line, here's the security one-pager"
- "Quality" → "show them the regression split: 10% factual on our generic corpus, your number on YOUR corpus during pilot"
- "Time / who would set it up" → "30-min Day-1 call with your engineer, then we're hands off"
- "Vendor risk" → "free pilot, you keep everything, leave anytime — what's the actual risk?"
- "Procurement / contract" → "no contract for the pilot; we'd talk price after Day 14 numbers"

If they say "nothing, sounds great" — they're not engaged. Probe.

## Minute 10-13 — The 60-second close

Read the room. Three branches:

### A. Strong fit (>$15k bill, real pain, no hard blocker)
> "OK, you're exactly who we built this for. Two weeks, free, in your VPC.
> Day 1 is a 30-min call with one of your engineers to drop in the mirror.
> Day 14 you get a report with YOUR cost savings and YOUR quality split —
> on YOUR traffic, not our corpus. Then you decide. Want to schedule the
> Day-1 call?"

(Try to book it on the call. If they need to check with someone, send the
pilot agreement immediately after.)

### B. Maybe fit (some hesitation, real pain but unclear authority)
> "Sounds like you'd want X involved too. Mind if I send you the evidence
> pack and the security one-pager so you can share internally? Then we can
> reconvene in a week with whoever needs to sign off."

(Mark as "warming" in your CRM, follow up in 7 days.)

### C. Not a fit (too small, regulated industry blocker, "not now")
> "Honest answer — sounds like timing/fit isn't right today. I'll send you
> the link to our public demo and check back in 90 days. If your bill grows
> 20% in that time, the pilot will make a lot more sense."

(Send link + add to a long-term nurture list. Do NOT chase.)

## Minute 13-15 — Wrap

Regardless of branch:
> "Last thing: who would be the most useful person at $company for me to
> chat with — your CTO? The CFO? An ops lead? I'll only reach out if YOU
> introduce me — never cold."

(One intro from a happy discovery call is worth 50 cold messages. Always ask.)

## Within 1 hour of the call — follow-up email

```
Subject: VIREN — evidence pack + next step

Hi {Name},

Thanks for the 15 minutes. Two attachments and a link:

  1. VIREN_evidence_pack_{date}.pdf — methodology, regression split (the
     factual-vs-stylistic breakdown we discussed), security one-pager, and
     14 baseline reports anyone on your team can audit.

  2. VIREN_security_onepager.pdf — VPC deployment, PII redaction, multi-
     tenant model, what's done vs. roadmap. Pre-empts most questionnaire items.

  3. Live demo: {link}

{If strong fit:}
You said the Day-1 setup call works {day}. Calendly: {link}.

{If maybe fit:}
Take this internally — happy to do a 15-min joint call with {X they mentioned}.

Either way, thanks for being straight with me.

— {Your name}
```

## Tracking

Every discovery call should produce ONE of these states. Update your CRM:

| State | Next action |
|---|---|
| **Pilot scheduled** | Set Day-1 calendar invite + send pilot agreement |
| **Warming (sent pack)** | Follow up Day 7 |
| **Not now (revisit 90d)** | Set 90-day reminder, do not chase before then |
| **Disqualified** | Note why, archive |
| **Referral** | Their referral becomes a new lead with `intro_from = $name` |

## The numbers that matter on this call

Print this card and keep it next to your screen:

- **87%** verified cost reduction (3-judge audit on our corpus)
- **90%** factually equivalent or better (regression split, auditable)
- **100% code-gen pass at 79% lower cost** (real execution tests, strict tie with Sonnet)
- **<250ms** added p95 routing latency (measured); **faster than direct Sonnet at median**
- **$0** pilot cost · **14 days** · **your VPC**
- **3-line** integration · removable instantly
- **0** factual regressions on every shipped route (contractual)

These are the ONLY numbers you need. Don't go off-script with bigger claims.

## Common mistakes (don't)

- ❌ Pitching features before qualifying. Lead with Q1, not the demo.
- ❌ Promising specific savings $ in the call. "Your number is what the pilot measures."
- ❌ Discounting before they push back. They haven't even agreed to start yet.
- ❌ Talking through their answers. Ask Q, **shut up**, listen, take notes.
- ❌ Closing on a "maybe." Always pin a specific next step or end the call cleanly.
- ❌ Forgetting the referral ask. That's the cheapest customer you'll ever get.
