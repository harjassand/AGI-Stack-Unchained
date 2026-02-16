from __future__ import annotations

from cdel.v1_5r.barrier import advance_barrier_state, barrier_scalar
from cdel.v1_5r.ctime.tokenization import build_macro_tokenization_report, build_rho_report


def _trace_events(actions: list[str]) -> list[dict]:
    events = []
    for idx, name in enumerate(actions):
        events.append(
            {
                "schema": "trace_event_v1",
                "schema_version": 1,
                "epoch_id": "epoch_test",
                "t_step": idx,
                "family_id": "sha256:" + "1" * 64,
                "inst_hash": "sha256:" + "2" * 64,
                "action": {"name": name, "args": {}},
                "macro_id": None,
                "obs_hash": "sha256:" + "3" * 64,
                "post_obs_hash": "sha256:" + "4" * 64,
                "receipt_hash": "sha256:" + "5" * 64,
                "duration_steps": 1,
            }
        )
    return events


def test_rho_increases_when_macro_matches_heldout() -> None:
    trace = _trace_events(["A", "B", "C", "A", "B", "C", "A", "B", "C", "A", "B", "C"])
    macro = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "sha256:" + "9" * 64,
        "body": [{"name": "A", "args": {}}, {"name": "B", "args": {}}, {"name": "C", "args": {}}],
        "guard": None,
        "admission_epoch": 0,
        "rent_bits": 0,
    }
    report = build_macro_tokenization_report(
        epoch_id="epoch_test",
        trace_events=trace,
        macro_defs=[macro],
        macro_active_set_hash="sha256:" + "7" * 64,
        trace_corpus_hashes=["sha256:" + "8" * 64],
    )
    rho = build_rho_report(epoch_id="epoch_test", tokenization_report=report)
    assert rho["rho_num"] > 0


def test_barrier_scalar_changes_when_workvec_changes() -> None:
    workvec_a = {"verifier_gas_total": 10}
    workvec_b = {"verifier_gas_total": 42}
    assert barrier_scalar(workvec_a) != barrier_scalar(workvec_b)


def test_barrier_segments_close_on_recovery() -> None:
    prev = {
        "recovery_state": "INSERTED_NOT_RECOVERED",
        "start_epoch_id": "epoch_1",
        "workvec_since_last_insertion": {"verifier_gas_total": 5},
    }
    start, recovered_epoch, workvec_since, state = advance_barrier_state(
        prev_record=prev,
        frontier_changed=False,
        recovered=True,
        epoch_id="epoch_2",
        workvec_epoch={"verifier_gas_total": 7},
    )
    assert start == "epoch_1"
    assert recovered_epoch == "epoch_2"
    assert state == "RECOVERED"
    assert workvec_since["verifier_gas_total"] == 12
