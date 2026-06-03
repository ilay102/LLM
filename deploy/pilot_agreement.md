# Pilot Agreement

**Between** [Customer Name] ("Customer") **and** VIREN ("Provider")
**Pilot Start Date:** [Date]
**Pilot Duration:** 14 calendar days from start
**Pilot ID:** [pilot-id]

---

## 1. What this pilot is

A free, time-limited test of Provider's LLM routing and caching gateway
("Service") on a subset of Customer's production traffic. No payment is
exchanged. Either party may end the pilot at any time with 24 hours'
notice.

## 2. What Provider will do

- Deploy the Service in Customer's environment (or a Customer-approved
  cloud account) using the open-source `pilot.sh` script.
- Provide the integration code samples and a 30-minute setup call.
- Send a mid-pilot summary on Day 7 and a final report on Day 14
  showing measured cost savings and quality comparison.
- Run all activity through a per-pilot API key (`pilot-<id>`) that
  Customer can revoke at any time.

## 3. What Customer will do

- Drop a small (~3 line) traffic-mirroring snippet into one or more
  application routes, OR enable equivalent mirroring at the proxy layer.
- Provide Provider's deployment with the necessary LLM provider keys
  (Anthropic / OpenAI / etc.) used only for the duration of the pilot.
- Designate one engineering point of contact for the setup call and
  the Day 7 / Day 14 check-ins.

## 4. Data handling

- All traffic processed by the Service stays within Customer's
  environment. The Service does not transmit prompts, responses, or
  derived data to Provider's systems unless Customer explicitly exports
  and sends them.
- A local cache of intermediate results lives in the Customer-controlled
  Redis instance. Customer controls retention and may purge it at any
  time.
- At the end of the pilot, Customer receives all data via the teardown
  script's audit tarball.
- Provider will not access Customer data without Customer's explicit
  written request (e.g., for joint debugging during the pilot).

## 5. Confidentiality

- Any technical or business information shared during the pilot is
  confidential to both parties and not disclosed externally without
  written consent.
- Provider may not use Customer's name in marketing, case studies, or
  any external communication without separate written permission.
- Aggregate, fully anonymized statistics ("a Series-B SaaS company saw
  X% savings") may be referenced by Provider without further consent.

## 6. No SLAs, no warranty

The Service is provided "as is" during the pilot, with no service-level
guarantee. The mirror integration is designed not to affect Customer's
production response path; nevertheless, Customer is responsible for
monitoring its own systems during the pilot.

## 7. Limitation of liability

In no event will Provider's aggregate liability for any claim arising
from this pilot exceed US $1,000. This limit is the express bargain of
the parties; both parties acknowledge the pilot is free.

## 8. End of pilot

At Day 14 (or earlier on notice from either party):
- Customer removes the mirror snippet (1-line change).
- Provider runs `teardown.sh`; logs are archived to a tarball under
  Customer's control.
- Final report is delivered. No further obligation on either party
  unless a paid services agreement is separately signed.

## 9. Signatures

| Customer | Provider |
|---|---|
| Name: | Name: |
| Title: | Title: |
| Date: | Date: |
| Signature: | Signature: |

---

*This is a template. Both parties should have it reviewed by their own
counsel before signing. It is not a substitute for legal advice.*
