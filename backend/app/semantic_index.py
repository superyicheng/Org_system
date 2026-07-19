"""Dependency-free local semantic vectors used by the offline demo.

REAL LOGIC: this module creates deterministic feature-hashed vectors and cosine
similarity.  Live LLM calls are never required for retrieval, so the award demo
still proves a real vector lookup when the network is unavailable.
"""

from __future__ import annotations

import hashlib
import math
import re


DIMENSIONS = 256

CONCEPTS = {
    "accelerator": "gpu",
    "accelerators": "gpu",
    "compute": "gpu",
    "cuda": "gpu",
    "embedding": "vectorize",
    "embeddings": "vectorize",
    "embed": "vectorize",
    "vector": "vectorize",
    "vectorizing": "vectorize",
    "k8s": "kubernetes",
    "cluster": "kubernetes",
    "clusters": "kubernetes",
    "diagnostic": "logs",
    "diagnostics": "logs",
    "logging": "logs",
    "log": "logs",
    "incidents": "incident",
    "retrieval": "search",
    "lookup": "search",
    "month": "30-days",
    "monthly": "30-days",
    "cost": "resource-spend",
    "expensive": "resource-spend",
    "resources": "resource-spend",
}


def _words(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())
    return [CONCEPTS.get(word, word) for word in raw]


def embed(text: str) -> list[float]:
    """Create a normalized semantic feature vector with stable hashing."""
    words = _words(text)
    features = list(words)
    features.extend(f"{left}::{right}" for left, right in zip(words, words[1:]))
    compact = " ".join(words)
    features.extend(f"char:{compact[index:index + 4]}" for index in range(max(0, len(compact) - 3)))
    vector = [0.0] * DIMENSIONS
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / magnitude for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right)))
