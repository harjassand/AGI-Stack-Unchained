from __future__ import annotations

from cdel.v1_7r.demon.trace import build_trace_event_v2
from cdel.v1_7r.hashutil import compute_self_hash
from cdel.v1_7r.ontology_v3.train import train_snapshot


def _hash_str(s: str) -> str:
    return "sha256:" + (s * 64)[:64]


def _event(t_step: int, action_name: str) -> dict:
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
        onto_ctx_hash=_hash_str("f"),
        active_ontology_id=None,
        active_snapshot_id=None,
    )


def _ontology_def() -> dict:
    concept = {
        "concept_id": "__SELF__",
        "concept_name": "t_step_mod2",
        "output_type": "i32",
        "expr": {"op": "get", "args": [], "path": ["t_step"]},
        "bucketer": {"kind": "mod_m", "m": 2},
    }
    concept["concept_id"] = compute_self_hash(concept, "concept_id")

    ontology_def = {
        "schema": "ontology_def_v3",
        "schema_version": 3,
        "dsl_version": 3,
        "ontology_id": "__SELF__",
        "concepts": [concept],
        "context_kernel": {"schema": "onto_context_kernel_spec_v1", "schema_version": 1, "max_arity": 8},
        "training": {
            "schema": "onto_training_spec_v1",
            "schema_version": 1,
            "method": "greedy_forward_select_v1",
            "stop_if_gain_bits_lt": 64,
        },
        "x-meta": {"KERNEL_HASH": "k", "META_HASH": "m", "constants_hash": "c"},
    }
    ontology_def["ontology_id"] = compute_self_hash(ontology_def, "ontology_id")
    return ontology_def


def test_ontology_v3_training_determinism() -> None:
    events = [_event(i, "act_0" if i % 2 == 0 else "act_1") for i in range(8)]
    ontology_def = _ontology_def()

    snapshot1 = train_snapshot(
        ontology_def=ontology_def,
        events=events,
        epoch_id="epoch_1",
        window_epochs=[1, 2],
        corpus_hash=_hash_str("1"),
        meta={"KERNEL_HASH": "k", "META_HASH": "m", "constants_hash": "c"},
    )
    snapshot2 = train_snapshot(
        ontology_def=ontology_def,
        events=events,
        epoch_id="epoch_1",
        window_epochs=[1, 2],
        corpus_hash=_hash_str("1"),
        meta={"KERNEL_HASH": "k", "META_HASH": "m", "constants_hash": "c"},
    )

    assert snapshot1["snapshot_id"] == snapshot2["snapshot_id"]
    assert (
        snapshot1["context_kernel_state"]["selected_concept_ids"]
        == snapshot2["context_kernel_state"]["selected_concept_ids"]
    )
