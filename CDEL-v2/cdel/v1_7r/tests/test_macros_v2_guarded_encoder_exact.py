from __future__ import annotations

from cdel.v1_7r.demon.trace import build_trace_event_v2
from cdel.v1_7r.macros_v2.encoder import encode_tokens


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


def test_macros_v2_guarded_encoder_exact() -> None:
    ctx1 = _hash_str("1")
    ctx2 = _hash_str("2")
    events = [
        _event(0, ctx1, "A"),
        _event(1, ctx1, "B"),
        _event(2, ctx2, "A"),
        _event(3, ctx2, "B"),
    ]

    macro_def = {
        "schema": "macro_def_v2",
        "schema_version": 2,
        "macro_id": _hash_str("m"),
        "body": [{"name": "A", "args": {}}, {"name": "B", "args": {}}],
        "guard": {"schema": "macro_guard_ctx_v1", "schema_version": 1, "ctx_hashes": [ctx1]},
        "admission_epoch": 1,
        "rent_bits": 0,
    }

    tokens1, occurrences1 = encode_tokens(events, [macro_def])
    tokens2, occurrences2 = encode_tokens(events, [macro_def])

    assert tokens1 == 3
    assert tokens2 == 3
    assert occurrences1 == occurrences2
    assert occurrences1 == [(macro_def["macro_id"], 0, 2)]
