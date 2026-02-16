from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_eudrs_u_promotion_v1 import verify as verify_promotion
from cdel.v18_0.omega_common_v1 import OmegaV18Error

_DMPL_MERKLE_LEAF_PREFIX = b"DMPL/MERKLE/LEAF/v1\x00"
_DMPL_MERKLE_NODE_PREFIX = b"DMPL/MERKLE/NODE/v1\x00"
_DMPL_TENSOR_MAGIC = b"DMPLTQ32"


def _write_hashed_json_v1(*, out_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, str]:
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(raw)
    return path, digest


def _write_hashed_bin_v1(*, out_dir: Path, suffix: str, data: bytes) -> tuple[Path, str]:
    digest = sha256_prefixed(bytes(data))
    hex64 = digest.split(":", 1)[1]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(bytes(data))
    return path, digest


def _dmpl_params_bundle_merkle_root_v1(*, tensors: list[dict[str, Any]]) -> str:
    leaf_hashes: list[bytes] = []
    for row in tensors:
        name = row["name"]
        if not isinstance(name, str) or not name:
            raise AssertionError("invalid tensor name")
        if "\x00" in name:
            raise AssertionError("NUL in tensor name")
        tbid = str(row["tensor_bin_id"])
        if not tbid.startswith("sha256:") or len(tbid) != len("sha256:") + 64:
            raise AssertionError("invalid tensor_bin_id")
        digest32 = bytes.fromhex(tbid.split(":", 1)[1])
        leaf_hashes.append(hashlib.sha256(_DMPL_MERKLE_LEAF_PREFIX + name.encode("utf-8") + b"\x00" + digest32).digest())
    if not leaf_hashes:
        raise AssertionError("empty tensors")
    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        nxt: list[bytes] = []
        for i in range(0, len(level), 2):
            nxt.append(hashlib.sha256(_DMPL_MERKLE_NODE_PREFIX + level[i] + level[i + 1]).digest())
        level = nxt
    return f"sha256:{level[0].hex()}"


def _write_min_phase1_schemas(schema_dir: Path) -> None:
    schema_dir.mkdir(parents=True, exist_ok=True)

    (schema_dir / "eudrs_u_artifact_ref_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "artifact_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "artifact_relpath": {"type": "string", "minLength": 1},
                },
                "required": ["artifact_id", "artifact_relpath"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (schema_dir / "eudrs_u_root_tuple_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/eudrs_u_root_tuple_v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_id": {"const": "eudrs_u_root_tuple_v1"},
                    "epoch_u64": {"type": "integer", "minimum": 0},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                    "sroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "oroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "kroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "croot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "droot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "mroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "iroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "wroot": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "stability_gate_bundle": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "determinism_cert": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "universality_cert": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                },
                "required": [
                    "schema_id",
                    "epoch_u64",
                    "dc1_id",
                    "opset_id",
                    "sroot",
                    "oroot",
                    "kroot",
                    "croot",
                    "droot",
                    "mroot",
                    "iroot",
                    "wroot",
                    "stability_gate_bundle",
                    "determinism_cert",
                    "universality_cert",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Minimal DMPL schemas for Phase 1 promotion verification.
    (schema_dir / "dmpl_droot_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/dmpl_droot_v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_id": {"const": "dmpl_droot_v1"},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                    "dmpl_config_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "froot": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "vroot": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "caps_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "opset_semantics_id": {"type": "string"},
                },
                "required": ["schema_id", "dc1_id", "opset_id", "dmpl_config_id", "froot", "vroot", "caps_digest", "opset_semantics_id"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (schema_dir / "dmpl_config_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/dmpl_config_v1",
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "schema_id": {"const": "dmpl_config_v1"},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                    "enabled_b": {"type": "boolean"},
                    "active_modelpack_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "fparams_bundle_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "vparams_bundle_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "caps": {"type": "object"},
                    "retrieval_spec": {"type": "object"},
                },
                "required": [
                    "schema_id",
                    "dc1_id",
                    "opset_id",
                    "enabled_b",
                    "active_modelpack_id",
                    "fparams_bundle_id",
                    "vparams_bundle_id",
                    "caps",
                    "retrieval_spec",
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (schema_dir / "dmpl_modelpack_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/dmpl_modelpack_v1",
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "schema_id": {"const": "dmpl_modelpack_v1"},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                },
                "required": ["schema_id", "dc1_id", "opset_id"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (schema_dir / "dmpl_params_bundle_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/dmpl_params_bundle_v1",
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "schema_id": {"const": "dmpl_params_bundle_v1"},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                    "bundle_kind": {"type": "string", "enum": ["F", "V"]},
                    "modelpack_id": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "tensors": {"type": "array"},
                    "merkle_root": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                },
                "required": ["schema_id", "dc1_id", "opset_id", "bundle_kind", "modelpack_id", "tensors", "merkle_root"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    (schema_dir / "eudrs_u_system_manifest_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/eudrs_u_system_manifest_v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_id": {"const": "eudrs_u_system_manifest_v1"},
                    "epoch_u64": {"type": "integer", "minimum": 0},
                    "dc1_id": {"type": "string", "const": "dc1:q32_v1"},
                    "opset_id": {"type": "string"},
                    "qxwmr": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "world_model_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                            "eval_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                        },
                        "required": ["world_model_manifest_ref", "eval_manifest_ref"],
                    },
                    "qxrl": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "model_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                            "eval_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                            "dataset_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                        },
                        "required": ["model_manifest_ref", "eval_manifest_ref", "dataset_manifest_ref"],
                    },
                    "ml_index": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "index_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                            "bucket_listing_manifest_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                        },
                        "required": ["index_manifest_ref", "bucket_listing_manifest_ref"],
                    },
                },
                "required": ["schema_id", "epoch_u64", "dc1_id", "opset_id", "qxwmr", "qxrl", "ml_index"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Minimal summary schema: verifier code enforces required keys separately.
    (schema_dir / "eudrs_u_promotion_summary_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/eudrs_u_promotion_summary_v1",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_id": {"const": "eudrs_u_promotion_summary_v1"},
                    "proposed_root_tuple_ref": {"$ref": "https://genesis.engine/specs/v18_0/eudrs_u_artifact_ref_v1"},
                    "staged_registry_tree_relpath": {"type": "string", "minLength": 1},
                    "evidence": {"type": "object"},
                    "dmpl_evidence": {"type": "object"},
                },
                "required": ["schema_id", "proposed_root_tuple_ref", "staged_registry_tree_relpath", "evidence"],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _mk_evidence_refs(*, state_dir: Path) -> tuple[Path, dict[str, Any]]:
    evidence_dir = state_dir / "eudrs_u" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def _ev(schema_id: str, suffix: str) -> dict[str, str]:
        p, d = _write_hashed_json_v1(out_dir=evidence_dir, suffix=suffix, payload={"schema_id": schema_id})
        return {"artifact_id": d, "artifact_relpath": p.relative_to(state_dir).as_posix()}

    evidence = {
        "weights_manifest_ref": _ev("weights_manifest_v1", "weights_manifest_v1.json"),
        "ml_index_manifest_ref": _ev("ml_index_manifest_v1", "ml_index_manifest_v1.json"),
        "cac_ref": _ev("cac_v1", "cac_v1.json"),
        "ufc_ref": _ev("ufc_v1", "ufc_v1.json"),
        "cooldown_ledger_ref": _ev("cooldown_ledger_v1", "cooldown_ledger_v1.json"),
        "stability_metrics_ref": _ev("stability_metrics_v1", "stability_metrics_v1.json"),
        "determinism_cert_ref": _ev("determinism_cert_v1", "determinism_cert_v1.json"),
        "universality_cert_ref": _ev("universality_cert_v1", "universality_cert_v1.json"),
    }
    return evidence_dir, evidence


def _mk_min_staged_root_tuple(
    *,
    state_dir: Path,
    epoch_u64: int,
    dc1_id: str,
    opset_id: str,
    system_manifest_schema_id: str = "eudrs_u_system_manifest_v1",
    system_manifest_epoch_u64: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    staged = state_dir / "eudrs_u" / "staged_registry_tree"
    staged.mkdir(parents=True, exist_ok=True)
    reg = staged / "polymath/registry/eudrs_u"

    def _mk_manifest(name: str) -> dict[str, str]:
        p, d = _write_hashed_json_v1(
            out_dir=reg / "manifests",
            suffix=f"{name}.json",
            payload={"schema_id": name, "dc1_id": dc1_id, "opset_id": opset_id},
        )
        return {"artifact_id": d, "artifact_relpath": p.relative_to(staged).as_posix()}

    # iroot stays stable across epochs in these Phase 1 tests to avoid triggering
    # Phase 2+ index verification logic.
    iroot = _mk_manifest("ml_index_root_ptr_v1")

    sm_epoch = epoch_u64 if system_manifest_epoch_u64 is None else int(system_manifest_epoch_u64)
    zero_ref = {
        "artifact_id": "sha256:" + ("00" * 32),
        "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("00" * 64) + ".placeholder.json",
    }
    sm_payload: dict[str, Any] = {
        "schema_id": system_manifest_schema_id,
        "epoch_u64": sm_epoch,
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "qxwmr": {"world_model_manifest_ref": zero_ref, "eval_manifest_ref": zero_ref},
        "qxrl": {"model_manifest_ref": zero_ref, "eval_manifest_ref": zero_ref, "dataset_manifest_ref": zero_ref},
        "ml_index": {"index_manifest_ref": zero_ref, "bucket_listing_manifest_ref": zero_ref},
    }
    sm_path, sm_digest = _write_hashed_json_v1(out_dir=reg / "manifests", suffix="eudrs_u_system_manifest_v1.json", payload=sm_payload)
    sroot = {"artifact_id": sm_digest, "artifact_relpath": sm_path.relative_to(staged).as_posix()}

    # DMPL (Phase 1): minimal disabled config + droot binding.
    dmpl_dir = reg / "dmpl"

    # Minimal tensor binary: shape [1], value 0.
    tensor_bytes = _DMPL_TENSOR_MAGIC + struct.pack("<II", 1, 1) + struct.pack("<I", 1) + struct.pack("<q", 0)
    tensor_path, tensor_id = _write_hashed_bin_v1(out_dir=dmpl_dir / "tensors", suffix="dmpl_tensor_q32_v1.bin", data=tensor_bytes)
    del tensor_path

    # Minimal modelpack (must satisfy Phase 3 opset verifier pins).
    modelpack_path, modelpack_id = _write_hashed_json_v1(
        out_dir=dmpl_dir / "modelpacks",
        suffix="dmpl_modelpack_v1.json",
        payload={
            "schema_id": "dmpl_modelpack_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "forward_arch_id": "dmpl_linear_pwl_v1",
            "value_arch_id": "dmpl_linear_v1",
            "activation_id": "hard_tanh_q32_v1",
            "gating_arch_id": "linear_gate_v1",
            "patch_policy": {"allowed_patch_types": ["matrix_patch", "lowrank_patch"], "vm_patch_allowed_b": False},
        },
    )
    del modelpack_path

    tensors = [{"name": "t0", "shape_u32": [1], "tensor_bin_id": tensor_id}]
    f_merkle = _dmpl_params_bundle_merkle_root_v1(tensors=tensors)
    v_merkle = _dmpl_params_bundle_merkle_root_v1(tensors=tensors)

    fparams_path, fparams_id = _write_hashed_json_v1(
        out_dir=dmpl_dir / "params",
        suffix="dmpl_params_bundle_v1.json",
        payload={
            "schema_id": "dmpl_params_bundle_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "bundle_kind": "F",
            "modelpack_id": modelpack_id,
            "tensors": tensors,
            "merkle_root": f_merkle,
        },
    )
    vparams_path, vparams_id = _write_hashed_json_v1(
        out_dir=dmpl_dir / "params",
        suffix="dmpl_params_bundle_v1.json",
        payload={
            "schema_id": "dmpl_params_bundle_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "bundle_kind": "V",
            "modelpack_id": modelpack_id,
            "tensors": tensors,
            "merkle_root": v_merkle,
        },
    )
    del fparams_path, vparams_path

    caps_obj = {"K_ctx_u32": 0, "K_g_u32": 0, "max_concept_bytes_per_step_u32": 0, "max_retrieval_bytes_u32": 0, "max_retrieval_ops_u64": 0}
    caps_digest = sha256_prefixed(gcj1_canon_bytes(caps_obj))

    config_path, config_id = _write_hashed_json_v1(
        out_dir=dmpl_dir / "configs",
        suffix="dmpl_config_v1.json",
        payload={
            "schema_id": "dmpl_config_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "enabled_b": False,
            "active_modelpack_id": modelpack_id,
            "fparams_bundle_id": fparams_id,
            "vparams_bundle_id": vparams_id,
            "caps": caps_obj,
            "retrieval_spec": {
                "ml_index_manifest_id": "sha256:" + ("00" * 32),
                "key_fn_id": "dmpl_key_v1",
                "score_fn_id": "ml_index_v1_default",
                "tie_rule_id": "score_desc_id_asc",
                "scan_cap_per_bucket_u32": 1,
                "K_ctx_u32": 0,
            },
            "gating_spec": {
                "normalize_weights_b": False,
                "epsilon_q32": {"q": 1},
                "pwl_pos_id": "pwl_pos_v1",
                "inv_q32_id": "",
                "inverse_head_enabled_b": False,
                "rev_err_threshold_q32": {"q": 0},
                "theta_cac_lb_q32": {"q": 0},
                "stab_thresholds": {"G0": {"q": 0}, "G1": {"q": 0}, "G2": {"q": 0}, "G3": {"q": 0}, "G4": {"q": 0}, "G5": {"q": 0}},
            },
            "planner_spec": {
                "algorithm_id": "dcbts_l_v1",
                "ladder_policy": {"ell_hi_u32": 0, "ell_lo_u32": 0, "refine_enabled_b": False, "refine_budget_u32": 0, "refine_per_step_budget_u32": 0},
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
            "objective_spec": {"gamma_q32": {"q": 0}, "reward_proxy_id": "ufc_proxy_v1", "ufc_objective_id": "ufc_v1_primary"},
        },
    )
    del config_path

    droot_path, droot_id = _write_hashed_json_v1(
        out_dir=dmpl_dir / "roots",
        suffix="dmpl_droot_v1.json",
        payload={
            "schema_id": "dmpl_droot_v1",
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "dmpl_config_id": config_id,
            "froot": f_merkle,
            "vroot": v_merkle,
            "caps_digest": caps_digest,
            "opset_semantics_id": opset_id,
        },
    )
    droot = {"artifact_id": droot_id, "artifact_relpath": droot_path.relative_to(staged).as_posix()}

    root_tuple = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": dc1_id,
        "opset_id": opset_id,
        "sroot": sroot,
        "oroot": _mk_manifest("oroot_ptr_v1"),
        "kroot": _mk_manifest("kroot_ptr_v1"),
        "croot": _mk_manifest("croot_ptr_v1"),
        "droot": droot,
        "mroot": _mk_manifest("mroot_ptr_v1"),
        "iroot": iroot,
        "wroot": _mk_manifest("wroot_ptr_v1"),
        "stability_gate_bundle": _mk_manifest("stability_gate_bundle_v1"),
        "determinism_cert": _mk_manifest("determinism_cert_v1"),
        "universality_cert": _mk_manifest("universality_cert_v1"),
    }

    rt_path, rt_digest = _write_hashed_json_v1(out_dir=reg / "roots", suffix="eudrs_u_root_tuple_v1.json", payload=root_tuple)
    proposed_root_tuple_ref = {
        "artifact_id": rt_digest,
        "artifact_relpath": rt_path.relative_to(state_dir).as_posix(),
    }

    # Staged activation pointer must reference the target path (without staging prefix).
    pointer_path = reg / "active/active_root_tuple_ref_v1.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": rt_digest,
                "artifact_relpath": rt_path.relative_to(staged).as_posix(),
            },
        },
    )

    return root_tuple, proposed_root_tuple_ref


def test_promotion_epoch_plus_one_and_sroot_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Candidate state_dir (epoch 1).
    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    _new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(state_dir=state_dir, epoch_u64=1, dc1_id=dc1_id, opset_id=opset_id)

    # Install previous active root tuple (epoch 0) in the repo root.
    prev_state_dir = tmp_path / "prev_state"
    prev_state_dir.mkdir(parents=True, exist_ok=True)
    prev_rt, _prev_proposed = _mk_min_staged_root_tuple(state_dir=prev_state_dir, epoch_u64=0, dc1_id=dc1_id, opset_id=opset_id)
    # Copy the root tuple artifact into the repo's canonical location.
    prev_rt_ref = prev_rt["iroot"]  # only used for stable iroot id; keep linter happy
    del prev_rt_ref

    # The helper wrote the previous root tuple under prev_state_dir staging; re-write it under repo_root roots.
    rt_payload = dict(prev_rt)
    rt_payload["epoch_u64"] = 0
    repo_roots_dir = repo_root / "polymath/registry/eudrs_u/roots"
    repo_rt_path, repo_rt_digest = _write_hashed_json_v1(out_dir=repo_roots_dir, suffix="eudrs_u_root_tuple_v1.json", payload=rt_payload)

    pointer_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": repo_rt_digest,
                "artifact_relpath": repo_rt_path.relative_to(repo_root).as_posix(),
            },
        },
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    evidence_dir = state_dir / "eudrs_u/evidence"
    _write_hashed_json_v1(out_dir=evidence_dir, suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    assert verify_promotion(state_dir, mode="full", repo_root_override=repo_root) == "VALID"


def test_promotion_rejects_epoch_not_plus_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Candidate epoch 2, but previous is epoch 0 -> should reject.
    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    _new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(state_dir=state_dir, epoch_u64=2, dc1_id=dc1_id, opset_id=opset_id)

    # Previous active epoch 0.
    prev_path, prev_digest = _write_hashed_json_v1(
        out_dir=repo_root / "polymath/registry/eudrs_u/roots",
        suffix="eudrs_u_root_tuple_v1.json",
        payload={
            "schema_id": "eudrs_u_root_tuple_v1",
            "epoch_u64": 0,
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "sroot": evidence["weights_manifest_ref"],
            "oroot": evidence["weights_manifest_ref"],
            "kroot": evidence["weights_manifest_ref"],
            "croot": evidence["weights_manifest_ref"],
            "droot": evidence["weights_manifest_ref"],
            "mroot": evidence["weights_manifest_ref"],
            "iroot": evidence["weights_manifest_ref"],
            "wroot": evidence["weights_manifest_ref"],
            "stability_gate_bundle": evidence["weights_manifest_ref"],
            "determinism_cert": evidence["weights_manifest_ref"],
            "universality_cert": evidence["weights_manifest_ref"],
        },
    )
    pointer_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": prev_digest,
                "artifact_relpath": prev_path.relative_to(repo_root).as_posix(),
            },
        },
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    _write_hashed_json_v1(out_dir=state_dir / "eudrs_u/evidence", suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    with pytest.raises(OmegaV18Error):
        verify_promotion(state_dir, mode="full", repo_root_override=repo_root)


def test_promotion_replay_mode_is_head_agnostic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(
        state_dir=state_dir,
        epoch_u64=1,
        dc1_id=dc1_id,
        opset_id=opset_id,
    )

    # Simulate historical replay after this tuple is already active.
    active_rt_path, active_rt_digest = _write_hashed_json_v1(
        out_dir=repo_root / "polymath/registry/eudrs_u/roots",
        suffix="eudrs_u_root_tuple_v1.json",
        payload=dict(new_root_tuple),
    )
    pointer_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": active_rt_digest,
                "artifact_relpath": active_rt_path.relative_to(repo_root).as_posix(),
            },
        },
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    _write_hashed_json_v1(out_dir=state_dir / "eudrs_u/evidence", suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    assert verify_promotion(state_dir, mode="replay", repo_root_override=repo_root) == "VALID"
    with pytest.raises(OmegaV18Error):
        verify_promotion(state_dir, mode="full", repo_root_override=repo_root)


def test_promotion_rejects_sroot_not_system_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    _new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(
        state_dir=state_dir,
        epoch_u64=0,
        dc1_id=dc1_id,
        opset_id=opset_id,
        system_manifest_schema_id="not_system_manifest_v1",
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    _write_hashed_json_v1(out_dir=state_dir / "eudrs_u/evidence", suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    with pytest.raises(OmegaV18Error):
        verify_promotion(state_dir, mode="full", repo_root_override=repo_root)


def test_promotion_rejects_system_manifest_epoch_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    _new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(
        state_dir=state_dir,
        epoch_u64=0,
        dc1_id=dc1_id,
        opset_id=opset_id,
        system_manifest_epoch_u64=1,
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
    }
    _write_hashed_json_v1(out_dir=state_dir / "eudrs_u/evidence", suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    with pytest.raises(OmegaV18Error):
        verify_promotion(state_dir, mode="full", repo_root_override=repo_root)


def test_promotion_rejects_dmpl_evidence_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis/schema/v18_0"
    _write_min_phase1_schemas(schema_dir)

    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    dc1_id = "dc1:q32_v1"
    opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Candidate state_dir (epoch 1) with DMPL disabled in config, but includes dmpl_evidence.plan_evidence.
    state_dir = tmp_path / "state"
    _evidence_dir, evidence = _mk_evidence_refs(state_dir=state_dir)
    _new_root_tuple, proposed_root_tuple_ref = _mk_min_staged_root_tuple(state_dir=state_dir, epoch_u64=1, dc1_id=dc1_id, opset_id=opset_id)

    # Previous active root tuple (epoch 0) in repo_root, keeping iroot stable to skip index verification.
    prev_path, prev_digest = _write_hashed_json_v1(
        out_dir=repo_root / "polymath/registry/eudrs_u/roots",
        suffix="eudrs_u_root_tuple_v1.json",
        payload={
            "schema_id": "eudrs_u_root_tuple_v1",
            "epoch_u64": 0,
            "dc1_id": dc1_id,
            "opset_id": opset_id,
            "sroot": evidence["weights_manifest_ref"],
            "oroot": evidence["weights_manifest_ref"],
            "kroot": evidence["weights_manifest_ref"],
            "croot": evidence["weights_manifest_ref"],
            "droot": evidence["weights_manifest_ref"],
            "mroot": evidence["weights_manifest_ref"],
            "iroot": evidence["weights_manifest_ref"],
            "wroot": evidence["weights_manifest_ref"],
            "stability_gate_bundle": evidence["weights_manifest_ref"],
            "determinism_cert": evidence["weights_manifest_ref"],
            "universality_cert": evidence["weights_manifest_ref"],
        },
    )
    pointer_path = repo_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": prev_digest,
                "artifact_relpath": prev_path.relative_to(repo_root).as_posix(),
            },
        },
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": evidence,
        "dmpl_evidence": {
            "schema_id": "dmpl_evidence_v1",
            "plan_evidence": [{}],
            "certificate_refs": {
                "dmpl_cac_pack_ref": None,
                "dmpl_ufc_flow_ref": None,
                "dmpl_stab_report_ref": None,
                "dmpl_lasum_report_ref": None,
            },
        },
    }
    _write_hashed_json_v1(out_dir=state_dir / "eudrs_u/evidence", suffix="eudrs_u_promotion_summary_v1.json", payload=summary)

    with pytest.raises(OmegaV18Error) as excinfo:
        verify_promotion(state_dir, mode="full", repo_root_override=repo_root)
    assert "DMPL_E_DISABLED" in str(excinfo.value)
