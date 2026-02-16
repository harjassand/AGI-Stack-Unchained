"""Deterministic hashed n-gram embeddings for offline retrieval."""

from __future__ import annotations

import re
from typing import Iterable

from blake3 import blake3


EMBED_DIM = 256
NGRAM_SIZES = (1, 2, 3)
MAX_TOKENS = 256
MAX_NGRAMS = 2048


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return tokens[:MAX_TOKENS]


def embed_text(text: str, *, dim: int = EMBED_DIM) -> list[int]:
    tokens = tokenize(text)
    vec = [0] * dim
    ngrams_added = 0
    for n in NGRAM_SIZES:
        for i in range(len(tokens) - n + 1):
            gram = " ".join(tokens[i : i + n])
            idx = _hash_to_index(gram, dim)
            vec[idx] += n
            ngrams_added += 1
            if ngrams_added >= MAX_NGRAMS:
                return vec
    return vec


def dot(a: Iterable[int], b: Iterable[int]) -> int:
    return sum(x * y for x, y in zip(a, b))


def _hash_to_index(token: str, dim: int) -> int:
    digest = blake3(token.encode("utf-8")).digest(length=4)
    return int.from_bytes(digest, "big") % dim
