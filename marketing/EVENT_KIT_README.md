# VIREN Event Kit

Everything you need for the booth, in print-ready form.

## What's in here

| File | What | When to print/use |
|---|---|---|
| `booth_poster.html` | A3 portrait standing poster | Print on A3 (or scaled A4), foam-board it, behind your laptop |
| `qr_cards.html` | 10 business-card-sized QR cards per A4 sheet | Print 2-3 sheets, cut, stack on the desk |
| `pitch_deck.html` | 12-slide HTML deck for 5-min conversations | Open on a tablet/phone if someone wants slides |
| `demo_dashboard.html` | Live interactive demo | Fullscreen on your laptop during the event |
| `cfo_dashboard.html` | **Live $-savings counter** reading `/metrics` | Second tab — when a CTO/CFO asks "how much have you saved?" — flip to it |
| `landing_page.html` | Public page QR codes point to | Host on GitHub Pages |
| `EVENT_PLAYBOOK.md` | 60-sec pitch + Q&A prep | Read morning-of |
| `../scripts/build_evidence_pack.py` | Generates the CTO handout PDF | After eval lands, generate fresh per-prospect |

## Step-by-step prep

### 1. Update placeholders (15 min)

Open each HTML file and replace:
- `[your-calendly-link]` — your real Calendly URL
- `[your-email]` — your real email
- `your-calendly-link.com` — short version for printed cards

Files affected:
- `booth_poster.html`
- `qr_cards.html`
- `pitch_deck.html`
- `landing_page.html`

### 2. Generate the QR code (5 min)

1. Go to https://qr.io or https://qrcode-monkey.com
2. URL field: your Calendly link
3. Download as PNG, high resolution
4. In `booth_poster.html` and `qr_cards.html`, replace the placeholder QR div with `<img src="qr.png" style="width: 100%; height: 100%;">`

### 3. Print physical materials (30 min)

| Item | Size | Quantity | Where |
|---|---|---|---|
| Booth poster | A3 portrait | 1 | Print shop with foam-board mounting |
| QR cards | A4 sheet of 10 | 3-4 sheets | Any printer + paper cutter |
| 1-pager | A4 portrait | 5 | Local printer |

Total cost: ~$20-30 at a campus print shop.

### 4. Host the landing page (10 min)

```bash
# In repo root
git checkout -b gh-pages
cp marketing/landing_page.html index.html
git add index.html
git commit -m "GitHub Pages publish"
git push -u origin gh-pages
```

Then in GitHub: Settings → Pages → Source = `gh-pages` branch. URL appears at
`https://ilay102.github.io/LLM/` within ~30 sec. Make the QR code point here.

### 5. Generate the evidence pack per-prospect (after each pilot interest)

```bash
python3 scripts/build_evidence_pack.py --client-name "Acme Inc"
# Opens scripts/evidence_pack.html
# Cmd/Ctrl+P -> Save as PDF -> email to them
```

## Day-of checklist

- [ ] Laptop charged + spare charger
- [ ] Demo dashboard tested with live gateway 30 min before
- [ ] QR cards stacked, 1-pagers in folder, poster on stand
- [ ] Phone hotspot ready in case venue WiFi sucks
- [ ] Calendly checked — slots open this week
- [ ] Water, notebook, 2 pens
- [ ] Clean shirt, hair combed
- [ ] Read `EVENT_PLAYBOOK.md` once more — the 60-sec pitch is muscle memory
- [ ] Deep breath. Smile. Have fun.

## The 60-second pitch (memorize)

> *(have demo dashboard open on laptop, click first prompt as you talk)*
>
> "Hi! 30 seconds — want to see how to cut an LLM API bill by 60%?
>
> Most companies send every AI request to one expensive model. We sit between your app and OpenAI/Anthropic and pick the right model per request, automatically.
>
> Watch — sentiment classification, cheap tier, 900ms, basically free.
> *(click prompt 5)*
>
> Architecture design — our classifier saw 'design schema' — escalated to Opus. Different decision, same gateway.
>
> *(click prompt 1 again)*
>
> Now the kicker — same question again. Cached. 3ms. Zero cost.
>
> We've verified this end-to-end. 87% cost savings, 80% pairwise quality with three different LLM judges.
>
> If you're at a company shipping AI features — I'd love a 15-minute chat. Here's a QR code." *(slide a card across)*

## After the event

Every QR scan triggers a Calendly booking. Within 24 hours:
1. Send the evidence pack PDF (use `build_evidence_pack.py`)
2. Send the Loom demo link
3. Send the 1-pager PDF
4. Schedule the follow-up call

If 10 people scan and 2 book, that's an excellent event. Keep going.
