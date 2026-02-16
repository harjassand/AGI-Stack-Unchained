from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.eudrs_u.eudrs_u_artifact_refs_v1 import require_safe_relpath_v1, verify_artifact_ref_v1
from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_eudrs_u_promotion_v1 import verify as verify_promotion
from cdel.v18_0.omega_common_v1 import OmegaV18Error, Q32_ONE, hash_bytes

_DMPL_MERKLE_LEAF_PREFIX = b"DMPL/MERKLE/LEAF/v1\x00"
_DMPL_MERKLE_NODE_PREFIX = b"DMPL/MERKLE/NODE/v1\x00"
_DMPL_TENSOR_MAGIC = b"DMPLTQ32"


def _write_hashed_json_v1(out_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = dict(payload)
    raw = gcj1_canon_bytes(obj)
    digest = sha256_prefixed(raw)
    name = f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    out_path = out_dir / name
    out_path.write_bytes(raw)
    return out_path, obj, digest


def test_require_safe_relpath_v1_rejects_bad_paths() -> None:
    bad = [
        "/abs/path",
        "../escape",
        "a/../b",
        "a\\b",
        "C:\\windows\\path",
        "a\x00b",
    ]
    for value in bad:
        with pytest.raises(OmegaV18Error):
            require_safe_relpath_v1(value)


def test_verify_artifact_ref_v1_accepts_canonical_json(tmp_path: Path) -> None:
    base = tmp_path
    payload = {"schema_id": "toy_v1", "a": 1, "b": [True, None]}
    digest = sha256_prefixed(gcj1_canon_bytes(payload))
    path = base / f"sha256_{digest.split(':', 1)[1]}.toy_v1.json"
    path.write_bytes(gcj1_canon_bytes(payload))

    ref = {"artifact_id": digest, "artifact_relpath": path.relative_to(base).as_posix()}
    verified = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base)
    assert verified.resolve() == path.resolve()

    # Non-canonical JSON must fail.
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(OmegaV18Error):
        verify_artifact_ref_v1(artifact_ref=ref, base_dir=base)

    # Canonical-but-different content must fail hash check.
    path.write_bytes(gcj1_canon_bytes({"schema_id": "toy_v1", "a": 2, "b": [True, None]}))
    with pytest.raises(OmegaV18Error):
        verify_artifact_ref_v1(artifact_ref=ref, base_dir=base)


def test_verify_promotion_bootstrap_epoch0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Build a minimal fake repo root so schema validation resolves to tmp files.
    repo_root = tmp_path / "repo"
    schema_dir = repo_root / "Genesis" / "schema" / "v18_0"
    schema_dir.mkdir(parents=True, exist_ok=True)

    # Minimal schemas needed by verify_eudrs_u_promotion_v1.
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

    # Minimal DMPL schemas needed by verify_eudrs_u_promotion_v1 Phase 1.
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
                "required": ["schema_id", "dc1_id", "opset_id", "enabled_b", "active_modelpack_id", "fparams_bundle_id", "vparams_bundle_id", "caps", "retrieval_spec"],
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
                },
                "required": ["schema_id", "proposed_root_tuple_ref", "staged_registry_tree_relpath", "evidence"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (schema_dir / "ml_index_manifest_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/ml_index_manifest_v1",
                "type": "object",
                "additionalProperties": True,
                "properties": {"schema_id": {"const": "ml_index_manifest_v1"}},
                "required": ["schema_id"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (schema_dir / "ml_index_bucket_listing_v1.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://genesis.engine/specs/v18_0/ml_index_bucket_listing_v1",
                "type": "object",
                "additionalProperties": True,
                "properties": {"schema_id": {"const": "ml_index_bucket_listing_v1"}},
                "required": ["schema_id"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Allow repo_root() override in RE2 helpers.
    monkeypatch.setenv("OMEGA_DEV_BENCHMARK_MODE", "1")
    monkeypatch.setenv("OMEGA_REPO_ROOT", str(repo_root))

    state_dir = tmp_path / "state"
    evidence_dir = state_dir / "eudrs_u" / "evidence"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    expected_dc1_id = "dc1:q32_v1"
    expected_opset_id = "opset:eudrs_u_v1:sha256:" + ("0" * 64)

    # Minimal staged artifacts.
    def _write_evidence(suffix: str, payload: dict) -> dict[str, str]:
        out_path, _obj, digest = _write_hashed_json_v1(evidence_dir, suffix, payload)
        return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(state_dir).as_posix()}

    def _write_staged(rel_dir: str, suffix: str, payload: dict) -> dict[str, str]:
        out_path, _obj, digest = _write_hashed_json_v1(staged_root / rel_dir, suffix, payload)
        return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(staged_root).as_posix()}

    # Root tuple dependencies.
    def _dep(schema_id: str) -> dict[str, Any]:
        return {"schema_id": schema_id, "dc1_id": expected_dc1_id, "opset_id": expected_opset_id}

    zero_ref = {
        "artifact_id": "sha256:" + ("00" * 32),
        "artifact_relpath": "polymath/registry/eudrs_u/manifests/sha256_" + ("00" * 64) + ".placeholder.json",
    }
    sroot = _write_staged(
        "polymath/registry/eudrs_u/manifests",
        "eudrs_u_system_manifest_v1.json",
        {
            "schema_id": "eudrs_u_system_manifest_v1",
            "epoch_u64": 0,
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "qxwmr": {"world_model_manifest_ref": zero_ref, "eval_manifest_ref": zero_ref},
            "qxrl": {"model_manifest_ref": zero_ref, "eval_manifest_ref": zero_ref, "dataset_manifest_ref": zero_ref},
            "ml_index": {"index_manifest_ref": zero_ref, "bucket_listing_manifest_ref": zero_ref},
        },
    )
    oroot = _write_staged("polymath/registry/eudrs_u/manifests", "concept_bank_manifest_v1.json", _dep("concept_bank_manifest_v1"))
    kroot = _write_staged("polymath/registry/eudrs_u/manifests", "strategy_vm_manifest_v1.json", _dep("strategy_vm_manifest_v1"))
    croot = _write_staged("polymath/registry/eudrs_u/manifests", "concept_def_v1.json", _dep("concept_def_v1"))
    mroot = _write_staged("polymath/registry/eudrs_u/manifests", "cooldown_ledger_v1.json", _dep("cooldown_ledger_v1"))
    # Minimal staged ML-index artifacts for verifier bootstrap.
    from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
    from cdel.v18_0.eudrs_u.ml_index_v1 import (
        MLIndexCodebookV1,
        MLIndexPageRecordV1,
        MLIndexPageV1,
        MLIndexRootV1,
        encode_ml_index_codebook_v1,
        encode_ml_index_page_v1,
        encode_ml_index_root_v1,
    )

    def _write_bin(rel_dir: str, suffix: str, data: bytes) -> dict[str, str]:
        out_dir = staged_root / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hash_bytes(bytes(data))
        hex64 = digest.split(":", 1)[1]
        path = out_dir / f"sha256_{hex64}.{suffix}"
        path.write_bytes(bytes(data))
        return {"artifact_id": digest, "artifact_relpath": path.relative_to(staged_root).as_posix()}

    # K=1, d=1, single-record bucket pages (non-empty index required for Phase 3 MEM gates).
    codebook = MLIndexCodebookV1(K_u32=1, d_u32=1, C_q32=[0])
    codebook_ref = _write_bin("polymath/registry/eudrs_u/indices", "ml_index_codebook_v1.bin", encode_ml_index_codebook_v1(codebook))

    rec = MLIndexPageRecordV1(record_hash32=b"\x01" * 32, payload_hash32=b"\x02" * 32, key_q32=[0])
    page = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=1, records=[rec])
    page_ref = _write_bin(
        "polymath/registry/eudrs_u/indices/buckets/0/pages",
        "ml_index_page_v1.bin",
        encode_ml_index_page_v1(page),
    )

    bucket_listing_ref = _write_staged(
        "polymath/registry/eudrs_u/indices",
        "ml_index_bucket_listing_v1.json",
        {
            "schema_id": "ml_index_bucket_listing_v1",
            "index_manifest_id": "sha256:" + ("11" * 32),
            "buckets": [
                {
                    "bucket_id_u32": 0,
                    "pages": [{"page_index_u32": 0, "page_ref": page_ref}],
                }
            ],
        },
    )

    leaf0 = bytes.fromhex(page_ref["artifact_id"].split(":", 1)[1])
    root0 = merkle_fanout_v1(leaf_hash32=[leaf0], fanout_u32=2)
    index_root = MLIndexRootV1(K_u32=1, fanout_u32=2, bucket_root_hash32=[root0])
    index_root_ref = _write_bin("polymath/registry/eudrs_u/indices", "ml_index_root_v1.bin", encode_ml_index_root_v1(index_root))

    # Root tuple iroot points at the index root binary.
    iroot = index_root_ref
    wroot = _write_staged("polymath/registry/eudrs_u/manifests", "weights_manifest_v1.json", _dep("weights_manifest_v1"))
    gates = _write_staged("polymath/registry/eudrs_u/gates", "stability_gate_bundle_v1.json", _dep("stability_gate_bundle_v1"))
    det = _write_staged("polymath/registry/eudrs_u/certs", "determinism_cert_v1.json", _dep("determinism_cert_v1"))
    uni = _write_staged("polymath/registry/eudrs_u/certs", "universality_cert_v1.json", _dep("universality_cert_v1"))

    # DMPL (Phase 1): minimal disabled config + droot binding.
    tensor_bytes = _DMPL_TENSOR_MAGIC + struct.pack("<II", 1, 1) + struct.pack("<I", 1) + struct.pack("<q", 0)
    tensor_bin_ref = _write_bin("polymath/registry/eudrs_u/dmpl/tensors", "dmpl_tensor_q32_v1.bin", tensor_bytes)
    tensors = [{"name": "t0", "shape_u32": [1], "tensor_bin_id": tensor_bin_ref["artifact_id"]}]

    def _dmpl_bundle_root(tensors: list[dict[str, Any]]) -> str:
        leaf_hashes: list[bytes] = []
        for row in tensors:
            name = str(row["name"])
            digest32 = bytes.fromhex(str(row["tensor_bin_id"]).split(":", 1)[1])
            leaf_hashes.append(hashlib.sha256(_DMPL_MERKLE_LEAF_PREFIX + name.encode("utf-8") + b"\x00" + digest32).digest())
        level = list(leaf_hashes)
        while len(level) > 1:
            if len(level) % 2 == 1:
                level = level + [level[-1]]
            nxt: list[bytes] = []
            for i in range(0, len(level), 2):
                nxt.append(hashlib.sha256(_DMPL_MERKLE_NODE_PREFIX + level[i] + level[i + 1]).digest())
            level = nxt
        return f"sha256:{level[0].hex()}"

    f_merkle = _dmpl_bundle_root(tensors)
    v_merkle = _dmpl_bundle_root(tensors)

    modelpack_ref = _write_staged(
        "polymath/registry/eudrs_u/dmpl/modelpacks",
        "dmpl_modelpack_v1.json",
        {
            "schema_id": "dmpl_modelpack_v1",
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "forward_arch_id": "dmpl_linear_pwl_v1",
            "value_arch_id": "dmpl_linear_v1",
            "activation_id": "hard_tanh_q32_v1",
            "gating_arch_id": "linear_gate_v1",
            "patch_policy": {"vm_patch_allowed_b": False, "allowed_patch_types": ["matrix_patch", "lowrank_patch"]},
        },
    )
    fparams_ref = _write_staged(
        "polymath/registry/eudrs_u/dmpl/params",
        "dmpl_params_bundle_v1.json",
        {
            "schema_id": "dmpl_params_bundle_v1",
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "bundle_kind": "F",
            "modelpack_id": modelpack_ref["artifact_id"],
            "tensors": tensors,
            "merkle_root": f_merkle,
        },
    )
    vparams_ref = _write_staged(
        "polymath/registry/eudrs_u/dmpl/params",
        "dmpl_params_bundle_v1.json",
        {
            "schema_id": "dmpl_params_bundle_v1",
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "bundle_kind": "V",
            "modelpack_id": modelpack_ref["artifact_id"],
            "tensors": tensors,
            "merkle_root": v_merkle,
        },
    )
    caps_obj = {"K_ctx_u32": 0, "K_g_u32": 0, "max_concept_bytes_per_step_u32": 0, "max_retrieval_bytes_u32": 0, "max_retrieval_ops_u64": 0}
    caps_digest = sha256_prefixed(gcj1_canon_bytes(caps_obj))
    config_ref = _write_staged(
        "polymath/registry/eudrs_u/dmpl/configs",
        "dmpl_config_v1.json",
        {
            "schema_id": "dmpl_config_v1",
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "enabled_b": False,
            "active_modelpack_id": modelpack_ref["artifact_id"],
            "fparams_bundle_id": fparams_ref["artifact_id"],
            "vparams_bundle_id": vparams_ref["artifact_id"],
            "caps": caps_obj,
            "retrieval_spec": {
                "key_fn_id": "dmpl_key_v1",
                "score_fn_id": "ml_index_v1_default",
                "tie_rule_id": "score_desc_id_asc",
                "K_ctx_u32": 0,
            },
            "gating_spec": {
                "pwl_pos_id": "pwl_pos_v1",
                "normalize_weights_b": False,
                "inv_q32_id": "",
                "inverse_head_enabled_b": False,
            },
            "planner_spec": {
                "algorithm_id": "dcbts_l_v1",
                "action_source_id": "dmpl_action_enum_v1",
                "ordering_policy": {
                    "primary_key_id": "upper_bound_primary_score_desc",
                    "secondary_key_id": "depth_asc",
                    "tertiary_key_id": "node_id_asc",
                },
                "aux_tie_break_policy": {"aux_allowed_only_on_exact_score_ties_b": True},
            },
            "hash_layout_ids": {"record_encoding_id": "lenpref_canonjson_v1", "chunking_rule_id": "fixed_1MiB_v1"},
            "objective_spec": {"reward_proxy_id": "ufc_proxy_v1", "ufc_objective_id": "ufc_v1_primary"},
        },
    )
    droot = _write_staged(
        "polymath/registry/eudrs_u/dmpl/roots",
        "dmpl_droot_v1.json",
        {
            "schema_id": "dmpl_droot_v1",
            "dc1_id": expected_dc1_id,
            "opset_id": expected_opset_id,
            "dmpl_config_id": config_ref["artifact_id"],
            "froot": f_merkle,
            "vroot": v_merkle,
            "caps_digest": caps_digest,
            "opset_semantics_id": expected_opset_id,
        },
    )

    root_tuple = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": 0,
        "dc1_id": expected_dc1_id,
        "opset_id": expected_opset_id,
        "sroot": sroot,
        "oroot": oroot,
        "kroot": kroot,
        "croot": croot,
        "droot": droot,
        "mroot": mroot,
        "iroot": iroot,
        "wroot": wroot,
        "stability_gate_bundle": gates,
        "determinism_cert": det,
        "universality_cert": uni,
    }
    root_tuple_path, _obj, root_tuple_digest = _write_hashed_json_v1(
        staged_root / "polymath/registry/eudrs_u/roots",
        "eudrs_u_root_tuple_v1.json",
        root_tuple,
    )
    proposed_root_tuple_ref = {
        "artifact_id": root_tuple_digest,
        "artifact_relpath": root_tuple_path.relative_to(state_dir).as_posix(),
    }

    # Staged activation pointer must point to target relpath.
    pointer_path = staged_root / "polymath/registry/eudrs_u/active/active_root_tuple_ref_v1.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        pointer_path,
        {
            "schema_id": "active_root_tuple_ref_v1",
            "active_root_tuple": {
                "artifact_id": root_tuple_digest,
                "artifact_relpath": root_tuple_path.relative_to(staged_root).as_posix(),
            },
        },
    )

    summary = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": proposed_root_tuple_ref,
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": {
            "weights_manifest_ref": _write_evidence("weights_manifest_v1.json", {"schema_id": "weights_manifest_v1"}),
            "ml_index_manifest_ref": _write_evidence(
                "ml_index_manifest_v1.json",
                {
                    "schema_id": "ml_index_manifest_v1",
                    "index_kind": "ML_INDEX_V1",
                    "opset_id": expected_opset_id,
                    "key_dim_u32": 1,
                    "codebook_size_u32": 1,
                    "bucket_visit_k_u32": 1,
                    "scan_cap_per_bucket_u32": 1,
                    "merkle_fanout_u32": 2,
                    "sim_kind": "DOT_Q32_SHIFT_END_V1",
                    "codebook_ref": codebook_ref,
                    "index_root_ref": index_root_ref,
                    "bucket_listing_ref": bucket_listing_ref,
                    "mem_gates": {
                        "mem_g1_bucket_balance_max_q32": {"q": 1 * Q32_ONE},
                        "mem_g2_anchor_recall_min_q32": {"q": 0},
                    },
                },
            ),
            "cac_ref": _write_evidence("cac_v1.json", {"schema_id": "cac_v1"}),
            "ufc_ref": _write_evidence("ufc_v1.json", {"schema_id": "ufc_v1"}),
            "cooldown_ledger_ref": _write_evidence("cooldown_ledger_v1.json", {"schema_id": "cooldown_ledger_v1"}),
            "stability_metrics_ref": _write_evidence("stability_metrics_v1.json", {"schema_id": "stability_metrics_v1"}),
            "determinism_cert_ref": _write_evidence("determinism_cert_v1.json", {"schema_id": "determinism_cert_v1"}),
            "universality_cert_ref": _write_evidence("universality_cert_v1.json", {"schema_id": "universality_cert_v1"}),
        },
    }
    _write_hashed_json_v1(evidence_dir, "eudrs_u_promotion_summary_v1.json", summary)

    assert verify_promotion(state_dir, mode="full", repo_root_override=repo_root) == "VALID"
