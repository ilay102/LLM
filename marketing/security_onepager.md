# VIREN — Security & Data Handling (one-pager)

For the engineering leader / security reviewer evaluating a pilot. Straight
answers, no hand-waving. Where something isn't done yet, we say so.

## Deployment model

- **Runs in YOUR environment (VPC), not ours.** The gateway is a container you
  deploy in your own cloud account. We do not host your traffic.
- Outbound connections go only to the LLM providers **you** configure
  (Anthropic / OpenAI / DeepSeek) using **your** API keys.
- We (VIREN) have **no standing access** to your environment, prompts, or
  responses. During a pilot we only see data you explicitly export and send us
  (the eval results you choose to share).

## Data flow

```
your app ──► VIREN gateway (your VPC) ──► LLM provider (your keys)
                  │
                  ├─ PII redaction before any cache write
                  ├─ semantic cache (Redis, in your VPC)
                  └─ structured logs (SQLite, in your VPC)
```

Nothing in this path leaves your cloud unless you send a request to a hosted
LLM provider — which your app already does today.

## PII handling

- **Redaction before caching.** Prompts pass through Microsoft Presidio (with a
  regex fallback) before anything is written to the cache. Emails, phone
  numbers, credit cards, US SSNs, IP addresses, and API keys are tokenized.
- PII **type + count** is logged for audit; the PII **content** is never logged.
- Redaction is per-request toggleable (`x-no-pii-redact`) and on by default.

## Authentication & multi-tenancy

- Per-tenant API keys, stored as **SHA-256 hashes** (never plaintext).
- Keys are revokable instantly; rotation supported.
- Per-tenant **monthly budget cap** (hard cutoff at limit) and **minimum-tier
  floor** (e.g. "never route this tenant below Sonnet").
- Per-tenant **model allowlist** — e.g. exclude China-hosted models for a
  regulated tenant with one config change.

## Logging & retention

- Structured per-call logs in SQLite **in your VPC**: tier, cost, latency,
  cache status, token counts, PII-entity counts. You control retention.
- Full audit tarball produced by the teardown script at pilot end.
- We do not ship logs to ourselves.

## Resilience

- **Fail-open on cache outage:** if Redis is unavailable the gateway keeps
  serving (just without caching) — a cache problem never causes a 5xx. Tested.
- Provider fallback: if your primary provider 5xx's or rate-limits, the gateway
  falls back to the next configured provider.
- Traffic-mirror integration is fire-and-forget — during a shadow pilot it
  **cannot** affect your production response path.

## Third-party model hosting (be aware)

- Anthropic (US), OpenAI (US) — standard enterprise providers.
- **DeepSeek is China-hosted.** It's the biggest cost lever but is **excluded
  by default for any tenant whose allowlist restricts it.** For HIPAA / PCI /
  EU-strict / government workloads, exclude `deepseek/*` — one config line.

## What we do NOT have yet (honest)

- **SOC 2 — not yet.** Planned once we have paying customers to justify the
  ~$20k + 12-month runway. We can sign your DPA and answer your security
  questionnaire today; formal attestation comes later.
- No third-party penetration test yet.
- Streaming responses currently bypass the cache and cascade layers.
- Secrets are read from environment / Codespace secrets today; HashiCorp Vault
  / AWS Secrets Manager integration is on the roadmap.

## What we CAN do today for your security review

- Deploy entirely in your VPC (your data never touches our systems).
- Sign your DPA and standard MSA.
- Complete a SIG-Lite / CAIQ questionnaire (honestly — "planned" where planned).
- Provide this document, the threat model, and the full source for review.
- Run the entire pilot with a revokable per-tenant key you control.

## The pilot is zero-trust-by-design

You're not asked to trust us. You deploy our code in your environment, mirror
traffic with a 3-line snippet you can remove instantly, and keep all the data.
If the security review says no, you've installed nothing you can't `docker
compose down`.

---
*Contact: ilay10lankin@gmail.com · Repo available for review on request.*
