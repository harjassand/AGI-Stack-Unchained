from __future__ import annotations

from pathlib import Path

from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import write_canon_json


def _write_authority_pins(repo_root: Path) -> None:
    allowlists = {
        "schema_version": "ccap_patch_allowlists_v1",
        "allow_prefixes": ["tools/omega/"],
        "forbid_prefixes": ["authority/"],
        "forbid_exact_paths": [],
    }
    write_canon_json(repo_root / "authority" / "ccap_patch_allowlists_v1.json", allowlists)
    pins = {
        "schema_version": "authority_pins_v1",
        "re1_constitution_state_id": "sha256:" + ("1" * 64),
        "re2_verifier_state_id": "sha256:" + ("2" * 64),
        "active_ek_id": "sha256:" + ("3" * 64),
        "active_op_pool_ids": ["sha256:" + ("4" * 64)],
        "active_dsbx_profile_ids": ["sha256:" + ("5" * 64)],
        "env_contract_id": "sha256:" + ("6" * 64),
        "toolchain_root_id": "sha256:" + ("7" * 64),
        "ccap_patch_allowlists_id": canon_hash_obj(allowlists),
        "canon_version_ids": {
            "ccap_can_v": "sha256:" + ("8" * 64),
            "ir_can_v": "sha256:" + ("9" * 64),
            "op_can_v": "sha256:" + ("a" * 64),
            "obs_can_v": "sha256:" + ("b" * 64),
        },
    }
    write_canon_json(repo_root / "authority" / "authority_pins_v1.json", pins)


def test_verify_ccap_refutes_auth_hash_mismatch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    subrun_root = tmp_path / "subrun"
    receipt_out = tmp_path / "receipt"
    (repo_root / "authority").mkdir(parents=True)
    (subrun_root / "ccap" / "blobs").mkdir(parents=True)

    _write_authority_pins(repo_root)

    patch_bytes = b"diff --git a/a.txt b/a.txt\nindex e69de29..4b825dc 100644\n--- a/a.txt\n+++ b/a.txt\n"
    patch_hash = "sha256:" + __import__("hashlib").sha256(patch_bytes).hexdigest()
    patch_path = subrun_root / "ccap" / "blobs" / f"sha256_{patch_hash.split(':', 1)[1]}.patch"
    patch_path.write_bytes(patch_bytes)

    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": "sha256:" + ("c" * 64),
            "auth_hash": "sha256:" + ("0" * 64),
            "dsbx_profile_id": "sha256:" + ("5" * 64),
            "env_contract_id": "sha256:" + ("6" * 64),
            "toolchain_root_id": "sha256:" + ("7" * 64),
            "ek_id": "sha256:" + ("3" * 64),
            "op_pool_id": "sha256:" + ("4" * 64),
            "canon_version_ids": {
                "ccap_can_v": "sha256:" + ("8" * 64),
                "ir_can_v": "sha256:" + ("9" * 64),
                "op_can_v": "sha256:" + ("a" * 64),
                "obs_can_v": "sha256:" + ("b" * 64),
            },
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": patch_hash,
        },
        "build": {
            "build_recipe_id": "sha256:" + ("d" * 64),
            "build_targets": ["unit"],
            "artifact_bindings": {"report": "reports/*.json"},
        },
        "eval": {
            "stages": [{"stage_name": "REALIZE"}],
            "final_suite_id": "sha256:" + ("e" * 64),
        },
        "budgets": {
            "cpu_ms_max": 1000,
            "wall_ms_max": 1000,
            "mem_mb_max": 1024,
            "disk_mb_max": 1024,
            "fds_max": 256,
            "procs_max": 64,
            "threads_max": 64,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap_payload)
    ccap_rel = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    write_canon_json(subrun_root / ccap_rel, ccap_payload)

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_rel,
        receipt_out_dir=receipt_out,
    )

    assert code == "AUTH_HASH_MISMATCH"
    assert receipt["decision"] == "REJECT"
    assert receipt["eval_status"] == "REFUTED"

    cert_paths = sorted((subrun_root / "ccap" / "refutations").glob("sha256_*.ccap_refutation_cert_v1.json"))
    assert cert_paths

    receipt_paths = sorted(receipt_out.glob("sha256_*.ccap_receipt_v1.json"))
    assert receipt_paths
