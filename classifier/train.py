"""
Train the real complexity classifier.

Approach: nearest-centroid in bge-small embedding space.
Why: small dataset (200), three classes, fast inference (numpy dot product),
no PyTorch dependency at runtime, no overfitting risk vs. a deep model.

Inputs:
    classifier/prompts_to_label.jsonl
    classifier/labels_claude.jsonl   (or labels.jsonl if humans relabeled)

Outputs:
    classifier/weights.npz   <- centroids + metadata, loaded by gateway at startup
    classifier/meta.json     <- training stats for the audit trail
    classifier/confusion.txt <- confusion matrix for the readme

Run:
    cd classifier && python train.py
"""
from __future__ import annotations
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
PROMPTS = HERE / "prompts_to_label.jsonl"
LABELS = HERE / "labels.jsonl"             # human-overridden if present
SEED_LABELS = HERE / "labels_claude.jsonl"  # fallback to Claude seed
OUT_WEIGHTS = HERE / "weights.npz"
OUT_META = HERE / "meta.json"
OUT_CONFUSION = HERE / "confusion.txt"

CLASSES = ["cheap", "balanced", "frontier"]


def load_jsonl(path: Path) -> dict:
    out = {}
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            out[r["id"]] = r
    return out


def main() -> int:
    print("Loading bge-small (one-time download, ~130MB)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    # Use human labels if they exist, else fall back to Claude seed labels
    labels_path = LABELS if LABELS.exists() else SEED_LABELS
    if not labels_path.exists():
        print(f"ERROR: no labels file found at {LABELS} or {SEED_LABELS}", file=sys.stderr)
        return 1
    print(f"Loading labels from {labels_path.name}")

    prompts = load_jsonl(PROMPTS)
    labels = load_jsonl(labels_path)

    common = sorted(set(prompts) & set(labels))
    print(f"  prompts: {len(prompts)}  labels: {len(labels)}  common: {len(common)}")

    # Skip labels that aren't in our class set (e.g. "skip")
    pairs = [(prompts[i]["prompt"], labels[i]["label"]) for i in common
             if labels[i]["label"] in CLASSES]
    print(f"  usable training rows: {len(pairs)}")
    print(f"  distribution: {Counter(l for _, l in pairs)}")

    if len(pairs) < 30:
        print("ERROR: need at least 30 labeled rows to train", file=sys.stderr)
        return 1

    # Compute embeddings (L2-normalised so cosine == dot product)
    print("Embedding prompts...")
    t0 = time.time()
    texts = [t for t, _ in pairs]
    embeddings = model.encode(texts, normalize_embeddings=True,
                              show_progress_bar=True, batch_size=32)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    print(f"  embedded {len(texts)} prompts in {time.time()-t0:.1f}s "
          f"dim={embeddings.shape[1]}")

    # ----- Train: 80/20 split, stratified by label -----
    rng = np.random.default_rng(seed=42)
    by_class = {c: [] for c in CLASSES}
    for idx, (_, lab) in enumerate(pairs):
        by_class[lab].append(idx)

    train_idx, test_idx = [], []
    for cls, idxs in by_class.items():
        rng.shuffle(idxs)
        n_test = max(1, len(idxs) // 5)
        test_idx.extend(idxs[:n_test])
        train_idx.extend(idxs[n_test:])

    # Compute one centroid per class from training set
    centroids = np.zeros((len(CLASSES), embeddings.shape[1]), dtype=np.float32)
    for ci, cls in enumerate(CLASSES):
        cls_idxs = [i for i in train_idx if pairs[i][1] == cls]
        if not cls_idxs:
            print(f"ERROR: no training data for class {cls}", file=sys.stderr)
            return 1
        # Mean of normalised embeddings, then re-normalise so dot-product == cosine sim
        mean = embeddings[cls_idxs].mean(axis=0)
        mean /= np.linalg.norm(mean) + 1e-12
        centroids[ci] = mean
        print(f"  centroid[{cls}]: {len(cls_idxs)} samples, "
              f"intra-class avg sim = "
              f"{float((embeddings[cls_idxs] @ mean).mean()):.3f}")

    # ----- Evaluate on held-out test set -----
    def predict(vec: np.ndarray) -> str:
        sims = centroids @ vec
        return CLASSES[int(np.argmax(sims))]

    test_correct = 0
    confusion = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    per_class = {c: [0, 0] for c in CLASSES}  # [correct, total]
    for i in test_idx:
        vec = embeddings[i]
        true = pairs[i][1]
        pred = predict(vec)
        ti, pi = CLASSES.index(true), CLASSES.index(pred)
        confusion[ti][pi] += 1
        per_class[true][1] += 1
        if pred == true:
            test_correct += 1
            per_class[true][0] += 1

    acc = test_correct / len(test_idx) if test_idx else 0
    print()
    print(f"Held-out accuracy: {acc:.1%} ({test_correct}/{len(test_idx)})")
    print(f"Per-class:")
    for c in CLASSES:
        corr, tot = per_class[c]
        rate = corr / tot if tot else 0
        print(f"  {c:9s}  {corr}/{tot}  ({rate:.0%})")

    # ----- Save -----
    np.savez(
        OUT_WEIGHTS,
        centroids=centroids,
        classes=np.array(CLASSES),
        dim=np.array([embeddings.shape[1]]),
    )
    print(f"  saved weights -> {OUT_WEIGHTS}")

    meta = {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "labels_source": labels_path.name,
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "held_out_accuracy": acc,
        "per_class_accuracy": {c: (corr / tot if tot else 0)
                               for c, (corr, tot) in per_class.items()},
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "embedding_dim": int(embeddings.shape[1]),
        "approach": "nearest centroid in normalised embedding space",
        "note": "If accuracy < 0.85, re-label disagreements and re-train. "
                "Rule layer still runs first; learned layer is fallback for unmatched.",
    }
    OUT_META.write_text(json.dumps(meta, indent=2))
    print(f"  saved meta    -> {OUT_META}")

    # Confusion as a tiny text matrix
    rows = ["", "Confusion matrix (rows=true, cols=pred):", "         " + "  ".join(f"{c:>9}" for c in CLASSES)]
    for ti, c in enumerate(CLASSES):
        rows.append(f"  {c:7s}  " + "  ".join(f"{confusion[ti][pi]:>9}" for pi in range(len(CLASSES))))
    rows.append("")
    rows.append(f"Held-out accuracy: {acc:.1%} ({test_correct}/{len(test_idx)})")
    OUT_CONFUSION.write_text("\n".join(rows))
    print(f"  saved confusion -> {OUT_CONFUSION}")

    return 0 if acc >= 0.70 else 2  # exit 2 if accuracy too low to ship


if __name__ == "__main__":
    sys.exit(main())
