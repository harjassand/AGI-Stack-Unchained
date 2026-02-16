"""Equivalence helpers for byte-level baseline vs candidate checks."""

from __future__ import annotations

import random
from typing import Iterable

from ...v1_7r.canon import canon_bytes, sha256_prefixed

KAT_MESSAGES = [
    b"",
    b"abc",
    b"The quick brown fox jumps over the lazy dog",
    b"The quick brown fox jumps over the lazy dog.",
    b"\x00" * 64,
    b"\xff" * 55,
    b"OpenAI-VAL-v17.0",
    bytes(range(64)),
]


class ValEquivalenceError(ValueError):
    pass


def _iter_random_vectors(*, n_random: int, random_max_len: int, seed: int) -> Iterable[bytes]:
    rng = random.Random(seed)
    for _ in range(n_random):
        bucket = rng.random()
        if bucket < 0.20:
            length = rng.randint(0, min(64, random_max_len))
        elif bucket < 0.70:
            lo = min(65, random_max_len)
            hi = min(1024, random_max_len)
            length = rng.randint(lo, hi) if lo <= hi else rng.randint(0, random_max_len)
        else:
            lo = min(1025, random_max_len)
            hi = random_max_len
            length = rng.randint(lo, hi) if lo <= hi else rng.randint(0, random_max_len)
        yield bytes(rng.getrandbits(8) for _ in range(length))


def vector_suite_hash(vectors_cfg: dict[str, int]) -> str:
    suite = {
        "schema_version": "sha256_vector_suite_v1",
        "n_kat": int(vectors_cfg.get("n_kat", 0)),
        "n_random": int(vectors_cfg.get("n_random", 0)),
        "random_max_len": int(vectors_cfg.get("random_max_len", 0)),
        "random_seed_u64": int(vectors_cfg.get("random_seed_u64", 0)),
    }
    return sha256_prefixed(canon_bytes(suite))


def generate_vector_messages(vectors_cfg: dict[str, int]) -> list[bytes]:
    n_kat = int(vectors_cfg.get("n_kat", 0))
    n_random = int(vectors_cfg.get("n_random", 0))
    random_max_len = int(vectors_cfg.get("random_max_len", 0))
    random_seed_u64 = int(vectors_cfg.get("random_seed_u64", 0))

    if n_kat < 0 or n_random < 0 or random_max_len < 0:
        raise ValEquivalenceError("INVALID:SCHEMA_FAIL")

    out: list[bytes] = []
    for i in range(n_kat):
        out.append(KAT_MESSAGES[i % len(KAT_MESSAGES)])
    out.extend(
        _iter_random_vectors(
            n_random=n_random,
            random_max_len=random_max_len,
            seed=random_seed_u64,
        )
    )
    return out


def build_equivalence_receipt_from_outputs(
    *,
    patch_id: str,
    vectors_cfg: dict[str, int],
    baseline_outputs: list[bytes],
    candidate_outputs: list[bytes],
) -> dict[str, object]:
    if len(baseline_outputs) != len(candidate_outputs):
        raise ValEquivalenceError("INVALID:SEMANTIC_MISMATCH")

    first_mismatch: dict[str, object] | None = None
    for idx, (base, cand) in enumerate(zip(baseline_outputs, candidate_outputs)):
        if cand != base:
            first_mismatch = {
                "index_u64": idx,
                "baseline_out_hash": sha256_prefixed(base),
                "candidate_out_hash": sha256_prefixed(cand),
                "len_u32": len(base),
            }
            break

    return {
        "schema_version": "val_equivalence_receipt_v1",
        "patch_id": patch_id,
        "vector_suite_hash": vector_suite_hash(vectors_cfg),
        "n_tests_total": len(baseline_outputs),
        "first_mismatch": first_mismatch,
        "pass": first_mismatch is None,
    }


__all__ = [
    "ValEquivalenceError",
    "build_equivalence_receipt_from_outputs",
    "generate_vector_messages",
    "vector_suite_hash",
]
