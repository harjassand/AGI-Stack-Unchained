from __future__ import annotations

from cdel.v1_7r.demon.trace import build_trace_event_v2
from cdel.v1_7r.hashutil import compute_self_hash
from cdel.v1_7r.macros_v2.io import compute_rent_bits
from cdel.v1_7r.macros_v2.mdl import compute_ctx_mdl_gain


def _hash_str(ch: str) -> str:
    return "sha256:" + (ch * 64)[:64]


def _event(t_step: int, ctx_hash: str, action_name: str) -> dict:
    return build_trace_event_v2(
        t_step=t_step,
        family_id=_hash_str("a"),
        inst_hash=_hash_str("b"),
        action_name=action_name,
        action_args={},
        obs_hash=_hash_str("c"),
        post_obs_hash=_hash_str("d"),
        receipt_hash=_hash_str("e"),
        macro_id=None,
        onto_ctx_hash=ctx_hash,
        active_ontology_id=None,
        active_snapshot_id=None,
    )


def test_macros_v2_mdl_gain_exact() -> None:
    ctx = _hash_str("1")
    events = [
        _event(0, ctx, "A"),
        _event(1, ctx, "B"),
        _event(2, ctx, "A"),
        _event(3, ctx, "B"),
    ]

    macro_def = {
        "schema": "macro_def_v2",
        "schema_version": 2,
        "macro_id": "sha256:" + "0" * 64,
        "body": [{"name": "A", "args": {}}, {"name": "B", "args": {}}],
        "guard": {"schema": "macro_guard_ctx_v1", "schema_version": 1, "ctx_hashes": [ctx]},
        "admission_epoch": 1,
        "rent_bits": 0,
    }
    macro_def["rent_bits"] = compute_rent_bits(macro_def)
    macro_def["macro_id"] = compute_self_hash(macro_def, "macro_id")

    gain = compute_ctx_mdl_gain(events=events, active_macros=[], candidate_macro=macro_def)

    expected_delta = 2
    expected_gain = 8 * expected_delta - macro_def["rent_bits"]
    assert gain["delta_tokens"] == expected_delta
    assert gain["ctx_mdl_gain_bits"] == expected_gain
