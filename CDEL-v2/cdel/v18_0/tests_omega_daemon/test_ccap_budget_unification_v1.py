from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.ek import ek_runner_v1
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import write_canon_json


def _sha(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_run_ek_disk_budget_env_override_moves_past_budget_exceeded(tmp_path: Path, monkeypatch) -> None:
    ccap = {
        "meta": {
            "ek_id": _sha("1"),
        },
        "budgets": {
            "cpu_ms_max": 10_000,
            "wall_ms_max": 10_000,
            "mem_mb_max": 10_000,
            "disk_mb_max": 1,
            "fds_max": 10_000,
            "procs_max": 10_000,
            "threads_max": 10_000,
            "net": "forbidden",
        },
    }
    monkeypatch.setattr(
        ek_runner_v1,
        "_load_active_ek",
        lambda _repo_root, _expected: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {"code_ref": {"path": "tools/omega/omega_benchmark_suite_v1.py"}},
        },
    )
    monkeypatch.setattr(ek_runner_v1, "_survival_drill_fast_ek_enabled", lambda: True)
    monkeypatch.setattr(ek_runner_v1, "_self_mem_mb", lambda: 0)
    monkeypatch.setattr(ek_runner_v1, "workspace_disk_mb", lambda _path: 32)
    monkeypatch.setattr(
        ek_runner_v1,
        "_realize_once",
        lambda **_kwargs: {
            "ok": True,
            "workspace": str(tmp_path / "workspace"),
            "applied_tree_id": _sha("a"),
            "realized_out_id": _sha("b"),
            "transcript_id": _sha("c"),
            "realize_logs_hash": _sha("d"),
            "harness_cost_vector": {},
        },
    )

    result_before = ek_runner_v1.run_ek(
        repo_root=tmp_path,
        subrun_root=tmp_path,
        ccap_id=_sha("9"),
        ccap=ccap,
        out_dir=tmp_path / "ek_before",
    )
    assert result_before["decision"] == "REJECT"
    assert isinstance(result_before["refutation"], dict)
    assert result_before["refutation"]["code"] == "BUDGET_EXCEEDED"

    monkeypatch.setenv("OMEGA_CCAP_DISK_MB_MAX", "64")
    result_after = ek_runner_v1.run_ek(
        repo_root=tmp_path,
        subrun_root=tmp_path,
        ccap_id=_sha("9"),
        ccap=ccap,
        out_dir=tmp_path / "ek_after",
    )
    assert result_after["decision"] == "PROMOTE"
    assert result_after["refutation"] is None
    assert result_after["effective_budget_limits"]["disk_mb_max"] == 64
    assert result_after["effective_budget_tuple"]["artifact_bytes_max"] == 64 * 1024 * 1024


def test_verify_ccap_emits_effective_budget_profile_and_passes_limits_to_ek(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    pins = load_authority_pins(repo_root)
    base_tree_id = _sha("2")

    subrun_root = tmp_path / "subrun"
    receipt_out_dir = tmp_path / "receipt"
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/tools/omega/ccap_budget_unification_generated.py b/tools/omega/ccap_budget_unification_generated.py\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/tools/omega/ccap_budget_unification_generated.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+MARKER = 'ccap_budget_unification'\n"
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
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {
            "build_recipe_id": _sha("3"),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": _sha("4"),
        },
        "budgets": {
            "cpu_ms_max": 1000,
            "wall_ms_max": 2000,
            "mem_mb_max": 256,
            "disk_mb_max": 4,
            "fds_max": 64,
            "procs_max": 8,
            "threads_max": 32,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap_payload)
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    write_canon_json(subrun_root / ccap_relpath, ccap_payload)

    monkeypatch.setenv("OMEGA_CCAP_DISK_MB_MAX", "4096")
    monkeypatch.setenv("OMEGA_CCAP_WALL_MS_MAX", "7777")
    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _repo_root: base_tree_id)
    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id_tolerant", lambda _repo_root: base_tree_id)

    captured: dict[str, dict[str, int]] = {}

    def _fake_run_ek(**kwargs):  # noqa: ANN003
        captured["limits"] = dict(kwargs["effective_budget_limits"])
        return {
            "determinism_check": "PASS",
            "eval_status": "FAIL",
            "decision": "REJECT",
            "applied_tree_id": _sha("e"),
            "realized_out_id": _sha("f"),
            "cost_vector": {
                "cpu_ms": 0,
                "wall_ms": 0,
                "mem_mb": 0,
                "disk_mb": 0,
                "fds": 0,
                "procs": 0,
                "threads": 0,
            },
            "logs_hash": _sha("0"),
            "refutation": {
                "code": "NO_IMPROVEMENT",
                "detail": "no utility delta",
            },
        }

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.run_ek", _fake_run_ek)

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "NO_IMPROVEMENT"
    assert captured["limits"]["disk_mb_max"] == 4096
    assert captured["limits"]["wall_ms_max"] == 7777
    effective_budget = receipt["effective_budget"]
    assert effective_budget["limits"]["disk_mb_max"] == 4096
    assert effective_budget["limits"]["wall_ms_max"] == 7777
    assert effective_budget["tuple"]["time_ms_max"] == 7777
    assert effective_budget["tuple"]["artifact_bytes_max"] == 4096 * 1024 * 1024
