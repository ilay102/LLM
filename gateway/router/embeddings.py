"""
Lightweight local embedding model. We use bge-small-en-v1.5:
  - 384 dims, fast on CPU (~5-15ms per query)
  - Free (no API call) -> embedding cost is not a routing tax
  - Good enough for both semantic-cache lookup and complexity classification

Loaded once at startup; the model is ~130MB and lives in memory.
Requires sentence-transformers and torch — see gateway/router/requirements.txt.
If you hit an ImportError here, you are on the wrong base image (need glibc,
not musl). See CONTRIBUTING.md.
"""
from __future__ import annotations
import threading
import numpy as np
from sentence_transformers import SentenceTransformer

EMBED_DIM = 384

_MODEL: SentenceTransformer | None = None
_LOCK = threading.Lock()


def get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                _MODEL = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _MODEL


def embed(text: str) -> np.ndarray:
    """L2-normalised embedding so cosine == dot product."""
    vec = get_model().encode(text, normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)
