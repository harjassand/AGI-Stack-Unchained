from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import write_jsonl_line
from cdel.v15_0.verify_rsi_sas_kernel_v1 import _validate_case_outputs

from .utils import repo_root


def test_negative_spawn_forbidden_orchestrator(tmp_path: Path) -> None:
    root = repo_root()
    case_out = root / "runs" / "_pytest_forbidden_spawn"
    if case_out.exists():
        import shutil

        shutil.rmtree(case_out)
    (case_out / "kernel" / "trace").mkdir(parents=True)
    (case_out / "kernel" / "ledger").mkdir(parents=True)
    (case_out / "kernel" / "snapshot").mkdir(parents=True)
    (case_out / "kernel" / "receipts").mkdir(parents=True)
    (case_out / "promotion").mkdir(parents=True)

    trace = case_out / "kernel" / "trace" / "kernel_trace_v1.jsonl"
    write_jsonl_line(
        trace,
        {
            "schema_version": "kernel_trace_event_v1",
            "event_ref_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000001",
            "prev_event_ref_hash": "GENESIS",
            "event_type": "KERNEL_SPAWN_V1",
            "payload": {"argv": ["python3", "-m", "orchestrator.run"]},
        },
    )

    # minimal valid ledger/receipt/snapshot/promotion placeholders are skipped by forcing early failure on trace
    (case_out / "kernel" / "ledger" / "kernel_ledger_v1.jsonl").write_text("", encoding="utf-8")
    (case_out / "kernel" / "snapshot" / "immutable_tree_snapshot_v1.json").write_text(
        '{"files":[],"root_hash_sha256":"sha256:0","root_rel":".","schema_version":"immutable_tree_snapshot_v1"}\n',
        encoding="utf-8",
    )
    (case_out / "kernel" / "receipts" / "kernel_run_receipt_v1.json").write_text(
        '{"schema_version":"kernel_run_receipt_v1","capability_id":"x","ledger_head_hash":"GENESIS","trace_head_hash":"GENESIS","snapshot_root_hash":"sha256:0","promotion_bundle_hash":"sha256:0","run_spec_hash":"sha256:0","receipt_hash":"sha256:0"}\n',
        encoding="utf-8",
    )
    (case_out / "promotion" / "kernel_promotion_bundle_v1.json").write_text(
        '{"schema_version":"kernel_activation_receipt_v1","kernel_component_id":"SAS_KERNEL_V15","binary_sha256":"sha256:0","abi_version":"kernel_run_spec_v1","activated_by_promotion_bundle_sha256":"sha256:0","activated_utc":"x","activation_hash":"sha256:0"}\n',
        encoding="utf-8",
    )

    case = {
        "capability_id": "X",
        "run_spec_rel": "campaigns/rsi_sas_kernel_v15_0/kernel_run_spec_v1.json",
        "case_out_dir_rel": str(case_out.relative_to(root)),
        "reference_snapshot_rel": "campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/immutable_tree_snapshot_v1.json",
        "reference_promotion_bundle_rel": "campaigns/rsi_sas_kernel_v15_0/fixtures/rsi_sas_system_v14_0/kernel_promotion_bundle_v1.json",
    }
    with pytest.raises(Exception):
        _validate_case_outputs(root, case, root / "Genesis" / "schema" / "v15_0")
