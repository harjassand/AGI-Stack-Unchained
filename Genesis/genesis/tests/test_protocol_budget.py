from __future__ import annotations

from pathlib import Path

from genesis.promotion.protocol_budget import (
    ProtocolCaps,
    ProtocolRequest,
    apply_promotion,
    apply_request,
    check_caps,
    load_state,
    record_attempt,
    save_state,
    snapshot,
)


def test_protocol_budget_caps(tmp_path: Path) -> None:
    state_path = tmp_path / "protocol_budget.json"
    state = load_state(state_path)
    caps = ProtocolCaps(
        max_promotions=1,
        max_cdel_calls=1,
        max_dp_queries=1,
        max_stat_queries=1,
        max_robust_queries=1,
    )
    request = ProtocolRequest(cdel_calls=1, dp_queries=1, stat_queries=1, robust_queries=1)

    ok, _ = check_caps(state, "epoch-1", caps, request)
    assert ok
    record_attempt(state, "epoch-1")
    apply_request(state, "epoch-1", request)
    apply_promotion(state, "epoch-1")
    save_state(state_path, state)

    state2 = load_state(state_path)
    snapshot_after = snapshot(state2, "epoch-1")
    assert snapshot_after["promotions"] == 1
    assert snapshot_after["cdel_calls"] == 1
    ok2, _ = check_caps(state2, "epoch-1", caps, request)
    assert not ok2
