#!/usr/bin/env python3
"""Package SIDC-v1 artifacts into one replay-oriented evidence bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _copy_into(src: Path, dst_root: Path, rel: str) -> str:
    dst = (dst_root / rel).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst.relative_to(dst_root).as_posix()


def _patch_metrics(patch_path: Path) -> dict[str, int]:
    text = patch_path.read_text(encoding="utf-8", errors="replace")
    touched: set[str] = set()
    add_u64 = 0
    del_u64 = 0
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            touched.add(line[6:])
        if line.startswith("+") and not line.startswith("+++"):
            add_u64 += 1
        elif line.startswith("-") and not line.startswith("---"):
            del_u64 += 1
    return {
        "touched_files_u64": len(touched),
        "added_lines_u64": int(add_u64),
        "deleted_lines_u64": int(del_u64),
        "loc_delta_u64": int(add_u64 + del_u64),
    }


def _collect_heavy_diffs(phase3_root: Path, bundle_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tick_dir in sorted(phase3_root.glob("tick_*"), key=lambda p: int(p.name.split("_")[1])):
        tick_u64 = int(tick_dir.name.split("_")[1])
        state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
        dispatch_paths = sorted((state_root / "dispatch").glob("*/*.omega_dispatch_receipt_v1.json"))
        if not dispatch_paths:
            continue
        dispatch_path = dispatch_paths[-1]
        dispatch_payload = _load_json(dispatch_path)
        if str(dispatch_payload.get("campaign_id", "")).strip() != "rsi_proposer_arena_v1":
            continue
        dispatch_id = dispatch_path.parent.name

        subverifier_paths = sorted((state_root / "dispatch" / dispatch_id / "verifier").glob("*.omega_subverifier_receipt_v1.json"))
        subverifier_payload = _load_json(subverifier_paths[-1]) if subverifier_paths else {}

        promotion_paths = sorted((state_root / "dispatch" / dispatch_id / "promotion").glob("*.omega_promotion_receipt_v1.json"))
        promoted_payload: dict[str, Any] | None = None
        for promotion_path in promotion_paths:
            candidate = _load_json(promotion_path)
            result = candidate.get("result")
            status = str((result or {}).get("status", "")).strip().upper() if isinstance(result, dict) else ""
            if status == "PROMOTED":
                promoted_payload = candidate
                break
        if promoted_payload is None:
            continue

        replay_binding = promoted_payload.get("replay_binding_v1")
        if not isinstance(replay_binding, dict):
            continue
        replay_rel = str(replay_binding.get("replay_state_dir_relpath", "")).strip()
        bundle_hash = str(promoted_payload.get("promotion_bundle_hash", "")).strip()
        if not replay_rel or not bundle_hash.startswith("sha256:"):
            continue

        replay_root = (state_root / replay_rel).resolve()
        bundle_path = replay_root / "promotion" / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
        bundle_payload = _load_json(bundle_path)

        patch_rel = str(bundle_payload.get("patch_relpath", "")).strip()
        if not patch_rel:
            continue
        patch_path = (replay_root / patch_rel).resolve()
        metrics = _patch_metrics(patch_path)

        run_receipt_paths = sorted((replay_root / "arena").glob("sha256_*.proposer_arena_run_receipt_v1.json"))
        winner_candidate_id = ""
        if run_receipt_paths:
            winner_candidate_id = str(_load_json(run_receipt_paths[-1]).get("winner_candidate_id", "")).strip()
        cert_id = ""
        for candidate_path in sorted((replay_root / "candidates").glob("sha256_*.arena_candidate_v1.json")):
            candidate_payload = _load_json(candidate_path)
            if str(candidate_payload.get("candidate_id", "")).strip() == winner_candidate_id:
                cert_id = str(candidate_payload.get("nontriviality_cert_id", "")).strip()
                break

        heavy_pass_b = bool(metrics["touched_files_u64"] >= 8 and metrics["loc_delta_u64"] >= 500)
        rows.append(
            {
                "tick_u64": int(tick_u64),
                "dispatch_id": dispatch_id,
                "dispatch_receipt_relpath": _copy_into(dispatch_path, bundle_root, f"phase3/dispatch/{dispatch_path.name}"),
                "subverifier_receipt_relpath": (
                    _copy_into(subverifier_paths[-1], bundle_root, f"phase3/subverifier/{subverifier_paths[-1].name}")
                    if subverifier_paths
                    else ""
                ),
                "promotion_receipt_id": str(promoted_payload.get("receipt_id", "")).strip(),
                "promotion_bundle_hash": bundle_hash,
                "promotion_bundle_relpath": _copy_into(bundle_path, bundle_root, f"phase3/promotion_bundle/{bundle_path.name}"),
                "patch_relpath": _copy_into(patch_path, bundle_root, f"phase3/patches/{patch_path.name}"),
                "ccap_id": str(bundle_payload.get("ccap_id", "")).strip(),
                "winner_candidate_id": winner_candidate_id,
                "nontriviality_cert_id": cert_id,
                "metrics": metrics,
                "heavy_diff_requirement_met_b": heavy_pass_b,
            }
        )
    return rows


def _collect_policy_chain(phase3_root: Path, bundle_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for tick_dir in sorted(phase3_root.glob("tick_*"), key=lambda p: int(p.name.split("_")[1])):
        tick_u64 = int(tick_dir.name.split("_")[1])
        state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
        activation_paths = sorted(state_root.glob("dispatch/*/activation/*.omega_activation_receipt_v1.json"))
        for activation_path in activation_paths:
            payload = _load_json(activation_path)
            activation_kind = str(payload.get("activation_kind", "")).strip()
            if activation_kind != "ACTIVATION_KIND_ORCH_POLICY_UPDATE":
                continue
            rows.append(
                {
                    "tick_u64": int(tick_u64),
                    "activation_receipt_id": str(payload.get("receipt_id", "")).strip(),
                    "activation_success_b": bool(payload.get("activation_success", False)),
                    "activation_relpath": _copy_into(activation_path, bundle_root, f"phase3/activation/{activation_path.name}"),
                }
            )
    active_paths = sorted(phase3_root.glob("tick_*/daemon/orch_policy/active/ORCH_POLICY_V1.json"), key=lambda p: p.as_posix())
    copied_active = [
        _copy_into(path, bundle_root, f"phase3/orch_policy_active/{path.parent.parent.parent.name}_{path.name}")
        for path in active_paths
    ]
    return {
        "activations": rows,
        "active_pointer_snapshots": copied_active,
        "policy_swap_requirement_met_b": any(bool(row.get("activation_success_b", False)) for row in rows),
    }


def _collect_training_lineage(run_root: Path, bundle_root: Path) -> dict[str, Any]:
    phase1_root = run_root / "phase1"
    result: dict[str, Any] = {
        "status": "MISSING",
        "artifacts": {},
    }
    if not phase1_root.exists() or not phase1_root.is_dir():
        return result

    artifacts: dict[str, str] = {}
    for name in [
        "proposer_corpus_builder_stdout.json",
        "train_lora_sft_stdout.json",
        "train_qlora_dpo_stdout.json",
    ]:
        src = phase1_root / name
        if src.exists() and src.is_file():
            artifacts[name] = _copy_into(src, bundle_root, f"phase1/{name}")
    result["status"] = "OK" if artifacts else "MISSING"
    result["artifacts"] = artifacts
    return result


def _collect_thermo_status(run_root: Path, bundle_root: Path) -> dict[str, Any]:
    phase4_verify = run_root / "phase4_thermo_verify_stdout.txt"
    if not phase4_verify.exists() or not phase4_verify.is_file():
        return {"status": "MISSING"}
    copied = _copy_into(phase4_verify, bundle_root, "phase4/phase4_thermo_verify_stdout.txt")
    result: dict[str, Any] = {"verify_stdout_relpath": copied}
    text = phase4_verify.read_text(encoding="utf-8", errors="replace")
    result["status"] = "OK" if "VALID" in text else "FAIL"

    phase4_runner = run_root / "phase4_thermo_runner_stdout.txt"
    if phase4_runner.exists() and phase4_runner.is_file():
        result["runner_stdout_relpath"] = _copy_into(phase4_runner, bundle_root, "phase4/phase4_thermo_runner_stdout.txt")

    phase4_state_path = run_root / "phase4_thermo_state_dir.txt"
    if phase4_state_path.exists() and phase4_state_path.is_file():
        state_dir = Path(phase4_state_path.read_text(encoding="utf-8").strip()).resolve()
        result["state_dir"] = state_dir.as_posix()
        if state_dir.exists() and state_dir.is_dir():
            ledger = state_dir / "thermo" / "thermo_ledger_v1.jsonl"
            probes = sorted((state_dir / "thermo" / "probes").glob("*.json"))
            bundles = sorted((state_dir / "thermo" / "improvement" / "promotion_bundles").glob("*.json"))
            result["ledger_lines_u64"] = (
                int(sum(1 for _ in ledger.open("r", encoding="utf-8")))
                if ledger.exists() and ledger.is_file()
                else 0
            )
            result["probe_receipts_u64"] = int(len(probes))
            result["promotion_bundles_u64"] = int(len(bundles))
            if ledger.exists() and ledger.is_file():
                result["ledger_relpath"] = _copy_into(ledger, bundle_root, "phase4/thermo_ledger_v1.jsonl")
    return result


def _write_replay_instructions(bundle_root: Path) -> None:
    lines = [
        "# SIDC-v1 Replay Instructions",
        "",
        "## 1) Run phases",
        "bash scripts/sidc_v1_demo_run.sh phase1",
        "bash scripts/sidc_v1_demo_run.sh phase2",
        "SIDC_TICKS=4 bash scripts/sidc_v1_demo_run.sh phase3",
        "",
        "## 2) Run multiseed holdout eval (before/after capability levels)",
        "python3 scripts/micdrop_eval_once_v2.py --suite_set_id <anchor_suite_set_id> --seed_u64 <seed> --ticks 1 --capability_level_override 0 --out runs/sidc_v1_demo/evidence/multiseed/seed_<seed>/before",
        "python3 scripts/micdrop_eval_once_v2.py --suite_set_id <anchor_suite_set_id> --seed_u64 <seed> --ticks 1 --capability_level_override 4 --out runs/sidc_v1_demo/evidence/multiseed/seed_<seed>/after",
        "",
        "## 3) Build per-seed evidence and aggregate report",
        "python3 scripts/micdrop_package_multiseed_report_v2.py --input_glob 'runs/sidc_v1_demo/evidence/multiseed/seed_*/MICDROP_SEED_EVIDENCE_v2.json' --out runs/sidc_v1_demo/evidence/MICDROP_MULTI_SEED_REPORT_v2.json",
        "",
        "## 4) Package final bundle",
        "python3 scripts/sidc_package_superintelligence_evidence_v1.py --run_root runs/sidc_v1_demo --out_dir runs/sidc_v1_demo/SUPERINTELLIGENCE_EVIDENCE_BUNDLE_v1",
        "",
        "## 5) Applied thermo track",
        "bash scripts/sidc_v1_demo_run.sh phase4",
    ]
    (bundle_root / "REPLAY_INSTRUCTIONS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(prog="sidc_package_superintelligence_evidence_v1")
    parser.add_argument("--run_root", default="runs/sidc_v1_demo")
    parser.add_argument("--out_dir", default="runs/sidc_v1_demo/SUPERINTELLIGENCE_EVIDENCE_BUNDLE_v1")
    args = parser.parse_args()

    run_root = (REPO_ROOT / str(args.run_root)).resolve()
    out_dir = (REPO_ROOT / str(args.out_dir)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    micdrop_report_src = run_root / "evidence" / "MICDROP_MULTI_SEED_REPORT_v2.json"
    if not micdrop_report_src.exists() or not micdrop_report_src.is_file():
        raise RuntimeError("missing micdrop multiseed report")
    micdrop_report_rel = _copy_into(micdrop_report_src, out_dir, "micdrop/MICDROP_MULTI_SEED_REPORT_v2.json")
    micdrop_report = _load_json(micdrop_report_src)

    heavy_diffs = _collect_heavy_diffs(run_root / "phase3", out_dir)
    policy_chain = _collect_policy_chain(run_root / "phase3", out_dir)
    training_lineage = _collect_training_lineage(run_root, out_dir)
    thermo_status = _collect_thermo_status(run_root, out_dir)

    heavy_pass_count = int(sum(1 for row in heavy_diffs if bool(row.get("heavy_diff_requirement_met_b", False))))
    heavy_requirement_met = bool(heavy_pass_count >= 3)
    improved_seeds_u64 = int(micdrop_report.get("improved_seeds_u64", 0))
    total_seeds_u64 = int(micdrop_report.get("total_seeds_u64", 0))
    per_suite_hits = dict((micdrop_report.get("breadth") or {}).get("per_suite_high_hits_u64") or {})
    cross_domain_suites_u64 = int(sum(1 for _suite, hits in per_suite_hits.items() if int(hits) >= max(1, total_seeds_u64)))
    cross_domain_met = bool(cross_domain_suites_u64 >= 3)

    acceptance_summary = {
        "schema_version": "sidc_v1_acceptance_summary_v1",
        "heavy_diff": {
            "promoted_heavy_diffs_u64": heavy_pass_count,
            "required_u64": 3,
            "met_b": heavy_requirement_met,
        },
        "micdrop_multiseed": {
            "report_relpath": micdrop_report_rel,
            "improved_seeds_u64": improved_seeds_u64,
            "total_seeds_u64": total_seeds_u64,
            "cross_domain_suites_u64": cross_domain_suites_u64,
            "cross_domain_requirement_met_b": cross_domain_met,
            "fraction_improved_q32": int(micdrop_report.get("fraction_improved_q32", 0)),
            "mean_delta_accuracy_q32": int(micdrop_report.get("mean_delta_accuracy_q32", 0)),
        },
        "policy_activation_chain": {
            "met_b": bool(policy_chain.get("policy_swap_requirement_met_b", False)),
            "activation_count_u64": len(list(policy_chain.get("activations") or [])),
        },
        "proposer_training_lineage": {
            "status": str(training_lineage.get("status", "MISSING")),
        },
        "thermo_applied_track": thermo_status,
    }
    acceptance_summary["overall_acceptance_met_b"] = bool(
        heavy_requirement_met
        and cross_domain_met
        and bool(policy_chain.get("policy_swap_requirement_met_b", False))
        and str(training_lineage.get("status", "MISSING")) == "OK"
        and str((thermo_status or {}).get("status", "MISSING")) == "OK"
    )

    bundle_index = {
        "schema_version": "sidc_v1_superintelligence_evidence_bundle_index_v1",
        "run_root_relpath": run_root.relative_to(REPO_ROOT).as_posix(),
        "micdrop_report_relpath": micdrop_report_rel,
        "heavy_diffs": heavy_diffs,
        "policy_activation_chain": policy_chain,
        "proposer_training_lineage": training_lineage,
        "thermo_applied_track": thermo_status,
        "acceptance_summary": acceptance_summary,
    }
    (out_dir / "BUNDLE_INDEX.json").write_text(json.dumps(bundle_index, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    (out_dir / "ACCEPTANCE_SUMMARY.json").write_text(json.dumps(acceptance_summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _write_replay_instructions(out_dir)
    print(json.dumps({"bundle_index": str((out_dir / "BUNDLE_INDEX.json").relative_to(REPO_ROOT).as_posix())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
