from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.orch_worldmodel.orch_worldmodel_trainer_v1 import TrainError, train_worldmodel_policy

from ._orch_worldmodel_test_utils_v1 import (
    make_transition_event,
    write_dataset_manifest,
    write_train_config,
    write_transition_blob,
)


def _write_dataset(tmp_path: Path, name: str, events: list[dict]) -> tuple[Path, Path]:
    repo_root = tmp_path.resolve()
    blob_path = repo_root / "blobs" / f"{name}.jsonl"
    blob_id, _ = write_transition_blob(path=blob_path, events=events)

    manifest_path = repo_root / "manifests" / f"{name}.json"
    write_dataset_manifest(
        repo_root=repo_root,
        manifest_path=manifest_path,
        transition_events_relpath=blob_path.relative_to(repo_root).as_posix(),
        transition_events_blob_id=blob_id,
        ek_id="sha256:" + ("5" * 64),
        kernel_ledger_id="sha256:" + ("6" * 64),
        included_run_ids=["run_bounds"],
        events_included_u64=len(events),
    )
    return manifest_path, repo_root


def test_policy_table_bounds_context_limit_v1(tmp_path: Path) -> None:
    events = [
        make_transition_event(
            run_id="run_bounds",
            tick_u64=1,
            context_key="sha256:" + ("1" * 64),
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_a",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key="sha256:" + ("2" * 64),
        ),
        make_transition_event(
            run_id="run_bounds",
            tick_u64=2,
            context_key="sha256:" + ("2" * 64),
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_a",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key="sha256:" + ("3" * 64),
        ),
        make_transition_event(
            run_id="run_bounds",
            tick_u64=3,
            context_key="sha256:" + ("3" * 64),
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_a",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key="sha256:" + ("1" * 64),
        ),
    ]
    manifest_path, repo_root = _write_dataset(tmp_path, "context_limit", events)
    train_cfg = write_train_config(repo_root / "config_context_limit.json", {"max_contexts_u32": 2})

    with pytest.raises(TrainError, match="FAIL:MAX_CONTEXTS"):
        train_worldmodel_policy(
            dataset_manifest_path=manifest_path,
            train_config_path=train_cfg,
            out_dir=repo_root / "out_context_limit",
            repo_root=repo_root,
        )


def test_policy_table_bounds_action_limit_v1(tmp_path: Path) -> None:
    context_key = "sha256:" + ("a" * 64)
    events = [
        make_transition_event(
            run_id="run_bounds",
            tick_u64=1,
            context_key=context_key,
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_a",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key=context_key,
        ),
        make_transition_event(
            run_id="run_bounds",
            tick_u64=2,
            context_key=context_key,
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_b",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key=context_key,
        ),
        make_transition_event(
            run_id="run_bounds",
            tick_u64=3,
            context_key=context_key,
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_c",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key=context_key,
        ),
    ]
    manifest_path, repo_root = _write_dataset(tmp_path, "action_limit", events)
    train_cfg = write_train_config(repo_root / "config_action_limit.json", {"max_actions_u32": 2})

    with pytest.raises(TrainError, match="FAIL:MAX_ACTIONS"):
        train_worldmodel_policy(
            dataset_manifest_path=manifest_path,
            train_config_path=train_cfg,
            out_dir=repo_root / "out_action_limit",
            repo_root=repo_root,
        )


def test_policy_table_bounds_ranked_action_cap_v1(tmp_path: Path) -> None:
    context_key = "sha256:" + ("f" * 64)
    events: list[dict] = []
    for idx in range(32):
        events.append(
            make_transition_event(
                run_id="run_bounds",
                tick_u64=idx + 1,
                context_key=context_key,
                lane_kind="BASELINE",
                objective_kind="RUN_CAMPAIGN",
                action_capability_id=f"cap_{idx:02d}",
                reward_q32=32 - idx,
                cost_norm_q32=0,
                toxic_fail_b=False,
                next_context_key=context_key,
            )
        )

    manifest_path, repo_root = _write_dataset(tmp_path, "ranked_cap", events)
    train_cfg = write_train_config(repo_root / "config_ranked_cap.json", {"max_actions_u32": 64, "max_contexts_u32": 4})

    train_worldmodel_policy(
        dataset_manifest_path=manifest_path,
        train_config_path=train_cfg,
        out_dir=repo_root / "out_ranked_cap",
        repo_root=repo_root,
    )

    policy = json.loads((repo_root / "out_ranked_cap" / "orch_policy_table_v1.json").read_text(encoding="utf-8"))
    rows = list(policy.get("context_rows") or [])
    assert len(rows) == 1
    ranked = list(rows[0].get("ranked_actions") or [])
    assert len(ranked) == 16
