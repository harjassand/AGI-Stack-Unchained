"""Policy enumerator for SAS-MATH (v11.0)."""

from __future__ import annotations

from typing import Any


def enumerate_policies(search_config: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(search_config, dict):
        return []
    explicit = search_config.get("candidates")
    if isinstance(explicit, list) and explicit:
        out: list[dict[str, Any]] = []
        for item in explicit:
            if isinstance(item, dict) and item.get("schema_version") == "sas_math_policy_ir_v1":
                out.append(item)
        return out

    families = list(search_config.get("policy_families") or [])
    seeds = list(search_config.get("seeds") or [])
    max_attempts_list = list(search_config.get("max_attempts_per_problem") or [])
    toy_lists = list(search_config.get("toy_checker_proofs") or [])
    lean_lists = list(search_config.get("lean_tactics") or [])

    candidates: list[dict[str, Any]] = []
    for family in families:
        for seed in seeds:
            for max_attempts in max_attempts_list:
                for toy in (toy_lists or [[]]):
                    for lean in (lean_lists or [[]]):
                        policy_ir = {
                            "schema_version": "sas_math_policy_ir_v1",
                            "policy_id": "",
                            "policy_family": str(family),
                            "toy_checker_proofs": list(toy) if isinstance(toy, list) else [],
                            "lean_tactics": list(lean) if isinstance(lean, list) else [],
                            "max_attempts_per_problem": int(max_attempts),
                            "seed": int(seed),
                        }
                        candidates.append(policy_ir)
    return candidates


__all__ = ["enumerate_policies"]
