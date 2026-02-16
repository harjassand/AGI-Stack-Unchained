from __future__ import annotations

from cdel.v1_6r.canon import sha256_prefixed, canon_bytes
from cdel.v1_6r.ctime.macro import compute_macro_id
from cdel.v1_6r.ctime.macro_cross_env import build_macro_cross_env_support_report
from cdel.v1_6r.ctime.trace import build_trace_event


def _inst_spec(env: str, inst_hash: str) -> dict:
    return {
        "schema": "instance_spec_v1",
        "schema_version": 1,
        "inst_hash": inst_hash,
        "payload": {"suite_row": {"env": env}},
    }


def test_macro_cross_env_support_report_replay() -> None:
    macro_def = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "",
        "body": [
            {"name": "RIGHT", "args": {}},
            {"name": "RIGHT", "args": {}},
        ],
        "guard": None,
        "rent_bits": 0,
    }
    macro_def["macro_id"] = compute_macro_id(macro_def)

    grid_hash = sha256_prefixed(b"grid")
    line_hash = sha256_prefixed(b"line")
    edit_hash = sha256_prefixed(b"edit")

    instance_specs = {
        grid_hash: _inst_spec("gridworld-v1", grid_hash),
        line_hash: _inst_spec("lineworld-v1", line_hash),
        edit_hash: _inst_spec("editworld-v1", edit_hash),
    }

    def _event(inst_hash: str, family_id: str, action: str, t: int) -> dict:
        return build_trace_event(
            epoch_id="epoch_1",
            t_step=t,
            family_id=family_id,
            inst_hash=inst_hash,
            action_name=action,
            action_args={},
            macro_id=None,
            obs_hash=sha256_prefixed(canon_bytes({"t": t})),
            post_obs_hash=sha256_prefixed(canon_bytes({"t": t + 1})),
            receipt_hash="sha256:" + "0" * 64,
            duration_steps=1,
        )

    trace_events = [
        _event(grid_hash, "fam_grid", "RIGHT", 0),
        _event(grid_hash, "fam_grid", "RIGHT", 1),
        _event(grid_hash, "fam_grid", "RIGHT", 2),
        _event(grid_hash, "fam_grid", "RIGHT", 3),
        _event(line_hash, "fam_line", "LEFT", 0),
        _event(edit_hash, "fam_edit", "RIGHT", 0),
        _event(edit_hash, "fam_edit", "RIGHT", 1),
    ]

    report_a = build_macro_cross_env_support_report(
        epoch_id="epoch_1",
        trace_events=trace_events,
        macro_defs=[macro_def],
        macro_active_set_hash="sha256:" + "0" * 64,
        instance_specs=instance_specs,
    )
    report_b = build_macro_cross_env_support_report(
        epoch_id="epoch_1",
        trace_events=trace_events,
        macro_defs=[macro_def],
        macro_active_set_hash="sha256:" + "0" * 64,
        instance_specs=instance_specs,
    )

    assert report_a == report_b
    macro = report_a["macros"][0]
    assert macro["support_envs_hold"] == 2
    assert macro["occurrences_by_env_kind"]["editworld-v1"] > 0
