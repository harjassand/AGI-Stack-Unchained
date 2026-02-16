from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cdel.v18_0.eudrs_u.dmpl_config_load_v1 import load_runtime_from_droot_v1
from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_params_bundle_merkle_root_v1
from cdel.v18_0.eudrs_u.dmpl_planner_dcbts_l_v1 import plan_call_v1
from cdel.v18_0.eudrs_u.dmpl_types_v1 import (
    DMPLError,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_RETRIEVAL_DIGEST_MISMATCH,
    DMPL_E_TRACE_CHAIN_BREAK,
)
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
)
from cdel.v18_0.eudrs_u.verify_dmpl_plan_replay_v1 import verify_dmpl_plan_replay_v1
from cdel.v18_0.omega_common_v1 import Q32_ONE


_U32LE = struct.Struct("<I")
_TRACE_PREFIX = b"DMPL/TRACE/v1\x00"


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _sha256_id(data: bytes) -> str:
    return f"sha256:{_sha25632(data).hex()}"


def _sha256_id_to_bytes32(sha256_id: str) -> bytes:
    if not isinstance(sha256_id, str) or not sha256_id.startswith("sha256:") or len(sha256_id) != (len("sha256:") + 64):
        raise AssertionError(f"bad sha256 id: {sha256_id!r}")
    return bytes.fromhex(sha256_id.split(":", 1)[1])


def _write_json_artifact(base_dir: Path, rel_dir: str, artifact_type: str, obj: dict) -> dict[str, str]:
    raw = gcj1_canon_bytes(obj)
    aid = sha256_prefixed(raw)
    hex64 = aid.split(":", 1)[1]
    path = (base_dir / rel_dir / f"sha256_{hex64}.{artifact_type}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"artifact_id": aid, "artifact_relpath": path.relative_to(base_dir).as_posix()}


def _write_bin_artifact(base_dir: Path, rel_dir: str, artifact_type: str, raw: bytes) -> dict[str, str]:
    b = bytes(raw)
    aid = sha256_prefixed(b)
    hex64 = aid.split(":", 1)[1]
    path = (base_dir / rel_dir / f"sha256_{hex64}.{artifact_type}.bin").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
    return {"artifact_id": aid, "artifact_relpath": path.relative_to(base_dir).as_posix()}


def _dmpl_tensor_bin(*, dims_u32: list[int], values_i64: list[int]) -> bytes:
    out = bytearray()
    out += b"DMPLTQ32"
    out += struct.pack("<II", 1, int(len(dims_u32)) & 0xFFFFFFFF)
    for d in dims_u32:
        out += struct.pack("<I", int(d) & 0xFFFFFFFF)
    for v in values_i64:
        out += struct.pack("<q", int(v))
    return bytes(out)


class _MultiRootResolverV1:
    def __init__(self, roots: list[Path]) -> None:
        self._roots = [Path(r).resolve() for r in roots]

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        aid = str(artifact_id).strip()
        at = str(artifact_type).strip()
        ex = str(ext).strip()
        if not aid.startswith("sha256:") or len(aid) != len("sha256:") + 64:
            raise AssertionError(f"bad artifact_id: {aid!r}")
        if ex not in {"json", "bin"} or not at:
            raise AssertionError("bad resolver request")
        hex64 = aid.split(":", 1)[1]
        filename = f"sha256_{hex64}.{at}.{ex}"
        matches: list[Path] = []
        for root in self._roots:
            matches.extend([p for p in root.rglob(filename) if p.is_file()])
        matches = sorted(matches, key=lambda p: p.as_posix())
        if len(matches) != 1:
            raise AssertionError(f"expected exactly 1 match for {filename}, got {len(matches)}")
        return matches[0].read_bytes()


class _FSArtifactWriterV1:
    def __init__(self, out_dir: Path) -> None:
        self._out = Path(out_dir).resolve()
        self._out.mkdir(parents=True, exist_ok=True)

    def write_json_artifact(self, artifact_type: str, obj: Any) -> str:
        raw = gcj1_canon_bytes(obj)
        aid = sha256_prefixed(raw)
        hex64 = aid.split(":", 1)[1]
        path = self._out / f"sha256_{hex64}.{str(artifact_type)}.json"
        if path.exists() and path.read_bytes() != raw:
            raise AssertionError("hash collision for json artifact")
        path.write_bytes(raw)
        return aid

    def write_bin_artifact(self, artifact_type: str, raw: bytes) -> str:
        b = bytes(raw)
        aid = sha256_prefixed(b)
        hex64 = aid.split(":", 1)[1]
        path = self._out / f"sha256_{hex64}.{str(artifact_type)}.bin"
        if path.exists() and path.read_bytes() != b:
            raise AssertionError("hash collision for bin artifact")
        path.write_bytes(b)
        return aid


@dataclass(frozen=True, slots=True)
class _Env:
    base_dir: Path
    out_dir: Path
    resolver: _MultiRootResolverV1
    droot_id: str
    modelpack_id: str
    opset_id: str
    plan_query_obj: dict[str, Any]


def _build_env(tmp_path: Path) -> _Env:
    base_dir = (tmp_path / "registry").resolve()
    out_dir = (tmp_path / "out").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # DMPL dims.
    d_u32 = 2
    p_u32 = 4
    embed_dim_u32 = 2

    # Base tensors (all zeros).
    A0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32, d_u32], values_i64=[0] * (d_u32 * d_u32)))
    B0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32, p_u32], values_i64=[0] * (d_u32 * p_u32)))
    Wg_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[embed_dim_u32, d_u32], values_i64=[0] * (embed_dim_u32 * d_u32)))
    b0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32], values_i64=[0] * d_u32))
    w0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[d_u32], values_i64=[0] * d_u32))
    v0_ref = _write_bin_artifact(base_dir, "polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1", _dmpl_tensor_bin(dims_u32=[1], values_i64=[0]))

    # Concept shard + embedding (retrieval payload points at this shard id).
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
        "max_trace_bytes_u32": 10_000_000,
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
    caps_digest = sha256_prefixed(gcj1_canon_bytes(caps_obj))

    config_obj = {
        "schema_id": "dmpl_config_v1",
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "enabled_b": True,
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

    # Resolver must be able to load from both registry and outputs.
    resolver = _MultiRootResolverV1([out_dir, base_dir])
    return _Env(
        base_dir=base_dir,
        out_dir=out_dir,
        resolver=resolver,
        droot_id=droot_ref["artifact_id"],
        modelpack_id=modelpack_id,
        opset_id=opset_id,
        plan_query_obj=plan_query_obj,
    )


def _load_json_from_out_dir(out_dir: Path, *, artifact_id: str, artifact_type: str) -> dict[str, Any]:
    hex64 = str(artifact_id).split(":", 1)[1]
    path = out_dir / f"sha256_{hex64}.{artifact_type}.json"
    obj = gcj1_loads_and_verify_canonical(path.read_bytes())
    assert isinstance(obj, dict)
    return dict(obj)


def _parse_trace_stream(stream: bytes) -> list[bytes]:
    off = 0
    out: list[bytes] = []
    while off < len(stream):
        (n,) = _U32LE.unpack_from(stream, off)
        off += 4
        rec = bytes(stream[off : off + int(n)])
        off += int(n)
        out.append(rec)
    assert off == len(stream)
    return out


def _build_trace_stream(records: list[bytes]) -> bytes:
    out = bytearray()
    for rec in records:
        out += _U32LE.pack(len(rec) & 0xFFFFFFFF)
        out += bytes(rec)
    return bytes(out)


def _trace_chain_final_id(*, plan_query_obj: dict[str, Any], modelpack_id: str, opset_id: str, record_bytes: list[bytes]) -> str:
    pq_id = sha256_prefixed(gcj1_canon_bytes(plan_query_obj))
    h = _sha25632(_TRACE_PREFIX + _sha256_id_to_bytes32(pq_id) + _sha256_id_to_bytes32(modelpack_id) + str(opset_id).encode("utf-8"))
    for rec in record_bytes:
        ri = _sha25632(rec)
        h = _sha25632(h + ri)
    return f"sha256:{h.hex()}"


def test_dmpl_phase3_plan_replay_verifier_positive(tmp_path: Path) -> None:
    env = _build_env(tmp_path)

    runtime = load_runtime_from_droot_v1(droot_id=env.droot_id, resolver=env.resolver)
    writer = _FSArtifactWriterV1(env.out_dir)
    plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(env.plan_query_obj), resolver=env.resolver, artifact_writer=writer)

    trace_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.rollout_trace_id), artifact_type="dmpl_rollout_trace_v1")
    receipt_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.action_receipt_id), artifact_type="dmpl_action_receipt_v1")

    verify_dmpl_plan_replay_v1(
        plan_query_obj=dict(env.plan_query_obj),
        rollout_trace_obj=dict(trace_obj),
        action_receipt_obj=dict(receipt_obj),
        resolver=env.resolver,
    )


def test_dmpl_phase3_plan_replay_verifier_detects_retrieval_digest_mismatch(tmp_path: Path) -> None:
    env = _build_env(tmp_path)

    runtime = load_runtime_from_droot_v1(droot_id=env.droot_id, resolver=env.resolver)
    writer = _FSArtifactWriterV1(env.out_dir)
    plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(env.plan_query_obj), resolver=env.resolver, artifact_writer=writer)

    trace_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.rollout_trace_id), artifact_type="dmpl_rollout_trace_v1")
    receipt_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.action_receipt_id), artifact_type="dmpl_action_receipt_v1")

    # Load the single trace stream (small tests => one chunk).
    assert trace_obj["chunks"], "expected at least one chunk"
    chunk0 = dict(trace_obj["chunks"][0])
    chunk0_id = str(chunk0["chunk_bin_id"])
    chunk0_bytes = env.resolver.load_artifact_bytes(artifact_id=chunk0_id, artifact_type="dmpl_rollout_trace_chunk_v1", ext="bin")
    records = _parse_trace_stream(bytes(chunk0_bytes))
    assert records, "expected at least one record"

    # Tamper: change retrieval_trace_root in the first record, keep the trace internally consistent.
    rec0_obj = gcj1_loads_and_verify_canonical(records[0])
    assert isinstance(rec0_obj, dict)
    rec0_obj["retrieval_trace_root"] = "sha256:" + ("00" * 32)
    records[0] = gcj1_canon_bytes(rec0_obj)

    tampered_stream = _build_trace_stream(records)
    tamper_dir = (tmp_path / "tampered").resolve()
    tamper_dir.mkdir(parents=True, exist_ok=True)
    chunk0_new_id = sha256_prefixed(tampered_stream)
    (tamper_dir / f"sha256_{chunk0_new_id.split(':',1)[1]}.dmpl_rollout_trace_chunk_v1.bin").write_bytes(tampered_stream)

    # Update manifest (chunks + roots + trace chain final) and receipt rollout_trace_id to stay link-consistent.
    trace_obj2 = dict(trace_obj)
    trace_obj2["chunks"] = [{"chunk_index_u32": 0, "chunk_bin_id": chunk0_new_id, "chunk_bytes_u32": len(tampered_stream)}]
    # chunks_merkle_root for 1 chunk: compute from chunk hash32 list.
    from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_chunk_merkle_root_v1

    root32 = compute_chunk_merkle_root_v1([_sha256_id_to_bytes32(chunk0_new_id)])
    trace_obj2["chunks_merkle_root"] = f"sha256:{bytes(root32).hex()}"
    trace_obj2["trace_chain_final"] = _trace_chain_final_id(plan_query_obj=env.plan_query_obj, modelpack_id=env.modelpack_id, opset_id=env.opset_id, record_bytes=records)

    rollout_trace_id2 = sha256_prefixed(gcj1_canon_bytes(trace_obj2))
    receipt_obj2 = dict(receipt_obj)
    receipt_obj2["rollout_trace_id"] = rollout_trace_id2

    tamper_resolver = _MultiRootResolverV1([tamper_dir, env.out_dir, env.base_dir])
    with pytest.raises(DMPLError) as excinfo:
        verify_dmpl_plan_replay_v1(
            plan_query_obj=dict(env.plan_query_obj),
            rollout_trace_obj=trace_obj2,
            action_receipt_obj=receipt_obj2,
            resolver=tamper_resolver,
        )
    assert excinfo.value.reason_code == DMPL_E_RETRIEVAL_DIGEST_MISMATCH


def test_dmpl_phase3_plan_replay_verifier_detects_trace_chain_break(tmp_path: Path) -> None:
    env = _build_env(tmp_path)

    runtime = load_runtime_from_droot_v1(droot_id=env.droot_id, resolver=env.resolver)
    writer = _FSArtifactWriterV1(env.out_dir)
    plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(env.plan_query_obj), resolver=env.resolver, artifact_writer=writer)

    trace_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.rollout_trace_id), artifact_type="dmpl_rollout_trace_v1")
    receipt_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.action_receipt_id), artifact_type="dmpl_action_receipt_v1")

    assert trace_obj["chunks"], "expected at least one chunk"
    chunk0 = dict(trace_obj["chunks"][0])
    chunk0_id = str(chunk0["chunk_bin_id"])
    chunk0_bytes = env.resolver.load_artifact_bytes(artifact_id=chunk0_id, artifact_type="dmpl_rollout_trace_chunk_v1", ext="bin")
    records = _parse_trace_stream(bytes(chunk0_bytes))
    assert records, "expected at least one record"

    # Flip one byte deterministically: change the first occurrence of '\"depth_u32\":1' to '\"depth_u32\":2'.
    idx = records[0].find(b"\"depth_u32\":1")
    assert idx >= 0, "expected depth_u32 field in record"
    pos = idx + len(b"\"depth_u32\":")
    assert records[0][pos : pos + 1] == b"1"
    records[0] = records[0][:pos] + b"2" + records[0][pos + 1 :]

    tampered_stream = _build_trace_stream(records)
    tamper_dir = (tmp_path / "tampered_chain").resolve()
    tamper_dir.mkdir(parents=True, exist_ok=True)
    chunk0_new_id = sha256_prefixed(tampered_stream)
    (tamper_dir / f"sha256_{chunk0_new_id.split(':',1)[1]}.dmpl_rollout_trace_chunk_v1.bin").write_bytes(tampered_stream)

    # Update chunks + chunks_merkle_root, but keep trace_chain_final unchanged => should fail DMPL_E_TRACE_CHAIN_BREAK.
    trace_obj2 = dict(trace_obj)
    trace_obj2["chunks"] = [{"chunk_index_u32": 0, "chunk_bin_id": chunk0_new_id, "chunk_bytes_u32": len(tampered_stream)}]
    from cdel.v18_0.eudrs_u.dmpl_merkle_v1 import compute_chunk_merkle_root_v1

    root32 = compute_chunk_merkle_root_v1([_sha256_id_to_bytes32(chunk0_new_id)])
    trace_obj2["chunks_merkle_root"] = f"sha256:{bytes(root32).hex()}"

    rollout_trace_id2 = sha256_prefixed(gcj1_canon_bytes(trace_obj2))
    receipt_obj2 = dict(receipt_obj)
    receipt_obj2["rollout_trace_id"] = rollout_trace_id2

    tamper_resolver = _MultiRootResolverV1([tamper_dir, env.out_dir, env.base_dir])
    with pytest.raises(DMPLError) as excinfo:
        verify_dmpl_plan_replay_v1(
            plan_query_obj=dict(env.plan_query_obj),
            rollout_trace_obj=trace_obj2,
            action_receipt_obj=receipt_obj2,
            resolver=tamper_resolver,
        )
    assert excinfo.value.reason_code == DMPL_E_TRACE_CHAIN_BREAK


def test_dmpl_phase3_plan_replay_verifier_detects_receipt_tamper(tmp_path: Path) -> None:
    env = _build_env(tmp_path)

    runtime = load_runtime_from_droot_v1(droot_id=env.droot_id, resolver=env.resolver)
    writer = _FSArtifactWriterV1(env.out_dir)
    plan_result = plan_call_v1(runtime=runtime, plan_query_obj=dict(env.plan_query_obj), resolver=env.resolver, artifact_writer=writer)

    trace_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.rollout_trace_id), artifact_type="dmpl_rollout_trace_v1")
    receipt_obj = _load_json_from_out_dir(env.out_dir, artifact_id=str(plan_result.action_receipt_id), artifact_type="dmpl_action_receipt_v1")

    # Tamper receipt: change depth without updating proof_digest.
    receipt_obj2 = dict(receipt_obj)
    tb = dict(receipt_obj2.get("tie_break_proof", {}))
    ok = dict(tb.get("ordering_keys", [{}])[0])
    ok["depth_u32"] = int(ok.get("depth_u32", 0)) + 1
    tb["ordering_keys"] = [ok]
    receipt_obj2["tie_break_proof"] = tb

    with pytest.raises(DMPLError) as excinfo:
        verify_dmpl_plan_replay_v1(
            plan_query_obj=dict(env.plan_query_obj),
            rollout_trace_obj=dict(trace_obj),
            action_receipt_obj=receipt_obj2,
            resolver=env.resolver,
        )
    assert excinfo.value.reason_code == DMPL_E_HASH_MISMATCH
