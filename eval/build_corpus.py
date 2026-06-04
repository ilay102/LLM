#!/usr/bin/env python3
"""
Build the v0.3 evaluation corpus.

Produces eval/corpus_v1.jsonl — a stratified, frozen, versioned eval set that
can actually detect a 2-point quality change (unlike the 30-prompt v0.2 corpus).

Composition:
  - The existing 200 single-turn prompts (classifier/prompts_to_label.jsonl)
    converted to messages-array format, labelled with their seed tier.
  - 30 multi-turn conversations (tests conversation memory + tier stickiness).
  - 30 long stable-system-prompt / RAG rows (tests prefix caching — the rows
    where provider prompt caching should slash input cost).

Each row:
  {
    "id": int,
    "category": "cheap"|"balanced"|"frontier"|"multiturn"|"rag",
    "messages": [ {role, content}, ... ],
    "expected_tier": "cheap"|"balanced"|"frontier",
    "expected_behavior": {...}   # optional deterministic check
  }

expected_behavior types (checked WITHOUT a judge by eval/run_deterministic.py):
  {"type": "contains", "value": "..."}            case-insensitive substring
  {"type": "contains_any", "values": [...]}       any of
  {"type": "valid_json", "fields": [...]}          parses + has fields
  {"type": "regex", "value": "..."}

Run:  python eval/build_corpus.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT = HERE / "corpus_v1.jsonl"
SRC_PROMPTS = REPO / "classifier" / "prompts_to_label.jsonl"
SRC_LABELS = REPO / "classifier" / "labels_claude.jsonl"


def load_jsonl(p: Path) -> dict[int, dict]:
    out = {}
    with open(p) as f:
        for line in f:
            r = json.loads(line)
            out[r["id"]] = r
    return out


def derive_behavior(prompt: str, tier: str) -> dict | None:
    """Add a deterministic check ONLY where the answer is unambiguous."""
    low = prompt.lower()
    # JSON-output requests -> must be valid JSON
    if re.search(r"\bas json\b|return (a )?json|json object|format as json|to json", low):
        return {"type": "valid_json", "fields": []}
    # Explicit yes/no
    if "yes or no" in low or "yes/no" in low:
        return {"type": "contains_any", "values": ["yes", "no"]}
    # Sentiment with explicit labels
    if "positive" in low and "negative" in low:
        return {"type": "contains_any", "values": ["positive", "negative", "neutral"]}
    return None


# ---------------------------------------------------------------------------
# 30 multi-turn conversations. Each tests whether routing stays coherent and
# the right tier is chosen given conversation context. expected_tier reflects
# the FINAL user turn's complexity.
# ---------------------------------------------------------------------------
MULTITURN = [
    # (expected_tier, [ (role, content), ... ])
    ("cheap", [
        ("user", "I need help with my SaaS dashboard."),
        ("assistant", "Sure — what's the issue?"),
        ("user", "Is the export button usually on the top right or bottom? One word."),
    ]),
    ("balanced", [
        ("user", "We're designing an onboarding email sequence."),
        ("assistant", "Happy to help. How many emails?"),
        ("user", "Three. Write the first one — welcome + one clear next step. Friendly, under 120 words."),
    ]),
    ("frontier", [
        ("user", "We have a latency problem in production."),
        ("assistant", "Tell me more — where's the latency?"),
        ("user", "p99 on our checkout endpoint jumped from 200ms to 2s after we added a fraud-check call. Walk me through how you'd diagnose and the three most likely root causes."),
    ]),
    ("cheap", [
        ("user", "Translate phrases for our UI."),
        ("assistant", "Go ahead."),
        ("user", "Translate to French: 'Save changes'"),
    ]),
    ("balanced", [
        ("user", "Reviewing a teammate's SQL."),
        ("assistant", "Paste it."),
        ("user", "SELECT * FROM orders o JOIN customers c ON o.cust_id=c.id WHERE c.active=1 — what would you improve for performance and correctness?"),
    ]),
    ("frontier", [
        ("user", "Architecture question for our platform."),
        ("assistant", "Sure."),
        ("user", "We're at 50 engineers, $20M ARR, monolith. Reason through whether to start breaking into services now — team topology, deploy risk, the realistic 18-month cost."),
    ]),
    ("cheap", [
        ("user", "Quick classification task."),
        ("assistant", "Ready."),
        ("user", "Is this ticket BILLING or TECHNICAL: 'My card was charged twice this month.'"),
    ]),
    ("balanced", [
        ("user", "Help me summarize a meeting."),
        ("assistant", "Paste the notes."),
        ("user", "Summarize in 3 bullets: we shipped 8/10 sprint items, two blocked on auth team, deploys faster via new CI, two prod incidents from missing feature flags."),
    ]),
    ("frontier", [
        ("user", "Math check for a billing feature."),
        ("assistant", "Go ahead."),
        ("user", "Prove that for any prime p>3, p^2-1 is divisible by 24. Show each step."),
    ]),
    ("cheap", [
        ("user", "Extracting fields."),
        ("assistant", "Sure."),
        ("user", "Pull the total amount from: 'Invoice #4421, total $2,499.50, due March 26.'"),
    ]),
    ("balanced", [
        ("user", "Need a Python helper."),
        ("assistant", "What should it do?"),
        ("user", "Write a function with type hints that retries an HTTP GET up to 3 times with exponential backoff. Explain the backoff choice in one line."),
    ]),
    ("frontier", [
        ("user", "Designing an agent workflow."),
        ("assistant", "Tell me the goal."),
        ("user", "Plan an agent that triages support emails into auto-reply / billing / engineering / human-escalate. Include the tools it calls, safety checks before each action, and the 3 most likely failure modes."),
    ]),
    ("cheap", [
        ("user", "Sentiment please."),
        ("assistant", "Ready."),
        ("user", "Positive or negative: 'Renewed my plan, love the new dashboard.'"),
    ]),
    ("balanced", [
        ("user", "Drafting customer comms."),
        ("assistant", "Sure."),
        ("user", "Write a brief, accountable apology email for a 2-hour outage. No excuses, offer a status page link."),
    ]),
    ("frontier", [
        ("user", "Capacity planning."),
        ("assistant", "Go on."),
        ("user", "We process 100B time-series events/month. Propose a storage + query architecture for sub-second p95 on common aggregations, with a cost model and the main trade-offs."),
    ]),
    ("cheap", [
        ("user", "Yes/no question."),
        ("assistant", "Ask away."),
        ("user", "Is PostgreSQL relational? Yes or no."),
    ]),
    ("balanced", [
        ("user", "Refactor request."),
        ("assistant", "Paste the code."),
        ("user", "Rewrite this to async/await: function getUser(id){return fetch('/u/'+id).then(r=>r.json())}"),
    ]),
    ("frontier", [
        ("user", "Pricing strategy."),
        ("assistant", "Sure."),
        ("user", "Compare per-seat vs per-token vs per-outcome pricing for an AI support product. Buyer psychology, margin impact, adoption risk. Then recommend one."),
    ]),
    ("cheap", [
        ("user", "Format conversion."),
        ("assistant", "Ready."),
        ("user", "Convert to JSON: name=Alice, role=admin, active=true"),
    ]),
    ("balanced", [
        ("user", "SQL help."),
        ("assistant", "Go."),
        ("user", "Write a query: customers who signed up in the last 30 days but haven't logged in this week."),
    ]),
    ("frontier", [
        ("user", "Debugging a heisenbug."),
        ("assistant", "Describe it."),
        ("user", "Background workers occasionally process the same job twice. Give the 5 most likely causes and how to diagnose each — and say whether the fix belongs at the queue, worker, or consumer."),
    ]),
    ("cheap", [
        ("user", "Tagging."),
        ("assistant", "Ready."),
        ("user", "Spam or not spam: 'CLICK NOW to claim your prize!!!'"),
    ]),
    ("balanced", [
        ("user", "Content task."),
        ("assistant", "Sure."),
        ("user", "Write 3 hero-headline options for a SaaS analytics product aimed at early-stage startups."),
    ]),
    ("frontier", [
        ("user", "Migration planning."),
        ("assistant", "Go on."),
        ("user", "We're moving 4TB from MongoDB to Postgres. Design the migration: dual-write window, cutover, rollback plan, and how you validate data integrity throughout."),
    ]),
    ("cheap", [
        ("user", "Extraction."),
        ("assistant", "Ready."),
        ("user", "Extract the email from: 'Reach me at sarah.k@example.org anytime.'"),
    ]),
    ("balanced", [
        ("user", "Explain for a PM."),
        ("assistant", "Sure."),
        ("user", "Explain what a database index is and when to add one, in 3-4 sentences a non-technical PM understands."),
    ]),
    ("frontier", [
        ("user", "Reliability design."),
        ("assistant", "Go."),
        ("user", "Design a webhook delivery system for 1M deliveries/day: retries, dedup, ordering, customer-visible status, backpressure. Specify each component and its failure modes."),
    ]),
    ("cheap", [
        ("user", "Quick check."),
        ("assistant", "Ask."),
        ("user", "What's the capital of France?"),
    ]),
    ("balanced", [
        ("user", "Data wrangling."),
        ("assistant", "Sure."),
        ("user", "Turn this into a markdown table: [{name:Alice,plan:Pro},{name:Bob,plan:Free}]"),
    ]),
    ("frontier", [
        ("user", "Multi-region design."),
        ("assistant", "Go on."),
        ("user", "Architect a multi-region active-active write path. Handle conflict resolution, monotonic reads per user, and regional failover. Discuss CRDTs vs leader-per-record."),
    ]),
]


# ---------------------------------------------------------------------------
# 30 long stable-system-prompt / RAG rows. A big system prompt (the kind real
# SaaS apps send on EVERY call) + a short user turn. These are where provider
# prefix caching should slash input cost — and where v0.2 corpus had nothing.
# ---------------------------------------------------------------------------
SUPPORT_SYSTEM = (
    "You are Aria, the support assistant for Nimbus, a project-management SaaS. "
    "Tone: warm, concise, professional. Always: (1) acknowledge the user's "
    "issue, (2) give the most direct fix first, (3) offer one follow-up. Never "
    "promise refunds — route billing disputes to billing@nimbus.example. We "
    "support web, iOS, Android. Plans: Free (3 projects), Pro ($12/user/mo, "
    "unlimited projects), Enterprise (SSO, audit logs, SLA). Common issues: "
    "sync delays (usually a stale cache — suggest hard refresh), missing "
    "invites (check spam, resend from Settings > Members), export failures "
    "(CSV export is under Project > ... > Export; large exports email a link). "
    "If a user is on Free and asks for an Enterprise feature, mention the "
    "upgrade path without being pushy. Keep replies under 120 words unless the "
    "user explicitly asks for detail. "
) * 3  # repeated to comfortably exceed prompt-cache minimums

RAG_SYSTEM = (
    "Answer ONLY from the provided context. If the answer isn't in the context, "
    "say 'I don't have that information.' Cite the section you used. Context:\n"
    "[Section A — Billing] Nimbus bills monthly on the 1st. Annual plans get "
    "2 months free. Proration applies on mid-cycle upgrades. Refunds within 14 "
    "days of first charge only.\n"
    "[Section B — Security] Data encrypted at rest (AES-256) and in transit "
    "(TLS 1.3). SOC2 Type II since 2024. SSO via SAML on Enterprise. Data "
    "residency: US or EU, chosen at signup.\n"
    "[Section C — Limits] Free: 3 projects, 5 members. Pro: unlimited projects, "
    "100 members. API rate limit: 600 req/min Pro, 2400 Enterprise.\n"
    "[Section D — Integrations] Slack, GitHub, Jira, Google Calendar. Webhooks "
    "on Pro+. Zapier via API key.\n"
) * 2

RAG_QUESTIONS = [
    ("cheap", "What's the API rate limit on Pro?", {"type": "contains", "value": "600"}),
    ("cheap", "Is data encrypted at rest? Yes or no.", {"type": "contains_any", "values": ["yes", "AES"]}),
    ("cheap", "How many projects on the Free plan?", {"type": "contains", "value": "3"}),
    ("cheap", "When does Nimbus bill?", {"type": "contains_any", "values": ["1st", "monthly", "first"]}),
    ("balanced", "A customer upgraded mid-cycle and asks why the charge looks odd. Explain using the context.", None),
    ("balanced", "Summarize the security posture for a prospect's questionnaire, citing sections.", None),
    ("cheap", "Do annual plans get a discount?", {"type": "contains_any", "values": ["2 months", "free", "yes"]}),
    ("cheap", "Which integrations are supported?", {"type": "contains_any", "values": ["Slack", "GitHub", "Jira"]}),
    ("balanced", "A user on Free wants SSO. Explain what's true from the context and the upgrade path.", None),
    ("cheap", "Is there a refund policy? Answer from context.", {"type": "contains", "value": "14 days"}),
]

SUPPORT_QUESTIONS = [
    ("cheap", "My projects aren't syncing. What do I do?"),
    ("cheap", "I didn't get my team invite."),
    ("balanced", "Export keeps failing on a big project and my boss needs it today — walk me through options."),
    ("cheap", "How much is Pro?"),
    ("balanced", "We're evaluating Enterprise. What do we get over Pro, and how do we start?"),
    ("cheap", "Where's the CSV export button?"),
    ("cheap", "Can I get a refund?"),
    ("balanced", "I'm on Free and need audit logs for a compliance review next week. What are my options?"),
    ("cheap", "Does the app work on Android?"),
    ("balanced", "Sync has been delayed for an hour across my whole team — is this an outage or something on our end? Walk me through checks."),
    ("cheap", "How many members on Pro?"),
    ("balanced", "Write a reply to a frustrated user whose export failed twice, on Enterprise, needs it for an audit Friday."),
    ("cheap", "Reset my password — where?"),
    ("balanced", "A user asks to dispute a double charge. Handle it per policy."),
    ("cheap", "Is there an iOS app?"),
    ("balanced", "Explain the difference between Pro and Enterprise to a non-technical buyer in 4 sentences."),
    ("cheap", "What's the rate limit?"),
    ("balanced", "Draft a friendly nudge to a Free user hitting the 3-project limit, mentioning the upgrade without being pushy."),
    ("cheap", "Do you support Slack?"),
    ("balanced", "A customer's invites keep landing in spam org-wide. Give a structured troubleshooting plan."),
]


def main() -> None:
    rows = []
    nid = 1

    # --- 1. Existing 200 single-turn prompts -------------------------------
    prompts = load_jsonl(SRC_PROMPTS)
    labels = load_jsonl(SRC_LABELS)
    for pid in sorted(prompts):
        text = prompts[pid]["prompt"]
        tier = labels.get(pid, {}).get("label", "balanced")
        if tier not in ("cheap", "balanced", "frontier"):
            tier = "balanced"
        rows.append({
            "id": nid,
            "category": tier,
            "messages": [{"role": "user", "content": text}],
            "expected_tier": tier,
            "expected_behavior": derive_behavior(text, tier),
        })
        nid += 1

    # --- 2. Multi-turn -----------------------------------------------------
    for tier, turns in MULTITURN:
        rows.append({
            "id": nid,
            "category": "multiturn",
            "messages": [{"role": r, "content": c} for r, c in turns],
            "expected_tier": tier,
            "expected_behavior": None,
        })
        nid += 1

    # --- 3. RAG (big system + question) ------------------------------------
    for tier, q, behavior in RAG_QUESTIONS:
        rows.append({
            "id": nid,
            "category": "rag",
            "messages": [
                {"role": "system", "content": RAG_SYSTEM},
                {"role": "user", "content": q},
            ],
            "expected_tier": tier,
            "expected_behavior": behavior,
        })
        nid += 1

    # --- 4. Long stable-system-prompt (support bot) ------------------------
    for tier, q in SUPPORT_QUESTIONS:
        rows.append({
            "id": nid,
            "category": "rag",
            "messages": [
                {"role": "system", "content": SUPPORT_SYSTEM},
                {"role": "user", "content": q},
            ],
            "expected_tier": tier,
            "expected_behavior": None,
        })
        nid += 1

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Report
    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    tiers = Counter(r["expected_tier"] for r in rows)
    deterministic = sum(1 for r in rows if r["expected_behavior"])
    print(f"Wrote {len(rows)} rows to {OUT}")
    print(f"  Categories: {dict(cats)}")
    print(f"  Expected tiers: {dict(tiers)}")
    print(f"  Rows with deterministic checks: {deterministic}")


if __name__ == "__main__":
    main()
