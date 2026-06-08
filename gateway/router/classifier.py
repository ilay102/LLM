"""
Complexity classifier — picks a tier (cheap / balanced / frontier).

Two-layer design:
  1. RULE layer (fast, deterministic) — fires on obvious cases.
  2. LEARNED layer — nearest-centroid in bge-small embedding space.
     Trained from `classifier/labels.jsonl` via `classifier/train.py`.
     Weights live at `classifier/weights.npz` and load at startup.

If the trained weights aren't found, the learned layer falls back to a
length+code heuristic and logs a warning. Never silently degrades into
zero-vector classification (we used to; that was a bug).
"""
from __future__ import annotations
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from embeddings import embed

LOG = logging.getLogger("gateway.classifier")
Tier = Literal["cheap", "balanced", "frontier"]


@dataclass
class RouteDecision:
    tier: Tier
    reason: str
    confidence: float


# --- Rule layer -------------------------------------------------------------

REASONING_KEYWORDS = re.compile(
    r"\b(prove|derive|step[- ]by[- ]step|reason|chain[- ]of[- ]thought|"
    r"plan and execute|multi[- ]step|complex algorithm|optimi[sz]e|"
    r"refactor|architect(?:ure)?|design pattern|trade[- ]offs?|agentic|"
    r"compare|comparison|pros\s*and\s*cons|versus|vs\.?|solve|calculate|"
    r"probability|math|logic|prime|divisible|bottleneck|puzzle|riddle|"
    r"propose|strategy|recommend\w*|renegotiat\w*|diagnose|troubleshoot|debug|timezone|"
    r"distributed|off\s+by|outage|incident|failure)\b",
    re.IGNORECASE,
)
# Structured extraction needs precision — route to balanced even when short
EXTRACTION_KEYWORDS = re.compile(
    r"\b(extract|parse|pull (?:out|the)|find all|get the|"
    r"convert (?:to|into) (?:json|yaml|csv|xml)|"
    r"into structured|with fields?|as a json object|"
    r"named entities?|entit(?:y|ies))\b",
    re.IGNORECASE,
)
SIMPLE_KEYWORDS = re.compile(
    r"\b(classify|label|tag|summari[sz]e|translate|rewrite|"
    r"format|yes/no|true/false)\b",
    re.IGNORECASE,
)
CODING_KEYWORDS = re.compile(
    r"\b(write a function|write code|implement a function|implement a class|"
    r"write a script|write a python|write a javascript|write a bash|write a sql|"
    r"write a query|database query|sql query|select.*join|refactor|debug|compile|regex|"
    r"sql|query|queries|select|join|schema|tuple|primitive|"
    r"js|javascript|python|html|css|bash|java|c\+\+|typescript|ts|ruby|php|go\b|rust\b|"
    r"loop|boolean|csv|xml|json|async|await|recursion|markdown|markup|bug\b|function\b|variable\b)\b",
    re.IGNORECASE,
)
COMPLEX_ENGINEERING_KEYWORDS = re.compile(
    r"\b(design|plan|architect|migration?|diagnose|troubleshoot|debug|latency|performance|"
    r"scaling|concurrency|asynchronous|async/await|thread-safe|lock|kubernetes|k8s|postgres|"
    r"mongodb|database|index\w*|sql|query|queries|select|join|optimization|optimize|caching?|"
    r"webhook|queue|circuit\s*breaker|rate\s*limit\w*|sso|auth|jwt|audit\s*log|postmortem|incident|agent|cdn|tcp|udp|dns|api|server|network|"
    r"enterprise|billing|charge|policy|dispute|compliance|questionnaire|security\s*posture|"
    r"export|fail\w*|error)\b",
    re.IGNORECASE,
)
EXPLANATION_KEYWORDS = re.compile(
    r"\b(explain|how do we|how can (?:i|we)|what (?:are|is) the (?:options?|difference|upgrade|steps?)|"
    r"troubleshoot|why did|why is)\b",
    re.IGNORECASE,
)
CRITICAL_BUSINESS_KEYWORDS = re.compile(
    r"\b(compliance|security\s*posture|sso|saml|audit\s*logs?|invoice\s*disputes?)\b",
    re.IGNORECASE,
)
WRITING_KEYWORDS = re.compile(
    r"\b(write|draft|compose|create|generate|nudge|apology|apologize|congratulate|welcome)\b",
    re.IGNORECASE,
)
STRUCTURED_SUMMARIZATION_KEYWORDS = re.compile(
    r"\b(bullets?|bullet\s*points?|takeaways?|tldr|executive|sprint|retro|meeting|incident|key\s*points?)\b",
    re.IGNORECASE,
)

# Short customer-support FAQ questions. These match common ENG/CRITICAL_BUSINESS
# keywords (api, policy, plan, export, csv, billing) but are NOT genuinely
# complex — they're lookups against a knowledge base. Without this guard the
# classifier would route them to balanced and quietly hurt cost savings.
# Deep-audit flagged ids 231/233/240/246 as expected=cheap but got=balanced
# precisely because of this over-match.
SHORT_FAQ_RE = re.compile(
    # "What's the X" / "What is the X" — require an article so bare concept
    # questions like "What is a webhook?" route to balanced instead.
    r"^(what'?s\s+(the|your|my|our)|what\s+is\s+(the|your|my|our)|"
    r"where'?s|where\s+is|how\s+(many|much|do|long|often)|"
    r"is\s+(there|the|this|that|it)|are\s+(there|the|these)|does\s+(the|it|this)|"
    r"do\s+(you|i|we|they)|can\s+(i|we|you)|when\s+(does|is|do))\b",
    re.IGNORECASE,
)

# Anti-match: even short questions starting with FAQ stems can be CONCEPT
# explanation requests that need balanced ("What's the difference between
# SQL and NoSQL?"). If any of these phrases appears, the FAQ rule abstains.
SHORT_FAQ_CONCEPT_EXCLUDE_RE = re.compile(
    r"\b(difference|differences|compare|comparison|pros\s+and\s+cons|"
    r"meaning|explain|explanation|how\s+does|why\s+(is|does|do))\b",
    re.IGNORECASE,
)

# Captures the quoted/apostrophe-delimited source text inside a translate request
_TRANSLATE_SRC = re.compile(r"['‘’\"](.*?)['’\"]", re.DOTALL)
CODE_BLOCK = re.compile(r"```")
TRANSLATION_PATTERN = re.compile(r"\btranslate\b.*\bto\b", re.IGNORECASE)
JSON_MULTIFIELD = re.compile(
    r"\b(?:as|into) (?:a )?json\b.*\b(?:with|fields?|keys?|\(|[a-zA-Z0-9_]+,)\b",
    re.IGNORECASE,
)
FIELD_LIST_PATTERN = re.compile(r"\b(?:fields?|keys?)\b[:\s].*?[,;]", re.IGNORECASE)


def rule_decision(messages, requested_max_tokens):
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(last_user, str):
        return RouteDecision("balanced", "non-text content", 0.6)

    n_chars = len(last_user)
    n_code_blocks = len(CODE_BLOCK.findall(last_user))

    # 1. Reasoning markers -> frontier
    #    Guard: if the prompt is a short classification/tagging task, reasoning
    #    keywords inside quoted options (e.g. 'refactor' as a label choice)
    #    should NOT trigger frontier.  Strip quoted content before matching.
    if REASONING_KEYWORDS.search(last_user):
        is_short_classification = (
            n_chars < 300 and SIMPLE_KEYWORDS.search(last_user)
        )
        if is_short_classification:
            # Remove quoted strings and re-check
            stripped = re.sub(r"['\"\u2018\u2019\u201c\u201d][^'\"\u2018\u2019\u201c\u201d]*['\"\u2018\u2019\u201c\u201d]", "", last_user)
            if REASONING_KEYWORDS.search(stripped):
                return RouteDecision("frontier", "reasoning keywords matched", 0.9)
            # else: keyword was only inside quotes -> treat as classification
        else:
            return RouteDecision("frontier", "reasoning keywords matched", 0.9)

    # 1.5. Critical Business / Security / Enterprise -> balanced.
    # MUST come before SHORT_FAQ so casually-phrased critical topics
    # (e.g. "Can you help with invoice disputes?") aren't downgraded.
    if CRITICAL_BUSINESS_KEYWORDS.search(last_user):
        return RouteDecision("balanced", "critical business/security prompt", 0.9)

    # 1.6. Short FAQ questions -> cheap.
    # Must come BEFORE CODING / COMPLEX_ENGINEERING because those have
    # aggressive keyword sets that match common FAQ words (api, policy, plan,
    # export). Length-gated to < 100 chars + ends-in-? so it only catches
    # genuine short lookups, never long support tickets.
    # Deep-audit ids 231/233/240/246 are the canonical regressions this fixes.
    if (
        n_chars < 100
        and "?" in last_user[:80]   # `?` near the front, allows trailing "Answer from context."
        and SHORT_FAQ_RE.match(last_user.strip())
        and not SHORT_FAQ_CONCEPT_EXCLUDE_RE.search(last_user)
        and n_code_blocks == 0
    ):
        return RouteDecision("cheap", "short FAQ-style lookup", 0.85)

    # 2. Coding or Code Analysis -> balanced
    if CODING_KEYWORDS.search(last_user) or (n_code_blocks >= 1 and n_chars > 250):
        return RouteDecision("balanced", "coding or code-analysis prompt", 0.85)

    # 3. Complex Systems / Engineering -> balanced
    if COMPLEX_ENGINEERING_KEYWORDS.search(last_user) and not (
        SIMPLE_KEYWORDS.search(last_user) or "yes or no" in last_user.lower() or "yes/no" in last_user.lower()
    ):
        return RouteDecision("balanced", "complex engineering/systems prompt", 0.8)

    # 4. Explanation / Troubleshooting -> balanced
    if EXPLANATION_KEYWORDS.search(last_user) and n_chars > 250:
        return RouteDecision("balanced", "explanation or troubleshooting request", 0.85)

    # 5. Creative writing / copywriting -> balanced
    if WRITING_KEYWORDS.search(last_user) and not (
        SIMPLE_KEYWORDS.search(last_user) or "yes or no" in last_user.lower() or "yes/no" in last_user.lower()
    ):
        return RouteDecision("balanced", "creative writing or drafting request", 0.8)

    # 6. Structured or complex summarization -> balanced
    if STRUCTURED_SUMMARIZATION_KEYWORDS.search(last_user):
        return RouteDecision("balanced", "structured or complex summarization", 0.8)

    # 6.5. Summarization of longer text -> balanced
    if "summarize" in last_user.lower() and n_chars > 200:
        return RouteDecision("balanced", "summarization of longer text", 0.8)

    # 7. Upgrade multi-field or structured extractions to balanced
    if EXTRACTION_KEYWORDS.search(last_user) and (
        "fields" in last_user.lower() or "keys" in last_user.lower() or
        "json" in last_user.lower() or "structured" in last_user.lower() or
        "yaml" in last_user.lower() or "csv" in last_user.lower()
    ):
        return RouteDecision("balanced", "multi-field or structured extraction", 0.85)

    # 5. Translations of full sentences/phrases need fluency -> balanced
    if TRANSLATION_PATTERN.search(last_user):
        # Find the content after "translate to X:" to measure length
        m = re.search(r"translate.*?to\s+\w+\s*[:.]?\s*['\"]?(.+?)['\"]?$",
                      last_user, re.IGNORECASE | re.DOTALL)
        content = (m.group(1) if m else last_user).strip()
        if len(content) > 25:
            return RouteDecision("balanced", "translation of multi-word phrase needs fluency", 0.8)
        # short translation (e.g. "Save changes") -> cheap is fine

    # 6. Multi-field JSON extraction -> balanced
    if JSON_MULTIFIELD.search(last_user):
        # Count comma-separated field-like tokens
        comma_count = last_user.count(",")
        if comma_count >= 3:
            return RouteDecision("balanced", "multi-field JSON extraction needs precision", 0.85)

    # 7. Heavy code with long output -> balanced (unchanged)
    if n_code_blocks >= 2 and (requested_max_tokens or 0) > 1500:
        return RouteDecision("balanced", "multi-block code with large output", 0.85)

    # 8. Short + simple-task keywords -> cheap (unchanged)
    if n_chars < 800 and SIMPLE_KEYWORDS.search(last_user):
        return RouteDecision("cheap", "short + simple-task keywords", 0.9)

    # 9. Very short -> cheap (unchanged)
    if n_chars < 250 and n_code_blocks == 0:
        return RouteDecision("cheap", "very short prompt", 0.8)

    return None


# --- Learned layer: nearest-centroid in bge space ---------------------------

_CENTROIDS: np.ndarray | None = None      # shape (n_classes, dim)
_CLASSES: list[str] | None = None         # parallel to centroid rows


def _find_weights() -> Path | None:
    """Search common locations the weights file might live at runtime."""
    env_val = os.environ.get("CLASSIFIER_WEIGHTS", "")
    candidates = [
        Path(env_val) if env_val else None,
        Path("/app/classifier/weights.npz"),
        Path(__file__).resolve().parent.parent.parent / "classifier" / "weights.npz",
        Path.cwd() / "classifier" / "weights.npz",
    ]
    for p in candidates:
        if p and p.exists() and p.is_file():
            return p
    return None


def load_weights() -> bool:
    """Load trained centroids into module state. Returns True on success."""
    global _CENTROIDS, _CLASSES
    path = _find_weights()
    if path is None:
        LOG.warning("classifier weights.npz not found — learned layer will use heuristic. "
                    "Run `python classifier/train.py` to fix.")
        return False
    try:
        data = np.load(path, allow_pickle=False)
        _CENTROIDS = np.asarray(data["centroids"], dtype=np.float32)
        _CLASSES = [str(c) for c in data["classes"]]
        LOG.info("classifier loaded: %d centroids dim=%d classes=%s",
                 _CENTROIDS.shape[0], _CENTROIDS.shape[1], _CLASSES)
        return True
    except Exception as e:
        LOG.exception("failed to load classifier weights from %s: %s", path, e)
        return False


def learned_decision(messages: list[dict]) -> RouteDecision:
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(last_user, str):
        return RouteDecision("balanced", "fallback non-text", 0.5)

    # If trained weights are loaded, use nearest centroid.
    if _CENTROIDS is not None and _CLASSES is not None:
        vec = embed(last_user[:4000])  # cap input so embedding stays fast
        sims = _CENTROIDS @ vec  # cosine sim because vectors are L2-normalised
        order = np.argsort(-sims)
        top, second = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
        margin = float(sims[top] - sims[second])
        tier = _CLASSES[top]
        # Confidence = margin to next class (0..1+), clipped
        conf = max(0.0, min(1.0, 0.5 + margin * 5))
        return RouteDecision(
            tier=tier,                                        # type: ignore[arg-type]
            reason=f"learned: sim_top={sims[top]:.2f} margin={margin:.2f}",
            confidence=conf,
        )

    # Heuristic fallback (only when no trained weights)
    n = len(last_user)
    code = last_user.count("```")
    score_hard = min(n / 4000, 1.0) * 0.55 + min(code / 4, 1.0) * 0.45
    if score_hard > 0.7:
        return RouteDecision("frontier", f"heuristic score={score_hard:.2f}", score_hard)
    if score_hard > 0.35:
        return RouteDecision("balanced", f"heuristic score={score_hard:.2f}", 1 - abs(score_hard - 0.5))
    return RouteDecision("cheap", f"heuristic score={score_hard:.2f}", 1 - score_hard)


def classify(messages: list[dict], requested_max_tokens: int | None = None) -> RouteDecision:
    """Public entry point. Rules first, then learned head."""
    rule = rule_decision(messages, requested_max_tokens)
    if rule is not None:
        return rule
    return learned_decision(messages)
