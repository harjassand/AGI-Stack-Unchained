from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v2_3.code_patch import compute_patch_id
from cdel.v2_3.immutable_core import load_lock


def build_valid_icore_receipt(repo_root: Path) -> dict[str, Any]:
    lock_path = repo_root / "meta-core" / "meta_constitution" / "v2_3" / "immutable_core_lock_v1.json"
    lock = load_lock(lock_path)

    receipt = {
        "schema": "immutable_core_receipt_v1",
        "spec_version": "v2_3",
        "verdict": "VALID",
        "reason": "OK",
        "repo_root_sha256": sha256_prefixed(str(repo_root).encode("utf-8")),
        "lock_path": str(lock_path.relative_to(repo_root)).replace("\\", "/"),
        "lock_id": lock["lock_id"],
        "core_id_expected": lock["core_id"],
        "core_id_observed": lock["core_id"],
        "mismatches": [],
        "receipt_head_hash": "__SELF__",
    }
    head = dict(receipt)
    head.pop("receipt_head_hash", None)
    receipt["receipt_head_hash"] = sha256_prefixed(canon_bytes(head))
    return receipt


def write_minimal_attempt(
    tmp_path: Path,
    repo_root: Path,
    *,
    include_receipt: bool,
    receipt_override: dict[str, Any] | None,
    touched_relpath: str,
) -> Path:
    run_root = tmp_path / "run"
    attempt_dir = run_root / "attempts" / "attempt_0001"
    (attempt_dir / "autonomy" / "csi").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)

    meta_hash = (repo_root / "meta-core" / "meta_constitution" / "v2_3" / "META_HASH").read_text(encoding="utf-8").strip()
    (run_root / "constitution_hash.txt").write_text(meta_hash, encoding="utf-8")

    if include_receipt:
        receipt = receipt_override or build_valid_icore_receipt(repo_root)
        write_canon_json(run_root / "diagnostics" / "immutable_core_receipt_v1.json", receipt)

    patch = {
        "schema": "code_patch_v1",
        "patch_id": "__SELF__",
        "base_tree_hash": "sha256:" + "0" * 64,
        "after_tree_hash": "sha256:" + "0" * 64,
        "touched_files": [
            {
                "relpath": touched_relpath,
                "before_sha256": "sha256:" + "0" * 64,
                "after_sha256": "sha256:" + "0" * 64,
                "unified_diff": f"--- a/{touched_relpath}\n+++ b/{touched_relpath}\n@@\n",
            }
        ],
        "concept_binding": {
            "mode": "recursive_ontology_v2_1",
            "selected_concept_id": "sha256:" + "0" * 64,
            "selected_concept_patch_id": "sha256:" + "0" * 64,
            "concept_eval_features": {
                "u_ctx": 0,
                "sha256_calls_total": 0,
                "sha256_bytes_total": 0,
                "canon_calls_total": 0,
                "canon_bytes_total": 0,
                "onto_ctx_hash_compute_calls_total": 0,
                "work_cost_base": 0,
            },
            "concept_eval_output_int": 0,
        },
    }
    patch["patch_id"] = compute_patch_id(patch)
    write_canon_json(attempt_dir / "autonomy" / "csi" / "code_patch.json", patch)

    manifest = {
        "schema": "csi_manifest_v1",
        "run_id": "sha256:" + "0" * 64,
        "attempt_id": "attempt_0001",
        "base_tree_hash": patch["base_tree_hash"],
        "candidate_rank": 0,
        "generated_patch_relpath": "autonomy/csi/code_patch.json",
        "patch_id": patch["patch_id"],
        "manifest_head_hash": "__SELF__",
    }
    head = dict(manifest)
    head.pop("manifest_head_hash", None)
    manifest["manifest_head_hash"] = sha256_prefixed(canon_bytes(head))
    write_canon_json(attempt_dir / "csi_manifest_v1.json", manifest)

    return attempt_dir
