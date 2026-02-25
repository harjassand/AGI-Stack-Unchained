from __future__ import annotations

import json
from pathlib import Path

from tools.orch_worldmodel.orch_transition_dataset_builder_v1 import build_transition_dataset

from ._orch_worldmodel_test_utils_v1 import write_sample_run_fixture


def test_transition_dataset_builder_is_deterministic_v1(tmp_path: Path) -> None:
    repo_root = tmp_path.resolve()
    runs_root = repo_root / "runs"
    write_sample_run_fixture(runs_root)

    out_root = repo_root / "daemon" / "orch_policy"
    ek_id = "sha256:" + ("1" * 64)
    kernel_ledger_id = "sha256:" + ("2" * 64)

    summary_a = build_transition_dataset(
        runs_root=runs_root,
        out_root=out_root,
        ek_id=ek_id,
        kernel_ledger_id=kernel_ledger_id,
        max_runs_u64=5000,
        max_events_u64=200000,
        cost_scale_ms_u64=60000,
        repo_root=repo_root,
    )
    summary_b = build_transition_dataset(
        runs_root=runs_root,
        out_root=out_root,
        ek_id=ek_id,
        kernel_ledger_id=kernel_ledger_id,
        max_runs_u64=5000,
        max_events_u64=200000,
        cost_scale_ms_u64=60000,
        repo_root=repo_root,
    )

    assert summary_a == summary_b
    assert int(summary_a["events_included_u64"]) == 2

    blob_a = Path(str(summary_a["transition_events_blob_path"]))
    blob_b = Path(str(summary_b["transition_events_blob_path"]))
    assert blob_a.read_bytes() == blob_b.read_bytes()

    manifest_path = Path(str(summary_a["dataset_manifest_path"]))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    drop_hist = dict(manifest_payload.get("drop_reason_histogram") or {})
    assert int(drop_hist.get("DROP:NO_NEXT_CONTEXT", 0)) >= 1
