"""PCLP + VPVM STARK-VM v1 common constants/helpers.

This module is RE2: deterministic, fail-closed, and float-free.

v1 scope note:
  - `vpvm_stark_{prover,verifier}_v1` implements a *real STARK* (Poseidon-Merkle
    commitments + FRI + AIR checks) for the current `stark_vm_v1` proof path.
  - The `vpvm_q32_air_v1` shipped in v1 is a compact "commitment machine" AIR
    that proves binding/commitment consistency; the full VPVM ISA AIR is
    roadmapped.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from ..omega_common_v1 import fail
from .eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed

# -----------------------
# Public constants / IDs.
# -----------------------

PROOF_SYSTEM_ID_STARK_VM_V1 = "stark_vm_v1"
VPVM_ID_Q32_V1 = "vpvm_q32_v1"
DC1_ID_Q32_V1 = "dc1:q32_v1"

SCHEMA_PCLP_BUNDLE_V1 = "pclp_bundle_v1"
SCHEMA_VPVM_CONFIG_V1 = "vpvm_config_v1"
SCHEMA_VPVM_PUBLIC_INPUTS_V1 = "vpvm_public_inputs_v1"
SCHEMA_STARK_VM_PROOF_V1 = "stark_vm_proof_v1"

COMMIT_ALGO_ID_ROLLHASH32_V1 = "rollhash32_v1"
COMMIT_ALGO_ID_ROLLHASH32X2_V1 = "rollhash32x2_v1"

# rollhash32x2 batching (u32 items per commitment-trace row).
#
# This is purely an internal proof-system parameter (not part of public JSON
# schemas). Larger batches reduce STARK trace length and keep tests feasible in
# pure-Python.
# Use a large batch so the commitment-machine trace stays small enough that the
# pinned FRI remainder-degree bound (64) remains valid without implementing full
# DEEP composition.
ROLLHASH32X2_BATCH_U32_PER_ROW_V1 = 512

# Reason codes (proof-path only; single primary).
EUDRSU_PCLP_SCHEMA_INVALID = "EUDRSU_PCLP_SCHEMA_INVALID"
EUDRSU_PCLP_BINDING_MISMATCH = "EUDRSU_PCLP_BINDING_MISMATCH"
EUDRSU_PCLP_PROOF_INVALID = "EUDRSU_PCLP_PROOF_INVALID"
EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH = "EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH"
EUDRSU_PCLP_CONFIG_MISMATCH = "EUDRSU_PCLP_CONFIG_MISMATCH"
EUDRSU_PCLP_UNSUPPORTED_MODE = "EUDRSU_PCLP_UNSUPPORTED_MODE"

# Goldilocks prime: 2^64 - 2^32 + 1.
GOLDILOCKS_P = 0xFFFFFFFF00000001
_U64_MASK = 0xFFFFFFFFFFFFFFFF

_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_PI_HASH_PREFIX = b"VPVM_PI_HASH_V1\0"
_PI_BASE_HASH_PREFIX = b"VPVM_PI_BASE_HASH_V1\0"
_BIND_R0_PREFIX = b"VPVM_BIND_R0_V1\0"
_BIND_R1_PREFIX = b"VPVM_BIND_R1_V1\0"
_TRACE_ROOT_PREFIX = b"VPVM_TRACE_ROOT_V1\0"
_PROOF_PAYLOAD_PREFIX = b"VPVM_PROOF_PAYLOAD_V1\0"

_PCLP_TRAIN_TAIL_PREFIX = b"PCLP_TRAIN_TAIL_V1\0"
_PCLP_EVAL_TAIL_PREFIX = b"PCLP_EVAL_TAIL_V1\0"


def require_sha256_id(value: Any, *, reason: str = EUDRSU_PCLP_SCHEMA_INVALID) -> str:
    if not isinstance(value, str) or _SHA256_ID_RE.fullmatch(value) is None:
        fail(reason)
    return str(value)


def bytes32_to_hex64(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return bytes(data).hex()


def hex64_to_bytes32(hex64: str, *, reason: str = EUDRSU_PCLP_SCHEMA_INVALID) -> bytes:
    if not isinstance(hex64, str) or len(hex64) != 64:
        fail(reason)
    try:
        b = bytes.fromhex(hex64)
    except Exception:
        fail(reason)
    if len(b) != 32:
        fail(reason)
    return b


def compute_self_hash_id_omit(obj: dict[str, Any], *, id_field: str) -> str:
    """Compute sha256:<hex> over GCJ-1 canonical bytes with `id_field` omitted."""

    if not isinstance(obj, dict):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    no_id = dict(obj)
    no_id.pop(str(id_field), None)
    return sha256_prefixed(gcj1_canon_bytes(no_id))


def public_inputs_without_commitments(pi_obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pi_obj, dict):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    out = dict(pi_obj)
    out.pop("commitments", None)
    # Proof-mode tails are derived from the base hash; omit them to avoid cycles.
    out.pop("h_train_tail32_hex_expected", None)
    out.pop("h_eval_tail32_hex_expected", None)
    return out


def compute_public_inputs_hash32(pi_obj: dict[str, Any]) -> bytes:
    return hashlib.sha256(_PI_HASH_PREFIX + gcj1_canon_bytes(pi_obj)).digest()


def compute_public_inputs_base_hash32(pi_obj: dict[str, Any]) -> bytes:
    base = public_inputs_without_commitments(pi_obj)
    return hashlib.sha256(_PI_BASE_HASH_PREFIX + gcj1_canon_bytes(base)).digest()


def is_power_of_two_u32(value: int) -> bool:
    if not isinstance(value, int):
        return False
    x = int(value)
    return x > 0 and (x & (x - 1)) == 0 and x <= 0xFFFFFFFF


def derive_trace_root32(*, public_inputs_base_hash32: bytes, program_bytes: bytes) -> bytes:
    if not isinstance(public_inputs_base_hash32, (bytes, bytearray, memoryview)) or len(public_inputs_base_hash32) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    prog_h = hashlib.sha256(bytes(program_bytes)).digest()
    return hashlib.sha256(_TRACE_ROOT_PREFIX + bytes(public_inputs_base_hash32) + prog_h).digest()


def derive_r_bind_u64(*, public_inputs_base_hash32: bytes, trace_root32: bytes) -> int:
    if not isinstance(public_inputs_base_hash32, (bytes, bytearray, memoryview)) or len(public_inputs_base_hash32) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if not isinstance(trace_root32, (bytes, bytearray, memoryview)) or len(trace_root32) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    seed = hashlib.sha256(_BIND_R0_PREFIX + bytes(public_inputs_base_hash32) + bytes(trace_root32)).digest()
    while True:
        x = int.from_bytes(seed[0:8], "little", signed=False) & _U64_MASK
        if x < GOLDILOCKS_P:
            return int(x)
        seed = hashlib.sha256(seed).digest()


def derive_r_bind_u64_pair(*, public_inputs_base_hash32: bytes, trace_root32: bytes) -> tuple[int, int]:
    """Derive two independent r_bind challenges (u64) in Goldilocks field.

    Deterministic and fail-closed. Values are rejection-sampled into [0, p).
    """

    if not isinstance(public_inputs_base_hash32, (bytes, bytearray, memoryview)) or len(public_inputs_base_hash32) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if not isinstance(trace_root32, (bytes, bytearray, memoryview)) or len(trace_root32) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    def _one(prefix: bytes) -> int:
        seed = hashlib.sha256(prefix + bytes(public_inputs_base_hash32) + bytes(trace_root32)).digest()
        while True:
            x = int.from_bytes(seed[0:8], "little", signed=False) & _U64_MASK
            if x < GOLDILOCKS_P:
                return int(x)
            seed = hashlib.sha256(seed).digest()

    return _one(_BIND_R0_PREFIX), _one(_BIND_R1_PREFIX)


def rollhash32_v1_u32_items(*, r_bind_u64: int, u32_items: Iterable[int]) -> int:
    """Rolling commitment over u32 items into Goldilocks field."""

    if not isinstance(r_bind_u64, int) or r_bind_u64 < 0 or r_bind_u64 > _U64_MASK:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    r = int(r_bind_u64) % int(GOLDILOCKS_P)

    acc = 0
    for t in u32_items:
        if not isinstance(t, int) or t < 0 or t > 0xFFFFFFFF:
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        acc = (acc * r + int(t)) % int(GOLDILOCKS_P)
    return int(acc)


def _u64_to_u32_limbs_le(u64: int) -> tuple[int, int]:
    u = int(u64) & _U64_MASK
    lo = u & 0xFFFFFFFF
    hi = (u >> 32) & 0xFFFFFFFF
    return int(lo), int(hi)


def _weights_to_u32_stream(weights_manifest: Any) -> list[int]:
    # WeightsManifestV1 from qxrl_train_replay_v1.
    tensors = getattr(weights_manifest, "tensors", None)
    if not isinstance(tensors, list):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    out: list[int] = []
    for t in tensors:
        name = getattr(t, "name", "")
        _ = str(name)  # defensive; name ordering enforced by loader

        blocks = getattr(t, "blocks", None)
        data = getattr(t, "data_q32_s64", None)
        if not isinstance(blocks, list) or not isinstance(data, list):
            fail(EUDRSU_PCLP_SCHEMA_INVALID)

        for b in blocks:
            off = int(getattr(b, "elem_offset_u64", -1))
            cnt = int(getattr(b, "elem_count_u32", -1))
            if off < 0 or cnt <= 0:
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            end = off + cnt
            if end < off or end > len(data):
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            for v_s64 in data[off:end]:
                if not isinstance(v_s64, int):
                    fail(EUDRSU_PCLP_SCHEMA_INVALID)
                u = int(v_s64) & _U64_MASK  # two's complement
                lo, hi = _u64_to_u32_limbs_le(u)
                out.append(lo)
                out.append(hi)
    return out


def weights_manifest_to_u32_stream_v1(weights_manifest: Any) -> list[int]:
    """Public helper: canonical u32 item stream for a WeightsManifestV1 object.

    This is used by both the producer-side prover and the RE2 verifier to avoid
    drift in commitment calculations.
    """

    return _weights_to_u32_stream(weights_manifest)


def _examples_to_u32_stream(examples: list[Any]) -> list[int]:
    if not isinstance(examples, list):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    out: list[int] = []
    for ex in examples:
        # Supports QXRLDatasetExampleV1 dataclass and dict-like test fixtures.
        if isinstance(ex, dict):
            example_id = ex.get("example_id_u64")
            anchor = ex.get("anchor_tokens_u32")
            positive = ex.get("positive_tokens_u32")
        else:
            example_id = getattr(ex, "example_id_u64", None)
            anchor = getattr(ex, "anchor_tokens_u32", None)
            positive = getattr(ex, "positive_tokens_u32", None)

        if not isinstance(example_id, int) or example_id < 0:
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        lo, hi = _u64_to_u32_limbs_le(int(example_id))
        out.append(lo)
        out.append(hi)

        if not isinstance(anchor, list) or not isinstance(positive, list):
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        for tok in anchor:
            if not isinstance(tok, int) or tok < 0 or tok > 0xFFFFFFFF:
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            out.append(int(tok))
        for tok in positive:
            if not isinstance(tok, int) or tok < 0 or tok > 0xFFFFFFFF:
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            out.append(int(tok))
    return out


def dataset_examples_to_u32_stream_v1(examples: list[Any]) -> list[int]:
    """Public helper: canonical u32 item stream for decoded QXRL dataset examples."""

    return _examples_to_u32_stream(examples)


def compute_rollhash_commitments_v1(
    *,
    r_bind_u64: int,
    program_bytes: bytes,
    lut_bytes: bytes,
    examples: list[Any],
    weights_before: Any,
    weights_after: Any,
) -> dict[str, int]:
    """Compute v1 rolling commitments over program/lut/dataset/weights streams."""

    program_items = [int(b) for b in bytes(program_bytes)]
    lut_items = [int(b) for b in bytes(lut_bytes)]
    dataset_items = _examples_to_u32_stream(examples)
    weights_before_items = _weights_to_u32_stream(weights_before)
    weights_after_items = _weights_to_u32_stream(weights_after)

    return {
        "program_commit_f": rollhash32_v1_u32_items(r_bind_u64=r_bind_u64, u32_items=program_items),
        "lut_commit_f": rollhash32_v1_u32_items(r_bind_u64=r_bind_u64, u32_items=lut_items),
        "dataset_commit_f": rollhash32_v1_u32_items(r_bind_u64=r_bind_u64, u32_items=dataset_items),
        "weights_before_commit_f": rollhash32_v1_u32_items(r_bind_u64=r_bind_u64, u32_items=weights_before_items),
        "weights_after_commit_f": rollhash32_v1_u32_items(r_bind_u64=r_bind_u64, u32_items=weights_after_items),
    }


def compute_rollhash32x2_commitments_v1(
    *,
    r_bind_u64_0: int,
    r_bind_u64_1: int,
    program_bytes: bytes,
    lut_bytes: bytes,
    examples: list[Any],
    weights_before: Any,
    weights_after: Any,
) -> dict[str, int]:
    """Compute rollhash32x2 commitments (two independent field elements per stream).

    v1 commits to *artifact contents* (not ids) using the same item-stream
    encoding as `compute_rollhash_commitments_v1`, but with two independent
    challenges (r0,r1) for stronger binding.

    Stream encodings (normative in v18_0 PCLP v1):
      - program: raw bytes, streamed as u32 items in [0..255]
      - lut: raw bytes, streamed as u32 items in [0..255]
      - dataset: decoded examples, streamed as u32 items (example_id limbs, then tokens)
      - weights: decoded WeightsManifestV1 tensors/blocks, streamed as u32 limbs of s64 values
    """

    p0 = int(GOLDILOCKS_P)

    def _one(r: int, items: Iterable[int]) -> int:
        v = rollhash32_v1_u32_items(r_bind_u64=r, u32_items=items)
        if not isinstance(v, int) or v < 0 or v >= p0:
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        return int(v)

    program_items = [int(b) for b in bytes(program_bytes)]
    lut_items = [int(b) for b in bytes(lut_bytes)]
    dataset_items = _examples_to_u32_stream(list(examples))
    weights_before_items = _weights_to_u32_stream(weights_before)
    weights_after_items = _weights_to_u32_stream(weights_after)

    def _pad(items: list[int]) -> list[int]:
        n = len(items)
        k = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)
        pad = (-n) % k
        if pad:
            items = list(items) + [0] * int(pad)
        return list(items)

    # Commitment-machine trace pads each stream to a fixed block size; mirror that here
    # so verifier-side recomputation matches the proof statement.
    program_items = _pad(program_items)
    lut_items = _pad(lut_items)
    dataset_items = _pad(dataset_items)
    weights_before_items = _pad(weights_before_items)
    weights_after_items = _pad(weights_after_items)

    return {
        "program_commit_f0": _one(int(r_bind_u64_0), program_items),
        "program_commit_f1": _one(int(r_bind_u64_1), program_items),
        "lut_commit_f0": _one(int(r_bind_u64_0), lut_items),
        "lut_commit_f1": _one(int(r_bind_u64_1), lut_items),
        "dataset_commit_f0": _one(int(r_bind_u64_0), dataset_items),
        "dataset_commit_f1": _one(int(r_bind_u64_1), dataset_items),
        "weights_before_commit_f0": _one(int(r_bind_u64_0), weights_before_items),
        "weights_before_commit_f1": _one(int(r_bind_u64_1), weights_before_items),
        "weights_after_commit_f0": _one(int(r_bind_u64_0), weights_after_items),
        "weights_after_commit_f1": _one(int(r_bind_u64_1), weights_after_items),
    }


def proof_payload_digest32_from_header_bytes(header_canon_bytes: bytes) -> bytes:
    if not isinstance(header_canon_bytes, (bytes, bytearray, memoryview)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return hashlib.sha256(_PROOF_PAYLOAD_PREFIX + bytes(header_canon_bytes)).digest()


def sha256_id_to_digest32(artifact_id: Any, *, reason: str = EUDRSU_PCLP_SCHEMA_INVALID) -> bytes:
    """Convert sha256:<hex> id string to raw 32-byte digest."""

    sid = require_sha256_id(artifact_id, reason=reason)
    try:
        return bytes.fromhex(str(sid).split(":", 1)[1])
    except Exception:
        fail(reason)
    return b"\x00" * 32


def derive_pclp_tails_v1(
    *,
    poseidon_params_bin: bytes,
    public_inputs_base_hash32: bytes,
    wroot_before_id: str,
    wroot_after_id: str,
    program_id: str,
    scorecard_artifact_id: str,
    eval_manifest_id: str,
) -> tuple[bytes, bytes]:
    """Derive (h_train_pclp_tail32, h_eval_pclp_tail32) per Option 2.

    This is verifier-recomputable and does not depend on legacy SHA256 tail chains.
    """

    from .poseidon_gld_v1 import parse_poseidon_params_gld_v1_bin, poseidon_sponge_hash32_v1

    params = parse_poseidon_params_gld_v1_bin(bytes(poseidon_params_bin))
    pib = bytes(public_inputs_base_hash32)
    if len(pib) != 32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    w0 = sha256_id_to_digest32(wroot_before_id, reason=EUDRSU_PCLP_SCHEMA_INVALID)
    w1 = sha256_id_to_digest32(wroot_after_id, reason=EUDRSU_PCLP_SCHEMA_INVALID)
    pid = sha256_id_to_digest32(program_id, reason=EUDRSU_PCLP_SCHEMA_INVALID)
    sc = sha256_id_to_digest32(scorecard_artifact_id, reason=EUDRSU_PCLP_SCHEMA_INVALID)
    em = sha256_id_to_digest32(eval_manifest_id, reason=EUDRSU_PCLP_SCHEMA_INVALID)

    h_train = poseidon_sponge_hash32_v1(params, data=b"".join([_PCLP_TRAIN_TAIL_PREFIX, pib, w0, w1, pid]))
    h_eval = poseidon_sponge_hash32_v1(params, data=b"".join([_PCLP_EVAL_TAIL_PREFIX, pib, w1, sc, em, pid]))
    return bytes(h_train), bytes(h_eval)


__all__ = [
    "COMMIT_ALGO_ID_ROLLHASH32_V1",
    "COMMIT_ALGO_ID_ROLLHASH32X2_V1",
    "DC1_ID_Q32_V1",
    "EUDRSU_PCLP_BINDING_MISMATCH",
    "EUDRSU_PCLP_CONFIG_MISMATCH",
    "EUDRSU_PCLP_PROOF_INVALID",
    "EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH",
    "EUDRSU_PCLP_SCHEMA_INVALID",
    "EUDRSU_PCLP_UNSUPPORTED_MODE",
    "GOLDILOCKS_P",
    "PROOF_SYSTEM_ID_STARK_VM_V1",
    "ROLLHASH32X2_BATCH_U32_PER_ROW_V1",
    "SCHEMA_PCLP_BUNDLE_V1",
    "SCHEMA_STARK_VM_PROOF_V1",
    "SCHEMA_VPVM_CONFIG_V1",
    "SCHEMA_VPVM_PUBLIC_INPUTS_V1",
    "VPVM_ID_Q32_V1",
    "bytes32_to_hex64",
    "dataset_examples_to_u32_stream_v1",
    "compute_rollhash32x2_commitments_v1",
    "compute_public_inputs_base_hash32",
    "compute_public_inputs_hash32",
    "compute_rollhash_commitments_v1",
    "compute_self_hash_id_omit",
    "derive_pclp_tails_v1",
    "derive_r_bind_u64",
    "derive_r_bind_u64_pair",
    "derive_trace_root32",
    "hex64_to_bytes32",
    "is_power_of_two_u32",
    "proof_payload_digest32_from_header_bytes",
    "public_inputs_without_commitments",
    "require_sha256_id",
    "rollhash32_v1_u32_items",
    "sha256_id_to_digest32",
    "weights_manifest_to_u32_stream_v1",
]
