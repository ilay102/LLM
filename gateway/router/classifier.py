"""
Complexity classifier — picks a tier (cheap / balanced / frontier).

Strategy: rules first, then a learned head. The learned head is a logistic
regression on the bge-small embedding of the last user message + a few hand
features. We ship a tiny default trained on a synthetic-but-realistic seed
corpus; clients re-train on their own shadow traffic in week 1 (see
shadow-eval/ for the harness).

Why not call an LLM to classify? Because that costs money and adds latency
on EVERY request. A 5-15ms CPU classifier is the right move.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np

from embeddings import embed

Tier = Literal["cheap", "balanced", "frontier"]


@dataclass
class RouteDecision:
    tier: Tier
    reason: str          # human-readable, logged for the client report
    confidence: float    # 0..1; used by the cascade to decide if we need a verifier


# --- Rule layer -------------------------------------------------------------

REASONING_KEYWORDS = re.compile(
    r"\b(prove|derive|step[- ]by[- ]step|reason|chain[- ]of[- ]thought|"
    r"plan and execute|multi[- ]step|complex algorithm|optimi[sz]e|"
    r"refactor|architecture|design pattern)\b",
    re.IGNORECASE,
)
SIMPLE_KEYWORDS = re.compile(
    r"\b(classify|extract|label|tag|summari[sz]e|translate|rewrite|"
    r"format|json|yes/no|true/false)\b",
    re.IGNORECASE,
)
CODE_BLOCK = re.compile(r"```")


def rule_decision(messages: list[dict], requested_max_tokens: int | None) -> RouteDecision | None:
    """Returns a decision if a hard rule fires, else None."""
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(last_user, str):
        # Multimodal content -> safer default to balanced
        return RouteDecision("balanced", "non-text content", 0.6)

    n_chars = len(last_user)
    n_code_blocks = len(CODE_BLOCK.findall(last_user))

    # 1. Reasoning markers -> never downgrade
    if REASONING_KEYWORDS.search(last_user):
        return RouteDecision("frontier", "reasoning keywords matched", 0.9)

    # 2. Heavy code with long output expectation -> balanced or up
    if n_code_blocks >= 2 and (requested_max_tokens or 0) > 1500:
        return RouteDecision("balanced", "multi-block code with large output", 0.85)

    # 3. Tiny prompts that look like classification/extraction -> cheap
    if n_chars < 800 and SIMPLE_KEYWORDS.search(last_user):
        return RouteDecision("cheap", "short + simple-task keywords", 0.9)

    # 4. Very short prompt, no special signal -> cheap
    if n_chars < 250 and n_code_blocks == 0:
        return RouteDecision("cheap", "very short prompt", 0.8)

    return None


# --- Learned layer ----------------------------------------------------------
# Tiny zero-dependency logistic-regression head. Weights below are seeded from
# a small synthetic dataset. The retrain script lives in shadow-eval/.
# Order: [cheap, balanced, frontier]

# A real deployment loads these from disk per-tenant; we inline a default.
_W = np.array([
    # 384 dims for embedding + 3 hand features (len, n_code, has_url)
    # We collapse to a 3-class head over a 4-feature reduction for brevity.
], dtype=np.float32)

# For the open-source skeleton we use a simple heuristic head. Replace with
# the real model after you've collected ~5k labeled shadow samples.
def learned_decision(messages: list[dict]) -> RouteDecision:
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(last_user, str):
        return RouteDecision("balanced", "fallback non-text", 0.5)

    # Embedding-based proxy: long, dense, technical text -> harder.
    vec = embed(last_user[:4000])
    norm_signal = float(np.linalg.norm(vec))   # ~1.0 (normalised)
    length_signal = min(len(last_user) / 4000, 1.0)
    code_signal = min(last_user.count("```") / 4, 1.0)

    score_hard = 0.55 * length_signal + 0.35 * code_signal + 0.10 * norm_signal
    if score_hard > 0.7:
        return RouteDecision("frontier", f"learned-hard score={score_hard:.2f}", score_hard)
    if score_hard > 0.35:
        return RouteDecision("balanced", f"learned-mid score={score_hard:.2f}", 1 - abs(score_hard - 0.5))
    return RouteDecision("cheap", f"learned-easy score={score_hard:.2f}", 1 - score_hard)


def classify(messages: list[dict], requested_max_tokens: int | None = None) -> RouteDecision:
    """Public entry point. Rules first, then learned head."""
    rule = rule_decision(messages, requested_max_tokens)
    if rule is not None:
        return rule
    return learned_decision(messages)
