from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes_pure, loads


def omega_kernel_canon_bytes_v1(raw_json: bytes) -> bytes:
    """Reference implementation for omega_kernel_canon_bytes_v1.

    Input: arbitrary UTF-8 JSON bytes.
    Output: GCJ-1 canonical JSON bytes (no trailing newline).
    """

    obj = loads(raw_json)
    return canon_bytes_pure(obj)


__all__ = ["omega_kernel_canon_bytes_v1"]

