from __future__ import annotations

import json
from pathlib import Path

from tools.orch_worldmodel.orch_transition_dataset_builder_v1 import build_transition_dataset
from tools.orch_worldmodel.orch_worldmodel_trainer_v1 import train_worldmodel_policy

from ._orch_worldmodel_test_utils_v1 import write_sample_run_fixture, write_train_config


def test_policy_table_training_is_deterministic_v1(tmp_path: Path) -> None:
    repo_root = tmp_path.resolve()
    runs_root = repo_root / "runs"
    write_sample_run_fixture(runs_root)

    dataset_summary = build_transition_dataset(
        runs_root=runs_root,
        out_root=repo_root / "daemon" / "orch_policy",
        ek_id="sha256:" + ("3" * 64),
        kernel_ledger_id="sha256:" + ("4" * 64),
        max_runs_u64=5000,
        max_events_u64=200000,
        cost_scale_ms_u64=60000,
        repo_root=repo_root,
    )

    train_config_path = write_train_config(repo_root / "train_config.json")
    manifest_path = Path(str(dataset_summary["dataset_manifest_path"]))

    out_a = repo_root / "out_a"
    out_b = repo_root / "out_b"

    train_a = train_worldmodel_policy(
        dataset_manifest_path=manifest_path,
        train_config_path=train_config_path,
        out_dir=out_a,
        repo_root=repo_root,
    )
    train_b = train_worldmodel_policy(
        dataset_manifest_path=manifest_path,
        train_config_path=train_config_path,
        out_dir=out_b,
        repo_root=repo_root,
    )

    assert train_a["policy_table_id"] == train_b["policy_table_id"]

    policy_a = json.loads((out_a / "orch_policy_table_v1.json").read_text(encoding="utf-8"))
    policy_b = json.loads((out_b / "orch_policy_table_v1.json").read_text(encoding="utf-8"))
    assert policy_a == policy_b
