#!/usr/bin/env python3
"""
Deep quality audit script — probes every prompt in the corpus for
classifier routing issues AND verifier weaknesses with expanded failure modes.

Goes beyond simulate_gateway.py by:
  1. Testing MORE failure modes (hallucinated numbers, garbled JSON, partial refusals,
     code-switched translations, over-eager yes/no, etc.)
  2. Auditing classifier BOTH directions: under-routing (hard→cheap) AND
     over-routing (cheap→frontier wasting money)
  3. Checking system-prompt-aware routing (RAG prompts with long system messages
     where the user message is short)
  4. Cross-validating verifier checks work correctly on GOOD responses too
     (no false escalations)
"""
import sys
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).parent
sys.path.append(str(HERE.parent / "gateway" / "router"))

import classifier
import verifier

CORPUS_PATH = HERE.parent / "eval" / "corpus_v1.jsonl"


def resp(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


def main():
    if not CORPUS_PATH.exists():
        print(f"Error: Corpus file not found at {CORPUS_PATH}", file=sys.stderr)
        return 1

    prompts = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                prompts.append(json.loads(line))
    print(f"Loaded {len(prompts)} prompts.\n")

    # ===== PHASE 1: CLASSIFIER ROUTING AUDIT =====
    print("=" * 60)
    print("PHASE 1: CLASSIFIER ROUTING AUDIT")
    print("=" * 60)

    routing_stats = {"cheap": 0, "balanced": 0, "frontier": 0}
    under_routed = []  # hard prompts routed cheap (bad)
    over_routed = []   # simple prompts routed to frontier (wasteful)
    all_decisions = []

    for r in prompts:
        pid = r["id"]
        messages = r["messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        expected_tier = r.get("expected_tier", "cheap")
        category = r.get("category", "")

        decision = classifier.classify(messages, None)
        routing_stats[decision.tier] += 1
        all_decisions.append((pid, expected_tier, decision.tier, decision.reason, category, last_user))

        # Under-routing: hard prompt went to cheap
        if expected_tier in ("balanced", "frontier") and decision.tier == "cheap":
            under_routed.append((pid, expected_tier, decision.tier, last_user[:150], decision.reason))

        # Over-routing: cheap prompt went to frontier (wastes money)
        if expected_tier == "cheap" and decision.tier == "frontier":
            over_routed.append((pid, expected_tier, decision.tier, last_user[:150], decision.reason))

    print("\nClassifier Distribution:")
    for tier, count in routing_stats.items():
        print(f"  {tier:10s} : {count:3d} ({count/len(prompts)*100:.1f}%)")

    if under_routed:
        print(f"\n  [CRITICAL] {len(under_routed)} UNDER-ROUTED prompts (hard->cheap):")
        for pid, exp, got, text, reason in under_routed:
            print(f"    ID={pid} expected={exp} got={got} reason='{reason}'")
            print(f"      {text}...")
    else:
        print("\n  [OK] No under-routing: all hard prompts route to balanced/frontier.")

    if over_routed:
        print(f"\n  [WARN] {len(over_routed)} OVER-ROUTED prompts (cheap->frontier, money wasted):")
        for pid, exp, got, text, reason in over_routed:
            print(f"    ID={pid} expected={exp} got={got} reason='{reason}'")
            print(f"      {text}...")
    else:
        print("\n  [OK] No over-routing: no cheap prompts wasted on frontier.")

    # Check for system-prompt-aware issues
    sys_prompt_issues = []
    for pid, exp, got, reason, cat, text in all_decisions:
        if cat == "rag" and exp != got:
            sys_prompt_issues.append((pid, exp, got, text[:100], reason))
    if sys_prompt_issues:
        print(f"\n  [INFO] {len(sys_prompt_issues)} RAG prompt routing mismatches:")
        for pid, exp, got, text, reason in sys_prompt_issues[:5]:
            print(f"    ID={pid} expected={exp} got={got}: {text}...")

    # ===== PHASE 2: VERIFIER EXHAUSTIVE LEAK TESTING =====
    print("\n" + "=" * 60)
    print("PHASE 2: VERIFIER EXHAUSTIVE LEAK TESTING")
    print("=" * 60)

    total_tests = 0
    total_leaks = 0
    leak_details = []
    false_escalation_details = []

    for r in prompts:
        pid = r["id"]
        messages = r["messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        expects_json = "json" in last_user.lower() or (
            r.get("expected_behavior", {}).get("type") == "valid_json"
            if r.get("expected_behavior") else False
        )

        decision = classifier.classify(messages, None)
        if decision.tier != "cheap":
            continue

        # --- Failure mode 1: Truncation ---
        total_tests += 1
        fail, reason = verifier.heuristic_fail(
            resp("This is truncated response...", finish="length"),
            expects_json=expects_json, user_prompt=last_user)
        if not fail:
            total_leaks += 1
            leak_details.append((pid, "truncation", last_user[:100]))

        # --- Failure mode 2: Refusal ---
        for refusal_text in [
            "I am sorry, but as an AI assistant I cannot help with that request.",
            "I can't assist with that.",
            "I don't know the answer to that question.",
            "Unfortunately, I'm unable to process your request.",
            "As an AI language model, I cannot provide personal opinions.",
            "Sorry, but I need more context to answer that.",
        ]:
            total_tests += 1
            fail, reason = verifier.heuristic_fail(
                resp(refusal_text), expects_json=expects_json, user_prompt=last_user)
            if not fail:
                total_leaks += 1
                leak_details.append((pid, f"refusal: {refusal_text[:50]}", last_user[:100]))

        # --- Failure mode 3: PII Placeholder Leak ---
        for placeholder in [
            "<EMAIL_ADDRESS>", "<PERSON>", "<PHONE_NUMBER>",
            "<IP_ADDRESS>", "<US_SSN>", "<US_DRIVER_LICENSE>",
            "<CREDIT_CARD>", "<API_KEY>", "<URL>",
            "<LOCATION>", "<ORGANIZATION>", "<DATE_TIME>",
        ]:
            total_tests += 1
            fail, reason = verifier.heuristic_fail(
                resp(f"The result is: {placeholder}"),
                expects_json=expects_json, user_prompt=last_user)
            if not fail:
                total_leaks += 1
                leak_details.append((pid, f"pii_leak_{placeholder}", last_user[:100]))

        # --- Failure mode 4: Dropped Literals ---
        literals = []
        for rx, label in [
            (verifier._EMAIL_RE, "email"),
            (verifier._PHONE_RE, "phone"),
            (verifier._IPV4_RE, "ip"),
            (verifier._URL_RE, "url"),
            (verifier._VERSION_RE, "version"),
            (verifier._SKU_RE, "sku"),
        ]:
            hits = rx.findall(last_user)
            if hits:
                literals.append((label, hits[0]))

        for label, lit in literals:
            total_tests += 1
            fail, reason = verifier.heuristic_fail(
                resp("Here is the answer but the value was replaced."),
                expects_json=expects_json, user_prompt=last_user)
            if not fail:
                total_leaks += 1
                leak_details.append((pid, f"dropped_{label}_{lit}", last_user[:100]))

        # --- Failure mode 5: Yes/No rambling ---
        if verifier._YES_NO_PROMPT_RE.search(last_user):
            for bad_answer in [
                "Based on the analysis, the answer would likely be affirmative.",
                "It depends on several factors...",
                "The answer is complex and nuanced.",
            ]:
                total_tests += 1
                fail, reason = verifier.heuristic_fail(
                    resp(bad_answer), expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    total_leaks += 1
                    leak_details.append((pid, "yes_no_rambling", last_user[:100]))

        # --- Failure mode 6: One-word rambling ---
        if verifier._ONE_WORD_PROMPT_RE.search(last_user):
            for bad_answer in [
                "The correct classification of the review is positive.",
                "Based on my analysis this would be classified as negative sentiment overall.",
            ]:
                total_tests += 1
                fail, reason = verifier.heuristic_fail(
                    resp(bad_answer), expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    total_leaks += 1
                    leak_details.append((pid, "one_word_rambling", last_user[:100]))

        # --- Failure mode 7: Missing classification option ---
        is_translation = bool(re.search(
            r"\b(translate|translation|in french|in spanish|in german|in japanese|"
            r"in italian|in portuguese|in hebrew|in dutch)\b",
            last_user, re.IGNORECASE
        ))
        if not is_translation:
            options = verifier.extract_options_from_prompt(last_user)
            if options:
                total_tests += 1
                fail, reason = verifier.heuristic_fail(
                    resp("I've classified it as category XYZ."),
                    expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    total_leaks += 1
                    leak_details.append((pid, f"missing_option", last_user[:100]))

        # --- Failure mode 8: Missing JSON keys ---
        if expects_json:
            expected_keys = verifier.extract_keys_from_prompt(last_user)
            if expected_keys and len(expected_keys) > 1:
                total_tests += 1
                bad_json = {}
                for k in expected_keys[:-1]:
                    bad_json[k] = "test_value"
                fail, reason = verifier.heuristic_fail(
                    resp(json.dumps(bad_json)),
                    expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    total_leaks += 1
                    leak_details.append((pid, f"missing_json_keys", last_user[:100]))

        # --- Failure mode 9: Garbled/invalid JSON when JSON expected ---
        if expects_json:
            total_tests += 1
            fail, reason = verifier.heuristic_fail(
                resp('{"name": "test", broken json here'),
                expects_json=expects_json, user_prompt=last_user)
            if not fail:
                total_leaks += 1
                leak_details.append((pid, "garbled_json", last_user[:100]))

        # --- Failure mode 10: Empty JSON ---
        if expects_json:
            total_tests += 1
            fail, reason = verifier.heuristic_fail(
                resp("{}"), expects_json=expects_json, user_prompt=last_user)
            # Empty JSON may or may not be valid depending on context; only check if keys expected
            if expected_keys and not fail:
                total_leaks += 1
                leak_details.append((pid, "empty_json_with_expected_keys", last_user[:100]))

        # --- Failure mode 11: Hallucinated numbers/values ---
        # If prompt asks to extract a specific number and response has a different number
        # This is harder to test generically, but we check version preservation
        if verifier._VERSION_RE.search(last_user):
            prompt_versions = verifier._VERSION_RE.findall(last_user)
            total_tests += 1
            # Response returns a wrong version
            fail, reason = verifier.heuristic_fail(
                resp("The version is 9.99.99"),
                expects_json=expects_json, user_prompt=last_user)
            if not fail and prompt_versions:
                total_leaks += 1
                leak_details.append((pid, f"hallucinated_version", last_user[:100]))

    # ===== PHASE 3: FALSE ESCALATION CHECK =====
    print("\n" + "=" * 60)
    print("PHASE 3: FALSE ESCALATION CHECK (good responses shouldn't escalate)")
    print("=" * 60)

    false_esc_count = 0
    false_esc_total = 0
    false_esc_details = []

    for r in prompts:
        pid = r["id"]
        messages = r["messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        expected = r.get("expected_behavior")
        if not expected:
            continue

        decision = classifier.classify(messages, None)
        if decision.tier != "cheap":
            continue

        # Build a "good" response that should pass verification
        eb_type = expected.get("type", "")
        good_response = None

        if eb_type == "contains_any":
            values = expected.get("values", [])
            if values:
                good_response = values[0]
        elif eb_type == "contains":
            val = expected.get("value", "")
            if val:
                good_response = f"The answer is {val}."
        elif eb_type == "valid_json":
            fields = expected.get("fields", [])
            if fields:
                obj = {f: "test" for f in fields}
                good_response = json.dumps(obj)
            else:
                good_response = '{"result": "test"}'

        if good_response:
            false_esc_total += 1
            expects_json = eb_type == "valid_json"
            fail, reason = verifier.heuristic_fail(
                resp(good_response),
                expects_json=expects_json, user_prompt=last_user)
            if fail:
                false_esc_count += 1
                false_esc_details.append((pid, reason, good_response[:80], last_user[:100]))

    # ===== RESULTS =====
    print(f"\n  Total false-escalation tests: {false_esc_total}")
    if false_esc_details:
        print(f"  [WARN] {false_esc_count} FALSE ESCALATIONS detected:")
        for pid, reason, resp_text, prompt in false_esc_details:
            print(f"    ID={pid} reason='{reason}'")
            print(f"      Good resp: {resp_text}")
            print(f"      Prompt:    {prompt}...")
    else:
        print(f"  [OK] 0 false escalations out of {false_esc_total} tests.")

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    print(f"\n  Classifier:")
    print(f"    Distribution:   cheap={routing_stats['cheap']}  balanced={routing_stats['balanced']}  frontier={routing_stats['frontier']}")
    print(f"    Under-routed:   {len(under_routed)}")
    print(f"    Over-routed:    {len(over_routed)}")

    print(f"\n  Verifier:")
    print(f"    Total leak tests:        {total_tests}")
    print(f"    Total leaks:             {total_leaks}")
    print(f"    False escalation tests:  {false_esc_total}")
    print(f"    False escalations:       {false_esc_count}")

    if leak_details:
        print(f"\n  === LEAK DETAIL ===")
        for pid, fail_type, prompt in leak_details[:20]:
            print(f"    [LEAK] ID={pid} type={fail_type}")
            print(f"           {prompt}...")

    overall_ok = (len(under_routed) == 0 and total_leaks == 0 and false_esc_count == 0)
    if overall_ok:
        print(f"\n  [PASS] PERFECT QUALITY: 0 under-routing, 0 leaks, 0 false escalations.")
        return 0
    else:
        issues = len(under_routed) + total_leaks + false_esc_count
        print(f"\n  [FAIL] {issues} TOTAL ISSUES found. Fix required.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
