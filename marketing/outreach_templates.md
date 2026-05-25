# Outreach Templates — for Person B

Pre-drafted messages for the 14-day sales sprint. Each template has been
shaped around what actually converts at this stage: student framing,
specific reference to their company, low ask, no pitch.

**Rules for using these:**
1. Always personalize one specific thing — never blast unchanged.
2. Send 15-20 per day, no more (LinkedIn throttles).
3. Track every message in your tracker spreadsheet (date sent, response, status).
4. If acceptance rate <25% after 50 messages, the profile or template is broken — change ONE thing, retry.

---

## 1. LinkedIn Connection Request (200-char limit)

**Use first.** Sent with the connect request.

```
Hi [Name] — engineering student researching how SaaS teams handle LLM API
costs at scale. Saw [Their Company] is shipping [specific AI feature].
Would love to learn from you — no pitch, just research. Mind connecting?
```

**Personalization rules:**
- `[specific AI feature]` — pull from their About page, recent blog post, or LinkedIn product update.
  Examples: "the AI search you launched", "your AI ticket summaries", "the new copilot feature".
- If you can't find a specific feature, DO NOT send. Find another target.

**A/B variants to test after 30 messages:**

Variant B (slightly different opener):
```
Hi [Name] — [University] student, doing my final-year research on LLM
cost in production SaaS. [Their Company]'s [feature] caught my eye —
mind a quick connect? Happy to share what I'm learning from the cohort.
```

---

## 2. Post-Acceptance DM

**Send 24–48 hours after they accept.** Don't send immediately — looks
automated.

```
Thanks for connecting, [Name] 🙏

Quick context — I'm an engineering student at [University] and for my
final project I'm researching how mid-stage SaaS teams handle the LLM
cost problem as their AI features scale.

I'm interviewing 15 VP Engs / Eng Leads over the next 2 weeks. Could
I get 15 minutes of your time on Zoom? No demo, no pitch — I just want
to hear what you're seeing in production. I'll share back the patterns
I learn from the other 14.

If yes, here's my calendar: [Calendly link]

If now's not the right time, no worries at all — totally understand.

Thanks,
[Your name]
```

---

## 3. Cold Email (when LinkedIn doesn't connect)

**Subject line options (rotate):**
- `Question from a [University] engineering student`
- `15-min research chat — LLM cost in SaaS`
- `Final project research — would love your perspective`
- `[University] student researching LLM cost in SaaS`

**Body:**

```
Hi [Name],

I'm [Your name], an engineering student at [University]. I'm working
on a final project researching how mid-stage SaaS companies are
managing LLM API costs as their AI features scale.

I noticed [Their Company] has shipped [specific feature]. Engineering
leaders at companies your size keep coming up as the people who
actually see this pain firsthand.

Would you be open to a 15-minute Zoom this week? No demo, no pitch —
just 4-5 questions on what your team is actually experiencing. I'm
talking to 15 VP Engs over the next two weeks and happy to share what
I find back with everyone I interview.

If yes, here's a calendar link: [Calendly]
If now's not the right time, completely understand.

Thanks,
[Your name]
[Your university email]
[LinkedIn URL]
```

---

## 4. Reply Handlers

### Reply 4a — "Sure, I'll book" ✅

> [calendar booking happens automatically]

Auto-confirmation. Update tracker → "Discovery scheduled."

### Reply 4b — "What's this about exactly?"

They're curious but want more before committing. Give them the
research framing, not the pitch.

```
Thanks for replying [Name]! Quick context:

I'm looking at the unit economics of AI features in B2B SaaS —
specifically, the engineering teams' experience of LLM API spend as
volume grows. A few questions I'm digging into:

  - At what monthly spend does cost start mattering at exec level?
  - How are teams thinking about routing between cheap vs. expensive models?
  - What does observability around AI cost look like in real apps?

I think there's a gap between what companies do today and what's
possible — and I want to understand it from people who live it.

15 minutes when convenient: [Calendly link]
```

### Reply 4c — "Not interested" / "Wrong person"

Graceful, single-reply close. **Do not chase.**

```
Totally understood — thanks for the quick reply. If you happen to know
anyone else who'd be a good person to chat with on this, would really
appreciate the intro. Either way, thanks for taking the time!
```

Mark as Dead. Move on.

### Reply 4d — "Reach out in [N] months"

```
Got it, thanks [Name]. Putting a note in my calendar to ping you in
[month]. Best of luck with [thing they mentioned] in the meantime.
```

Add to tracker → status "Snooze", note the month.

### Reply 4e — "Send me info"

They want to read first. Send the 1-pager — and STILL ask for the call.

```
Of course — here's a 1-pager on what I'm building and how the pilot
works: [link to one_pager.pdf]

If after reading it you think a 15-min chat would be useful, here's
my calendar: [Calendly link]
No pressure either way — wouldn't be wasting your time if it doesn't
fit.
```

---

## 5. Pre-Call Confirmation Email

**Send 24h before the booked call.**

```
Hi [Name],

Looking forward to chatting tomorrow at [time] PT / [their time].
Zoom link: [link from Calendly]

Quick agenda so you know what to expect (15 min total):
  - 2 min: your AI feature setup
  - 10 min: 5 questions about cost, routing, quality, observability
  - 3 min: I'll share what I'm building in case it's interesting

Nothing to prepare. Talk soon!

[Your name]
```

---

## 6. Post-Call Follow-Up (within 4 hours)

This is the most important message in the whole sequence.

If they showed real pain on the call:

```
Hey [Name],

Really enjoyed the chat — thanks for being so candid about [specific
thing they mentioned, e.g. "the GPT-4o spend exploding since you
launched the copilot"].

Here's what I mentioned: a 1-pager on the pilot, plus a 4-min Loom
walking through the gateway in action.

- 1-pager (PDF): [link]
- Loom: [link]

If after looking those over you think it's worth a 30-min follow-up
with one of your engineers to actually try this on a sample of your
traffic, here's my calendar: [Calendly]

If the timing isn't right or it's not a fit, no worries — would still
love to send you the final results when I'm done with the research.

Thanks again,
[Your name]
```

If the call revealed they're not a fit (too small, regulated industry,
already using a competitor):

```
Hey [Name],

Thanks for the chat — really useful for the research. Based on what
you described it sounds like [specific reason, e.g. "your spend isn't
there yet" or "you're already using BedRock's optimization"], so I
don't think the pilot would be useful right now — wanted to be upfront
rather than waste either of our time.

If anything changes (you cross [threshold], or things shift), I'd love
to reconnect. And if you know anyone at companies who might be feeling
the LLM cost pain harder, an intro would mean a lot.

Thanks again,
[Your name]
```

(Always ask for the referral. Even a polite "no" can produce a hot lead.)

---

## 7. 7-Day Follow-Up (no response from cold)

For prospects who never replied to the LinkedIn DM or cold email. **One
follow-up only. Then drop them.**

```
[Name] — quick bump in case the first message got buried. I'm wrapping
up the research interviews by [date]; any chance of a 15-min chat in
the next week? Calendar: [Calendly]

If now's not a fit, I'll stop bothering you — totally fine.
```

---

## 8. Referral Request (after a great call)

End every good call with this:

> "Last thing — I'm trying to talk to 14 more engineering leaders.
> Anyone you'd recommend I reach out to who might have strong opinions
> on LLM cost? Even just a 'try X at company Y' would help."

Get the name → send this DM/email same day:

```
Hi [Referred Name] —

[Original Champion] mentioned you might be a good person to chat with
about how SaaS teams handle LLM API cost. They thought you'd have
strong opinions.

I'm a [University] engineering student doing research on this for my
final project. Talking to 15 VP Engs over the next two weeks. Would
you be open to 15 minutes? No demo, no pitch.

Calendar: [Calendly]

Thanks!
[Your name]
```

Warm intros convert at 5-10x the rate of cold. Always ask.

---

## 9. Pilot Agreement Hand-Off

When they say yes verbally and want to start:

```
Awesome [Name] — let's get this rolling.

Three things to make it real:

1. A short pilot agreement (free, 14 days, no commitment) —
   one-page PDF attached. Pretty standard terms; have your team
   eyeball it. Sign back when you're ready.

2. Who's the engineer on your side I'll do the 30-min setup call with?
   I'll reach out directly to schedule.

3. Which route do you want to start with? My recommendation: the one
   with the highest daily volume. We can always add more later.

Looking forward to it.

[Your name]
```

---

## 10. The Day-7 Mid-Pilot Email

Person B sends this on Day 7 of every running pilot:

```
Hi [Name],

Quick mid-pilot snapshot for [Company]. We've processed [N] of your
mirrored calls so far. Numbers:

  - Cost savings vs. baseline: [X%]
  - Cache hit rate: [Y%] ([Z calls served from cache, $0])
  - Tier distribution: [A%] cheap, [B%] balanced, [C%] frontier
  - p95 latency: [N]ms

The full quality eval drops in 7 days with the final report.

No action needed on your side. Pilot key still valid; mirror still
flowing. Let me know if anything looks off.

Best,
[Your name]
```

---

## 11. Final Report Delivery

```
Hi [Name],

The 14-day pilot is done. Here's the full report:

[link to client-specific report.html]

Headline numbers for [Company]:
  - Cost reduction: [X%]
  - Pairwise quality (win-or-tie): [Y%]
  - p95 latency: [Z]ms (vs. [baseline] for direct calls)
  - Projected annual savings: $[N]

The appendix has every prompt + every routing decision + the judge's
reasoning, so your team can audit anything that looks interesting.

I'd love to walk you through it on a 30-min call this week or next —
both to answer questions and to talk about what happens after the pilot.
[Calendly]

If you'd rather just send feedback over email, that works too.

Thanks for taking the bet,
[Your name]
```

---

## Tracker Spreadsheet Columns (recap)

| Column | Example |
|---|---|
| Date added | 2026-05-14 |
| Company | Acme AI |
| Industry | AI customer support |
| Employees | 47 |
| Funding stage | Series A |
| Champion name + role | Sarah Chen, VP Eng |
| LinkedIn URL | linkedin.com/in/sarahc |
| Email | sarah@acme.ai |
| Source | "AI customer support" LinkedIn search |
| LinkedIn sent | 2026-05-15 |
| LinkedIn reply | "..." |
| Email sent | 2026-05-17 |
| Email reply | "..." |
| Call booked | 2026-05-22 14:00 |
| Call outcome | "Wants pilot" / "Not now" / "Wrong ICP" |
| Status | Discovery / Pilot / Closed-Won / Closed-Lost / Dead |
| Notes | "$80k/mo Anthropic, board pressure" |
| Last touch | 2026-05-22 |
| Next action | "Send 1-pager + Loom" |
| Next action date | 2026-05-23 |

---

## What "good" looks like by end of Day 14

| Metric | Target | Healthy range |
|---|---|---|
| LinkedIn requests sent | 150 | 100-200 |
| Acceptance rate | 30%+ | 25-45% |
| DMs sent (post-acceptance) | ~45 | |
| Emails sent | 60-80 | |
| Replies | 20-30 | |
| Discovery calls completed | 5-8 | 4-10 |
| **Pilots verbally agreed** | **1-2** | **1-3** |
| **Pilots signed (1-pager)** | **1** | **0-2** |

If you're below the healthy range, ONE variable is broken. Diagnose and
adjust:
- Low acceptance → profile or ICP
- Low replies → message body
- Low call → pilot conversion → pitch (the on-call ask)
- Pilots agree but won't sign → reduce friction in the agreement
