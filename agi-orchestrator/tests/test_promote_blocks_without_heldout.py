from pathlib import Path

from orchestrator.cdel_client import CDELClient
from orchestrator.promote import promote_candidate
from orchestrator.types import Candidate


def _write_sealed_config(path: Path, suite_hash: str) -> None:
    content = (
        "[sealed]\n"
        "eval_harness_id = \"suite-harness-v1\"\n"
        "eval_harness_hash = \"suite-harness-hash\"\n"
        f"eval_suite_hash = \"{suite_hash}\"\n"
        "alpha_total = \"1e-4\"\n"
        "episodes = 2\n\n"
        "[sealed.alpha_schedule]\n"
        "name = \"p_series\"\n"
        "exponent = 2\n"
        "coefficient = \"0.5\"\n"
    )
    path.write_text(content, encoding="utf-8")


def test_promote_blocks_without_heldout(tmp_path: Path) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    root.mkdir()

    dev_config = tmp_path / "dev.toml"
    heldout_config = tmp_path / "heldout.toml"
    _write_sealed_config(dev_config, "dev-hash")
    _write_sealed_config(heldout_config, "heldout-hash")

    candidate_payload = {
        "new_symbols": ["cand"],
        "definitions": [
            {
                "name": "cand",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {"tag": "bool", "value": True},
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "parity", "symbol": "cand"}],
    }
    candidate = Candidate(name="cand", payload=candidate_payload, proposer="test")

    out_dir = tmp_path / "out"
    result = promote_candidate(
        client=client,
        root_dir=root,
        concept="parity",
        baseline="baseline",
        oracle="oracle",
        candidate=candidate,
        dev_config=dev_config,
        heldout_config=heldout_config,
        heldout_suites_dir=None,
        safety_config=None,
        safety_suites_dir=None,
        constraint_spec_path=None,
        seed_key="sealed-seed",
        min_dev_diff_sum=1,
        out_dir=out_dir,
    )

    assert not result.accepted
    assert result.reason == "heldout_suites_missing"
    assert not (out_dir / "adoption.json").exists()
