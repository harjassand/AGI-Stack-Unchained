"""WorkVec v1 counters and instrumentation for metabolism v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from ...v1_7r.canon import canon_bytes as _canon_bytes


WORKVEC_FIELDS = (
    "sha256_calls_total",
    "canon_calls_total",
    "sha256_bytes_total",
    "canon_bytes_total",
    "onto_ctx_hash_compute_calls_total",
)


@dataclass
class WorkVec:
    sha256_calls_total: int = 0
    canon_calls_total: int = 0
    sha256_bytes_total: int = 0
    canon_bytes_total: int = 0
    onto_ctx_hash_compute_calls_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "workvec_v1",
            "schema_version": 1,
            "sha256_calls_total": int(self.sha256_calls_total),
            "canon_calls_total": int(self.canon_calls_total),
            "sha256_bytes_total": int(self.sha256_bytes_total),
            "canon_bytes_total": int(self.canon_bytes_total),
            "onto_ctx_hash_compute_calls_total": int(self.onto_ctx_hash_compute_calls_total),
        }


def new_workvec() -> WorkVec:
    return WorkVec()


def workvec_tuple(workvec: WorkVec | dict[str, Any]) -> tuple[int, int, int, int, int]:
    if isinstance(workvec, WorkVec):
        return (
            int(workvec.sha256_calls_total),
            int(workvec.canon_calls_total),
            int(workvec.sha256_bytes_total),
            int(workvec.canon_bytes_total),
            int(workvec.onto_ctx_hash_compute_calls_total),
        )
    return (
        int(workvec.get("sha256_calls_total", 0)),
        int(workvec.get("canon_calls_total", 0)),
        int(workvec.get("sha256_bytes_total", 0)),
        int(workvec.get("canon_bytes_total", 0)),
        int(workvec.get("onto_ctx_hash_compute_calls_total", 0)),
    )


def lexicographic_strictly_smaller(a: WorkVec | dict[str, Any], b: WorkVec | dict[str, Any]) -> bool:
    return workvec_tuple(a) < workvec_tuple(b)


def canon_bytes(payload: Any, workvec: WorkVec | None) -> bytes:
    out = _canon_bytes(payload)
    if workvec is not None:
        workvec.canon_calls_total += 1
        workvec.canon_bytes_total += len(out)
    return out


def sha256(data: bytes, workvec: WorkVec | None) -> str:
    if workvec is not None:
        workvec.sha256_calls_total += 1
        workvec.sha256_bytes_total += len(data)
    digest = hashlib.sha256(data).hexdigest()
    return f"sha256:{digest}"
