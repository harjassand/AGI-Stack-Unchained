from __future__ import annotations

from tools.arena.proposer_arena_v1 import _trim_backlog


def test_proposer_arena_backlog_limits_v1() -> None:
    rows = []
    for idx in range(200):
        rows.append(
            {
                "candidate_id": f"sha256:{idx:064x}",
                "surrogate_score_q32": idx,
                "surrogate_cost_q32": 1,
                "risk_class": "LOW",
            }
        )

    trimmed = _trim_backlog(rows, backlog_max_u32=128)
    kept_scores = sorted(int(row.get("surrogate_score_q32", 0)) for row in trimmed)

    assert len(trimmed) == 128
    assert kept_scores[0] == 72
    assert kept_scores[-1] == 199
