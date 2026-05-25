# VIREN Marketing & Sales Assets

Everything Person B needs to sell the pilot.

## Files

| File | What it is | Who uses it | When |
|---|---|---|---|
| `one_pager.html` | Branded leave-behind PDF | Person B sends after every call | After every discovery call |
| `pricing_calculator.html` | Interactive savings calculator | Person B shares with prospects | After they share rough $ spend |
| `outreach_templates.md` | 11 pre-drafted messages | Person B copy-pastes daily | Throughout the 14-day sprint |
| `demo_script.md` | Script for the 4-min Loom | Person A records once | Week 1 (one-time) |

## How to use the one-pager

Open `one_pager.html` in Chrome → Cmd/Ctrl+P → Save as PDF → A4, no margins.
Save as `VIREN-Pilot-1pager.pdf`. Send as an attachment after every call.

**Customize these placeholders before exporting:**
- `[calendar-link]` → your real Calendly URL
- `[your-email]@[domain]` → your contact email
- `github.com/[org]/llm-gateway` → your repo or homepage

## How to use the pricing calculator

Two options:
1. Open `pricing_calculator.html` in browser, share via screen on calls
2. Host it (GitHub Pages free) and send the link with the one-pager

Calculator inputs:
- Monthly LLM spend (USD)
- Provider (Anthropic / OpenAI / Mixed)
- Default model
- Traffic mix (3 sliders: % simple, % repeat, % long-context)

Outputs estimated savings, our fee, net to them. Numbers based on
empirical pilot data; we explicitly say "actual savings depend on
your traffic distribution and are verified during the 2-week pilot."

## How to use the outreach templates

Open `outreach_templates.md`. Follow the daily playbook in
`shadow-eval/` or the master plan. Templates are numbered 1-11 in
order of when you'd use them in a conversation:

1. LinkedIn connection request (200 chars)
2. Post-acceptance DM
3. Cold email
4a-e. Reply handlers
5. Pre-call confirmation
6. Post-call follow-up
7. 7-day cold-follow-up
8. Referral request
9. Pilot agreement hand-off
10. Day-7 mid-pilot email
11. Final report delivery

**Critical:** personalize one specific thing per company. Never blast.

## How to record the demo

Read `demo_script.md`. Use Loom (free). Target 4:00 total.
- 0:00-0:20 hook (talking head)
- 0:20-0:50 problem framing
- 0:50-1:50 gateway running (screen share)
- 1:50-2:30 integration (3 lines of code)
- 2:30-3:30 the report
- 3:30-4:00 close + ask

Save the Loom URL in your tracker. Use it in:
- Email follow-ups after calls
- LinkedIn DMs once they accept (occasionally — don't lead with it)
- The 1-pager hand-off

## Brand notes

- Company name: **VIREN**
- Tagline (cold-outreach version): "Cut your LLM bill by 60%. Without changing your code."
- Tagline (broader): "The control plane for your LLM stack."
- Logo: 3D minimal geometry, white background (see logo prompts in chat history)
- Accent color: `#3b35ff` (electric indigo)
- Wordmark: `VIREN` all-caps, loose letter-spacing, sans-serif (Inter / Söhne / Geist)
