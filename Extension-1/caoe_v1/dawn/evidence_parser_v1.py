"""Evidence report parsing for CAOE v1 proposer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import load_json  # noqa: E402


class EvidenceParseError(ValueError):
    pass


def _extract_nested(report: dict[str, Any], path: list[str]) -> Any:
    cur: Any = report
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _require(report: dict[str, Any], paths: list[list[str]], label: str) -> Any:
    for path in paths:
        val = _extract_nested(report, path)
        if val is not None:
            return val
    raise EvidenceParseError(f"missing required field: {label}")


def _parse_decision(report: dict[str, Any]) -> str:
    decision = report.get("decision")
    if isinstance(decision, str):
        decision = decision.upper()
        if decision in {"PASS", "FAIL"}:
            return decision
    if isinstance(decision, bool):
        return "PASS" if decision else "FAIL"
    result = report.get("result")
    if isinstance(result, str):
        result = result.upper()
        if result in {"PASS", "FAIL"}:
            return result
    raise EvidenceParseError("decision missing or invalid")


def _parse_contracts(report: dict[str, Any]) -> dict[str, bool]:
    contracts: dict[str, bool] = {}
    raw = report.get("contracts") or report.get("contract_results") or {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, dict):
                if "pass" in val and isinstance(val["pass"], bool):
                    contracts[key] = val["pass"]
                elif "ok" in val and isinstance(val["ok"], bool):
                    contracts[key] = val["ok"]
            elif isinstance(val, bool):
                contracts[key] = val
    return contracts


def _failed_contract(report: dict[str, Any], decision: str) -> str | None:
    if decision == "PASS":
        return None
    for key in ("failed_contract", "failed_contract_id"):
        val = report.get(key)
        if isinstance(val, str) and val:
            return val
    contracts = _parse_contracts(report)
    order = ["C-ANTI", "C-DO", "C-MDL", "C-INV", "C-LIFE"]
    for name in order:
        if name in contracts and contracts[name] is False:
            return name
    return "C-INV"


def _metric(report: dict[str, Any], candidates: list[list[str]], label: str, default: Any | None = None) -> Any:
    for path in candidates:
        val = _extract_nested(report, path)
        if val is not None:
            return val
    if default is not None:
        return default
    raise EvidenceParseError(f"missing metric: {label}")


def _mdl_breakdown(bundle: Any) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return None
    required = ("k_bits_ontology", "k_bits_mechanism", "log_bits", "total_bits")
    if not all(key in bundle for key in required):
        return None
    return {
        "k_bits_ontology": bundle.get("k_bits_ontology"),
        "k_bits_mechanism": bundle.get("k_bits_mechanism"),
        "log_bits": bundle.get("log_bits"),
        "total_bits": bundle.get("total_bits"),
    }


def parse_evidence_report(path: str | Path) -> dict[str, Any]:
    report = load_json(path)
    if not isinstance(report, dict):
        raise EvidenceParseError("evidence report not an object")
    candidate_id = report.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise EvidenceParseError("candidate_id missing")

    decision = _parse_decision(report)
    failed_contract = _failed_contract(report, decision)

    heldout_wcs = _require(
        report,
        [["candidate_metrics", "c_inv", "heldout_worst_case_success"]],
        "candidate_metrics.c_inv.heldout_worst_case_success",
    )
    heldout_wcs_eval = _metric(
        report,
        [["candidate_metrics", "c_inv", "heldout_worst_case_success_eval"]],
        "candidate_metrics.c_inv.heldout_worst_case_success_eval",
        default=heldout_wcs,
    )
    heldout_wce = _require(
        report,
        [["candidate_metrics", "c_inv", "heldout_worst_case_efficiency"]],
        "candidate_metrics.c_inv.heldout_worst_case_efficiency",
    )
    heldout_mdl_bits = _require(
        report,
        [["candidate_metrics", "c_mdl", "heldout_tml_bits"]],
        "candidate_metrics.c_mdl.heldout_tml_bits",
    )
    base_bits = _require(
        report,
        [["base_metrics", "c_mdl", "heldout_tml_bits"]],
        "base_metrics.c_mdl.heldout_tml_bits",
    )
    dev_bits = _require(
        report,
        [["candidate_metrics", "c_mdl", "dev_tml_bits"]],
        "candidate_metrics.c_mdl.dev_tml_bits",
    )
    base_dev_bits = _require(
        report,
        [["base_metrics", "c_mdl", "dev_tml_bits"]],
        "base_metrics.c_mdl.dev_tml_bits",
    )
    mdl_improvement = float(base_bits) - float(heldout_mdl_bits)
    dev_mdl_improvement = float(base_dev_bits) - float(dev_bits)

    leakage = _require(
        report,
        [["candidate_metrics", "c_anti", "leakage_sensitivity"]],
        "candidate_metrics.c_anti.leakage_sensitivity",
    )
    relabel = _require(
        report,
        [["candidate_metrics", "c_anti", "relabel_sensitivity"]],
        "candidate_metrics.c_anti.relabel_sensitivity",
    )

    contracts = _parse_contracts(report)
    if "C-ANTI" not in contracts or "C-DO" not in contracts:
        raise EvidenceParseError("missing contract results for C-ANTI or C-DO")
    anti_pass = contracts.get("C-ANTI")
    do_pass = contracts.get("C-DO")

    return {
        "candidate_id": candidate_id,
        "decision": decision,
        "failed_contract": failed_contract,
        "heldout_worst_case_success": float(heldout_wcs),
        "heldout_worst_case_success_eval": float(heldout_wcs_eval) if heldout_wcs_eval is not None else float(heldout_wcs),
        "heldout_worst_case_efficiency": float(heldout_wce),
        "heldout_mdl_bits": float(heldout_mdl_bits),
        "heldout_mdl_improvement_bits": float(mdl_improvement),
        "dev_mdl_bits": float(dev_bits),
        "dev_mdl_improvement_bits": float(dev_mdl_improvement),
        "leakage_sensitivity": float(leakage),
        "relabel_sensitivity": float(relabel),
        "anti_pass": bool(anti_pass),
        "do_pass": bool(do_pass),
        "base_mdl_breakdown_dev": _mdl_breakdown(
            _extract_nested(report, ["base_metrics", "c_mdl", "dev_breakdown"])
        ),
        "base_mdl_breakdown_heldout": _mdl_breakdown(
            _extract_nested(report, ["base_metrics", "c_mdl", "heldout_breakdown"])
        ),
        "cand_mdl_breakdown_dev": _mdl_breakdown(
            _extract_nested(report, ["candidate_metrics", "c_mdl", "dev_breakdown"])
        ),
        "cand_mdl_breakdown_heldout": _mdl_breakdown(
            _extract_nested(report, ["candidate_metrics", "c_mdl", "heldout_breakdown"])
        ),
    }
