from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes
from cdel.v1_7r.macro_cross_env_support_report_v2 import compute_macro_cross_env_support_v2


def test_v1_7r_macro_cross_env_support_v2_recompute() -> None:
    # One macro shared across both env kinds.
    macro_def = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "macro_test_001",
        "rent_bits": 0,
        "body": [
            {"name": "NEXT_PARAM", "args": {}},
            {"name": "INC_VALUE", "args": {}},
        ],
    }

    inst_wm = "sha256:" + "11" * 32
    inst_causal = "sha256:" + "22" * 32

    instance_specs = {
        inst_wm: {"inst_hash": inst_wm, "payload": {"suite_row": {"env": "wmworld-v1"}}},
        inst_causal: {"inst_hash": inst_causal, "payload": {"suite_row": {"env": "causalworld-v1"}}},
    }

    # Build traces that contain the macro body twice per env, in one family each.
    trace_events = []
    for (inst_hash, family_id) in [(inst_wm, "FWM"), (inst_causal, "FCA")]:
        # actions: (NEXT_PARAM, INC_VALUE) repeated twice
        for name in ["NEXT_PARAM", "INC_VALUE", "NEXT_PARAM", "INC_VALUE"]:
            trace_events.append(
                {
                    "schema": "trace_event_v1",
                    "schema_version": 1,
                    "epoch_id": "epoch_9",
                    "t_step": 0,
                    "family_id": family_id,
                    "inst_hash": inst_hash,
                    "action": {"name": name, "args": {}},
                    "macro_id": None,
                    "obs_hash": "sha256:" + "00" * 32,
                    "post_obs_hash": "sha256:" + "00" * 32,
                    "receipt_hash": "sha256:" + "00" * 32,
                    "duration_steps": 1,
                }
            )

    report_a = compute_macro_cross_env_support_v2(
        epoch_id="epoch_9",
        trace_events=trace_events,
        macro_defs=[macro_def],
        macro_active_set_hash="sha256:" + "33" * 32,
        instance_specs=instance_specs,
    )
    report_b = compute_macro_cross_env_support_v2(
        epoch_id="epoch_9",
        trace_events=trace_events,
        macro_defs=[macro_def],
        macro_active_set_hash="sha256:" + "33" * 32,
        instance_specs=instance_specs,
    )

    assert canon_bytes(report_a) == canon_bytes(report_b)
    assert report_a["schema"] == "macro_cross_env_support_report_v2"
    assert report_a["schema_version"] == 2

    macros = report_a["macros"]
    assert isinstance(macros, list) and len(macros) == 1
    m0 = macros[0]
    assert m0["macro_id"] == "macro_test_001"
    assert m0["support_envs_hold"] == 2
    assert m0["support_total_hold_by_env_kind"]["wmworld-v1"] == 2
    assert m0["support_total_hold_by_env_kind"]["causalworld-v1"] == 2
    assert m0["support_families_hold_by_env_kind"]["wmworld-v1"] == 1
    assert m0["support_families_hold_by_env_kind"]["causalworld-v1"] == 1
