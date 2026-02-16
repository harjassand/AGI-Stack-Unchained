"""Env gridworld v1 domain config and candidate templates."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from orchestrator.types import Candidate

DOMAIN_ID = "env-gridworld-v1"


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
        dev_config = cdel_repo_root / "configs" / "sealed_env_dev.toml"
        heldout_config = cdel_repo_root / "configs" / "sealed_env_heldout.toml"
    return DomainSpec(
        concept="gridworld",
        baseline_symbol="policy_base",
        oracle_symbol="policy_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
    )


def candidate_templates(*, concept: str, rng_seed: int) -> list[Candidate]:
    rng = random.Random(rng_seed)
    name = f"{concept}_greedy_{rng.randint(1000, 9999)}"
    params = [
        {"name": "agent_x", "type": {"tag": "int"}},
        {"name": "agent_y", "type": {"tag": "int"}},
        {"name": "goal_x", "type": {"tag": "int"}},
        {"name": "goal_y", "type": {"tag": "int"}},
    ]
    body = {
        "tag": "if",
        "cond": {
            "tag": "prim",
            "op": "lt_int",
            "args": [
                {"tag": "var", "name": "agent_x"},
                {"tag": "var", "name": "goal_x"},
            ],
        },
        "then": {"tag": "int", "value": 3},
        "else": {
            "tag": "if",
            "cond": {
                "tag": "prim",
                "op": "lt_int",
                "args": [
                    {"tag": "var", "name": "goal_x"},
                    {"tag": "var", "name": "agent_x"},
                ],
            },
            "then": {"tag": "int", "value": 2},
            "else": {
                "tag": "if",
                "cond": {
                    "tag": "prim",
                    "op": "lt_int",
                    "args": [
                        {"tag": "var", "name": "agent_y"},
                        {"tag": "var", "name": "goal_y"},
                    ],
                },
                "then": {"tag": "int", "value": 0},
                "else": {
                    "tag": "if",
                    "cond": {
                        "tag": "prim",
                        "op": "lt_int",
                        "args": [
                            {"tag": "var", "name": "goal_y"},
                            {"tag": "var", "name": "agent_y"},
                        ],
                    },
                    "then": {"tag": "int", "value": 1},
                    "else": {"tag": "int", "value": 0},
                },
            },
        },
    }
    payload = {
        "new_symbols": [name],
        "definitions": [
            {
                "name": name,
                "params": params,
                "ret_type": {"tag": "int"},
                "body": body,
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": concept, "symbol": name}],
    }
    return [Candidate(name=name, payload=payload, proposer="env-template", notes="greedy-policy")]
