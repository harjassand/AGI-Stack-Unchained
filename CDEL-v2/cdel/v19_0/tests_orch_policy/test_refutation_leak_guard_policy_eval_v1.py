from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

import cdel.v19_0.verify_orch_policy_bundle_v1 as eval_module

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _build_policy_bundle(context_key: str, selected_capability_id: str) -> tuple[dict, str]:
    table_payload = {
        "schema_version": "orch_policy_table_v1",
        "policy_table_id": "sha256:" + ("0" * 64),
        "rows": [
            {
                "context_key": str(context_key),
                "ranked_capabilities": [{"capability_id": str(selected_capability_id), "score_q32": 1}],
            }
        ],
    }
    table_payload["policy_table_id"] = _sha_obj(
        {
            "schema_version": str(table_payload["schema_version"]),
            "rows": list(table_payload["rows"]),
        }
    )
    bundle_payload = {
        "schema_version": "orch_policy_bundle_v1",
        "policy_bundle_id": "sha256:" + ("0" * 64),
        "policy_table_id": str(table_payload["policy_table_id"]),
        "policy_table": dict(table_payload),
    }
    bundle_payload["policy_bundle_id"] = _sha_obj(
        {
            "schema_version": str(bundle_payload["schema_version"]),
            "policy_table_id": str(bundle_payload["policy_table_id"]),
            "policy_table": dict(bundle_payload["policy_table"]),
        }
    )
    return bundle_payload, str(bundle_payload["policy_bundle_id"])


def test_refutation_leak_guard_policy_eval_v1(tmp_path: Path, monkeypatch) -> None:
    context_key = "sha256:" + ("a" * 64)
    selected_capability = "CAP_LEAK_SENTINEL"
    holdout_rows = [
        {
            "context_key": context_key,
            "action_capability_id": selected_capability,
            "reward_q32": 1,
            "toxic_fail_b": False,
            "eligible_capability_ids": [selected_capability],
        }
    ]

    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_dir = state_root / "dispatch" / "tick_0001"
    (state_root.parent / "config").mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    bundle_payload, _bundle_id = _build_policy_bundle(context_key=context_key, selected_capability_id=selected_capability)
    candidate_path = dispatch_dir / "candidate.orch_policy_bundle_v1.json"
    write_canon_json(candidate_path, bundle_payload)

    def _fake_load_and_pin_eval_config(*, config_dir: Path, state_root: Path) -> tuple[dict, list[dict]]:
        del config_dir
        del state_root
        return (
            {
                "schema_version": "orch_policy_eval_config_v1",
                "holdout_dataset_id": "sha256:" + ("b" * 64),
                "min_delta_q32": 0,
                "min_coverage_q32": 0,
                "max_toxic_increase_q32": 0,
                "baseline_kind": "ACTIVE_POLICY",
            },
            holdout_rows,
        )

    def _fake_load_active_policy_lookup(*, state_root: Path) -> tuple[str, dict[str, list[dict]]]:
        del state_root
        return "sha256:" + ("f" * 64), {}

    monkeypatch.setattr(eval_module, "_load_and_pin_eval_config", _fake_load_and_pin_eval_config)
    monkeypatch.setattr(eval_module, "_load_active_policy_lookup", _fake_load_active_policy_lookup)

    receipt, receipt_id = eval_module.verify_orch_policy_bundle_v1(
        tick_u64=1,
        dispatch_ctx={
            "state_root": str(state_root),
            "dispatch_dir": str(dispatch_dir),
        },
        candidate_bundle_path=candidate_path,
    )
    receipt_json = json.dumps(receipt, sort_keys=True)
    assert "context_key" not in receipt_json
    assert "eligible_capability_ids" not in receipt_json
    assert selected_capability not in receipt_json
    assert context_key not in receipt_json

    receipt_path = dispatch_dir / "promotion" / f"sha256_{receipt_id.split(':', 1)[1]}.orch_policy_eval_receipt_v1.json"
    written_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    written_json = json.dumps(written_payload, sort_keys=True)
    assert "context_key" not in written_json
    assert "eligible_capability_ids" not in written_json
    assert selected_capability not in written_json
    assert context_key not in written_json
