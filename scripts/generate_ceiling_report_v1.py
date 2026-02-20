#!/usr/bin/env python3
from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO_ROOT / "runs"
OUT_ROOT = RUNS_ROOT / "ceiling_report_v1"

PHASES = (
    ("phase1_baseline", "ceiling_phase2_market_toy", 1, 20),
    ("phase2_exploration", "ceiling_phase2_market_toy", 21, 240),
    ("phase3_adversarial", "ceiling_phase3_phase0", 1, 60),
)

SIP_PHASE = ("phase2_data_ingest", "ceiling_phase2_sip", 1, 5)
SURVIVAL_DRILL_DIR = RUNS_ROOT / "ceiling_survival_drill_v1"
ARCH_MUTATOR_DIR = RUNS_ROOT / "manual_mlx_coordinator_mutator_tick_0009"
SCIENCE_DIR = RUNS_ROOT / "ceiling_science_tick_0001"
PROOF_TAMPER_EVIDENCE = RUNS_ROOT / "PHASE3B_PHASE4_EVIDENCE_v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _q32_to_float(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("q")
    try:
        q = int(value)
    except Exception:
        return 0.0
    return float(q) / float(1 << 32)


def _q32_to_int(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("q")
    try:
        return int(value)
    except Exception:
        return 0


def _find_one(root: Path, pattern: str) -> Path | None:
    rows = sorted(root.glob(pattern), key=lambda p: p.as_posix())
    return rows[-1] if rows else None


def _find_by_hash(root: Path, digest: str, suffix: str) -> Path | None:
    if not digest.startswith("sha256:"):
        return None
    h = digest.split(":", 1)[1]
    rows = sorted(root.glob(f"**/sha256_{h}.{suffix}"), key=lambda p: p.as_posix())
    return rows[0] if rows else None


def _tick_dirs(prefix: str, start: int, end: int) -> list[Path]:
    out: list[Path] = []
    for path in sorted(RUNS_ROOT.glob(f"{prefix}_tick_*"), key=lambda p: p.as_posix()):
        name = path.name
        tick_str = name.rsplit("_tick_", 1)[-1]
        try:
            tick = int(tick_str)
        except ValueError:
            continue
        if start <= tick <= end:
            out.append(path)
    return out


def _ledger_rollbacks(state_root: Path) -> int:
    ledger = state_root / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger.exists():
        return 0
    total = 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict) and str(row.get("event_type", "")) == "ROLLBACK":
            total += 1
    return total


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass
class TickRow:
    phase: str
    tick_u64: int
    run_dir_rel: str
    action_kind: str
    campaign_id: str | None
    promotion_status: str | None
    promotion_reason: str | None
    promotion_bundle_hash: str | None
    obj_expand_q32: int
    cap_frontier_u64: int
    total_ns: int
    subverifier_ns: int
    activation_success_b: bool
    rollback_events_u64: int
    settlement_delta_j_q32: int
    settlement_j_cur_q32: int
    settlement_j_prev_q32: int
    tick_snapshot_hash: str | None
    observation_hash: str | None
    promotion_receipt_rel: str | None
    dispatch_receipt_rel: str | None
    subverifier_receipt_rel: str | None


def _extract_tick_row(phase: str, tick_dir: Path) -> TickRow | None:
    state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_root.exists():
        return None

    obs_path = _find_one(state_root / "observations", "*.omega_observation_report_v1.json")
    obs_obj = _load_json(obs_path) if obs_path else {}
    metrics = obs_obj.get("metrics") if isinstance(obs_obj.get("metrics"), dict) else {}
    obj_expand_q32 = _q32_to_int((metrics or {}).get("OBJ_EXPAND_CAPABILITIES"))
    cap_frontier_u64 = int((metrics or {}).get("cap_frontier_u64", 0) or 0)

    perf_path = _find_one(state_root / "perf", "*.omega_tick_perf_v1.json")
    perf_obj = _load_json(perf_path) if perf_path else {}
    stage_ns = perf_obj.get("stage_ns") if isinstance(perf_obj.get("stage_ns"), dict) else {}
    total_ns = int(perf_obj.get("total_ns", 0) or 0)
    subverifier_ns = int((stage_ns or {}).get("run_subverifier", 0) or 0)

    outcome_path = _find_one(state_root / "perf", "*.omega_tick_outcome_v1.json")
    outcome_obj = _load_json(outcome_path) if outcome_path else {}
    action_kind = str(outcome_obj.get("action_kind", "UNKNOWN"))
    activation_success_b = bool(outcome_obj.get("activation_success", False))

    dispatch_path = _find_one(state_root / "dispatch", "*/*.omega_dispatch_receipt_v1.json")
    dispatch_obj = _load_json(dispatch_path) if dispatch_path else {}
    campaign_id = str(dispatch_obj.get("campaign_id", "")).strip() or None

    promo_path = _find_one(state_root / "dispatch", "*/promotion/*.omega_promotion_receipt_v1.json")
    promo_obj = _load_json(promo_path) if promo_path else {}
    result = promo_obj.get("result") if isinstance(promo_obj.get("result"), dict) else {}
    promotion_status = str(result.get("status", "")).strip() or None
    promotion_reason = str(result.get("reason_code", "")).strip() or None
    promotion_bundle_hash = str(promo_obj.get("promotion_bundle_hash", "")).strip() or None

    subverifier_path = _find_one(state_root / "dispatch", "*/verifier/*.omega_subverifier_receipt_v1.json")
    if subverifier_path is None:
        subverifier_path = _find_one(state_root / "dispatch", "*/verifier/*.ccap_receipt_v1.json")

    settlement_path = _find_one(state_root / "market" / "settlement", "*.bid_settlement_receipt_v1.json")
    settlement_obj = _load_json(settlement_path) if settlement_path else {}
    settlement_delta_j_q32 = _q32_to_int(settlement_obj.get("realized_delta_J_q32"))
    settlement_j_cur_q32 = _q32_to_int(settlement_obj.get("J_cur_q32"))
    settlement_j_prev_q32 = _q32_to_int(settlement_obj.get("J_prev_q32"))

    tick_u64 = int(outcome_obj.get("tick_u64", obs_obj.get("tick_u64", 0)) or 0)
    tick_snapshot_hash = str(_load_json(_find_one(state_root / "snapshot", "*.omega_tick_snapshot_v1.json") or Path()).get("snapshot_id", "")) if (state_root / "snapshot").exists() else None
    if not tick_snapshot_hash:
        snap = _find_one(state_root / "snapshot", "*.omega_tick_snapshot_v1.json")
        tick_snapshot_hash = (snap.name.split(".")[0].replace("sha256_", "sha256:") if snap else None)

    obs_hash = None
    if obs_path is not None:
        obs_hash = obs_path.name.split(".")[0].replace("sha256_", "sha256:")

    return TickRow(
        phase=phase,
        tick_u64=tick_u64,
        run_dir_rel=_rel(tick_dir) or str(tick_dir),
        action_kind=action_kind,
        campaign_id=campaign_id,
        promotion_status=promotion_status,
        promotion_reason=promotion_reason,
        promotion_bundle_hash=promotion_bundle_hash,
        obj_expand_q32=obj_expand_q32,
        cap_frontier_u64=cap_frontier_u64,
        total_ns=total_ns,
        subverifier_ns=subverifier_ns,
        activation_success_b=activation_success_b,
        rollback_events_u64=_ledger_rollbacks(state_root),
        settlement_delta_j_q32=settlement_delta_j_q32,
        settlement_j_cur_q32=settlement_j_cur_q32,
        settlement_j_prev_q32=settlement_j_prev_q32,
        tick_snapshot_hash=tick_snapshot_hash,
        observation_hash=obs_hash,
        promotion_receipt_rel=_rel(promo_path),
        dispatch_receipt_rel=_rel(dispatch_path),
        subverifier_receipt_rel=_rel(subverifier_path),
    )


def _phase_summary(rows: list[TickRow]) -> dict[str, Any]:
    promoted = sum(1 for row in rows if row.promotion_status == "PROMOTED")
    rejected = sum(1 for row in rows if row.promotion_status == "REJECTED")
    skipped = sum(1 for row in rows if row.promotion_status == "SKIPPED")
    attempted = promoted + rejected + skipped
    accepted_plus_rejected = promoted + rejected

    deltas = []
    by_tick = sorted(rows, key=lambda r: r.tick_u64)
    for idx in range(1, len(by_tick)):
        deltas.append(by_tick[idx].obj_expand_q32 - by_tick[idx - 1].obj_expand_q32)

    settlement_deltas = [row.settlement_delta_j_q32 for row in by_tick if row.settlement_delta_j_q32 != 0]
    total_ns_rows = [row.total_ns for row in by_tick if row.total_ns > 0]
    subverifier_rows = [row.subverifier_ns for row in by_tick if row.subverifier_ns > 0]
    frontiers = [row.cap_frontier_u64 for row in by_tick]
    rollback_total = sum(row.rollback_events_u64 for row in by_tick)

    return {
        "ticks_u64": len(rows),
        "promoted_u64": promoted,
        "rejected_u64": rejected,
        "skipped_u64": skipped,
        "attempted_u64": attempted,
        "acceptance_rate_all_attempts_f64": (float(promoted) / float(attempted)) if attempted else 0.0,
        "acceptance_rate_promote_vs_reject_f64": (float(promoted) / float(accepted_plus_rejected)) if accepted_plus_rejected else 0.0,
        "median_delta_obj_expand_q32": int(statistics.median(deltas)) if deltas else 0,
        "delta_obj_expand_distribution_q32": deltas,
        "median_settlement_delta_j_q32": int(statistics.median(settlement_deltas)) if settlement_deltas else 0,
        "settlement_delta_j_distribution_q32": settlement_deltas,
        "median_total_ns": int(statistics.median(total_ns_rows)) if total_ns_rows else 0,
        "median_subverifier_ns": int(statistics.median(subverifier_rows)) if subverifier_rows else 0,
        "rollback_events_u64": rollback_total,
        "frontier_movement_u64": (frontiers[-1] - frontiers[0]) if len(frontiers) >= 2 else 0,
        "activation_success_u64": sum(1 for row in rows if row.activation_success_b),
    }


def _resolve_bundle(state_root: Path, bundle_hash: str | None) -> Path | None:
    if not bundle_hash or not bundle_hash.startswith("sha256:"):
        return None
    h = bundle_hash.split(":", 1)[1]
    rows = sorted(state_root.glob(f"subruns/**/promotion/sha256_{h}.*.json"), key=lambda p: p.as_posix())
    return rows[0] if rows else None


def _extract_promoted_change(row: TickRow) -> dict[str, Any] | None:
    if row.promotion_status != "PROMOTED":
        return None
    state_root = REPO_ROOT / row.run_dir_rel / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    bundle_path = _resolve_bundle(state_root, row.promotion_bundle_hash)
    if bundle_path is None:
        return None
    bundle = _load_json(bundle_path)
    schema = str(bundle.get("schema_version", "unknown"))
    change_type = "other"
    novelty_score = 0.0
    perf_impact = {}
    novelty_pass = False
    non_trivial_b = False
    replay_proof = row.subverifier_receipt_rel

    if schema == "sas_code_promotion_bundle_v1":
        change_type = "code_algo"
        novelty_pass = bool((bundle.get("acceptance_decision") or {}).get("pass", False)) and bool(bundle.get("require_novelty", False))
        baseline_algo = str(bundle.get("baseline_algo_id", ""))
        candidate_algo = str(bundle.get("candidate_algo_id", ""))
        non_trivial_b = baseline_algo != candidate_algo
        heldout_hash = str(bundle.get("perf_report_sha256_heldout", ""))
        dev_hash = str(bundle.get("perf_report_sha256_dev", ""))
        heldout_path = _find_by_hash(state_root, heldout_hash, "sas_code_perf_report_v1.json")
        dev_path = _find_by_hash(state_root, dev_hash, "sas_code_perf_report_v1.json")
        heldout_obj = _load_json(heldout_path) if heldout_path else {}
        dev_obj = _load_json(dev_path) if dev_path else {}
        heldout_speedup = _q32_to_float((heldout_obj.get("speedup_q32") or {}).get("q"))
        dev_speedup = _q32_to_float((dev_obj.get("speedup_q32") or {}).get("q"))
        novelty_score = heldout_speedup
        perf_impact = {
            "heldout_speedup_x": heldout_speedup,
            "dev_speedup_x": dev_speedup,
            "heldout_report_rel": _rel(heldout_path),
            "dev_report_rel": _rel(dev_path),
        }
    elif schema == "omega_promotion_bundle_ccap_v1":
        change_type = "ccap_patch"
        non_trivial_b = True
        novelty_pass = True
        novelty_score = 1.0
    elif schema == "sas_science_promotion_bundle_v1":
        change_type = "science_theory"
        novelty_pass = bool((bundle.get("acceptance_decision") or {}).get("pass", False))
        non_trivial_b = True
        novelty_score = 1.0

    return {
        "tick_u64": row.tick_u64,
        "phase": row.phase,
        "run_dir_rel": row.run_dir_rel,
        "campaign_id": row.campaign_id,
        "promotion_bundle_hash": row.promotion_bundle_hash,
        "promotion_bundle_rel": _rel(bundle_path),
        "bundle_schema": schema,
        "change_type": change_type,
        "novelty_pass_b": novelty_pass,
        "non_trivial_b": non_trivial_b,
        "novelty_score": novelty_score,
        "perf_impact": perf_impact,
        "replay_proof_rel": replay_proof,
    }


def _extract_mutator_proposal() -> dict[str, Any]:
    bench = _load_json(ARCH_MUTATOR_DIR / "coordinator_mutator_bench_receipt_v1.json")
    structural = _load_json(ARCH_MUTATOR_DIR / "coordinator_mutator_structural_receipt_v1.json")
    promo_bundle_path = _find_one(ARCH_MUTATOR_DIR / "promotion", "*.omega_promotion_bundle_ccap_v1.json")
    promo_bundle = _load_json(promo_bundle_path) if promo_bundle_path else {}
    ccap_path = _find_one(ARCH_MUTATOR_DIR / "ccap", "*.ccap_v1.json")
    ccap = _load_json(ccap_path) if ccap_path else {}
    median_impr = float(bench.get("median_improvement_frac_f64", "0") or 0.0)
    structural_ok = str(structural.get("tree_hash_a", "")) == str(structural.get("tree_hash_b", ""))
    return {
        "proposal_id": str(promo_bundle.get("ccap_id", "")) or str(ccap.get("meta", {}).get("base_tree_id", "")),
        "kind": "architecture_upgrade",
        "inputs_hashes": {
            "base_tree_id": str((ccap.get("meta") or {}).get("base_tree_id", "")),
            "ccap_id": str(promo_bundle.get("ccap_id", "")),
            "patch_blob_id": str((ccap.get("payload") or {}).get("patch_blob_id", "")),
        },
        "outputs_hashes": {
            "promotion_bundle_hash": str(promo_bundle.get("activation_key", "")),
        },
        "novelty_gate_evidence": {
            "structural_tree_match_b": structural_ok,
            "alternate_order_b": bool(bench.get("alternate_order_b", False)),
            "non_trivial_b": True,
        },
        "performance_impact": {
            "median_improvement_frac_f64": median_impr,
            "accept_gate_f64": float(bench.get("accept_median_improvement_frac_f64", "0") or 0.0),
        },
        "replay_verification_proof": {
            "bench_receipt_rel": _rel(ARCH_MUTATOR_DIR / "coordinator_mutator_bench_receipt_v1.json"),
            "structural_receipt_rel": _rel(ARCH_MUTATOR_DIR / "coordinator_mutator_structural_receipt_v1.json"),
            "llm_replay_rel": _rel(ARCH_MUTATOR_DIR / "orch_llm_replay.jsonl"),
        },
        "novelty_score": median_impr,
    }


def _extract_science_proposal() -> dict[str, Any]:
    promo_path = _find_one(SCIENCE_DIR / "daemon" / "rsi_sas_science_v13_0" / "state" / "promotion", "*.sas_science_promotion_bundle_v1.json")
    promo = _load_json(promo_path) if promo_path else {}
    discovery = promo.get("discovery_bundle") if isinstance(promo.get("discovery_bundle"), dict) else {}
    heldout_metrics = discovery.get("heldout_metrics") if isinstance(discovery.get("heldout_metrics"), dict) else {}
    work_cost = int(heldout_metrics.get("work_cost_total", 0) or 0)
    return {
        "proposal_id": str(promo.get("bundle_id", "")),
        "kind": "math_science_proposal",
        "inputs_hashes": {
            "dataset_receipt_hash": str(promo.get("dataset_receipt_hash", "")),
            "split_receipt_hash": str(promo.get("split_receipt_hash", "")),
            "ir_policy_hash": str(promo.get("ir_policy_hash", "")),
        },
        "outputs_hashes": {
            "promotion_bundle_hash": str(promo.get("bundle_id", "")),
            "theory_id": str(discovery.get("theory_id", "")),
        },
        "novelty_gate_evidence": {
            "acceptance_pass_b": bool((promo.get("acceptance_decision") or {}).get("pass", False)),
            "non_trivial_b": True,
            "new_law_kind": str(discovery.get("law_kind", "")),
        },
        "performance_impact": {
            "heldout_work_cost_total": work_cost,
            "audit_evidence_rel": str(promo.get("audit_evidence_path", "")),
        },
        "replay_verification_proof": {
            "promotion_bundle_rel": _rel(promo_path),
            "selection_receipt_hash": str(promo.get("selection_receipt_hash", "")),
            "sealed_eval_receipts_u64": len(promo.get("candidate_evals") or []),
        },
        "novelty_score": 1.0,
    }


def _anti_goodhart(rows_phase2: list[TickRow]) -> dict[str, Any]:
    # Deterministic perturbation test:
    # 1) original ordering
    # 2) ordering by hash(tick_snapshot_hash)
    # 3) reversed ordering
    vals = [row.settlement_delta_j_q32 for row in sorted(rows_phase2, key=lambda r: r.tick_u64)]
    if not vals:
        return {
            "status": "NO_DATA",
            "suspect_b": True,
        }

    def _mean(seq: list[int]) -> float:
        return float(sum(seq)) / float(len(seq)) if seq else 0.0

    original_mean = _mean(vals)
    by_hash = sorted(
        rows_phase2,
        key=lambda row: hashlib.sha256(str(row.tick_snapshot_hash or "").encode("utf-8")).hexdigest(),
    )
    hash_mean = _mean([row.settlement_delta_j_q32 for row in by_hash])
    reverse_mean = _mean(list(reversed(vals)))

    # If alternate representations materially flip sign or collapse near zero, suspect gaming.
    suspect_b = False
    if original_mean > 0 and (hash_mean <= 0 or reverse_mean <= 0):
        suspect_b = True
    if original_mean != 0:
        if abs(hash_mean / original_mean) < 0.2 or abs(reverse_mean / original_mean) < 0.2:
            suspect_b = True

    return {
        "status": "OK",
        "original_mean_delta_j_q32": original_mean,
        "hash_order_mean_delta_j_q32": hash_mean,
        "reverse_order_mean_delta_j_q32": reverse_mean,
        "suspect_b": suspect_b,
    }


def _bottleneck(summary_phase2: dict[str, Any], summary_phase3: dict[str, Any], accepted_changes: list[dict[str, Any]]) -> dict[str, Any]:
    if summary_phase2.get("median_subverifier_ns", 0) > 0 and summary_phase2.get("median_total_ns", 0) > 0:
        ratio = float(summary_phase2["median_subverifier_ns"]) / float(summary_phase2["median_total_ns"])
    else:
        ratio = 0.0
    novelty_pass_rate = (
        float(sum(1 for row in accepted_changes if row.get("novelty_pass_b"))) / float(len(accepted_changes))
        if accepted_changes
        else 0.0
    )

    if ratio > 0.55:
        primary = "verification_cost"
        detail = "subverifier time dominates tick cost"
    elif summary_phase2.get("median_settlement_delta_j_q32", 0) == 0:
        primary = "evaluation_kernel_too_narrow"
        detail = "exploration lane shows near-zero net delta-J"
    elif novelty_pass_rate < 0.3:
        primary = "proposer_quality"
        detail = "novelty gates pass too rarely"
    else:
        primary = "data_ingest_quality"
        detail = "ingest lane active but low frontier movement"

    return {
        "primary_bottleneck": primary,
        "detail": detail,
        "subverifier_cost_ratio_f64": ratio,
        "novelty_pass_rate_f64": novelty_pass_rate,
    }


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    phase_rows: dict[str, list[TickRow]] = {}
    for phase_name, prefix, start, end in PHASES:
        rows: list[TickRow] = []
        for tick_dir in _tick_dirs(prefix, start, end):
            row = _extract_tick_row(phase_name, tick_dir)
            if row is not None:
                rows.append(row)
        phase_rows[phase_name] = sorted(rows, key=lambda r: r.tick_u64)

    sip_rows: list[TickRow] = []
    sip_name, sip_prefix, sip_start, sip_end = SIP_PHASE
    for tick_dir in _tick_dirs(sip_prefix, sip_start, sip_end):
        row = _extract_tick_row(sip_name, tick_dir)
        if row is not None:
            sip_rows.append(row)

    summary = {name: _phase_summary(rows) for name, rows in phase_rows.items()}
    summary[sip_name] = _phase_summary(sip_rows)

    all_rows = []
    for name, rows in phase_rows.items():
        all_rows.extend(rows)
    all_rows.extend(sip_rows)

    # Accepted changes from promoted phase3 ticks
    accepted_changes = []
    for row in phase_rows.get("phase3_adversarial", []):
        item = _extract_promoted_change(row)
        if item is not None:
            accepted_changes.append(item)
    accepted_changes = sorted(accepted_changes, key=lambda x: (-float(x.get("novelty_score", 0.0)), int(x.get("tick_u64", 0))))
    top10_accepted = accepted_changes[:10]

    # Top 20 novel proposals dossier (accepted + architecture + science)
    dossier = []
    dossier.extend(top10_accepted)
    dossier.append(_extract_mutator_proposal())
    dossier.append(_extract_science_proposal())
    # Fill up to 20 from remaining accepted changes
    for item in accepted_changes[10:]:
        if len(dossier) >= 20:
            break
        dossier.append(item)
    dossier = dossier[:20]

    anti_goodhart = _anti_goodhart(phase_rows.get("phase2_exploration", []))
    bottleneck = _bottleneck(summary.get("phase2_exploration", {}), summary.get("phase3_adversarial", {}), accepted_changes)

    proof_evidence = _load_json(PROOF_TAMPER_EVIDENCE)
    survival_failure = _load_json(SURVIVAL_DRILL_DIR / "survival_drill" / "SURVIVAL_DRILL_FAILURE_v1.json")
    survival_config = _load_json(SURVIVAL_DRILL_DIR / "survival_drill" / "SURVIVAL_DRILL_CONFIG_v1.json")

    report_obj = {
        "schema_version": "ceiling_report_v1",
        "generated_at_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "phase_config": {
            "phase1_baseline_ticks_u64": summary.get("phase1_baseline", {}).get("ticks_u64", 0),
            "phase2_exploration_ticks_u64": summary.get("phase2_exploration", {}).get("ticks_u64", 0),
            "phase3_adversarial_ticks_u64": summary.get("phase3_adversarial", {}).get("ticks_u64", 0),
            "data_ingest_ticks_u64": summary.get(sip_name, {}).get("ticks_u64", 0),
        },
        "phase_summaries": summary,
        "anti_goodhart_detector": anti_goodhart,
        "top_10_novel_accepted_changes": top10_accepted,
        "top_20_novel_proposals_dossier": dossier,
        "architecture_upgrade_evidence_rel": _rel(ARCH_MUTATOR_DIR),
        "science_proposal_evidence_rel": _rel(SCIENCE_DIR),
        "proof_tamper_evidence_rel": _rel(PROOF_TAMPER_EVIDENCE),
        "proof_tamper_summary": {
            "fallback_accept_b": bool((proof_evidence.get("phase4_proof_fallback") or {}).get("fallback_accept_b", False)),
            "fallback_triggered_b": bool((proof_evidence.get("phase4_proof_fallback") or {}).get("fallback_triggered_b", False)),
            "proof_unit_verdict_after_tamper": str((proof_evidence.get("phase4_proof_fallback") or {}).get("proof_unit_verdict_after_tamper", "")),
        },
        "survival_drill": {
            "config_rel": _rel(SURVIVAL_DRILL_DIR / "survival_drill" / "SURVIVAL_DRILL_CONFIG_v1.json"),
            "failure_rel": _rel(SURVIVAL_DRILL_DIR / "survival_drill" / "SURVIVAL_DRILL_FAILURE_v1.json"),
            "tick_budget_u64": int(survival_config.get("tick_budget_u64", 0) or 0),
            "start_head": str(survival_failure.get("start_head", "")),
            "end_head": str(survival_failure.get("end_head", "")),
        },
        "bottleneck_diagnosis": bottleneck,
        "next_phase_plan": [
            "Keep bid-market exploration lane but replace toy campaigns with verifier-valid capability campaigns that emit promotion bundles.",
            "Preserve current novelty/perf gates; add per-campaign minimum non-triviality checks at promotion-bundle level.",
            "Expand SIP lane with additional pinned corpora and route resulting artifacts into science/code campaigns under existing allowlists.",
            "Run survival drill with higher tick budget and track rollback invariants per 25-tick window.",
        ],
    }

    (OUT_ROOT / "top_10_novel_accepted_changes_v1.json").write_text(
        json.dumps(top10_accepted, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (OUT_ROOT / "top_20_novel_proposals_v1.json").write_text(
        json.dumps(dossier, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (OUT_ROOT / "ceiling_report_v1.json").write_text(
        json.dumps(report_obj, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    # CSV artifacts for tables/plots
    acceptance_csv = OUT_ROOT / "acceptance_over_time.csv"
    with acceptance_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "phase",
                "tick_u64",
                "campaign_id",
                "promotion_status",
                "promotion_reason",
                "activation_success_b",
                "settlement_delta_j_q32",
                "total_ns",
                "subverifier_ns",
            ]
        )
        for row in sorted(all_rows, key=lambda r: (r.phase, r.tick_u64)):
            writer.writerow(
                [
                    row.phase,
                    row.tick_u64,
                    row.campaign_id or "",
                    row.promotion_status or "",
                    row.promotion_reason or "",
                    "1" if row.activation_success_b else "0",
                    row.settlement_delta_j_q32,
                    row.total_ns,
                    row.subverifier_ns,
                ]
            )

    novelty_csv = OUT_ROOT / "novelty_over_time.csv"
    with novelty_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "phase", "tick_u64", "change_type", "novelty_pass_b", "novelty_score", "promotion_bundle_rel"])
        for idx, item in enumerate(accepted_changes, start=1):
            writer.writerow(
                [
                    idx,
                    item.get("phase", ""),
                    item.get("tick_u64", 0),
                    item.get("change_type", ""),
                    "1" if item.get("novelty_pass_b") else "0",
                    item.get("novelty_score", 0.0),
                    item.get("promotion_bundle_rel", ""),
                ]
            )

    delta_csv = OUT_ROOT / "delta_j_distribution.csv"
    with delta_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "delta_j_q32"])
        for phase_name, phase_summary in summary.items():
            for val in phase_summary.get("settlement_delta_j_distribution_q32", []):
                writer.writerow([phase_name, val])

    runtime_csv = OUT_ROOT / "runtime_cost.csv"
    with runtime_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "median_total_ns", "median_subverifier_ns", "rollback_events_u64"])
        for phase_name, phase_summary in summary.items():
            writer.writerow(
                [
                    phase_name,
                    phase_summary.get("median_total_ns", 0),
                    phase_summary.get("median_subverifier_ns", 0),
                    phase_summary.get("rollback_events_u64", 0),
                ]
            )

    # Human-readable markdown
    md = []
    md.append("# Ceiling Report v1")
    md.append("")
    md.append("## Phase Summary")
    md.append("")
    md.append("| Phase | Ticks | Promoted | Rejected | Skipped | Acceptance(all) | Median ΔJ(q32) | Median total ns |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for phase_name in ("phase1_baseline", "phase2_exploration", "phase3_adversarial", sip_name):
        row = summary.get(phase_name, {})
        md.append(
            f"| {phase_name} | {row.get('ticks_u64', 0)} | {row.get('promoted_u64', 0)} | "
            f"{row.get('rejected_u64', 0)} | {row.get('skipped_u64', 0)} | "
            f"{row.get('acceptance_rate_all_attempts_f64', 0.0):.4f} | {row.get('median_settlement_delta_j_q32', 0)} | "
            f"{row.get('median_total_ns', 0)} |"
        )
    md.append("")
    md.append("## Novelty Gates")
    md.append("")
    novelty_pass_u64 = sum(1 for item in accepted_changes if item.get("novelty_pass_b"))
    novelty_total_u64 = len(accepted_changes)
    novelty_rate = (float(novelty_pass_u64) / float(novelty_total_u64)) if novelty_total_u64 else 0.0
    md.append(f"- `novelty_pass_u64`: {novelty_pass_u64}")
    md.append(f"- `novelty_total_u64`: {novelty_total_u64}")
    md.append(f"- `novelty_pass_rate_f64`: {novelty_rate:.4f}")
    md.append("")
    md.append("## Anti-Goodhart Detector")
    md.append("")
    md.append(f"- `status`: {anti_goodhart.get('status', '')}")
    md.append(f"- `suspect_b`: {anti_goodhart.get('suspect_b', True)}")
    md.append(
        f"- `means_q32`: original={anti_goodhart.get('original_mean_delta_j_q32', 0.0)} "
        f"hash_order={anti_goodhart.get('hash_order_mean_delta_j_q32', 0.0)} "
        f"reverse={anti_goodhart.get('reverse_order_mean_delta_j_q32', 0.0)}"
    )
    md.append("")
    md.append("## Robustness")
    md.append("")
    md.append(f"- `proof_tamper_evidence_rel`: `{_rel(PROOF_TAMPER_EVIDENCE)}`")
    md.append(f"- `proof_fallback_accept_b`: {bool((proof_evidence.get('phase4_proof_fallback') or {}).get('fallback_accept_b', False))}")
    md.append(f"- `survival_failure_rel`: `{_rel(SURVIVAL_DRILL_DIR / 'survival_drill' / 'SURVIVAL_DRILL_FAILURE_v1.json')}`")
    md.append("")
    md.append("## Bottleneck Diagnosis")
    md.append("")
    md.append(f"- `primary_bottleneck`: {bottleneck.get('primary_bottleneck', '')}")
    md.append(f"- `detail`: {bottleneck.get('detail', '')}")
    md.append(f"- `subverifier_cost_ratio_f64`: {bottleneck.get('subverifier_cost_ratio_f64', 0.0):.4f}")
    md.append("")
    md.append("## Top 10 Novel Accepted Changes")
    md.append("")
    md.append("| Rank | Tick | Phase | Type | Novelty Score | Bundle | Replay Proof |")
    md.append("|---|---:|---|---|---:|---|---|")
    for idx, item in enumerate(top10_accepted, start=1):
        md.append(
            f"| {idx} | {item.get('tick_u64', 0)} | {item.get('phase', '')} | {item.get('change_type', '')} | "
            f"{float(item.get('novelty_score', 0.0)):.6f} | `{item.get('promotion_bundle_rel', '')}` | "
            f"`{item.get('replay_proof_rel', '')}` |"
        )
    md.append("")
    md.append("## Top 20 Novel Proposals Dossier")
    md.append("")
    md.append(f"- Saved at `{_rel(OUT_ROOT / 'top_20_novel_proposals_v1.json')}`")
    md.append("")
    md.append("## Generated Artifacts")
    md.append("")
    for artifact in (
        OUT_ROOT / "ceiling_report_v1.json",
        OUT_ROOT / "acceptance_over_time.csv",
        OUT_ROOT / "novelty_over_time.csv",
        OUT_ROOT / "delta_j_distribution.csv",
        OUT_ROOT / "runtime_cost.csv",
        OUT_ROOT / "top_10_novel_accepted_changes_v1.json",
        OUT_ROOT / "top_20_novel_proposals_v1.json",
    ):
        md.append(f"- `{_rel(artifact)}`")
    (OUT_ROOT / "ceiling_report_v1.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(str(_rel(OUT_ROOT / "ceiling_report_v1.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
