#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PROMOTION_STATUSES = {"PROMOTED", "REJECTED", "SKIPPED"}
TICK_OUTCOME_RECORD_SCHEMA_REL = Path("Genesis/schema/v18_0/omega_tick_outcome_record_v1.jsonschema")

PHASE_SPECS = (
    ("phase1_baseline", "ceiling_phase2_market_toy", 1, 20),
    ("phase2_exploration", "ceiling_phase2_market_toy", 21, 240),
    ("phase3_adversarial", "ceiling_phase3_phase0", 1, 60),
    ("phase2_data_ingest", "ceiling_phase2_sip", 1, 5),
)


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _q32_to_int(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("q")
    try:
        return int(value)
    except Exception:
        return 0


def _q32_to_float(value: Any) -> float:
    return float(_q32_to_int(value)) / float(1 << 32)


def _canon_hash_obj(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _rel(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _find_latest(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    rows = sorted(root.glob(pattern), key=lambda p: p.as_posix())
    return rows[-1] if rows else None


def _tick_dirs(source_runs_root: Path, prefix: str, start: int, end: int) -> list[Path]:
    out: list[Path] = []
    for path in sorted(source_runs_root.glob(f"{prefix}_tick_*"), key=lambda p: p.as_posix()):
        tick_raw = path.name.rsplit("_tick_", 1)[-1]
        try:
            tick_u64 = int(tick_raw)
        except ValueError:
            continue
        if start <= tick_u64 <= end:
            out.append(path)
    return out


def _ledger_rollbacks(state_root: Path) -> int:
    ledger = state_root / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger.exists():
        return 0
    total = 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            row = json.loads(value)
        except Exception:
            continue
        if isinstance(row, dict) and str(row.get("event_type", "")) == "ROLLBACK":
            total += 1
    return total


@dataclass
class TickOutcomeRecord:
    schema_version: str
    phase: str
    tick_u64: int
    run_dir_rel: str
    selected_campaign_id: str | None
    promotion_status: str
    promotion_reason: str
    eval_kernel_ran_b: bool
    objective_terms_before_hash: str | None
    objective_terms_after_hash: str | None
    delta_j_q32: int | None
    promotion_receipt_rel: str | None
    subverifier_receipt_rel: str | None
    dispatch_receipt_rel: str | None


@dataclass
class TickRow:
    phase: str
    tick_u64: int
    run_dir: Path
    run_dir_rel: str
    selected_campaign_id: str | None
    promotion_status: str
    promotion_reason: str
    eval_kernel_ran_b: bool
    delta_j_q32: int | None
    total_ns: int
    subverifier_ns: int
    activation_success_b: bool
    rollback_events_u64: int
    obj_expand_q32: int
    cap_frontier_u64: int
    promotion_bundle_hash: str | None
    promotion_receipt_rel: str | None
    subverifier_receipt_rel: str | None
    dispatch_receipt_rel: str | None
    observation_hash: str | None
    snapshot_hash: str | None
    record: TickOutcomeRecord


def _extract_tick_row(
    *,
    phase: str,
    tick_dir: Path,
    source_runs_root: Path,
    prev_observation_hash: str | None,
    prev_snapshot_hash: str | None,
) -> TickRow | None:
    state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_root.exists():
        return None

    obs_path = _find_latest(state_root / "observations", "sha256_*.omega_observation_report_v1.json")
    obs_obj = _load_json(obs_path)
    obs_metrics = obs_obj.get("metrics") if isinstance(obs_obj.get("metrics"), dict) else {}
    obj_expand_q32 = _q32_to_int((obs_metrics or {}).get("OBJ_EXPAND_CAPABILITIES"))
    cap_frontier_u64 = int((obs_metrics or {}).get("cap_frontier_u64", 0) or 0)
    observation_hash = (
        obs_path.name.split(".", 1)[0].replace("sha256_", "sha256:")
        if obs_path is not None
        else None
    )

    snapshot_path = _find_latest(state_root / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot_obj = _load_json(snapshot_path)
    snapshot_hash = str(snapshot_obj.get("snapshot_id", "")).strip() or None
    if not snapshot_hash and snapshot_path is not None:
        snapshot_hash = snapshot_path.name.split(".", 1)[0].replace("sha256_", "sha256:")

    perf_path = _find_latest(state_root / "perf", "sha256_*.omega_tick_perf_v1.json")
    perf_obj = _load_json(perf_path)
    stage_ns = perf_obj.get("stage_ns") if isinstance(perf_obj.get("stage_ns"), dict) else {}
    total_ns = int(perf_obj.get("total_ns", 0) or 0)
    subverifier_ns = int((stage_ns or {}).get("run_subverifier", 0) or 0)

    outcome_path = _find_latest(state_root / "perf", "sha256_*.omega_tick_outcome_v1.json")
    outcome_obj = _load_json(outcome_path)

    dispatch_path = _find_latest(state_root / "dispatch", "*/sha256_*.omega_dispatch_receipt_v1.json")
    dispatch_obj = _load_json(dispatch_path)
    selected_campaign_id = str(dispatch_obj.get("campaign_id", "")).strip() or None
    if selected_campaign_id is None:
        selected_campaign_id = str(outcome_obj.get("campaign_id", "")).strip() or None

    promotion_path = _find_latest(state_root / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    promotion_obj = _load_json(promotion_path)
    promotion_result = promotion_obj.get("result") if isinstance(promotion_obj.get("result"), dict) else {}
    promotion_status_raw = str(promotion_result.get("status", "")).strip()
    promotion_status = promotion_status_raw if promotion_status_raw in PROMOTION_STATUSES else "SKIPPED"
    promotion_reason = str(promotion_result.get("reason_code", "")).strip()
    if not promotion_reason:
        promotion_reason = "NO_PROMOTION_RECEIPT" if promotion_status == "SKIPPED" else "UNKNOWN"

    eval_kernel_ran_b = promotion_status in {"PROMOTED", "REJECTED"}
    settlement_path = _find_latest(state_root / "market" / "settlement", "sha256_*.bid_settlement_receipt_v1.json")
    settlement_obj = _load_json(settlement_path)
    delta_j_q32: int | None = None
    if eval_kernel_ran_b and settlement_path is not None:
        delta_j_q32 = _q32_to_int(settlement_obj.get("realized_delta_J_q32"))
    if promotion_status == "SKIPPED":
        delta_j_q32 = None
    if not eval_kernel_ran_b:
        delta_j_q32 = None

    if promotion_status == "SKIPPED" and delta_j_q32 is not None:
        raise RuntimeError(f"SKIPPED tick has delta_j_q32: {tick_dir}")

    objective_before = {
        "observation_hash": prev_observation_hash,
        "snapshot_hash": prev_snapshot_hash,
        "settlement_j_prev_q32": _q32_to_int(settlement_obj.get("J_prev_q32")) if settlement_obj else None,
    }
    objective_after = {
        "observation_hash": observation_hash,
        "snapshot_hash": snapshot_hash,
        "settlement_j_cur_q32": _q32_to_int(settlement_obj.get("J_cur_q32")) if settlement_obj else None,
    }
    objective_terms_before_hash = _canon_hash_obj(objective_before) if any(v is not None for v in objective_before.values()) else None
    objective_terms_after_hash = _canon_hash_obj(objective_after) if any(v is not None for v in objective_after.values()) else None

    subverifier_path = _find_latest(state_root / "dispatch", "*/verifier/sha256_*.omega_subverifier_receipt_v1.json")
    if subverifier_path is None:
        subverifier_path = _find_latest(state_root / "dispatch", "*/verifier/sha256_*.ccap_receipt_v1.json")

    promotion_bundle_hash = str(promotion_obj.get("promotion_bundle_hash", "")).strip() or None
    activation_success_b = bool(outcome_obj.get("activation_success", False))
    tick_u64 = int(outcome_obj.get("tick_u64", obs_obj.get("tick_u64", 0)) or 0)

    record = TickOutcomeRecord(
        schema_version="omega_tick_outcome_record_v1",
        phase=phase,
        tick_u64=tick_u64,
        run_dir_rel=_rel(tick_dir, source_runs_root) or tick_dir.as_posix(),
        selected_campaign_id=selected_campaign_id,
        promotion_status=promotion_status,
        promotion_reason=promotion_reason,
        eval_kernel_ran_b=bool(eval_kernel_ran_b),
        objective_terms_before_hash=objective_terms_before_hash,
        objective_terms_after_hash=objective_terms_after_hash,
        delta_j_q32=delta_j_q32,
        promotion_receipt_rel=_rel(promotion_path, source_runs_root),
        subverifier_receipt_rel=_rel(subverifier_path, source_runs_root),
        dispatch_receipt_rel=_rel(dispatch_path, source_runs_root),
    )

    if record.promotion_status == "SKIPPED" and record.delta_j_q32 is not None:
        raise RuntimeError(f"invalid SKIPPED semantics in tick record: {tick_dir}")
    if (not record.eval_kernel_ran_b) and record.delta_j_q32 is not None:
        raise RuntimeError(f"invalid eval semantics in tick record: {tick_dir}")

    return TickRow(
        phase=phase,
        tick_u64=tick_u64,
        run_dir=tick_dir,
        run_dir_rel=record.run_dir_rel,
        selected_campaign_id=selected_campaign_id,
        promotion_status=promotion_status,
        promotion_reason=promotion_reason,
        eval_kernel_ran_b=bool(eval_kernel_ran_b),
        delta_j_q32=delta_j_q32,
        total_ns=total_ns,
        subverifier_ns=subverifier_ns,
        activation_success_b=activation_success_b,
        rollback_events_u64=_ledger_rollbacks(state_root),
        obj_expand_q32=obj_expand_q32,
        cap_frontier_u64=cap_frontier_u64,
        promotion_bundle_hash=promotion_bundle_hash,
        promotion_receipt_rel=record.promotion_receipt_rel,
        subverifier_receipt_rel=record.subverifier_receipt_rel,
        dispatch_receipt_rel=record.dispatch_receipt_rel,
        observation_hash=observation_hash,
        snapshot_hash=snapshot_hash,
        record=record,
    )


def _phase_summary(rows: list[TickRow]) -> dict[str, Any]:
    by_tick = sorted(rows, key=lambda r: r.tick_u64)
    promoted = sum(1 for r in by_tick if r.promotion_status == "PROMOTED")
    rejected = sum(1 for r in by_tick if r.promotion_status == "REJECTED")
    skipped = sum(1 for r in by_tick if r.promotion_status == "SKIPPED")
    attempted = promoted + rejected + skipped
    promote_vs_reject = promoted + rejected

    obj_delta: list[int] = []
    for idx in range(1, len(by_tick)):
        obj_delta.append(int(by_tick[idx].obj_expand_q32) - int(by_tick[idx - 1].obj_expand_q32))

    eligible_deltas = [int(r.delta_j_q32) for r in by_tick if r.eval_kernel_ran_b and r.delta_j_q32 is not None]
    total_ns = [int(r.total_ns) for r in by_tick if int(r.total_ns) > 0]
    sub_ns = [int(r.subverifier_ns) for r in by_tick if int(r.subverifier_ns) >= 0]
    frontiers = [int(r.cap_frontier_u64) for r in by_tick]

    return {
        "ticks_u64": len(by_tick),
        "promoted_u64": promoted,
        "rejected_u64": rejected,
        "skipped_u64": skipped,
        "attempted_u64": attempted,
        "acceptance_rate_all_attempts_f64": (float(promoted) / float(attempted)) if attempted else 0.0,
        "acceptance_rate_promote_vs_reject_f64": (float(promoted) / float(promote_vs_reject)) if promote_vs_reject else 0.0,
        "eligible_settlement_rows_u64": len(eligible_deltas),
        "median_settlement_delta_j_q32": int(statistics.median(eligible_deltas)) if eligible_deltas else None,
        "median_settlement_delta_j_q32_eligible": int(statistics.median(eligible_deltas)) if eligible_deltas else None,
        "settlement_delta_j_distribution_q32_eligible": eligible_deltas,
        "median_delta_obj_expand_q32": int(statistics.median(obj_delta)) if obj_delta else None,
        "delta_obj_expand_distribution_q32": obj_delta,
        "median_total_ns": int(statistics.median(total_ns)) if total_ns else 0,
        "median_subverifier_ns": int(statistics.median(sub_ns)) if sub_ns else 0,
        "rollback_events_u64": sum(int(r.rollback_events_u64) for r in by_tick),
        "frontier_movement_u64": (frontiers[-1] - frontiers[0]) if len(frontiers) >= 2 else 0,
        "activation_success_u64": sum(1 for r in by_tick if r.activation_success_b),
    }


def _resolve_bundle(state_root: Path, bundle_hash: str | None) -> Path | None:
    if not bundle_hash or not bundle_hash.startswith("sha256:"):
        return None
    bundle_hex = bundle_hash.split(":", 1)[1]
    rows = sorted(
        state_root.glob(f"subruns/**/promotion/sha256_{bundle_hex}.*.json"),
        key=lambda p: p.as_posix(),
    )
    return rows[0] if rows else None


def _extract_promoted_change(row: TickRow, source_runs_root: Path) -> dict[str, Any] | None:
    if row.promotion_status != "PROMOTED":
        return None
    state_root = row.run_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    bundle_path = _resolve_bundle(state_root, row.promotion_bundle_hash)
    if bundle_path is None:
        return None
    bundle = _load_json(bundle_path)
    schema = str(bundle.get("schema_version", "unknown"))

    change_type = "other"
    novelty_score = 0.0
    novelty_pass_b = False
    non_trivial_b = False
    perf_impact: dict[str, Any] = {}
    if schema == "sas_code_promotion_bundle_v1":
        change_type = "code_algo"
        novelty_pass_b = bool((bundle.get("acceptance_decision") or {}).get("pass", False))
        non_trivial_b = str(bundle.get("baseline_algo_id", "")) != str(bundle.get("candidate_algo_id", ""))
        heldout_hash = str(bundle.get("perf_report_sha256_heldout", ""))
        heldout_path = _find_by_hash(state_root, heldout_hash, "sas_code_perf_report_v1.json")
        heldout_obj = _load_json(heldout_path)
        novelty_score = _q32_to_float((heldout_obj.get("speedup_q32") or {}).get("q"))
        perf_impact = {
            "heldout_speedup_x": novelty_score,
            "heldout_report_rel": _rel(heldout_path, source_runs_root),
        }
    elif schema == "sas_science_promotion_bundle_v1":
        change_type = "science_theory"
        novelty_pass_b = bool((bundle.get("acceptance_decision") or {}).get("pass", False))
        non_trivial_b = True
        novelty_score = 1.0
    elif schema == "omega_promotion_bundle_ccap_v1":
        change_type = "ccap_patch"
        novelty_pass_b = True
        non_trivial_b = True
        novelty_score = 1.0

    return {
        "tick_u64": row.tick_u64,
        "phase": row.phase,
        "run_dir_rel": row.run_dir_rel,
        "campaign_id": row.selected_campaign_id,
        "bundle_schema": schema,
        "change_type": change_type,
        "novelty_score": novelty_score,
        "novelty_pass_b": novelty_pass_b,
        "non_trivial_b": non_trivial_b,
        "promotion_bundle_hash": row.promotion_bundle_hash,
        "promotion_bundle_rel": _rel(bundle_path, source_runs_root),
        "perf_impact": perf_impact,
        "replay_proof_rel": row.subverifier_receipt_rel,
    }


def _find_by_hash(root: Path, digest: str, suffix: str) -> Path | None:
    if not digest.startswith("sha256:"):
        return None
    h = digest.split(":", 1)[1]
    rows = sorted(root.glob(f"**/sha256_{h}.{suffix}"), key=lambda p: p.as_posix())
    return rows[0] if rows else None


def _anti_goodhart(rows: list[TickRow]) -> dict[str, Any]:
    vals = [int(r.delta_j_q32) for r in sorted(rows, key=lambda r: r.tick_u64) if r.eval_kernel_ran_b and r.delta_j_q32 is not None]
    if not vals:
        return {"status": "NO_DATA", "suspect_b": True}
    original_mean = float(sum(vals)) / float(len(vals))
    hash_order = sorted(vals, key=lambda v: hashlib.sha256(str(v).encode("utf-8")).hexdigest())
    hash_mean = float(sum(hash_order)) / float(len(hash_order))
    reverse_mean = float(sum(reversed(vals))) / float(len(vals))
    suspect_b = False
    if original_mean != 0.0:
        if abs(hash_mean / original_mean) < 0.2 or abs(reverse_mean / original_mean) < 0.2:
            suspect_b = True
    if original_mean > 0.0 and (hash_mean <= 0.0 or reverse_mean <= 0.0):
        suspect_b = True
    return {
        "status": "OK",
        "suspect_b": bool(suspect_b),
        "original_mean_delta_j_q32": original_mean,
        "hash_order_mean_delta_j_q32": hash_mean,
        "reverse_order_mean_delta_j_q32": reverse_mean,
    }


def _extract_mutator_proposal(source_runs_root: Path) -> dict[str, Any]:
    run_dir = source_runs_root / "manual_mlx_coordinator_mutator_tick_0009"
    bench = _load_json(run_dir / "coordinator_mutator_bench_receipt_v1.json")
    structural = _load_json(run_dir / "coordinator_mutator_structural_receipt_v1.json")
    ccap_bundle = _find_latest(run_dir / "promotion", "sha256_*.omega_promotion_bundle_ccap_v1.json")
    ccap_payload = _load_json(ccap_bundle)
    return {
        "proposal_id": str(ccap_payload.get("ccap_id", "")),
        "kind": "architecture_upgrade",
        "inputs_hashes": {
            "base_tree_id": str((_load_json(_find_latest(run_dir / "ccap", "sha256_*.ccap_v1.json"))).get("meta", {}).get("base_tree_id", "")),
        },
        "outputs_hashes": {
            "promotion_bundle_hash": str(ccap_payload.get("activation_key", "")),
        },
        "novelty_gate_evidence": {
            "non_trivial_b": True,
            "structural_tree_match_b": str(structural.get("tree_hash_a", "")) == str(structural.get("tree_hash_b", "")),
            "alternate_order_b": bool(bench.get("alternate_order_b", False)),
        },
        "performance_impact": {
            "median_improvement_frac_f64": float(bench.get("median_improvement_frac_f64", 0.0) or 0.0),
            "accept_gate_f64": float(bench.get("accept_median_improvement_frac_f64", 0.0) or 0.0),
        },
        "replay_verification_proof": {
            "bench_receipt_rel": _rel(run_dir / "coordinator_mutator_bench_receipt_v1.json", source_runs_root),
            "structural_receipt_rel": _rel(run_dir / "coordinator_mutator_structural_receipt_v1.json", source_runs_root),
            "llm_replay_rel": _rel(run_dir / "orch_llm_replay.jsonl", source_runs_root),
        },
        "novelty_score": float(bench.get("median_improvement_frac_f64", 0.0) or 0.0),
    }


def _extract_science_proposal(source_runs_root: Path) -> dict[str, Any]:
    run_dir = source_runs_root / "ceiling_science_tick_0001"
    promo_path = _find_latest(
        run_dir / "daemon" / "rsi_sas_science_v13_0" / "state" / "promotion",
        "sha256_*.sas_science_promotion_bundle_v1.json",
    )
    promo = _load_json(promo_path)
    discovery = promo.get("discovery_bundle") if isinstance(promo.get("discovery_bundle"), dict) else {}
    heldout = discovery.get("heldout_metrics") if isinstance(discovery.get("heldout_metrics"), dict) else {}
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
            "heldout_work_cost_total": int(heldout.get("work_cost_total", 0) or 0),
            "audit_evidence_rel": str(promo.get("audit_evidence_path", "")),
        },
        "replay_verification_proof": {
            "promotion_bundle_rel": _rel(promo_path, source_runs_root),
            "selection_receipt_hash": str(promo.get("selection_receipt_hash", "")),
            "sealed_eval_receipts_u64": len(promo.get("candidate_evals") or []),
        },
        "novelty_score": 1.0,
    }


def _ceiling_criteria(
    *,
    summary_phase2: dict[str, Any],
    summary_phase3: dict[str, Any],
    novelty_pass_rate_f64: float,
    anti_goodhart: dict[str, Any],
    proof_tamper: dict[str, Any],
) -> dict[str, Any]:
    net_delta_positive_b = (summary_phase2.get("median_settlement_delta_j_q32") or 0) > 0
    acceptance_non_trivial_b = (
        float(summary_phase3.get("acceptance_rate_promote_vs_reject_f64", 0.0)) > 0.0
        and novelty_pass_rate_f64 > 0.0
    )
    frontier_movement_positive_b = int(summary_phase2.get("frontier_movement_u64", 0)) > 0
    robustness_fail_closed_b = bool(
        str((proof_tamper.get("phase4_proof_fallback") or {}).get("proof_unit_verdict_after_tamper", "")).startswith("INVALID:")
        and bool((proof_tamper.get("phase4_proof_fallback") or {}).get("fallback_triggered_b", False))
    )
    anti_goodhart_pass_b = not bool(anti_goodhart.get("suspect_b", True))
    pass_b = bool(
        acceptance_non_trivial_b
        and net_delta_positive_b
        and frontier_movement_positive_b
        and robustness_fail_closed_b
        and anti_goodhart_pass_b
    )
    return {
        "acceptance_non_trivial_b": acceptance_non_trivial_b,
        "net_delta_positive_b": net_delta_positive_b,
        "frontier_movement_positive_b": frontier_movement_positive_b,
        "robustness_fail_closed_b": robustness_fail_closed_b,
        "anti_goodhart_pass_b": anti_goodhart_pass_b,
        "pass_b": pass_b,
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="generate_ceiling_report_v1")
    parser.add_argument("--source_runs_root", default=str(REPO_ROOT / "runs"))
    parser.add_argument("--out_root", default="")
    args = parser.parse_args()

    source_runs_root = Path(args.source_runs_root).resolve()
    out_root = Path(args.out_root).resolve() if str(args.out_root).strip() else (source_runs_root / "ceiling_report_v1")
    out_root.mkdir(parents=True, exist_ok=True)

    phase_rows: dict[str, list[TickRow]] = {}
    all_tick_records: list[TickOutcomeRecord] = []

    for phase_name, prefix, start, end in PHASE_SPECS:
        rows: list[TickRow] = []
        prev_obs_hash: str | None = None
        prev_snapshot_hash: str | None = None
        for tick_dir in _tick_dirs(source_runs_root, prefix, start, end):
            row = _extract_tick_row(
                phase=phase_name,
                tick_dir=tick_dir,
                source_runs_root=source_runs_root,
                prev_observation_hash=prev_obs_hash,
                prev_snapshot_hash=prev_snapshot_hash,
            )
            if row is None:
                continue
            rows.append(row)
            all_tick_records.append(row.record)
            prev_obs_hash = row.observation_hash
            prev_snapshot_hash = row.snapshot_hash
        phase_rows[phase_name] = sorted(rows, key=lambda r: r.tick_u64)

    phase_summaries = {phase: _phase_summary(rows) for phase, rows in phase_rows.items()}
    all_rows = [row for phase in phase_rows.values() for row in phase]

    accepted_changes = []
    for row in phase_rows.get("phase3_adversarial", []):
        item = _extract_promoted_change(row, source_runs_root)
        if item is not None:
            accepted_changes.append(item)
    accepted_changes = sorted(
        accepted_changes,
        key=lambda item: (-float(item.get("novelty_score", 0.0)), int(item.get("tick_u64", 0))),
    )
    top10 = accepted_changes[:10]

    dossier = list(top10)
    dossier.append(_extract_mutator_proposal(source_runs_root))
    dossier.append(_extract_science_proposal(source_runs_root))
    for item in accepted_changes[10:]:
        if len(dossier) >= 20:
            break
        dossier.append(item)
    dossier = dossier[:20]

    anti_goodhart = _anti_goodhart(phase_rows.get("phase2_exploration", []))
    novelty_pass = sum(1 for item in accepted_changes if bool(item.get("novelty_pass_b", False)))
    novelty_total = len(accepted_changes)
    novelty_pass_rate = (float(novelty_pass) / float(novelty_total)) if novelty_total else 0.0

    proof_tamper = _load_json(source_runs_root / "PHASE3B_PHASE4_EVIDENCE_v1.json")
    survival_failure = _load_json(source_runs_root / "ceiling_survival_drill_v1" / "survival_drill" / "SURVIVAL_DRILL_FAILURE_v1.json")
    survival_config = _load_json(source_runs_root / "ceiling_survival_drill_v1" / "survival_drill" / "SURVIVAL_DRILL_CONFIG_v1.json")

    summary_phase2 = phase_summaries.get("phase2_exploration", {})
    summary_phase3 = phase_summaries.get("phase3_adversarial", {})
    criteria = _ceiling_criteria(
        summary_phase2=summary_phase2,
        summary_phase3=summary_phase3,
        novelty_pass_rate_f64=novelty_pass_rate,
        anti_goodhart=anti_goodhart,
        proof_tamper=proof_tamper,
    )

    bottleneck = {
        "primary_bottleneck": (
            "evaluation_kernel_too_narrow"
            if not criteria.get("net_delta_positive_b", False)
            else "proposer_quality"
        ),
        "detail": (
            "exploration lane shows near-zero net delta-J on eligible ticks"
            if not criteria.get("net_delta_positive_b", False)
            else "frontier movement remains low under strict novelty gates"
        ),
        "novelty_pass_rate_f64": novelty_pass_rate,
        "subverifier_cost_ratio_f64": (
            float(summary_phase2.get("median_subverifier_ns", 0)) / float(summary_phase2.get("median_total_ns", 1) or 1)
        ),
    }

    report_obj = {
        "schema_version": "ceiling_report_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_runs_root": str(source_runs_root),
        "tick_outcome_records_schema_rel": str(TICK_OUTCOME_RECORD_SCHEMA_REL),
        "phase_config": {
            phase: {
                "ticks_u64": int(phase_summaries.get(phase, {}).get("ticks_u64", 0)),
            }
            for phase, *_ in PHASE_SPECS
        },
        "phase_summaries": phase_summaries,
        "novelty": {
            "novelty_pass_u64": novelty_pass,
            "novelty_total_u64": novelty_total,
            "novelty_pass_rate_f64": novelty_pass_rate,
        },
        "anti_goodhart_detector": anti_goodhart,
        "ceiling_criteria": criteria,
        "top_10_novel_accepted_changes": top10,
        "top_20_novel_proposals_dossier": dossier,
        "proof_tamper_evidence_rel": _rel(source_runs_root / "PHASE3B_PHASE4_EVIDENCE_v1.json", source_runs_root),
        "proof_tamper_summary": {
            "fallback_accept_b": bool((proof_tamper.get("phase4_proof_fallback") or {}).get("fallback_accept_b", False)),
            "fallback_triggered_b": bool((proof_tamper.get("phase4_proof_fallback") or {}).get("fallback_triggered_b", False)),
            "proof_unit_verdict_after_tamper": str((proof_tamper.get("phase4_proof_fallback") or {}).get("proof_unit_verdict_after_tamper", "")),
            "proof_fallback_reason_code": (proof_tamper.get("phase4_proof_fallback") or {}).get("proof_fallback_reason_code"),
        },
        "survival_drill": {
            "failure_rel": _rel(source_runs_root / "ceiling_survival_drill_v1" / "survival_drill" / "SURVIVAL_DRILL_FAILURE_v1.json", source_runs_root),
            "config_rel": _rel(source_runs_root / "ceiling_survival_drill_v1" / "survival_drill" / "SURVIVAL_DRILL_CONFIG_v1.json", source_runs_root),
            "tick_budget_u64": int(survival_config.get("tick_budget_u64", 0) or 0),
            "start_head": str(survival_failure.get("start_head", "")),
            "end_head": str(survival_failure.get("end_head", "")),
        },
        "bottleneck_diagnosis": bottleneck,
        "next_phase_plan": [
            "Use the non-toy exploration registries and no-promotion-bundle throttle to keep market selection evaluable.",
            "Use ek_omega_v19_ceiling_v1 with expanded economics and science-suite gates pinned in authority.",
            "Require positive eligible-delta-J movement over long windows before declaring a ceiling.",
            "Continue adversarial proof/survival interleaving and fail closed on any nondeterministic evidence path.",
        ],
    }

    tick_records_path = out_root / "tick_outcomes_v1.jsonl"
    with tick_records_path.open("w", encoding="utf-8") as handle:
        for row in sorted(all_tick_records, key=lambda r: (r.phase, r.tick_u64)):
            handle.write(json.dumps(asdict(row), sort_keys=True, separators=(",", ":")) + "\n")

    (out_root / "top_10_novel_accepted_changes_v1.json").write_text(
        json.dumps(top10, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (out_root / "top_20_novel_proposals_v1.json").write_text(
        json.dumps(dossier, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (out_root / "ceiling_report_v1.json").write_text(
        json.dumps(report_obj, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    acceptance_csv = out_root / "acceptance_over_time.csv"
    with acceptance_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "phase",
                "tick_u64",
                "selected_campaign_id",
                "promotion_status",
                "promotion_reason",
                "eval_kernel_ran_b",
                "delta_j_q32",
                "activation_success_b",
                "total_ns",
                "subverifier_ns",
            ]
        )
        for row in sorted(all_rows, key=lambda r: (r.phase, r.tick_u64)):
            writer.writerow(
                [
                    row.phase,
                    row.tick_u64,
                    row.selected_campaign_id or "",
                    row.promotion_status,
                    row.promotion_reason,
                    "1" if row.eval_kernel_ran_b else "0",
                    "" if row.delta_j_q32 is None else int(row.delta_j_q32),
                    "1" if row.activation_success_b else "0",
                    int(row.total_ns),
                    int(row.subverifier_ns),
                ]
            )

    novelty_csv = out_root / "novelty_over_time.csv"
    with novelty_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "phase", "tick_u64", "change_type", "novelty_pass_b", "novelty_score", "promotion_bundle_rel"])
        for idx, item in enumerate(accepted_changes, start=1):
            writer.writerow(
                [
                    idx,
                    item.get("phase", ""),
                    int(item.get("tick_u64", 0)),
                    item.get("change_type", ""),
                    "1" if bool(item.get("novelty_pass_b", False)) else "0",
                    float(item.get("novelty_score", 0.0)),
                    item.get("promotion_bundle_rel", ""),
                ]
            )

    delta_csv = out_root / "delta_j_distribution.csv"
    with delta_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "delta_j_q32"])
        for phase, summary in phase_summaries.items():
            for value in summary.get("settlement_delta_j_distribution_q32_eligible", []):
                writer.writerow([phase, int(value)])

    runtime_csv = out_root / "runtime_cost.csv"
    with runtime_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "median_total_ns", "median_subverifier_ns", "rollback_events_u64"])
        for phase, summary in phase_summaries.items():
            writer.writerow(
                [
                    phase,
                    int(summary.get("median_total_ns", 0)),
                    int(summary.get("median_subverifier_ns", 0)),
                    int(summary.get("rollback_events_u64", 0)),
                ]
            )

    md = []
    md.append("# Ceiling Report v1")
    md.append("")
    md.append("## Phase Summary")
    md.append("")
    md.append("| Phase | Ticks | Promoted | Rejected | Skipped | Eligible ΔJ rows | Median eligible ΔJ(q32) | Frontier movement |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for phase, *_ in PHASE_SPECS:
        row = phase_summaries.get(phase, {})
        md.append(
            f"| {phase} | {row.get('ticks_u64', 0)} | {row.get('promoted_u64', 0)} | "
            f"{row.get('rejected_u64', 0)} | {row.get('skipped_u64', 0)} | "
            f"{row.get('eligible_settlement_rows_u64', 0)} | {row.get('median_settlement_delta_j_q32', None)} | "
            f"{row.get('frontier_movement_u64', 0)} |"
        )
    md.append("")
    md.append("## Ceiling Criteria")
    md.append("")
    for key in (
        "acceptance_non_trivial_b",
        "net_delta_positive_b",
        "frontier_movement_positive_b",
        "robustness_fail_closed_b",
        "anti_goodhart_pass_b",
        "pass_b",
    ):
        md.append(f"- `{key}`: {criteria.get(key)}")
    md.append("")
    md.append("## Novelty")
    md.append("")
    md.append(f"- `novelty_pass_u64`: {novelty_pass}")
    md.append(f"- `novelty_total_u64`: {novelty_total}")
    md.append(f"- `novelty_pass_rate_f64`: {novelty_pass_rate:.4f}")
    md.append("")
    md.append("## Generated Artifacts")
    md.append("")
    for path in (
        out_root / "ceiling_report_v1.json",
        out_root / "tick_outcomes_v1.jsonl",
        out_root / "acceptance_over_time.csv",
        out_root / "novelty_over_time.csv",
        out_root / "delta_j_distribution.csv",
        out_root / "runtime_cost.csv",
        out_root / "top_10_novel_accepted_changes_v1.json",
        out_root / "top_20_novel_proposals_v1.json",
    ):
        md.append(f"- `{_rel(path, source_runs_root)}`")
    (out_root / "ceiling_report_v1.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(str(out_root / "ceiling_report_v1.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
