"""Legacy ontology adapter (v1.6r lineage) for Omega v18."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..omega_common_v1 import rat_q32, repo_root, validate_schema
from ..omega_common_v1 import load_canon_dict


_REGISTRY_REL = Path("polymath/registry/polymath_domain_registry_v1.json")
_PORTFOLIO_REL = Path("polymath/registry/polymath_portfolio_v1.json")


def compute_skill_report(*, tick_u64: int, state_root: Path, config_dir: Path) -> dict[str, Any]:
    _ = state_root
    _ = config_dir

    root = repo_root()
    flags: list[str] = []
    active_domains: set[str] = set()
    portfolio_domains: set[str] = set()

    registry_path = root / _REGISTRY_REL
    if registry_path.exists() and registry_path.is_file():
        registry = load_canon_dict(registry_path)
        validate_schema(registry, "polymath_domain_registry_v1")
        for row in registry.get("domains", []):
            if not isinstance(row, dict):
                continue
            if str(row.get("status", "")).strip() != "ACTIVE":
                continue
            domain_id = str(row.get("domain_id", "")).strip()
            if domain_id:
                active_domains.add(domain_id)
    else:
        flags.append("REGISTRY_MISSING")

    portfolio_path = root / _PORTFOLIO_REL
    if portfolio_path.exists() and portfolio_path.is_file():
        portfolio = load_canon_dict(portfolio_path)
        validate_schema(portfolio, "polymath_portfolio_v1")
        for row in portfolio.get("domains", []):
            if not isinstance(row, dict):
                continue
            domain_id = str(row.get("domain_id", "")).strip()
            if domain_id:
                portfolio_domains.add(domain_id)
    else:
        flags.append("PORTFOLIO_MISSING")

    overlap_u64 = len(active_domains & portfolio_domains)
    active_u64 = len(active_domains)
    consistency_q32 = rat_q32(overlap_u64, max(1, active_u64)) if active_u64 > 0 else 0
    if active_u64 > 0 and overlap_u64 < active_u64:
        flags.append("ONTOLOGY_DRIFT_DETECTED")

    return {
        "schema_version": "omega_skill_report_v1",
        "skill_id": "ONTOLOGY_V2_V1_6R",
        "tick_u64": int(tick_u64),
        "metrics": {
            "ontology_consistency_q32": {"q": int(consistency_q32)},
            "ontology_overlap_q32": {"q": int(overlap_u64)},
        },
        "flags": flags,
        "recommendations": [
            {
                "kind": "ONTOLOGY_SYNC",
                "detail": "Keep portfolio domains aligned with active registry concepts.",
            }
        ],
    }
