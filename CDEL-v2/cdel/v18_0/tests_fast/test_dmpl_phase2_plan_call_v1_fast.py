from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_chunk_merkle_root_v1
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import artifact_id_from_json_obj, gcj1_canon_bytes, gcj1_loads_and_verify_canonical
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
)
from cdel.v18_0.eudrs_u.qxwmr_canon_wl_v1 import canon_state_packed_v1
from cdel.v18_0.eudrs_u.qxwmr_state_v1 import QXWMRStatePackedV1, pack_state_packed_v1
from cdel.v18_0.eudrs_u.sls_vm_v1 import MLIndexCtxV1, OntologyV1, run_strategy_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error, Q32_ONE, validate_schema


_SLS1_HDR = struct.Struct("<4sIII4I")
_INSTR = struct.Struct("<HHIII")

_SLS_LOG_MAGIC = b"SLD1"


def _sha256_id(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(bytes(raw)).hexdigest()}"


def _sha256_id_to_bytes32(sha256_id: str) -> bytes:
    if not isinstance(sha256_id, str) or not sha256_id.startswith("sha256:") or len(sha256_id) != (len("sha256:") + 64):
        raise AssertionError(f"bad sha256 id: {sha256_id!r}")
    return bytes.fromhex(sha256_id.split(":", 1)[1])


def _write_json_artifact(base_dir: Path, rel_dir: str, artifact_type: str, obj: dict) -> dict[str, str]:
    raw = gcj1_canon_bytes(obj)
    aid = _sha256_id(raw)
    hex64 = aid.split(":", 1)[1]
    path = (base_dir / rel_dir / f"sha256_{hex64}.{artifact_type}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"artifact_id": aid, "artifact_relpath": path.relative_to(base_dir).as_posix()}


def _write_bin_artifact(base_dir: Path, rel_dir: str, artifact_type: str, raw: bytes) -> dict[str, str]:
    b = bytes(raw)
    aid = _sha256_id(b)
    hex64 = aid.split(":", 1)[1]
    path = (base_dir / rel_dir / f"sha256_{hex64}.{artifact_type}.bin").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
    return {"artifact_id": aid, "artifact_relpath": path.relative_to(base_dir).as_posix()}


def _dmpl_tensor_bin(*, dims_u32: list[int], values_i64: list[int]) -> bytes:
    # Matches dmpl_tensor_io_v1.py: magic+version+ndim+dims+payload i64le.
    out = bytearray()
    out += b"DMPLTQ32"
    out += struct.pack("<II", 1, int(len(dims_u32)) & 0xFFFFFFFF)
    for d in dims_u32:
        out += struct.pack("<I", int(d) & 0xFFFFFFFF)
    for v in values_i64:
        out += struct.pack("<q", int(v))
    return bytes(out)


def _cartridge_bytes(*, instrs: list[tuple[int, int, int, int]]) -> bytes:
    # SLS1: header + no consts + fixed-width instructions.
    const_count = 0
    instr_count = len(instrs)
    out = bytearray()
    out += _SLS1_HDR.pack(b"SLS1", 1, int(const_count), int(instr_count), 0, 0, 0, 0)
    for opcode_u16, a_u32, b_u32, c_u32 in instrs:
        out += _INSTR.pack(int(opcode_u16) & 0xFFFF, 0, int(a_u32) & 0xFFFFFFFF, int(b_u32) & 0xFFFFFFFF, int(c_u32) & 0xFFFFFFFF)
    return bytes(out)


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
    if len(state_before_hash32) != 32 or len(state_after_hash32) != 32:
        raise AssertionError("bad state hash len")
    if len(retrieval_trace_root32) != 32 or len(witness_hash32) != 32 or len(aux_hash32) != 32:
        raise AssertionError("bad aux hash len")

    out = bytearray()
    out += _SLS_LOG_MAGIC
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
    if len(out) != 256:
        raise AssertionError(f"bad record len: {len(out)}")
    return bytes(out)


def _find_unique_by_suffix(root: Path, suffix: str) -> Path:
    hits = sorted([p for p in root.glob(f"*.{suffix}") if p.is_file()], key=lambda p: p.name)
    assert len(hits) == 1, f"expected exactly 1 *.{suffix}, got {len(hits)}"
    return hits[0]


@dataclass(frozen=True, slots=True)
class _DMPLTestEnv:
    base_dir: Path
    opset_id: str
    modelpack_id: str
    droot_ref: dict[str, str]
    plan_query_ref: dict[str, str]
    initial_state_bytes: bytes


def _build_env(*, tmp_path: Path, enabled_b: bool, max_trace_bytes_u32: int) -> _DMPLTestEnv:
    base_dir = (tmp_path / "registry").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Minimal canonical QXWMR state (N=0, E=0).
    raw_state = pack_state_packed_v1(
        QXWMRStatePackedV1(
            flags_u32=0,
            N_u32=0,
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
            node_tok_u32=[],
            node_level_u16=None,
            node_attr_s64le=memoryview(b""),
            src_u32=[],
            dst_u32=[],
            edge_tok_u32=[],
            edge_attr_s64le=memoryview(b""),
            r_s64le=memoryview(b""),
            kappa_bitfield=memoryview(b""),
        )
    )
    initial_state_bytes = canon_state_packed_v1(raw_state, caps_ctx=None)

    # DMPL dims.
    d_u32 = 2
    p_u32 = 4
    embed_dim_u32 = 2

    # Base tensors (all zeros).
    A0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32, d_u32], values_i64=[0] * (d_u32 * d_u32)))
    B0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32, p_u32], values_i64=[0] * (d_u32 * p_u32)))
    Wg_ref = _write_bin_artifact(
        base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[embed_dim_u32, d_u32], values_i64=[0] * (embed_dim_u32 * d_u32))
    )
    b0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32], values_i64=[0] * d_u32))
    w0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32], values_i64=[0] * d_u32))
    v0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[1], values_i64=[0]))

    # Concept shard + embedding (payload in ML-index points at this shard id).
    embed_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[embed_dim_u32], values_i64=[0] * embed_dim_u32))
    concept_obj = {
        "schema_id": "dmpl_concept_shard_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "concept_handle": "concept/test_concept",
        "concept_shard_kind": "dmpl_patch_v1",
        "embed_tensor_bin_id": embed_ref["artifact_id"],
        "patches_by_level": [
            {
                "ladder_level_u32": 0,
                "patch_kind": "none",
                "v_c0_q32": {"q": 0},
                "w_bin_id": "sha256:" + ("0" * 64),
            }
        ],
    }
    concept_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/concepts", "dmpl_concept_shard_v1", concept_obj)
    concept_id32 = _sha256_id_to_bytes32(concept_ref["artifact_id"])

    # Minimal ML-index artifacts (key_dim must satisfy DMPL retrieve wrapper: 8*key_dim == 32 => key_dim=4).
    key_dim_u32 = 4
    codebook = MLIndexCodebookV1(K_u32=1, d_u32=key_dim_u32, C_q32=[0] * key_dim_u32)
    codebook_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/indices", "ml_index_codebook_v1", encode_ml_index_codebook_v1(codebook))

    page = MLIndexPageV1(
        bucket_id_u32=0,
        page_index_u32=0,
        key_dim_u32=key_dim_u32,
        records=[MLIndexPageRecordV1(record_hash32=b"\x01" * 32, payload_hash32=concept_id32, key_q32=[0] * key_dim_u32)],
    )
    page_ref = _write_bin_artifact(
        base_dir,
        "polymath/registry/eudrs_u/indices/buckets/0/pages",
        "ml_index_page_v1",
        encode_ml_index_page_v1(page),
    )

    bucket_listing_obj = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("11" * 32),
        "buckets": [{"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": page_ref}]}],
    }
    bucket_listing_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/indices", "ml_index_bucket_listing_v1", bucket_listing_obj)

    from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1

    leaf0 = _sha256_id_to_bytes32(page_ref["artifact_id"])
    root0 = merkle_fanout_v1(leaf_hash32=[leaf0], fanout_u32=2)
    index_root = MLIndexRootV1(K_u32=1, fanout_u32=2, bucket_root_hash32=[root0])
    index_root_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/indices", "ml_index_root_v1", encode_ml_index_root_v1(index_root))

    ml_index_manifest_obj = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": opset_id,
        "key_dim_u32": key_dim_u32,
        "codebook_size_u32": 1,
        "bucket_visit_k_u32": 1,
        "scan_cap_per_bucket_u32": 10,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_END_V1",
        "codebook_ref": codebook_ref,
        "index_root_ref": index_root_ref,
        "bucket_listing_ref": bucket_listing_ref,
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": int(Q32_ONE)},
            "mem_g2_anchor_recall_min_q32": {"q": 0},
        },
    }
    ml_index_manifest_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/indices", "ml_index_manifest_v1", ml_index_manifest_obj)

    # DMPL modelpack/config/droot/bundles.
    modelpack_obj = {
        "schema_id": "dmpl_modelpack_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "dims": {"d_u32": d_u32, "p_u32": p_u32, "embed_dim_u32": embed_dim_u32},
        "forward_arch_id": "dmpl_linear_pwl_v1",
        "value_arch_id": "dmpl_linear_v1",
        "activation_id": "hard_tanh_q32_v1",
        "gating_arch_id": "linear_gate_v1",
        "inverse_head_supported_b": False,
        "tensor_specs": [{"name": "A0", "shape_u32": [d_u32, d_u32], "role": "forward"}],
        "patch_policy": {"allowed_patch_types": ["matrix_patch", "lowrank_patch"], "vm_patch_allowed_b": False},
    }
    modelpack_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/modelpacks", "dmpl_modelpack_v1", modelpack_obj)
    modelpack_id = modelpack_ref["artifact_id"]

    forward_bundle_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "bundle_kind": "F",
        "modelpack_id": modelpack_id,
        "tensors": [
            {"name": "A0", "shape_u32": [d_u32, d_u32], "tensor_bin_id": A0_ref["artifact_id"]},
            {"name": "B0", "shape_u32": [d_u32, p_u32], "tensor_bin_id": B0_ref["artifact_id"]},
            {"name": "Wg", "shape_u32": [embed_dim_u32, d_u32], "tensor_bin_id": Wg_ref["artifact_id"]},
            {"name": "b0", "shape_u32": [d_u32], "tensor_bin_id": b0_ref["artifact_id"]},
        ],
        "merkle_root": "sha256:" + ("0" * 64),
    }
    from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_params_bundle_merkle_root_v1

    forward_bundle_obj["merkle_root"] = compute_params_bundle_merkle_root_v1(bundle_obj=forward_bundle_obj, resolver=None)
    fparams_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/params", "dmpl_params_bundle_v1", forward_bundle_obj)

    value_bundle_obj = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "bundle_kind": "V",
        "modelpack_id": modelpack_id,
        "tensors": [
            {"name": "v0", "shape_u32": [1], "tensor_bin_id": v0_ref["artifact_id"]},
            {"name": "w0", "shape_u32": [d_u32], "tensor_bin_id": w0_ref["artifact_id"]},
        ],
        "merkle_root": "sha256:" + ("0" * 64),
    }
    value_bundle_obj["merkle_root"] = compute_params_bundle_merkle_root_v1(bundle_obj=value_bundle_obj, resolver=None)
    vparams_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/params", "dmpl_params_bundle_v1", value_bundle_obj)

    caps_obj = {
        "K_ctx_u32": 2,
        "K_g_u32": 1,
        "max_concept_bytes_per_step_u32": 0,
        "max_retrieval_bytes_u32": 0,
        "max_retrieval_ops_u64": 0,
        "max_patch_rank_u32": 0,
        "max_patch_bytes_u32": 0,
        "max_patch_vm_steps_u32": 0,
        "H_u32": 1,
        "Nmax_u32": 10,
        "Ka_u32": 2,
        "beam_width_u32": 0,
        "max_trace_bytes_u32": int(max_trace_bytes_u32) & 0xFFFFFFFF,
        "max_node_opcount_u64": 10_000_000,
        "max_total_opcount_u64": 100_000_000,
        "train_steps_u32": 0,
        "batch_size_u32": 0,
        "max_grad_norm_q32": {"q": 0},
        "lr_q32": {"q": 0},
        "dataset_max_bytes_u64": 0,
        "max_stack_depth_u32": 0,
        "max_recursion_depth_u32": 0,
    }
    caps_digest = artifact_id_from_json_obj(caps_obj)

    config_obj = {
        "schema_id": "dmpl_config_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "enabled_b": bool(enabled_b),
        "active_modelpack_id": modelpack_id,
        "fparams_bundle_id": fparams_ref["artifact_id"],
        "vparams_bundle_id": vparams_ref["artifact_id"],
        "caps": caps_obj,
        "retrieval_spec": {
            "ml_index_manifest_id": ml_index_manifest_ref["artifact_id"],
            "key_fn_id": "dmpl_key_v1",
            "score_fn_id": "ml_index_v1_default",
            "tie_rule_id": "score_desc_id_asc",
            "scan_cap_per_bucket_u32": 10,
            "K_ctx_u32": int(caps_obj["K_ctx_u32"]),
        },
        "gating_spec": {
            "normalize_weights_b": True,
            "epsilon_q32": {"q": int(Q32_ONE)},
            "pwl_pos_id": "pwl_pos_v1",
            "inv_q32_id": "div_q32_pos_rne_v1",
            "inverse_head_enabled_b": False,
            "rev_err_threshold_q32": {"q": 0},
            "theta_cac_lb_q32": {"q": 0},
            "stab_thresholds": {"G0": {"q": 0}, "G1": {"q": 0}, "G2": {"q": 0}, "G3": {"q": 0}, "G4": {"q": 0}, "G5": {"q": 0}},
        },
        "planner_spec": {
            "algorithm_id": "dcbts_l_v1",
            "ladder_policy": {
                "ell_hi_u32": 0,
                "ell_lo_u32": 0,
                "refine_enabled_b": False,
                "refine_budget_u32": 0,
                "refine_per_step_budget_u32": 0,
            },
            "action_source_id": "dmpl_action_enum_v1",
            "ordering_policy": {"primary_key_id": "upper_bound_primary_score_desc", "secondary_key_id": "depth_asc", "tertiary_key_id": "node_id_asc"},
            "aux_tie_break_policy": {"dl_proxy_enabled_b": False, "dl_proxy_id": "", "aux_allowed_only_on_exact_score_ties_b": True},
        },
        "hash_layout_ids": {
            "step_digest_layout_id": "dmpl_step_digest_v1",
            "trace_chain_layout_id": "dmpl_trace_chain_v1",
            "record_encoding_id": "lenpref_canonjson_v1",
            "chunking_rule_id": "fixed_1MiB_v1",
        },
        "objective_spec": {"gamma_q32": {"q": int(Q32_ONE)}, "reward_proxy_id": "ufc_proxy_v1", "ufc_objective_id": "ufc_v1_primary"},
    }
    config_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/configs", "dmpl_config_v1", config_obj)

    droot_obj = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "dmpl_config_id": config_ref["artifact_id"],
        "froot": str(forward_bundle_obj["merkle_root"]),
        "vroot": str(value_bundle_obj["merkle_root"]),
        "caps_digest": str(caps_digest),
        "opset_semantics_id": opset_id,
    }
    droot_ref = _write_json_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/roots", "dmpl_droot_v1", droot_obj)

    # z0 tensor bin (shape [d]).
    z0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32], values_i64=[0] * d_u32))

    plan_query_obj = {
        "schema_id": "dmpl_plan_query_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "dmpl_droot_id": droot_ref["artifact_id"],
        "start_state_id": "sha256:" + ("22" * 32),
        "z0_tensor_bin_id": z0_ref["artifact_id"],
        "call_context": {"vm_step_u64": 0, "scenario_id": ""},
    }
    plan_query_ref = _write_json_artifact(base_dir, "inputs", "dmpl_plan_query_v1", plan_query_obj)

    return _DMPLTestEnv(
        base_dir=base_dir,
        opset_id=opset_id,
        modelpack_id=modelpack_id,
        droot_ref=droot_ref,
        plan_query_ref=plan_query_ref,
        initial_state_bytes=bytes(initial_state_bytes),
    )


def _strategy_def_obj(*, opset_id: str, cartridge_ref: dict[str, str], budgets: dict[str, int]) -> dict:
    obj = {
        "schema_id": "strategy_def_v1",
        "strategy_id": "sha256:" + ("0" * 64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": str(opset_id),
        "handle": "strategy/dmpl_phase2_test",
        "cartridge_ref": dict(cartridge_ref),
        "concept_deps": [],
        "budgets": dict(budgets),
    }
    computed = _sha256_id(gcj1_canon_bytes(obj))
    obj2 = dict(obj)
    obj2["strategy_id"] = computed
    return obj2


def test_dmpl_plan_call_repeatable_and_vm_log_binds_hashes(tmp_path: Path) -> None:
    env1 = _build_env(tmp_path=tmp_path / "run1", enabled_b=True, max_trace_bytes_u32=10_000_000)
    env2 = _build_env(tmp_path=tmp_path / "run2", enabled_b=True, max_trace_bytes_u32=10_000_000)

    # Use the same registry tree bytes for both runs; only mroot differs.
    # (We reuse env1 registry as the canonical base.)
    base_dir = env1.base_dir

    mroot1 = (tmp_path / "mroot1").resolve()
    mroot2 = (tmp_path / "mroot2").resolve()
    oroot1 = (tmp_path / "oroot1").resolve()
    oroot2 = (tmp_path / "oroot2").resolve()

    cart = _cartridge_bytes(instrs=[(0x0015, 0, 0, 0), (0x0001, 0, 0, 0)])  # PLAN_CALL slot 0, then HALT
    cart_ref = _write_bin_artifact(base_dir, "inputs", "strategy_cartridge_v1", cart)
    budgets = {
        "instr_cap_u64": 100,
        "cost_cap_u64": 10_000,
        "log_cap_u32": 100,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(opset_id=env1.opset_id, cartridge_ref=cart_ref, budgets=budgets)

    def _run_once(mroot_dir: Path, oroot_dir: Path) -> tuple[bytes, int]:
        out_state, h_sls, log_count = run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=env1.initial_state_bytes,
            caps_ctx=None,
            registry_load_bytes=lambda _ref: b"",
            artifact_slots={0: dict(env1.plan_query_ref)},
            root_tuple_obj={"droot": dict(env1.droot_ref)},
            dmpl_registry_base_dir=base_dir,
            dmpl_mroot_dir=mroot_dir,
            dmpl_oroot_dir=oroot_dir,
        )
        assert out_state == env1.initial_state_bytes  # PLAN_CALL doesn't mutate state.
        return bytes(h_sls), int(log_count)

    h1, n1 = _run_once(mroot1, oroot1)
    h2, n2 = _run_once(mroot2, oroot2)
    assert n1 == 2 and n2 == 2
    assert h1 == h2

    # Outputs must be content-addressed and identical across runs.
    trace1 = _find_unique_by_suffix(mroot1, "dmpl_rollout_trace_v1.json")
    trace2 = _find_unique_by_suffix(mroot2, "dmpl_rollout_trace_v1.json")
    receipt1 = _find_unique_by_suffix(mroot1, "dmpl_action_receipt_v1.json")
    receipt2 = _find_unique_by_suffix(mroot2, "dmpl_action_receipt_v1.json")
    step1 = _find_unique_by_suffix(oroot1, "dmpl_step_digest_v1.json")
    step2 = _find_unique_by_suffix(oroot2, "dmpl_step_digest_v1.json")

    assert trace1.name == trace2.name
    assert receipt1.name == receipt2.name
    assert step1.name == step2.name

    trace_obj = gcj1_loads_and_verify_canonical(trace1.read_bytes())
    assert isinstance(trace_obj, dict)
    validate_schema(trace_obj, "dmpl_rollout_trace_v1")

    receipt_obj = gcj1_loads_and_verify_canonical(receipt1.read_bytes())
    assert isinstance(receipt_obj, dict)
    validate_schema(receipt_obj, "dmpl_action_receipt_v1")

    chosen_action_hash_id = str(receipt_obj["chosen_action_hash"])
    chosen_action_hash32 = _sha256_id_to_bytes32(chosen_action_hash_id)
    receipt_id32 = bytes.fromhex(receipt1.name.split(".", 2)[0].split("_", 1)[1])
    receipt_id = f"sha256:{receipt_id32.hex()}"

    # oroot binding: step digest must point at the ActionReceipt id.
    step_obj = gcj1_loads_and_verify_canonical(step1.read_bytes())
    assert isinstance(step_obj, dict)
    assert str(step_obj.get("dmpl_action_receipt_id", "")) == receipt_id

    # Verify SLS log binding: aux_hash32=chosen_action_hash32, witness_hash32=receipt_id32.
    state_h32 = hashlib.sha256(env1.initial_state_bytes).digest()
    rec0 = _emit_log_record_v1(
        event_kind_u32=6,
        step_index_u64=0,
        pc_u32=0,
        state_before_hash32=state_h32,
        state_after_hash32=state_h32,
        retrieval_trace_root32=b"\x00" * 32,
        witness_hash32=receipt_id32,
        aux_hash32=chosen_action_hash32,
        instr_used_u64=1,
        cost_used_u64=25,
    )
    rec1 = _emit_log_record_v1(
        event_kind_u32=9,
        step_index_u64=1,
        pc_u32=1,
        state_before_hash32=state_h32,
        state_after_hash32=state_h32,
        retrieval_trace_root32=b"\x00" * 32,
        witness_hash32=b"\x00" * 32,
        aux_hash32=b"\x00" * 32,
        instr_used_u64=2,
        cost_used_u64=25,
    )
    H0 = b"\x00" * 32
    H1 = hashlib.sha256(H0 + rec0).digest()
    H2 = hashlib.sha256(H1 + rec1).digest()
    assert bytes(H2) == bytes(h1)


def test_dmpl_trace_integrity_recompute_chain_and_merkle(tmp_path: Path) -> None:
    env = _build_env(tmp_path=tmp_path, enabled_b=True, max_trace_bytes_u32=10_000_000)

    mroot = (tmp_path / "mroot").resolve()
    oroot = (tmp_path / "oroot").resolve()
    cart = _cartridge_bytes(instrs=[(0x0015, 0, 0, 0), (0x0001, 0, 0, 0)])
    cart_ref = _write_bin_artifact(env.base_dir, "inputs", "strategy_cartridge_v1", cart)
    budgets = {
        "instr_cap_u64": 100,
        "cost_cap_u64": 10_000,
        "log_cap_u32": 100,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(opset_id=env.opset_id, cartridge_ref=cart_ref, budgets=budgets)

    _out_state, _h_sls, _log_count = run_strategy_v1(
        strategy_def_obj=strat,
        cartridge_bytes=cart,
        ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
        ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
        initial_state_bytes=env.initial_state_bytes,
        caps_ctx=None,
        registry_load_bytes=lambda _ref: b"",
        artifact_slots={0: dict(env.plan_query_ref)},
        root_tuple_obj={"droot": dict(env.droot_ref)},
        dmpl_registry_base_dir=env.base_dir,
        dmpl_mroot_dir=mroot,
        dmpl_oroot_dir=oroot,
    )

    trace_path = _find_unique_by_suffix(mroot, "dmpl_rollout_trace_v1.json")
    trace_obj = gcj1_loads_and_verify_canonical(trace_path.read_bytes())
    assert isinstance(trace_obj, dict)
    validate_schema(trace_obj, "dmpl_rollout_trace_v1")

    assert int(trace_obj["record_count_u64"]) > 0
    assert int(trace_obj["chunk_size_bytes_u32"]) == 1048576

    plan_query_id = str(trace_obj["plan_query_id"])
    plan_query_hash32 = _sha256_id_to_bytes32(plan_query_id)
    modelpack_hash32 = _sha256_id_to_bytes32(env.modelpack_id)
    opset_id = str(trace_obj["opset_id"])

    # Recompute chain.
    h_i = hashlib.sha256(b"DMPL/TRACE/v1\x00" + plan_query_hash32 + modelpack_hash32 + opset_id.encode("utf-8", errors="strict")).digest()
    record_count = 0

    chunks = trace_obj["chunks"]
    assert isinstance(chunks, list) and chunks
    chunk_hashes32: list[bytes] = []
    for entry in chunks:
        assert isinstance(entry, dict)
        idx = int(entry["chunk_index_u32"])
        chunk_bin_id = str(entry["chunk_bin_id"])
        chunk_bytes_u32 = int(entry["chunk_bytes_u32"])

        # Load chunk bytes from mroot.
        chunk_hex = chunk_bin_id.split(":", 1)[1]
        chunk_path = (mroot / f"sha256_{chunk_hex}.dmpl_rollout_trace_chunk_v1.bin").resolve()
        chunk_bytes = chunk_path.read_bytes()
        assert len(chunk_bytes) == chunk_bytes_u32

        # Hash check: sha256(chunk_bytes) == chunk_bin_id.
        actual_chunk_id = _sha256_id(chunk_bytes)
        assert actual_chunk_id == chunk_bin_id
        chunk_hashes32.append(_sha256_id_to_bytes32(chunk_bin_id))

        # Decode records.
        off = 0
        while off < len(chunk_bytes):
            if off + 4 > len(chunk_bytes):
                raise AssertionError("lenpref truncated")
            (n,) = struct.unpack_from("<I", chunk_bytes, off)
            off += 4
            if off + n > len(chunk_bytes):
                raise AssertionError("record bytes truncated")
            rec_bytes = bytes(chunk_bytes[off : off + n])
            off += n

            rec_obj = gcj1_loads_and_verify_canonical(rec_bytes)
            assert isinstance(rec_obj, dict)
            ri_hash32 = hashlib.sha256(rec_bytes).digest()
            h_i = hashlib.sha256(bytes(h_i) + bytes(ri_hash32)).digest()
            record_count += 1

        assert off == len(chunk_bytes)
        assert idx == chunks.index(entry)  # chunk list must be in index order for this test.

    assert int(trace_obj["record_count_u64"]) == int(record_count)
    assert str(trace_obj["trace_chain_final"]) == f"sha256:{h_i.hex()}"

    # Recompute chunk merkle root and compare.
    chunks_root32 = compute_chunk_merkle_root_v1(chunk_hashes32)
    assert str(trace_obj["chunks_merkle_root"]) == f"sha256:{chunks_root32.hex()}"


def test_dmpl_caps_enforcement_emits_action_receipt(tmp_path: Path) -> None:
    env = _build_env(tmp_path=tmp_path, enabled_b=True, max_trace_bytes_u32=1)  # forces DMPL_E_BUDGET_EXCEEDED

    mroot = (tmp_path / "mroot").resolve()
    oroot = (tmp_path / "oroot").resolve()
    cart = _cartridge_bytes(instrs=[(0x0015, 0, 0, 0), (0x0001, 0, 0, 0)])
    cart_ref = _write_bin_artifact(env.base_dir, "inputs", "strategy_cartridge_v1", cart)
    budgets = {
        "instr_cap_u64": 100,
        "cost_cap_u64": 10_000,
        "log_cap_u32": 100,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(opset_id=env.opset_id, cartridge_ref=cart_ref, budgets=budgets)

    with pytest.raises(OmegaV18Error) as exc:
        run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=env.initial_state_bytes,
            caps_ctx=None,
            registry_load_bytes=lambda _ref: b"",
            artifact_slots={0: dict(env.plan_query_ref)},
            root_tuple_obj={"droot": dict(env.droot_ref)},
            dmpl_registry_base_dir=env.base_dir,
            dmpl_mroot_dir=mroot,
            dmpl_oroot_dir=oroot,
        )
    assert "DMPL_E_BUDGET_EXCEEDED" in str(exc.value)

    receipt_path = _find_unique_by_suffix(mroot, "dmpl_action_receipt_v1.json")
    receipt_obj = gcj1_loads_and_verify_canonical(receipt_path.read_bytes())
    assert isinstance(receipt_obj, dict)
    validate_schema(receipt_obj, "dmpl_action_receipt_v1")

    gating = receipt_obj["gating_summary"]
    assert isinstance(gating, dict)
    status = gating["status"]
    assert isinstance(status, dict)
    assert bool(status["ok_b"]) is False
    assert str(status["reason_code"]) == "DMPL_E_BUDGET_EXCEEDED"

    step_path = _find_unique_by_suffix(oroot, "dmpl_step_digest_v1.json")
    step_obj = gcj1_loads_and_verify_canonical(step_path.read_bytes())
    assert isinstance(step_obj, dict)
    receipt_id = _sha256_id(receipt_path.read_bytes())
    assert str(step_obj.get("dmpl_action_receipt_id", "")) == receipt_id


def test_dmpl_disabled_fails_without_writing_artifacts(tmp_path: Path) -> None:
    env = _build_env(tmp_path=tmp_path, enabled_b=False, max_trace_bytes_u32=10_000_000)

    mroot = (tmp_path / "mroot").resolve()
    oroot = (tmp_path / "oroot").resolve()
    cart = _cartridge_bytes(instrs=[(0x0015, 0, 0, 0), (0x0001, 0, 0, 0)])
    cart_ref = _write_bin_artifact(env.base_dir, "inputs", "strategy_cartridge_v1", cart)
    budgets = {
        "instr_cap_u64": 100,
        "cost_cap_u64": 10_000,
        "log_cap_u32": 100,
        "retrieve_cap_u32": 1,
        "unify_cap_u32": 1,
        "apply_cap_u32": 1,
        "lift_cap_u32": 1,
        "project_cap_u32": 1,
        "plan_cap_u32": 1,
        "urc_cap_u32": 1,
        "max_state_bytes_u32": 1_000_000,
    }
    strat = _strategy_def_obj(opset_id=env.opset_id, cartridge_ref=cart_ref, budgets=budgets)

    with pytest.raises(OmegaV18Error) as exc:
        run_strategy_v1(
            strategy_def_obj=strat,
            cartridge_bytes=cart,
            ontology=OntologyV1(handle_map_obj={}, concept_defs_by_handle={}, topo_order_handles=[]),
            ml_index_ctx=MLIndexCtxV1(index_manifest_obj={}, codebook_bytes=b"", index_root_bytes=b"", bucket_listing_obj={}),
            initial_state_bytes=env.initial_state_bytes,
            caps_ctx=None,
            registry_load_bytes=lambda _ref: b"",
            artifact_slots={0: dict(env.plan_query_ref)},
            root_tuple_obj={"droot": dict(env.droot_ref)},
            dmpl_registry_base_dir=env.base_dir,
            dmpl_mroot_dir=mroot,
            dmpl_oroot_dir=oroot,
        )
    assert "DMPL_E_DISABLED" in str(exc.value)
    assert list(mroot.glob("*")) == []
    assert list(oroot.glob("*")) == []
