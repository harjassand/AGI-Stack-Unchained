from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from genesis.capsules.canonicalize import capsule_hash
from genesis.shadow_cdel.shadow_eval import ShadowResult
from genesis.shadow_cdel.nontriviality import margin_bucket


@dataclass
class ArchiveEntry:
    capsule_id: str
    capsule_hash: str
    descriptor: Dict[str, str]
    shadow_metric: float | None
    status: str
    parents: List[str]
    operators: List[str]
    metric_target: float | None
    metric_direction: str | None
    repair_depth: int
    failure_pattern_ids: List[str]


class Archive:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _descriptor(self, capsule: Dict, shadow: ShadowResult | None, repair_depth: int) -> Dict[str, str]:
        ops = capsule.get("operators_used", [])
        op_key = "+".join(sorted(set(ops))) or "none"
        entrypoints = len(capsule.get("entrypoints", []))
        loc_bucket = "small" if entrypoints <= 1 else "large"
        tests = capsule.get("evidence", {}).get("unit_tests", [])
        test_bucket = "none" if not tests else "some"
        op_history = ">".join(ops)
        op_signature = hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12] if op_history else "none"
        runtime_ms = shadow.duration_ms if shadow else 0
        if runtime_ms < 50:
            runtime_bucket = "rt_fast"
        elif runtime_ms < 200:
            runtime_bucket = "rt_medium"
        else:
            runtime_bucket = "rt_slow"
        coverage_bucket = "cov_none"
        if shadow:
            if shadow.tests_total <= 0:
                coverage_bucket = "cov_none"
            elif shadow.tests_passed >= shadow.tests_total:
                coverage_bucket = "cov_full"
            else:
                coverage_bucket = "cov_partial"
        repair_bucket = f"r{repair_depth}"
        if shadow is None:
            nontriviality = "unknown"
            base_bucket = "base_unknown"
        else:
            nt_value = getattr(shadow, "nontriviality_pass", None)
            if nt_value is True:
                nontriviality = "pass"
            elif nt_value is False:
                nontriviality = "fail"
            else:
                nontriviality = "unknown"
            base_bucket = margin_bucket(getattr(shadow, "baseline_margin", None))

        return {
            "loc_bucket": loc_bucket,
            "operator_set": op_key,
            "test_bucket": test_bucket,
            "runtime_bucket": runtime_bucket,
            "operator_history_sig": op_signature,
            "coverage_bucket": coverage_bucket,
            "repair_depth": repair_bucket,
            "nontriviality_pass": nontriviality,
            "baseline_margin_bucket": base_bucket,
        }

    def append(
        self,
        capsule: Dict,
        status: str,
        shadow_metric: float | None,
        shadow: ShadowResult | None = None,
        repair_depth: int = 0,
        failure_pattern_ids: List[str] | None = None,
    ) -> ArchiveEntry:
        metric_clause = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [{}])[0]
        metric_target = metric_clause.get("target")
        metric_direction = metric_clause.get("direction")
        failure_pattern_ids = list(failure_pattern_ids or [])
        entry = ArchiveEntry(
            capsule_id=capsule.get("capsule_id", ""),
            capsule_hash=capsule_hash(capsule),
            descriptor=self._descriptor(capsule, shadow, repair_depth),
            shadow_metric=shadow_metric,
            status=status,
            parents=list(capsule.get("parents", [])),
            operators=list(capsule.get("operators_used", [])),
            metric_target=metric_target if isinstance(metric_target, (int, float)) else None,
            metric_direction=metric_direction if isinstance(metric_direction, str) else None,
            repair_depth=repair_depth,
            failure_pattern_ids=failure_pattern_ids,
        )
        record = {
            "capsule_id": entry.capsule_id,
            "capsule_hash": entry.capsule_hash,
            "descriptor": entry.descriptor,
            "shadow_metric": entry.shadow_metric,
            "status": entry.status,
            "parents": entry.parents,
            "operators": entry.operators,
            "metric_target": entry.metric_target,
            "metric_direction": entry.metric_direction,
            "repair_depth": entry.repair_depth,
            "failure_pattern_ids": entry.failure_pattern_ids,
        }
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return entry
