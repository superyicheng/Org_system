import hashlib
import math
import re


EMBEDDING_DIMENSIONS = 384


def _tokens(text: str) -> list[str]:
    """Create mixed word/character n-grams that work offline for CN/EN logs."""

    normalized = text.lower().strip()
    words = re.findall(r"[a-z0-9_./:-]+", normalized)
    compact_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    cjk_ngrams = [compact_cjk[i : i + 2] for i in range(max(0, len(compact_cjk) - 1))]
    return words + cjk_ngrams


def embed_text(text: str) -> list[float]:
    """Return a deterministic local embedding without a model download.

    This is intentionally lightweight for the hackathon. It still produces real
    vectors consumed by ChromaDB; step 2 can query the exact same embedding space.
    """

    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]

