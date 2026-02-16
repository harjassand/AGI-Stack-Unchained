from __future__ import annotations

import pytest

from cdel.v1_6r.canon import sha256_prefixed
from cdel.v1_6r.constants import meta_identities, require_constants
from cdel.v1_6r.ontology_v2.dsl import evaluate_ontology, validate_ontology_def
from cdel.v1_6r.ontology_v2.io import compute_concept_id, compute_ontology_id
from cdel.v1_6r.ontology_v2.dl_metric import compute_dl_metrics
from cdel.v1_6r.ontology_v2.ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries
from cdel.v1_6r.ctime.trace import build_trace_event


def _const_def() -> dict:
    meta = meta_identities()
    concept = {
        "concept_name": "const_zero",
        "concept_id": "__SELF__",
        "output_type": "i32",
        "expr": {"op": "const_i32", "value": 0, "args": []},
    }
    concept["concept_id"] = compute_concept_id(concept)
    ontology_def = {
        "schema": "ontology_def_v2",
        "schema_version": 2,
        "dsl_version": 2,
        "ontology_id": "__SELF__",
        "concepts": [concept],
        "stateful": False,
        "x-meta": meta,
    }
    ontology_def["ontology_id"] = compute_ontology_id(ontology_def)
    return ontology_def


def test_ontology_dsl_determinism() -> None:
    constants = require_constants()
    ontology_def = _const_def()
    validate_ontology_def(ontology_def, constants=constants)
    z_core = {"obs_u32": 1, "post_obs_u32": 2, "family_u32": 3, "t_step": 0}
    out_a = evaluate_ontology(ontology_def, z_core)
    out_b = evaluate_ontology(ontology_def, z_core)
    assert out_a == out_b


def test_ontology_dsl_type_error() -> None:
    constants = require_constants()
    meta = meta_identities()
    concept = {
        "concept_name": "bad_type",
        "concept_id": "__SELF__",
        "output_type": "i32",
        "expr": {"op": "const_bool", "value": True, "args": []},
    }
    concept["concept_id"] = compute_concept_id(concept)
    ontology_def = {
        "schema": "ontology_def_v2",
        "schema_version": 2,
        "dsl_version": 2,
        "ontology_id": "__SELF__",
        "concepts": [concept],
        "stateful": False,
        "x-meta": meta,
    }
    ontology_def["ontology_id"] = compute_ontology_id(ontology_def)
    validate_ontology_def(ontology_def, constants=constants)
    with pytest.raises(Exception):
        evaluate_ontology(ontology_def, {"obs_u32": 1, "post_obs_u32": 2, "family_u32": 3, "t_step": 0})


def test_ontology_dsl_gas_limit() -> None:
    constants = require_constants()
    meta = meta_identities()
    max_nodes = int(constants.get("ontology", {}).get("ONTO_MAX_NODES_PER_CONCEPT", 0))
    leaves = [{"op": "const_i32", "value": 1, "args": []} for _ in range(max_nodes + 2)]
    while len(leaves) > 1:
        next_level = []
        for idx in range(0, len(leaves), 2):
            if idx + 1 < len(leaves):
                next_level.append({"op": "add", "args": [leaves[idx], leaves[idx + 1]]})
            else:
                next_level.append(leaves[idx])
        leaves = next_level
    expr = leaves[0]
    concept = {
        "concept_name": "too_big",
        "concept_id": "__SELF__",
        "output_type": "i32",
        "expr": expr,
    }
    concept["concept_id"] = compute_concept_id(concept)
    ontology_def = {
        "schema": "ontology_def_v2",
        "schema_version": 2,
        "dsl_version": 2,
        "ontology_id": "__SELF__",
        "concepts": [concept],
        "stateful": False,
        "x-meta": meta,
    }
    ontology_def["ontology_id"] = compute_ontology_id(ontology_def)
    with pytest.raises(Exception):
        validate_ontology_def(ontology_def, constants=constants)


def test_dl_metric_small_gain() -> None:
    ontology_def = _const_def()
    event_a = build_trace_event(
        epoch_id="epoch_1",
        t_step=0,
        family_id="sha256:" + "1" * 64,
        inst_hash="sha256:" + "2" * 64,
        action_name="A",
        action_args={},
        macro_id=None,
        obs_hash=sha256_prefixed(b"obs_a"),
        post_obs_hash=sha256_prefixed(b"post_a"),
        receipt_hash=sha256_prefixed(b"r"),
        duration_steps=1,
    )
    event_b = build_trace_event(
        epoch_id="epoch_1",
        t_step=1,
        family_id="sha256:" + "1" * 64,
        inst_hash="sha256:" + "3" * 64,
        action_name="B",
        action_args={},
        macro_id=None,
        obs_hash=sha256_prefixed(b"obs_b"),
        post_obs_hash=sha256_prefixed(b"post_b"),
        receipt_hash=sha256_prefixed(b"r2"),
        duration_steps=1,
    )
    events = [event_a, event_b]
    base = compute_dl_metrics(events=events, ontology_def=None, include_rent=False)
    new = compute_dl_metrics(events=events, ontology_def=ontology_def, include_rent=False)
    assert base.context_count == 1
    assert new.context_count == 1
    assert base.model_bits == new.model_bits
    assert base.data_bits == new.data_bits
    assert base.dl_bits == new.dl_bits


def test_ontology_ledger_chain(tmp_path) -> None:
    meta = meta_identities()
    ledger = tmp_path / "ontology_ledger_v2.jsonl"
    entry_a = build_ledger_entry(
        event="ADMIT",
        epoch_id="epoch_1",
        ontology_id="sha256:" + "a" * 64,
        ontology_def_hash="sha256:" + "b" * 64,
        admit_receipt_hash="sha256:" + "c" * 64,
        active_snapshot_hash=None,
        prev_line_hash=None,
        meta=meta,
    )
    append_ledger_entry(ledger, entry_a)
    entry_b = build_ledger_entry(
        event="ACTIVATE",
        epoch_id="epoch_1",
        ontology_id="sha256:" + "a" * 64,
        ontology_def_hash="sha256:" + "b" * 64,
        admit_receipt_hash="sha256:" + "c" * 64,
        active_snapshot_hash="sha256:" + "d" * 64,
        prev_line_hash=entry_a["line_hash"],
        meta=meta,
    )
    append_ledger_entry(ledger, entry_b)

    entries = load_ledger_entries(ledger)
    assert len(entries) == 2

    # Corrupt the ledger
    raw = ledger.read_text(encoding="utf-8").splitlines()
    raw[1] = raw[1].replace("ACTIVATE", "ADMIT")
    ledger.write_text("\n".join(raw) + "\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_ledger_entries(ledger)
