from __future__ import annotations

import importlib.util
import hashlib
import struct
from pathlib import Path
from typing import Any, Callable

import pytest

# This suite is pinned to the URC implementation and AGI-Stack polymath registry.
# Some CDEL-v2 checkouts (including this branch) intentionally do not include URC.
if importlib.util.find_spec("cdel.v18_0.eudrs_u.urc_merkle_v1") is None:
    pytest.skip("requires URC implementation (urc_merkle_v1 missing)", allow_module_level=True)

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.ontology_v1 import OntologyV1
from cdel.v18_0.eudrs_u.qxwmr_canon_wl_v1 import canon_state_packed_v1
from cdel.v18_0.eudrs_u.qxwmr_state_v1 import QXWMRStatePackedV1, encode_state_packed_v1
from cdel.v18_0.eudrs_u.sls_vm_v1 import MLIndexCtxV1, run_strategy_v1
from cdel.v18_0.eudrs_u.urc_merkle_v1 import (
    ZERO32,
    urc_derive_page_relpath_v1,
    urc_derive_ptnode_relpath_v1,
    urc_mem_read64_v1,
    urc_parse_page_v1,
    urc_pt_lookup_page_hash_v1,
)
from cdel.v18_0.eudrs_u.urc_vm_v1 import URCCapsuleV1, urc_encode_capsule_v1, urc_parse_capsule_v1, urc_step_capsule_v1, verify_universality_cert_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error, repo_root


# This suite requires the AGI-Stack polymath registry golden fixtures.
_ROOT = repo_root()
_REQUIRED_DIRS = [
    _ROOT / "polymath/registry/eudrs_u/capsules",
    _ROOT / "polymath/registry/eudrs_u/certs",
    _ROOT / "polymath/registry/eudrs_u/memory/urc_pt",
    _ROOT / "polymath/registry/eudrs_u/memory/urc_pages",
]
if not all(p.is_dir() for p in _REQUIRED_DIRS):
    pytest.skip("requires URC polymath registry fixtures (run via AGI-Stack)", allow_module_level=True)


# Phase-7 pinned golden vector constants.
_MEMRW_BEFORE_ID = "sha256:976abf9f6df7b1790f303ab1c06cab3a2f938b952681c7ba1d375a97e2d2fac9"
_MEMRW_AFTER_ID = "sha256:330c18aed2ba04fc8a4341acf6babc97b14b53d1e7efeba7043272dec0e532ed"
_MEMRW_MEMROOT_AFTER_HEX = "0f8df0cbcddb5b8e254b604e987df39554011347bb1e2edd5963fd7837541c2a"
_MEMRW_TAIL_AFTER_HEX = "5eec7b8705e54e5d646df37187e88cbdda62b96e86a662d6444cb0a6a1427ae5"

_CALLRET_BEFORE_ID = "sha256:008e9bc7d975e80e2a5f407cf2f26e53ecc17aea693e4b5c8113533f73bacc28"
_CALLRET_AFTER_ID = "sha256:b32a2a7de0715d56f50f15bbc306ab36d3c82175359ca88838b6befd53fc10e2"
_CALLRET_MEMROOT_AFTER_HEX = "00" * 32
_CALLRET_TAIL_AFTER_HEX = "601542d756d166ec1f41717c8e169c7d016ee9d351f3d63a6a46780fcf4e20a7"

_BRANCH_BEFORE_ID = "sha256:23af01e3a43e2ea1f9d44f695a81f10c0a448e80f07681eed868175760a78ef5"
_BRANCH_AFTER_ID = "sha256:edb265ad8ac9cab75dfd2aea1c213141e91afb1c9c5a197fcbabb081bf5cac3f"
_BRANCH_MEMROOT_AFTER_HEX = "00" * 32
_BRANCH_TAIL_AFTER_HEX = "050e6f4bd3d85838f2787b38f5db8aaf75ac999ee1e53b943a333c868fccd198"

# Merkle proof pinned fixture for MEMRW.
_MEMRW_PAGE_ID_U32 = 1
_MEMRW_PAGE_HASH_HEX = "44b7fb0e233c43b28ba2b2d39a1963d17bfaf313ddd643b18fe3a09fdd69d985"
_MEMRW_PT_L3_HASH_HEX = "56eae96a9a748bccd1a09be9ea3e025bd85a35e3876db0095712158e86c086fd"
_MEMRW_PT_L2_HASH_HEX = "0a3a631a4263ba26a921d6fb1c414ff47e031a8b3ebf5cc0d0cfe428b32c503f"
_MEMRW_PT_L1_HASH_HEX = "a6e377c8fc8a5ffff40dd2e0a60519a9812b9eba8ad56324b064384c44f501bd"
_MEMRW_PT_ROOT_HASH_HEX = _MEMRW_MEMROOT_AFTER_HEX


def _load_bytes_by_artifact_id_from_repo(artifact_id: str) -> bytes:
    if not isinstance(artifact_id, str) or not artifact_id.startswith("sha256:"):
        raise OmegaV18Error("INVALID:SCHEMA_FAIL")
    hex_ = artifact_id.split(":", 1)[1]
    if len(hex_) != 64:
        raise OmegaV18Error("INVALID:SCHEMA_FAIL")
    p = repo_root() / f"polymath/registry/eudrs_u/capsules/sha256_{hex_}.urc_capsule_v1.bin"
    raw = p.read_bytes()
    if sha256_prefixed(raw) != artifact_id:
        raise OmegaV18Error("INVALID:NONDETERMINISTIC")
    return raw


def _load_urc_mem_bytes_by_hash32_from_repo(hash32: bytes, kind: str) -> bytes:
    if not isinstance(hash32, (bytes, bytearray, memoryview)):
        raise OmegaV18Error("INVALID:SCHEMA_FAIL")
    h = bytes(hash32)
    if len(h) != 32 or h == (b"\x00" * 32):
        raise OmegaV18Error("INVALID:SCHEMA_FAIL")

    if str(kind) == "page":
        rel = urc_derive_page_relpath_v1(h)
    elif str(kind) == "ptnode":
        rel = urc_derive_ptnode_relpath_v1(h)
    else:
        raise OmegaV18Error("INVALID:SCHEMA_FAIL")

    p = repo_root() / rel
    raw = p.read_bytes()
    if hashlib.sha256(raw).digest() != h:
        raise OmegaV18Error("INVALID:NONDETERMINISTIC")
    return raw


def _load_universality_cert_obj_from_repo() -> dict[str, Any]:
    cert_dir = repo_root() / "polymath/registry/eudrs_u/certs"
    if not cert_dir.exists() or not cert_dir.is_dir():
        raise OmegaV18Error("INVALID:MISSING_STATE_INPUT")

    paths = sorted(cert_dir.glob("sha256_*.universality_cert_v1.json"))
    if not paths:
        raise OmegaV18Error("INVALID:MISSING_STATE_INPUT")

    required_before_ids = {_MEMRW_BEFORE_ID, _CALLRET_BEFORE_ID, _BRANCH_BEFORE_ID}

    for p in paths:
        raw = p.read_bytes()
        obj = gcj1_loads_strict(raw)
        if not isinstance(obj, dict):
            continue
        if str(obj.get("schema_id", "")) != "universality_cert_v1":
            continue
        # Ensure GCJ-1 canonical bytes.
        if gcj1_canon_bytes(obj) != raw:
            raise OmegaV18Error("INVALID:NONDETERMINISTIC")

        golden = ((obj.get("urc_vm") or {}).get("golden_vectors")) if isinstance(obj.get("urc_vm"), dict) else None
        if not isinstance(golden, list):
            continue
        before_ids = {str(row.get("capsule_before_id")) for row in golden if isinstance(row, dict)}
        if not required_before_ids.issubset(before_ids):
            continue

        return dict(obj)

    raise OmegaV18Error("INVALID:MISSING_STATE_INPUT")


def test_urc_capsule_decode_encode_roundtrip_pinned() -> None:
    before = _load_bytes_by_artifact_id_from_repo(_MEMRW_BEFORE_ID)
    assert sha256_prefixed(before) == _MEMRW_BEFORE_ID

    cap = urc_parse_capsule_v1(before)
    out = urc_encode_capsule_v1(cap)
    assert out == before


def test_verify_universality_cert_v1_accepts_pinned_golden_vectors() -> None:
    cert = _load_universality_cert_obj_from_repo()
    ok, reason = verify_universality_cert_v1(
        universality_cert_obj=cert,
        load_bytes_by_artifact_id=_load_bytes_by_artifact_id_from_repo,
        load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
    )
    assert ok is True
    assert reason == "OK"


def test_verify_universality_cert_v1_detects_mutated_after_bytes() -> None:
    cert = _load_universality_cert_obj_from_repo()

    def _load_mutated(artifact_id: str) -> bytes:
        raw = _load_bytes_by_artifact_id_from_repo(artifact_id)
        if artifact_id == _MEMRW_AFTER_ID:
            b = bytearray(raw)
            b[0] ^= 0x01
            return bytes(b)
        return raw

    ok, reason = verify_universality_cert_v1(
        universality_cert_obj=cert,
        load_bytes_by_artifact_id=_load_mutated,
        load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
    )
    assert ok is False
    assert reason == "EUDRSU_URC_GOLDEN_TRACE_MISMATCH"


def test_urc_merkle_proof_fixture_memrw() -> None:
    memroot = bytes.fromhex(_MEMRW_MEMROOT_AFTER_HEX)
    page_hash_expected = bytes.fromhex(_MEMRW_PAGE_HASH_HEX)

    # Ensure all pinned ptnodes exist and hash-match.
    for hx in (_MEMRW_PT_ROOT_HASH_HEX, _MEMRW_PT_L1_HASH_HEX, _MEMRW_PT_L2_HASH_HEX, _MEMRW_PT_L3_HASH_HEX):
        node_hash32 = bytes.fromhex(hx)
        node_bytes = _load_urc_mem_bytes_by_hash32_from_repo(node_hash32, "ptnode")
        assert hashlib.sha256(node_bytes).digest() == node_hash32

    # Lookup must return the pinned page hash.
    page_hash32 = urc_pt_lookup_page_hash_v1(
        pt_root_hash32=memroot,
        page_id_u32=_MEMRW_PAGE_ID_U32,
        load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
    )
    assert page_hash32 == page_hash_expected

    page_bytes = _load_urc_mem_bytes_by_hash32_from_repo(page_hash32, "page")
    assert hashlib.sha256(page_bytes).digest() == page_hash32

    pid_u32, page_data = urc_parse_page_v1(page_bytes)
    assert int(pid_u32) == _MEMRW_PAGE_ID_U32
    assert len(page_data) == 4096

    # Basic sanity: LOAD64 at addr 0x1000 should return 0x11223344 in the pinned fixture.
    v = urc_mem_read64_v1(
        pt_root_hash32=memroot,
        addr_u64=0x1000,
        load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
    )
    assert int(v) == 0x11223344


def _ins(op_u8: int, rd_u8: int, rs_u8: int, rt_u8: int, imm_i32: int) -> bytes:
    if any((x < 0 or x > 0xFF) for x in (op_u8, rd_u8, rs_u8, rt_u8)):
        raise AssertionError("bad reg/op")
    if imm_i32 < -(1 << 31) or imm_i32 > (1 << 31) - 1:
        raise AssertionError("bad imm")
    return struct.pack("<BBBBi", int(op_u8), int(rd_u8), int(rs_u8), int(rt_u8), int(imm_i32))


def _build_capsule_bytes(*, instrs: list[bytes], call_depth_u32: int = 0) -> bytes:
    instr_bytes = b"".join(instrs)
    cap = URCCapsuleV1(
        pc_u32=0,
        flags_u32=0,
        pt_root_hash32=ZERO32,
        regs_u64=[0] * 16,
        call_depth_u32=int(call_depth_u32),
        call_stack_u32=[0] * 16,
        instr_count_u32=len(instrs),
        instr_bytes=instr_bytes,
    )
    return urc_encode_capsule_v1(cap)


def _capsule_def_obj_for_capsule(*, capsule_id: str, instr_step_cap_u64: int, mem_write_ops_cap_u64: int, mem_write_pages_cap_u32: int) -> dict[str, Any]:
    if not isinstance(capsule_id, str) or not capsule_id.startswith("sha256:"):
        raise AssertionError("capsule_id must be sha256:...")
    hex_ = capsule_id.split(":", 1)[1]
    obj: dict[str, Any] = {
        "schema_id": "urc_capsule_def_v1",
        "capsule_def_id": "sha256:" + ("0" * 64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "handle": "capsule/tests/budget",
        "isa_kind": "URC_ISA_V1",
        "page_shift_u32": 12,
        "pt_fanout_u32": 256,
        "pt_depth_u32": 4,
        "call_depth_cap_u32": 16,
        "budgets": {
            "instr_step_cap_u64": int(instr_step_cap_u64),
            "mem_write_ops_cap_u64": int(mem_write_ops_cap_u64),
            "mem_write_pages_cap_u32": int(mem_write_pages_cap_u32),
        },
        "capsule_bin_ref": {
            "artifact_id": capsule_id,
            "artifact_relpath": f"polymath/registry/eudrs_u/capsules/sha256_{hex_}.urc_capsule_v1.bin",
        },
    }
    tmp = dict(obj)
    tmp["capsule_def_id"] = "sha256:" + ("0" * 64)
    obj["capsule_def_id"] = sha256_prefixed(gcj1_canon_bytes(tmp))
    return obj


def test_urc_budget_step_cap_rejected() -> None:
    before = _load_bytes_by_artifact_id_from_repo(_MEMRW_BEFORE_ID)
    cap_def = _capsule_def_obj_for_capsule(
        capsule_id=_MEMRW_BEFORE_ID,
        instr_step_cap_u64=1,
        mem_write_ops_cap_u64=1,
        mem_write_pages_cap_u32=1,
    )
    with pytest.raises(OmegaV18Error):
        urc_step_capsule_v1(
            capsule_bytes=before,
            capsule_def_obj=cap_def,
            step_budget_u64=2,
            load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
        )


def test_urc_budget_store_ops_cap_rejected() -> None:
    # Two STORE64 ops but cap is 1.
    cap_bytes = _build_capsule_bytes(
        instrs=[
            _ins(0x02, 1, 0, 0, 0x1000),  # MOVI R1, 0x1000
            _ins(0x02, 2, 0, 0, 0x11223344),  # MOVI R2, 0x11223344
            _ins(0x0D, 0, 1, 2, 0),  # STORE64 [R1+0], R2
            _ins(0x0D, 0, 1, 2, 8),  # STORE64 [R1+8], R2
            _ins(0x01, 0, 0, 0, 0),  # HALT
        ]
    )
    cap_id = sha256_prefixed(cap_bytes)
    cap_def = _capsule_def_obj_for_capsule(
        capsule_id=cap_id,
        instr_step_cap_u64=10,
        mem_write_ops_cap_u64=1,
        mem_write_pages_cap_u32=1,
    )

    with pytest.raises(OmegaV18Error):
        urc_step_capsule_v1(
            capsule_bytes=cap_bytes,
            capsule_def_obj=cap_def,
            step_budget_u64=10,
            load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
        )


def test_urc_budget_distinct_pages_cap_rejected() -> None:
    # Two distinct pages but cap is 1.
    cap_bytes = _build_capsule_bytes(
        instrs=[
            _ins(0x02, 1, 0, 0, 0x1000),  # MOVI R1, 0x1000
            _ins(0x02, 2, 0, 0, 1),  # MOVI R2, 1
            _ins(0x0D, 0, 1, 2, 0),  # STORE64 [R1+0], R2  (page_id=1)
            _ins(0x02, 1, 0, 0, 0x2000),  # MOVI R1, 0x2000
            _ins(0x0D, 0, 1, 2, 0),  # STORE64 [R1+0], R2  (page_id=2)
            _ins(0x01, 0, 0, 0, 0),  # HALT
        ]
    )
    cap_id = sha256_prefixed(cap_bytes)
    cap_def = _capsule_def_obj_for_capsule(
        capsule_id=cap_id,
        instr_step_cap_u64=10,
        mem_write_ops_cap_u64=10,
        mem_write_pages_cap_u32=1,
    )

    with pytest.raises(OmegaV18Error):
        urc_step_capsule_v1(
            capsule_bytes=cap_bytes,
            capsule_def_obj=cap_def,
            step_budget_u64=10,
            load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
        )


def test_urc_call_overflow_rejected() -> None:
    cap_bytes = _build_capsule_bytes(instrs=[_ins(0x13, 0, 0, 0, 0)], call_depth_u32=16)  # CALL 0
    cap_id = sha256_prefixed(cap_bytes)
    cap_def = _capsule_def_obj_for_capsule(
        capsule_id=cap_id,
        instr_step_cap_u64=1,
        mem_write_ops_cap_u64=0,
        mem_write_pages_cap_u32=0,
    )

    with pytest.raises(OmegaV18Error):
        urc_step_capsule_v1(
            capsule_bytes=cap_bytes,
            capsule_def_obj=cap_def,
            step_budget_u64=1,
            load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
        )


def test_urc_ret_underflow_rejected() -> None:
    cap_bytes = _build_capsule_bytes(instrs=[_ins(0x14, 0, 0, 0, 0)])  # RET
    cap_id = sha256_prefixed(cap_bytes)
    cap_def = _capsule_def_obj_for_capsule(
        capsule_id=cap_id,
        instr_step_cap_u64=1,
        mem_write_ops_cap_u64=0,
        mem_write_pages_cap_u32=0,
    )

    with pytest.raises(OmegaV18Error):
        urc_step_capsule_v1(
            capsule_bytes=cap_bytes,
            capsule_def_obj=cap_def,
            step_budget_u64=1,
            load_bytes_by_hash32=_load_urc_mem_bytes_by_hash32_from_repo,
        )


def _cartridge_bytes(*, consts: list[tuple[int, bytes]], instrs: list[tuple[int, int, int, int]]) -> bytes:
    out = bytearray()
    out += struct.pack("<4sIII4I", b"SLS1", 1, len(consts), len(instrs), 0, 0, 0, 0)
    for kind_u32, payload in consts:
        out += struct.pack("<II", int(kind_u32), len(payload))
        out += bytes(payload)
    for opcode_u16, a_u32, b_u32, c_u32 in instrs:
        out += struct.pack("<HHIII", int(opcode_u16), 0, int(a_u32), int(b_u32), int(c_u32))
    return bytes(out)


def _strategy_def_obj(*, cartridge_ref: dict[str, str], budgets: dict[str, int]) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "schema_id": "strategy_def_v1",
        "strategy_id": "sha256:" + ("0" * 64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "handle": "strategy/tests/urc_step",
        "cartridge_ref": dict(cartridge_ref),
        "concept_deps": [],
        "budgets": dict(budgets),
    }
    tmp = dict(obj)
    tmp["strategy_id"] = "sha256:" + ("0" * 64)
    obj["strategy_id"] = sha256_prefixed(gcj1_canon_bytes(tmp))
    return obj


def _canonical_state_minimal() -> bytes:
    st = QXWMRStatePackedV1(
        flags_u32=0,
        N_u32=1,
        E_u32=0,
        K_n_u32=0,
        K_e_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        Lmax_u16=0,
        kappa_bits_u16=0,
        node_tok_u32=[7],
        node_level_u16=None,
        node_attr_s64le=b"",
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
        edge_attr_s64le=b"",
        r_s64le=b"",
        kappa_bitfield=b"",
    )
    raw = encode_state_packed_v1(st)
    return canon_state_packed_v1(raw, caps_ctx=None)


def _sls_log_record_v1(
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
    out = bytearray()
    out += b"SLD1"
    out += struct.pack("<I", 1)  # version_u32
    out += struct.pack("<I", int(event_kind_u32) & 0xFFFFFFFF)
    out += struct.pack("<Q", int(step_index_u64) & 0xFFFFFFFFFFFFFFFF)
    out += struct.pack("<I", int(pc_u32) & 0xFFFFFFFF)
    out += struct.pack("<I", 0)  # reserved_u32
    out += bytes(state_before_hash32)
    out += bytes(state_after_hash32)
    out += bytes(retrieval_trace_root32)
    out += bytes(witness_hash32)
    out += bytes(aux_hash32)
    out += struct.pack("<Q", int(instr_used_u64) & 0xFFFFFFFFFFFFFFFF)
    out += struct.pack("<Q", int(cost_used_u64) & 0xFFFFFFFFFFFFFFFF)
    out += b"\x00" * (6 * 8)  # reserved_u64[6]
    out += struct.pack("<I", 0)  # reserved_u32_tail
    assert len(out) == 256
    return bytes(out)


def test_sls_urc_step_integration_fixture_memrw() -> None:
    root = repo_root()

    capsule_def_id = "sha256:fa74bdfdac2c089946deede922d5bf652db3cacd6f6320e12f7d79655175eb6f"
    capsule_def_hash32 = bytes.fromhex(capsule_def_id.split(":", 1)[1])

    capsule_before_hash32 = bytes.fromhex(_MEMRW_BEFORE_ID.split(":", 1)[1])
    step_budget_u64 = 8

    consts = [
        (6, capsule_before_hash32),
        (2, struct.pack("<Q", step_budget_u64)),
        (6, capsule_def_hash32),
    ]
    # Stack top first for URC_STEP pop order: capsule_before, step_budget, capsule_def.
    # So we push capsule_def, step_budget, capsule_before.
    instrs = [
        (0x0002, 2, 0, 0),  # LOAD_CONST 2 (capsule_def)
        (0x0002, 1, 0, 0),  # LOAD_CONST 1 (step_budget)
        (0x0002, 0, 0, 0),  # LOAD_CONST 0 (capsule_before)
        (0x0018, 0, 0, 0),  # URC_STEP
        (0x0001, 0, 0, 0),  # HALT
    ]
    cartridge = _cartridge_bytes(consts=consts, instrs=instrs)

    # Strategy budgets must include urc_cap_u32 and allow 2 log records.
    budgets = {
        "instr_cap_u64": 10,
        "cost_cap_u64": 10000,
        "log_cap_u32": 10,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1024,
    }

    strategy_def = _strategy_def_obj(
        cartridge_ref={"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/strategies/sha256_00.strategy_cartridge_v1.bin"},
        budgets=budgets,
    )

    initial_state = _canonical_state_minimal()

    ontology = OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[])
    ml_index_ctx = MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={})

    def _registry_load_bytes(ref: dict[str, str]) -> bytes:
        rel = str(ref.get("artifact_relpath", ""))
        if not rel:
            raise OmegaV18Error("INVALID:SCHEMA_FAIL")
        p = root / rel
        raw = p.read_bytes()
        if sha256_prefixed(raw) != str(ref.get("artifact_id")):
            raise OmegaV18Error("INVALID:NONDETERMINISTIC")
        return raw

    final_state, h_sls_tail32, log_count = run_strategy_v1(
        strategy_def_obj=strategy_def,
        cartridge_bytes=cartridge,
        ontology=ontology,
        ml_index_ctx=ml_index_ctx,
        initial_state_bytes=initial_state,
        caps_ctx=None,
        registry_load_bytes=_registry_load_bytes,
    )

    assert final_state == initial_state
    assert log_count == 2

    # Expected SLS log chain for this minimal program: URC_STEP record then HALT record.
    memroot_after32 = bytes.fromhex(_MEMRW_MEMROOT_AFTER_HEX)
    h_urc_tail32 = bytes.fromhex(_MEMRW_TAIL_AFTER_HEX)
    capsule_after_hash32 = bytes.fromhex(_MEMRW_AFTER_ID.split(":", 1)[1])

    state_hash32 = hashlib.sha256(initial_state).digest()

    rec0 = _sls_log_record_v1(
        event_kind_u32=10,
        step_index_u64=0,
        pc_u32=3,
        state_before_hash32=capsule_before_hash32,
        state_after_hash32=capsule_after_hash32,
        retrieval_trace_root32=b"\x00" * 32,
        witness_hash32=memroot_after32,
        aux_hash32=h_urc_tail32,
        instr_used_u64=4,
        cost_used_u64=255,
    )
    rec1 = _sls_log_record_v1(
        event_kind_u32=9,
        step_index_u64=1,
        pc_u32=4,
        state_before_hash32=state_hash32,
        state_after_hash32=state_hash32,
        retrieval_trace_root32=b"\x00" * 32,
        witness_hash32=b"\x00" * 32,
        aux_hash32=b"\x00" * 32,
        instr_used_u64=5,
        cost_used_u64=255,
    )

    H0 = b"\x00" * 32
    H1 = hashlib.sha256(H0 + rec0).digest()
    H2 = hashlib.sha256(H1 + rec1).digest()

    assert bytes(h_sls_tail32) == H2

    # Also ensure the URC capsule def referenced by the cartridge exists on disk.
    def_rel = f"polymath/registry/eudrs_u/capsules/sha256_{capsule_def_id.split(':',1)[1]}.urc_capsule_def_v1.json"
    assert (root / def_rel).exists()
