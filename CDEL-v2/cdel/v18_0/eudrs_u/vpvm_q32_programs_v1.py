"""VPVM Q32 program builders (v1).

v1 provides a minimal canonical "program" byte format used to bind a proof
statement to the exact QXRL-QRE workload configuration.

This is RE2: deterministic and fail-closed.
"""

from __future__ import annotations

import struct
from typing import Any

from ..omega_common_v1 import fail


_MAGIC = b"VPVM"
_VERSION_U32_V1 = 1


def _enc_utf8(s: Any, *, reason: str) -> bytes:
    if not isinstance(s, str) or not s:
        fail(reason)
    try:
        b = s.encode("utf-8", errors="strict")
    except Exception:
        fail(reason)
    return b


def _enc_field(buf: bytearray, s: Any, *, reason: str) -> None:
    b = _enc_utf8(s, reason=reason)
    if len(b) > 0xFFFFFFFF:
        fail(reason)
    buf += struct.pack("<I", int(len(b)) & 0xFFFFFFFF)
    buf += b


def build_vpvm_program_qxrl_qre_train_eval_v1(
    *,
    opset_id: str,
    training_manifest_id: str,
    dataset_manifest_id: str,
    eval_manifest_id: str,
    lut_manifest_id: str,
    wroot_before_id: str,
    wroot_after_id: str,
) -> bytes:
    """Build canonical VPVM program bytes for QXRL QRE train+eval (v1).

    The byte format is intentionally simple and self-describing; it is not a
    general-purpose VM ISA in v1.
    """

    reason = "SCHEMA_FAIL"
    out = bytearray()
    out += _MAGIC
    out += struct.pack("<I", int(_VERSION_U32_V1) & 0xFFFFFFFF)
    _enc_field(out, opset_id, reason=reason)
    _enc_field(out, training_manifest_id, reason=reason)
    _enc_field(out, dataset_manifest_id, reason=reason)
    _enc_field(out, eval_manifest_id, reason=reason)
    _enc_field(out, lut_manifest_id, reason=reason)
    _enc_field(out, wroot_before_id, reason=reason)
    _enc_field(out, wroot_after_id, reason=reason)
    return bytes(out)


__all__ = ["build_vpvm_program_qxrl_qre_train_eval_v1"]

