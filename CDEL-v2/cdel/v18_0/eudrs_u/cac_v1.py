"""CAC artifact helpers + verifier (v1).

This module implements deterministic structural verification for `cac_v1.json`
and its per-episode binary records (`cac_episode_record_v1.bin`) as specified in
the repo-anchored EUDRS-U v1.0 spec (Section 15.1).

Notes:
  - All JSON inputs are expected to be GCJ-1 canonical upstream.
  - This module is RE2: fail-closed via `omega_common_v1.fail(...)`.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any, Callable

from ..omega_common_v1 import fail


_U32LE = struct.Struct("<I")
_U64LE = struct.Struct("<Q")
_I64LE = struct.Struct("<q")

_CACE_MAGIC_U32 = int.from_bytes(b"CACE", "little", signed=False)
_CACE_VERSION_U32 = 1


def _sha256_id_from_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


def _require_sha256_id(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        fail("SCHEMA_FAIL")
    hex64 = value.split(":", 1)[1]
    try:
        raw = bytes.fromhex(hex64)
    except Exception:
        fail("SCHEMA_FAIL")
    if len(raw) != 32:
        fail("SCHEMA_FAIL")
    return str(value)


def _require_q32_obj(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict) or set(obj.keys()) != {"q"}:
        fail("SCHEMA_FAIL")
    q = obj.get("q")
    if not isinstance(q, int):
        fail("SCHEMA_FAIL")
    return {"q": int(q)}


def compute_cac_root_sha256_v1(*, episode_record_hashes: list[str]) -> str:
    """v1 root: sha256(concat(record_hash32_bytes in episode order))."""

    buf = bytearray()
    for h in episode_record_hashes:
        hid = _require_sha256_id(h)
        buf += bytes.fromhex(hid.split(":", 1)[1])
    return _sha256_id_from_bytes(bytes(buf))


@dataclass(frozen=True, slots=True)
class CACEpisodeRecordV1:
    episode_id_u32: int
    h_tail_base32: bytes
    h_tail_cf32: bytes
    r_base_q32_s64: int
    r_cf_q32_s64: int
    a_q32_s64: int
    ladder_decomp_root32: bytes


def decode_cac_episode_record_v1(raw: bytes) -> CACEpisodeRecordV1:
    b = bytes(raw)
    if len(b) < 16 + (32 * 3) + (8 * 3):
        fail("SCHEMA_FAIL")

    magic_u32, version_u32, episode_id_u32, reserved_u32 = struct.unpack_from("<IIII", b, 0)
    if int(magic_u32) != int(_CACE_MAGIC_U32):
        fail("SCHEMA_FAIL")
    if int(version_u32) != int(_CACE_VERSION_U32):
        fail("SCHEMA_FAIL")
    if int(reserved_u32) != 0:
        fail("SCHEMA_FAIL")

    off = 16
    h_tail_base32 = bytes(b[off : off + 32])
    off += 32
    h_tail_cf32 = bytes(b[off : off + 32])
    off += 32
    r_base_q32_s64 = _I64LE.unpack_from(b, off)[0]
    off += 8
    r_cf_q32_s64 = _I64LE.unpack_from(b, off)[0]
    off += 8
    a_q32_s64 = _I64LE.unpack_from(b, off)[0]
    off += 8
    ladder_decomp_root32 = bytes(b[off : off + 32]) if (off + 32) <= len(b) else b""
    if ladder_decomp_root32 and len(ladder_decomp_root32) != 32:
        fail("SCHEMA_FAIL")

    return CACEpisodeRecordV1(
        episode_id_u32=int(episode_id_u32) & 0xFFFFFFFF,
        h_tail_base32=h_tail_base32,
        h_tail_cf32=h_tail_cf32,
        r_base_q32_s64=int(r_base_q32_s64),
        r_cf_q32_s64=int(r_cf_q32_s64),
        a_q32_s64=int(a_q32_s64),
        ladder_decomp_root32=ladder_decomp_root32 or (b"\x00" * 32),
    )


def verify_cac_v1(
    *,
    cac_obj: dict[str, Any],
    load_episode_record_bytes: Callable[[str], bytes] | None = None,
) -> None:
    """Deterministic CAC v1 verification.

    If `load_episode_record_bytes` is provided, it MUST return the exact bytes of
    the `cac_episode_record_v1.bin` artifact addressed by the given `record_hash`.
    """

    if not isinstance(cac_obj, dict):
        fail("SCHEMA_FAIL")
    if str(cac_obj.get("schema_id", "")).strip() != "cac_v1":
        fail("SCHEMA_FAIL")

    _require_sha256_id(cac_obj.get("delta_id"))
    _require_sha256_id(cac_obj.get("eval_suite_id"))
    _require_sha256_id(cac_obj.get("episode_list_hash"))

    episode_records = cac_obj.get("episode_records")
    if not isinstance(episode_records, list):
        fail("SCHEMA_FAIL")

    prev_ep: int | None = None
    record_hashes: list[str] = []
    for row in episode_records:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ep = row.get("episode_id_u32")
        if not isinstance(ep, int) or ep < 0 or ep > 0xFFFFFFFF:
            fail("SCHEMA_FAIL")
        ep_u32 = int(ep) & 0xFFFFFFFF
        if prev_ep is not None and ep_u32 <= prev_ep:
            fail("SCHEMA_FAIL")
        prev_ep = ep_u32

        rh = _require_sha256_id(row.get("record_hash"))
        record_hashes.append(rh)

        if load_episode_record_bytes is not None:
            rec_bytes = bytes(load_episode_record_bytes(rh))
            if _sha256_id_from_bytes(rec_bytes) != rh:
                fail("NONDETERMINISTIC")
            parsed = decode_cac_episode_record_v1(rec_bytes)
            if int(parsed.episode_id_u32) != int(ep_u32):
                fail("SCHEMA_FAIL")

    _require_q32_obj(cac_obj.get("delta_u_q32"))
    _require_q32_obj(cac_obj.get("delta_u_rob_q32"))

    root_exp = compute_cac_root_sha256_v1(episode_record_hashes=record_hashes)
    root_got = _require_sha256_id(cac_obj.get("cac_root_sha256"))
    if root_exp != root_got:
        fail("NONDETERMINISTIC")


__all__ = [
    "CACEpisodeRecordV1",
    "compute_cac_root_sha256_v1",
    "decode_cac_episode_record_v1",
    "verify_cac_v1",
]

