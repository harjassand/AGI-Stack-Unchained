from cdel.v1_5r.sr_cegar.witness import build_failure_witness, shrink_trace


def test_shrinker_minimizes_prefix() -> None:
    events = []
    for idx in range(6):
        events.append({"action": {"name": "A"}, "t_step": idx})

    def predicate(prefix):
        return len(prefix) >= 3

    shrunk, proof = shrink_trace(events, predicate, max_gas=10)
    assert len(shrunk) == 3
    assert proof["final_prefix_steps"] == 3


def test_failure_witness_shape() -> None:
    witness = build_failure_witness(
        epoch_id="epoch",
        subject="base",
        candidate_id=None,
        family_id="sha256:" + "0" * 64,
        theta={},
        inst_hash="sha256:" + "1" * 64,
        failure_kind="GOAL_FAIL",
        trace_hashes=["sha256:" + "2" * 64],
        shrink_proof_ref=None,
    )
    assert witness["schema"] == "failure_witness_v1"
    assert witness["failure_kind"] == "GOAL_FAIL"
