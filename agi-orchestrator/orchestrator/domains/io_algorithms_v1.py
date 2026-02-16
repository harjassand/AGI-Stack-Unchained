"""I/O algorithms v1 domain config and candidate templates."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from orchestrator.types import Candidate

DOMAIN_ID = "io-algorithms-v1"


@dataclass(frozen=True)
class DomainSpec:
    concept: str
    baseline_symbol: str
    oracle_symbol: str
    dev_config: Path | None
    heldout_config: Path | None


def load_domain(cdel_repo_root: Path | None = None) -> DomainSpec:
    dev_config = None
    heldout_config = None
    if cdel_repo_root is not None:
        dev_config = cdel_repo_root / "configs" / "sealed_io_dev.toml"
        heldout_config = cdel_repo_root / "configs" / "sealed_io_heldout.toml"
    return DomainSpec(
        concept="algo.is_even",
        baseline_symbol="is_even_base",
        oracle_symbol="is_even_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
    )


def candidate_templates(*, concept: str, rng_seed: int) -> list[Candidate]:
    rng = random.Random(rng_seed)
    name = f"{concept}_mod_{rng.randint(1000, 9999)}"
    params = [{"name": "n", "type": {"tag": "int"}}]
    body = {
        "tag": "prim",
        "op": "eq_int",
        "args": [
            {
                "tag": "prim",
                "op": "mod",
                "args": [
                    {"tag": "var", "name": "n"},
                    {"tag": "int", "value": 2},
                ],
            },
            {"tag": "int", "value": 0},
        ],
    }
    payload = {
        "new_symbols": [name],
        "definitions": [
            {
                "name": name,
                "params": params,
                "ret_type": {"tag": "bool"},
                "body": body,
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": concept, "symbol": name}],
    }
    return [Candidate(name=name, payload=payload, proposer="io-template", notes="mod-2")]
