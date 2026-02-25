from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.orch_worldmodel.pack_orch_policy_bundle_v1 import pack_orch_policy_bundle

from ._orch_worldmodel_test_utils_v1 import (
    make_transition_event,
    write_dataset_manifest,
    write_train_config,
    write_transition_blob,
)


def test_policy_bundle_hash_binding_v1(tmp_path: Path) -> None:
    repo_root = tmp_path.resolve()
    events = [
        make_transition_event(
            run_id="run_bundle",
            tick_u64=1,
            context_key="sha256:" + ("0" * 64),
            lane_kind="BASELINE",
            objective_kind="RUN_CAMPAIGN",
            action_capability_id="cap_a",
            reward_q32=1,
            cost_norm_q32=0,
            toxic_fail_b=False,
            next_context_key="sha256:" + ("0" * 64),
        )
    ]
    blob_path = repo_root / "blobs" / "bundle_events.jsonl"
    blob_id, _ = write_transition_blob(path=blob_path, events=events)

    manifest_path = repo_root / "manifests" / "bundle_manifest.json"
    write_dataset_manifest(
        repo_root=repo_root,
        manifest_path=manifest_path,
        transition_events_relpath=blob_path.relative_to(repo_root).as_posix(),
        transition_events_blob_id=blob_id,
        ek_id="sha256:" + ("7" * 64),
        kernel_ledger_id="sha256:" + ("8" * 64),
        included_run_ids=["run_bundle"],
        events_included_u64=1,
    )

    train_config_path = write_train_config(repo_root / "train_config.json")

    policy_no_id = {
        "schema_version": "orch_policy_table_v1",
        "ek_id": "sha256:" + ("7" * 64),
        "kernel_ledger_id": "sha256:" + ("8" * 64),
        "mode": "ADD_BONUS_V1",
        "context_rows": [
            {
                "context_key": "sha256:" + ("0" * 64),
                "ranked_actions": [{"capability_id": "cap_a", "score_q32": 1}],
            }
        ],
        "defaults": {
            "unknown_context_bonus_q32": 0,
            "max_ranked_actions_u32": 16,
        },
    }
    policy_id = str(canon_hash_obj(policy_no_id))
    policy_payload = dict(policy_no_id)
    policy_payload["policy_id"] = policy_id

    policy_path = repo_root / "policy_table.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(policy_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    out_root = repo_root / "daemon" / "orch_policy"
    summary_a = pack_orch_policy_bundle(
        policy_table_path=policy_path,
        train_config_path=train_config_path,
        transition_dataset_manifest_path=manifest_path,
        out_root=out_root,
        notes="",
        repo_root=repo_root,
    )
    summary_b = pack_orch_policy_bundle(
        policy_table_path=policy_path,
        train_config_path=train_config_path,
        transition_dataset_manifest_path=manifest_path,
        out_root=out_root,
        notes="",
        repo_root=repo_root,
    )

    assert summary_a["bundle_id"] == summary_b["bundle_id"]

    bundle_payload = json.loads(Path(str(summary_a["plain_bundle_path"])).read_text(encoding="utf-8"))
    bundle_no_id = dict(bundle_payload)
    bundle_no_id.pop("bundle_id", None)
    assert str(bundle_payload.get("bundle_id", "")) == str(canon_hash_obj(bundle_no_id))
    assert str(bundle_payload.get("policy_table_id", "")) == policy_id

    policy_relpath = str(bundle_payload.get("policy_table_relpath", ""))
    policy_blob_path = (repo_root / policy_relpath).resolve()
    assert policy_blob_path.exists()

    observed_sha = "sha256:" + __import__("hashlib").sha256(policy_blob_path.read_bytes()).hexdigest()
    artifacts = [row for row in list(bundle_payload.get("artifacts") or []) if isinstance(row, dict)]
    policy_artifacts = [row for row in artifacts if str(row.get("relpath", "")) == policy_relpath]
    assert len(policy_artifacts) == 1
    assert observed_sha == str(policy_artifacts[0].get("sha256", ""))
