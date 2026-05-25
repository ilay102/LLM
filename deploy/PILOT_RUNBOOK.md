# Pilot Setup Call — Runbook for Person A

This is the script you follow on the 30-minute technical kickoff call
with the customer's engineer. Open this doc in a second monitor
during the call.

## Before the call (15 min prep)

- [ ] Confirm customer name, engineer name + email, cloud (AWS / GCP / Azure / on-prem)
- [ ] Generate a pilot key offline: `openssl rand -hex 12` — keep handy
- [ ] Verify their language: Python / Node / Other
- [ ] Have `deploy/integration_samples/README.md` open
- [ ] Have a clean terminal ready, your screen-share rehearsed
- [ ] Sip water. Take a breath. You're going to be calm and helpful.

## Minute 0-2 — Warm open

> "Hi [Name], thanks for the time. The plan for the next 30 minutes is:
> we'll get the gateway running in your environment, drop a 30-line
> snippet into your app to mirror traffic, and verify it's working —
> then I'll get out of your way. Nothing we do today affects your prod
> traffic. Sound good?"

(Wait for their confirmation. Tension drops.)

## Minute 2-5 — Confirm the setup

Ask, then confirm out loud:
- "Where are you planning to run the gateway?" (their AWS account / a dev VM / locally on your laptop)
- "Which app are we mirroring from?" (the support-bot / the assistant / specific route)
- "What's the rough daily volume on that route?" (helps you set expectations)

## Minute 5-15 — Get the gateway running

Share your screen. Walk them through these commands (or, if they prefer,
they screen-share and you guide).

```bash
git clone https://github.com/<your-org>/llm-gateway-pilot.git
cd llm-gateway-pilot

./deploy/pilot.sh \
    --client-id <theirs> \
    --anthropic-key <their key> \
    --openai-key <their key>
```

Wait for the green banner. Verify together:
- `/health` returns 200
- The smoke call returns "OK"
- Logs appear in `deploy/clients/<id>/logs/`

**If pilot.sh errors:**
- Most likely: Docker not running. Have them start it.
- Second most likely: port conflict. Re-run with `--base-port 8100`.
- Third: bad API key. Have them re-paste, double-check no whitespace.

Mark this milestone explicitly: **"OK, the gateway is up. Now let's
mirror traffic."**

## Minute 15-25 — Drop in the mirror

Switch to `deploy/integration_samples/README.md`. Open the right
language section.

Walk them through pasting `attach_mirror` (~3 lines) into their app.
Critical:
- Confirm they're editing a **dev or staging branch**, not main
- Confirm the `gateway_url` matches the URL pilot.sh printed
- Confirm the `gateway_key` matches what pilot.sh printed
- Pick a `pilot_id` — usually `<their-company>-pilot-1`

Have them deploy to dev/staging, send one test call, then check the
gateway logs:

```bash
docker compose --env-file deploy/clients/<id>/.env logs -f gateway
```

You should see a `POST /v1/chat/completions` line with their `x-pilot-id`
header. **Celebrate this moment** — it's the first real customer
traffic. "We're live. Mirror is working."

## Minute 25-30 — Schedule + close

> "OK, you're all set. I'll check in on Day 7 with a mid-pilot snapshot
> of the cost & cache numbers — just for visibility, no decisions
> required. On Day 14 I'll send the full report: cost saved, quality
> comparison, latency. Then your team decides if there's anything to
> talk about. Sound good?"

Book the day-7 + day-14 check-ins on the spot via Calendly.

Send them by email **immediately after the call**:
- Link to `deploy/integration_samples/README.md` in your repo
- Their pilot key (in a one-time-secret link, not email plain text)
- The day-7 and day-14 calendar invites
- A copy of the signed Pilot Agreement (see `pilot_agreement.md`)

## Day 7 — Mid-pilot check-in (Person B owns this)

Run:
```bash
./deploy/daily_summary.py --client-id <id> --since 7d --csv
```

Send a short email:
> "Hey [Name], quick mid-pilot snapshot. We've processed [N] of your
> calls so far. Current cost savings: [X%]. Cache hit rate: [Y%].
> Latency p95: [Z]ms. Quality eval coming on Day 14. No action needed
> on your side. Let me know if anything looks off."

## Day 14 — Report delivery (Person A + B)

Run the shadow-eval pipeline (see `deploy/README.md`). Generate
`report.html` with the customer's name in it. Schedule a 30-min
delivery call. Walk them through the report. Then Person B handles
the close.

## Common questions during the setup call (have answers ready)

**"Where does our data go?"**
> "Nowhere outside the VPC the gateway is running in. The gateway is
> stateless aside from the local cache; the cache lives in a Redis
> container next to it. We never see your prompts or responses unless
> you explicitly export them and send them to us."

**"What's the latency overhead?"**
> "On the mirror path, zero — it runs in a background task and doesn't
> block your prod response. On the gateway path, typically 20-60 ms of
> overhead on top of the underlying provider call."

**"What if your gateway crashes?"**
> "Mirror calls are fire-and-forget; they fail silently. Your prod
> traffic is never affected. The mirror has a 10-second timeout."

**"Can we mirror just one route?"**
> "Yes. Use the `should_mirror=` predicate (Python) or `shouldMirror`
> callback (Node)."

**"What's the cost to us during the pilot?"**
> "Zero on our side. You're paying your existing Anthropic/OpenAI bill
> as you would anyway. We're not adding inference cost; we're showing
> you where you can subtract it."

**"What happens at the end of the pilot?"**
> "You get the full report. If the savings + quality numbers are
> compelling, we talk pricing — typically 25-30% of verified savings
> with a floor, 12-month commitment. If they're not compelling, you
> remove the 3-line mirror snippet and we part ways with a tarball of
> your logs."
