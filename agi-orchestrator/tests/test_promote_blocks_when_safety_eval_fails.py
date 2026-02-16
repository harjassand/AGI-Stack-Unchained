from __future__ import annotations

import json
from pathlib import Path

from orchestrator.promote import promote_candidate_heldout
from orchestrator.types import Candidate


def _write_min_sealed_config(path: Path, suite_hash: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "tooluse-harness-v1"',
                'eval_harness_hash = "tooluse-harness-v1-hash"',
                f'eval_suite_hash = "{suite_hash}"',
                "episodes = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _make_cert(*, mantissa: str, exponent10: int) -> dict:
    return {
        "risk": {"alpha_i": "1", "evalue_threshold": "1"},
        "certificate": {"evalue": {"mantissa": mantissa, "exponent10": exponent10}},
    }


class _DummyClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def issue_stat_cert(
        self,
        *,
        root_dir: Path,
        request_path: Path,
        out_path: Path,
        config: Path,
        seed_key: str,
        suites_dir: Path | None,
        candidate_module: Path | None = None,
    ) -> None:
        mantissa = "1.00000000000000000000000"
        if "heldout" in out_path.name:
            cert = _make_cert(mantissa=mantissa, exponent10=1)
        else:
            cert = _make_cert(mantissa=mantissa, exponent10=-6)
        out_path.write_text(json.dumps(cert, sort_keys=True) + "\n", encoding="utf-8")
        self.calls.append(out_path.name)

    def commit_module(self, *args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("commit_module should not be called on safety failure")

    def adopt(self, *args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError("adopt should not be called on safety failure")


def test_promote_blocks_when_safety_eval_fails(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    heldout_dir = tmp_path / "heldout"
    heldout_dir.mkdir()
    safety_dir = tmp_path / "safety"
    safety_dir.mkdir()

    heldout_config = tmp_path / "heldout.toml"
    safety_config = tmp_path / "safety.toml"
    _write_min_sealed_config(heldout_config, "heldout-hash")
    _write_min_sealed_config(safety_config, "safety-hash")

    constraints_path = tmp_path / "constraints.json"
    constraints_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "constraint_spec",
                "domain": "tooluse",
                "constraints": {
                    "banned_tools": [],
                    "max_steps": 1,
                    "max_file_writes": 0,
                    "allow_path_escape": False,
                    "allow_network": False,
                    "allow_subprocess": False,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    candidate = Candidate(
        name="candidate_symbol",
        proposer="test",
        payload={"new_symbols": [], "definitions": [], "declared_deps": [], "specs": [], "concepts": []},
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = promote_candidate_heldout(
        client=_DummyClient(),
        root_dir=root,
        concept="tooluse.safe",
        baseline="baseline_symbol",
        oracle="oracle_symbol",
        candidate=candidate,
        candidate_path=tmp_path / "candidate.json",
        heldout_config=heldout_config,
        heldout_suites_dir=heldout_dir,
        safety_config=safety_config,
        safety_suites_dir=safety_dir,
        constraint_spec_path=constraints_path,
        seed_key="seed",
        out_dir=out_dir,
    )

    assert not result.accepted
    assert result.reason == "safety_below_threshold"
