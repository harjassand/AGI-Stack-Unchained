from __future__ import annotations

import hashlib
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import write_canon_json


def _h(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _setup_ccap_subrun(tmp_path: Path, repo_root: Path) -> tuple[Path, Path, str, str, dict[str, object], dict[str, object]]:
    pins = load_authority_pins(repo_root)
    base_tree_id = _h("1")

    subrun_root = tmp_path / "subrun"
    receipt_out_dir = tmp_path / "receipt"
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/campaigns/rsi_omega_daemon_v19_0_super_unified/phase1_marker.txt b/campaigns/rsi_omega_daemon_v19_0_super_unified/phase1_marker.txt\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/campaigns/rsi_omega_daemon_v19_0_super_unified/phase1_marker.txt\n"
        "@@ -0,0 +1,1 @@\n"
        "+phase1\n"
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
            "build_recipe_id": _h("2"),
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": _h("3"),
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
    return subrun_root, receipt_out_dir, ccap_relpath, base_tree_id, pins, ccap_payload


def _benchmark_receipt_for_pins(pins: dict[str, object], *, suite_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": _h("4"),
        "ek_id": str(pins["active_ek_id"]),
        "anchor_suite_set_id": str(pins["anchor_suite_set_id"]),
        "extensions_ledger_id": str(pins["active_kernel_extensions_ledger_id"]),
        "suite_runner_id": str(pins["suite_runner_id"]),
        "executed_suites": [
            {
                "suite_id": suite_id,
                "suite_name": f"suite_{idx}",
                "suite_set_id": _h("5"),
                "suite_source": "ANCHOR",
                "ledger_ordinal_u64": idx,
                "suite_outcome": "PASS",
                "metrics": {"median_stps_non_noop_q32": {"q": 100}},
                "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
                "budget_outcome": {
                    "within_budget_b": True,
                    "cpu_ms_u64": 1,
                    "wall_ms_u64": 1,
                    "disk_mb_u64": 0,
                },
            }
            for idx, suite_id in enumerate(suite_ids)
        ],
        "effective_suite_ids": list(suite_ids),
        "aggregate_metrics": {"median_stps_non_noop_q32": {"q": 100}},
        "gate_results": [{"gate_id": "ALL_SUITES_PASS", "passed_b": True}],
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": 1,
            "wall_ms_u64": 1,
            "disk_mb_u64": 0,
        },
    }


def test_verify_ccap_rejects_v2_receipt_pin_mismatch(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    subrun_root, receipt_out_dir, ccap_relpath, base_tree_id, pins, _ccap_payload = _setup_ccap_subrun(tmp_path, repo_root)

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _repo_root: base_tree_id)

    bad_receipt = _benchmark_receipt_for_pins(
        pins,
        suite_ids=[_h("6")],
    )
    bad_receipt["anchor_suite_set_id"] = _h("f")

    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1.run_ek",
        lambda **_kwargs: {
            "determinism_check": "PASS",
            "eval_status": "PASS",
            "decision": "PROMOTE",
            "applied_tree_id": _h("7"),
            "realized_out_id": _h("8"),
            "cost_vector": {
                "cpu_ms": 1,
                "wall_ms": 1,
                "mem_mb": 1,
                "disk_mb": 1,
                "fds": 0,
                "procs": 0,
                "threads": 0,
            },
            "logs_hash": _h("9"),
            "benchmark_run_receipt_v2": bad_receipt,
            "refutation": None,
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "EK_EXT_LEDGER_PIN_MISMATCH"
    assert receipt["decision"] == "REJECT"
    assert receipt["eval_status"] == "REFUTED"


def test_verify_ccap_rejects_v2_receipt_suite_list_mismatch(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    subrun_root, receipt_out_dir, ccap_relpath, base_tree_id, pins, _ccap_payload = _setup_ccap_subrun(tmp_path, repo_root)

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _repo_root: base_tree_id)

    benchmark_receipt = _benchmark_receipt_for_pins(
        pins,
        suite_ids=[_h("a"), _h("b")],
    )

    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1._resolve_effective_suite_ids_from_pins",
        lambda **_kwargs: [_h("a"), _h("c")],
    )
    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1.run_ek",
        lambda **_kwargs: {
            "determinism_check": "PASS",
            "eval_status": "PASS",
            "decision": "PROMOTE",
            "applied_tree_id": _h("7"),
            "realized_out_id": _h("8"),
            "cost_vector": {
                "cpu_ms": 1,
                "wall_ms": 1,
                "mem_mb": 1,
                "disk_mb": 1,
                "fds": 0,
                "procs": 0,
                "threads": 0,
            },
            "logs_hash": _h("9"),
            "benchmark_run_receipt_v2": benchmark_receipt,
            "refutation": None,
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "EK_SUITE_LIST_MISMATCH"
    assert receipt["decision"] == "REJECT"
    assert receipt["eval_status"] == "REFUTED"


def test_verify_ccap_rejects_v2_receipt_suite_runner_pin_mismatch(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    subrun_root, receipt_out_dir, ccap_relpath, base_tree_id, pins, _ccap_payload = _setup_ccap_subrun(tmp_path, repo_root)

    monkeypatch.setattr("cdel.v18_0.verify_ccap_v1.compute_repo_base_tree_id", lambda _repo_root: base_tree_id)

    bad_receipt = _benchmark_receipt_for_pins(
        pins,
        suite_ids=[_h("a")],
    )
    bad_receipt["suite_runner_id"] = _h("f")

    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1._resolve_effective_suite_ids_from_pins",
        lambda **_kwargs: [_h("a")],
    )
    monkeypatch.setattr(
        "cdel.v18_0.verify_ccap_v1.run_ek",
        lambda **_kwargs: {
            "determinism_check": "PASS",
            "eval_status": "PASS",
            "decision": "PROMOTE",
            "applied_tree_id": _h("7"),
            "realized_out_id": _h("8"),
            "cost_vector": {
                "cpu_ms": 1,
                "wall_ms": 1,
                "mem_mb": 1,
                "disk_mb": 1,
                "fds": 0,
                "procs": 0,
                "threads": 0,
            },
            "logs_hash": _h("9"),
            "benchmark_run_receipt_v2": bad_receipt,
            "refutation": None,
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "EK_SUITE_RUNNER_PIN_MISMATCH"
    assert receipt["decision"] == "REJECT"
    assert receipt["eval_status"] == "REFUTED"
