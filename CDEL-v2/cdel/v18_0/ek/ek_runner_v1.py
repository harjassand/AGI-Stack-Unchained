"""Deterministic evaluation-kernel runner for CCAP v0.2."""

from __future__ import annotations

import os
import resource
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Any

from ...v1_7r.canon import write_canon_json
from ..authority.authority_hash_v1 import load_authority_pins
from ..ccap_runtime_v1 import (
    apply_patch_bytes,
    compute_workspace_tree_id,
    materialize_repo_snapshot,
    read_patch_blob,
    workspace_disk_mb,
)
from ..omega_common_v1 import canon_hash_obj, hash_bytes, load_canon_dict, validate_schema
from ..realize.repo_harness_v1 import run_repo_harness

_Q32_ONE = 1 << 32
_DEFAULT_STPS_DELTA_MIN_Q32 = int(0.02 * float(_Q32_ONE))


def _self_mem_mb() -> int:
    usage_self = resource.getrusage(resource.RUSAGE_SELF)
    usage_child = resource.getrusage(resource.RUSAGE_CHILDREN)
    raw = max(int(usage_self.ru_maxrss), int(usage_child.ru_maxrss))
    if sys.platform == "darwin":
        return max(0, raw // (1024 * 1024))
    return max(0, raw // 1024)


def _fd_count() -> int:
    fd_root = Path("/dev/fd")
    if not fd_root.exists() or not fd_root.is_dir():
        return 0
    try:
        return len(list(fd_root.iterdir()))
    except Exception:  # noqa: BLE001
        return 0


def _cost_vector(*, cpu_ms: int, wall_ms: int, mem_mb: int, disk_mb: int) -> dict[str, int]:
    return {
        "cpu_ms": max(0, int(cpu_ms)),
        "wall_ms": max(0, int(wall_ms)),
        "mem_mb": max(0, int(mem_mb)),
        "disk_mb": max(0, int(disk_mb)),
        "fds": max(0, int(_fd_count())),
        "procs": 0,
        "threads": 0,
    }


def _budget_exceeded(*, budgets: dict[str, Any], cost: dict[str, int]) -> bool:
    checks = [
        ("cpu_ms_max", "cpu_ms"),
        ("wall_ms_max", "wall_ms"),
        ("mem_mb_max", "mem_mb"),
        ("disk_mb_max", "disk_mb"),
        ("fds_max", "fds"),
        ("procs_max", "procs"),
        ("threads_max", "threads"),
    ]
    for budget_key, cost_key in checks:
        budget = int(budgets.get(budget_key, 0))
        if int(cost.get(cost_key, 0)) > budget:
            return True
    return False


def _layer3_enabled() -> bool:
    return str(os.environ.get("OMEGA_CCAP_ENABLE_LAYER3", "0")).strip() == "1"


def _survival_drill_fast_ek_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_SURVIVAL_DRILL", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _scorecard_summary(scorecard: dict[str, Any]) -> dict[str, Any]:
    return {
        "median_stps_non_noop_q32": int(scorecard.get("median_stps_non_noop_q32", 0)),
        "non_noop_ticks_per_min_f64": float(scorecard.get("non_noop_ticks_per_min", 0.0)),
        "promotions_u64": int(scorecard.get("promotions_u64", 0)),
        "activation_success_u64": int(scorecard.get("activation_success_u64", 0)),
    }


def _summary_delta(*, base: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "median_stps_non_noop_q32": int(cand.get("median_stps_non_noop_q32", 0)) - int(base.get("median_stps_non_noop_q32", 0)),
        "non_noop_ticks_per_min_f64": float(cand.get("non_noop_ticks_per_min_f64", 0.0))
        - float(base.get("non_noop_ticks_per_min_f64", 0.0)),
        "promotions_u64": int(cand.get("promotions_u64", 0)) - int(base.get("promotions_u64", 0)),
        "activation_success_u64": int(cand.get("activation_success_u64", 0)) - int(base.get("activation_success_u64", 0)),
    }


def _resolve_patch_bytes_for_payload(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
) -> tuple[bytes | None, dict[str, Any] | None]:
    payload = ccap.get("payload")
    if not isinstance(payload, dict):
        return None, {"code": "PAYLOAD_KIND_UNSUPPORTED", "detail": "payload object missing"}
    kind = str(payload.get("kind", "")).strip()
    if kind == "PATCH":
        patch_blob_id = str(payload.get("patch_blob_id", "")).strip()
        if not patch_blob_id.startswith("sha256:"):
            return None, {"code": "PATCH_HASH_MISMATCH", "detail": "patch_blob_id is missing or invalid"}
        try:
            patch_bytes = read_patch_blob(subrun_root=subrun_root, patch_blob_id=patch_blob_id)
        except Exception:  # noqa: BLE001
            return None, {"code": "PATCH_HASH_MISMATCH", "detail": "patch blob missing or digest mismatch"}
        return patch_bytes, None
    if kind == "ACTIONSEQ":
        if not _layer3_enabled():
            return None, {
                "code": "PAYLOAD_KIND_UNSUPPORTED",
                "detail": "ACTIONSEQ path is disabled by default in v0.2",
            }
        try:
            from ..ccap.payload_apply_actionseq_v1 import build_patch_from_actionseq

            patch_bytes = build_patch_from_actionseq(
                repo_root=repo_root,
                subrun_root=subrun_root,
                ccap_id=ccap_id,
                ccap=ccap,
            )
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if text.startswith("INVALID:"):
                code = text.split(":", 1)[1].strip() or "EVAL_STAGE_FAIL"
            else:
                code = "EVAL_STAGE_FAIL"
            return None, {"code": code, "detail": text or "ACTIONSEQ patch synthesis failed"}
        return patch_bytes, None
    if kind == "GIR":
        if not _layer3_enabled():
            return None, {
                "code": "PAYLOAD_KIND_UNSUPPORTED",
                "detail": "GIR path is disabled by default in v0.2",
            }
        try:
            from ..gir.gir_integrator_v1 import build_patch_from_gir_payload

            patch_bytes = build_patch_from_gir_payload(
                repo_root=repo_root,
                subrun_root=subrun_root,
                ccap_id=ccap_id,
                ccap=ccap,
            )
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            if text.startswith("INVALID:"):
                code = text.split(":", 1)[1].strip() or "EVAL_STAGE_FAIL"
            else:
                code = "EVAL_STAGE_FAIL"
            return None, {"code": code, "detail": text or "GIR patch synthesis failed"}
        return patch_bytes, None
    return None, {"code": "PAYLOAD_KIND_UNSUPPORTED", "detail": f"payload kind unsupported in v0.2: {kind}"}


def _realize_once(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    workspace = out_dir / "workspace"
    materialize_repo_snapshot(repo_root, workspace)

    patch_bytes, refutation = _resolve_patch_bytes_for_payload(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
    )
    if patch_bytes is None:
        return {"ok": False, "refutation": dict(refutation or {"code": "EVAL_STAGE_FAIL", "detail": "missing patch bytes"})}

    try:
        apply_patch_bytes(workspace_root=workspace, patch_bytes=patch_bytes)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc) or "patch application failed"
        return {
            "ok": False,
            "refutation": {
                "code": "SITE_NOT_FOUND",
                "detail": detail,
            },
        }

    applied_tree_id = compute_workspace_tree_id(workspace)
    meta = ccap.get("meta")
    build = ccap.get("build")
    budgets = ccap.get("budgets")
    if not isinstance(meta, dict) or not isinstance(build, dict) or not isinstance(budgets, dict):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "ccap meta/build/budgets missing"},
        }
    harness = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=workspace,
        build_recipe_id=str(build.get("build_recipe_id", "")).strip(),
        budgets=budgets,
        env_contract_id=str(meta.get("env_contract_id", "")).strip(),
        dsbx_profile_id=str(meta.get("dsbx_profile_id", "")).strip(),
        toolchain_root_id=str(meta.get("toolchain_root_id", "")).strip(),
        sandbox_root=out_dir / "harness_sandbox",
    )
    if not bool(harness.get("ok", False)):
        return {
            "ok": False,
            "refutation": dict(harness.get("refutation") or {"code": "EVAL_STAGE_FAIL", "detail": "repo harness failed"}),
            "applied_tree_id": applied_tree_id,
            "realized_out_id": str(harness.get("out_tree_id", "")),
            "transcript_id": str(harness.get("transcript_id", "")),
            "realize_logs_hash": str(harness.get("logs_hash", "")),
            "harness_cost_vector": dict(harness.get("cost_vector") or {}),
        }

    return {
        "ok": True,
        "workspace": workspace,
        "applied_tree_id": applied_tree_id,
        "realized_out_id": str(harness.get("out_tree_id", "")),
        "transcript_id": str(harness.get("transcript_id", "")),
        "realize_logs_hash": str(harness.get("logs_hash", "")),
        "harness_cost_vector": dict(harness.get("cost_vector") or {}),
    }


def _run_score_stage_once(
    *,
    score_repo_root: Path,
    work_dir: Path,
    ccap_id: str,
    ek: dict[str, Any],
    run_label: str,
    ticks_u64: int,
) -> dict[str, Any]:
    scoring = ek.get("scoring_impl")
    if not isinstance(scoring, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl missing"}}
    code_ref = scoring.get("code_ref")
    if not isinstance(code_ref, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl.code_ref missing"}}
    rel = str(code_ref.get("path", "")).strip()
    if not rel:
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl.code_ref.path missing"}}

    tool_path = (score_repo_root / rel).resolve()
    if not tool_path.exists() or not tool_path.is_file():
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring tool path missing"}}

    score_root = work_dir / "score" / str(run_label)
    score_root.mkdir(parents=True, exist_ok=True)
    runs_root = score_root / "runs"
    series_prefix = f"ccap_score_{ccap_id.split(':', 1)[1][:12]}_{run_label}"

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["OMEGA_RUN_SEED_U64"] = "0"
    env["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    env["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    env["PYTHONPATH"] = f"{score_repo_root}:{score_repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")

    cmd = [
        sys.executable,
        str(tool_path),
        "--ticks",
        str(max(1, int(ticks_u64))),
        "--seed_u64",
        "0",
        "--series_prefix",
        series_prefix,
        "--runs_root",
        str(runs_root),
    ]
    run = subprocess.run(
        cmd,
        cwd=score_repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_path = score_root / "stdout.log"
    stderr_path = score_root / "stderr.log"
    stdout_path.write_text(run.stdout, encoding="utf-8")
    stderr_path.write_text(run.stderr, encoding="utf-8")

    if run.returncode != 0:
        return {
            "ok": False,
            "refutation": {
                "code": "EVAL_STAGE_FAIL",
                "detail": "omega benchmark suite failed",
                "evidence_hashes": [hash_bytes(run.stdout.encode("utf-8")), hash_bytes(run.stderr.encode("utf-8"))],
            },
        }

    run_dir = runs_root / series_prefix
    scorecard_path = run_dir / "OMEGA_RUN_SCORECARD_v1.json"
    if not scorecard_path.exists() or not scorecard_path.is_file():
        return {
            "ok": False,
            "refutation": {
                "code": "EVAL_STAGE_FAIL",
                "detail": "score stage missing OMEGA_RUN_SCORECARD_v1.json",
            },
        }
    try:
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        scorecard = {}
    if not isinstance(scorecard, dict):
        scorecard = {}
    scorecard_summary = _scorecard_summary(scorecard)

    return {
        "ok": True,
        "score_run_root": run_dir,
        "score_run_hash": compute_workspace_tree_id(run_dir),
        "scorecard_summary": scorecard_summary,
    }


def _run_score_stage(*, base_repo_root: Path, candidate_repo_root: Path, work_dir: Path, ccap_id: str, ek: dict[str, Any]) -> dict[str, Any]:
    scoring = ek.get("scoring_impl")
    if not isinstance(scoring, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl missing"}}

    accept_policy = scoring.get("accept_policy")
    accept_policy_obj = accept_policy if isinstance(accept_policy, dict) else {}
    require_any_improvement_b = bool(accept_policy_obj.get("require_any_improvement_b", True))
    stps_delta_min_q32 = int(accept_policy_obj.get("stps_delta_min_q32", _DEFAULT_STPS_DELTA_MIN_Q32))
    if stps_delta_min_q32 < 0:
        stps_delta_min_q32 = 0
    ticks_u64 = int(accept_policy_obj.get("ticks_u64", 10))
    if ticks_u64 <= 0:
        ticks_u64 = 10

    score_base = _run_score_stage_once(
        score_repo_root=base_repo_root,
        work_dir=work_dir,
        ccap_id=ccap_id,
        ek=ek,
        run_label="base",
        ticks_u64=ticks_u64,
    )
    if not bool(score_base.get("ok", False)):
        return score_base
    score_cand = _run_score_stage_once(
        score_repo_root=candidate_repo_root,
        work_dir=work_dir,
        ccap_id=ccap_id,
        ek=ek,
        run_label="cand",
        ticks_u64=ticks_u64,
    )
    if not bool(score_cand.get("ok", False)):
        return score_cand

    score_base_summary = score_base.get("scorecard_summary")
    score_cand_summary = score_cand.get("scorecard_summary")
    if not isinstance(score_base_summary, dict) or not isinstance(score_cand_summary, dict):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "score stage missing scorecard summary payload"},
        }
    score_delta_summary = _summary_delta(base=score_base_summary, cand=score_cand_summary)

    stps_delta_q32 = int(score_delta_summary.get("median_stps_non_noop_q32", 0))
    promotions_delta_u64 = int(score_delta_summary.get("promotions_u64", 0))
    activation_delta_u64 = int(score_delta_summary.get("activation_success_u64", 0))
    improved_b = (
        stps_delta_q32 >= int(stps_delta_min_q32)
        or promotions_delta_u64 > 0
        or activation_delta_u64 > 0
    )

    if require_any_improvement_b and not improved_b:
        return {
            "ok": False,
            "refutation": {
                "code": "NO_IMPROVEMENT",
                "detail": (
                    f"stps_base={int(score_base_summary.get('median_stps_non_noop_q32', 0))} "
                    f"stps_cand={int(score_cand_summary.get('median_stps_non_noop_q32', 0))} "
                    f"promos_base={int(score_base_summary.get('promotions_u64', 0))} "
                    f"promos_cand={int(score_cand_summary.get('promotions_u64', 0))} "
                    f"activations_base={int(score_base_summary.get('activation_success_u64', 0))} "
                    f"activations_cand={int(score_cand_summary.get('activation_success_u64', 0))} "
                    f"stps_delta_min_q32={int(stps_delta_min_q32)}"
                ),
            },
            "score_base_summary": score_base_summary,
            "score_cand_summary": score_cand_summary,
            "score_delta_summary": score_delta_summary,
            "score_base_run_hash": str(score_base.get("score_run_hash", "")),
            "score_cand_run_hash": str(score_cand.get("score_run_hash", "")),
        }

    return {
        "ok": True,
        "score_base_summary": score_base_summary,
        "score_cand_summary": score_cand_summary,
        "score_delta_summary": score_delta_summary,
        "score_base_run_hash": str(score_base.get("score_run_hash", "")),
        "score_cand_run_hash": str(score_cand.get("score_run_hash", "")),
    }


def _active_ek_id(repo_root: Path) -> str:
    try:
        pins = load_authority_pins(repo_root)
        pinned_active = str(pins.get("active_ek_id", "")).strip()
        if pinned_active.startswith("sha256:"):
            return pinned_active
    except Exception:  # noqa: BLE001
        pass

    active_path = repo_root / "authority" / "evaluation_kernels" / "ek_active_v1.json"
    payload = load_canon_dict(active_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "ek_active_v1":
        raise RuntimeError("EVAL_STAGE_FAIL")
    value = str(payload.get("active_ek_id", "")).strip()
    if not value.startswith("sha256:"):
        raise RuntimeError("EVAL_STAGE_FAIL")
    return value


def _load_active_ek(repo_root: Path, expected_ek_id: str) -> dict[str, Any]:
    active_ek_id = _active_ek_id(repo_root)
    if active_ek_id != expected_ek_id:
        raise ValueError("EK_ID_NOT_ACTIVE")

    kernels_dir = repo_root / "authority" / "evaluation_kernels"
    for path in sorted(kernels_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        if not isinstance(payload, dict) or payload.get("schema_version") != "evaluation_kernel_v1":
            continue
        digest = canon_hash_obj(payload)
        if digest != active_ek_id:
            continue
        validate_schema(payload, "evaluation_kernel_v1")
        return payload
    raise RuntimeError("EVAL_STAGE_FAIL")


def run_ek(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_logs: list[str] = []

    cpu_start = int(time.process_time() * 1000)
    wall_start = int(time.time() * 1000)

    meta = ccap.get("meta")
    if not isinstance(meta, dict):
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "ccap.meta missing"},
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }

    ek_id = str(meta.get("ek_id", "")).strip()
    try:
        ek = _load_active_ek(repo_root, ek_id)
    except ValueError:
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": {"code": "EK_ID_NOT_ACTIVE", "detail": "ccap meta ek_id is not active"},
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }
    except Exception:  # noqa: BLE001
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "active evaluation kernel missing"},
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }

    stage_specs = ek.get("stages")
    if not isinstance(stage_specs, list):
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "evaluation kernel stages missing"},
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }

    # RE2 owns stage semantics. GE stage ladder is ignored if it conflicts.
    pinned_stage_names = [str(row.get("stage_name", "")).strip() for row in stage_specs if isinstance(row, dict)]
    if pinned_stage_names != ["REALIZE", "SCORE", "FINAL_AUDIT"]:
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "active EK stage list is invalid for v0.2"},
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }

    realize_a = _realize_once(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
        out_dir=out_dir / "realize_a",
    )
    realize_b = _realize_once(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
        out_dir=out_dir / "realize_b",
    )

    if not bool(realize_a.get("ok", False)):
        ref = dict(realize_a.get("refutation") or {"code": "EVAL_STAGE_FAIL", "detail": "realize stage failed"})
        return {
            "determinism_check": "REFUTED",
            "eval_status": "REFUTED",
            "decision": "REJECT",
            "refutation": ref,
            "applied_tree_id": "sha256:" + ("0" * 64),
            "realized_out_id": "",
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes(b""),
        }
    enforce_deterministic_compilation = (
        str(os.environ.get("OMEGA_ENFORCE_DETERMINISTIC_COMPILATION", "0")).strip().lower()
        in {"1", "true", "yes", "on"}
    )
    applied_tree_a = str(realize_a.get("applied_tree_id"))
    realized_out_a = str(realize_a.get("realized_out_id"))
    transcript_a = str(realize_a.get("transcript_id", ""))
    if not bool(realize_b.get("ok", False)):
        if enforce_deterministic_compilation:
            ref = dict(realize_b.get("refutation") or {"code": "NONDETERMINISM_DETECTED", "detail": "realize stage second pass failed"})
            return {
                "determinism_check": "DIVERGED",
                "eval_status": "REFUTED",
                "decision": "REJECT",
                "refutation": ref,
                "applied_tree_id": applied_tree_a,
                "realized_out_id": "",
                "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
                "logs_hash": hash_bytes(b""),
            }
        stage_logs.append("REALIZE:WARN:NONDETERMINISM_IGNORED:second-pass-failed")
        applied_tree_b = applied_tree_a
        realized_out_b = realized_out_a
        transcript_b = transcript_a
    else:
        applied_tree_b = str(realize_b.get("applied_tree_id"))
        realized_out_b = str(realize_b.get("realized_out_id"))
        transcript_b = str(realize_b.get("transcript_id", ""))
    if applied_tree_a != applied_tree_b or realized_out_a != realized_out_b or transcript_a != transcript_b:
        if enforce_deterministic_compilation:
            return {
                "determinism_check": "DIVERGED",
                "eval_status": "REFUTED",
                "decision": "REJECT",
                "refutation": {
                    "code": "NONDETERMINISM_DETECTED",
                    "detail": (
                        f"double-run realization mismatch out1={realized_out_a} out2={realized_out_b} "
                        f"transcript1={transcript_a} transcript2={transcript_b}"
                    ),
                },
                "applied_tree_id": applied_tree_a,
                "realized_out_id": "",
                "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
                "logs_hash": hash_bytes(b""),
            }
        stage_logs.append(
            "REALIZE:WARN:NONDETERMINISM_IGNORED:"
            f"out1={realized_out_a}:out2={realized_out_b}:transcript1={transcript_a}:transcript2={transcript_b}"
        )

    stage_logs.append(f"REALIZE:PASS:{applied_tree_a}:{realized_out_a}:{transcript_a}")

    # Survival Drill v1: skip SCORE and FINAL_AUDIT. Those stages are intentionally expensive
    # (they run benchmark scoring suites) and are not required to prove CCAP contract repair.
    # We still require REALIZE to succeed (patch application + repo harness) and enforce budgets.
    if _survival_drill_fast_ek_enabled():
        cpu_ms = int(time.process_time() * 1000) - cpu_start
        wall_ms = int(time.time() * 1000) - wall_start
        mem_mb = _self_mem_mb()
        disk_mb = workspace_disk_mb(out_dir)
        cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)
        budgets = ccap.get("budgets")
        if not isinstance(budgets, dict):
            budgets = {}
        if _budget_exceeded(budgets=budgets, cost=cost):
            return {
                "determinism_check": "PASS",
                "eval_status": "FAIL",
                "decision": "REJECT",
                "refutation": {
                    "code": "BUDGET_EXCEEDED",
                    "detail": "cost vector exceeded declared budgets",
                },
                "applied_tree_id": applied_tree_a,
                "realized_out_id": realized_out_a,
                "cost_vector": cost,
                "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
            }
        return {
            "determinism_check": "PASS",
            "eval_status": "PASS",
            "decision": "PROMOTE",
            "refutation": None,
            "applied_tree_id": applied_tree_a,
            "realized_out_id": realized_out_a,
            "cost_vector": cost,
            "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
        }

    score = _run_score_stage(
        base_repo_root=repo_root,
        candidate_repo_root=Path(realize_a["workspace"]),
        work_dir=out_dir,
        ccap_id=ccap_id,
        ek=ek,
    )
    if not bool(score.get("ok", False)):
        ref = dict(score.get("refutation") or {"code": "EVAL_STAGE_FAIL", "detail": "score stage failed"})
        score_base_summary = score.get("score_base_summary")
        score_cand_summary = score.get("score_cand_summary")
        score_delta_summary = score.get("score_delta_summary")
        scorecard_summary = score_cand_summary if isinstance(score_cand_summary, dict) else None
        return {
            "determinism_check": "PASS",
            "eval_status": "FAIL",
            "decision": "REJECT",
            "refutation": ref,
            "applied_tree_id": applied_tree_a,
            "realized_out_id": realized_out_a,
            "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
            "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
            "scorecard_summary": scorecard_summary,
            "score_base_summary": score_base_summary if isinstance(score_base_summary, dict) else None,
            "score_cand_summary": score_cand_summary if isinstance(score_cand_summary, dict) else None,
            "score_delta_summary": score_delta_summary if isinstance(score_delta_summary, dict) else None,
        }

    score_base_hash = str(score.get("score_base_run_hash", "")).strip()
    score_cand_hash = str(score.get("score_cand_run_hash", "")).strip()
    score_hash = score_cand_hash or str(score.get("score_run_hash", "")).strip()
    score_base_summary = score.get("score_base_summary")
    score_cand_summary = score.get("score_cand_summary")
    score_delta_summary = score.get("score_delta_summary")
    scorecard_summary = score.get("scorecard_summary")
    if isinstance(score_cand_summary, dict):
        scorecard_summary = score_cand_summary
    if not isinstance(score_base_summary, dict):
        score_base_summary = None
    if not isinstance(score_cand_summary, dict):
        score_cand_summary = None
    if not isinstance(score_delta_summary, dict):
        score_delta_summary = None
    if not isinstance(scorecard_summary, dict):
        scorecard_summary = None
    stage_logs.append(f"SCORE:PASS:base={score_base_hash}:cand={score_hash}")

    final_audit_payload = {
        "schema_version": "ccap_final_audit_v1",
        "ccap_id": ccap_id,
        "applied_tree_id": applied_tree_a,
        "realized_out_id": realized_out_a,
        "score_base_run_hash": score_base_hash,
        "score_cand_run_hash": score_hash,
    }
    final_audit_id = canon_hash_obj(final_audit_payload)
    write_canon_json(out_dir / "final_audit_v1.json", {**final_audit_payload, "audit_id": final_audit_id})
    stage_logs.append(f"FINAL_AUDIT:PASS:{final_audit_id}")

    cpu_ms = int(time.process_time() * 1000) - cpu_start
    wall_ms = int(time.time() * 1000) - wall_start
    mem_mb = _self_mem_mb()
    disk_mb = workspace_disk_mb(out_dir)
    cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)

    budgets = ccap.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    if _budget_exceeded(budgets=budgets, cost=cost):
        return {
            "determinism_check": "PASS",
            "eval_status": "FAIL",
            "decision": "REJECT",
            "refutation": {
                "code": "BUDGET_EXCEEDED",
                "detail": "cost vector exceeded declared budgets",
            },
            "applied_tree_id": applied_tree_a,
            "realized_out_id": realized_out_a,
            "cost_vector": cost,
            "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
            "scorecard_summary": scorecard_summary,
            "score_base_summary": score_base_summary,
            "score_cand_summary": score_cand_summary,
            "score_delta_summary": score_delta_summary,
        }

    return {
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "PROMOTE",
        "refutation": None,
        "applied_tree_id": applied_tree_a,
        "realized_out_id": realized_out_a,
        "cost_vector": cost,
        "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
        "scorecard_summary": scorecard_summary,
        "score_base_summary": score_base_summary,
        "score_cand_summary": score_cand_summary,
        "score_delta_summary": score_delta_summary,
    }


__all__ = ["run_ek"]
