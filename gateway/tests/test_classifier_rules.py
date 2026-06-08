import pytest
from classifier import rule_decision

pytestmark = pytest.mark.unit


def msg(text):
    return [{"role": "user", "content": text}]


def test_reasoning_keywords_go_frontier():
    d = rule_decision(msg("Prove that 1+1=2 step by step."), None)
    assert d is not None
    assert d.tier == "frontier"


def test_simple_short_classification_goes_cheap():
    d = rule_decision(msg("Classify this sentiment: 'great product'"), None)
    assert d is not None
    assert d.tier == "cheap"


def test_very_short_no_signal_goes_cheap():
    d = rule_decision(msg("What is 2+2?"), None)
    assert d is not None
    assert d.tier == "cheap"


def test_medium_unmatched_returns_none():
    """Medium-length, no keywords -> rule layer abstains, learned layer decides."""
    text = "Mesopotamia is a historical region in Western Asia situated within the Tigris–Euphrates river system, in the northern part of the Fertile Crescent, in modern days roughly corresponding to most of Iraq, Kuwait, the eastern parts of Syria, Southeastern Turkey, and regions along the Turkish–Syrian and Iran–Iraq borders."
    d = rule_decision(msg(text), None)
    assert d is None


def test_non_text_content_goes_balanced():
    d = rule_decision([{"role": "user", "content": [{"type": "image_url", "url": "..."}]}], None)
    assert d is not None
    assert d.tier == "balanced"


def test_translation_of_long_phrase_goes_balanced():
    """Pin: TRANSLATION_PATTERN with content > 25 chars -> balanced.
    Eval id 25 ('Translate to Italian: ...') depends on this upgrade
    so the cheap tier doesn't butcher fluency."""
    d = rule_decision(msg("Translate to Italian: 'Forgot password? Reset it here.'"), None)
    assert d is not None
    assert d.tier == "balanced", f"translation should upgrade to balanced, got {d.tier} ({d.reason})"


def test_translation_of_short_phrase_stays_cheap():
    """Pin: short translations don't waste the balanced tier."""
    d = rule_decision(msg("Translate to French: 'Save'"), None)
    # Either matches SIMPLE_KEYWORDS (translate) -> cheap, or no rule -> None.
    # Both outcomes are acceptable. What we forbid is balanced/frontier.
    assert d is None or d.tier == "cheap"


def test_extract_short_goes_cheap_after_pii_fix():
    """Pin: short extraction prompts (id 12, 14, 15, 17, 18) should hit cheap.
    They lost in pre-v0.2.3 evals due to PII corruption, NOT routing.
    With the PII fix landed, cheap is the right tier for these — they're
    one-line extractions where Sonnet would be overkill."""
    for short_extract in [
        "Extract email and phone from: 'Reach me at sarah.k@example.org or 555-0142.'",
        "Extract product SKU from: 'Order shipped: SKU-A7-2231 (qty 3).'",
        "Find all person names in: 'Alice and Bob met with Carlos to discuss the proposal.'",
        "Pull the version number from: 'Upgraded to v3.14.2 last Tuesday.'",
        "Get the IP address from: 'Login attempt from 192.168.1.55 at 03:42 UTC.'",
    ]:
        d = rule_decision(msg(short_extract), None)
        # Short + EXTRACTION/SIMPLE keyword should route to cheap.
        # If a future change wants to send these to balanced, it must
        # justify the cost vs. quality trade explicitly.
        assert d is not None, f"rule layer abstained on short extraction: {short_extract!r}"
        assert d.tier == "cheap", (
            f"short extraction should stay cheap (post-PII-fix); got {d.tier} "
            f"on {short_extract!r} reason={d.reason}"
        )


def test_multi_field_json_extraction_goes_balanced():
    """Pin: JSON_MULTIFIELD with 3+ fields -> balanced for precision."""
    d = rule_decision(msg(
        "Convert this into a JSON object with fields name, email, phone, "
        "address, role for the contact: ..."
    ), None)
    assert d is not None
    assert d.tier == "balanced"


def test_multi_codeblock_with_large_output_goes_balanced():
    text = "```python\nprint(1)\n```\nAnd also:\n```sql\nSELECT 1;\n```"
    d = rule_decision(msg(text), requested_max_tokens=2000)
    assert d is not None
    assert d.tier == "balanced"


def test_critical_business_keywords_go_balanced():
    """Pin: Critical business terms (security posture, compliance, etc.) route to balanced."""
    for prompt in [
        "Summarize the security posture for a prospect's questionnaire, citing sections.",
        "We need an audit log for our compliance review next week.",
        "Can you help with invoice disputes?",
    ]:
        d = rule_decision(msg(prompt), None)
        assert d is not None
        assert d.tier == "balanced", f"Expected balanced for critical business keyword in: {prompt}"


def test_failing_export_goes_balanced():
    """Pin: Export failing / errors route to balanced."""
    d = rule_decision(msg("Export keeps failing on a big project and my boss needs it today — walk me through options."), None)
    assert d is not None
    assert d.tier == "balanced"


def test_outage_incident_failure_go_frontier():
    """Pin: Outages/incidents/failures in troubleshooting go to frontier as diagnostic puzzles."""
    for prompt in [
        "Sync has been delayed for an hour across my whole team — is this an outage or something on our end?",
        "We are experiencing a major system failure in production.",
    ]:
        d = rule_decision(msg(prompt), None)
        assert d is not None
        assert d.tier == "frontier"


def test_reasoning_keyword_inside_quoted_option_avoids_frontier():
    """Pin: 'refactor' as a classification label shouldn't trigger frontier.
    Eval id 9 depends on this — it's a simple tag task.
    It may route to balanced (due to 'bug' in 'bugfix' matching CODING_KEYWORDS)
    which is acceptable over-routing (quality > price)."""
    d = rule_decision(msg(
        "Tag this PR description as 'feature', 'bugfix', or 'refactor': "
        "'Memoize expensive recomputation in dashboard.'"
    ), None)
    assert d is not None
    assert d.tier != "frontier", (
        f"short classification with reasoning keyword in quotes should NOT go frontier, "
        f"got {d.tier} ({d.reason})"
    )


def test_short_faq_lookups_go_cheap():
    """Pin: short customer-FAQ questions go to cheap. Without this guard
    they hit COMPLEX_ENGINEERING_KEYWORDS (api, policy, plan, export, csv)
    and quietly waste balanced-tier spend. Deep audit ids 231/233/240/246
    are the canonical regression cases."""
    for faq in [
        "What's the API rate limit on Pro?",
        "How many projects on the Free plan?",
        "Is there a refund policy?",
        "Where's the CSV export button?",
        "Do you support Slack?",
        "When does Nimbus bill?",
        "Can I get a refund?",
        "Does the app work on Android?",
        "Reset my password — where?",  # ends in '?' but no FAQ stem — should NOT match
    ]:
        d = rule_decision(msg(faq), None)
        if faq.startswith("Reset"):
            # Sanity check: imperative form should NOT match the FAQ rule.
            # Either rule layer abstains or routes via a different rule.
            assert d is None or d.tier in ("cheap", "balanced"), \
                f"imperative shouldn't go frontier, got {d.tier if d else None}"
            continue
        assert d is not None, f"FAQ rule abstained: {faq!r}"
        assert d.tier == "cheap", (
            f"short FAQ should be cheap, got {d.tier} on {faq!r} (reason: {d.reason})"
        )


def test_short_faq_rule_doesnt_swallow_real_complex_questions():
    """Guard: the FAQ rule is length-gated to <100 chars. Longer customer-
    support prompts that include real diagnostic detail must still route
    to balanced/frontier."""
    long_support = (
        "What's happening with our integration? Webhooks have been failing "
        "intermittently for the past 4 hours and our customers are complaining."
    )
    d = rule_decision(msg(long_support), None)
    # Whatever happens, must NOT downgrade to cheap.
    assert d is None or d.tier != "cheap", \
        f"long support ticket should not route to cheap, got {d.tier if d else None}"


def test_comparison_question_doesnt_match_faq():
    """Pin: 'What's the difference between X and Y?' is a comparison/concept
    question requiring balanced, not a cheap lookup. Deep-audit id 142 is
    this regression case."""
    for prompt in [
        "What's the difference between SQL and NoSQL? Keep under 100 words.",
        "What's the comparison between TCP and UDP?",
        "Can you explain the difference between cheap and balanced?",
    ]:
        d = rule_decision(msg(prompt), None)
        # Forbid: FAQ rule firing on comparison/concept questions.
        if d is not None:
            assert "FAQ" not in d.reason, \
                f"comparison should NOT match FAQ rule, got reason={d.reason!r} on {prompt!r}"


def test_bare_concept_question_doesnt_match_faq():
    """Pin: 'What is a webhook?' is a CONCEPT question (needs prose
    explanation), not a lookup. SHORT_FAQ requires 'what's THE X' or
    'what is THE X' — bare 'what is a/an X' must fall through to whatever
    the next rule decides. Deep-audit id 145 is this regression case."""
    d = rule_decision(msg("What is a webhook and when should I use one?"), None)
    # The FAQ rule must NOT fire. Next rule may decide cheap or balanced
    # depending on length/keywords — what's forbidden is falsely tagging
    # this with the FAQ reason.
    if d is not None:
        assert "FAQ" not in d.reason, \
            f"bare 'what is a X' should NOT match FAQ rule, got reason={d.reason!r}"


def test_short_faq_doesnt_override_explicit_reasoning():
    """Guard: a short question that contains a reasoning keyword (e.g. 'prove')
    must still route to frontier. SHORT_FAQ must be ordered AFTER REASONING."""
    d = rule_decision(msg("What's the proof that 2+2=4? Derive it."), None)
    assert d is not None
    assert d.tier == "frontier", \
        f"reasoning keyword must win over FAQ stem, got {d.tier}"


def test_real_reasoning_prompt_still_goes_frontier():
    """Sanity: a genuine reasoning request with the same keyword must still go frontier."""
    d = rule_decision(msg(
        "Please refactor this authentication module to use the strategy pattern "
        "and explain your design trade-offs step by step."
    ), None)
    assert d is not None
    assert d.tier == "frontier"

