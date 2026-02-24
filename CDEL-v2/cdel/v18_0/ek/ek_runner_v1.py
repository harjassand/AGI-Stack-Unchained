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
from ..ccap_budget_v1 import (
    effective_ccap_budget_tuple,
    normalize_ccap_budget_limits,
    resolve_effective_ccap_budget_profile,
)
from ..ccap_runtime_v1 import (
    apply_patch_bytes,
    build_patch_apply_failure_detail,
    classify_patch_apply_exception,
    compute_workspace_tree_id,
    materialize_repo_snapshot,
    read_patch_blob,
    workspace_disk_mb,
)
from ..omega_common_v1 import canon_hash_obj, hash_bytes, load_canon_dict, validate_schema
from ..realize.repo_harness_v1 import run_repo_harness

_Q32_ONE = 1 << 32
_DEFAULT_STPS_DELTA_MIN_Q32 = int(0.02 * float(_Q32_ONE))
_DEFAULT_SMOKE_BUDGET_LADDER_V1: tuple[tuple[int, int, int, int], ...] = (
    (60_000, 60_000, 1_024, 536_870_912),
    (120_000, 120_000, 2_048, 1_073_741_824),
    (240_000, 240_000, 4_096, 2_147_483_648),
)


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


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_u64(name: str, *, default: int, minimum: int = 0) -> int:
    raw = str(os.environ.get(name, str(int(default)))).strip()
    value = int(raw)
    return int(max(int(minimum), value))


def _ccap_smoke_ek_enabled() -> bool:
    return _env_bool("OMEGA_CCAP_SMOKE_EK_B", default=False)


def _ccap_smoke_only_enabled() -> bool:
    return _env_bool("OMEGA_CCAP_SMOKE_ONLY_B", default=False)


def _smoke_score_ticks_u64(*, default_ticks_u64: int) -> int:
    fallback = int(max(1, min(5, int(default_ticks_u64))))
    return _env_u64("OMEGA_CCAP_SMOKE_SCORE_TICKS_U64", default=fallback, minimum=1)


def _smoke_budget_tuple_from_env() -> dict[str, int]:
    return {
        "time_ms_max": _env_u64("OMEGA_CCAP_SMOKE_TIME_MS_MAX", default=60_000, minimum=1),
        "stage_cost_budget": _env_u64("OMEGA_CCAP_SMOKE_STAGE_COST_BUDGET", default=60_000, minimum=1),
        "disk_mb_max": _env_u64("OMEGA_CCAP_SMOKE_DISK_MB_MAX", default=1_024, minimum=1),
        "artifact_bytes_max": _env_u64("OMEGA_CCAP_SMOKE_ARTIFACT_BYTES_MAX", default=536_870_912, minimum=1),
    }


def _normalize_smoke_budget_tuple(raw: dict[str, Any]) -> dict[str, int]:
    return {
        "time_ms_max": int(max(1, int(raw.get("time_ms_max", 60_000)))),
        "stage_cost_budget": int(max(1, int(raw.get("stage_cost_budget", 60_000)))),
        "disk_mb_max": int(max(1, int(raw.get("disk_mb_max", 1_024)))),
        "artifact_bytes_max": int(max(1, int(raw.get("artifact_bytes_max", 536_870_912)))),
    }


def _default_smoke_budget_ladder_v1() -> list[dict[str, int]]:
    return [
        {
            "time_ms_max": int(time_ms),
            "stage_cost_budget": int(stage_cost),
            "disk_mb_max": int(disk_mb),
            "artifact_bytes_max": int(artifact_bytes),
        }
        for time_ms, stage_cost, disk_mb, artifact_bytes in _DEFAULT_SMOKE_BUDGET_LADDER_V1
    ]


def _smoke_budget_ladder_from_env() -> list[dict[str, int]]:
    raw = str(os.environ.get("OMEGA_CCAP_SMOKE_BUDGET_LADDER_V1", "")).strip()
    if not raw:
        default_ladder = _default_smoke_budget_ladder_v1()
        legacy_rung = _smoke_budget_tuple_from_env()
        if legacy_rung == default_ladder[0]:
            return default_ladder
        rung2_default = default_ladder[1]
        rung3_default = default_ladder[2]
        rung2 = {
            "time_ms_max": int(max(int(legacy_rung["time_ms_max"]) * 2, int(rung2_default["time_ms_max"]))),
            "stage_cost_budget": int(max(int(legacy_rung["stage_cost_budget"]) * 2, int(rung2_default["stage_cost_budget"]))),
            "disk_mb_max": int(max(int(legacy_rung["disk_mb_max"]) * 2, int(rung2_default["disk_mb_max"]))),
            "artifact_bytes_max": int(
                max(int(legacy_rung["artifact_bytes_max"]) * 2, int(rung2_default["artifact_bytes_max"]))
            ),
        }
        rung3 = {
            "time_ms_max": int(max(int(legacy_rung["time_ms_max"]) * 4, int(rung3_default["time_ms_max"]))),
            "stage_cost_budget": int(max(int(legacy_rung["stage_cost_budget"]) * 4, int(rung3_default["stage_cost_budget"]))),
            "disk_mb_max": int(max(int(legacy_rung["disk_mb_max"]) * 4, int(rung3_default["disk_mb_max"]))),
            "artifact_bytes_max": int(
                max(int(legacy_rung["artifact_bytes_max"]) * 4, int(rung3_default["artifact_bytes_max"]))
            ),
        }
        return [legacy_rung, rung2, rung3]
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        return _default_smoke_budget_ladder_v1()
    parsed: list[dict[str, int]] = []
    if isinstance(payload, list):
        for item in payload:
            tuple_obj: dict[str, Any] | None = None
            if isinstance(item, list) and len(item) == 4:
                tuple_obj = {
                    "time_ms_max": item[0],
                    "stage_cost_budget": item[1],
                    "disk_mb_max": item[2],
                    "artifact_bytes_max": item[3],
                }
            elif isinstance(item, dict):
                tuple_obj = {
                    "time_ms_max": item.get("time_ms_max"),
                    "stage_cost_budget": item.get("stage_cost_budget"),
                    "disk_mb_max": item.get("disk_mb_max"),
                    "artifact_bytes_max": item.get("artifact_bytes_max"),
                }
            if not isinstance(tuple_obj, dict):
                continue
            try:
                parsed.append(_normalize_smoke_budget_tuple(tuple_obj))
            except Exception:  # noqa: BLE001
                continue
            if len(parsed) >= 8:
                break
    if parsed:
        return parsed
    return _default_smoke_budget_ladder_v1()


def _smoke_budget_start_rung_u8(*, ladder_len: int) -> int:
    rung = int(_env_u64("OMEGA_CCAP_SMOKE_BUDGET_START_RUNG_U8", default=1, minimum=1))
    return int(max(1, min(int(max(1, ladder_len)), rung)))


def _smoke_budget_max_bumps_u8() -> int:
    return int(_env_u64("OMEGA_CCAP_SMOKE_BUDGET_MAX_BUMPS_U8", default=1, minimum=0))


def _smoke_winner_escalate_full_ek_enabled() -> bool:
    return _env_bool("OMEGA_CCAP_SMOKE_WINNER_ESCALATE_FULL_EK_B", default=True)


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
    effective_budgets: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    def _write_patch_apply_fail_detail(*, payload: dict[str, Any]) -> str:
        digest = canon_hash_obj(payload)
        details_dir = out_dir / "patch_apply_failures"
        details_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(
            details_dir / f"sha256_{digest.split(':', 1)[1]}.patch_apply_fail_detail_v1.json",
            payload,
        )
        return digest

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
        classification = classify_patch_apply_exception(exc=exc)
        detail_payload = build_patch_apply_failure_detail(
            workspace_root=workspace,
            patch_bytes=patch_bytes,
            exc=exc,
        )
        detail_hash = _write_patch_apply_fail_detail(payload=detail_payload)
        refutation_code = str(classification.get("refutation_code", "PATCH_APPLY_FAILED")).strip() or "PATCH_APPLY_FAILED"
        patch_apply_fail_code = str(classification.get("patch_apply_fail_code", "") or "").strip()
        refutation_detail = (
            "patch base hash mismatch before apply"
            if refutation_code == "PATCH_BASE_MISMATCH"
            else f"patch application failed ({patch_apply_fail_code or 'OTHER_EXCEPTION'})"
        )
        refutation_payload: dict[str, Any] = {
            "code": refutation_code,
            "detail": refutation_detail,
            "evidence_hashes": [detail_hash],
            "patch_apply_fail_detail_hash": detail_hash,
        }
        if patch_apply_fail_code:
            refutation_payload["patch_apply_fail_stage"] = "APPLY_PATCH_BYTES"
            refutation_payload["patch_apply_fail_code"] = patch_apply_fail_code
        elif refutation_code == "PATCH_APPLY_FAILED":
            refutation_payload["patch_apply_fail_stage"] = "APPLY_PATCH_BYTES"
            refutation_payload["patch_apply_fail_code"] = "OTHER_EXCEPTION"
        return {
            "ok": False,
            "refutation": refutation_payload,
        }

    applied_tree_id = compute_workspace_tree_id(workspace)
    meta = ccap.get("meta")
    build = ccap.get("build")
    if not isinstance(meta, dict) or not isinstance(build, dict):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "ccap meta/build missing"},
        }
    harness = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=workspace,
        build_recipe_id=str(build.get("build_recipe_id", "")).strip(),
        budgets=effective_budgets,
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
    authority_pins: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema_version = str(ek.get("schema_version", "")).strip()
    scoring = ek.get("scoring_impl")
    if not isinstance(scoring, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl missing"}}
    scoring_kind = str(scoring.get("kind", "")).strip()
    code_ref = scoring.get("code_ref")
    if not isinstance(code_ref, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl.code_ref missing"}}
    rel = str(code_ref.get("path", "")).strip()
    if not rel:
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl.code_ref.path missing"}}

    if schema_version == "evaluation_kernel_v2" or scoring_kind == "OMEGA_BENCHMARK_SUITE_COMPOSITE":
        if schema_version != "evaluation_kernel_v2":
            return {
                "ok": False,
                "refutation": {
                    "code": "EVAL_STAGE_FAIL",
                    "detail": "OMEGA_BENCHMARK_SUITE_COMPOSITE requires evaluation_kernel_v2",
                },
            }
        anchor_suite_set_id = str(ek.get("anchor_suite_set_id", "")).strip()
        extensions_ledger_id = str(ek.get("extensions_ledger_id", "")).strip()
        suite_runner_id = str(ek.get("suite_runner_id", "")).strip()
        holdout_policy_id = str(ek.get("holdout_policy_id", "")).strip()
        if (
            not anchor_suite_set_id.startswith("sha256:")
            or not extensions_ledger_id.startswith("sha256:")
            or not suite_runner_id.startswith("sha256:")
            or not holdout_policy_id.startswith("sha256:")
        ):
            return {
                "ok": False,
                "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "evaluation_kernel_v2 missing binding ids"},
            }

        pinned_anchor = str((authority_pins or {}).get("anchor_suite_set_id", "")).strip()
        pinned_ledger = str((authority_pins or {}).get("active_kernel_extensions_ledger_id", "")).strip()
        pinned_runner = str((authority_pins or {}).get("suite_runner_id", "")).strip()
        pinned_holdout_policy = str((authority_pins or {}).get("holdout_policy_id", "")).strip()
        if (
            not pinned_anchor.startswith("sha256:")
            or not pinned_ledger.startswith("sha256:")
            or anchor_suite_set_id != pinned_anchor
            or extensions_ledger_id != pinned_ledger
        ):
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_EXT_LEDGER_PIN_MISMATCH",
                    "detail": "evaluation_kernel_v2 suite-set/ledger bindings do not match active pins",
                },
            }
        if not pinned_runner.startswith("sha256:") or suite_runner_id != pinned_runner:
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_SUITE_RUNNER_PIN_MISMATCH",
                    "detail": "evaluation_kernel_v2 suite runner binding does not match active pins",
                },
            }
        if not pinned_holdout_policy.startswith("sha256:") or holdout_policy_id != pinned_holdout_policy:
            return {
                "ok": False,
                "refutation": {
                    "code": "HOLDOUT_POLICY_PIN_MISMATCH",
                    "detail": "evaluation_kernel_v2 holdout policy binding does not match active pins",
                },
            }

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

    if schema_version == "evaluation_kernel_v2" or scoring_kind == "OMEGA_BENCHMARK_SUITE_COMPOSITE":
        observed_runner_id = hash_bytes(tool_path.read_bytes())
        pinned_runner = str((authority_pins or {}).get("suite_runner_id", "")).strip()
        if observed_runner_id != str(ek.get("suite_runner_id", "")).strip():
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_SUITE_RUNNER_PIN_MISMATCH",
                    "detail": "composite score runner hash does not match kernel suite_runner_id",
                },
            }
        if not pinned_runner.startswith("sha256:") or observed_runner_id != pinned_runner:
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_SUITE_RUNNER_PIN_MISMATCH",
                    "detail": "composite score runner hash does not match pinned suite_runner_id",
                },
            }
        cmd = [
            sys.executable,
            str(tool_path),
            "--mode",
            "composite_once",
            "--repo_root",
            str(score_repo_root),
            "--ticks",
            str(max(1, int(ticks_u64))),
            "--seed_u64",
            "0",
            "--series_prefix",
            series_prefix,
            "--runs_root",
            str(runs_root),
            "--ek_id",
            str(ek.get("ek_id", "")) if str(ek.get("ek_id", "")).strip().startswith("sha256:") else _active_ek_id(score_repo_root),
            "--anchor_suite_set_id",
            str(ek.get("anchor_suite_set_id")),
            "--extensions_ledger_id",
            str(ek.get("extensions_ledger_id")),
            "--suite_runner_id",
            str(ek.get("suite_runner_id")),
            "--holdout_policy_id",
            str(ek.get("holdout_policy_id")),
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

        run_dir = runs_root / series_prefix
        receipt_path = run_dir / "BENCHMARK_RUN_RECEIPT_v2.json"
        benchmark_run_receipt_v2: dict[str, Any] | None = None
        if receipt_path.exists() and receipt_path.is_file():
            try:
                benchmark_run_receipt_v2 = json.loads(receipt_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                benchmark_run_receipt_v2 = None
            if not isinstance(benchmark_run_receipt_v2, dict):
                benchmark_run_receipt_v2 = None
            elif str(benchmark_run_receipt_v2.get("schema_version", "")).strip() != "benchmark_run_receipt_v2":
                benchmark_run_receipt_v2 = None
            elif not (
                str(benchmark_run_receipt_v2.get("anchor_suite_set_id", "")).strip()
                == str(ek.get("anchor_suite_set_id", "")).strip()
                and str(benchmark_run_receipt_v2.get("extensions_ledger_id", "")).strip()
                == str(ek.get("extensions_ledger_id", "")).strip()
                and str(benchmark_run_receipt_v2.get("suite_runner_id", "")).strip()
                == str(ek.get("suite_runner_id", "")).strip()
            ):
                benchmark_run_receipt_v2 = None
            elif str(benchmark_run_receipt_v2.get("holdout_policy_id", "")).strip() not in {"", str(ek.get("holdout_policy_id", "")).strip()}:
                benchmark_run_receipt_v2 = None

        if run.returncode != 0:
            invalid_code = "EVAL_STAGE_FAIL"
            invalid_detail = "composite benchmark runner failed"
            for line in (run.stdout.splitlines() + run.stderr.splitlines()):
                text = str(line).strip()
                if text.startswith("INVALID:"):
                    invalid_code = text.split(":", 1)[1].strip() or "EVAL_STAGE_FAIL"
                    break
                if text.startswith("DETAIL:"):
                    invalid_detail = text.split(":", 1)[1].strip() or invalid_detail
            mapped_code = "EVAL_STAGE_FAIL"
            if invalid_code in {
                "EK_EXT_LEDGER_PIN_MISMATCH",
                "EK_SUITE_RUNNER_PIN_MISMATCH",
                "EK_SUITE_LIST_MISMATCH",
                "EK_EXTENSION_SUITE_FAILED",
                "EK_ANCHOR_SUITE_FAILED",
                "HOLDOUT_POLICY_PIN_MISMATCH",
                "HOLDOUT_ACCESS_VIOLATION",
                "SUITE_IO_CONTRACT_VIOLATION",
                "HOLDOUT_PACK_MATERIALIZED",
                "PREDICTIONS_MISSING_OR_MALFORMED",
                "NONDETERMINISM_DETECTED",
            }:
                mapped_code = invalid_code
            elif invalid_code == "SUITE_FAILURE":
                mapped_code = "EK_EXTENSION_SUITE_FAILED"
            if isinstance(benchmark_run_receipt_v2, dict):
                suites = benchmark_run_receipt_v2.get("executed_suites")
                if isinstance(suites, list):
                    failed_sources = sorted(
                        {
                            str(row.get("suite_source", "")).strip().upper()
                            for row in suites
                            if isinstance(row, dict) and str(row.get("suite_outcome", "")).strip().upper() != "PASS"
                        }
                    )
                    if "ANCHOR" in failed_sources:
                        mapped_code = "EK_ANCHOR_SUITE_FAILED"
                    elif failed_sources:
                        mapped_code = "EK_EXTENSION_SUITE_FAILED"
            return {
                "ok": False,
                "refutation": {
                    "code": mapped_code,
                    "detail": invalid_detail,
                    "evidence_hashes": [hash_bytes(run.stdout.encode("utf-8")), hash_bytes(run.stderr.encode("utf-8"))],
                },
                "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            }

        if not isinstance(benchmark_run_receipt_v2, dict):
            return {
                "ok": False,
                "refutation": {
                    "code": "EVAL_STAGE_FAIL",
                    "detail": "composite score stage missing BENCHMARK_RUN_RECEIPT_v2.json",
                },
            }
        suites_raw = benchmark_run_receipt_v2.get("executed_suites")
        if not isinstance(suites_raw, list) or not suites_raw:
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_SUITE_LIST_MISMATCH",
                    "detail": "benchmark_run_receipt_v2 missing executed_suites",
                },
                "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            }
        seen_suite_ids: set[str] = set()
        failed_anchor = False
        failed_extension = False
        expected_holdout_policy_id = str(ek.get("holdout_policy_id", "")).strip()
        receipt_holdout_policy_id = str(benchmark_run_receipt_v2.get("holdout_policy_id", "")).strip()
        if receipt_holdout_policy_id and receipt_holdout_policy_id != expected_holdout_policy_id:
            return {
                "ok": False,
                "refutation": {
                    "code": "HOLDOUT_POLICY_PIN_MISMATCH",
                    "detail": "benchmark_run_receipt_v2 holdout_policy_id does not match evaluation kernel",
                },
                "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            }
        has_holdout_suite = False
        for row in suites_raw:
            if not isinstance(row, dict):
                return {
                    "ok": False,
                    "refutation": {"code": "EK_SUITE_LIST_MISMATCH", "detail": "executed_suites row must be object"},
                    "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                }
            suite_id = str(row.get("suite_id", "")).strip()
            if not suite_id.startswith("sha256:") or suite_id in seen_suite_ids:
                return {
                    "ok": False,
                    "refutation": {"code": "EK_SUITE_LIST_MISMATCH", "detail": "executed_suites has duplicate/invalid suite_id"},
                    "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                }
            seen_suite_ids.add(suite_id)
            outcome = str(row.get("suite_outcome", "")).strip().upper()
            source = str(row.get("suite_source", "")).strip().upper()
            visibility = str(row.get("suite_visibility", "")).strip().upper()
            holdout_execution = row.get("holdout_execution")
            if outcome != "PASS":
                if source == "ANCHOR":
                    failed_anchor = True
                else:
                    failed_extension = True
            if visibility == "HOLDOUT":
                has_holdout_suite = True
                if not isinstance(holdout_execution, dict):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "SUITE_IO_CONTRACT_VIOLATION",
                            "detail": "holdout suite is missing holdout_execution evidence",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                holdout_id = str(holdout_execution.get("holdout_policy_id", "")).strip()
                if holdout_id != expected_holdout_policy_id:
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "HOLDOUT_POLICY_PIN_MISMATCH",
                            "detail": "holdout_execution holdout_policy_id does not match evaluation kernel",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                if not bool(holdout_execution.get("io_contract_enforced_b", False)):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "SUITE_IO_CONTRACT_VIOLATION",
                            "detail": "holdout_execution indicates io_contract was not enforced",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                if not bool(holdout_execution.get("sandbox_available_b", False)):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "HOLDOUT_ACCESS_VIOLATION",
                            "detail": "holdout_execution indicates OS sandbox backend was unavailable",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                if not bool(holdout_execution.get("sandbox_enforced_b", False)):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "HOLDOUT_ACCESS_VIOLATION",
                            "detail": "holdout_execution indicates OS sandbox was not enforced",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                outputs_hash = str(holdout_execution.get("candidate_outputs_hash", "")).strip()
                if not outputs_hash.startswith("sha256:"):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "PREDICTIONS_MISSING_OR_MALFORMED",
                            "detail": "holdout_execution candidate_outputs_hash is missing",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                output_files = holdout_execution.get("candidate_output_files")
                if not isinstance(output_files, list):
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "SUITE_IO_CONTRACT_VIOLATION",
                            "detail": "holdout_execution candidate_output_files must be a list",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                predictions_rows = int(holdout_execution.get("predictions_rows_u64", 0))
                if predictions_rows <= 0:
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "PREDICTIONS_MISSING_OR_MALFORMED",
                            "detail": "holdout_execution predictions_rows_u64 must be positive",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
                candidate_stage_status = str(holdout_execution.get("candidate_stage_status", "")).strip().upper()
                harness_stage_status = str(holdout_execution.get("harness_stage_status", "")).strip().upper()
                if candidate_stage_status not in {"PASS", "FAIL"} or harness_stage_status not in {"PASS", "FAIL", "SKIPPED"}:
                    return {
                        "ok": False,
                        "refutation": {
                            "code": "SUITE_IO_CONTRACT_VIOLATION",
                            "detail": "holdout_execution stage status is invalid",
                        },
                        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
                    }
        if has_holdout_suite and receipt_holdout_policy_id != expected_holdout_policy_id:
            return {
                "ok": False,
                "refutation": {
                    "code": "HOLDOUT_POLICY_PIN_MISMATCH",
                    "detail": "benchmark_run_receipt_v2 holdout suites require matching holdout_policy_id",
                },
                "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            }
        if failed_anchor or failed_extension:
            return {
                "ok": False,
                "refutation": {
                    "code": "EK_ANCHOR_SUITE_FAILED" if failed_anchor else "EK_EXTENSION_SUITE_FAILED",
                    "detail": "composite score stage includes failed suite outcome",
                },
                "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            }

        aggregate_metrics = benchmark_run_receipt_v2.get("aggregate_metrics")
        if not isinstance(aggregate_metrics, dict):
            aggregate_metrics = {}
        median_stps_obj = aggregate_metrics.get("median_stps_non_noop_q32")
        tpm_obj = aggregate_metrics.get("non_noop_ticks_per_min_q32")
        promotions_obj = aggregate_metrics.get("promotions_u64_q32")
        activation_obj = aggregate_metrics.get("activation_success_u64_q32")
        median_stps_q32 = int(median_stps_obj.get("q", 0)) if isinstance(median_stps_obj, dict) else 0
        tpm_q32 = int(tpm_obj.get("q", 0)) if isinstance(tpm_obj, dict) else 0
        promotions_u64 = int(promotions_obj.get("q", 0) >> 32) if isinstance(promotions_obj, dict) else len(suites_raw)
        activation_u64 = int(activation_obj.get("q", 0) >> 32) if isinstance(activation_obj, dict) else len(suites_raw)
        scorecard_summary = {
            "median_stps_non_noop_q32": int(median_stps_q32),
            "non_noop_ticks_per_min_f64": float(max(0.0, float(tpm_q32) / float(_Q32_ONE))),
            "promotions_u64": int(max(0, promotions_u64)),
            "activation_success_u64": int(max(0, activation_u64)),
        }
        effective_suite_ids = benchmark_run_receipt_v2.get("effective_suite_ids")
        if not isinstance(effective_suite_ids, list):
            effective_suite_ids = [str(row.get("suite_id", "")).strip() for row in suites_raw]
        return {
            "ok": True,
            "score_run_root": run_dir,
            "score_run_hash": compute_workspace_tree_id(run_dir),
            "scorecard_summary": scorecard_summary,
            "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            "effective_suite_ids": list(effective_suite_ids),
        }

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


def _run_score_stage(
    *,
    base_repo_root: Path,
    candidate_repo_root: Path,
    work_dir: Path,
    ccap_id: str,
    ek: dict[str, Any],
    ticks_override_u64: int | None = None,
    require_any_improvement_override_b: bool | None = None,
    authority_pins: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scoring = ek.get("scoring_impl")
    if not isinstance(scoring, dict):
        return {"ok": False, "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "scoring_impl missing"}}

    accept_policy = scoring.get("accept_policy")
    accept_policy_obj = accept_policy if isinstance(accept_policy, dict) else {}
    require_any_improvement_b = bool(accept_policy_obj.get("require_any_improvement_b", True))
    if isinstance(require_any_improvement_override_b, bool):
        require_any_improvement_b = bool(require_any_improvement_override_b)
    stps_delta_min_q32 = int(accept_policy_obj.get("stps_delta_min_q32", _DEFAULT_STPS_DELTA_MIN_Q32))
    if stps_delta_min_q32 < 0:
        stps_delta_min_q32 = 0
    ticks_u64 = int(accept_policy_obj.get("ticks_u64", 10))
    if ticks_u64 <= 0:
        ticks_u64 = 10
    if isinstance(ticks_override_u64, int) and int(ticks_override_u64) > 0:
        ticks_u64 = int(ticks_override_u64)

    score_base = _run_score_stage_once(
        score_repo_root=base_repo_root,
        work_dir=work_dir,
        ccap_id=ccap_id,
        ek=ek,
        run_label="base",
        ticks_u64=ticks_u64,
        authority_pins=authority_pins,
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
        authority_pins=authority_pins,
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
            "benchmark_run_receipt_v2": (
                dict(score_cand.get("benchmark_run_receipt_v2"))
                if isinstance(score_cand.get("benchmark_run_receipt_v2"), dict)
                else None
            ),
            "effective_suite_ids": list(score_cand.get("effective_suite_ids", []))
            if isinstance(score_cand.get("effective_suite_ids"), list)
            else None,
        }

    return {
        "ok": True,
        "score_base_summary": score_base_summary,
        "score_cand_summary": score_cand_summary,
        "score_delta_summary": score_delta_summary,
        "score_base_run_hash": str(score_base.get("score_run_hash", "")),
        "score_cand_run_hash": str(score_cand.get("score_run_hash", "")),
        "benchmark_run_receipt_v2": (
            dict(score_cand.get("benchmark_run_receipt_v2"))
            if isinstance(score_cand.get("benchmark_run_receipt_v2"), dict)
            else None
        ),
        "effective_suite_ids": list(score_cand.get("effective_suite_ids", []))
        if isinstance(score_cand.get("effective_suite_ids"), list)
        else None,
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
        if not isinstance(payload, dict):
            continue
        schema_version = str(payload.get("schema_version", "")).strip()
        if schema_version not in {"evaluation_kernel_v1", "evaluation_kernel_v2"}:
            continue
        digest = canon_hash_obj(payload)
        if digest != active_ek_id:
            continue
        validate_schema(payload, schema_version)
        return payload
    raise RuntimeError("EVAL_STAGE_FAIL")


def run_ek(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
    out_dir: Path,
    effective_budget_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_logs: list[str] = []

    cpu_start = int(time.process_time() * 1000)
    wall_start = int(time.time() * 1000)
    declared_budgets = ccap.get("budgets")
    if isinstance(effective_budget_limits, dict):
        effective_budgets = normalize_ccap_budget_limits(effective_budget_limits)
        budget_profile_id = canon_hash_obj(
            {
                "schema_version": "ccap_effective_budget_profile_v1",
                "limits": effective_budgets,
                "tuple": effective_ccap_budget_tuple(limits=effective_budgets),
                "source": "provided",
            }
        )
    else:
        budget_profile = resolve_effective_ccap_budget_profile(
            declared_budgets=declared_budgets if isinstance(declared_budgets, dict) else {},
        )
        effective_budgets = dict(budget_profile["limits"])
        budget_profile_id = str(budget_profile["profile_id"])
    effective_budget_tuple = effective_ccap_budget_tuple(limits=effective_budgets)

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

    try:
        authority_pins = load_authority_pins(repo_root)
    except Exception:  # noqa: BLE001
        authority_pins = {}
    ek_schema_version = str(ek.get("schema_version", "")).strip()

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

    if ek_schema_version == "evaluation_kernel_v2":
        pinned_anchor = str((authority_pins or {}).get("anchor_suite_set_id", "")).strip()
        pinned_ledger = str((authority_pins or {}).get("active_kernel_extensions_ledger_id", "")).strip()
        pinned_runner = str((authority_pins or {}).get("suite_runner_id", "")).strip()
        pinned_holdout = str((authority_pins or {}).get("holdout_policy_id", "")).strip()
        ek_anchor = str(ek.get("anchor_suite_set_id", "")).strip()
        ek_ledger = str(ek.get("extensions_ledger_id", "")).strip()
        ek_runner_id = str(ek.get("suite_runner_id", "")).strip()
        ek_holdout_id = str(ek.get("holdout_policy_id", "")).strip()
        if (
            not pinned_anchor.startswith("sha256:")
            or not pinned_ledger.startswith("sha256:")
            or not ek_anchor.startswith("sha256:")
            or not ek_ledger.startswith("sha256:")
            or ek_anchor != pinned_anchor
            or ek_ledger != pinned_ledger
        ):
            return {
                "determinism_check": "REFUTED",
                "eval_status": "REFUTED",
                "decision": "REJECT",
                "refutation": {
                    "code": "EK_EXT_LEDGER_PIN_MISMATCH",
                    "detail": "active evaluation_kernel_v2 suite-set/ledger bindings mismatch active pins",
                },
                "applied_tree_id": "sha256:" + ("0" * 64),
                "realized_out_id": "",
                "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
                "logs_hash": hash_bytes(b""),
            }
        if (
            not pinned_runner.startswith("sha256:")
            or not ek_runner_id.startswith("sha256:")
            or ek_runner_id != pinned_runner
        ):
            return {
                "determinism_check": "REFUTED",
                "eval_status": "REFUTED",
                "decision": "REJECT",
                "refutation": {
                    "code": "EK_SUITE_RUNNER_PIN_MISMATCH",
                    "detail": "active evaluation_kernel_v2 suite runner binding mismatch active pin",
                },
                "applied_tree_id": "sha256:" + ("0" * 64),
                "realized_out_id": "",
                "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
                "logs_hash": hash_bytes(b""),
            }
        if (
            not pinned_holdout.startswith("sha256:")
            or not ek_holdout_id.startswith("sha256:")
            or ek_holdout_id != pinned_holdout
        ):
            return {
                "determinism_check": "REFUTED",
                "eval_status": "REFUTED",
                "decision": "REJECT",
                "refutation": {
                    "code": "HOLDOUT_POLICY_PIN_MISMATCH",
                    "detail": "active evaluation_kernel_v2 holdout policy binding mismatch active pin",
                },
                "applied_tree_id": "sha256:" + ("0" * 64),
                "realized_out_id": "",
                "cost_vector": _cost_vector(cpu_ms=0, wall_ms=0, mem_mb=0, disk_mb=0),
                "logs_hash": hash_bytes(b""),
            }

    fast_ek = _survival_drill_fast_ek_enabled()
    smoke_ek_enabled = bool(_ccap_smoke_ek_enabled() and (not fast_ek))
    smoke_only_ek_enabled = bool(_ccap_smoke_only_enabled() and smoke_ek_enabled)
    smoke_budget_ladder_v1 = _smoke_budget_ladder_from_env()
    smoke_budget_start_rung_u8 = _smoke_budget_start_rung_u8(ladder_len=len(smoke_budget_ladder_v1))
    smoke_budget_max_bumps_u8 = _smoke_budget_max_bumps_u8()
    smoke_winner_escalate_full_ek_b = bool(smoke_only_ek_enabled and _smoke_winner_escalate_full_ek_enabled())
    smoke_rung_u8 = int(smoke_budget_start_rung_u8)
    smoke_budget_tuple = dict(smoke_budget_ladder_v1[max(0, int(smoke_rung_u8) - 1)])
    smoke_score_ticks_u64 = _smoke_score_ticks_u64(default_ticks_u64=5)

    realize_a = _realize_once(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
        effective_budgets=effective_budgets,
        out_dir=out_dir / "realize_a",
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

    applied_tree_a = str(realize_a.get("applied_tree_id"))
    realized_out_a = str(realize_a.get("realized_out_id"))
    transcript_a = str(realize_a.get("transcript_id", ""))

    # Survival Drill v1: run a single REALIZE pass, skip determinism and scoring stages.
    # REALIZE still enforces patch application + repo harness, so verification remains meaningful.
    if fast_ek:
        stage_logs.append(f"REALIZE:PASS:{applied_tree_a}:{realized_out_a}:{transcript_a}")
        cpu_ms = int(time.process_time() * 1000) - cpu_start
        wall_ms = int(time.time() * 1000) - wall_start
        mem_mb = _self_mem_mb()
        disk_mb = workspace_disk_mb(out_dir)
        cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)
        if _budget_exceeded(budgets=effective_budgets, cost=cost):
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
                "effective_budget_limits": dict(effective_budgets),
                "effective_budget_tuple": dict(effective_budget_tuple),
                "effective_budget_profile_id": str(budget_profile_id),
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
            "effective_budget_limits": dict(effective_budgets),
            "effective_budget_tuple": dict(effective_budget_tuple),
            "effective_budget_profile_id": str(budget_profile_id),
        }

    enforce_deterministic_compilation = (
        str(os.environ.get("OMEGA_ENFORCE_DETERMINISTIC_COMPILATION", "0")).strip().lower()
        in {"1", "true", "yes", "on"}
    )

    realize_b = _realize_once(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
        effective_budgets=effective_budgets,
        out_dir=out_dir / "realize_b",
    )
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

    if smoke_ek_enabled:
        smoke_ladder_len_u8 = int(max(1, len(smoke_budget_ladder_v1)))
        smoke_start_idx = int(max(0, min(smoke_ladder_len_u8 - 1, int(smoke_budget_start_rung_u8) - 1)))
        smoke_final_idx = int(
            max(
                smoke_start_idx,
                min(
                    smoke_ladder_len_u8 - 1,
                    smoke_start_idx + int(max(0, int(smoke_budget_max_bumps_u8))),
                ),
            )
        )
        smoke_passed_b = False
        for rung_idx in range(smoke_start_idx, smoke_final_idx + 1):
            smoke_rung_u8 = int(rung_idx + 1)
            smoke_budget_tuple = dict(smoke_budget_ladder_v1[rung_idx])
            smoke_score = _run_score_stage(
                base_repo_root=repo_root,
                candidate_repo_root=Path(realize_a["workspace"]),
                work_dir=out_dir / "smoke_ek" / f"rung_{int(smoke_rung_u8):02d}",
                ccap_id=ccap_id,
                ek=ek,
                ticks_override_u64=int(smoke_score_ticks_u64),
                require_any_improvement_override_b=False,
                authority_pins=authority_pins if isinstance(authority_pins, dict) else None,
            )
            if not bool(smoke_score.get("ok", False)):
                smoke_refutation = dict(
                    smoke_score.get("refutation") or {"code": "SMOKE_EK_STAGE_FAIL", "detail": "smoke EK failed"}
                )
                smoke_refutation_code = (
                    str(smoke_refutation.get("code", "SMOKE_EK_STAGE_FAIL")).strip() or "SMOKE_EK_STAGE_FAIL"
                )
                smoke_refutation_detail = str(smoke_refutation.get("detail", "smoke EK failed")).strip() or "smoke EK failed"
                pass_through_smoke_code = smoke_refutation_code in {
                    "EK_EXT_LEDGER_PIN_MISMATCH",
                    "EK_SUITE_RUNNER_PIN_MISMATCH",
                    "EK_SUITE_LIST_MISMATCH",
                    "EK_EXTENSION_SUITE_FAILED",
                    "EK_ANCHOR_SUITE_FAILED",
                }
                cpu_ms = int(time.process_time() * 1000) - cpu_start
                wall_ms = int(time.time() * 1000) - wall_start
                mem_mb = _self_mem_mb()
                disk_mb = workspace_disk_mb(out_dir)
                cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)
                return {
                    "determinism_check": "PASS",
                    "eval_status": "FAIL",
                    "decision": "REJECT",
                    "refutation": {
                        "code": smoke_refutation_code if pass_through_smoke_code else "SMOKE_EK_FAIL",
                        "detail": (
                            smoke_refutation_detail
                            if pass_through_smoke_code
                            else f"{smoke_refutation_code}:{smoke_refutation_detail}"
                        ),
                    },
                    "applied_tree_id": applied_tree_a,
                    "realized_out_id": realized_out_a,
                    "cost_vector": cost,
                    "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
                    "effective_budget_limits": dict(effective_budgets),
                    "effective_budget_tuple": dict(effective_budget_tuple),
                    "effective_budget_profile_id": str(budget_profile_id),
                    "smoke_ek_enabled_b": True,
                    "smoke_only_ek_enabled_b": bool(smoke_only_ek_enabled),
                    "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64),
                    "smoke_budget_ladder_len_u8": int(smoke_ladder_len_u8),
                    "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8),
                    "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8),
                    "smoke_rung_u8": int(smoke_rung_u8),
                    "smoke_budget_tuple": dict(smoke_budget_tuple),
                }
            stage_logs.append(
                "SMOKE_EK:PASS:"
                f"rung_u8={int(smoke_rung_u8)}:"
                f"ticks_u64={int(smoke_score_ticks_u64)}:"
                f"time_ms_max={int(smoke_budget_tuple['time_ms_max'])}"
            )
            smoke_base_summary = smoke_score.get("score_base_summary")
            smoke_cand_summary = smoke_score.get("score_cand_summary")
            smoke_delta_summary = smoke_score.get("score_delta_summary")
            if not isinstance(smoke_base_summary, dict):
                smoke_base_summary = None
            if not isinstance(smoke_cand_summary, dict):
                smoke_cand_summary = None
            if not isinstance(smoke_delta_summary, dict):
                smoke_delta_summary = None

            if not smoke_only_ek_enabled:
                smoke_passed_b = True
                break

            cpu_ms = int(time.process_time() * 1000) - cpu_start
            wall_ms = int(time.time() * 1000) - wall_start
            mem_mb = _self_mem_mb()
            disk_mb = workspace_disk_mb(out_dir)
            cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)
            smoke_time_exceeded_b = int(cost.get("wall_ms", 0)) > int(smoke_budget_tuple.get("time_ms_max", 0))
            smoke_stage_exceeded_b = int(cost.get("cpu_ms", 0)) > int(smoke_budget_tuple.get("stage_cost_budget", 0))
            smoke_disk_exceeded_b = int(cost.get("disk_mb", 0)) > int(smoke_budget_tuple.get("disk_mb_max", 0))
            smoke_budget_exceeded_b = bool(smoke_time_exceeded_b or smoke_stage_exceeded_b or smoke_disk_exceeded_b)
            smoke_time_ms_max = int(smoke_budget_tuple.get("time_ms_max", 0))
            smoke_too_slow_b = bool(
                smoke_time_ms_max > 0
                and int(cost.get("wall_ms", 0)) > int(2 * smoke_time_ms_max)
            )
            if smoke_too_slow_b and int(rung_idx) >= int(smoke_final_idx):
                stage_logs.append(
                    "SMOKE_EK:TOO_SLOW_DROP:"
                    f"rung_u8={int(smoke_rung_u8)}:"
                    f"wall_ms={int(cost.get('wall_ms', 0))}:"
                    f"time_ms_max={int(smoke_time_ms_max)}"
                )
                return {
                    "determinism_check": "PASS",
                    "eval_status": "FAIL",
                    "decision": "REJECT",
                    "refutation": {
                        "code": "SMOKE_TOO_SLOW",
                        "detail": (
                            f"wall_ms={int(cost.get('wall_ms', 0))} "
                            f"max_allowed_wall_ms={int(2 * smoke_time_ms_max)} "
                            f"rung_u8={int(smoke_rung_u8)}"
                        ),
                    },
                    "applied_tree_id": applied_tree_a,
                    "realized_out_id": realized_out_a,
                    "cost_vector": cost,
                    "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
                    "effective_budget_limits": dict(effective_budgets),
                    "effective_budget_tuple": dict(effective_budget_tuple),
                    "effective_budget_profile_id": str(budget_profile_id),
                    "smoke_ek_enabled_b": True,
                    "smoke_only_ek_enabled_b": True,
                    "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64),
                    "smoke_budget_ladder_len_u8": int(smoke_ladder_len_u8),
                    "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8),
                    "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8),
                    "smoke_rung_u8": int(smoke_rung_u8),
                    "smoke_budget_tuple": dict(smoke_budget_tuple),
                }
            if smoke_budget_exceeded_b:
                can_bump_b = bool(rung_idx < smoke_final_idx and rung_idx < (smoke_ladder_len_u8 - 1))
                if can_bump_b:
                    stage_logs.append(
                        "SMOKE_EK:BUDGET_EXCEEDED_RERUN:"
                        f"from_rung_u8={int(smoke_rung_u8)}:"
                        f"to_rung_u8={int(smoke_rung_u8 + 1)}"
                    )
                    continue
                return {
                    "determinism_check": "PASS",
                    "eval_status": "FAIL",
                    "decision": "REJECT",
                    "refutation": {
                        "code": "SMOKE_EK_BUDGET_EXCEEDED",
                        "detail": (
                            f"wall_ms={int(cost.get('wall_ms', 0))}/{int(smoke_budget_tuple.get('time_ms_max', 0))} "
                            f"cpu_ms={int(cost.get('cpu_ms', 0))}/{int(smoke_budget_tuple.get('stage_cost_budget', 0))} "
                            f"disk_mb={int(cost.get('disk_mb', 0))}/{int(smoke_budget_tuple.get('disk_mb_max', 0))}"
                        ),
                    },
                    "applied_tree_id": applied_tree_a,
                    "realized_out_id": realized_out_a,
                    "cost_vector": cost,
                    "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
                    "effective_budget_limits": dict(effective_budgets),
                    "effective_budget_tuple": dict(effective_budget_tuple),
                    "effective_budget_profile_id": str(budget_profile_id),
                    "smoke_ek_enabled_b": True,
                    "smoke_only_ek_enabled_b": True,
                    "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64),
                    "smoke_budget_ladder_len_u8": int(smoke_ladder_len_u8),
                    "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8),
                    "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8),
                    "smoke_rung_u8": int(smoke_rung_u8),
                    "smoke_budget_tuple": dict(smoke_budget_tuple),
                }
            smoke_passed_b = True
            if smoke_winner_escalate_full_ek_b:
                stage_logs.append(f"SMOKE_EK:WINNER_ESCALATE_FULL_EK:rung_u8={int(smoke_rung_u8)}")
                break
            return {
                "determinism_check": "PASS",
                "eval_status": "PASS",
                "decision": "PROMOTE",
                "refutation": None,
                "applied_tree_id": applied_tree_a,
                "realized_out_id": realized_out_a,
                "cost_vector": cost,
                "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
                "scorecard_summary": smoke_cand_summary if isinstance(smoke_cand_summary, dict) else None,
                "score_base_summary": smoke_base_summary,
                "score_cand_summary": smoke_cand_summary,
                "score_delta_summary": smoke_delta_summary,
                "benchmark_run_receipt_v2": (
                    dict(smoke_score.get("benchmark_run_receipt_v2"))
                    if isinstance(smoke_score.get("benchmark_run_receipt_v2"), dict)
                    else None
                ),
                "effective_budget_limits": dict(effective_budgets),
                "effective_budget_tuple": dict(effective_budget_tuple),
                "effective_budget_profile_id": str(budget_profile_id),
                "smoke_ek_enabled_b": True,
                "smoke_only_ek_enabled_b": True,
                "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64),
                "smoke_budget_ladder_len_u8": int(smoke_ladder_len_u8),
                "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8),
                "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8),
                "smoke_rung_u8": int(smoke_rung_u8),
                "smoke_budget_tuple": dict(smoke_budget_tuple),
            }

        if smoke_only_ek_enabled and not smoke_passed_b:
            cpu_ms = int(time.process_time() * 1000) - cpu_start
            wall_ms = int(time.time() * 1000) - wall_start
            mem_mb = _self_mem_mb()
            disk_mb = workspace_disk_mb(out_dir)
            cost = _cost_vector(cpu_ms=cpu_ms, wall_ms=wall_ms, mem_mb=mem_mb, disk_mb=disk_mb)
            return {
                "determinism_check": "PASS",
                "eval_status": "FAIL",
                "decision": "REJECT",
                "refutation": {
                    "code": "SMOKE_EK_FAIL",
                    "detail": "smoke EK did not pass within configured ladder bounds",
                },
                "applied_tree_id": applied_tree_a,
                "realized_out_id": realized_out_a,
                "cost_vector": cost,
                "logs_hash": hash_bytes("\n".join(stage_logs).encode("utf-8")),
                "effective_budget_limits": dict(effective_budgets),
                "effective_budget_tuple": dict(effective_budget_tuple),
                "effective_budget_profile_id": str(budget_profile_id),
                "smoke_ek_enabled_b": True,
                "smoke_only_ek_enabled_b": True,
                "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64),
                "smoke_budget_ladder_len_u8": int(smoke_ladder_len_u8),
                "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8),
                "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8),
                "smoke_rung_u8": int(smoke_rung_u8),
                "smoke_budget_tuple": dict(smoke_budget_tuple),
            }

    score = _run_score_stage(
        base_repo_root=repo_root,
        candidate_repo_root=Path(realize_a["workspace"]),
        work_dir=out_dir,
        ccap_id=ccap_id,
        ek=ek,
        authority_pins=authority_pins if isinstance(authority_pins, dict) else None,
    )
    if not bool(score.get("ok", False)):
        ref = dict(score.get("refutation") or {"code": "EVAL_STAGE_FAIL", "detail": "score stage failed"})
        score_base_summary = score.get("score_base_summary")
        score_cand_summary = score.get("score_cand_summary")
        score_delta_summary = score.get("score_delta_summary")
        scorecard_summary = score_cand_summary if isinstance(score_cand_summary, dict) else None
        benchmark_run_receipt_v2 = score.get("benchmark_run_receipt_v2")
        if not isinstance(benchmark_run_receipt_v2, dict):
            benchmark_run_receipt_v2 = None
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
            "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            "smoke_ek_enabled_b": bool(smoke_ek_enabled),
            "smoke_only_ek_enabled_b": bool(smoke_only_ek_enabled),
            "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64) if smoke_ek_enabled else 0,
            "smoke_budget_ladder_len_u8": int(len(smoke_budget_ladder_v1)) if smoke_ek_enabled else 0,
            "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8) if smoke_ek_enabled else 0,
            "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8) if smoke_ek_enabled else 0,
            "smoke_rung_u8": int(smoke_rung_u8) if smoke_ek_enabled else 0,
            "smoke_budget_tuple": dict(smoke_budget_tuple) if smoke_ek_enabled else None,
        }

    score_base_hash = str(score.get("score_base_run_hash", "")).strip()
    score_cand_hash = str(score.get("score_cand_run_hash", "")).strip()
    score_hash = score_cand_hash or str(score.get("score_run_hash", "")).strip()
    score_base_summary = score.get("score_base_summary")
    score_cand_summary = score.get("score_cand_summary")
    score_delta_summary = score.get("score_delta_summary")
    scorecard_summary = score.get("scorecard_summary")
    benchmark_run_receipt_v2 = score.get("benchmark_run_receipt_v2")
    if not isinstance(benchmark_run_receipt_v2, dict):
        benchmark_run_receipt_v2 = None
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

    if _budget_exceeded(budgets=effective_budgets, cost=cost):
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
            "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
            "effective_budget_limits": dict(effective_budgets),
            "effective_budget_tuple": dict(effective_budget_tuple),
            "effective_budget_profile_id": str(budget_profile_id),
            "smoke_ek_enabled_b": bool(smoke_ek_enabled),
            "smoke_only_ek_enabled_b": bool(smoke_only_ek_enabled),
            "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64) if smoke_ek_enabled else 0,
            "smoke_budget_ladder_len_u8": int(len(smoke_budget_ladder_v1)) if smoke_ek_enabled else 0,
            "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8) if smoke_ek_enabled else 0,
            "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8) if smoke_ek_enabled else 0,
            "smoke_rung_u8": int(smoke_rung_u8) if smoke_ek_enabled else 0,
            "smoke_budget_tuple": dict(smoke_budget_tuple) if smoke_ek_enabled else None,
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
        "benchmark_run_receipt_v2": benchmark_run_receipt_v2,
        "effective_budget_limits": dict(effective_budgets),
        "effective_budget_tuple": dict(effective_budget_tuple),
        "effective_budget_profile_id": str(budget_profile_id),
        "smoke_ek_enabled_b": bool(smoke_ek_enabled),
        "smoke_only_ek_enabled_b": bool(smoke_only_ek_enabled),
        "smoke_ek_score_ticks_u64": int(smoke_score_ticks_u64) if smoke_ek_enabled else 0,
        "smoke_budget_ladder_len_u8": int(len(smoke_budget_ladder_v1)) if smoke_ek_enabled else 0,
        "smoke_budget_start_rung_u8": int(smoke_budget_start_rung_u8) if smoke_ek_enabled else 0,
        "smoke_budget_max_bumps_u8": int(smoke_budget_max_bumps_u8) if smoke_ek_enabled else 0,
        "smoke_rung_u8": int(smoke_rung_u8) if smoke_ek_enabled else 0,
        "smoke_budget_tuple": dict(smoke_budget_tuple) if smoke_ek_enabled else None,
    }


__all__ = ["run_ek"]
