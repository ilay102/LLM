# 4-Minute Loom Demo Script

Read this aloud while screen-recording. Don't memorize verbatim — internalize
the flow. Recording tool: Loom (free) or OBS. Resolution: 1080p minimum.

**Total time: 4:00**

---

## 0:00–0:20 — The hook (talking head, no screen yet)

> "Hi, I'm [your name], one of the builders behind VIREN. If you're shipping
> AI features in a B2B SaaS product, your LLM bill is probably the line item
> nobody on the exec team understands but everyone has opinions about.
>
> What I'm going to show you in the next 4 minutes is how we cut that bill
> by 60% or more — without changing the code your team writes."

## 0:20–0:50 — The problem on one slide (or just talk to camera)

> "Most teams send every request to one default model — usually Sonnet or
> GPT-4o. That's like sending every email through FedEx Priority Overnight.
> A simple sentiment classification doesn't need the same model as a
> system-architecture proposal.
>
> VIREN is a gateway. Your app talks to us with the standard OpenAI SDK.
> We classify each request, route it to the right tier, cache identical
> and similar prompts, and stream the response back. You change three
> lines in your app. Quality stays the same. Cost drops by half or more."

## 0:50–1:50 — Show the gateway running (screen share)

Open your terminal. Show the gateway is up:
```bash
curl -s http://localhost:8000/health | jq
```

Talk over it:
> "Here's the gateway running locally. Three available tiers — cheap,
> balanced, frontier — backed by Haiku, Sonnet, and Opus, with provider
> fallbacks if any one of them is down."

Run the smoke test:
```bash
python tests/smoke.py
```

As the output prints, narrate:
> "Five real prompts. Watch the tier the gateway picks for each one.
> Sentiment classification — Haiku, 900 milliseconds, $0.0001.
> Translation — also Haiku.
> Three-paragraph essay — Sonnet automatically.
> Math proof — escalates to Opus because the classifier sees reasoning
> markers.
> Code refactor — also Opus.
>
> Now watch the sixth call — same prompt as the first, sent again."

Point at the cached- ID:
> "Cached. Three milliseconds. Zero cost. That's the semantic cache —
> same prompt, even slightly different wording, comes back instantly."

## 1:50–2:30 — Show the integration (screen share)

Open `deploy/integration_samples/mirror_python.py`. Scroll to the
`attach_mirror` example at the top.

> "This is everything your engineer needs to change. Three lines. The
> mirror runs in a background task — never touches your prod response
> path. If our gateway is slow or down, your users see zero impact.
>
> This is what makes the pilot zero-risk. You're mirroring traffic for
> measurement. Your customers never see a different answer."

## 2:30–3:30 — Show the report (screen share)

Open a sample `report.html` (or use the one in `baselines/` if you have one).

> "After two weeks, you get this report. Side-by-side comparison of
> every prompt your app sent: what the gateway routed it to, what the
> response was, what your baseline model would have returned, and which
> answer a panel of LLM judges preferred.
>
> Look at the headline numbers. Win-or-tie rate against your baseline:
> 98%. Cost reduction: 62%. p95 latency: within 30 milliseconds.
>
> Every regression is right here in the appendix — you can audit any
> decision, see the prompts, the answers, the judge's reasoning. No
> magic. No marketing math."

## 3:30–4:00 — Close

(Back to talking head if possible)

> "The pilot is free. We deploy in your VPC. Your data never leaves
> your cloud. After two weeks you get the report — even if you decide
> we suck, you keep the data.
>
> We're looking for three design partners. If you'd like to be one,
> the email is in the description. 15-minute discovery call, no demo,
> no pitch — just five questions to make sure it's a fit.
>
> Thanks for watching."

---

## Production notes

- **Camera framing:** chest-up. Eye-level camera. Soft natural light from in front.
- **Background:** plain wall, no clutter. Or a clean code editor.
- **Audio:** wired headphones with mic > laptop mic. Record in a small room with soft furnishings.
- **Practice runs:** do 3 takes. The 3rd is always the best. Pick that one.
- **Editing:** Loom auto-trims silence. Don't over-edit. Real beats polished.
- **Captions:** Loom auto-generates. Review for "VIREN" being spelled right.
- **Thumbnail:** the "62% / 98%" report frame. That number does the click work.
- **Length:** target 4:00. If you go to 5:00, cut. Nobody watches longer.

## Variations to record

- **30-second teaser** for LinkedIn DMs (just the cost result + "want the 15-min call?")
- **2-min "for your CTO" version** that emphasizes the security & quality story
- **6-min deep dive** for prospects who want technical detail

Build the 4-min one first. The others are just edits of it.
