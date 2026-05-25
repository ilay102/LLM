# Traffic-Mirroring Integration Samples

Drop-in code your engineer pastes into your app so we can run a 2-week
shadow test on real production traffic — **without affecting your prod
responses**.

## How mirroring works

Your prod code keeps calling OpenAI/Anthropic exactly as before. Every
request is *also* sent in the background to the VIREN gateway, which routes
it intelligently. We then compare the two answers and produce a quality +
cost report. Your users never see a difference.

```
Your app  ─►  OpenAI/Anthropic  ─►  user response
   │
   └──(background)──►  VIREN gateway  ─►  log only (no user impact)
```

Three properties to internalize:

1. **Non-blocking.** Mirror runs in a fire-and-forget task. Your prod
   request returns first, every time.
2. **Fail-safe.** If the gateway is unreachable, the mirror is silently
   dropped. Prod is never affected.
3. **Sample-able.** You can mirror 100% of one route and 0% of another,
   or 10% sampling, etc.

## Choose your integration

### Python — `mirror_python.py`
For apps using the official `openai` or `anthropic` Python SDKs.

```python
from openai import OpenAI
from mirror_python import attach_mirror

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
attach_mirror(
    client,
    gateway_url="https://viren-gw.your-vpc:8000/v1",
    gateway_key="pilot-xxxxxxxx",      # we give you this
    pilot_id="acme-pilot-1",
)

# Use client as usual — every call is now mirrored.
resp = client.chat.completions.create(model="gpt-4o", messages=[...])
```

To mirror only one route:
```python
attach_mirror(client, ..., should_mirror=lambda kw: kw.get("user") == "support-bot")
```

To mirror 10% sampling:
```python
attach_mirror(client, ..., sample_rate=0.1)
```

### Node.js — `mirror_node.js`
For apps using `openai` or `@anthropic-ai/sdk`. Node 18+ recommended.

```javascript
const OpenAI = require('openai');
const { attachMirror } = require('./mirror_node');

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
attachMirror(client, {
    gatewayUrl: 'https://viren-gw.your-vpc:8000/v1',
    gatewayKey: 'pilot-xxxxxxxx',
    pilotId: 'acme-pilot-1',
});

// Use client as usual.
const resp = await client.chat.completions.create({ ... });
```

### Proxy-level (no code changes) — Envoy / Nginx mirroring

If you'd rather not touch app code, ask us about a proxy-level mirror.
We can hand you an Envoy `request_mirror_policies` snippet or an Nginx
`mirror` directive. Useful for:
- Polyglot architectures (multiple languages calling LLMs)
- Cases where the SDK is deeply embedded
- When app deploys are slow and you want to start the pilot today

## What the pilot key looks like

We generate a per-pilot key during onboarding. It looks like:
```
pilot-7f3a9b2c1d4e8f0a
```
Treat it like a regular API key. Put it in your secrets manager. It works
**only** against your dedicated pilot gateway endpoint; it cannot access
any other tenant.

## Tearing it down

When the pilot ends, remove the `attachMirror` line (one line) or set
`sampleRate: 0`. The mirror disappears instantly. No cleanup needed in
your prod code.

## Privacy & data handling

- Mirror traffic terminates inside **your** VPC at the gateway we deployed
  for you. Nothing leaves your cloud unless you explicitly forward to a
  hosted LLM provider (Anthropic/OpenAI) using your existing keys.
- We log the prompt content and the model response in the pilot's
  shadow log file — same as your existing OpenAI/Anthropic logs do today.
  We use it only to compute the pilot report.
- At pilot end you run `./deploy/teardown.sh --client-id <you>` and we
  produce a tarball of all data for your audit. You delete the volume
  whenever you want.

## Questions?

- **Latency impact:** ~0 ms in steady state. The mirror runs on a
  separate thread/event loop and doesn't await.
- **CPU/memory overhead:** negligible. Each call is one HTTP POST.
- **What if your gateway is slow?** Mirror calls time out after 10 s and
  are dropped. Prod calls are never impacted.
- **Will my user IDs / PII end up in your cache?** Only if you don't
  redact them. We can enable PII redaction at the gateway — ask us.
