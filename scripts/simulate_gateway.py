#!/usr/bin/env python3
import sys
import json
import re
from pathlib import Path

# Add gateway/router to Python path
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

    print("====================================================")
    # 1. Load corpus
    prompts = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                prompts.append(json.loads(line))
    print(f"Loaded {len(prompts)} prompts from corpus.")

    # 2. Track stats
    routing_stats = {"cheap": 0, "balanced": 0, "frontier": 0}
    verification_tests = 0
    verification_failures = 0
    leaks = []

    print("\n--- Running Classifier Audit ---")
    for r in prompts:
        pid = r["id"]
        messages = r["messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        expected_tier = r.get("expected_tier", "cheap")
        
        # Run classifier
        decision = classifier.classify(messages, None)
        routing_stats[decision.tier] += 1
        
        # Check if hard prompt got routed to cheap
        if expected_tier in ("balanced", "frontier") and decision.tier == "cheap":
            print(f"  [WARN] Hard prompt (id={pid}, expected={expected_tier}) routed to CHEAP!")
            print(f"         Prompt: {last_user[:120]}...")

    print("\nClassifier Distribution:")
    for tier, count in routing_stats.items():
        print(f"  {tier:10s} : {count:3d} ({count/len(prompts)*100:.1f}%)")

    print("\n--- Running Verifier Audit ---")
    for r in prompts:
        pid = r["id"]
        messages = r["messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        expects_json = "json" in last_user.lower() or r.get("expected_behavior", {}).get("type") == "valid_json" if r.get("expected_behavior") else "json" in last_user.lower()

        # Run verifier tests only on cheap-tier prompts
        decision = classifier.classify(messages, None)
        if decision.tier != "cheap":
            continue

        # We will simulate multiple failure modes for this cheap prompt
        # 1. Truncation failure
        verification_tests += 1
        trunc_resp = resp("This is truncated response...", finish="length")
        fail, reason = verifier.heuristic_fail(trunc_resp, expects_json=expects_json, user_prompt=last_user)
        if not fail:
            verification_failures += 1
            leaks.append((pid, "truncation", last_user, trunc_resp))

        # 2. Refusal failure
        verification_tests += 1
        refusal_resp = resp("I am sorry, but as an AI assistant I cannot help with that request.")
        fail, reason = verifier.heuristic_fail(refusal_resp, expects_json=expects_json, user_prompt=last_user)
        if not fail:
            verification_failures += 1
            leaks.append((pid, "refusal", last_user, refusal_resp))

        # 3. PII Placeholder Leak
        verification_tests += 1
        pii_resp = resp("The requested customer info is: <EMAIL_ADDRESS>")
        fail, reason = verifier.heuristic_fail(pii_resp, expects_json=expects_json, user_prompt=last_user)
        if not fail:
            verification_failures += 1
            leaks.append((pid, "pii_leak", last_user, pii_resp))

        # 4. Dropped Literals
        # Detect if prompt contains URL, email, phone, IP, version, or SKU
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

        if literals:
            # Generate a response that drops the literal completely
            for label, lit in literals:
                verification_tests += 1
                dropped_resp = resp(f"Here is your request answer, but the literal value has been replaced by placeholder text.")
                fail, reason = verifier.heuristic_fail(dropped_resp, expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    verification_failures += 1
                    leaks.append((pid, f"dropped_{label}_{lit}", last_user, dropped_resp))

        # 5. Yes/No rambling
        if verifier._YES_NO_PROMPT_RE.search(last_user):
            verification_tests += 1
            rambling_resp = resp("Based on the search results, yes, that seems to be the correct answer.")
            fail, reason = verifier.heuristic_fail(rambling_resp, expects_json=expects_json, user_prompt=last_user)
            if not fail:
                verification_failures += 1
                leaks.append((pid, "yes_no_rambling", last_user, rambling_resp))

        # 6. One-word rambling
        if verifier._ONE_WORD_PROMPT_RE.search(last_user):
            verification_tests += 1
            verbose_resp = resp("The correct classification of the review is positive.")
            fail, reason = verifier.heuristic_fail(verbose_resp, expects_json=expects_json, user_prompt=last_user)
            if not fail:
                verification_failures += 1
                leaks.append((pid, "one_word_rambling", last_user, verbose_resp))

        # 7. Classification Option missing
        is_translation = bool(re.search(
            r"\b(translate|translation|in french|in spanish|in german|in japanese|"
            r"in italian|in portuguese|in hebrew|in dutch)\b",
            last_user, re.IGNORECASE
        ))
        if not is_translation:
            options = verifier.extract_options_from_prompt(last_user)
            if options:
                verification_tests += 1
                missing_opt_resp = resp("I've classified it as category XYZ.")
                fail, reason = verifier.heuristic_fail(missing_opt_resp, expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    verification_failures += 1
                    leaks.append((pid, f"missing_option_{options}", last_user, missing_opt_resp))

        # 8. Missing JSON keys
        if expects_json:
            expected_keys = verifier.extract_keys_from_prompt(last_user)
            if expected_keys:
                verification_tests += 1
                # Generate JSON response missing one key
                bad_json = {}
                for k in expected_keys[:-1]:
                    bad_json[k] = "test_value"
                bad_json_resp = resp(json.dumps(bad_json))
                fail, reason = verifier.heuristic_fail(bad_json_resp, expects_json=expects_json, user_prompt=last_user)
                if not fail:
                    verification_failures += 1
                    leaks.append((pid, f"missing_json_keys_{expected_keys}", last_user, bad_json_resp))

    print(f"\nVerifier Audit Completed.")
    print(f"Total simulated failure tests run: {verification_tests}")
    print(f"Total leaks (failed to escalate): {verification_failures}")

    if leaks:
        print("\n=== LEAK DETAIL REPORT ===")
        for pid, fail_type, prompt, response in leaks[:15]:
            print(f"\n  [LEAK] Prompt ID {pid} - Type: {fail_type}")
            print(f"         Prompt  : {prompt[:100]}...")
            print(f"         Response: {response['choices'][0]['message']['content']}")
        if len(leaks) > 15:
            print(f"\n  ... and {len(leaks) - 15} more leaks.")
        return 1
    else:
        print("\n[SUCCESS] Perfect verifier quality! 0 leaks detected across all simulated error scenarios.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
