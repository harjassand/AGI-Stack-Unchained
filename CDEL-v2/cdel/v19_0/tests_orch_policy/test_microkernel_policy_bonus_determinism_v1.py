from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from orchestrator.omega_v19_0 import microkernel_v1
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import (
    Q32_ONE,
    compute_context_key,
    select_capability_id,
    select_capability_id_with_bonus,
)


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _build_policy_bundle(context_key: str) -> tuple[dict, str]:
    table_payload = {
        "schema_version": "orch_policy_table_v1",
        "policy_table_id": "sha256:" + ("0" * 64),
        "rows": [
            {
                "context_key": str(context_key),
                "ranked_capabilities": [
                    {"capability_id": "cap_a", "score_q32": -Q32_ONE},
                    {"capability_id": "cap_b", "score_q32": Q32_ONE},
                ],
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


def test_microkernel_policy_bonus_determinism_v1(tmp_path: Path) -> None:
    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    orch_root = microkernel_v1._orch_policy_root(state_root=state_root)
    store_dir = orch_root / "store"
    active_dir = orch_root / "active"
    store_dir.mkdir(parents=True, exist_ok=True)
    active_dir.mkdir(parents=True, exist_ok=True)

    context_key = compute_context_key(
        lane_kind="UNKNOWN",
        runaway_level_u32=0,
        objective_kind="RUN_CAMPAIGN",
    )
    bundle_payload, bundle_id = _build_policy_bundle(context_key=context_key)
    write_canon_json(
        store_dir / f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json",
        bundle_payload,
    )
    write_canon_json(
        active_dir / "ORCH_POLICY_V1.json",
        {
            "schema_version": "orch_policy_pointer_v1",
            "active_policy_bundle_id": str(bundle_id),
            "updated_tick_u64": 1,
        },
    )

    active_bundle_id, lookup = microkernel_v1._load_active_orch_policy_lookup(state_root=state_root)
    assert active_bundle_id == bundle_id
    assert isinstance(lookup, dict)
    row_scores = dict((lookup or {}).get(str(context_key), {}))

    config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 64,
        "max_arms_per_context_u32": 64,
        "alpha_q32": Q32_ONE // 2,
        "explore_weight_q32": 0,
        "cost_weight_q32": 0,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 0,
    }
    state = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 1,
        "parent_state_hash": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("1" * 64),
        "kernel_ledger_id": "sha256:" + ("2" * 64),
        "contexts": [
            {
                "context_key": str(context_key),
                "lane_kind": "UNKNOWN",
                "runaway_band_u32": 0,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [
                    {
                        "capability_id": "cap_a",
                        "n_u64": 10,
                        "reward_ewma_q32": (Q32_ONE * 3) // 5,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 1,
                    },
                    {
                        "capability_id": "cap_b",
                        "n_u64": 10,
                        "reward_ewma_q32": (Q32_ONE * 2) // 5,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 1,
                    },
                ],
            }
        ],
    }
    eligible = ["cap_a", "cap_b"]
    selected_without_bonus = select_capability_id(
        config=config,
        state=state,
        context_key=str(context_key),
        eligible_capability_ids=list(eligible),
    )
    assert selected_without_bonus == "cap_a"

    bonus_by_capability_q32 = {
        capability_id: microkernel_v1._clamp_orch_policy_bonus_q32(int(row_scores.get(capability_id, 0)))
        for capability_id in eligible
    }
    assert int(bonus_by_capability_q32["cap_a"]) == -(Q32_ONE // 4)
    assert int(bonus_by_capability_q32["cap_b"]) == (Q32_ONE // 4)

    seen: set[str] = set()
    for _ in range(20):
        selected_with_bonus = select_capability_id_with_bonus(
            config=config,
            state=state,
            context_key=str(context_key),
            eligible_capability_ids=list(eligible),
            bonus_by_capability_q32=bonus_by_capability_q32,
        )
        seen.add(selected_with_bonus)
    assert seen == {"cap_b"}
