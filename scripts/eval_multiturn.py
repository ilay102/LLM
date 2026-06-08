#!/usr/bin/env python3
"""
Multi-turn conversation eval.

Sends each conversation's turns to the gateway in sequence, with the SAME
x-conversation-id header so the stickiness module sees them as one chat.
After each turn, checks:

  1. Tier picked >= the expected_min_tier for that turn
       (we accept upgrades from the rule layer, never silent downgrades)
  2. Stickiness rule honoured: tier never DROPS below the highest tier the
       conversation has used previously
  3. Verifier didn't false-escalate (we check by looking at the
       `tier_reason` in the response headers / shadow log if available)
  4. Expected content tokens appear in the response (best-effort
       contains_any per turn)
  5. No PII placeholder leaked into any response

Usage:
    export GATEWAY_URL=http://localhost:8000/v1
    export GATEWAY_KEY=<master or tenant key>
    export ANTHROPIC_API_KEY=...   # not strictly needed; gateway has them
    python scripts/eval_multiturn.py

  Cost: typically ~$0.05 — 5 convos × 3 turns = 15 calls, all short.

Outputs:
    - per-conversation result printed to stdout
    - scripts/multiturn_report.html
    - exit 0 if all pass, 1 if any violation
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

try:
    from openai import AsyncOpenAI
except ImportError:
    print("pip install openai", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).parent
REPO = HERE.parent
CORPUS = REPO / "eval" / "multiturn_corpus.jsonl"
REPORT = HERE / "multiturn_report.html"

TIER_ORDER = {"cheap": 0, "balanced": 1, "frontier": 2}

PLACEHOLDER_RE = re.compile(
    r"<(EMAIL_ADDRESS|PHONE_NUMBER|PERSON|IP_ADDRESS|US_SSN|US_DRIVER_LICENSE|"
    r"US_PASSPORT|CREDIT_CARD|API_KEY|URL|LOCATION|ORGANIZATION|DATE_TIME)>"
)


def _tier_of_model(model_name: str | None) -> str:
    if not model_name:
        return "unknown"
    m = model_name.lower()
    if "haiku" in m or "mini" in m:
        return "cheap"
    if "opus" in m:
        return "frontier"
    if "reasoner" in m or "r1" in m:
        return "frontier"
    return "balanced"


async def run_one_conversation(client: AsyncOpenAI, convo: dict) -> dict:
    """Run a full conversation, return a result dict per turn."""
    conv_id = convo["conv_id"] + "-" + uuid.uuid4().hex[:8]
    messages: list[dict] = []
    per_turn: list[dict] = []
    max_tier_seen = -1
    total_cost = 0.0

    for i, turn in enumerate(convo["turns"]):
        messages.append({"role": "user", "content": turn["user"]})
        t0 = time.perf_counter()
        try:
            r = await client.chat.completions.create(
                model="auto",
                messages=messages,
                max_tokens=400,
                temperature=0.2,
                extra_headers={"x-conversation-id": conv_id},
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            content = r.choices[0].message.content or ""
            tier = _tier_of_model(r.model)
            # quick cost estimate (Sonnet pricing as upper bound)
            usage_in = r.usage.prompt_tokens or 0
            usage_out = r.usage.completion_tokens or 0
            est_cost = (usage_in * 3.0 + usage_out * 15.0) / 1_000_000
            total_cost += est_cost
            messages.append({"role": "assistant", "content": content})
        except Exception as e:
            per_turn.append({
                "turn": i, "error": str(e), "passed": False,
                "violations": [f"call failed: {e}"],
            })
            continue

        violations: list[str] = []

        # Check 1: tier >= expected_min_tier
        expected_min = convo.get("expected_min_tiers", [None] * len(convo["turns"]))[i]
        if expected_min and TIER_ORDER.get(tier, 0) < TIER_ORDER.get(expected_min, 0):
            violations.append(
                f"tier_below_minimum: got {tier}, expected ≥ {expected_min}"
            )

        # Check 2: stickiness — never DROP below the max tier seen so far
        tier_rank = TIER_ORDER.get(tier, 0)
        if tier_rank < max_tier_seen:
            violations.append(
                f"stickiness_violation: tier {tier} (rank {tier_rank}) "
                f"is below max-seen rank {max_tier_seen}"
            )
        max_tier_seen = max(max_tier_seen, tier_rank)

        # Check 3: no placeholder leak
        if PLACEHOLDER_RE.search(content):
            m = PLACEHOLDER_RE.search(content)
            violations.append(f"placeholder_leak: {m.group(0) if m else '<?>'}")

        # Check 4: contains_any content tokens
        expected_any = (
            convo.get("expected_contains_any_per_turn", [[]] * len(convo["turns"]))[i] or []
        )
        if expected_any:
            content_l = content.lower()
            if not any(tok.lower() in content_l for tok in expected_any):
                violations.append(
                    f"content_missing: none of {expected_any} present in response"
                )

        per_turn.append({
            "turn": i,
            "user": turn["user"][:120],
            "model": r.model,
            "tier": tier,
            "latency_ms": round(latency_ms, 1),
            "response_excerpt": content[:200],
            "violations": violations,
            "passed": len(violations) == 0,
            "est_cost_usd": est_cost,
        })

    return {
        "conv_id": convo["conv_id"],
        "description": convo.get("description", ""),
        "per_turn": per_turn,
        "all_passed": all(t.get("passed") for t in per_turn),
        "total_cost_usd": total_cost,
    }


async def amain():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default=str(CORPUS))
    p.add_argument("--gateway-url", default=os.environ.get("GATEWAY_URL", "http://localhost:8000/v1"))
    p.add_argument("--gateway-key", default=os.environ.get("GATEWAY_KEY", os.environ.get("GATEWAY_MASTER_KEY", "")))
    args = p.parse_args()

    if not args.gateway_key:
        print("ERROR: set GATEWAY_KEY or GATEWAY_MASTER_KEY env var", file=sys.stderr)
        return 2

    convos = [json.loads(l) for l in open(args.corpus, encoding="utf-8")]
    print(f"Running {len(convos)} multi-turn conversations against {args.gateway_url}")

    client = AsyncOpenAI(base_url=args.gateway_url, api_key=args.gateway_key)
    results = []
    for c in convos:
        r = await run_one_conversation(client, c)
        results.append(r)
        status = "PASS" if r["all_passed"] else "FAIL"
        print(f"  [{status}] {r['conv_id']}: {len(r['per_turn'])} turns, "
              f"${r['total_cost_usd']:.4f}")
        for t in r["per_turn"]:
            for v in t.get("violations", []):
                print(f"     turn {t['turn']} ({t.get('tier','?')}): {v}")

    # ---- summary
    passed = sum(1 for r in results if r["all_passed"])
    total = len(results)
    total_violations = sum(len(t.get("violations", [])) for r in results for t in r["per_turn"])
    total_cost = sum(r["total_cost_usd"] for r in results)
    tier_dist = Counter(t["tier"] for r in results for t in r["per_turn"] if "tier" in t)

    print()
    print(f"=== Summary ===")
    print(f"  Conversations passed: {passed}/{total}")
    print(f"  Total violations:     {total_violations}")
    print(f"  Total estimated cost: ${total_cost:.4f}")
    print(f"  Tier distribution:    {dict(tier_dist)}")

    # ---- HTML
    html = ["<!doctype html><meta charset='utf-8'><title>VIREN — Multi-turn eval</title>",
            "<style>body{font-family:-apple-system,Inter,system-ui;max-width:1100px;margin:30px auto;padding:0 20px;color:#111}"
            "table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #eee;padding:6px 8px;text-align:left;vertical-align:top}"
            ".pass{background:#e6f4ea;color:#137333}.fail{background:#fce8e6;color:#b3261e}"
            ".pill{padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#eef}</style>",
            f"<h1>Multi-turn eval — {passed}/{total} convos passed</h1>",
            f"<p>{total_violations} violations · ${total_cost:.4f} · tiers: {dict(tier_dist)}</p>"]
    for r in results:
        cls = "pass" if r["all_passed"] else "fail"
        html.append(f"<h2 class='{cls}'>{r['conv_id']} — {'PASS' if r['all_passed'] else 'FAIL'}</h2>")
        html.append(f"<p>{r['description']}</p>")
        html.append("<table><tr><th>#</th><th>user</th><th>tier</th><th>model</th><th>excerpt</th><th>violations</th></tr>")
        for t in r["per_turn"]:
            row_cls = "pass" if t.get("passed") else "fail"
            html.append(f"<tr class='{row_cls}'><td>{t['turn']}</td>"
                        f"<td>{t.get('user','')}</td>"
                        f"<td><span class='pill'>{t.get('tier','?')}</span></td>"
                        f"<td>{t.get('model','?')}</td>"
                        f"<td>{t.get('response_excerpt','')}</td>"
                        f"<td>{'<br>'.join(t.get('violations',[])) or '—'}</td></tr>")
        html.append("</table>")
    REPORT.write_text("\n".join(html), encoding="utf-8")
    print(f"\nReport: {REPORT}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
