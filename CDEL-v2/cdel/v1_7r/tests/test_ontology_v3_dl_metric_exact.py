from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes
from cdel.v1_7r.demon.trace import build_trace_event_v2
from cdel.v1_7r.hashutil import compute_self_hash
from cdel.v1_7r.ontology_v3.dl_metric import compute_dl_metrics


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


def test_ontology_v3_dl_metric_exact() -> None:
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

    snapshot = {
        "schema": "ontology_snapshot_v3",
        "schema_version": 3,
        "snapshot_id": "__SELF__",
        "epoch_id": "epoch_1",
        "ontology_id": ontology_def["ontology_id"],
        "trained_on": {"window_epochs": [1, 2], "corpus_hash": _hash_str("z")},
        "context_kernel_state": {
            "schema": "onto_context_kernel_state_v1",
            "schema_version": 1,
            "selected_concept_ids": [concept["concept_id"]],
            "arity": 1,
        },
        "x-meta": {"KERNEL_HASH": "k", "META_HASH": "m", "constants_hash": "c"},
    }
    snapshot["snapshot_id"] = compute_self_hash(snapshot, "snapshot_id")

    events = [_event(0, "act_0"), _event(1, "act_1"), _event(2, "act_0"), _event(3, "act_1")]

    metrics = compute_dl_metrics(events=events, ontology_def=ontology_def, snapshot=snapshot)

    rent_bits = (len(canon_bytes(ontology_def)) + len(canon_bytes(snapshot))) * 8
    # two contexts (t_step mod 2), alphabet size 2 -> action_id_bits = 1, alt_bits = 0
    model_bits = 2 * 1
    data_bits = 4  # each of the 2 contexts has 2 events, no nondefault penalty
    expected_dl_bits = rent_bits + model_bits + data_bits

    assert metrics.rent_bits == rent_bits
    assert metrics.model_bits == model_bits
    assert metrics.data_bits == data_bits
    assert metrics.dl_bits == expected_dl_bits
