from __future__ import annotations

from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.promote import promote_candidate_heldout
from orchestrator.types import Candidate


def _write_min_sealed_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "io-harness-v1"',
                'eval_harness_hash = "io-harness-v1-hash"',
                'eval_suite_hash = "suite-hash"',
                "episodes = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_promote_blocks_without_safety_suites(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    heldout_dir = tmp_path / "heldout"
    heldout_dir.mkdir()

    heldout_config = tmp_path / "heldout.toml"
    safety_config = tmp_path / "safety.toml"
    _write_min_sealed_config(heldout_config)
    _write_min_sealed_config(safety_config)

    candidate = Candidate(
        name="candidate_symbol",
        proposer="test",
        payload={"new_symbols": [], "definitions": [], "declared_deps": [], "specs": [], "concepts": []},
    )

    result = promote_candidate_heldout(
        client=CDELClient(),
        root_dir=root,
        concept="tooluse.file_transform",
        baseline="baseline_symbol",
        oracle="oracle_symbol",
        candidate=candidate,
        candidate_path=tmp_path / "candidate.json",
        heldout_config=heldout_config,
        heldout_suites_dir=heldout_dir,
        safety_config=safety_config,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="seed",
        out_dir=tmp_path / "out",
    )
    assert not result.accepted
    assert result.reason == "safety_suites_missing"
