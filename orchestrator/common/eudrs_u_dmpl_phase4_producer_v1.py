"""Shared DMPL Phase-4 producer helpers for EUDRS-U (RE3, untrusted).

This module builds a self-contained promotion bundle that passes the RE2
promotion verifier (`cdel.v18_0.eudrs_u.verify_eudrs_u_promotion_v1`) with
DMPL Phase-4 evidence enabled:
  - training evidence (dataset + TrainRun/Trace/Receipt)
  - plan evidence (baseline + candidate PlanQuery/Trace/ActionReceipt)
  - CAC/UFC/STAB/LA-SUM DMPL certificates

Hard constraints:
  - GCJ-1 canonical JSON on disk (floats rejected by encoder).
  - Content-addressed artifacts everywhere (`sha256:<hex>` ids).
  - Q32 (int64) only for quantized fields.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cdel.v18_0.eudrs_u.dmpl_action_encode_v1 import make_noop_action_v1
from cdel.v18_0.eudrs_u.dmpl_config_load_v1 import load_runtime_from_droot_v1
from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_chunk_merkle_root_v1, compute_params_bundle_merkle_root_v1
from cdel.v18_0.eudrs_u.dmpl_planner_dcbts_l_v1 import plan_call_v1
from cdel.v18_0.eudrs_u.dmpl_train_sgd_v1 import (
    ConceptPatchEntryV1,
    TrainableStateV1,
    encode_tensor_q32_v1,
    sha256_prefixed_bytes,
    train_step_sgd_det_v1,
)
from cdel.v18_0.eudrs_u.dmpl_train_trace_v1 import TrainTraceWriterV1, encode_record_lenpref_canonjson_v1
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
from cdel.v18_0.eudrs_u.eudrs_u_q32ops_v1 import add_sat, mul_q32
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
)
from cdel.v18_0.eudrs_u.verify_dmpl_certificates_v1 import (
    _compute_holdout_mean_L1_pred_q32,
    _recompute_ufc_for_scenario,
    _reconstruct_chosen_path_from_trace,
)
from cdel.v18_0.omega_common_v1 import Q32_ONE, fail, require_no_absolute_paths, validate_schema


_U32LE = struct.Struct("<I")

_CHUNK_SIZE_BYTES_V1 = 1048576

_DATASET_CHAIN_PREFIX = b"DMPL/DATASET/v1\x00"


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id(data: bytes) -> str:
    return f"sha256:{_sha25632(data).hex()}"


def _write_canon_json(*, root: Path, relpath: str, obj: dict[str, Any]) -> None:
    require_no_absolute_paths(obj)
    raw = gcj1_canon_bytes(obj)
    path = (Path(root).resolve() / relpath).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _write_hashed_json(*, root: Path, rel_dir: str, artifact_type: str, obj: dict[str, Any]) -> dict[str, str]:
    require_no_absolute_paths(obj)
    raw = gcj1_canon_bytes(obj)
    aid = sha256_prefixed(raw)
    hex64 = aid.split(":", 1)[1]
    relpath = f"{str(rel_dir).rstrip('/')}/sha256_{hex64}.{str(artifact_type)}.json"
    path = (Path(root).resolve() / relpath).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        fail("NONDETERMINISTIC")
    path.write_bytes(raw)
    return {"artifact_id": aid, "artifact_relpath": relpath}


def _write_hashed_bin(*, root: Path, rel_dir: str, artifact_type: str, data: bytes) -> dict[str, str]:
    b = bytes(data)
    aid = sha256_prefixed(b)
    hex64 = aid.split(":", 1)[1]
    relpath = f"{str(rel_dir).rstrip('/')}/sha256_{hex64}.{str(artifact_type)}.bin"
    path = (Path(root).resolve() / relpath).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != b:
        fail("NONDETERMINISTIC")
    path.write_bytes(b)
    return {"artifact_id": aid, "artifact_relpath": relpath}


def _stage_rel_to_state_rel(relpath_under_stage: str) -> str:
    return f"eudrs_u/staged_registry_tree/{str(relpath_under_stage).lstrip('/')}"


def _read_prev_epoch_u64(repo_root: Path) -> int | None:
    pointer = Path(repo_root).resolve() / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    if not pointer.exists():
        return None
    if not pointer.is_file():
        fail("SCHEMA_FAIL")
    payload = gcj1_loads_and_verify_canonical(pointer.read_bytes())
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(payload)
    if str(payload.get("schema_id", "")).strip() != "active_root_tuple_ref_v1":
        fail("SCHEMA_FAIL")
    active = payload.get("active_root_tuple")
    if not isinstance(active, dict):
        fail("SCHEMA_FAIL")
    artifact_relpath = str(active.get("artifact_relpath", "")).strip()
    if not artifact_relpath:
        fail("SCHEMA_FAIL")
    root_tuple_path = (Path(repo_root).resolve() / artifact_relpath).resolve()
    if not root_tuple_path.exists() or not root_tuple_path.is_file():
        fail("MISSING_STATE_INPUT")
    root_tuple_obj = gcj1_loads_and_verify_canonical(root_tuple_path.read_bytes())
    if not isinstance(root_tuple_obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(root_tuple_obj)
    if str(root_tuple_obj.get("schema_id", "")).strip() != "eudrs_u_root_tuple_v1":
        fail("SCHEMA_FAIL")
    epoch = root_tuple_obj.get("epoch_u64")
    if not isinstance(epoch, int) or epoch < 0:
        fail("SCHEMA_FAIL")
    return int(epoch)


@dataclass(slots=True)
class _StageWriter:
    stage_root: Path  # .../eudrs_u/staged_registry_tree
    registry_prefix: str = "polymath/registry/eudrs_u"

    _refs: dict[tuple[str, str, str], dict[str, str]] = None  # (type,id,ext)->ArtifactRef

    def __post_init__(self) -> None:
        self.stage_root = Path(self.stage_root).resolve()
        self._refs = {}

    def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
        if not isinstance(obj, dict):
            fail("SCHEMA_FAIL")
        rel_dir = self._default_rel_dir_for_type(str(artifact_type), ext="json")
        ref = _write_hashed_json(root=self.stage_root, rel_dir=rel_dir, artifact_type=str(artifact_type), obj=dict(obj))
        self._refs[(str(artifact_type), str(ref["artifact_id"]), "json")] = dict(ref)
        return str(ref["artifact_id"])

    def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
        rel_dir = self._default_rel_dir_for_type(str(artifact_type), ext="bin")
        ref = _write_hashed_bin(root=self.stage_root, rel_dir=rel_dir, artifact_type=str(artifact_type), data=bytes(raw))
        self._refs[(str(artifact_type), str(ref["artifact_id"]), "bin")] = dict(ref)
        return str(ref["artifact_id"])

    def get_ref_under_stage(self, *, artifact_type: str, artifact_id: str, ext: str) -> dict[str, str]:
        key = (str(artifact_type), str(artifact_id), str(ext))
        ref = self._refs.get(key)
        if ref is None:
            fail("MISSING_STATE_INPUT")
        return dict(ref)

    def _default_rel_dir_for_type(self, artifact_type: str, *, ext: str) -> str:
        # Keep DMPL artifacts in stable subtrees (matches Phase-4 directory layout guidance).
        at = str(artifact_type).strip()
        if at in {
            "dmpl_plan_query_v1",
            "dmpl_rollout_trace_v1",
            "dmpl_action_receipt_v1",
            "dmpl_action_v1",
        }:
            return f"{self.registry_prefix}/memory/dmpl/rollout"
        if at in {
            "dmpl_train_run_v1",
            "dmpl_train_trace_v1",
            "dmpl_train_receipt_v1",
        }:
            return f"{self.registry_prefix}/memory/dmpl/train"
        if at in {"dmpl_rollout_trace_chunk_v1"}:
            return f"{self.registry_prefix}/memory/dmpl/rollout"
        if at in {"dmpl_train_trace_chunk_v1"}:
            return f"{self.registry_prefix}/memory/dmpl/train"
        if at in {"dmpl_dataset_pack_v1"}:
            return f"{self.registry_prefix}/dmpl/datasets"
        if at in {"dmpl_dataset_chunk_v1"}:
            return f"{self.registry_prefix}/dmpl/datasets"
        if at in {"dmpl_tensor_q32_v1"}:
            return f"{self.registry_prefix}/dmpl/tensors"
        if at in {"dmpl_params_bundle_v1"}:
            return f"{self.registry_prefix}/dmpl/params"
        if at in {"dmpl_config_v1"}:
            return f"{self.registry_prefix}/dmpl/config"
        if at in {"dmpl_modelpack_v1"}:
            return f"{self.registry_prefix}/dmpl/modelpacks"
        if at in {"dmpl_droot_v1"}:
            return f"{self.registry_prefix}/dmpl/roots"
        if at in {"dmpl_concept_shard_v1"}:
            return f"{self.registry_prefix}/dmpl/concepts"
        if at in {"dmpl_cac_pack_v1", "dmpl_ufc_flow_v1", "dmpl_stab_report_v1", "dmpl_lasum_report_v1"}:
            return f"{self.registry_prefix}/certs/dmpl"
        if at.startswith("ml_index_"):
            # ML-index lives under indices/.
            if at == "ml_index_page_v1":
                return f"{self.registry_prefix}/indices/buckets/0/pages"
            return f"{self.registry_prefix}/indices"
        # Fallback for producer-only artifacts.
        if ext == "bin":
            return f"{self.registry_prefix}/blobs"
        return f"{self.registry_prefix}/objects"


class _MultiRootResolverV1:
    def __init__(self, roots: list[Path]) -> None:
        self._roots = [Path(r).resolve() for r in roots]

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        aid = str(artifact_id).strip()
        at = str(artifact_type).strip()
        ex = str(ext).strip()
        if not aid.startswith("sha256:") or len(aid) != len("sha256:") + 64:
            fail("SCHEMA_FAIL")
        if ex not in {"json", "bin"} or not at:
            fail("SCHEMA_FAIL")
        hex64 = aid.split(":", 1)[1]
        filename = f"sha256_{hex64}.{at}.{ex}"
        matches: list[Path] = []
        for root in self._roots:
            if root.exists() and root.is_dir():
                matches.extend([p for p in root.rglob(filename) if p.is_file()])
        matches = sorted(matches, key=lambda p: p.as_posix())
        if len(matches) != 1:
            fail("MISSING_STATE_INPUT")
        return matches[0].read_bytes()


def _build_dataset_one_sample(
    *,
    writer: _StageWriter,
    opset_id: str,
    d_u32: int,
    concept_shard_id: str,
) -> tuple[str, dict[str, str]]:
    # z_t and z_tp1_true bins (shape [d]) are both zero.
    z_t_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[int(d_u32)], values_i64=[0] * int(d_u32)))
    z_true_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[int(d_u32)], values_i64=[0] * int(d_u32)))

    # Action record (NOOP).
    action_obj = make_noop_action_v1("dc1:q32_v1", str(opset_id))
    action_id = writer.write_json_artifact("dmpl_action_v1", dict(action_obj))

    rec_obj = {
        "record_kind": "SAMPLE",
        "episode_id": "episode0",
        "t_u32": 0,
        "ladder_level_u32": 0,
        "start_state_id": "sha256:" + ("22" * 32),
        "z_t_bin_id": str(z_t_id),
        "z_tp1_true_bin_id": str(z_true_id),
        "action_record_id": str(action_id),
        "active_concepts": [str(concept_shard_id)],
    }
    rec_raw = gcj1_canon_bytes(rec_obj)

    # Build one BIN chunk containing one lenpref record.
    stream = encode_record_lenpref_canonjson_v1(dict(rec_obj))
    if len(stream) > _CHUNK_SIZE_BYTES_V1:
        fail("SCHEMA_FAIL")
    chunk_id = writer.write_bin_artifact("dmpl_dataset_chunk_v1", bytes(stream))
    chunk_hash32 = bytes.fromhex(str(chunk_id).split(":", 1)[1])
    chunks_merkle_root32 = compute_chunk_merkle_root_v1([chunk_hash32])
    chunks_merkle_root = f"sha256:{bytes(chunks_merkle_root32).hex()}"

    # Dataset chain final (over canonical record bytes, not lenpref).
    h = _sha25632(_DATASET_CHAIN_PREFIX + str(opset_id).encode("utf-8", errors="strict"))
    h = _sha25632(bytes(h) + _sha25632(rec_raw))
    samples_chain_final = f"sha256:{bytes(h).hex()}"

    pack_obj = {
        "schema_id": "dmpl_dataset_pack_v1",
        "dc1_id": "dc1:q32_v1",
        "opset_id": str(opset_id),
        "sample_count_u64": 1,
        "chunk_size_bytes_u32": _CHUNK_SIZE_BYTES_V1,
        "chunks": [{"chunk_index_u32": 0, "chunk_bin_id": str(chunk_id), "chunk_bytes_u32": int(len(stream))}],
        "samples_chain_final": str(samples_chain_final),
        "chunks_merkle_root": str(chunks_merkle_root),
    }
    dataset_pack_id = writer.write_json_artifact("dmpl_dataset_pack_v1", dict(pack_obj))

    pack_ref = writer.get_ref_under_stage(artifact_type="dmpl_dataset_pack_v1", artifact_id=dataset_pack_id, ext="json")
    return str(dataset_pack_id), dict(pack_ref)


def _build_dmpl_baseline(
    *,
    writer: _StageWriter,
    opset_id: str,
    ml_index_manifest_id: str,
) -> tuple[str, str, str, str]:
    dc1_id = "dc1:q32_v1"

    # DMPL dims (kept tiny for fast producer runs).
    d_u32 = 2
    p_u32 = 4
    embed_dim_u32 = 2

    # Base tensors (all zeros).
    A0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[d_u32, d_u32], values_i64=[0] * (d_u32 * d_u32)))
    B0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[d_u32, p_u32], values_i64=[0] * (d_u32 * p_u32)))
    Wg_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[embed_dim_u32, d_u32], values_i64=[0] * (embed_dim_u32 * d_u32)))
    b0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[d_u32], values_i64=[0] * d_u32))
    w0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[d_u32], values_i64=[0] * d_u32))
    v0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[1], values_i64=[0]))

    # One concept shard (patch_kind=none) + embedding.
    embed_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[embed_dim_u32], values_i64=[0] * embed_dim_u32))
    concept_obj = {
        "schema_id": "dmpl_concept_shard_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "concept_handle": "concept/test_concept",
        "concept_shard_kind": "dmpl_patch_v1",
        "embed_tensor_bin_id": str(embed_id),
        "patches_by_level": [
            {
                "ladder_level_u32": 0,
                "patch_kind": "none",
                "v_c0_q32": {"q": 0},
                "w_bin_id": "sha256:" + ("0" * 64),
            }
        ],
    }
    concept_id = writer.write_json_artifact("dmpl_concept_shard_v1", dict(concept_obj))

    modelpack_obj = {
        "schema_id": "dmpl_modelpack_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "dims": {"d_u32": d_u32, "p_u32": p_u32, "embed_dim_u32": embed_dim_u32},
        "forward_arch_id": "dmpl_linear_pwl_v1",
        "value_arch_id": "dmpl_linear_v1",
        "activation_id": "hard_tanh_q32_v1",
        "gating_arch_id": "linear_gate_v1",
        "inverse_head_supported_b": False,
        "tensor_specs": [
            {"name": "A0", "shape_u32": [d_u32, d_u32], "role": "forward"},
            {"name": "B0", "shape_u32": [d_u32, p_u32], "role": "forward"},
            {"name": "Wg", "shape_u32": [embed_dim_u32, d_u32], "role": "gate"},
            {"name": "b0", "shape_u32": [d_u32], "role": "forward"},
            {"name": "v0", "shape_u32": [1], "role": "value"},
            {"name": "w0", "shape_u32": [d_u32], "role": "value"},
        ],
        "patch_policy": {"allowed_patch_types": ["matrix_patch", "lowrank_patch"], "vm_patch_allowed_b": False},
    }
    modelpack_id = writer.write_json_artifact("dmpl_modelpack_v1", dict(modelpack_obj))

    # Params bundles.
    f_bundle = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "bundle_kind": "F",
        "modelpack_id": str(modelpack_id),
        "tensors": [
            {"name": "A0", "shape_u32": [d_u32, d_u32], "tensor_bin_id": str(A0_id)},
            {"name": "B0", "shape_u32": [d_u32, p_u32], "tensor_bin_id": str(B0_id)},
            {"name": "Wg", "shape_u32": [embed_dim_u32, d_u32], "tensor_bin_id": str(Wg_id)},
            {"name": "b0", "shape_u32": [d_u32], "tensor_bin_id": str(b0_id)},
        ],
        "merkle_root": "",
    }
    f_bundle["tensors"].sort(key=lambda r: str(r["name"]))
    f_bundle["merkle_root"] = compute_params_bundle_merkle_root_v1(bundle_obj=dict(f_bundle), resolver=None)
    fparams_id = writer.write_json_artifact("dmpl_params_bundle_v1", dict(f_bundle))

    v_bundle = {
        "schema_id": "dmpl_params_bundle_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "bundle_kind": "V",
        "modelpack_id": str(modelpack_id),
        "tensors": [
            {"name": "v0", "shape_u32": [1], "tensor_bin_id": str(v0_id)},
            {"name": "w0", "shape_u32": [d_u32], "tensor_bin_id": str(w0_id)},
        ],
        "merkle_root": "",
    }
    v_bundle["tensors"].sort(key=lambda r: str(r["name"]))
    v_bundle["merkle_root"] = compute_params_bundle_merkle_root_v1(bundle_obj=dict(v_bundle), resolver=None)
    vparams_id = writer.write_json_artifact("dmpl_params_bundle_v1", dict(v_bundle))

    # DMPL config (enabled).
    caps_obj = {
        "K_ctx_u32": 2,
        "K_g_u32": 1,
        "max_concept_bytes_per_step_u32": 1_000_000,
        "max_retrieval_bytes_u32": 1_000_000,
        "max_retrieval_ops_u64": 10_000_000,
        "max_patch_rank_u32": 0,
        "max_patch_bytes_u32": 0,
        "max_patch_vm_steps_u32": 0,
        "H_u32": 1,
        "Nmax_u32": 10,
        "Ka_u32": 2,
        "beam_width_u32": 0,
        "max_trace_bytes_u32": 10_000_000,
        "max_node_opcount_u64": 10_000_000,
        "max_total_opcount_u64": 100_000_000,
        "train_steps_u32": 1,
        "batch_size_u32": 1,
        "max_grad_norm_q32": {"q": int(Q32_ONE)},
        "lr_q32": {"q": 0},
        "dataset_max_bytes_u64": 10_000_000,
        "max_stack_depth_u32": 0,
        "max_recursion_depth_u32": 0,
    }
    caps_digest = sha256_prefixed(gcj1_canon_bytes(caps_obj))

    config_obj = {
        "schema_id": "dmpl_config_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "enabled_b": True,
        "active_modelpack_id": str(modelpack_id),
        "fparams_bundle_id": str(fparams_id),
        "vparams_bundle_id": str(vparams_id),
        "caps": dict(caps_obj),
        "retrieval_spec": {
            "ml_index_manifest_id": str(ml_index_manifest_id),
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
            "stab_thresholds": {
                "G0": {"q": 0},
                "G1": {"q": int(Q32_ONE)},
                "G2": {"q": 0},
                "G3": {"q": 0},
                "G4": {"q": 0},
                "G5": {"q": 0},
            },
        },
        "planner_spec": {
            "algorithm_id": "dcbts_l_v1",
            "ladder_policy": {"ell_hi_u32": 0, "ell_lo_u32": 0, "refine_enabled_b": False, "refine_budget_u32": 0, "refine_per_step_budget_u32": 0},
            "action_source_id": "dmpl_action_enum_v1",
            "ordering_policy": {
                "primary_key_id": "upper_bound_primary_score_desc",
                "secondary_key_id": "depth_asc",
                "tertiary_key_id": "node_id_asc",
            },
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
    config_id = writer.write_json_artifact("dmpl_config_v1", dict(config_obj))

    droot_obj = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": dc1_id,
        "opset_id": str(opset_id),
        "dmpl_config_id": str(config_id),
        "froot": str(f_bundle["merkle_root"]),
        "vroot": str(v_bundle["merkle_root"]),
        "caps_digest": str(caps_digest),
        "opset_semantics_id": str(opset_id),
    }
    droot_id = writer.write_json_artifact("dmpl_droot_v1", dict(droot_obj))

    return str(droot_id), str(config_id), str(modelpack_id), str(concept_id)


def _build_ml_index_one_concept(
    *,
    writer: _StageWriter,
    opset_id: str,
    concept_id: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, Any]]:
    # Minimal ML-index bundle that satisfies MEM gates and DMPL key wrapper constraints.
    key_dim_u32 = 4

    codebook = MLIndexCodebookV1(K_u32=1, d_u32=key_dim_u32, C_q32=[0] * key_dim_u32)
    codebook_id = writer.write_bin_artifact("ml_index_codebook_v1", encode_ml_index_codebook_v1(codebook))
    codebook_ref = writer.get_ref_under_stage(artifact_type="ml_index_codebook_v1", artifact_id=codebook_id, ext="bin")

    concept_id32 = bytes.fromhex(str(concept_id).split(":", 1)[1])
    page = MLIndexPageV1(
        bucket_id_u32=0,
        page_index_u32=0,
        key_dim_u32=key_dim_u32,
        records=[
            MLIndexPageRecordV1(
                record_hash32=b"\x01" * 32,
                payload_hash32=concept_id32,
                key_q32=[0] * key_dim_u32,
            )
        ],
    )
    page_id = writer.write_bin_artifact("ml_index_page_v1", encode_ml_index_page_v1(page))
    page_ref = writer.get_ref_under_stage(artifact_type="ml_index_page_v1", artifact_id=page_id, ext="bin")

    bucket_listing_obj = {
        "schema_id": "ml_index_bucket_listing_v1",
        "index_manifest_id": "sha256:" + ("11" * 32),
        "buckets": [{"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": dict(page_ref)}]}],
    }
    bucket_listing_id = writer.write_json_artifact("ml_index_bucket_listing_v1", dict(bucket_listing_obj))
    bucket_listing_ref = writer.get_ref_under_stage(artifact_type="ml_index_bucket_listing_v1", artifact_id=bucket_listing_id, ext="json")

    leaf0 = bytes.fromhex(str(page_id).split(":", 1)[1])
    root0 = merkle_fanout_v1(leaf_hash32=[leaf0], fanout_u32=2)
    index_root = MLIndexRootV1(K_u32=1, fanout_u32=2, bucket_root_hash32=[root0])
    index_root_id = writer.write_bin_artifact("ml_index_root_v1", encode_ml_index_root_v1(index_root))
    index_root_ref = writer.get_ref_under_stage(artifact_type="ml_index_root_v1", artifact_id=index_root_id, ext="bin")

    ml_index_manifest_obj = {
        "schema_id": "ml_index_manifest_v1",
        "index_kind": "ML_INDEX_V1",
        "opset_id": str(opset_id),
        "key_dim_u32": key_dim_u32,
        "codebook_size_u32": 1,
        "bucket_visit_k_u32": 1,
        "scan_cap_per_bucket_u32": 10,
        "merkle_fanout_u32": 2,
        "sim_kind": "DOT_Q32_SHIFT_END_V1",
        "codebook_ref": dict(codebook_ref),
        "index_root_ref": dict(index_root_ref),
        "bucket_listing_ref": dict(bucket_listing_ref),
        "mem_gates": {
            "mem_g1_bucket_balance_max_q32": {"q": int(Q32_ONE)},
            "mem_g2_anchor_recall_min_q32": {"q": 0},
        },
    }
    ml_index_manifest_id = writer.write_json_artifact("ml_index_manifest_v1", dict(ml_index_manifest_obj))
    ml_index_manifest_ref = writer.get_ref_under_stage(artifact_type="ml_index_manifest_v1", artifact_id=ml_index_manifest_id, ext="json")

    return ml_index_manifest_ref, index_root_ref, bucket_listing_ref, dict(ml_index_manifest_obj)


def emit_dmpl_phase4_promotion_bundle_v1(*, state_dir: Path, producer_kind: str) -> dict[str, Any]:
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    evidence_dir = state_dir / "eudrs_u" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    stage_root = state_dir / "eudrs_u" / "staged_registry_tree"
    stage_root.mkdir(parents=True, exist_ok=True)

    writer = _StageWriter(stage_root=stage_root)

    dc1_id = "dc1:q32_v1"

    repo_root = Path(__file__).resolve().parents[2]
    prev_epoch = _read_prev_epoch_u64(repo_root)
    epoch_u64 = 0 if prev_epoch is None else (prev_epoch + 1)

    opset_digest = sha256_prefixed(gcj1_canon_bytes({"schema_id": "eudrs_u_opset_stub_v1", "version_u64": 1}))
    opset_id = f"opset:eudrs_u_v1:{opset_digest}"

    # Placeholder evidence artifacts (run-local) required by the promotion summary schema.
    weights_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="weights_manifest_v1",
        obj={"schema_id": "weights_manifest_v1", "producer_kind": str(producer_kind)},
    )
    cac_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="cac_v1",
        obj={"schema_id": "cac_v1", "producer_kind": str(producer_kind)},
    )
    ufc_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="ufc_v1",
        obj={"schema_id": "ufc_v1", "producer_kind": str(producer_kind)},
    )
    cooldown_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="cooldown_ledger_v1",
        obj={"schema_id": "cooldown_ledger_v1", "producer_kind": str(producer_kind), "epoch_u64": int(epoch_u64), "locks": []},
    )
    stability_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="stability_metrics_v1",
        obj={"schema_id": "stability_metrics_v1", "producer_kind": str(producer_kind)},
    )
    det_cert_obj = {
        "schema_id": "determinism_cert_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxrl": {
            "training_manifest_ref": {
                "artifact_id": "sha256:" + ("0" * 64),
                "artifact_relpath": "polymath/registry/eudrs_u/objects/sha256_" + ("0" * 64) + ".missing.json",
            },
            "h_train_tail32_hex": "0" * 64,
            "h_eval_tail32_hex": "0" * 64,
            "math": {
                "dot_kind": "DOT_Q32_SHIFT_END_V1",
                "div_kind": "DIV_Q32_POS_RNE_V1",
                "invsqrt_kind": "INVSQRT_Q32_NR_LUT_V1",
                "invsqrt_lut_manifest_ref": {
                    "artifact_id": "sha256:" + ("0" * 64),
                    "artifact_relpath": "polymath/registry/eudrs_u/objects/sha256_" + ("0" * 64) + ".missing.json",
                },
                "invsqrt_iters_u32": 1,
            },
        },
    }
    det_cert_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="determinism_cert_v1",
        obj=dict(det_cert_obj),
    )
    uni_cert_ref = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="universality_cert_v1",
        obj={"schema_id": "universality_cert_v1", "producer_kind": str(producer_kind)},
    )

    # Build baseline DMPL artifacts and a minimal ML-index bundle.
    # Note: the ML-index payload is a single concept shard id.
    # Build DMPL first to obtain concept id, then build the index, then fix config ml_index_manifest_id.
    # We do this by building the index manifest as a stage artifact (and mirroring into evidence).
    # Step 1: temporary placeholder id for config; actual id is the written manifest artifact id.
    placeholder_ml_index_manifest_id = "sha256:" + ("11" * 32)
    droot_id, config_id, modelpack_id, concept_id = _build_dmpl_baseline(
        writer=writer,
        opset_id=opset_id,
        ml_index_manifest_id=placeholder_ml_index_manifest_id,
    )

    # Step 2: ML-index (depends on concept_id).
    ml_index_manifest_ref_stage, index_root_ref, bucket_listing_ref_stage, ml_index_manifest_obj = _build_ml_index_one_concept(
        writer=writer,
        opset_id=opset_id,
        concept_id=concept_id,
    )
    ml_index_manifest_id = str(ml_index_manifest_ref_stage["artifact_id"])

    # Step 3: Rewrite DMPL config+droot so retrieval_spec binds the actual ml_index_manifest_id.
    # (Content-addressed: this produces new config/droot IDs; the verifier binds via droot anyway.)
    # Load existing config+bundles from the stage tree to preserve all other fields deterministically.
    resolver = _MultiRootResolverV1([stage_root])
    old_cfg = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=config_id, artifact_type="dmpl_config_v1", ext="json"))
    if not isinstance(old_cfg, dict):
        fail("SCHEMA_FAIL")
    new_cfg = dict(old_cfg)
    new_cfg["retrieval_spec"] = dict(new_cfg.get("retrieval_spec") or {})
    new_cfg["retrieval_spec"]["ml_index_manifest_id"] = str(ml_index_manifest_id)
    new_cfg_id = writer.write_json_artifact("dmpl_config_v1", new_cfg)

    # Update droot to point at the new config id; roots are unchanged.
    old_droot = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=droot_id, artifact_type="dmpl_droot_v1", ext="json"))
    if not isinstance(old_droot, dict):
        fail("SCHEMA_FAIL")
    new_droot = dict(old_droot)
    new_droot["dmpl_config_id"] = str(new_cfg_id)
    new_droot_id = writer.write_json_artifact("dmpl_droot_v1", new_droot)
    droot_id = str(new_droot_id)
    config_id = str(new_cfg_id)

    # Mirror ML-index manifest into evidence directory (required by promotion verifier).
    ml_index_manifest_ref_evidence = _write_hashed_json(
        root=state_dir,
        rel_dir="eudrs_u/evidence",
        artifact_type="ml_index_manifest_v1",
        obj=dict(ml_index_manifest_obj),
    )

    # Mirror should hash-identical; otherwise verifier will reject via ArtifactRef hash mismatch.
    if str(ml_index_manifest_ref_evidence["artifact_id"]).strip() != str(ml_index_manifest_id).strip():
        fail("NONDETERMINISTIC")

    # Build dataset pack (for training replay) using the concept id.
    runtime = load_runtime_from_droot_v1(str(droot_id), resolver=_MultiRootResolverV1([stage_root]))
    d_u32 = int(runtime.dims.d_u32)
    dataset_pack_id, dataset_pack_ref_under_stage = _build_dataset_one_sample(writer=writer, opset_id=opset_id, d_u32=d_u32, concept_shard_id=concept_id)

    # Training: 1 step, batch_size 1, lr=0 (no-op update but fully replayable).
    train_run_obj = {
        "schema_id": "dmpl_train_run_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "baseline_droot_id": str(droot_id),
        "dataset_pack_id": str(dataset_pack_id),
        "initial_fparams_bundle_id": str(runtime.config.get("fparams_bundle_id")),
        "initial_vparams_bundle_id": str(runtime.config.get("vparams_bundle_id")),
        "train_steps_u32": int(runtime.caps.get("train_steps_u32", 1)),
        "batch_size_u32": int(runtime.caps.get("batch_size_u32", 1)),
        "lr_q32": dict(runtime.caps.get("lr_q32") or {"q": 0}),
        "max_grad_norm_q32": dict(runtime.caps.get("max_grad_norm_q32") or {"q": int(Q32_ONE)}),
        "trainable_tensors": ["A0", "B0", "Wg", "b0", "v0", "w0"],
        "expected_output_kind": "FULL_TENSORS_EACH_STEP_V1",
    }
    train_run_id = writer.write_json_artifact("dmpl_train_run_v1", dict(train_run_obj))
    train_run_ref_under_stage = writer.get_ref_under_stage(artifact_type="dmpl_train_run_v1", artifact_id=train_run_id, ext="json")

    # Load dataset sample object back (canonical) to ensure we train on exactly what we wrote.
    dataset_pack_bytes = resolver.load_artifact_bytes(artifact_id=str(dataset_pack_id), artifact_type="dmpl_dataset_pack_v1", ext="json")
    dataset_pack_obj = gcj1_loads_and_verify_canonical(dataset_pack_bytes)
    if not isinstance(dataset_pack_obj, dict):
        fail("SCHEMA_FAIL")
    chunks = dataset_pack_obj.get("chunks")
    if not isinstance(chunks, list) or len(chunks) != 1 or not isinstance(chunks[0], dict):
        fail("SCHEMA_FAIL")
    chunk_id = str(chunks[0].get("chunk_bin_id", "")).strip()
    chunk_bytes = resolver.load_artifact_bytes(artifact_id=chunk_id, artifact_type="dmpl_dataset_chunk_v1", ext="bin")
    # Parse the single record: u32le(nbytes)+json.
    if len(chunk_bytes) < 4:
        fail("SCHEMA_FAIL")
    (n,) = _U32LE.unpack_from(chunk_bytes, 0)
    rec_bytes = bytes(chunk_bytes[4 : 4 + int(n)])
    rec_obj = gcj1_loads_and_verify_canonical(rec_bytes)
    if not isinstance(rec_obj, dict):
        fail("SCHEMA_FAIL")

    # Load tensors + action for training math.
    z_t_raw = resolver.load_artifact_bytes(artifact_id=str(rec_obj["z_t_bin_id"]), artifact_type="dmpl_tensor_q32_v1", ext="bin")
    z_true_raw = resolver.load_artifact_bytes(artifact_id=str(rec_obj["z_tp1_true_bin_id"]), artifact_type="dmpl_tensor_q32_v1", ext="bin")
    # Parse the tensor bins using runtime loader's already-loaded base dims; these were written by this producer.
    from cdel.v18_0.eudrs_u.dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape

    z_t_dims, z_t_vals = parse_tensor_q32_v1(z_t_raw)
    z_true_dims, z_true_vals = parse_tensor_q32_v1(z_true_raw)
    require_shape(z_t_dims, [d_u32])
    require_shape(z_true_dims, [d_u32])

    action_raw = resolver.load_artifact_bytes(artifact_id=str(rec_obj["action_record_id"]), artifact_type="dmpl_action_v1", ext="json")
    action_obj = gcj1_loads_and_verify_canonical(action_raw)
    if not isinstance(action_obj, dict):
        fail("SCHEMA_FAIL")

    # Build ConceptPatchEntry list from the concept shard artifact.
    concept_raw = resolver.load_artifact_bytes(artifact_id=str(concept_id), artifact_type="dmpl_concept_shard_v1", ext="json")
    concept_obj2 = gcj1_loads_and_verify_canonical(concept_raw)
    if not isinstance(concept_obj2, dict):
        fail("SCHEMA_FAIL")
    embed_bin_id = str(concept_obj2.get("embed_tensor_bin_id", "")).strip()
    embed_raw = resolver.load_artifact_bytes(artifact_id=embed_bin_id, artifact_type="dmpl_tensor_q32_v1", ext="bin")
    embed_dims, embed_vals = parse_tensor_q32_v1(embed_raw)
    require_shape(embed_dims, [int(runtime.dims.embed_dim_u32)])

    concept_entry = ConceptPatchEntryV1(
        concept_shard_id=str(concept_id),
        embed_vec_q32=[int(v) for v in embed_vals],
        patch_kind="none",
        A_vals_q32=None,
        B_vals_q32=None,
        b_vals_q32=None,
        rank_u32=None,
        A_u_vals_q32=None,
        A_v_vals_q32=None,
        B_u_vals_q32=None,
        B_v_vals_q32=None,
        v_c0_q32=0,
        w_vec_q32=None,
    )

    state = TrainableStateV1(
        A0_q32=[int(v) for v in runtime.base_forward["A0"][1]],
        B0_q32=[int(v) for v in runtime.base_forward["B0"][1]],
        b0_q32=[int(v) for v in runtime.base_forward["b0"][1]],
        Wg_q32=[int(v) for v in runtime.base_forward["Wg"][1]],
        w0_q32=[int(v) for v in runtime.base_value["w0"][1]],
        v0_q32=int(runtime.base_value["v0"][1][0]),
    )

    trace_writer = TrainTraceWriterV1(train_run_id=str(train_run_id), opset_id=str(opset_id))

    # One training step on the single record.
    step_res = train_step_sgd_det_v1(
        d_u32=int(d_u32),
        p_u32=int(runtime.dims.p_u32),
        embed_dim_u32=int(runtime.dims.embed_dim_u32),
        gamma_q32=int(runtime.config["objective_spec"]["gamma_q32"]["q"]),
        normalize_weights_b=bool(runtime.config["gating_spec"]["normalize_weights_b"]),
        epsilon_q32=int(runtime.config["gating_spec"]["epsilon_q32"]["q"]),
        max_grad_norm_q32=int(runtime.caps["max_grad_norm_q32"]["q"]),
        lr_q32=int(runtime.caps["lr_q32"]["q"]),
        state=state,
        batch=[dict(rec_obj)],
        concept_patches_by_sample=[[concept_entry]],
        action_objs=[dict(action_obj)],
        z_t_vecs_q32=[[int(v) for v in z_t_vals]],
        z_tp1_true_vecs_q32=[[int(v) for v in z_true_vals]],
    )

    updated_ids = {
        "A0": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[d_u32, d_u32], values_i64=[int(v) for v in state.A0_q32])),
        "B0": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[d_u32, int(runtime.dims.p_u32)], values_i64=[int(v) for v in state.B0_q32])),
        "b0": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[d_u32], values_i64=[int(v) for v in state.b0_q32])),
        "Wg": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[int(runtime.dims.embed_dim_u32), d_u32], values_i64=[int(v) for v in state.Wg_q32])),
        "w0": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[d_u32], values_i64=[int(v) for v in state.w0_q32])),
        "v0": sha256_prefixed_bytes(encode_tensor_q32_v1(dims_u32=[1], values_i64=[int(state.v0_q32)])),
    }

    train_step_obj = {
        "record_kind": "TRAIN_STEP",
        "step_u32": 0,
        "batch_start_index_u64": 0,
        "batch_ids": [{"episode_id": str(rec_obj["episode_id"]), "t_u32": int(rec_obj["t_u32"])}],
        "loss_pred_q32": {"q": int(step_res.loss_pred_q32)},
        "loss_value_q32": {"q": int(step_res.loss_value_q32)},
        "loss_total_q32": {"q": int(step_res.loss_total_q32)},
        "grad_norm_q32": {"q": int(step_res.grad_norm_q32)},
        "clipped_b": bool(step_res.clipped_b),
        "lr_q32": {"q": int(runtime.caps["lr_q32"]["q"])},
        "max_grad_norm_q32": {"q": int(runtime.caps["max_grad_norm_q32"]["q"])},
        "updated_tensor_bin_ids": dict(updated_ids),
        "cap_counters": {"ops_u64": 0, "bytes_u64": 0},
    }
    trace_writer.append_record(dict(train_step_obj))

    train_trace_id, _chunks_root = trace_writer.finalize(writer.write_bin_artifact, writer.write_json_artifact)
    train_trace_ref_under_stage = writer.get_ref_under_stage(artifact_type="dmpl_train_trace_v1", artifact_id=train_trace_id, ext="json")

    # Candidate bundles/config/droot are identical (lr=0); compute ids deterministically as the verifier does.
    candidate_fparams_bundle_id = str(runtime.config["fparams_bundle_id"])
    candidate_vparams_bundle_id = str(runtime.config["vparams_bundle_id"])
    candidate_froot = str(new_droot.get("froot"))
    candidate_vroot = str(new_droot.get("vroot"))
    candidate_config_id = str(config_id)
    candidate_droot_id = str(droot_id)

    train_receipt_obj = {
        "schema_id": "dmpl_train_receipt_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "train_run_id": str(train_run_id),
        "train_trace_id": str(train_trace_id),
        "baseline_droot_id": str(droot_id),
        "candidate_droot_id": str(candidate_droot_id),
        "candidate_config_id": str(candidate_config_id),
        "candidate_fparams_bundle_id": str(candidate_fparams_bundle_id),
        "candidate_vparams_bundle_id": str(candidate_vparams_bundle_id),
        "candidate_froot": str(candidate_froot),
        "candidate_vroot": str(candidate_vroot),
        "status": {"ok_b": True, "reason_code": "DMPL_OK"},
    }
    train_receipt_id = writer.write_json_artifact("dmpl_train_receipt_v1", dict(train_receipt_obj))
    train_receipt_ref_under_stage = writer.get_ref_under_stage(artifact_type="dmpl_train_receipt_v1", artifact_id=train_receipt_id, ext="json")

    # Plan evidence: baseline + candidate (scenario_id pinned for CAC).
    z0_id = writer.write_bin_artifact("dmpl_tensor_q32_v1", encode_tensor_q32_v1(dims_u32=[d_u32], values_i64=[0] * d_u32))

    def _plan_one(vm_step_u64: int) -> tuple[dict[str, Any], str, str]:
        plan_query_obj = {
            "schema_id": "dmpl_plan_query_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "dmpl_droot_id": str(droot_id),
            "start_state_id": "sha256:" + ("22" * 32),
            "z0_tensor_bin_id": str(z0_id),
            "call_context": {"vm_step_u64": int(vm_step_u64), "scenario_id": "scenario_0"},
        }
        pq_id = writer.write_json_artifact("dmpl_plan_query_v1", dict(plan_query_obj))
        plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(plan_query_obj), resolver=_MultiRootResolverV1([stage_root]), artifact_writer=writer)
        return dict(plan_query_obj), str(pq_id), str(plan_result.rollout_trace_id), str(plan_result.action_receipt_id)

    baseline_pq_obj, baseline_pq_id, baseline_rt_id, baseline_ar_id = _plan_one(0)
    cand_pq_obj, cand_pq_id, cand_rt_id, cand_ar_id = _plan_one(1)

    plan_evidence_items_under_state: list[dict[str, Any]] = []
    for pq_id, rt_id, ar_id in [
        (baseline_pq_id, baseline_rt_id, baseline_ar_id),
        (cand_pq_id, cand_rt_id, cand_ar_id),
    ]:
        pq_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_plan_query_v1", artifact_id=pq_id, ext="json")
        rt_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_rollout_trace_v1", artifact_id=rt_id, ext="json")
        ar_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_action_receipt_v1", artifact_id=ar_id, ext="json")
        plan_evidence_items_under_state.append(
            {
                "schema_id": "dmpl_plan_evidence_v1",
                "plan_query_ref": {"artifact_id": pq_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(pq_ref_stage["artifact_relpath"])},
                "rollout_trace_ref": {"artifact_id": rt_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(rt_ref_stage["artifact_relpath"])},
                "action_receipt_ref": {"artifact_id": ar_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(ar_ref_stage["artifact_relpath"])},
            }
        )

    plan_evidence_items_under_state.sort(key=lambda it: str(it["plan_query_ref"]["artifact_id"]))

    # Certificates (producer convenience; RE2 recomputes).
    eval_suite_id = sha256_prefixed(gcj1_canon_bytes({"schema_id": "dmpl_eval_suite_stub_v1", "scenarios": ["scenario_0"]}))

    # Load ActionReceipts to get bound scores for CAC.
    base_ar_obj = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=baseline_ar_id, artifact_type="dmpl_action_receipt_v1", ext="json"))
    cand_ar_obj = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=cand_ar_id, artifact_type="dmpl_action_receipt_v1", ext="json"))
    if not isinstance(base_ar_obj, dict) or not isinstance(cand_ar_obj, dict):
        fail("SCHEMA_FAIL")
    J_base = int(base_ar_obj["tie_break_proof"]["ordering_keys"][0]["bound_score_q32"]["q"])
    J_cand = int(cand_ar_obj["tie_break_proof"]["ordering_keys"][0]["bound_score_q32"]["q"])
    delta = add_sat(int(J_cand), int(-int(J_base)))

    cac_pack_obj = {
        "schema_id": "dmpl_cac_pack_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "baseline_droot_id": str(droot_id),
        "candidate_droot_id": str(droot_id),
        "eval_suite_id": str(eval_suite_id),
        "per_scenario": [
            {
                "scenario_id": "scenario_0",
                "J_base_q32": {"q": int(J_base)},
                "J_cand_q32": {"q": int(J_cand)},
                "delta_q32": {"q": int(delta)},
                "baseline_plan_evidence": {"plan_query_id": str(baseline_pq_id), "rollout_trace_id": str(baseline_rt_id), "action_receipt_id": str(baseline_ar_id)},
                "candidate_plan_evidence": {"plan_query_id": str(cand_pq_id), "rollout_trace_id": str(cand_rt_id), "action_receipt_id": str(cand_ar_id)},
            }
        ],
        "cac_lb_q32": {"q": int(delta)},
        "status": {"ok_b": True, "reason_code": "DMPL_OK"},
    }
    cac_pack_id = writer.write_json_artifact("dmpl_cac_pack_v1", dict(cac_pack_obj))
    cac_pack_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_cac_pack_v1", artifact_id=cac_pack_id, ext="json")

    # UFC (candidate scenario).
    cand_rt_obj = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=cand_rt_id, artifact_type="dmpl_rollout_trace_v1", ext="json"))
    if not isinstance(cand_rt_obj, dict):
        fail("SCHEMA_FAIL")
    ufc_row = _recompute_ufc_for_scenario(
        scenario_id="scenario_0",
        chosen_action_receipt_id=str(cand_ar_id),
        chosen_rollout_trace_id=str(cand_rt_id),
        rollout_trace_obj=dict(cand_rt_obj),
        action_receipt_obj=dict(cand_ar_obj),
        gamma_q32=int(runtime.config["objective_spec"]["gamma_q32"]["q"]),
        resolver=_MultiRootResolverV1([stage_root]),
    )
    ufc_obj = {
        "schema_id": "dmpl_ufc_flow_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "candidate_droot_id": str(droot_id),
        "eval_suite_id": str(eval_suite_id),
        "per_scenario": [dict(ufc_row)],
    }
    ufc_id = writer.write_json_artifact("dmpl_ufc_flow_v1", dict(ufc_obj))
    ufc_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_ufc_flow_v1", artifact_id=ufc_id, ext="json")

    # STAB report (recomputed in RE2; producer writes identical expected object).
    # G0 threshold pinned to 0; G2,G4 pinned to 0; G5 >=0.
    stab_thresholds = dict(runtime.config["gating_spec"]["stab_thresholds"])
    thr_G0 = int(stab_thresholds["G0"]["q"])
    thr_G1 = int(stab_thresholds["G1"]["q"])
    thr_G2 = int(stab_thresholds["G2"]["q"])
    thr_G3 = int(stab_thresholds["G3"]["q"])
    thr_G4 = int(stab_thresholds["G4"]["q"])
    thr_G5 = int(stab_thresholds["G5"]["q"])

    max_grad_seen = int(step_res.grad_norm_q32)
    pass_G1 = bool(int(max_grad_seen) <= int(thr_G1))

    # Planning budget: ensure all action receipts in plan evidence have ok_b.
    fail_count = 0
    for ar_id in [baseline_ar_id, cand_ar_id]:
        ar_obj = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=ar_id, artifact_type="dmpl_action_receipt_v1", ext="json"))
        if not isinstance(ar_obj, dict):
            fail("SCHEMA_FAIL")
        if bool(((ar_obj.get("gating_summary") or {}).get("status") or {}).get("ok_b", False)) is not True:
            fail_count += 1
    pass_G2 = bool(fail_count == 0)

    # Holdout predictive sanity.
    dataset_pack_obj2 = gcj1_loads_and_verify_canonical(resolver.load_artifact_bytes(artifact_id=str(dataset_pack_id), artifact_type="dmpl_dataset_pack_v1", ext="json"))
    if not isinstance(dataset_pack_obj2, dict):
        fail("SCHEMA_FAIL")
    mean_L1_pred_q32 = int(
        _compute_holdout_mean_L1_pred_q32(
            candidate_droot_id=str(droot_id),
            dataset_pack_obj=dict(dataset_pack_obj2),
            config_obj=dict(runtime.config),
            resolver=_MultiRootResolverV1([stage_root]),
        )
    )
    pass_G3 = bool(int(mean_L1_pred_q32) <= int(thr_G3))

    gate_results = {
        "G0": {"pass_b": True, "metrics": {"metric_q32": {"q": 0}}, "thresholds": {"threshold_q32": {"q": int(thr_G0)}}, "reason_code": "DMPL_OK"},
        "G1": {
            "pass_b": bool(pass_G1),
            "metrics": {"max_grad_norm_seen_q32": {"q": int(max_grad_seen)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G1)}},
            "reason_code": "DMPL_OK" if pass_G1 else "DMPL_E_STAB_GATE_FAIL_G1",
        },
        "G2": {
            "pass_b": bool(pass_G2),
            "metrics": {"planner_budget_fail_count_q32": {"q": int(fail_count)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G2)}},
            "reason_code": "DMPL_OK" if pass_G2 else "DMPL_E_STAB_GATE_FAIL_G2",
        },
        "G3": {
            "pass_b": bool(pass_G3),
            "metrics": {"mean_L1_pred_q32": {"q": int(mean_L1_pred_q32)}},
            "thresholds": {"threshold_q32": {"q": int(thr_G3)}},
            "reason_code": "DMPL_OK" if pass_G3 else "DMPL_E_STAB_GATE_FAIL_G3",
        },
        "G4": {"pass_b": True, "metrics": {"retrieval_mismatch_count_q32": {"q": 0}}, "thresholds": {"threshold_q32": {"q": int(thr_G4)}}, "reason_code": "DMPL_OK"},
        "G5": {"pass_b": True, "metrics": {"metric_q32": {"q": 0}}, "thresholds": {"threshold_q32": {"q": int(thr_G5)}}, "reason_code": "DMPL_OK"},
    }
    stab_obj = {
        "schema_id": "dmpl_stab_report_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "candidate_droot_id": str(droot_id),
        "eval_suite_id": str(eval_suite_id),
        "gate_results": gate_results,
    }
    stab_id = writer.write_json_artifact("dmpl_stab_report_v1", dict(stab_obj))
    stab_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_stab_report_v1", artifact_id=stab_id, ext="json")

    # LA-SUM: compute credits from chosen path reconstruction (must match RE2 verifier exactly).
    normalize_weights_b = bool(runtime.config["gating_spec"]["normalize_weights_b"])
    credit_by_level: dict[int, int] = {}
    credit_by_concept: dict[str, int] = {"RESIDUAL": 0}
    total_ufc = 0

    path_recs = _reconstruct_chosen_path_from_trace(
        rollout_trace_obj=dict(cand_rt_obj),
        action_receipt_obj=dict(cand_ar_obj),
        resolver=_MultiRootResolverV1([stage_root]),
    )
    for rec in path_recs:
        ladder_level = int(rec.get("ladder_level_u32", 0))
        r_hat_q32 = int((rec.get("r_hat_q32") or {}).get("q", 0))
        credit_by_level[ladder_level] = add_sat(int(credit_by_level.get(ladder_level, 0)), int(r_hat_q32))

        delta_u = int(r_hat_q32)
        if normalize_weights_b:
            alloc_sum = 0
            gate_active = rec.get("gate_active")
            if not isinstance(gate_active, list):
                fail("SCHEMA_FAIL")
            for g in gate_active:
                if not isinstance(g, dict):
                    continue
                cid = str(g.get("concept_shard_id", "")).strip()
                w_q32 = int((g.get("w_q32") or {}).get("q", 0))
                alloc = int(mul_q32(int(w_q32), int(delta_u)))
                credit_by_concept[cid] = add_sat(int(credit_by_concept.get(cid, 0)), int(alloc))
                alloc_sum = add_sat(int(alloc_sum), int(alloc))
            residual = add_sat(int(delta_u), int(-int(alloc_sum)))
            credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(residual))
        else:
            credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(delta_u))

        total_ufc = add_sat(int(total_ufc), int(delta_u))

    # Terminal: allocate v_tp1_q32 to residual and to leaf ladder level.
    if path_recs:
        leaf = path_recs[-1]
        ladder_level = int(leaf.get("ladder_level_u32", 0))
        v_term_q32 = int((leaf.get("v_tp1_q32") or {}).get("q", 0))
        credit_by_level[ladder_level] = add_sat(int(credit_by_level.get(ladder_level, 0)), int(v_term_q32))
        credit_by_concept["RESIDUAL"] = add_sat(int(credit_by_concept["RESIDUAL"]), int(v_term_q32))
        total_ufc = add_sat(int(total_ufc), int(v_term_q32))

    total_credit = 0
    for v in credit_by_concept.values():
        total_credit = add_sat(int(total_credit), int(v))
    ok_b = bool(int(total_credit) == int(total_ufc))

    credit_by_level_arr = [{"ladder_level_u32": int(k) & 0xFFFFFFFF, "credit_q32": {"q": int(credit_by_level[k])}} for k in sorted(credit_by_level.keys())]
    credit_by_concept_items = []
    for cid in sorted([k for k in credit_by_concept.keys() if k != "RESIDUAL"]):
        credit_by_concept_items.append({"concept_shard_id": str(cid), "credit_q32": {"q": int(credit_by_concept[cid])}})
    credit_by_concept_items.append({"concept_shard_id": "RESIDUAL", "credit_q32": {"q": int(credit_by_concept["RESIDUAL"])}})

    lasum_obj = {
        "schema_id": "dmpl_lasum_report_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "candidate_droot_id": str(droot_id),
        "eval_suite_id": str(eval_suite_id),
        "credit_by_level": credit_by_level_arr,
        "credit_by_concept": credit_by_concept_items,
        "totals": {"total_credit_q32": {"q": int(total_credit)}, "total_ufc_q32": {"q": int(total_ufc)}, "ok_b": bool(ok_b)},
        "status": {"ok_b": bool(ok_b), "reason_code": "DMPL_OK" if ok_b else "DMPL_E_LASUM_BROKEN"},
    }
    lasum_id = writer.write_json_artifact("dmpl_lasum_report_v1", dict(lasum_obj))
    lasum_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_lasum_report_v1", artifact_id=lasum_id, ext="json")

    # Root tuple + system manifest binding.
    # Minimal system manifest that satisfies schema binding; referenced refs are placeholders.
    world_model_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/manifests",
        artifact_type="qxwmr_world_model_manifest_v1",
        obj={"schema_id": "qxwmr_world_model_manifest_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id},
    )
    qxwmr_eval_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/manifests",
        artifact_type="qxwmr_eval_manifest_v1",
        obj={"schema_id": "qxwmr_eval_manifest_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id},
    )
    stub_qxrl_model_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/manifests",
        artifact_type="qxrl_model_manifest_stub_v1",
        obj={"schema_id": "qxrl_model_manifest_stub_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id},
    )
    stub_qxrl_eval_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/manifests",
        artifact_type="qxrl_eval_manifest_stub_v1",
        obj={"schema_id": "qxrl_eval_manifest_stub_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id},
    )
    stub_qxrl_dataset_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/manifests",
        artifact_type="qxrl_dataset_manifest_stub_v1",
        obj={"schema_id": "qxrl_dataset_manifest_stub_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id},
    )

    system_manifest_obj = {
        "schema_id": "eudrs_u_system_manifest_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxwmr": {"world_model_manifest_ref": dict(world_model_ref), "eval_manifest_ref": dict(qxwmr_eval_ref)},
        "qxrl": {"model_manifest_ref": dict(stub_qxrl_model_ref), "eval_manifest_ref": dict(stub_qxrl_eval_ref), "dataset_manifest_ref": dict(stub_qxrl_dataset_ref)},
        "ml_index": {"index_manifest_ref": dict(ml_index_manifest_ref_stage), "bucket_listing_manifest_ref": dict(bucket_listing_ref_stage)},
    }
    validate_schema(system_manifest_obj, "eudrs_u_system_manifest_v1")
    sroot_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/manifests", artifact_type="eudrs_u_system_manifest_v1", obj=dict(system_manifest_obj))

    # Remaining root tuple refs: minimal DC1/opset JSON stubs (verifier only enforces dc1/opset bindings).
    oroot_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/ontology", artifact_type="ontology_root_stub_v1", obj={"schema_id": "ontology_root_stub_v1", "dc1_id": dc1_id, "opset_id": opset_id})
    kroot_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/manifests", artifact_type="strategy_vm_manifest_stub_v1", obj={"schema_id": "strategy_vm_manifest_stub_v1", "dc1_id": dc1_id, "opset_id": opset_id})
    croot_ref = _write_hashed_bin(root=stage_root, rel_dir="polymath/registry/eudrs_u/capsules", artifact_type="urc_capsule_v1", data=b"\x00" * 16)
    mroot_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/memory", artifact_type="memory_root_stub_v1", obj={"schema_id": "memory_root_stub_v1", "dc1_id": dc1_id, "opset_id": opset_id})
    wroot_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/weights", artifact_type="weights_manifest_v1", obj={"schema_id": "weights_manifest_v1", "dc1_id": dc1_id, "opset_id": opset_id})
    stability_gate_bundle_ref = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/gates", artifact_type="stability_metrics_v1", obj={"schema_id": "stability_metrics_v1", "dc1_id": dc1_id, "opset_id": opset_id})
    determinism_cert_ref_stage = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/certs",
        artifact_type="determinism_cert_v1",
        obj={"schema_id": "determinism_cert_v1", "epoch_u64": int(epoch_u64), "dc1_id": dc1_id, "opset_id": opset_id, "qxrl": dict(det_cert_obj["qxrl"])},
    )
    universality_cert_ref_stage = _write_hashed_json(root=stage_root, rel_dir="polymath/registry/eudrs_u/certs", artifact_type="universality_cert_v1", obj={"schema_id": "universality_cert_v1", "dc1_id": dc1_id, "opset_id": opset_id})

    droot_ref_stage = writer.get_ref_under_stage(artifact_type="dmpl_droot_v1", artifact_id=str(droot_id), ext="json")

    root_tuple_obj = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "sroot": dict(sroot_ref),
        "oroot": dict(oroot_ref),
        "kroot": dict(kroot_ref),
        "croot": dict(croot_ref),
        "droot": dict(droot_ref_stage),
        "mroot": dict(mroot_ref),
        "iroot": dict(index_root_ref),
        "wroot": dict(wroot_ref),
        "stability_gate_bundle": dict(stability_gate_bundle_ref),
        "determinism_cert": dict(determinism_cert_ref_stage),
        "universality_cert": dict(universality_cert_ref_stage),
    }
    validate_schema(root_tuple_obj, "eudrs_u_root_tuple_v1")
    root_tuple_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/roots",
        artifact_type="eudrs_u_root_tuple_v1",
        obj=dict(root_tuple_obj),
    )

    # Active pointer inside staged tree (must reference repo-relpath without staging prefix).
    active_pointer_obj = {
        "schema_id": "active_root_tuple_ref_v1",
        "active_root_tuple": {"artifact_id": root_tuple_ref["artifact_id"], "artifact_relpath": str(root_tuple_ref["artifact_relpath"])},
    }
    _write_canon_json(root=stage_root, relpath="polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json", obj=dict(active_pointer_obj))

    proposed_root_tuple_ref = {
        "artifact_id": str(root_tuple_ref["artifact_id"]),
        "artifact_relpath": _stage_rel_to_state_rel(str(root_tuple_ref["artifact_relpath"])),
    }

    # Summary (entrypoint for RE2 verifier).
    summary_obj = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": dict(proposed_root_tuple_ref),
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": {
            "weights_manifest_ref": dict(weights_ref),
            "ml_index_manifest_ref": dict(ml_index_manifest_ref_evidence),
            "cac_ref": dict(cac_ref),
            "ufc_ref": dict(ufc_ref),
            "cooldown_ledger_ref": dict(cooldown_ref),
            "stability_metrics_ref": dict(stability_ref),
            "determinism_cert_ref": dict(det_cert_ref),
            "universality_cert_ref": dict(uni_cert_ref),
        },
        "dmpl_evidence": {
            "schema_id": "dmpl_evidence_v1",
            "plan_evidence": list(plan_evidence_items_under_state),
            "train_evidence": {
                "schema_id": "dmpl_train_evidence_v1",
                "dmpl_train_run_ref": {"artifact_id": train_run_ref_under_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(train_run_ref_under_stage["artifact_relpath"])},
                "dmpl_train_trace_ref": {"artifact_id": train_trace_ref_under_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(train_trace_ref_under_stage["artifact_relpath"])},
                "dmpl_train_receipt_ref": {"artifact_id": train_receipt_ref_under_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(train_receipt_ref_under_stage["artifact_relpath"])},
            },
            "certificate_refs": {
                "dmpl_cac_pack_ref": {"artifact_id": cac_pack_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(cac_pack_ref_stage["artifact_relpath"])},
                "dmpl_ufc_flow_ref": {"artifact_id": ufc_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(ufc_ref_stage["artifact_relpath"])},
                "dmpl_stab_report_ref": {"artifact_id": stab_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(stab_ref_stage["artifact_relpath"])},
                "dmpl_lasum_report_ref": {"artifact_id": lasum_ref_stage["artifact_id"], "artifact_relpath": _stage_rel_to_state_rel(lasum_ref_stage["artifact_relpath"])},
            },
        },
    }
    validate_schema(summary_obj, "eudrs_u_promotion_summary_v1")
    _write_canon_json(root=state_dir, relpath="eudrs_u/evidence/eudrs_u_promotion_summary_v1.json", obj=dict(summary_obj))

    # Promotion bundle (not used by verifier but used by campaign infrastructure).
    touched = [
        str(root_tuple_ref["artifact_relpath"]),
        "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json",
    ]
    bundle_obj = {
        "schema_version": "eudrs_u_promotion_bundle_v1",
        "activation_key": str(root_tuple_ref["artifact_id"]),
        "touched_paths": sorted(set(touched)),
        "summary_relpath": "eudrs_u/evidence/eudrs_u_promotion_summary_v1.json",
    }
    bundle_raw = gcj1_canon_bytes(bundle_obj)
    bundle_id = sha256_prefixed(bundle_raw)
    bundle_hex = bundle_id.split(":", 1)[1]
    promo_dir = state_dir / "promotion"
    promo_dir.mkdir(parents=True, exist_ok=True)
    (promo_dir / f"sha256_{bundle_hex}.eudrs_u_promotion_bundle_v1.json").write_bytes(bundle_raw)

    return {"status": "OK", "root_tuple_id": str(root_tuple_ref["artifact_id"])}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="eudrs_u_dmpl_phase4_producer_v1")
    p.add_argument("--campaign_pack", required=True)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--producer_kind", required=True)
    return p.parse_args(argv)
