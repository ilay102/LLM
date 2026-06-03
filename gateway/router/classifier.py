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
    r"refactor|architecture|design pattern|trade[- ]offs?)\b",
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
# Captures the quoted/apostrophe-delimited source text inside a translate request
_TRANSLATE_SRC = re.compile(r"['‘’\"](.*?)['’\"]", re.DOTALL)
CODE_BLOCK = re.compile(r"```")


def rule_decision(messages: list[dict], requested_max_tokens: int | None) -> RouteDecision | None:
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    if not isinstance(last_user, str):
        return RouteDecision("balanced", "non-text content", 0.6)

    n_chars = len(last_user)
    n_code_blocks = len(CODE_BLOCK.findall(last_user))

    if REASONING_KEYWORDS.search(last_user):
        return RouteDecision("frontier", "reasoning keywords matched", 0.9)

    if n_code_blocks >= 2 and (requested_max_tokens or 0) > 1500:
        return RouteDecision("balanced", "multi-block code with large output", 0.85)

    # Structured extraction needs faithfulness — cheap models miss fields/formats
    if EXTRACTION_KEYWORDS.search(last_user):
        return RouteDecision("balanced", "structured extraction needs precision", 0.85)

    # Long translation (>50 chars of source text) needs fluency from a stronger model
    if re.search(r"\btranslate\b", last_user, re.IGNORECASE):
        src_texts = _TRANSLATE_SRC.findall(last_user)
        if src_texts and max(len(t) for t in src_texts) > 50:
            return RouteDecision("balanced", "translation of long source text", 0.80)

    if n_chars < 800 and SIMPLE_KEYWORDS.search(last_user):
        return RouteDecision("cheap", "short + simple-task keywords", 0.9)

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
