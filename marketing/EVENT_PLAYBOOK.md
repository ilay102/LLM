# Tech Company Event — 7-Day Prep + On-the-Day Playbook

You have one week. Tech company reps are coming to campus. Goal: get
**5-15 qualified follow-up conversations** booked from the event.

## What you're NOT doing at the event

- ❌ Selling on the spot — nobody signs anything at a uni event
- ❌ Giving a 5-minute pitch — they'll walk away after 30 sec
- ❌ Showing slides — they hate slides
- ❌ Reading the 1-pager out loud — they'll read it later

## What you ARE doing

- ✅ Showing a live, moving demo on a laptop in <60 sec
- ✅ Saying ONE crisp sentence about what it is
- ✅ Capturing their info with a QR code → Calendly
- ✅ Sending a personalized follow-up within 24 hours

---

## 7-Day Prep Plan (Person A owns; Person B handles outreach side)

### Day 1 (today) — Verify everything works
1. Test `pilot.sh` end-to-end in your Codespace. Must produce green banner.
2. Open `marketing/demo_dashboard.html` in browser. Connect to running gateway. Verify all 6 prompts work and cache hit fires on repeat.
3. Fix anything broken.

### Day 2 — Polish the demo
1. Replace any `[placeholder]` values in `one_pager.html` with real ones (your email, Calendly URL)
2. Export `one_pager.html` to PDF (Chrome → Print → Save as PDF, A4, no margins)
3. Generate a QR code (free at qrcode-monkey.com or qr.io) pointing to your Calendly. Save as PNG.
4. Print 5 copies of the 1-pager (or have them ready as a digital share link)

### Day 3 — Record the Loom (backup demo)
Follow `marketing/demo_script.md`. Why: at the event, sometimes WiFi is bad. The Loom video plays from your laptop with no internet. Have it ready as a fallback to the live demo.

### Day 4 — Practice the 60-second pitch
Memorize the script below (see "Elevator pitch" section). Practice it 20 times. Out loud. To a mirror. Record yourself once and watch it back.

### Day 5 — Stress-test the demo
1. Run the live demo on your laptop unplugged (battery)
2. Run it with phone hotspot (worst-case WiFi)
3. Click every prompt twice in random order — verify nothing breaks
4. Time yourself: from "click first prompt" to "show cached- moment" should be <90 seconds

### Day 6 — Build the "leave-behind" digital handoff
Create a simple landing page (one HTML page) at a memorable URL that contains:
- Your tagline
- A 30-second embedded video (the Loom)
- The 1-pager PDF
- A Calendly link to book a 15-min chat
- Your contact info

Host free on GitHub Pages, Vercel, or Cloudflare Pages. Get a memorable URL like `viren-llm.com` (Namecheap, $10) or just use the GitHub Pages URL.

### Day 7 — Final dry run
1. Set up your "booth" on a desk: laptop, business cards, printed QR code, printed 1-pagers, water
2. Run through the whole flow with a friend playing "tech rep walking by"
3. Get feedback on what's confusing
4. Sleep 8 hours the night before

---

## The 60-Second Pitch (memorize this)

**Setup (the prop):** Have `demo_dashboard.html` open in fullscreen on the laptop, gateway running in the background. Don't talk until they're looking at the screen.

**0:00-0:10 — Hook**
> "Hi! 30 seconds — want to see how to cut an LLM API bill by 60%?"

(If they walk away, smile and let them. If they pause: continue.)

**0:10-0:20 — Setup**
> "Most companies send every AI request to one expensive model — like sending every email FedEx Priority. We sit between your app and OpenAI/Anthropic and pick the right model per request, automatically."

(While talking, click prompt #1 — sentiment classification.)

**0:20-0:35 — The demo lands**
> "Watch — sentiment classification. Cheap tier, Haiku, 900 milliseconds, costs basically nothing. Now watch this..." (click prompt #5 — the architecture one)
> "...architecture design. Our classifier saw 'design schema, trade-offs' — escalated to Opus. Same gateway, different decision."

**0:35-0:50 — The closer**
(Click prompt #1 again — the sentiment one)
> "And now the kicker — same question, asked again. Cached. 3 milliseconds. Zero cost. Twenty-five percent of typical SaaS traffic is repeats."

(Point at the savings counter at the bottom)
> "That counter is real-time. In a real deployment we save 50-70%."

**0:50-1:00 — The ask**
> "If you're at a company shipping AI features and your bill is climbing — I'd love a 15-minute chat. Here's my code, here's a calendar link." (Slide the QR code in front of them)
> "If not, no worries — thanks for stopping by."

---

## The QR Code Strategy

Print a card with:
- Big QR code in the middle
- "Book 15 minutes with VIREN" above it
- Your name + email below
- Tiny URL backup printed below the QR

Put 3 of these cards on your desk in a stand. The QR points to your Calendly with pre-filled fields.

**Don't ask for business cards.** Ask them to scan. It's faster, modern, and means follow-up is automatic.

---

## Things to Bring

| Item | Why |
|---|---|
| Laptop, fully charged, charger | The demo |
| Phone hotspot ready | WiFi backup |
| 10 printed QR cards | The capture mechanism |
| 5 printed 1-pagers | For the rare person who wants paper |
| Water bottle | You'll be talking a lot |
| Notebook + 2 pens | For taking notes on who you talked to |
| Backup laptop charger | Yours will fail |
| Phone charger | You'll need it |
| Stand for laptop at chest-height | So you can demo standing |

**Outfit:** Look like a serious engineering student, not a startup bro. Clean shirt, no slogan, nothing that distracts from the demo.

---

## What to do AT the event

### Setup (30 min before doors open)
- Get the gateway running locally
- Open `demo_dashboard.html` in fullscreen on the laptop
- Test connect — see the live "Gateway live" indicator
- Click each prompt once to "prime" the demo (so cache shows hits later)
- Click "Reset stats" so you start clean
- Put laptop at chest height, screen rotated slightly so people can see from the side
- Set out QR cards + 1-pagers
- Take a breath

### When someone approaches
1. Make eye contact, smile
2. Wait for them to lean in / look at the screen
3. **First sentence is always the hook** (see pitch)
4. If they engage → run the 60-second demo
5. If they have a question → answer it; then back to demo
6. End with the QR ask
7. After they walk away → in your notebook write: name, company, what they said, follow-up note

### Track these metrics in your notebook
- People stopped at the booth: ____
- People who watched the full demo: ____
- People who scanned the QR / took a card: ____
- People who booked a Calendly: ____

These numbers tell you which step is broken and what to fix next time.

---

## Likely Questions (have answers ready)

**"Who are you?"**
> "I'm an engineering student building this with [partner]. We're early — looking for design partner companies to run free 2-week pilots."

**"Is this open source?"**
> "The gateway core is, the routing logic and eval harness are proprietary. Pilot teams get the whole stack."

**"What if my company already uses LiteLLM / Portkey / OpenRouter?"**
> "Those are great gateways. We're not a gateway — we're a managed service that uses one. The product is the routing logic, the eval harness, and the pilot methodology that proves quality. The infrastructure is just plumbing."

**"How does the routing actually work?"**
> "Two layers: rule-based for obvious cases — short prompts with classification keywords go cheap. Then a learned head — a logistic regression on bge embeddings, trained on labeled prompts. Want me to show the corpus?" (open `classifier/prompts_to_label.jsonl`)

**"What about quality? How do you prove the cheap model didn't degrade my output?"**
> "Two-week shadow pilot in your VPC. We mirror your prod traffic, route it both ways, run a 3-judge pairwise audit, and split every disagreement into 'factually wrong' vs 'stylistic-only.' Contractually we guarantee zero factual regressions vs your baseline on every route we ship — or that route stays on the higher tier."

**"What about PII / GDPR?"**
> "Gateway deploys in your VPC. Your traffic never leaves your cloud. Optional Presidio integration for PII redaction before cache write. SOC2 — not yet, expected Q3 next year. Most pre-Series-C companies don't require it on day one, but we'd love to talk to your security person."

**"What's the pricing?"**
> "Pilot is free. After: 25% of verified savings, $2k/month floor, 12-month term, 60-day notice. Aligned incentives — if we don't save you money you don't pay."

**"You're a student, why should I trust this in production?"**
> (Honest answer, no fake bravado.) "Right. That's why the pilot is free, runs in your VPC, and you can pull the plug with one line of code at any time. We're not asking for trust — we're asking for two weeks of mirrored traffic. The data speaks. If it doesn't work for you, you lose nothing."

**"Can I see the code?"**
> "Yep — repo is here." (Point to the GitHub URL on your QR card / 1-pager.)

---

## After the Event — Day 1 Follow-Up

Within 24 hours, send a personal email to every person who scanned the QR
or took a card. Use template #6 ("Post-call follow-up") from
`outreach_templates.md`, adjusted:

```
Hi [Name],

Great to meet you at [event] today. As promised, here's everything:

- 1-pager: [link]
- 4-min demo video: [Loom link]
- The repo: [GitHub link]

If after looking those over you think a 15-min chat would be useful with
your team, here's my calendar: [Calendly link]

If not, no worries — happy to follow up in [N] months when timing's
better. Either way, appreciate you stopping by.

[Your name]
```

---

## Don't Beat Yourself Up

Most people walking past will not stop. Most who stop will not book.
Most who book will not convert. **This is normal.** If 50 people walk by,
10 stop, 5 watch the full demo, 2 scan the QR, 1 books a real call — you
have done EXCELLENTLY.

That's how startups are built: one yes at a time.
