from __future__ import annotations

from tools.arena.proposer_arena_v1 import _deterministic_rank_and_select


def test_proposer_arena_selection_determinism_v1() -> None:
    rows = [
        {
            "candidate_id": "sha256:" + ("1" * 64),
            "surrogate_score_q32": 20,
            "surrogate_cost_q32": 3,
            "risk_class": "LOW",
        },
        {
            "candidate_id": "sha256:" + ("2" * 64),
            "surrogate_score_q32": 20,
            "surrogate_cost_q32": 3,
            "risk_class": "LOW",
        },
        {
            "candidate_id": "sha256:" + ("3" * 64),
            "surrogate_score_q32": 10,
            "surrogate_cost_q32": 1,
            "risk_class": "MED",
        },
    ]

    ranked_a, winner_a = _deterministic_rank_and_select(rows)
    ranked_b, winner_b = _deterministic_rank_and_select(rows)

    assert [str(row.get("candidate_id")) for row in ranked_a] == [str(row.get("candidate_id")) for row in ranked_b]
    assert winner_a is not None and winner_b is not None
    assert str(winner_a.get("candidate_id")) == str(winner_b.get("candidate_id"))
