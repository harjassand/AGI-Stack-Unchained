"""SLS-VM v1 (deterministic Strategy VM baseline).

Phase 6 directive (normative):
  - Parse SLS1 cartridge binaries (constant pool + fixed-width instructions).
  - Execute a typed stack machine with strict budgets and deterministic log chain.
  - Integrate ML-Index retrieval + concept shard UNIFY/APPLY.

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Any, Callable, Final, Iterable, Literal

from ..omega_common_v1 import OmegaV18Error, ensure_sha256, fail, validate_schema
from .concept_shard_v1 import _unify_shard_region_with_stats_v1, apply_shard_v1
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict
from .fal_ladder_v1 import count_abstracts_out_in_v1, validate_fal_constraints_for_qxwmr_state_v1
from .ml_index_v1 import retrieve_topk_v1, require_ml_index_manifest_v1
from .ontology_v1 import OntologyV1
from .qxwmr_canon_wl_v1 import QXWMRCanonCapsContextV1, canon_state_packed_v1
from .qxwmr_state_v1 import unpack_state_packed_v1, validate_state_packed_v1
from .urc_merkle_v1 import urc_derive_page_relpath_v1, urc_derive_ptnode_relpath_v1, urc_parse_page_v1
from .urc_vm_v1 import urc_step_capsule_v1

_REASON_CARTRIDGE_DECODE_FAIL: Final[str] = "EUDRSU_SLS_CARTRIDGE_DECODE_FAIL"
_REASON_OPCODE_INVALID: Final[str] = "EUDRSU_SLS_OPCODE_INVALID"
_REASON_STACK_OVERFLOW: Final[str] = "EUDRSU_SLS_STACK_OVERFLOW"
_REASON_STACK_UNDERFLOW: Final[str] = "EUDRSU_SLS_STACK_UNDERFLOW"
_REASON_STACK_TYPE_ERROR: Final[str] = "EUDRSU_SLS_STACK_TYPE_ERROR"
_REASON_BUDGET_EXCEEDED: Final[str] = "EUDRSU_SLS_BUDGET_EXCEEDED"
_REASON_INVARIANT_FAIL: Final[str] = "EUDRSU_SLS_INVARIANT_FAIL"
_REASON_PROJECT_NO_PARENT: Final[str] = "EUDRSU_SLS_PROJECT_NO_PARENT"

EDGE_ABSTRACTS_V1: Final[int] = 0xAB57AB57

_SLS1_HDR = struct.Struct("<4sIII4I")  # magic, ver, const_count, instr_count, reserved[4]
_CONST_HDR = struct.Struct("<II")  # kind, len
_INSTR = struct.Struct("<HHIII")  # opcode_u16, flags_u16, a_u32, b_u32, c_u32

_SLS_LOG_MAGIC: Final[bytes] = b"SLD1"
_SLS_PLAN_STUB_DOMAIN: Final[bytes] = b"SLS_PLAN_STUB_V1"
_SLS_USER_LOG_DOMAIN: Final[bytes] = b"SLS_USER_LOG_V1"


ConstKind = Literal[1, 2, 3, 4, 5, 6]


@dataclass(frozen=True, slots=True)
class SLSConstV1:
    kind_u32: int
    value: Any


@dataclass(frozen=True, slots=True)
class SLSInstrV1:
    opcode_u16: int
    a_u32: int
    b_u32: int
    c_u32: int


@dataclass(frozen=True, slots=True)
class SLSCartridgeV1:
    consts: list[SLSConstV1]
    instrs: list[SLSInstrV1]


@dataclass(frozen=True, slots=True)
class MLIndexCtxV1:
    index_manifest_obj: dict[str, Any]
    codebook_bytes: bytes
    index_root_bytes: bytes
    bucket_listing_obj: dict[str, Any]


ValueType = Literal[
    "U32",
    "U64",
    "S64",
    "BYTES",
    "BYTES32",
    "UTF8",
    "LIST_BYTES32",
    "LIST_U32",
    "WITNESS",
]


@dataclass(frozen=True, slots=True)
class SLSValueV1:
    typ: ValueType
    v: Any


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _u32_le(value: int) -> bytes:
    v = int(value)
    if v < 0 or v > 0xFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return struct.pack("<I", v & 0xFFFFFFFF)


def _u64_le(value: int) -> bytes:
    v = int(value)
    if v < 0 or v > 0xFFFFFFFFFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF)


def _s64_le(value: int) -> bytes:
    try:
        return struct.pack("<q", int(value))
    except Exception:
        fail(_REASON_INVARIANT_FAIL)
    return b""


def _require_bytes32(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        fail(_REASON_STACK_TYPE_ERROR)
    b = bytes(value)
    if len(b) != 32:
        fail(_REASON_STACK_TYPE_ERROR)
    return b


def _decode_cartridge_v1(cartridge_bytes: bytes) -> SLSCartridgeV1:
    if not isinstance(cartridge_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_CARTRIDGE_DECODE_FAIL)
    mv = memoryview(bytes(cartridge_bytes))
    if len(mv) < _SLS1_HDR.size:
        fail(_REASON_CARTRIDGE_DECODE_FAIL)

    magic, ver_u32, const_count_u32, instr_count_u32, r0, r1, r2, r3 = _SLS1_HDR.unpack_from(mv, 0)
    if bytes(magic) != b"SLS1":
        fail(_REASON_CARTRIDGE_DECODE_FAIL)
    if int(ver_u32) != 1:
        fail(_REASON_CARTRIDGE_DECODE_FAIL)
    if any(int(x) != 0 for x in (r0, r1, r2, r3)):
        fail(_REASON_CARTRIDGE_DECODE_FAIL)

    const_count = int(const_count_u32)
    instr_count = int(instr_count_u32)
    if const_count < 0 or instr_count < 0:
        fail(_REASON_CARTRIDGE_DECODE_FAIL)

    off = _SLS1_HDR.size
    consts: list[SLSConstV1] = []
    for _ in range(const_count):
        if off + _CONST_HDR.size > len(mv):
            fail(_REASON_CARTRIDGE_DECODE_FAIL)
        kind_u32, const_len_u32 = _CONST_HDR.unpack_from(mv, off)
        off += _CONST_HDR.size

        kind = int(kind_u32)
        n = int(const_len_u32)
        if kind not in {1, 2, 3, 4, 5, 6}:
            fail(_REASON_CARTRIDGE_DECODE_FAIL)
        if n < 0 or off + n > len(mv):
            fail(_REASON_CARTRIDGE_DECODE_FAIL)
        payload = bytes(mv[off : off + n])
        off += n

        if kind == 1:
            if n != 4:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            consts.append(SLSConstV1(kind_u32=kind, value=int(struct.unpack("<I", payload)[0])))
        elif kind == 2:
            if n != 8:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            consts.append(SLSConstV1(kind_u32=kind, value=int(struct.unpack("<Q", payload)[0])))
        elif kind == 3:
            if n != 8:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            consts.append(SLSConstV1(kind_u32=kind, value=int(struct.unpack("<q", payload)[0])))
        elif kind == 4:
            consts.append(SLSConstV1(kind_u32=kind, value=payload))
        elif kind == 5:
            if n < 1 or n > 256:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            if b"\x00" in payload:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            try:
                s = payload.decode("utf-8", errors="strict")
            except Exception:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            consts.append(SLSConstV1(kind_u32=kind, value=s))
        elif kind == 6:
            if n != 32:
                fail(_REASON_CARTRIDGE_DECODE_FAIL)
            consts.append(SLSConstV1(kind_u32=kind, value=payload))
        else:  # pragma: no cover
            fail(_REASON_CARTRIDGE_DECODE_FAIL)

    # Instructions are fixed-width and must consume the remainder exactly.
    expected_instr_bytes = instr_count * _INSTR.size
    if off + expected_instr_bytes != len(mv):
        fail(_REASON_CARTRIDGE_DECODE_FAIL)

    instrs: list[SLSInstrV1] = []
    for _ in range(instr_count):
        opcode_u16, flags_u16, a_u32, b_u32, c_u32 = _INSTR.unpack_from(mv, off)
        off += _INSTR.size
        if int(flags_u16) != 0:
            fail(_REASON_CARTRIDGE_DECODE_FAIL)
        instrs.append(
            SLSInstrV1(
                opcode_u16=int(opcode_u16),
                a_u32=int(a_u32),
                b_u32=int(b_u32),
                c_u32=int(c_u32),
            )
        )

    if off != len(mv):
        fail(_REASON_CARTRIDGE_DECODE_FAIL)

    return SLSCartridgeV1(consts=consts, instrs=instrs)


def _require_strategy_def_v1(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        fail(_REASON_INVARIANT_FAIL)
    try:
        validate_schema(obj, "strategy_def_v1")
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_INVARIANT_FAIL)

    if str(obj.get("schema_id", "")).strip() != "strategy_def_v1":
        fail(_REASON_INVARIANT_FAIL)

    strategy_id = ensure_sha256(obj.get("strategy_id"), reason=_REASON_INVARIANT_FAIL)
    tmp = dict(obj)
    tmp["strategy_id"] = "sha256:" + ("0" * 64)
    computed = f"sha256:{hashlib.sha256(gcj1_canon_bytes(tmp)).hexdigest()}"
    if computed != strategy_id:
        fail(_REASON_INVARIANT_FAIL)

    if str(obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(_REASON_INVARIANT_FAIL)
    opset_id = str(obj.get("opset_id", "")).strip()
    if not opset_id.startswith("opset:eudrs_u_v1:sha256:"):
        fail(_REASON_INVARIANT_FAIL)

    cartridge_ref = require_artifact_ref_v1(obj.get("cartridge_ref"), reason=_REASON_INVARIANT_FAIL)
    if not str(cartridge_ref.get("artifact_relpath", "")).endswith(".strategy_cartridge_v1.bin"):
        fail(_REASON_INVARIANT_FAIL)

    concept_deps = obj.get("concept_deps")
    if not isinstance(concept_deps, list):
        fail(_REASON_INVARIANT_FAIL)
    prev: str | None = None
    seen: set[str] = set()
    deps_out: list[str] = []
    for item in concept_deps:
        if not isinstance(item, str):
            fail(_REASON_INVARIANT_FAIL)
        if prev is not None and item < prev:
            fail(_REASON_INVARIANT_FAIL)
        prev = item
        if item in seen:
            fail(_REASON_INVARIANT_FAIL)
        seen.add(item)
        deps_out.append(item)

    budgets = obj.get("budgets")
    if not isinstance(budgets, dict):
        fail(_REASON_INVARIANT_FAIL)
    required_budget_keys = {
        "instr_cap_u64",
        "cost_cap_u64",
        "log_cap_u32",
        "retrieve_cap_u32",
        "unify_cap_u32",
        "apply_cap_u32",
        "lift_cap_u32",
        "project_cap_u32",
        "plan_cap_u32",
        "urc_cap_u32",
        "max_state_bytes_u32",
    }
    if set(budgets.keys()) != required_budget_keys:
        fail(_REASON_INVARIANT_FAIL)

    def _u64_cap(name: str) -> int:
        v = budgets.get(name)
        if not isinstance(v, int) or v < 1:
            fail(_REASON_INVARIANT_FAIL)
        if v > 0xFFFFFFFFFFFFFFFF:
            fail(_REASON_INVARIANT_FAIL)
        return int(v)

    def _u32_cap(name: str) -> int:
        v = budgets.get(name)
        if not isinstance(v, int) or v < 1:
            fail(_REASON_INVARIANT_FAIL)
        if v > 0xFFFFFFFF:
            fail(_REASON_INVARIANT_FAIL)
        return int(v)

    _u64_cap("instr_cap_u64")
    _u64_cap("cost_cap_u64")
    _u32_cap("log_cap_u32")
    _u32_cap("retrieve_cap_u32")
    _u32_cap("unify_cap_u32")
    _u32_cap("apply_cap_u32")
    _u32_cap("lift_cap_u32")
    _u32_cap("project_cap_u32")
    _u32_cap("plan_cap_u32")
    _u32_cap("urc_cap_u32")
    max_state_bytes_u32 = _u32_cap("max_state_bytes_u32")
    if max_state_bytes_u32 < 64:
        fail(_REASON_INVARIANT_FAIL)

    return dict(obj)


def _push(stack: list[SLSValueV1], item: SLSValueV1) -> None:
    if len(stack) >= 1024:
        fail(_REASON_STACK_OVERFLOW)
    stack.append(item)


def _pop(stack: list[SLSValueV1]) -> SLSValueV1:
    if not stack:
        fail(_REASON_STACK_UNDERFLOW)
    return stack.pop()


def _expect(value: SLSValueV1, typ: ValueType) -> Any:
    if not isinstance(value, SLSValueV1) or value.typ != typ:
        fail(_REASON_STACK_TYPE_ERROR)
    return value.v


def _stack_u32(v: int) -> SLSValueV1:
    if not isinstance(v, int) or v < 0 or v > 0xFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return SLSValueV1("U32", int(v))


def _stack_u64(v: int) -> SLSValueV1:
    if not isinstance(v, int) or v < 0 or v > 0xFFFFFFFFFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return SLSValueV1("U64", int(v))


def _stack_s64(v: int) -> SLSValueV1:
    if not isinstance(v, int) or v < -(1 << 63) or v > (1 << 63) - 1:
        fail(_REASON_INVARIANT_FAIL)
    return SLSValueV1("S64", int(v))


def _stack_bytes(v: bytes) -> SLSValueV1:
    if not isinstance(v, (bytes, bytearray, memoryview)):
        fail(_REASON_INVARIANT_FAIL)
    return SLSValueV1("BYTES", bytes(v))


def _stack_bytes32(v: bytes) -> SLSValueV1:
    b = _require_bytes32(v)
    return SLSValueV1("BYTES32", b)


def _stack_utf8(v: str) -> SLSValueV1:
    if not isinstance(v, str):
        fail(_REASON_INVARIANT_FAIL)
    return SLSValueV1("UTF8", str(v))


def _emit_log_record_v1(
    *,
    event_kind_u32: int,
    step_index_u64: int,
    pc_u32: int,
    state_before_hash32: bytes,
    state_after_hash32: bytes,
    retrieval_trace_root32: bytes,
    witness_hash32: bytes,
    aux_hash32: bytes,
    instr_used_u64: int,
    cost_used_u64: int,
) -> bytes:
    # Fixed-width 256-byte record (SLD1).
    if len(state_before_hash32) != 32 or len(state_after_hash32) != 32:
        fail(_REASON_INVARIANT_FAIL)
    if len(retrieval_trace_root32) != 32 or len(witness_hash32) != 32 or len(aux_hash32) != 32:
        fail(_REASON_INVARIANT_FAIL)

    out = bytearray()
    out += _SLS_LOG_MAGIC
    out += struct.pack("<I", 1)  # version_u32
    out += struct.pack("<I", int(event_kind_u32) & 0xFFFFFFFF)
    out += _u64_le(int(step_index_u64))
    out += _u32_le(int(pc_u32))
    out += _u32_le(0)  # reserved_u32
    out += bytes(state_before_hash32)
    out += bytes(state_after_hash32)
    out += bytes(retrieval_trace_root32)
    out += bytes(witness_hash32)
    out += bytes(aux_hash32)
    out += _u64_le(int(instr_used_u64))
    out += _u64_le(int(cost_used_u64))
    out += b"\x00" * (6 * 8)  # reserved_u64[6]
    out += _u32_le(0)  # reserved_u32_tail
    if len(out) != 256:
        fail(_REASON_INVARIANT_FAIL)
    return bytes(out)


def _registry_load_gcj1_json(*, ref: dict[str, str], registry_load_bytes: Callable[[dict[str, str]], bytes]) -> tuple[dict[str, Any], bytes]:
    """Load JSON by ArtifactRefV1 via callback; verify sha256 and GCJ-1 canonical bytes."""

    aref = require_artifact_ref_v1(ref, reason=_REASON_INVARIANT_FAIL)
    raw = registry_load_bytes(aref)
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail(_REASON_INVARIANT_FAIL)
    b = bytes(raw)
    digest = f"sha256:{hashlib.sha256(b).hexdigest()}"
    if digest != aref["artifact_id"]:
        fail("EUDRSU_MCL_HASH_MISMATCH")

    try:
        obj = gcj1_loads_strict(b)
    except Exception:
        fail("EUDRSU_MCL_SCHEMA_INVALID")
    canon = gcj1_canon_bytes(obj)
    if canon != b:
        fail("EUDRSU_MCL_HASH_MISMATCH")
    if not isinstance(obj, dict):
        fail("EUDRSU_MCL_SCHEMA_INVALID")
    return dict(obj), b


def _decode_query_key_q32_s64(*, key_bytes: bytes, key_dim_u32: int) -> list[int]:
    if not isinstance(key_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_STACK_TYPE_ERROR)
    b = bytes(key_bytes)
    d = int(key_dim_u32)
    if d < 0:
        fail(_REASON_INVARIANT_FAIL)
    if len(b) != 8 * d:
        fail(_REASON_INVARIANT_FAIL)
    out: list[int] = []
    for i in range(d):
        out.append(int(struct.unpack_from("<q", b, i * 8)[0]))
    return out


def _retrieve_shard_topk_v1(
    *,
    ml_index_ctx: MLIndexCtxV1,
    registry_load_bytes: Callable[[dict[str, str]], bytes],
    query_key_bytes: bytes,
    top_k_u32: int,
) -> tuple[tuple[bytes, ...], bytes, int]:
    """Return (payload_hashes, retrieval_trace_root32, scanned_records_total_u64)."""

    if not isinstance(ml_index_ctx, MLIndexCtxV1) or not callable(registry_load_bytes):
        fail(_REASON_INVARIANT_FAIL)

    manifest = require_ml_index_manifest_v1(ml_index_ctx.index_manifest_obj)
    query_key_q32 = _decode_query_key_q32_s64(key_bytes=query_key_bytes, key_dim_u32=int(manifest.key_dim_u32))

    scanned_total = 0

    def _load_page_bytes(ref: dict[str, str]) -> bytes:
        nonlocal scanned_total
        # retrieve_topk_v1 already re-hashes; we also need scanned count for cost.
        aref = require_artifact_ref_v1(ref)
        raw = registry_load_bytes(aref)
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            fail(_REASON_INVARIANT_FAIL)
        b = bytes(raw)
        # scanned_total counts scanned records, which are per-page records capped by scan_cap_per_bucket.
        # We compute scanned_total later by parsing the retrieval trace root inputs; easiest is to mirror
        # retrieve_topk_v1's per-record scan accounting. Here we only return bytes; scanning accounting is
        # reconstructed from the retrieval trace below.
        return b

    results, retrieval_trace_root32 = retrieve_topk_v1(
        index_manifest_obj=ml_index_ctx.index_manifest_obj,
        codebook_bytes=ml_index_ctx.codebook_bytes,
        index_root_bytes=ml_index_ctx.index_root_bytes,
        bucket_listing_obj=ml_index_ctx.bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes,
        query_key_q32_s64=query_key_q32,
        top_k_u32=int(top_k_u32),
    )

    # Deterministically recompute scanned_total by re-scanning selected buckets up to scan caps.
    # This is replay-stable because it uses the same listing order, scan caps, and page decoding.
    # Note: This does re-load pages; Phase 6 mandates scanned_records_total is derived inside retrieval.
    scanned_total = _recompute_scanned_total_v1(
        ml_index_ctx=ml_index_ctx,
        registry_load_bytes=registry_load_bytes,
        query_key_q32=query_key_q32,
    )

    payload_hashes = tuple(bytes(ph) for _rh, ph, _score in results)
    return payload_hashes, bytes(retrieval_trace_root32), int(scanned_total)


def _recompute_scanned_total_v1(
    *,
    ml_index_ctx: MLIndexCtxV1,
    registry_load_bytes: Callable[[dict[str, str]], bytes],
    query_key_q32: list[int],
) -> int:
    # Mirror retrieve_topk_v1's bucket selection and scan caps to sum scanned records.
    # This is intentionally redundant but deterministic; it avoids changing the Phase-3 API.
    from .ml_index_v1 import decode_ml_index_codebook_v1, decode_ml_index_page_v1, require_ml_index_bucket_listing_v1
    from .eudrs_u_q32ops_v1 import topk_det
    from .eudrs_u_q32ops_v1 import dot_q32_shift_each_dim_v1, dot_q32_shift_end_v1

    manifest = require_ml_index_manifest_v1(ml_index_ctx.index_manifest_obj)
    listing = require_ml_index_bucket_listing_v1(ml_index_ctx.bucket_listing_obj)
    codebook = decode_ml_index_codebook_v1(ml_index_ctx.codebook_bytes)

    if int(codebook.K_u32) != int(manifest.codebook_size_u32) or int(codebook.d_u32) != int(manifest.key_dim_u32):
        fail(_REASON_INVARIANT_FAIL)

    B = int(manifest.codebook_size_u32)
    if B <= 0:
        fail(_REASON_INVARIANT_FAIL)

    dot_fn = dot_q32_shift_each_dim_v1 if manifest.sim_kind == "DOT_Q32_SHIFT_EACH_DIM_V1" else dot_q32_shift_end_v1

    V = min(int(manifest.bucket_visit_k_u32), B)
    bucket_scores = [(int(dot_fn(query_key_q32, codebook.vec(bucket_id))), int(bucket_id)) for bucket_id in range(B)]
    selected = topk_det(bucket_scores, V)
    selected_bucket_ids = sorted(int(bucket_id) for _score, bucket_id in selected)

    pages_by_bucket: dict[int, list[dict[str, Any]]] = {int(b.bucket_id_u32): [dict({"page_index_u32": p.page_index_u32, "page_ref": p.page_ref}) for p in b.pages] for b in listing.buckets}

    scan_cap = int(manifest.scan_cap_per_bucket_u32)
    if scan_cap <= 0:
        fail(_REASON_INVARIANT_FAIL)

    scanned_total = 0
    for bucket_id in selected_bucket_ids:
        pages = pages_by_bucket.get(int(bucket_id), [])
        scanned = 0
        for entry in pages:
            if scanned >= scan_cap:
                break
            page_ref = require_artifact_ref_v1(entry.get("page_ref"))
            page_bytes = registry_load_bytes(page_ref)
            if not isinstance(page_bytes, (bytes, bytearray, memoryview)):
                fail(_REASON_INVARIANT_FAIL)
            page = decode_ml_index_page_v1(bytes(page_bytes))
            if int(page.bucket_id_u32) != int(bucket_id):
                fail(_REASON_INVARIANT_FAIL)
            for _rec in page.records:
                if scanned >= scan_cap:
                    break
                scanned += 1
        scanned_total += scanned
    return int(scanned_total)


def _require_sha256_digest32(value: bytes) -> str:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        fail(_REASON_STACK_TYPE_ERROR)
    b = bytes(value)
    if len(b) != 32:
        fail(_REASON_STACK_TYPE_ERROR)
    return f"sha256:{b.hex()}"


def run_strategy_v1(
    *,
    strategy_def_obj: dict,
    cartridge_bytes: bytes,
    ontology: OntologyV1,
    ml_index_ctx: MLIndexCtxV1,
    initial_state_bytes: bytes,
    caps_ctx: QXWMRCanonCapsContextV1 | None,
    registry_load_bytes: Callable[[dict[str, str]], bytes],
    artifact_slots: dict[int, dict[str, str]] | None = None,
    root_tuple_obj: dict[str, Any] | None = None,
    dmpl_registry_base_dir: Path | None = None,
    dmpl_mroot_dir: Path | None = None,
    dmpl_oroot_dir: Path | None = None,
) -> tuple[bytes, bytes, int]:
    """Run SLS-VM v1.

    Returns (final_state_bytes, h_sls_tail32, log_count_u32).
    """

    if not callable(registry_load_bytes):
        fail(_REASON_INVARIANT_FAIL)
    if not isinstance(ontology, OntologyV1):
        fail(_REASON_INVARIANT_FAIL)
    if not isinstance(ml_index_ctx, MLIndexCtxV1):
        fail(_REASON_INVARIANT_FAIL)

    strategy_def = _require_strategy_def_v1(strategy_def_obj)

    budgets = dict(strategy_def["budgets"])
    instr_cap_u64 = int(budgets["instr_cap_u64"])
    cost_cap_u64 = int(budgets["cost_cap_u64"])
    log_cap_u32 = int(budgets["log_cap_u32"])
    retrieve_cap_u32 = int(budgets["retrieve_cap_u32"])
    unify_cap_u32 = int(budgets["unify_cap_u32"])
    apply_cap_u32 = int(budgets["apply_cap_u32"])
    lift_cap_u32 = int(budgets["lift_cap_u32"])
    project_cap_u32 = int(budgets["project_cap_u32"])
    plan_cap_u32 = int(budgets["plan_cap_u32"])
    urc_cap_u32 = int(budgets["urc_cap_u32"])
    max_state_bytes_u32 = int(budgets["max_state_bytes_u32"])

    # Ensure concept deps exist in ontology (deterministic).
    for h in list(strategy_def.get("concept_deps", [])):
        if not isinstance(h, str) or h not in ontology.concept_defs_by_handle:
            fail(_REASON_INVARIANT_FAIL)

    # Canonical initial state requirement.
    if not isinstance(initial_state_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_INVARIANT_FAIL)
    state_bytes = bytes(initial_state_bytes)
    if len(state_bytes) > max_state_bytes_u32:
        fail(_REASON_INVARIANT_FAIL)
    try:
        canon0 = canon_state_packed_v1(state_bytes, caps_ctx=caps_ctx)
    except OmegaV18Error:
        fail(_REASON_INVARIANT_FAIL)
    if canon0 != state_bytes:
        fail(_REASON_INVARIANT_FAIL)

    cart = _decode_cartridge_v1(cartridge_bytes)

    # VM registers/counters.
    stack: list[SLSValueV1] = []
    H_sls = b"\x00" * 32
    step_index_u64 = 0
    instr_used_u64 = 0
    cost_used_u64 = 0

    retrieve_calls_u32 = 0
    unify_calls_u32 = 0
    apply_calls_u32 = 0
    lift_calls_u32 = 0
    project_calls_u32 = 0
    plan_calls_u32 = 0
    urc_calls_u32 = 0

    urc_cache: dict[bytes, bytes] = {}

    def _budget_instr() -> None:
        nonlocal instr_used_u64
        instr_used_u64 += 1
        if instr_used_u64 > instr_cap_u64:
            fail(_REASON_BUDGET_EXCEEDED)

    def _budget_cost(delta: int) -> None:
        nonlocal cost_used_u64
        cost_used_u64 += int(delta)
        if cost_used_u64 > cost_cap_u64:
            fail(_REASON_BUDGET_EXCEEDED)

    def _emit_event(
        *,
        kind_u32: int,
        pc_u32: int,
        state_before: bytes,
        state_after: bytes,
        retrieval_trace_root32: bytes = b"\x00" * 32,
        witness_hash32: bytes = b"\x00" * 32,
        aux_hash32: bytes = b"\x00" * 32,
    ) -> None:
        nonlocal H_sls, step_index_u64
        if step_index_u64 >= int(log_cap_u32):
            fail(_REASON_BUDGET_EXCEEDED)
        before_h = _sha25632(state_before)
        after_h = _sha25632(state_after)
        rec = _emit_log_record_v1(
            event_kind_u32=int(kind_u32),
            step_index_u64=int(step_index_u64),
            pc_u32=int(pc_u32),
            state_before_hash32=before_h,
            state_after_hash32=after_h,
            retrieval_trace_root32=bytes(retrieval_trace_root32),
            witness_hash32=bytes(witness_hash32),
            aux_hash32=bytes(aux_hash32),
            instr_used_u64=int(instr_used_u64),
            cost_used_u64=int(cost_used_u64),
        )
        H_sls = hashlib.sha256(bytes(H_sls) + rec).digest()
        step_index_u64 += 1

    def _emit_event_hashes(
        *,
        kind_u32: int,
        pc_u32: int,
        state_before_hash32: bytes,
        state_after_hash32: bytes,
        retrieval_trace_root32: bytes = b"\x00" * 32,
        witness_hash32: bytes = b"\x00" * 32,
        aux_hash32: bytes = b"\x00" * 32,
    ) -> None:
        nonlocal H_sls, step_index_u64
        if step_index_u64 >= int(log_cap_u32):
            fail(_REASON_BUDGET_EXCEEDED)
        rec = _emit_log_record_v1(
            event_kind_u32=int(kind_u32),
            step_index_u64=int(step_index_u64),
            pc_u32=int(pc_u32),
            state_before_hash32=_require_bytes32(state_before_hash32),
            state_after_hash32=_require_bytes32(state_after_hash32),
            retrieval_trace_root32=_require_bytes32(retrieval_trace_root32),
            witness_hash32=_require_bytes32(witness_hash32),
            aux_hash32=_require_bytes32(aux_hash32),
            instr_used_u64=int(instr_used_u64),
            cost_used_u64=int(cost_used_u64),
        )
        H_sls = hashlib.sha256(bytes(H_sls) + rec).digest()
        step_index_u64 += 1

    pc = 0
    instrs = cart.instrs

    while pc < len(instrs):
        ins = instrs[pc]
        opcode = int(ins.opcode_u16)
        a = int(ins.a_u32)
        b = int(ins.b_u32)
        c = int(ins.c_u32)

        _budget_instr()

        if opcode == 0x0001:  # HALT
            _emit_event(kind_u32=9, pc_u32=pc, state_before=state_bytes, state_after=state_bytes)
            break

        if opcode == 0x0002:  # LOAD_CONST
            idx = int(a)
            if idx < 0 or idx >= len(cart.consts):
                fail(_REASON_INVARIANT_FAIL)
            const = cart.consts[idx]
            kind = int(const.kind_u32)
            if kind == 1:
                _push(stack, _stack_u32(int(const.value)))
            elif kind == 2:
                _push(stack, _stack_u64(int(const.value)))
            elif kind == 3:
                _push(stack, _stack_s64(int(const.value)))
            elif kind == 4:
                _push(stack, _stack_bytes(bytes(const.value)))
            elif kind == 5:
                _push(stack, _stack_utf8(str(const.value)))
            elif kind == 6:
                _push(stack, _stack_bytes32(bytes(const.value)))
            else:  # pragma: no cover
                fail(_REASON_INVARIANT_FAIL)
            pc += 1
            continue

        if opcode == 0x0003:  # DROP
            _pop(stack)
            pc += 1
            continue

        if opcode == 0x0004:  # DUP
            top = _pop(stack)
            _push(stack, top)
            _push(stack, top)
            pc += 1
            continue

        if opcode == 0x0010:  # RETRIEVE_SHARD_TOPK
            top_k_u32 = int(a)
            if int(b) != 0 or int(c) != 0:
                fail(_REASON_INVARIANT_FAIL)
            query_key_bytes = _expect(_pop(stack), "BYTES")

            retrieve_calls_u32 += 1
            if retrieve_calls_u32 > retrieve_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)

            payload_hashes, trace_root32, scanned_total = _retrieve_shard_topk_v1(
                ml_index_ctx=ml_index_ctx,
                registry_load_bytes=registry_load_bytes,
                query_key_bytes=bytes(query_key_bytes),
                top_k_u32=int(top_k_u32),
            )
            # cost += 100 + scanned_total
            _budget_cost(100 + int(scanned_total))

            _push(stack, SLSValueV1("LIST_BYTES32", payload_hashes))
            _push(stack, _stack_bytes32(trace_root32))
            _emit_event(kind_u32=1, pc_u32=pc, state_before=state_bytes, state_after=state_bytes, retrieval_trace_root32=trace_root32)
            pc += 1
            continue

        if opcode == 0x0011:  # UNIFY_SHARD_REGION
            if int(a) != 0 or int(b) != 0 or int(c) != 0:
                fail(_REASON_INVARIANT_FAIL)

            concept_def_hash32 = _expect(_pop(stack), "BYTES32")
            concept_def_id = _require_sha256_digest32(concept_def_hash32)
            concept_hex = concept_def_id.split(":", 1)[1]
            concept_relpath = f"polymath/registry/eudrs_u/ontology/concepts/sha256_{concept_hex}.concept_def_v1.json"
            concept_ref = {"artifact_id": concept_def_id, "artifact_relpath": concept_relpath}

            unify_calls_u32 += 1
            if unify_calls_u32 > unify_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)

            concept_def_obj, concept_def_raw = _registry_load_gcj1_json(ref=concept_ref, registry_load_bytes=registry_load_bytes)
            # Ensure loaded sha matches the BYTES32 digest (defense-in-depth).
            if _sha25632(concept_def_raw) != bytes(concept_def_hash32):
                fail("EUDRSU_MCL_HASH_MISMATCH")

            shard_ref = require_artifact_ref_v1(concept_def_obj.get("shard_ref"), reason="EUDRSU_MCL_SCHEMA_INVALID")
            shard_raw = registry_load_bytes(shard_ref)
            if not isinstance(shard_raw, (bytes, bytearray, memoryview)):
                fail(_REASON_INVARIANT_FAIL)
            shard_bytes = bytes(shard_raw)
            shard_digest = f"sha256:{hashlib.sha256(shard_bytes).hexdigest()}"
            if shard_digest != shard_ref["artifact_id"]:
                fail("EUDRSU_MCL_HASH_MISMATCH")

            witness_bytes, backtrack_steps, candidate_leafs = _unify_shard_region_with_stats_v1(
                target_state_bytes=state_bytes,
                concept_def_obj=concept_def_obj,
                shard_bytes=shard_bytes,
                caps_ctx=caps_ctx,
            )
            witness_hash32 = bytes(witness_bytes[-32:])
            _budget_cost(50 + int(backtrack_steps) + (10 * int(candidate_leafs)))

            _push(stack, SLSValueV1("WITNESS", bytes(witness_bytes)))
            _push(stack, _stack_bytes32(witness_hash32))
            _emit_event(kind_u32=2, pc_u32=pc, state_before=state_bytes, state_after=state_bytes, witness_hash32=witness_hash32)
            pc += 1
            continue

        if opcode == 0x0012:  # APPLY_SHARD
            if int(a) != 0 or int(b) != 0 or int(c) != 0:
                fail(_REASON_INVARIANT_FAIL)

            witness_bytes = _expect(_pop(stack), "WITNESS")
            concept_def_hash32 = _expect(_pop(stack), "BYTES32")
            concept_def_id = _require_sha256_digest32(concept_def_hash32)
            concept_hex = concept_def_id.split(":", 1)[1]
            concept_relpath = f"polymath/registry/eudrs_u/ontology/concepts/sha256_{concept_hex}.concept_def_v1.json"
            concept_ref = {"artifact_id": concept_def_id, "artifact_relpath": concept_relpath}

            apply_calls_u32 += 1
            if apply_calls_u32 > apply_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)

            concept_def_obj, concept_def_raw = _registry_load_gcj1_json(ref=concept_ref, registry_load_bytes=registry_load_bytes)
            if _sha25632(concept_def_raw) != bytes(concept_def_hash32):
                fail("EUDRSU_MCL_HASH_MISMATCH")

            shard_ref = require_artifact_ref_v1(concept_def_obj.get("shard_ref"), reason="EUDRSU_MCL_SCHEMA_INVALID")
            shard_raw = registry_load_bytes(shard_ref)
            if not isinstance(shard_raw, (bytes, bytearray, memoryview)):
                fail(_REASON_INVARIANT_FAIL)
            shard_bytes = bytes(shard_raw)
            shard_digest = f"sha256:{hashlib.sha256(shard_bytes).hexdigest()}"
            if shard_digest != shard_ref["artifact_id"]:
                fail("EUDRSU_MCL_HASH_MISMATCH")

            before = state_bytes
            after = apply_shard_v1(
                target_state_bytes=state_bytes,
                concept_def_obj=concept_def_obj,
                shard_bytes=shard_bytes,
                witness_bytes=bytes(witness_bytes),
                caps_ctx=caps_ctx,
            )
            if len(after) > max_state_bytes_u32:
                fail(_REASON_INVARIANT_FAIL)

            # cost += 20 + rewrite_op_count
            from .concept_shard_v1 import parse_concept_shard_v1

            shard = parse_concept_shard_v1(shard_bytes)
            _budget_cost(20 + int(shard.rewrite_op_count_u32))

            state_bytes = bytes(after)
            state_hash_after32 = _sha25632(state_bytes)
            _push(stack, _stack_bytes32(state_hash_after32))
            _emit_event(kind_u32=3, pc_u32=pc, state_before=before, state_after=state_bytes, witness_hash32=bytes(witness_bytes[-32:]))
            pc += 1
            continue

        if opcode == 0x0013:  # LIFT
            node_id_u32 = _expect(_pop(stack), "U32")
            lift_calls_u32 += 1
            if lift_calls_u32 > lift_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)
            _budget_cost(10)

            # Enforce FAL caps presence for ladder-modifying ops.
            if caps_ctx is None or not isinstance(caps_ctx, QXWMRCanonCapsContextV1) or not bool(caps_ctx.fal_enabled):
                fail(_REASON_INVARIANT_FAIL)

            before = state_bytes
            st = unpack_state_packed_v1(state_bytes)
            N = int(st.N_u32)
            node_id = int(node_id_u32)
            if node_id < 0 or node_id >= N:
                fail(_REASON_INVARIANT_FAIL)
            if int(st.node_tok_u32[node_id]) == 0:
                fail(_REASON_INVARIANT_FAIL)

            # If there is already at least one outgoing ABSTRACTS edge, return smallest dst; state unchanged.
            dsts: list[int] = []
            for e, tok in enumerate(st.edge_tok_u32):
                if int(tok) != int(EDGE_ABSTRACTS_V1):
                    continue
                if int(st.src_u32[e]) == node_id:
                    dsts.append(int(st.dst_u32[e]))
            if dsts:
                parent = min(dsts)
                _push(stack, _stack_u32(parent))
                _emit_event(kind_u32=4, pc_u32=pc, state_before=state_bytes, state_after=state_bytes)
                pc += 1
                continue

            # Allocate new node + edge, then canonicalize with mapping so returned id refers to canonical state.
            from .concept_shard_v1 import _mutate_state_add_node_and_edge_for_lift_v1
            from .qxwmr_canon_wl_v1 import canon_state_packed_v1_with_node_mapping_v1

            mutated_bytes, new_node_old = _mutate_state_add_node_and_edge_for_lift_v1(
                state_bytes=state_bytes,
                child_node_u32=int(node_id),
                edge_tok_u32=int(EDGE_ABSTRACTS_V1),
            )

            # Canonicalize + get old->new mapping.
            canon_bytes, old_to_new = canon_state_packed_v1_with_node_mapping_v1(mutated_bytes, caps_ctx=caps_ctx)
            state_bytes = bytes(canon_bytes)

            child_new = int(old_to_new[int(node_id)])
            # Find parent in canonical state as smallest dst on outgoing ABSTRACTS edges.
            st2 = unpack_state_packed_v1(state_bytes)
            dsts2: list[int] = []
            for e, tok in enumerate(st2.edge_tok_u32):
                if int(tok) != int(EDGE_ABSTRACTS_V1):
                    continue
                if int(st2.src_u32[e]) == child_new:
                    dsts2.append(int(st2.dst_u32[e]))
            if not dsts2:
                fail(_REASON_INVARIANT_FAIL)
            parent_new = min(dsts2)

            # Defensive: validate FAL constraints (also enforces in/out caps and monotone levels).
            try:
                validate_fal_constraints_for_qxwmr_state_v1(st2, caps_ctx)
            except OmegaV18Error:
                fail(_REASON_INVARIANT_FAIL)
            except Exception:  # noqa: BLE001 - fail-closed
                fail(_REASON_INVARIANT_FAIL)

            _push(stack, _stack_u32(parent_new))
            _emit_event(kind_u32=4, pc_u32=pc, state_before=before, state_after=state_bytes)
            pc += 1
            continue

        if opcode == 0x0014:  # PROJECT
            node_id_u32 = _expect(_pop(stack), "U32")
            project_calls_u32 += 1
            if project_calls_u32 > project_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)
            _budget_cost(5)

            st = unpack_state_packed_v1(state_bytes)
            node_id = int(node_id_u32)
            if node_id < 0 or node_id >= int(st.N_u32):
                fail(_REASON_INVARIANT_FAIL)
            srcs: list[int] = []
            for e, tok in enumerate(st.edge_tok_u32):
                if int(tok) != int(EDGE_ABSTRACTS_V1):
                    continue
                if int(st.dst_u32[e]) == node_id:
                    srcs.append(int(st.src_u32[e]))
            if not srcs:
                fail(_REASON_PROJECT_NO_PARENT)
            parent = min(srcs)
            _push(stack, _stack_u32(parent))
            _emit_event(kind_u32=5, pc_u32=pc, state_before=state_bytes, state_after=state_bytes)
            pc += 1
            continue

        if opcode == 0x0015:  # PLAN_CALL (stub)
            # Phase 2: DMPL PLAN_CALL integration.
            # Instruction immediates:
            #   a_u32 = plan_query_ref_slot_u32
            #   b_u32,c_u32 must be 0
            plan_query_ref_slot_u32 = int(a)
            if int(b) != 0 or int(c) != 0:
                fail(_REASON_INVARIANT_FAIL)
            plan_calls_u32 += 1
            if plan_calls_u32 > plan_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)
            _budget_cost(25)

            if artifact_slots is None or not isinstance(artifact_slots, dict):
                fail(_REASON_INVARIANT_FAIL)
            slot_ref = artifact_slots.get(int(plan_query_ref_slot_u32))
            if not isinstance(slot_ref, dict):
                fail(_REASON_INVARIANT_FAIL)
            plan_query_ref = require_artifact_ref_v1(slot_ref, reason=_REASON_INVARIANT_FAIL)
            if not str(plan_query_ref.get("artifact_relpath", "")).endswith(".dmpl_plan_query_v1.json"):
                fail(_REASON_INVARIANT_FAIL)

            if dmpl_registry_base_dir is None or not isinstance(dmpl_registry_base_dir, Path):
                fail(_REASON_INVARIANT_FAIL)
            if dmpl_mroot_dir is None or not isinstance(dmpl_mroot_dir, Path):
                fail(_REASON_INVARIANT_FAIL)
            if dmpl_oroot_dir is None or not isinstance(dmpl_oroot_dir, Path):
                # Phase 2: execution binding requires an oroot step output artifact.
                fail("DMPL_E_HASH_MISMATCH")
            base_dir = Path(dmpl_registry_base_dir).resolve()
            mroot_dir = Path(dmpl_mroot_dir).resolve()
            oroot_dir = Path(dmpl_oroot_dir).resolve()

            # Verify the PlanQuery ArtifactRef under the provided base dir.
            pq_path = verify_artifact_ref_v1(artifact_ref=plan_query_ref, base_dir=base_dir)
            pq_bytes = pq_path.read_bytes()
            pq_digest = f"sha256:{hashlib.sha256(pq_bytes).hexdigest()}"
            if pq_digest != str(plan_query_ref.get("artifact_id", "")).strip():
                fail("DMPL_E_HASH_MISMATCH")
            try:
                pq_obj = gcj1_loads_strict(pq_bytes)
            except Exception:  # noqa: BLE001 - fail closed
                fail("DMPL_E_NONCANON_GCJ1")
            # Enforce GCJ-1 canonical bytes (do not trust proposer-provided artifact_id).
            if gcj1_canon_bytes(pq_obj) != pq_bytes:
                fail("DMPL_E_NONCANON_GCJ1")
            if not isinstance(pq_obj, dict):
                fail("DMPL_E_OPSET_MISMATCH")
            try:
                validate_schema(pq_obj, "dmpl_plan_query_v1")
            except Exception:  # noqa: BLE001 - fail closed
                fail("DMPL_E_OPSET_MISMATCH")

            # Bind to active droot from root tuple.
            if root_tuple_obj is None or not isinstance(root_tuple_obj, dict):
                fail(_REASON_INVARIANT_FAIL)
            droot_ref = require_artifact_ref_v1(root_tuple_obj.get("droot"), reason=_REASON_INVARIANT_FAIL)
            droot_id_active = str(droot_ref.get("artifact_id", "")).strip()
            if str(pq_obj.get("dmpl_droot_id", "")).strip() != droot_id_active:
                fail("DMPL_E_HASH_MISMATCH")

            # DMPL PLAN_CALL: load runtime from droot, plan, and write artifacts under mroot.
            from .dmpl_config_load_v1 import load_runtime_from_droot_v1
            from .dmpl_planner_dcbts_l_v1 import plan_call_v1
            from .dmpl_types_v1 import DMPLError as _DMPLError
            from .dmpl_types_v1 import _sha25632_count as _dmpl_sha25632_count

            class _FSResolverV1:
                def __init__(self, root: Path) -> None:
                    self._root = Path(root).resolve()

                def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
                    # Deterministic lookup by hashed filename under the base dir.
                    aid = ensure_sha256(artifact_id, reason="DMPL_E_HASH_MISMATCH")
                    hex64 = aid.split(":", 1)[1]
                    at = str(artifact_type).strip()
                    ex = str(ext).strip()
                    if ex not in {"json", "bin"} or not at:
                        fail("DMPL_E_OPSET_MISMATCH")
                    filename = f"sha256_{hex64}.{at}.{ex}"
                    matches = sorted([p for p in self._root.rglob(filename) if p.is_file()], key=lambda p: p.as_posix())
                    if len(matches) != 1:
                        fail("MISSING_STATE_INPUT")
                    return matches[0].read_bytes()

            class _FSArtifactWriterV1:
                def __init__(self, out_dir: Path) -> None:
                    self._out = Path(out_dir).resolve()
                    self._out.mkdir(parents=True, exist_ok=True)

                def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
                    raw = gcj1_canon_bytes(obj)
                    aid = f"sha256:{_dmpl_sha25632_count(raw).hex()}"
                    hex64 = aid.split(":", 1)[1]
                    filename = f"sha256_{hex64}.{str(artifact_type)}.json"
                    path = (self._out / filename).resolve()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        if path.read_bytes() != raw:
                            fail("DMPL_E_HASH_MISMATCH")
                        return aid
                    path.write_bytes(raw)
                    return aid

                def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
                    b = bytes(raw)
                    aid = f"sha256:{_dmpl_sha25632_count(b).hex()}"
                    hex64 = aid.split(":", 1)[1]
                    filename = f"sha256_{hex64}.{str(artifact_type)}.bin"
                    path = (self._out / filename).resolve()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        if path.read_bytes() != b:
                            fail("DMPL_E_HASH_MISMATCH")
                        return aid
                    path.write_bytes(b)
                    return aid

            dmpl_resolver = _FSResolverV1(base_dir)
            mroot_writer = _FSArtifactWriterV1(mroot_dir)
            oroot_writer = _FSArtifactWriterV1(oroot_dir)

            class _DMPLWriterBoundV1:
                def __init__(self, *, mroot_writer: _FSArtifactWriterV1, oroot_writer: _FSArtifactWriterV1, plan_query_obj: dict[str, Any]) -> None:
                    self._mroot = mroot_writer
                    self._oroot = oroot_writer
                    self._pq = dict(plan_query_obj)
                    self._bound_b = False

                def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
                    return self._mroot.write_bin_artifact(str(artifact_type), bytes(raw))

                def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
                    at = str(artifact_type).strip()
                    out_id = self._mroot.write_json_artifact(at, obj)

                    # Phase 2: bind PLAN_CALL execution to oroot via a step output digest.
                    if at == "dmpl_action_receipt_v1":
                        if self._bound_b:
                            fail("DMPL_E_OPSET_MISMATCH")
                        if not isinstance(obj, dict):
                            fail("DMPL_E_OPSET_MISMATCH")
                        cc = self._pq.get("call_context")
                        if not isinstance(cc, dict):
                            fail("DMPL_E_OPSET_MISMATCH")
                        vm_step_u64 = cc.get("vm_step_u64")
                        scenario_id = cc.get("scenario_id")
                        if not isinstance(vm_step_u64, int) or vm_step_u64 < 0:
                            fail("DMPL_E_OPSET_MISMATCH")
                        if not isinstance(scenario_id, str):
                            fail("DMPL_E_OPSET_MISMATCH")

                        step_obj = {
                            "schema_id": "dmpl_step_digest_v1",
                            "dc1_id": str(obj.get("dc1_id", "")),
                            "opset_id": str(obj.get("opset_id", "")),
                            "plan_query_id": str(obj.get("plan_query_id", "")),
                            "vm_step_u64": int(vm_step_u64),
                            "scenario_id": str(scenario_id),
                            "dmpl_action_receipt_id": str(out_id),
                            "chosen_action_hash": str(obj.get("chosen_action_hash", "")),
                        }
                        if str(step_obj.get("dmpl_action_receipt_id", "")).strip() != str(out_id).strip():
                            fail("DMPL_E_HASH_MISMATCH")
                        _ = self._oroot.write_json_artifact("dmpl_step_digest_v1", step_obj)
                        self._bound_b = True

                    return str(out_id)

            dmpl_writer = _DMPLWriterBoundV1(mroot_writer=mroot_writer, oroot_writer=oroot_writer, plan_query_obj=dict(pq_obj))

            try:
                runtime = load_runtime_from_droot_v1(droot_id=str(droot_id_active), resolver=dmpl_resolver)
                # Disabled DMPL => hard fail with no artifacts written.
                if not bool(runtime.config.get("enabled_b", False)):
                    fail("DMPL_E_DISABLED")

                plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(pq_obj), resolver=dmpl_resolver, artifact_writer=dmpl_writer)
            except _DMPLError as exc:
                # Convert DMPL fail-closed errors into the VM's fail-closed error type.
                fail(str(exc.reason_code))
            except OmegaV18Error:
                raise
            except Exception:  # noqa: BLE001 - fail-closed
                fail("DMPL_E_OPSET_MISMATCH")

            chosen_action_hash32 = bytes(plan_result.chosen_action_hash32)
            receipt_id32 = bytes.fromhex(str(plan_result.action_receipt_id).split(":", 1)[1])
            _push(stack, _stack_bytes32(chosen_action_hash32))
            _push(stack, _stack_bytes32(receipt_id32))

            # PLAN_CALL log binding (Phase 2):
            #   aux_hash32 := chosen_action_hash32 (=> chosen_action_hash_id via "sha256:"+hex)
            #   witness_hash32 := action_receipt_id32 (=> action_receipt_id via "sha256:"+hex)
            _emit_event(
                kind_u32=6,
                pc_u32=pc,
                state_before=state_bytes,
                state_after=state_bytes,
                witness_hash32=receipt_id32,
                aux_hash32=chosen_action_hash32,
            )
            pc += 1
            continue

        if opcode == 0x0016:  # WRITE_LOG_DIGEST
            payload_bytes = _expect(_pop(stack), "BYTES")
            _budget_cost(1)
            aux_hash32 = hashlib.sha256(_SLS_USER_LOG_DOMAIN + bytes(payload_bytes)).digest()
            _push(stack, _stack_bytes32(aux_hash32))
            _emit_event(kind_u32=8, pc_u32=pc, state_before=state_bytes, state_after=state_bytes, aux_hash32=aux_hash32)
            pc += 1
            continue

        if opcode == 0x0017:  # INVARIANT_CHECK
            _budget_cost(5)
            # Canonical check.
            canon = canon_state_packed_v1(state_bytes, caps_ctx=caps_ctx)
            if canon != state_bytes:
                fail(_REASON_INVARIANT_FAIL)
            try:
                validate_state_packed_v1(state_bytes)
            except Exception:  # noqa: BLE001 - fail-closed
                fail(_REASON_INVARIANT_FAIL)
            # FAL caps must be explicitly configured if this opcode is present.
            if caps_ctx is None or not isinstance(caps_ctx, QXWMRCanonCapsContextV1) or not bool(caps_ctx.fal_enabled):
                fail(_REASON_INVARIANT_FAIL)
            st = unpack_state_packed_v1(state_bytes)
            try:
                validate_fal_constraints_for_qxwmr_state_v1(st, caps_ctx)
            except OmegaV18Error:
                fail(_REASON_INVARIANT_FAIL)
            except Exception:  # noqa: BLE001 - fail-closed
                fail(_REASON_INVARIANT_FAIL)
            _emit_event(kind_u32=7, pc_u32=pc, state_before=state_bytes, state_after=state_bytes)
            pc += 1
            continue

        if opcode == 0x0018:  # URC_STEP
            if int(a) != 0 or int(b) != 0 or int(c) != 0:
                fail(_REASON_INVARIANT_FAIL)

            capsule_before_hash32 = _expect(_pop(stack), "BYTES32")
            step_budget_u64 = _expect(_pop(stack), "U64")
            capsule_def_hash32 = _expect(_pop(stack), "BYTES32")

            urc_calls_u32 += 1
            if urc_calls_u32 > urc_cap_u32:
                fail(_REASON_BUDGET_EXCEEDED)

            capsule_def_id = _require_sha256_digest32(capsule_def_hash32)
            capsule_def_hex = capsule_def_id.split(":", 1)[1]
            capsule_def_relpath = f"polymath/registry/eudrs_u/capsules/sha256_{capsule_def_hex}.urc_capsule_def_v1.json"
            capsule_def_ref = {"artifact_id": capsule_def_id, "artifact_relpath": capsule_def_relpath}
            capsule_def_obj, capsule_def_raw = _registry_load_gcj1_json(ref=capsule_def_ref, registry_load_bytes=registry_load_bytes)
            try:
                validate_schema(capsule_def_obj, "urc_capsule_def_v1")
            except Exception:  # noqa: BLE001 - fail-closed
                fail(_REASON_INVARIANT_FAIL)
            if _sha25632(capsule_def_raw) != bytes(capsule_def_hash32):
                fail(_REASON_INVARIANT_FAIL)

            capsule_before_id = _require_sha256_digest32(capsule_before_hash32)
            capsule_before_hex = capsule_before_id.split(":", 1)[1]
            capsule_before_relpath = f"polymath/registry/eudrs_u/capsules/sha256_{capsule_before_hex}.urc_capsule_v1.bin"
            capsule_before_ref = {"artifact_id": capsule_before_id, "artifact_relpath": capsule_before_relpath}

            cap_before_bytes = urc_cache.get(bytes(capsule_before_hash32))
            if cap_before_bytes is None:
                raw = registry_load_bytes(require_artifact_ref_v1(capsule_before_ref))
                if not isinstance(raw, (bytes, bytearray, memoryview)):
                    fail(_REASON_INVARIANT_FAIL)
                cap_before_bytes = bytes(raw)
                urc_cache[bytes(capsule_before_hash32)] = cap_before_bytes
            if _sha25632(cap_before_bytes) != bytes(capsule_before_hash32):
                fail(_REASON_INVARIANT_FAIL)

            def _urc_load_bytes_by_hash32(hash32: bytes, kind: str) -> bytes:
                h = _require_bytes32(hash32)
                if h == (b"\x00" * 32):
                    fail(_REASON_INVARIANT_FAIL)
                cached = urc_cache.get(bytes(h))
                if cached is not None:
                    if _sha25632(cached) != bytes(h):
                        fail(_REASON_INVARIANT_FAIL)
                    return bytes(cached)

                if str(kind) == "page":
                    rel = urc_derive_page_relpath_v1(h)
                elif str(kind) == "ptnode":
                    rel = urc_derive_ptnode_relpath_v1(h)
                else:
                    fail(_REASON_INVARIANT_FAIL)

                ref = {"artifact_id": f"sha256:{h.hex()}", "artifact_relpath": rel}
                raw = registry_load_bytes(require_artifact_ref_v1(ref))
                if not isinstance(raw, (bytes, bytearray, memoryview)):
                    fail(_REASON_INVARIANT_FAIL)
                b = bytes(raw)
                if _sha25632(b) != bytes(h):
                    fail(_REASON_INVARIANT_FAIL)
                urc_cache[bytes(h)] = b
                return b

            capsule_after_bytes, memroot_after32, h_urc_tail32, steps_executed_u64, new_pages, new_nodes = urc_step_capsule_v1(
                capsule_bytes=bytes(cap_before_bytes),
                capsule_def_obj=dict(capsule_def_obj),
                step_budget_u64=int(step_budget_u64),
                load_bytes_by_hash32=_urc_load_bytes_by_hash32,
            )

            capsule_after_hash32 = _sha25632(capsule_after_bytes)
            urc_cache[bytes(capsule_after_hash32)] = bytes(capsule_after_bytes)

            for h32, raw in dict(new_pages).items():
                hb = _require_bytes32(h32)
                bb = bytes(raw)
                if _sha25632(bb) != hb:
                    fail(_REASON_INVARIANT_FAIL)
                urc_cache[hb] = bb
            for h32, raw in dict(new_nodes).items():
                hb = _require_bytes32(h32)
                bb = bytes(raw)
                if _sha25632(bb) != hb:
                    fail(_REASON_INVARIANT_FAIL)
                urc_cache[hb] = bb

            page_ids: set[int] = set()
            for _h, raw in dict(new_pages).items():
                pid, _data = urc_parse_page_v1(bytes(raw))
                page_ids.add(int(pid))
            pages_written_distinct = len(page_ids)
            _budget_cost(200 + int(steps_executed_u64) + (50 * int(pages_written_distinct)))

            _push(stack, _stack_bytes32(bytes(capsule_after_hash32)))
            _push(stack, _stack_bytes32(_require_bytes32(memroot_after32)))
            _push(stack, _stack_bytes32(_require_bytes32(h_urc_tail32)))

            _emit_event_hashes(
                kind_u32=10,
                pc_u32=pc,
                state_before_hash32=bytes(capsule_before_hash32),
                state_after_hash32=bytes(capsule_after_hash32),
                witness_hash32=_require_bytes32(memroot_after32),
                aux_hash32=_require_bytes32(h_urc_tail32),
                retrieval_trace_root32=b"\x00" * 32,
            )
            pc += 1
            continue

        fail(_REASON_OPCODE_INVALID)

    return bytes(state_bytes), bytes(H_sls), int(step_index_u64)


__all__ = [
    "EDGE_ABSTRACTS_V1",
    "MLIndexCtxV1",
    "SLSCartridgeV1",
    "SLSConstV1",
    "SLSInstrV1",
    "SLSValueV1",
    "run_strategy_v1",
]
