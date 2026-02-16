from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import write_canon_json


def test_verify_ccap_preserves_ek_determinism_and_eval_fields(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    pins = load_authority_pins(repo_root)
    base_tree_id = "sha256:" + ("1" * 64)

    subrun_root = tmp_path / "subrun"
    receipt_out_dir = tmp_path / "receipt"
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/tools/omega/ccap_truth_fields_generated.py b/tools/omega/ccap_truth_fields_generated.py\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/tools/omega/ccap_truth_fields_generated.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+MARKER = 'truthful_ek_fields'\n"
    ).encode("utf-8")
    patch_blob_id = f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}"
    (subrun_root / "ccap" / "blobs" / f"sha256_{patch_blob_id.split(':', 1)[1]}.patch").write_bytes(patch_bytes)

    ccap_payload = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": str(pins["active_dsbx_profile_ids"][0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(pins["active_op_pool_ids"][0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": patch_blob_id,
        },
        "build": {
            "build_recipe_id": "sha256:" + ("2" * 64),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": "sha256:" + ("3" * 64),
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
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    write_canon_json(subrun_root / ccap_relpath, ccap_payload)

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _repo_root: base_tree_id)
    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1.run_ek",
        lambda **_kwargs: {
            "determinism_check": "DIVERGED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "applied_tree_id": "sha256:" + ("e" * 64),
            "realized_out_id": "sha256:" + ("f" * 64),
            "cost_vector": {
                "cpu_ms": 0,
                "wall_ms": 0,
                "mem_mb": 0,
                "disk_mb": 0,
                "fds": 0,
                "procs": 0,
                "threads": 0,
            },
            "logs_hash": "sha256:" + ("0" * 64),
            "refutation": {
                "code": "NONDETERMINISM_DETECTED",
                "detail": "double-run outputs diverged",
            },
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "NONDETERMINISM_DETECTED"
    assert receipt["determinism_check"] == "DIVERGED"
    assert receipt["eval_status"] == "REFUTED"
    assert receipt["decision"] == "REJECT"
