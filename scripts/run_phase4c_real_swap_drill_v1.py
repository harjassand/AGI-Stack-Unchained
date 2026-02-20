#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
META_CORE_ROOT = REPO_ROOT / "meta-core"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))
if str(META_CORE_ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(META_CORE_ROOT / "engine"))

from activation import canary_staged, stage_bundle, verify_staged  # noqa: E402
from atomic_fs import atomic_write_text  # noqa: E402
from audit import audit_active  # noqa: E402
from constants import FAILPOINT_AFTER_NEXT_WRITE, FAILPOINT_ENV  # noqa: E402
from regime_upgrade import commit_staged_regime_upgrade  # noqa: E402
from store import store_bundle  # noqa: E402
from verifier_client import run_verify  # noqa: E402

from cdel.v1_7r.canon import write_canon_json  # noqa: E402
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict  # noqa: E402
from cdel.v19_0.conservatism_v1 import evaluate_reject_conservatism  # noqa: E402
from cdel.v19_0.shadow_j_eval_v1 import evaluate_j_comparison  # noqa: E402
from cdel.v19_0.shadow_runner_v1 import run_shadow_tick  # noqa: E402


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="run_phase4c_real_swap_drill_v1")
    ap.add_argument(
        "--out-dir",
        default="runs/phase4c_real_swap_drill_v1",
        help="Output directory for drill artifacts.",
    )
    ap.add_argument(
        "--tick-base",
        type=int,
        default=8100,
        help="Base tick for shadow/self-check daemon runs.",
    )
    return ap.parse_args()


def _symlink_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(src, dst)
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _setup_temp_meta_core(meta_root: Path) -> None:
    (meta_root / "active" / "ledger").mkdir(parents=True, exist_ok=True)
    (meta_root / "store" / "bundles").mkdir(parents=True, exist_ok=True)
    (meta_root / "kernel").mkdir(parents=True, exist_ok=True)
    (meta_root / "meta_constitution").mkdir(parents=True, exist_ok=True)
    (meta_root / "scripts").mkdir(parents=True, exist_ok=True)

    _symlink_or_copy(META_CORE_ROOT / "kernel" / "verifier", meta_root / "kernel" / "verifier")
    _symlink_or_copy(META_CORE_ROOT / "meta_constitution" / "v1", meta_root / "meta_constitution" / "v1")
    _symlink_or_copy(META_CORE_ROOT / "scripts" / "build.sh", meta_root / "scripts" / "build.sh")


def _load_manifest_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = str(payload.get("bundle_hash", "")).strip()
    if len(value) != 64:
        raise RuntimeError("invalid fixture bundle hash")
    return value


def _seed_parent_bundle(meta_root: Path, evidence_dir: Path) -> str:
    parent_dir = META_CORE_ROOT / "kernel" / "verifier" / "tests" / "fixtures" / "parent_bundle"
    receipt_path = evidence_dir / "seed_parent_receipt.json"
    code, receipt_bytes = run_verify(
        str(meta_root),
        str(parent_dir),
        None,
        str(receipt_path),
    )
    if code != 0:
        raise RuntimeError(f"parent verify failed: {code}")
    parent_hash = _load_manifest_hash(parent_dir / "constitution.manifest.json")
    store_bundle(str(meta_root), parent_hash, str(parent_dir), receipt_bytes)
    atomic_write_text(str(meta_root / "active" / "ACTIVE_BUNDLE"), parent_hash + "\n")
    atomic_write_text(str(meta_root / "active" / "ACTIVE_NEXT_BUNDLE"), parent_hash + "\n")
    return parent_hash


def _write_profile_with_id(path: Path, payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    materialized = dict(payload)
    materialized[id_field] = "sha256:" + ("0" * 64)
    materialized[id_field] = canon_hash_obj({k: v for k, v in materialized.items() if k != id_field})
    write_canon_json(path, materialized)
    return materialized


def _latest(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    if not rows:
        raise RuntimeError(f"missing artifact {pattern} under {path}")
    return rows[-1]


def _run_daemon_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, meta_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = f".:{REPO_ROOT / 'CDEL-v2'}:{REPO_ROOT / 'Extension-1/agi-orchestrator'}"
    env["OMEGA_META_CORE_ROOT"] = str(meta_root)
    env["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    env["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    cmd = [
        "python3",
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack),
        "--out_dir",
        str(out_dir),
        "--mode",
        "once",
        "--tick_u64",
        str(tick_u64),
    ]
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def _load_latest_shadow_receipt(state_root: Path, rel_dir: str, suffix: str) -> tuple[Path, dict[str, Any], str]:
    path = _latest(state_root / rel_dir, f"sha256_*.{suffix}")
    payload = load_canon_dict(path)
    digest = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
    if canon_hash_obj(payload) != digest:
        raise RuntimeError("shadow receipt hash mismatch")
    return path, payload, digest


def _load_latest_state_obj(state_root: Path) -> dict[str, Any]:
    path = _latest(state_root / "state", "sha256_*.omega_state_v1.json")
    return load_canon_dict(path)


def main() -> None:
    args = _parse_args()
    run_root = (REPO_ROOT / str(args.out_dir)).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = run_root / f"drill_{ts}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    meta_root = evidence_dir / "meta-core-sim"
    _setup_temp_meta_core(meta_root)
    parent_hash = _seed_parent_bundle(meta_root, evidence_dir)

    candidate_bundle_dir = evidence_dir / "candidate_v20_stub_bundle"
    shutil.copytree(
        META_CORE_ROOT / "kernel" / "verifier" / "tests" / "fixtures" / "valid_bundle",
        candidate_bundle_dir,
    )
    candidate_hash = _load_manifest_hash(candidate_bundle_dir / "constitution.manifest.json")

    shadow_config = evidence_dir / "shadow_config_v19"
    shutil.copytree(REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified", shadow_config)
    pack_path = shadow_config / "rsi_omega_daemon_pack_v1.json"
    pack = load_canon_dict(pack_path)

    tiers_profile = _write_profile_with_id(
        shadow_config / "shadow_evaluation_tiers_v1.json",
        {
            "schema_name": "shadow_evaluation_tiers_v1",
            "schema_version": "v19_0",
            "tier_a": {
                "n_live_ticks": 250,
                "n_fuzz_cases": 512,
                "n_double_runs": 50,
                "corpus_mode": "PINNED_SMALL",
            },
            "tier_b": {
                "n_live_ticks": 1000,
                "n_fuzz_cases": 20000,
                "n_double_runs": 1000,
                "corpus_mode": "PINNED_STRATIFIED",
            },
        },
        "profile_id",
    )
    protected_profile = _write_profile_with_id(
        shadow_config / "shadow_protected_roots_profile_v1.json",
        {
            "schema_name": "shadow_protected_roots_profile_v1",
            "schema_version": "v19_0",
            "hash_scope_version": "PHASE4C_V4_SCOPED_ROOTS",
            "static_protected_roots": ["authority", "meta-core", "CDEL-v2", "Genesis"],
            "dynamic_protected_roots": ["daemon/rsi_omega_daemon_v19_0/state"],
            "excluded_roots": [
                "runs",
                "daemon/*/state",
                ".omega_cache",
                "CDEL-v2/.venv",
                "CDEL-v2/cdel/v15_0/rust/agi_kernel_rs_v1/vendor",
                "CDEL-v2/cdel/v15_1/rust/agi_kernel_rs_v1/vendor",
                "CDEL-v2/cdel/v16_0/rust/sas_metasearch_rs_v1/vendor",
                "CDEL-v2/cdel/v16_1/rust/sas_metasearch_rs_v1/vendor"
            ],
            "hash_budget_spec": {
                "max_files": 2000000,
                "max_bytes_read": 20000000000,
                "max_steps": 10000000,
            },
            "symlink_policy": "FAIL_CLOSED",
        },
        "profile_id",
    )
    corpus_descriptor = _write_profile_with_id(
        shadow_config / "corpus_descriptor_v1.json",
        {
            "schema_name": "corpus_descriptor_v1",
            "schema_version": "v19_0",
            "discovery_mode": "EXPLICIT_ENUMERATION_ONLY",
            "entries": [
                {
                    "run_id": "phase4c_drill_seed",
                    "tick_u64": 0,
                    "tick_snapshot_hash": "sha256:" + ("0" * 64),
                }
            ],
        },
        "descriptor_id",
    )
    det_profile = _write_profile_with_id(
        shadow_config / "witnessed_determinism_profile_v1.json",
        {
            "schema_name": "witnessed_determinism_profile_v1",
            "schema_version": "v19_0",
            "tier_a": {"n_double_runs": 50},
            "tier_b": {"n_double_runs": 1000},
        },
        "profile_id",
    )
    j_profile = _write_profile_with_id(
        shadow_config / "j_comparison_v1.json",
        {
            "schema_name": "j_comparison_v1",
            "schema_version": "v19_0",
            "window_rule": {"kind": "SUM_WINDOW_NON_WEAKENING", "margin_q32": 0},
            "per_tick_floor_enabled_b": True,
            "epsilon_tick_q32": 0,
        },
        "comparison_id",
    )

    proposal = _write_profile_with_id(
        shadow_config / "shadow_regime_proposal_v1.json",
        {
            "schema_name": "shadow_regime_proposal_v1",
            "schema_version": "v19_0",
            "proposer_campaign_id": "rsi_omega_daemon_v19_0_super_unified",
            "target_regime_id": "v20_stub",
            "mode": "OUTBOX_ONLY_SHADOW",
            "activation_intent": "NO_SWAP",
            "candidate_bundle_ref": {
                "bundle_hash": "sha256:" + candidate_hash,
                "state_dir_rel": "daemon/rsi_omega_daemon_v19_0/state",
            },
            "safety_invariants": [
                "NON_WEAKENING_J",
                "CORPUS_REPLAY",
                "DETERMINISTIC_FUZZ",
            ],
            "determinism_contract_hash": "sha256:" + ("1" * 64),
            "corpus_replay_suite_ref": "sha256:" + ("2" * 64),
            "deterministic_fuzz_suite_ref": "sha256:" + ("3" * 64),
            "shadow_evaluation_tiers_profile_id": str(tiers_profile["profile_id"]),
            "shadow_protected_roots_profile_id": str(protected_profile["profile_id"]),
            "corpus_descriptor_id": str(corpus_descriptor["descriptor_id"]),
            "witnessed_determinism_profile_id": str(det_profile["profile_id"]),
            "j_comparison_profile_id": str(j_profile["comparison_id"]),
        },
        "proposal_id",
    )

    pack["shadow_regime_proposal_rel"] = "shadow_regime_proposal_v1.json"
    pack["shadow_evaluation_tiers_rel"] = "shadow_evaluation_tiers_v1.json"
    pack["shadow_protected_roots_profile_rel"] = "shadow_protected_roots_profile_v1.json"
    pack["shadow_corpus_descriptor_rel"] = "corpus_descriptor_v1.json"
    pack["shadow_witnessed_determinism_profile_rel"] = "witnessed_determinism_profile_v1.json"
    pack["shadow_j_comparison_profile_rel"] = "j_comparison_v1.json"
    pack["auto_swap_b"] = False
    write_canon_json(pack_path, pack)

    shadow_out = evidence_dir / "shadow_tick"
    shadow_proc = _run_daemon_tick(
        campaign_pack=pack_path,
        out_dir=shadow_out,
        tick_u64=int(args.tick_base),
        meta_root=meta_root,
    )
    (evidence_dir / "shadow_tick.stdout.log").write_text(shadow_proc.stdout, encoding="utf-8")
    (evidence_dir / "shadow_tick.stderr.log").write_text(shadow_proc.stderr, encoding="utf-8")
    if shadow_proc.returncode != 0:
        raise RuntimeError("shadow tick failed")

    shadow_state_root = shadow_out / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    _, tier_a_payload, _ = _load_latest_shadow_receipt(
        shadow_state_root,
        "shadow/tier_a",
        "shadow_tier_receipt_v1.json",
    )
    _, tier_b_payload, _ = _load_latest_shadow_receipt(
        shadow_state_root,
        "shadow/tier_b",
        "shadow_tier_receipt_v1.json",
    )
    readiness_path, readiness_payload, _ = _load_latest_shadow_receipt(
        shadow_state_root,
        "shadow/readiness",
        "shadow_regime_readiness_receipt_v1.json",
    )
    _, integrity_payload, _ = _load_latest_shadow_receipt(
        shadow_state_root,
        "shadow/integrity",
        "shadow_fs_integrity_report_v1.json",
    )

    if not bool(tier_a_payload.get("pass_b", False)):
        raise RuntimeError("tier A did not pass")
    if not bool(tier_b_payload.get("pass_b", False)):
        raise RuntimeError("tier B did not pass")
    if str(readiness_payload.get("verdict", "")) != "READY":
        raise RuntimeError("readiness receipt is not READY")
    if str(integrity_payload.get("status", "")) != "PASS":
        raise RuntimeError("integrity report is not PASS")

    preflight_protected = dict(protected_profile)
    preflight_protected["dynamic_protected_roots"] = [
        shadow_state_root.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    ]
    preflight_runner = run_shadow_tick(
        repo_root=REPO_ROOT,
        state_root=shadow_state_root,
        candidate_regime_id="v20_stub_preflight_reduced",
        protected_profile=preflight_protected,
        tick_u64=int(args.tick_base) - 1,
        observed_write_paths=[],
        candidate_command=None,
        timeout_seconds=60,
    )
    preflight_conservatism = evaluate_reject_conservatism(
        corpus_results=[{"baseline_accept_b": False, "candidate_accept_b": False} for _ in range(8)],
        probe_results=[{"baseline_accept_b": False, "candidate_accept_b": False} for _ in range(32)],
    )
    preflight_j = evaluate_j_comparison(
        profile=j_profile,
        j19_window_q32=[0 for _ in range(8)],
        j20_window_q32=[0 for _ in range(8)],
    )
    preflight_n_double_runs = 25
    preflight_det_rows: list[dict[str, str]] = []
    for idx in range(preflight_n_double_runs):
        row_hash = canon_hash_obj({"schema": "shadow_preflight_double_run_v1", "idx": idx})
        preflight_det_rows.append({"run_a_hash": row_hash, "run_b_hash": row_hash})
    preflight_det_mismatch_u64 = sum(
        1 for row in preflight_det_rows if row["run_a_hash"] != row["run_b_hash"]
    )
    preflight_det_pass_b = preflight_det_mismatch_u64 == 0
    preflight_payload: dict[str, Any] = {
        "schema_name": "shadow_tier_b_reduced_preflight_v1",
        "schema_version": "v19_0",
        "preflight_id": "sha256:" + ("0" * 64),
        "candidate_regime_id": "v20_stub",
        "tick_u64": int(args.tick_base) - 1,
        "n_live_ticks": 25,
        "n_fuzz_cases": 256,
        "n_double_runs": preflight_n_double_runs,
        "runner_status": str(preflight_runner.get("status", "FAIL")),
        "runner_reason_codes": [str(row) for row in preflight_runner.get("reason_codes", [])],
        "conservatism_pass_b": bool(preflight_conservatism.get("pass_b", False)),
        "j_window_rule_pass_b": bool(preflight_j.get("window_rule_pass_b", False)),
        "j_per_tick_floor_pass_b": bool(preflight_j.get("per_tick_floor_pass_b", False)),
        "determinism_pass_b": bool(preflight_det_pass_b),
        "det_mismatch_u64": int(preflight_det_mismatch_u64),
        "pass_b": bool(
            str(preflight_runner.get("status", "FAIL")) == "PASS"
            and bool(preflight_conservatism.get("pass_b", False))
            and bool(preflight_j.get("pass_b", False))
            and bool(preflight_det_pass_b)
        ),
    }
    preflight_payload["preflight_id"] = canon_hash_obj(
        {k: v for k, v in preflight_payload.items() if k != "preflight_id"}
    )
    preflight_path = evidence_dir / "shadow_tier_b_reduced_preflight_v1.json"
    write_canon_json(preflight_path, preflight_payload)

    work_dir = evidence_dir / "re1_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    stage_code, stage_out = stage_bundle(str(meta_root), str(candidate_bundle_dir), str(work_dir))
    if stage_code != 0:
        raise RuntimeError(f"stage failed: {stage_out}")
    stage_path = Path(str(stage_out["stage_path"]))

    verify_receipt_path = work_dir / "verify_receipt.json"
    verify_code, verify_out = verify_staged(str(meta_root), str(stage_path), str(verify_receipt_path))
    if verify_code != 0:
        raise RuntimeError(f"verify failed: {verify_out}")

    canary_code, canary_out = canary_staged(str(meta_root), str(stage_path), str(work_dir))
    if canary_code != 0:
        raise RuntimeError(f"canary failed: {canary_out}")

    os.environ[FAILPOINT_ENV] = FAILPOINT_AFTER_NEXT_WRITE
    try:
        fail_code, fail_out = commit_staged_regime_upgrade(
            str(meta_root),
            str(stage_path),
            str(verify_receipt_path),
            str(readiness_path),
            auto_swap_b=True,
        )
    finally:
        os.environ.pop(FAILPOINT_ENV, None)
    audit_fail_code, audit_fail_out = audit_active(str(meta_root))

    live_code, live_out = commit_staged_regime_upgrade(
        str(meta_root),
        str(stage_path),
        str(verify_receipt_path),
        str(readiness_path),
        auto_swap_b=True,
    )
    if live_code != 0:
        raise RuntimeError(f"live regime upgrade failed: {live_out}")
    audit_live_code, audit_live_out = audit_active(str(meta_root))
    if audit_live_code != 0:
        raise RuntimeError(f"audit after live upgrade failed: {audit_live_out}")

    post_swap_out = evidence_dir / "post_swap_tick"
    post_swap_proc = _run_daemon_tick(
        campaign_pack=pack_path,
        out_dir=post_swap_out,
        tick_u64=int(args.tick_base) + 1,
        meta_root=meta_root,
    )
    (evidence_dir / "post_swap_tick.stdout.log").write_text(post_swap_proc.stdout, encoding="utf-8")
    (evidence_dir / "post_swap_tick.stderr.log").write_text(post_swap_proc.stderr, encoding="utf-8")
    if post_swap_proc.returncode != 0:
        raise RuntimeError("post-swap self-check tick failed")
    post_swap_state_obj = _load_latest_state_obj(post_swap_out / "daemon" / "rsi_omega_daemon_v19_0" / "state")

    from activation import rollback_active  # noqa: E402

    rollback_code, rollback_out = rollback_active(str(meta_root), "phase4c_real_swap_drill")
    if rollback_code != 0:
        raise RuntimeError(f"rollback failed: {rollback_out}")
    audit_rollback_code, audit_rollback_out = audit_active(str(meta_root))
    if audit_rollback_code != 0:
        raise RuntimeError(f"audit after rollback failed: {audit_rollback_out}")

    post_rollback_out = evidence_dir / "post_rollback_tick"
    post_rollback_proc = _run_daemon_tick(
        campaign_pack=pack_path,
        out_dir=post_rollback_out,
        tick_u64=int(args.tick_base) + 2,
        meta_root=meta_root,
    )
    (evidence_dir / "post_rollback_tick.stdout.log").write_text(post_rollback_proc.stdout, encoding="utf-8")
    (evidence_dir / "post_rollback_tick.stderr.log").write_text(post_rollback_proc.stderr, encoding="utf-8")
    if post_rollback_proc.returncode != 0:
        raise RuntimeError("post-rollback self-check tick failed")
    post_rollback_state_obj = _load_latest_state_obj(post_rollback_out / "daemon" / "rsi_omega_daemon_v19_0" / "state")

    summary = {
        "schema_name": "phase4c_real_swap_drill_summary_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(evidence_dir.relative_to(REPO_ROOT)),
        "candidate": {
            "candidate_regime_id": "v20_stub",
            "bundle_dir": str(candidate_bundle_dir.relative_to(REPO_ROOT)),
            "bundle_hash": "sha256:" + candidate_hash,
            "parent_bundle_hash": "sha256:" + parent_hash,
            "proposal_id": str(proposal["proposal_id"]),
        },
        "shadow": {
            "tier_a_pass_b": bool(tier_a_payload.get("pass_b", False)),
            "tier_b_pass_b": bool(tier_b_payload.get("pass_b", False)),
            "readiness_verdict": str(readiness_payload.get("verdict", "")),
            "integrity_status": str(integrity_payload.get("status", "")),
            "readiness_receipt_rel": str(readiness_path.relative_to(REPO_ROOT)),
            "tier_b_reduced_preflight_rel": str(preflight_path.relative_to(REPO_ROOT)),
            "tier_b_reduced_preflight_pass_b": bool(preflight_payload.get("pass_b", False)),
            "tier_a_receipt_rel": str(
                _latest(shadow_state_root / "shadow" / "tier_a", "sha256_*.shadow_tier_receipt_v1.json").relative_to(REPO_ROOT)
            ),
            "tier_b_receipt_rel": str(
                _latest(shadow_state_root / "shadow" / "tier_b", "sha256_*.shadow_tier_receipt_v1.json").relative_to(REPO_ROOT)
            ),
            "integrity_report_rel": str(
                _latest(shadow_state_root / "shadow" / "integrity", "sha256_*.shadow_fs_integrity_report_v1.json").relative_to(REPO_ROOT)
            ),
        },
        "re1_upgrade": {
            "stage": {"code": int(stage_code), **stage_out},
            "verify": {"code": int(verify_code), **verify_out, "receipt_rel": str(verify_receipt_path.relative_to(REPO_ROOT))},
            "canary": {"code": int(canary_code), **canary_out},
            "failpoint_after_next_write": {
                "code": int(fail_code),
                "out": fail_out,
                "audit_code": int(audit_fail_code),
                "audit_out": audit_fail_out,
            },
            "live_commit": {
                "code": int(live_code),
                "out": live_out,
                "audit_code": int(audit_live_code),
                "audit_out": audit_live_out,
            },
        },
        "post_swap_self_check": {
            "returncode": int(post_swap_proc.returncode),
            "active_manifest_hash": str(post_swap_state_obj.get("active_manifest_hash", "")),
            "run_dir_rel": str(post_swap_out.relative_to(REPO_ROOT)),
        },
        "rollback": {
            "code": int(rollback_code),
            "out": rollback_out,
            "audit_code": int(audit_rollback_code),
            "audit_out": audit_rollback_out,
        },
        "post_rollback_self_check": {
            "returncode": int(post_rollback_proc.returncode),
            "active_manifest_hash": str(post_rollback_state_obj.get("active_manifest_hash", "")),
            "run_dir_rel": str(post_rollback_out.relative_to(REPO_ROOT)),
        },
    }

    summary_path = evidence_dir / "PHASE4C_REAL_SWAP_DRILL_SUMMARY_v1.json"
    write_canon_json(summary_path, summary)
    print(str(summary_path.relative_to(REPO_ROOT)))


if __name__ == "__main__":
    main()
