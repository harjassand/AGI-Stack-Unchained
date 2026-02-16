from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from genesis.capsules.causal_witness import build_witness_certificate


def _capsule_id(causal_spec: Dict[str, Any], witness: Dict[str, Any]) -> str:
    payload = json.dumps(
        {"causal_spec": causal_spec, "witness": witness},
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, payload))


def build_causal_model_capsule(
    causal_spec: Dict[str, Any],
    witness: Dict[str, Any],
    config: Dict[str, Any],
    parents: List[str] | None = None,
    operators: List[str] | None = None,
    repair_depth: int = 0,
) -> Dict[str, Any]:
    metric_name = config.get("causal_metric_name", "ate_abs_error")
    target = config.get("causal_target", 0.7)
    direction = config.get("causal_direction", "minimize")
    risk_bound = config.get("causal_risk_bound", 0.7)
    nontrivial = config.get("nontriviality") or {}
    min_margin = str(nontrivial.get("causal_baseline_margin", "0.05"))

    resource_spec = {
        "max_wall_time_ms": int(config.get("causal_max_wall_time_ms", 1000)),
        "max_memory_mb": int(config.get("causal_max_memory_mb", 256)),
        "max_sample_count": int(config.get("causal_max_sample_count", 0)),
        "max_gpu_seconds": 0,
    }

    budget_bid = config.get("default_bid") or causal_spec.get("budget_bid")
    if not isinstance(budget_bid, dict):
        raise ValueError("default_bid is required for causal model capsules")

    capsule = {
        "schema_version": "1.0.1",
        "capsule_version": "1.0.0",
        "forward_compat": "x_prefix_only",
        "canonicalization": "gcj-1",
        "capsule_id": _capsule_id(causal_spec, witness),
        "artifact_type": "CAUSAL_MODEL",
        "parents": parents or [],
        "operators_used": operators or [],
        "build_hashes": {
            "ir_hash": "a" * 64,
            "container_hash": "b" * 64,
            "dependency_hashes": [],
        },
        "commitments": {
            "capsule_hash": "0" * 64,
            "checkpoint_merkle_root": "6" * 64,
        },
        "ir_payload": {
            "format": "GIR1-CAUSAL",
            "version": "1.0",
            "payload_base64": "AA==",
        },
        "entrypoints": [
            {
                "name": "estimate_effect",
                "signature": {
                    "inputs": [
                        {"name": "treatment", "type": "Tensor<float32>[n]"},
                        {"name": "outcome", "type": "Tensor<float32>[n]"},
                        {"name": "covariates", "type": "Tensor<float32>[n,d]"},
                    ],
                    "outputs": [{"name": "ate", "type": "float32"}],
                },
            }
        ],
        "effects": {
            "allow": ["read_only"],
            "deny": ["network", "filesystem_write", "process_spawn"],
        },
        "contract": {
            "functional_spec": {
                "spec_language": "DSL1",
                "clauses": [
                    {
                        "id": "fs-1",
                        "clause_type": "functional",
                        "text": "Return ATE under stated identifiability conditions.",
                    }
                ],
            },
            "safety_spec": {
                "invariants": [
                    {
                        "id": "s-1",
                        "clause_type": "safety",
                        "text": "No NaNs or infinities in ATE output.",
                    }
                ],
                "forbidden_behaviors": [],
            },
            "resource_spec": resource_spec,
            "statistical_spec": {
                "metrics": [
                    {
                        "name": metric_name,
                        "direction": direction,
                        "target": target,
                    }
                ],
                "decision_rule": "threshold",
                "confidence_requirement": {"delta": 0.001},
            },
            "robustness_spec": {
                "mode": "certified_slices",
                "slice_family": {
                    "family": "finite_template",
                    "capacity": {"parameters": {"templates": 3}},
                },
                "risk_metric": metric_name,
                "risk_bound": risk_bound,
            },
        },
        "assumptions": [],
        "budget_bid": budget_bid,
        "evidence": {
            "certificates": [build_witness_certificate(witness)],
            "unit_tests": [],
            "property_tests": [],
            "checkpoints": [],
        },
        "reproducibility": {
            "determinism_mode": "seeded",
            "seed_policy": "harness_seeded",
            "runtime_env": {
                "os": "linux",
                "arch": "x86_64",
                "kernel_isa": "KISA-1",
            },
        },
        "provenance": {
            "created_by": "genesis",
            "timestamp": "2025-01-01T00:00:00Z",
            "source_repo": "genesis",
        },
        "x-nontriviality": {
            "checks": [
                {"type": "no_nan_inf"},
                {"type": "baseline_improvement", "metric": metric_name, "min_margin": min_margin},
            ]
        },
        "x-harness": {"mode": "causal_estimate"},
        "x-causal": causal_spec,
        "x-identifiability_witness": witness,
        "x-repair_depth": repair_depth,
    }
    return capsule
