#!/usr/bin/env python3
"""Emit heavy capability probe-coverage status for a campaign pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v18_0.omega_common_v1 import load_canon_dict


_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_SH1_CAPABILITY_ID = "RSI_GE_SH1_OPTIMIZER"
_DEFAULT_SH1_PROBES = ["utility_probe_suite_default_v1", "utility_stress_probe_suite_default_v1"]


def _normalize_probe_registry(utility_policy: dict[str, Any]) -> dict[str, list[str]]:
    raw = utility_policy.get("probe_registry_v1")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for probe_id_raw, row in sorted(raw.items(), key=lambda kv: str(kv[0])):
        probe_id = str(probe_id_raw).strip()
        if not probe_id or not isinstance(row, dict):
            continue
        assets_raw = row.get("required_asset_relpaths_v1")
        if not isinstance(assets_raw, list):
            assets_raw = []
        assets = [str(item).strip().replace("\\", "/") for item in assets_raw if str(item).strip()]
        out[probe_id] = sorted(set(assets))
    return out


def _required_probe_ids_for_capability(heavy_policy: dict[str, Any] | None) -> tuple[list[str], bool]:
    if not isinstance(heavy_policy, dict):
        return [], False
    eligible_raw = heavy_policy.get("frontier_heavy_eligible_b")
    frontier_heavy_eligible_b = bool(eligible_raw) if isinstance(eligible_raw, bool) else True
    required_probe_ids = heavy_policy.get("required_probe_ids_v1")
    if isinstance(required_probe_ids, list):
        values = [str(item).strip() for item in required_probe_ids if str(item).strip()]
        return sorted(set(values)), frontier_heavy_eligible_b
    required_probe_id = str(heavy_policy.get("required_probe_id", "")).strip()
    if required_probe_id:
        return [required_probe_id], frontier_heavy_eligible_b
    fallback = [
        str(heavy_policy.get("probe_suite_id", "")).strip(),
        str(heavy_policy.get("stress_probe_suite_id", "")).strip(),
    ]
    values = [item for item in fallback if item]
    return sorted(set(values)), frontier_heavy_eligible_b


def _required_probe_suite_ids_from_utility_policy(heavy_policies: dict[str, Any]) -> list[str]:
    required: set[str] = set()
    for _capability_id, heavy_policy in sorted(heavy_policies.items(), key=lambda kv: str(kv[0])):
        if not isinstance(heavy_policy, dict):
            continue
        required_probe_ids = heavy_policy.get("required_probe_ids_v1")
        if isinstance(required_probe_ids, list):
            for item in required_probe_ids:
                probe_id = str(item).strip()
                if probe_id:
                    required.add(probe_id)
        required_probe_id = str(heavy_policy.get("required_probe_id", "")).strip()
        if required_probe_id:
            required.add(required_probe_id)
        probe_suite_id = str(heavy_policy.get("probe_suite_id", "")).strip()
        stress_probe_suite_id = str(heavy_policy.get("stress_probe_suite_id", "")).strip()
        if probe_suite_id:
            required.add(probe_suite_id)
        if stress_probe_suite_id:
            required.add(stress_probe_suite_id)
    return sorted(required)


def _report_for_pack(campaign_pack: Path) -> dict[str, Any]:
    repo_root = REPO_ROOT
    pack = load_canon_dict(campaign_pack)
    profile_rel = str(pack.get("long_run_profile_rel", "")).strip()
    if not profile_rel:
        raise RuntimeError("MISSING_LONG_RUN_PROFILE_REL")
    profile = load_canon_dict((campaign_pack.parent / profile_rel).resolve())
    utility_rel = str(profile.get("utility_policy_rel", "")).strip()
    if not utility_rel:
        raise RuntimeError("MISSING_UTILITY_POLICY_REL")
    utility_policy = load_canon_dict((campaign_pack.parent / utility_rel).resolve())
    declared_map = utility_policy.get("declared_class_by_capability")
    if not isinstance(declared_map, dict):
        raise RuntimeError("SCHEMA_FAIL")
    heavy_policies = utility_policy.get("heavy_policies")
    if not isinstance(heavy_policies, dict):
        raise RuntimeError("SCHEMA_FAIL")
    probe_registry = _normalize_probe_registry(utility_policy)
    required_suite_ids = _required_probe_suite_ids_from_utility_policy(heavy_policies)
    available_suite_ids = sorted({*probe_registry.keys(), *_DEFAULT_SH1_PROBES})
    missing_required_suite_ids = sorted(set(required_suite_ids) - set(available_suite_ids))

    rows: list[dict[str, Any]] = []

    sh1_row: dict[str, Any] = {
        "capability_id": _SH1_CAPABILITY_ID,
        "declared_class": "FRONTIER_HEAVY",
        "frontier_heavy_eligible_b": True,
        "required_probe_ids_v1": list(_DEFAULT_SH1_PROBES),
        "missing_probe_ids_v1": [],
        "missing_probe_assets_v1": [],
        "probe_covered_b": True,
        "coverage_source": "IMPLICIT_SH1_DEFAULT",
    }
    rows.append(sh1_row)

    for capability_id_raw, declared_class_raw in sorted(declared_map.items(), key=lambda kv: str(kv[0])):
        capability_id = str(capability_id_raw).strip()
        if not capability_id or capability_id == _SH1_CAPABILITY_ID:
            continue
        declared_class = str(declared_class_raw).strip().upper()
        if declared_class not in _HEAVY_DECLARED_CLASSES:
            continue
        heavy_policy = heavy_policies.get(capability_id)
        required_probe_ids, heavy_eligible_b = _required_probe_ids_for_capability(heavy_policy if isinstance(heavy_policy, dict) else None)
        missing_probe_ids = [probe_id for probe_id in required_probe_ids if probe_id not in probe_registry]
        missing_probe_assets: list[dict[str, str]] = []
        if heavy_eligible_b and not missing_probe_ids:
            for probe_id in required_probe_ids:
                for rel in probe_registry.get(probe_id, []):
                    candidate = (repo_root / rel).resolve()
                    if not candidate.exists():
                        missing_probe_assets.append({"probe_id": probe_id, "asset_relpath": rel})
        probe_covered_b = bool(
            heavy_eligible_b
            and bool(required_probe_ids)
            and (not missing_probe_ids)
            and (not missing_probe_assets)
        )
        rows.append(
            {
                "capability_id": capability_id,
                "declared_class": declared_class,
                "frontier_heavy_eligible_b": bool(heavy_eligible_b),
                "required_probe_ids_v1": list(required_probe_ids),
                "missing_probe_ids_v1": list(missing_probe_ids),
                "missing_probe_assets_v1": list(missing_probe_assets),
                "probe_covered_b": probe_covered_b,
                "coverage_source": "UTILITY_POLICY_V1",
            }
        )

    heavy_eligible_rows = [row for row in rows if bool(row.get("frontier_heavy_eligible_b", False))]
    covered_rows = [row for row in heavy_eligible_rows if bool(row.get("probe_covered_b", False))]
    missing_probe_rows = [
        row for row in heavy_eligible_rows if isinstance(row.get("missing_probe_ids_v1"), list) and row.get("missing_probe_ids_v1")
    ]
    missing_asset_rows = [
        row
        for row in heavy_eligible_rows
        if isinstance(row.get("missing_probe_assets_v1"), list) and row.get("missing_probe_assets_v1")
    ]
    return {
        "schema_name": "probe_coverage_report_v1",
        "schema_version": "v1",
        "campaign_pack_relpath": campaign_pack.relative_to(repo_root).as_posix(),
        "utility_policy_relpath": (campaign_pack.parent / utility_rel).resolve().relative_to(repo_root).as_posix(),
        "heavy_rows": rows,
        "required_suite_ids": required_suite_ids,
        "available_suite_ids": available_suite_ids,
        "missing_required_suite_ids": missing_required_suite_ids,
        "probe_suite_resolution_contract_ok_b": not bool(missing_required_suite_ids),
        "heavy_eligible_capability_ids": [str(row.get("capability_id")) for row in heavy_eligible_rows],
        "probe_covered_capability_ids": [str(row.get("capability_id")) for row in covered_rows],
        "missing_probe_capability_ids": [str(row.get("capability_id")) for row in missing_probe_rows],
        "missing_asset_capability_ids": [str(row.get("capability_id")) for row in missing_asset_rows],
        "has_probe_covered_heavy_b": bool(covered_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="probe_coverage_report_v1")
    parser.add_argument(
        "--campaign_pack",
        default="campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json",
    )
    parser.add_argument("--fail_if_no_probe_covered_heavy", action="store_true")
    args = parser.parse_args()

    campaign_pack = (REPO_ROOT / str(args.campaign_pack)).resolve()
    report = _report_for_pack(campaign_pack)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    if bool(args.fail_if_no_probe_covered_heavy) and (not bool(report.get("has_probe_covered_heavy_b", False))):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
