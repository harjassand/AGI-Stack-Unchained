from __future__ import annotations

import hashlib
import struct

import pytest

from cdel.v18_0.eudrs_u.concept_shard_v1 import apply_shard_v1, parse_concept_shard_v1, unify_shard_region_v1
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
)
from cdel.v18_0.eudrs_u.ontology_v1 import OntologyV1
from cdel.v18_0.eudrs_u.qxwmr_canon_wl_v1 import canon_state_packed_v1
from cdel.v18_0.eudrs_u.qxwmr_state_v1 import QXWMRStatePackedV1, encode_state_packed_v1
from cdel.v18_0.eudrs_u.sls_vm_v1 import MLIndexCtxV1, run_strategy_v1, _retrieve_shard_topk_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error


def _encode_qxwmr(
    *,
    flags_u32: int,
    N_u32: int,
    E_u32: int,
    d_n_u32: int,
    d_e_u32: int,
    WL_R_u32: int,
    CANON_TIE_CAP_u32: int,
    node_tok_u32: list[int],
    src_u32: list[int],
    dst_u32: list[int],
    edge_tok_u32: list[int],
    node_attr_s64le: bytes = b"",
    edge_attr_s64le: bytes = b"",
    d_r_u32: int = 0,
    r_s64le: bytes = b"",
    kappa_bits_u16: int = 0,
    kappa_bitfield: bytes = b"",
    K_n_u32: int = 0,
    K_e_u32: int = 0,
    Lmax_u16: int = 0,
    node_level_u16: list[int] | None = None,
) -> bytes:
    st = QXWMRStatePackedV1(
        flags_u32=int(flags_u32),
        N_u32=int(N_u32),
        E_u32=int(E_u32),
        K_n_u32=int(K_n_u32),
        K_e_u32=int(K_e_u32),
        d_n_u32=int(d_n_u32),
        d_e_u32=int(d_e_u32),
        d_r_u32=int(d_r_u32),
        WL_R_u32=int(WL_R_u32),
        CANON_TIE_CAP_u32=int(CANON_TIE_CAP_u32),
        Lmax_u16=int(Lmax_u16),
        kappa_bits_u16=int(kappa_bits_u16),
        node_tok_u32=list(node_tok_u32),
        node_level_u16=None if node_level_u16 is None else list(node_level_u16),
        node_attr_s64le=bytes(node_attr_s64le),
        src_u32=list(src_u32),
        dst_u32=list(dst_u32),
        edge_tok_u32=list(edge_tok_u32),
        edge_attr_s64le=bytes(edge_attr_s64le),
        r_s64le=bytes(r_s64le),
        kappa_bitfield=bytes(kappa_bitfield),
    )
    return encode_state_packed_v1(st)


def _build_concept_shard_bytes(
    *,
    pattern_state_bytes: bytes,
    region_nodes_u32: list[int],
    anchor_nodes_u32: list[int],
    rewrite_ops: list[tuple[int, int, int, int, int, int]],
) -> bytes:
    # rewrite_ops entries: (op_kind, a, b, c, d, val_s64)
    hdr = struct.pack(
        "<4s6I4I",
        b"CSH1",
        1,
        0,  # flags
        len(pattern_state_bytes),
        len(region_nodes_u32),
        len(anchor_nodes_u32),
        len(rewrite_ops),
        0,
        0,
        0,
        0,
    )
    body = bytearray()
    body += bytes(pattern_state_bytes)
    body += b"".join(struct.pack("<I", int(v) & 0xFFFFFFFF) for v in region_nodes_u32)
    body += b"".join(struct.pack("<I", int(v) & 0xFFFFFFFF) for v in anchor_nodes_u32)
    for op_kind, a, b, c, d, val in rewrite_ops:
        # 36-byte layout: op_kind,a,b,c,d,res0,res1,val_s64
        body += struct.pack("<7Iq", int(op_kind), int(a), int(b), int(c), int(d), 0, 0, int(val))
    return bytes(hdr + bytes(body))


def _concept_def_obj(
    *, handle: str, deps: list[str], shard_bytes: bytes, shard_relpath: str, unify_caps: dict[str, int] | None = None
) -> tuple[dict, bytes, bytes]:
    shard_id = f"sha256:{hashlib.sha256(shard_bytes).hexdigest()}"
    caps = (
        {
            "region_node_cap_u32": 64,
            "backtrack_step_cap_u32": 1_000_000,
            "candidate_leaf_cap_u32": 1_000_000,
        }
        if unify_caps is None
        else dict(unify_caps)
    )
    obj = {
        "schema_id": "concept_def_v1",
        "concept_id": "sha256:" + ("0" * 64),  # placeholder for self-hash
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "handle": handle,
        "deps": list(deps),
        "shard_ref": {"artifact_id": shard_id, "artifact_relpath": shard_relpath},
        "unify_caps": caps,
    }
    tmp = dict(obj)
    tmp["concept_id"] = "sha256:" + ("0" * 64)
    concept_id = f"sha256:{hashlib.sha256(gcj1_canon_bytes(tmp)).hexdigest()}"
    obj["concept_id"] = concept_id
    canon = gcj1_canon_bytes(obj)
    concept_hash32 = hashlib.sha256(canon).digest()
    return obj, canon, concept_hash32


def _strategy_def_obj(*, budgets: dict[str, int]) -> dict:
    b = dict(budgets)
    b.setdefault("urc_cap_u32", 1)
    obj = {
        "schema_id": "strategy_def_v1",
        "strategy_id": "sha256:" + ("0" * 64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "handle": "strategy/test",
        "cartridge_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/strategies/sha256_00.strategy_cartridge_v1.bin"},
        "concept_deps": [],
        "budgets": dict(b),
    }
    tmp = dict(obj)
    tmp["strategy_id"] = "sha256:" + ("0" * 64)
    obj["strategy_id"] = f"sha256:{hashlib.sha256(gcj1_canon_bytes(tmp)).hexdigest()}"
    return obj


def _cartridge_bytes(*, consts: list[tuple[int, bytes]], instrs: list[tuple[int, int, int, int]]) -> bytes:
    # consts: list of (kind_u32, payload_bytes) where len is encoded
    # instrs: list of (opcode_u16, a_u32, b_u32, c_u32)
    out = bytearray()
    out += struct.pack("<4sIII4I", b"SLS1", 1, len(consts), len(instrs), 0, 0, 0, 0)
    for kind_u32, payload in consts:
        out += struct.pack("<II", int(kind_u32), len(payload))
        out += bytes(payload)
    for opcode_u16, a_u32, b_u32, c_u32 in instrs:
        out += struct.pack("<HHIII", int(opcode_u16), 0, int(a_u32), int(b_u32), int(c_u32))
    return bytes(out)


def _canonical_state_minimal() -> bytes:
    raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=1,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[7],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    return canon_state_packed_v1(raw, caps_ctx=None)


def test_unify_deterministic_selection_and_witness_hash_pinned() -> None:
    # Pattern: 2-node chain (0 -> 1).
    pat_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[5],
    )
    pat = canon_state_packed_v1(pat_raw, caps_ctx=None)

    shard_bytes = _build_concept_shard_bytes(
        pattern_state_bytes=pat,
        region_nodes_u32=[0, 1],
        anchor_nodes_u32=[],
        rewrite_ops=[],
    )

    # Target has two disjoint matching chains: (0->1) and (2->3).
    tgt_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=4,
        E_u32=2,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=4,
        node_tok_u32=[7, 7, 7, 7],
        src_u32=[0, 2],
        dst_u32=[1, 3],
        edge_tok_u32=[5, 5],
    )
    tgt = canon_state_packed_v1(tgt_raw, caps_ctx=None)

    concept_def, _concept_def_bytes, _concept_def_hash32 = _concept_def_obj(
        handle="concept/test_unify",
        deps=[],
        shard_bytes=shard_bytes,
        shard_relpath="polymath/registry/eudrs_u/ontology/concepts/sha256_00.concept_shard_v1.bin",
    )

    witness = unify_shard_region_v1(
        target_state_bytes=tgt,
        concept_def_obj=concept_def,
        shard_bytes=shard_bytes,
        caps_ctx=None,
    )
    assert witness[:4] == b"UWIT"
    # Pinned mapping (pattern nodes 0,1 -> target nodes 0,1) and pinned witness hash.
    mapping_count = struct.unpack_from("<I", witness, 4 + 4 + 32 + 32 + 32)[0]
    assert mapping_count == 2
    # mapping entries start at offset 112
    p0, t0 = struct.unpack_from("<II", witness, 112)
    p1, t1 = struct.unpack_from("<II", witness, 120)
    assert (p0, t0, p1, t1) == (0, 0, 1, 1)
    witness_hash32 = witness[-32:]
    assert witness_hash32.hex() == "57c19d43ad11fcc2f733978826de987cddc56b096897c3ec02d7b66ef42816ce"


def test_unify_pattern_mismatch_rejected() -> None:
    pat_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[5],
    )
    pat = canon_state_packed_v1(pat_raw, caps_ctx=None)
    shard_bytes = _build_concept_shard_bytes(pattern_state_bytes=pat, region_nodes_u32=[0, 1], anchor_nodes_u32=[], rewrite_ops=[])

    # Target differs by one edge type.
    tgt_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[6],  # mismatch
    )
    tgt = canon_state_packed_v1(tgt_raw, caps_ctx=None)

    concept_def, _concept_def_bytes, _concept_def_hash32 = _concept_def_obj(
        handle="concept/test_mismatch",
        deps=[],
        shard_bytes=shard_bytes,
        shard_relpath="polymath/registry/eudrs_u/ontology/concepts/sha256_00.concept_shard_v1.bin",
    )
    with pytest.raises(OmegaV18Error) as exc:
        unify_shard_region_v1(target_state_bytes=tgt, concept_def_obj=concept_def, shard_bytes=shard_bytes, caps_ctx=None)
    assert "EUDRSU_MCL_UNIFY_NO_MATCH" in str(exc.value)


def test_unify_cap_exceeded_rejected() -> None:
    # Pattern is a single node; target has many candidates; backtrack cap is tiny.
    pat_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=1,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[7],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    pat = canon_state_packed_v1(pat_raw, caps_ctx=None)
    shard_bytes = _build_concept_shard_bytes(pattern_state_bytes=pat, region_nodes_u32=[0], anchor_nodes_u32=[], rewrite_ops=[])

    tgt_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=5,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=5,
        node_tok_u32=[7] * 5,
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    tgt = canon_state_packed_v1(tgt_raw, caps_ctx=None)

    concept_def, _concept_def_bytes, _concept_def_hash32 = _concept_def_obj(
        handle="concept/test_cap",
        deps=[],
        shard_bytes=shard_bytes,
        shard_relpath="polymath/registry/eudrs_u/ontology/concepts/sha256_00.concept_shard_v1.bin",
        unify_caps={
            "region_node_cap_u32": 64,
            "backtrack_step_cap_u32": 1,
            "candidate_leaf_cap_u32": 1_000_000,
        },
    )
    with pytest.raises(OmegaV18Error) as exc:
        unify_shard_region_v1(target_state_bytes=tgt, concept_def_obj=concept_def, shard_bytes=shard_bytes, caps_ctx=None)
    assert "EUDRSU_MCL_UNIFY_CAP_EXCEEDED" in str(exc.value)


def test_apply_determinism_bytes_and_hash_pinned() -> None:
    # Initial target state has one NULL node + one NULL edge slot.
    raw0 = _encode_qxwmr(
        flags_u32=0,
        N_u32=3,
        E_u32=2,
        d_n_u32=1,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=3,
        node_tok_u32=[7, 7, 0],
        node_attr_s64le=b"\x00" * (3 * 1 * 8),
        src_u32=[0, 0],
        dst_u32=[1, 0],
        edge_tok_u32=[5, 0],
    )
    tgt0 = canon_state_packed_v1(raw0, caps_ctx=None)

    # Pattern matches nodes 0 and 1 with the same edge.
    pat_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=1,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        node_attr_s64le=b"\x00" * (2 * 1 * 8),
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[5],
    )
    pat = canon_state_packed_v1(pat_raw, caps_ctx=None)

    # Rewrite: set node0 attr0=123, add a new node (type=9), add edge new->node1 (type=6).
    # NodeRef encoding: local id 1 => (1<<31)|1.
    local1 = (1 << 31) | 1
    rewrite_ops = [
        (3, 0, 0, 0, 0, 123),  # SET_NODE_ATTR pattern node 0 key 0 val 123
        (1, local1, 9, 0, 0, 0),  # ADD_NODE local1 type 9 tag 0
        (5, local1, 1, 6, 0, 0),  # ADD_EDGE local1 -> pattern node 1 type 6
    ]
    shard_bytes = _build_concept_shard_bytes(pattern_state_bytes=pat, region_nodes_u32=[0, 1], anchor_nodes_u32=[], rewrite_ops=rewrite_ops)

    concept_def, _concept_def_bytes, _concept_def_hash32 = _concept_def_obj(
        handle="concept/test_apply",
        deps=[],
        shard_bytes=shard_bytes,
        shard_relpath="polymath/registry/eudrs_u/ontology/concepts/sha256_00.concept_shard_v1.bin",
    )

    witness = unify_shard_region_v1(target_state_bytes=tgt0, concept_def_obj=concept_def, shard_bytes=shard_bytes, caps_ctx=None)
    out = apply_shard_v1(target_state_bytes=tgt0, concept_def_obj=concept_def, shard_bytes=shard_bytes, witness_bytes=witness, caps_ctx=None)

    out_hash = hashlib.sha256(out).hexdigest()
    assert out_hash == "d5e35eb53f1f0e5c7d7f3f7ec4ba0171c6c2ba9dff3d7c0f4759ce64f0028af0"
    assert (
        out.hex()
        == "4d575851010000000000000003000000020000000000000000000000010000000000000000000000000000000300000000000000000000000700000009000000070000007b0000000000000000000000000000000000000000000000000000000100000002000000020000000500000006000000"
    )


def test_vm_instr_cap_exceeded() -> None:
    budgets = {
        "instr_cap_u64": 1,
        "cost_cap_u64": 1_000_000,
        "log_cap_u32": 1_000_000,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(budgets=budgets)
    cart = _cartridge_bytes(
        consts=[(1, struct.pack("<I", 0))],  # U32
        instrs=[
            (0x0002, 0, 0, 0),  # LOAD_CONST 0
            (0x0001, 0, 0, 0),  # HALT (would exceed instr cap)
        ],
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=_canonical_state_minimal(),
            caps_ctx=None,
            registry_load_bytes=lambda _ref: b"",
        )
    assert "EUDRSU_SLS_BUDGET_EXCEEDED" in str(exc.value)


def test_vm_log_cap_exceeded() -> None:
    budgets = {
        "instr_cap_u64": 1_000_000,
        "cost_cap_u64": 1_000_000,
        "log_cap_u32": 2,  # only 2 log records allowed
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(budgets=budgets)

    payload = b"abc"
    cart = _cartridge_bytes(
        consts=[(4, payload)],  # BYTES
        instrs=[
            (0x0002, 0, 0, 0),  # LOAD_CONST 0 (BYTES)
            (0x0016, 0, 0, 0),  # WRITE_LOG_DIGEST -> USER log #0
            (0x0003, 0, 0, 0),  # DROP (BYTES32)
            (0x0002, 0, 0, 0),  # LOAD_CONST 0 (BYTES)
            (0x0016, 0, 0, 0),  # WRITE_LOG_DIGEST -> USER log #1
            (0x0003, 0, 0, 0),  # DROP (BYTES32)
            (0x0001, 0, 0, 0),  # HALT would emit log #2 => exceed
        ],
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=_canonical_state_minimal(),
            caps_ctx=None,
            registry_load_bytes=lambda _ref: b"",
        )
    assert "EUDRSU_SLS_BUDGET_EXCEEDED" in str(exc.value)


def test_vm_unify_cap_exceeded() -> None:
    # Set up an in-memory concept_def + shard and run UNIFY twice with unify_cap=1.
    pat_raw = _encode_qxwmr(
        flags_u32=0,
        N_u32=1,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[7],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    pat = canon_state_packed_v1(pat_raw, caps_ctx=None)
    shard_bytes = _build_concept_shard_bytes(pattern_state_bytes=pat, region_nodes_u32=[0], anchor_nodes_u32=[], rewrite_ops=[])

    concept_def, concept_def_bytes, concept_def_hash32 = _concept_def_obj(
        handle="concept/test_vm_unify",
        deps=[],
        shard_bytes=shard_bytes,
        shard_relpath="polymath/registry/eudrs_u/ontology/concepts/sha256_aa.concept_shard_v1.bin",
    )
    concept_def_id = f"sha256:{hashlib.sha256(concept_def_bytes).hexdigest()}"
    concept_hex = concept_def_id.split(":", 1)[1]

    # Registry loader keyed by artifact_id.
    blob_by_id = {
        concept_def_id: concept_def_bytes,
        concept_def["shard_ref"]["artifact_id"]: shard_bytes,
    }

    def _registry_load(ref: dict[str, str]) -> bytes:
        return blob_by_id[str(ref["artifact_id"])]

    budgets = {
        "instr_cap_u64": 1_000_000,
        "cost_cap_u64": 1_000_000,
        "log_cap_u32": 1_000_000,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(budgets=budgets)

    cart = _cartridge_bytes(
        consts=[(6, concept_def_hash32)],  # BYTES32 concept_def_hash32
        instrs=[
            (0x0002, 0, 0, 0),  # LOAD_CONST
            (0x0004, 0, 0, 0),  # DUP
            (0x0011, 0, 0, 0),  # UNIFY
            (0x0003, 0, 0, 0),  # DROP witness_hash32
            (0x0003, 0, 0, 0),  # DROP witness bytes
            (0x0011, 0, 0, 0),  # UNIFY again => cap exceeded
        ],
    )

    with pytest.raises(OmegaV18Error) as exc:
        run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=_canonical_state_minimal(),
            caps_ctx=None,
            registry_load_bytes=_registry_load,
        )
    assert "EUDRSU_SLS_BUDGET_EXCEEDED" in str(exc.value)


def test_retrieve_opcode_determinism_topk_ties_and_trace_root_pinned() -> None:
    # Minimal ML-index with 2 buckets, bucket selection tie; bucket 0 should be chosen.
    q = 1 << 32  # 1.0 in Q32
    codebook = MLIndexCodebookV1(K_u32=2, d_u32=1, C_q32=[q, q])
    codebook_bytes = encode_ml_index_codebook_v1(codebook)

    root = MLIndexRootV1(K_u32=2, fanout_u32=2, bucket_root_hash32=[b"\x00" * 32, b"\x00" * 32])
    index_root_bytes = encode_ml_index_root_v1(root)

    # Page for bucket 0 with 2 records that tie on score; order by record_hash32 asc.
    rh0 = b"\x00" * 31 + b"\x01"
    rh1 = b"\x00" * 31 + b"\x02"
    ph0 = b"\x11" * 32
    ph1 = b"\x22" * 32
    page0 = MLIndexPageV1(
        bucket_id_u32=0,
        page_index_u32=0,
        key_dim_u32=1,
        records=[
            MLIndexPageRecordV1(record_hash32=rh0, payload_hash32=ph0, key_q32=[q]),
            MLIndexPageRecordV1(record_hash32=rh1, payload_hash32=ph1, key_q32=[q]),
        ],
    )
    page0_bytes = encode_ml_index_page_v1(page0)
    page0_id = f"sha256:{hashlib.sha256(page0_bytes).hexdigest()}"

    # Bucket 1 page exists but is irrelevant (not selected by V=1 tie-break).
    page1 = MLIndexPageV1(bucket_id_u32=1, page_index_u32=0, key_dim_u32=1, records=[])
    page1_bytes = encode_ml_index_page_v1(page1)
    page1_id = f"sha256:{hashlib.sha256(page1_bytes).hexdigest()}"

    manifest_obj = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "key_dim_u32": 1,
        "codebook_size_u32": 2,
        "bucket_visit_k_u32": 1,
        "scan_cap_per_bucket_u32": 10,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_EACH_DIM_V1",
        "codebook_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/idx/cbk.bin"},
        "index_root_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/idx/root.bin"},
        "bucket_listing_ref": {"artifact_id": "sha256:" + ("0" * 64), "artifact_relpath": "polymath/registry/eudrs_u/idx/listing.json"},
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": 1},
            "mem_g2_anchor_recall_min_q32": {"q": 1},
        },
    }

    listing_obj = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("0" * 64),
        "buckets": [
            {
                "bucket_id_u32": 0,
                "pages": [{"page_index_u32": 0, "page_ref": {"artifact_id": page0_id, "artifact_relpath": "polymath/registry/eudrs_u/idx/sha256_page0.page"}}],
            },
            {
                "bucket_id_u32": 1,
                "pages": [{"page_index_u32": 0, "page_ref": {"artifact_id": page1_id, "artifact_relpath": "polymath/registry/eudrs_u/idx/sha256_page1.page"}}],
            },
        ],
    }

    blob_by_id = {page0_id: page0_bytes, page1_id: page1_bytes}

    def _registry_load(ref: dict[str, str]) -> bytes:
        return blob_by_id[str(ref["artifact_id"])]

    ml_ctx = MLIndexCtxV1(index_manifest_obj=manifest_obj, codebook_bytes=codebook_bytes, index_root_bytes=index_root_bytes, bucket_listing_obj=listing_obj)
    query_key_bytes = struct.pack("<q", q)

    payload_hashes, trace_root32, scanned_total = _retrieve_shard_topk_v1(
        ml_index_ctx=ml_ctx,
        registry_load_bytes=_registry_load,
        query_key_bytes=query_key_bytes,
        top_k_u32=2,
    )
    assert payload_hashes == (ph0, ph1)
    assert scanned_total == 2
    assert trace_root32.hex() == "5a17ca77617556c64a936cc786a2d8bc63162391da7fbe2f0d7211b68d80ed24"
