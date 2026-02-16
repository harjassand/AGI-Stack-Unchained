from pathlib import Path

from orchestrator.ranking import RankedCandidate, rank_candidates
from orchestrator.types import Candidate


def test_ranking_prefers_higher_diff_sum_then_smaller_ast() -> None:
    cand_a = Candidate(name="a", payload={"new_symbols": ["a"], "definitions": []}, proposer="test")
    cand_b = Candidate(name="b", payload={"new_symbols": ["b"], "definitions": []}, proposer="test")
    cand_c = Candidate(name="c", payload={"new_symbols": ["c"], "definitions": []}, proposer="test")

    ranked = rank_candidates(
        [
            RankedCandidate(candidate=cand_a, diff_sum=2, ast_nodes=10, new_symbols=1, attempt_idx=0, candidate_path=Path("a.json")),
            RankedCandidate(candidate=cand_b, diff_sum=2, ast_nodes=3, new_symbols=1, attempt_idx=1, candidate_path=Path("b.json")),
            RankedCandidate(candidate=cand_c, diff_sum=4, ast_nodes=20, new_symbols=1, attempt_idx=2, candidate_path=Path("c.json")),
        ]
    )

    assert [entry.candidate.name for entry in ranked] == ["c", "b", "a"]
