"""Python unit-test v1 domain config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.proposer.llm import ProposerLimits
from orchestrator.validation import Limits

DOMAIN_ID = "python-ut-v1"

_PYUT_LIMITS = Limits(max_new_symbols=1, max_ast_nodes=2000, max_ast_depth=2000)
_PYUT_PROPOSER_LIMITS = ProposerLimits(max_new_symbols=1, max_ast_nodes=2000, max_ast_depth=2000)


@dataclass(frozen=True)
class DomainSpec:
    concept: str
    baseline_symbol: str
    oracle_symbol: str
    dev_config: Path | None
    heldout_config: Path | None
    validation_limits: Limits | None = None
    proposer_limits: ProposerLimits | None = None


def load_domain(cdel_repo_root: Path | None = None) -> DomainSpec:
    dev_config = None
    heldout_config = None
    if cdel_repo_root is not None:
        dev_config = cdel_repo_root / "configs" / "sealed_pyut_dev.toml"
        heldout_config = cdel_repo_root / "configs" / "sealed_pyut_heldout.toml"
    return DomainSpec(
        concept="py.abs_int",
        baseline_symbol="abs_int_base",
        oracle_symbol="abs_int_oracle",
        dev_config=dev_config,
        heldout_config=heldout_config,
        validation_limits=_PYUT_LIMITS,
        proposer_limits=_PYUT_PROPOSER_LIMITS,
    )


def candidate_templates(*, concept: str, rng_seed: int) -> list:
    _ = (concept, rng_seed)
    return []
