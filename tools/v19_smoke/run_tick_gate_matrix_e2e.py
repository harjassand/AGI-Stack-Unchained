#!/usr/bin/env python3
"""Tick-level E2E gate-matrix runner for v19 coordinator integration."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
_ORDERED_PATHS = [str(REPO_ROOT / "CDEL-v2"), str(REPO_ROOT)]
for _path in _ORDERED_PATHS:
    while _path in sys.path:
        sys.path.remove(_path)
for _path in reversed(_ORDERED_PATHS):
    sys.path.insert(0, _path)

import cdel.v18_0.omega_executor_v1 as v18_executor
import cdel.v18_0.omega_promoter_v1 as v18_promoter
from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, hash_file, validate_schema as validate_v18_schema, write_hashed_json
from cdel.v18_0.omega_tick_outcome_v1 import load_latest_tick_outcome
from orchestrator.omega_v18_0 import applier_v1 as applier_v18
from orchestrator.omega_v19_0 import coordinator_v1
from orchestrator.omega_v19_0 import promoter_v1 as orchestrator_promoter_v19


def _load_gate_matrix_module() -> Any:
    module_path = REPO_ROOT / "tools" / "v19_smoke" / "run_gate_matrix_e2e.py"
    spec = importlib.util.spec_from_file_location("v19_gate_matrix_e2e_module_for_tick", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GATE_MATRIX = _load_gate_matrix_module()
MORPHISM_TYPES: tuple[str, ...] = tuple(_GATE_MATRIX.MORPHISM_TYPES)


@dataclass(frozen=True)
class _CaseSpec:
    morphism_type: str
    variant: str


@dataclass
class _TickCaseResult:
    run_root: Path
    dispatch_dir: Path
    promotion_dir: Path
    tick_outcome: dict[str, Any]
    promotion_receipt: dict[str, Any]
    gate_failure: dict[str, Any] | None


@contextmanager
def _set_env(key: str, value: str) -> Iterator[None]:
    had_key = key in os.environ
    previous = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if had_key and previous is not None:
            os.environ[key] = previous
        else:
            os.environ.pop(key, None)


@contextmanager
def _patched_executor_run_module(active_case: dict[str, Any]) -> Iterator[None]:
    original_run_module = v18_executor.run_module

    def _arg_value(argv: list[str], flag: str) -> str:
        try:
            idx = argv.index(flag)
        except ValueError as exc:
            raise RuntimeError(f"MISSING_ARG:{flag}") from exc
        if idx + 1 >= len(argv):
            raise RuntimeError(f"MISSING_ARG_VALUE:{flag}")
        return str(argv[idx + 1])

    def _fake_run_module(
        *,
        py_module: str,
        argv: list[str],
        cwd: Path,
        output_dir: Path,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        spec = active_case.get("spec")
        if not isinstance(spec, _CaseSpec):
            raise RuntimeError("ACTIVE_CASE_MISSING")
        if str(py_module).strip() != "orchestrator.rsi_sas_code_v12_0":
            raise RuntimeError(f"UNEXPECTED_CAMPAIGN_MODULE:{py_module}")

        active_case["run_module_calls"] = int(active_case.get("run_module_calls", 0)) + 1
        out_dir_arg = _arg_value(argv, "--out_dir")
        exec_root = (Path(cwd) / out_dir_arg).resolve()
        promotion_dir = exec_root / "daemon" / "rsi_sas_code_v12_0" / "state" / "promotion"
        promotion_dir.mkdir(parents=True, exist_ok=True)

        bundle_payload = {
            "schema_version": "sas_code_promotion_bundle_v1",
            "candidate_algo_id": "sha256:" + ("1" * 64),
            "touched_paths": ["CDEL-v2/cdel/v12_0/verify_rsi_sas_code_v1.py"],
        }
        write_canon_json(promotion_dir / "sha256_feedface.sas_code_promotion_bundle_v1.json", bundle_payload)

        _GATE_MATRIX._build_axis_case(
            subrun_root=exec_root,
            promotion_dir=promotion_dir,
            morphism_type=spec.morphism_type,
            variant=spec.variant,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text(f"DISPATCH_OK:{spec.morphism_type}:{spec.variant}\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        env_fingerprint_hash = canon_hash_obj(
            {
                "schema_version": "env_fingerprint_v1",
                "entries": [
                    {"k": str(key), "v": str(value)}
                    for key, value in sorted((extra_env or {}).items(), key=lambda row: row[0])
                ],
            }
        )
        return {
            "return_code": 0,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout_hash": hash_file(stdout_path),
            "stderr_hash": hash_file(stderr_path),
            "env_fingerprint_hash": env_fingerprint_hash,
            "py_module": py_module,
            "argv": list(argv),
        }

    v18_executor.run_module = _fake_run_module
    try:
        yield
    finally:
        v18_executor.run_module = original_run_module


@contextmanager
def _patched_subverifier() -> Iterator[None]:
    original_coordinator_subverifier = coordinator_v1.run_subverifier
    original_orchestrator_promoter_subverifier = orchestrator_promoter_v19.run_subverifier

    def _fake_run_subverifier(
        *,
        tick_u64: int,
        dispatch_ctx: dict[str, Any] | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if dispatch_ctx is None:
            return None, None
        campaign_entry = dispatch_ctx.get("campaign_entry")
        if not isinstance(campaign_entry, dict):
            raise RuntimeError("SCHEMA_FAIL")
        out_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
        payload = {
            "schema_version": "omega_subverifier_receipt_v1",
            "receipt_id": "sha256:" + ("0" * 64),
            "tick_u64": int(tick_u64),
            "campaign_id": str(campaign_entry.get("campaign_id", "")),
            "verifier_module": str(campaign_entry.get("verifier_module", "cdel.v12_0.verify_rsi_sas_code_v1")),
            "verifier_mode": "full",
            "state_dir_hash": "sha256:" + ("0" * 64),
            "replay_repo_root_rel": None,
            "replay_repo_root_hash": None,
            "result": {
                "status": "VALID",
                "reason_code": None,
            },
            "stdout_hash": "sha256:" + ("0" * 64),
            "stderr_hash": "sha256:" + ("0" * 64),
        }
        _, receipt, digest = write_hashed_json(
            out_dir,
            "omega_subverifier_receipt_v1.json",
            payload,
            id_field="receipt_id",
        )
        validate_v18_schema(receipt, "omega_subverifier_receipt_v1")
        return receipt, digest

    coordinator_v1.run_subverifier = _fake_run_subverifier
    orchestrator_promoter_v19.run_subverifier = _fake_run_subverifier
    try:
        yield
    finally:
        coordinator_v1.run_subverifier = original_coordinator_subverifier
        orchestrator_promoter_v19.run_subverifier = original_orchestrator_promoter_subverifier


@contextmanager
def _patched_promotion_cwd() -> Iterator[None]:
    original_coordinator_promotion = coordinator_v1.run_promotion
    original_orchestrator_promoter_promotion = orchestrator_promoter_v19.run_promotion

    def _wrapped_run_promotion(
        *,
        tick_u64: int,
        dispatch_ctx: dict[str, Any] | None,
        subverifier_receipt: dict[str, Any] | None,
        allowlists: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None]:
        if dispatch_ctx is None:
            return original_coordinator_promotion(
                tick_u64=tick_u64,
                dispatch_ctx=dispatch_ctx,
                subverifier_receipt=subverifier_receipt,
                allowlists=allowlists,
            )
        subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
        if not isinstance(subrun_root_raw, (str, Path)):
            raise RuntimeError("SCHEMA_FAIL")
        with _GATE_MATRIX._chdir(Path(subrun_root_raw)):
            return original_coordinator_promotion(
                tick_u64=tick_u64,
                dispatch_ctx=dispatch_ctx,
                subverifier_receipt=subverifier_receipt,
                allowlists=allowlists,
            )

    coordinator_v1.run_promotion = _wrapped_run_promotion
    orchestrator_promoter_v19.run_promotion = _wrapped_run_promotion
    try:
        yield
    finally:
        coordinator_v1.run_promotion = original_coordinator_promotion
        orchestrator_promoter_v19.run_promotion = original_orchestrator_promoter_promotion


@contextmanager
def _patched_activation_simulate() -> Iterator[None]:
    original_coordinator_activation = coordinator_v1.run_activation
    original_applier_activation = applier_v18.run_activation

    def _wrapped_run_activation(*, tick_u64: int, dispatch_ctx: dict[str, Any] | None, promotion_receipt: dict[str, Any] | None,
                                healthcheck_suitepack: dict[str, Any], healthcheck_suite_hash: str,
                                active_manifest_hash_before: str) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None, str | None, str]:
        with _set_env("OMEGA_META_CORE_ACTIVATION_MODE", "simulate"):
            with _set_env("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1"):
                return original_coordinator_activation(
                    tick_u64=tick_u64,
                    dispatch_ctx=dispatch_ctx,
                    promotion_receipt=promotion_receipt,
                    healthcheck_suitepack=healthcheck_suitepack,
                    healthcheck_suite_hash=healthcheck_suite_hash,
                    active_manifest_hash_before=active_manifest_hash_before,
                )

    coordinator_v1.run_activation = _wrapped_run_activation
    applier_v18.run_activation = _wrapped_run_activation
    try:
        yield
    finally:
        coordinator_v1.run_activation = original_coordinator_activation
        applier_v18.run_activation = original_applier_activation


def _prepare_campaign_pack(root: Path) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0"
    dst = root / "campaign_pack"
    shutil.copytree(src, dst)

    policy = load_canon_json(dst / "omega_policy_ir_v1.json")
    policy["rules"] = []
    write_canon_json(dst / "omega_policy_ir_v1.json", policy)

    runaway_cfg = load_canon_json(dst / "omega_runaway_config_v1.json")
    runaway_cfg["enabled"] = False
    write_canon_json(dst / "omega_runaway_config_v1.json", runaway_cfg)

    write_canon_json(
        dst / "goals" / "omega_goal_queue_v1.json",
        {
            "schema_version": "omega_goal_queue_v1",
            "goals": [
                {
                    "goal_id": "goal_tick_gate_matrix_0001",
                    "capability_id": "RSI_SAS_CODE",
                    "status": "PENDING",
                }
            ],
        },
    )
    return dst / "rsi_omega_daemon_pack_v1.json"


def _single_dir(path: Path) -> Path:
    rows = sorted([row for row in path.iterdir() if row.is_dir()], key=lambda row: row.as_posix())
    if len(rows) != 1:
        raise RuntimeError(f"EXPECTED_ONE_DIR:{path}")
    return rows[0]


def _latest_json(path: Path, pattern: str) -> dict[str, Any]:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    if not rows:
        raise RuntimeError(f"MISSING_ARTIFACT:{path}:{pattern}")
    return load_canon_json(rows[-1])


def _promoted_axis_bundle_bytes(dispatch_dir: Path) -> bytes:
    path = dispatch_dir / "promotion" / "meta_core_promotion_bundle_v1" / "omega" / "axis_upgrade_bundle_v1.json"
    if not path.exists() or not path.is_file():
        raise RuntimeError("PROMOTED_AXIS_BUNDLE_MISSING")
    payload = load_canon_json(path)
    return canon_bytes(payload)


def _objective_bytes(promotion_dir: Path, filename: str) -> bytes:
    path = promotion_dir / filename
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"MISSING_OBJECTIVE:{filename}")
    return canon_bytes(load_canon_json(path))


def _collect_tick_case_result(run_root: Path) -> _TickCaseResult:
    state_root = run_root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_dir = _single_dir(state_root / "dispatch")
    subrun_root = _single_dir(state_root / "subruns")
    promotion_dir = subrun_root / "daemon" / "rsi_sas_code_v12_0" / "state" / "promotion"
    if not promotion_dir.exists() or not promotion_dir.is_dir():
        raise RuntimeError("PROMOTION_DIR_MISSING")

    tick_outcome = load_latest_tick_outcome(state_root / "perf")
    if tick_outcome is None:
        raise RuntimeError("TICK_OUTCOME_MISSING")
    promotion_receipt = _latest_json(dispatch_dir / "promotion", "sha256_*.omega_promotion_receipt_v1.json")

    gate_failure_path = promotion_dir / "axis_gate_failure_v1.json"
    gate_failure = load_canon_json(gate_failure_path) if gate_failure_path.exists() and gate_failure_path.is_file() else None
    return _TickCaseResult(
        run_root=run_root,
        dispatch_dir=dispatch_dir,
        promotion_dir=promotion_dir,
        tick_outcome=tick_outcome,
        promotion_receipt=promotion_receipt,
        gate_failure=gate_failure,
    )


def _assert_positive_tick(case: _TickCaseResult) -> None:
    outcome = case.tick_outcome
    if str(outcome.get("promotion_status", "")) != "PROMOTED":
        raise RuntimeError("EXPECTED_PROMOTED")
    if not bool(outcome.get("activation_success", False)):
        raise RuntimeError("EXPECTED_ACTIVATION_SUCCESS")
    if not bool(outcome.get("manifest_changed", False)):
        raise RuntimeError("EXPECTED_MANIFEST_CHANGED")
    if bool(outcome.get("safe_halt", False)):
        raise RuntimeError("UNEXPECTED_SAFE_HALT")


def _assert_negative_safe_halt(case: _TickCaseResult) -> tuple[str, str]:
    outcome = case.tick_outcome
    if str(outcome.get("promotion_status", "")) != "REJECTED":
        raise RuntimeError("EXPECTED_REJECTED")
    if case.gate_failure is None:
        raise RuntimeError("AXIS_GATE_FAILURE_MISSING")
    gate_outcome = str(case.gate_failure.get("outcome", "")).strip()
    gate_detail = str(case.gate_failure.get("detail", "")).strip()
    if gate_outcome != "SAFE_HALT":
        raise RuntimeError(f"EXPECTED_SAFE_HALT:{gate_outcome}")
    if not bool(outcome.get("safe_halt", False)):
        raise RuntimeError("EXPECTED_SAFE_HALT_PROPAGATION")
    reason = str(outcome.get("promotion_reason_code", ""))
    if not reason.startswith("AXIS_GATE_SAFE_HALT:"):
        raise RuntimeError(f"BAD_REASON_PREFIX:{reason}")
    return gate_outcome, gate_detail


def _assert_negative_safe_split(case: _TickCaseResult) -> tuple[str, str]:
    outcome = case.tick_outcome
    if str(outcome.get("promotion_status", "")) != "REJECTED":
        raise RuntimeError("EXPECTED_REJECTED")
    if case.gate_failure is None:
        raise RuntimeError("AXIS_GATE_FAILURE_MISSING")
    gate_outcome = str(case.gate_failure.get("outcome", "")).strip()
    gate_detail = str(case.gate_failure.get("detail", "")).strip()
    if gate_outcome != "SAFE_SPLIT":
        raise RuntimeError(f"EXPECTED_SAFE_SPLIT:{gate_outcome}")
    if bool(outcome.get("safe_halt", False)):
        raise RuntimeError("UNEXPECTED_SAFE_HALT_PROPAGATION")
    reason = str(outcome.get("promotion_reason_code", ""))
    if not reason.startswith("AXIS_GATE_SAFE_SPLIT:"):
        raise RuntimeError(f"BAD_REASON_PREFIX:{reason}")
    return gate_outcome, gate_detail


def _tick_fields(outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_kind": str(outcome.get("action_kind", "")),
        "campaign_id": outcome.get("campaign_id"),
        "promotion_status": str(outcome.get("promotion_status", "")),
        "promotion_reason_code": str(outcome.get("promotion_reason_code", "")),
        "activation_success": bool(outcome.get("activation_success", False)),
        "manifest_changed": bool(outcome.get("manifest_changed", False)),
        "safe_halt": bool(outcome.get("safe_halt", False)),
    }


def _run_tick_case(
    *,
    campaign_pack: Path,
    run_root: Path,
    case_spec: _CaseSpec,
    active_case: dict[str, Any],
) -> _TickCaseResult:
    active_case["spec"] = case_spec
    active_case["run_module_calls"] = 0
    coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=run_root,
        tick_u64=1,
        prev_state_dir=None,
    )
    run_module_calls = int(active_case.get("run_module_calls", 0))
    active_case["spec"] = None
    if run_module_calls != 1:
        raise RuntimeError(f"UNEXPECTED_RUN_MODULE_CALLS:{run_module_calls}")
    return _collect_tick_case_result(run_root)


def _run_positive_pair(
    *,
    out_dir: Path,
    campaign_pack: Path,
    morphism_type: str,
    active_case: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "morphism_type": morphism_type,
        "variant": "positive_ab_determinism",
    }
    try:
        case_spec = _CaseSpec(morphism_type=morphism_type, variant="positive")
        run_a = _run_tick_case(
            campaign_pack=campaign_pack,
            run_root=out_dir / f"{morphism_type}_positive_a",
            case_spec=case_spec,
            active_case=active_case,
        )
        run_b = _run_tick_case(
            campaign_pack=campaign_pack,
            run_root=out_dir / f"{morphism_type}_positive_b",
            case_spec=case_spec,
            active_case=active_case,
        )

        _assert_positive_tick(run_a)
        _assert_positive_tick(run_b)
        _GATE_MATRIX._assert_promoted_axis_bundle_integrity({"dispatch_dir": run_a.dispatch_dir})
        _GATE_MATRIX._assert_promoted_axis_bundle_integrity({"dispatch_dir": run_b.dispatch_dir})

        deterministic_receipt = canon_bytes(run_a.promotion_receipt) == canon_bytes(run_b.promotion_receipt)
        deterministic_j_old = _objective_bytes(run_a.promotion_dir, "objective_J_old_v1.json") == _objective_bytes(
            run_b.promotion_dir, "objective_J_old_v1.json"
        )
        deterministic_j_new = _objective_bytes(run_a.promotion_dir, "objective_J_new_v1.json") == _objective_bytes(
            run_b.promotion_dir, "objective_J_new_v1.json"
        )
        deterministic_promoted_axis_bundle = _promoted_axis_bundle_bytes(run_a.dispatch_dir) == _promoted_axis_bundle_bytes(
            run_b.dispatch_dir
        )

        row.update(
            {
                "tick_outcome_a": _tick_fields(run_a.tick_outcome),
                "tick_outcome_b": _tick_fields(run_b.tick_outcome),
                "deterministic_receipt": deterministic_receipt,
                "deterministic_objective_J_old": deterministic_j_old,
                "deterministic_objective_J_new": deterministic_j_new,
                "deterministic_promoted_axis_bundle": deterministic_promoted_axis_bundle,
                "passes": all(
                    [
                        deterministic_receipt,
                        deterministic_j_old,
                        deterministic_j_new,
                        deterministic_promoted_axis_bundle,
                    ]
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["passes"] = False
        row["error"] = f"{exc.__class__.__name__}:{exc}"
    return row


def _run_negative_case(
    *,
    out_dir: Path,
    campaign_pack: Path,
    morphism_type: str,
    variant: str,
    active_case: dict[str, Any],
    expected_outcome: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "morphism_type": morphism_type,
        "variant": variant,
    }
    try:
        case = _run_tick_case(
            campaign_pack=campaign_pack,
            run_root=out_dir / f"{morphism_type}_{variant}",
            case_spec=_CaseSpec(morphism_type=morphism_type, variant=variant),
            active_case=active_case,
        )

        if expected_outcome == "SAFE_HALT":
            gate_outcome, gate_detail = _assert_negative_safe_halt(case)
        elif expected_outcome == "SAFE_SPLIT":
            gate_outcome, gate_detail = _assert_negative_safe_split(case)
        else:
            raise RuntimeError(f"UNSUPPORTED_EXPECTED_OUTCOME:{expected_outcome}")

        row.update(
            {
                "tick_outcome": _tick_fields(case.tick_outcome),
                "gate_outcome": gate_outcome,
                "gate_detail": gate_detail,
                "passes": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["passes"] = False
        row["error"] = f"{exc.__class__.__name__}:{exc}"
    return row


def _clear_exec_workspace_namespace(namespace: str) -> None:
    workspace_root = REPO_ROOT / ".omega_v18_exec_workspace"
    if not workspace_root.exists() or not workspace_root.is_dir():
        return
    prefix = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:12] + "_"
    for path in sorted(workspace_root.iterdir(), key=lambda row: row.as_posix()):
        if not path.is_dir() or path.is_symlink():
            continue
        if not path.name.startswith(prefix):
            continue
        shutil.rmtree(path, ignore_errors=True)


def run_tick_gate_matrix(*, out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    campaign_pack = _prepare_campaign_pack(out_dir)
    active_case: dict[str, Any] = {"spec": None, "run_module_calls": 0}
    rows: list[dict[str, Any]] = []

    worker = str(os.environ.get("PYTEST_XDIST_WORKER", "single")).strip() or "single"
    workspace_namespace = f"tick_gate_matrix_{worker}"
    _clear_exec_workspace_namespace(workspace_namespace)

    with _set_env("OMEGA_EXEC_WORKSPACE_NAMESPACE", workspace_namespace):
        with _GATE_MATRIX._patched_v18_promoter():
            with _patched_executor_run_module(active_case):
                with _patched_subverifier():
                    with _patched_promotion_cwd():
                        with _patched_activation_simulate():
                            for morphism_type in MORPHISM_TYPES:
                                rows.append(
                                    _run_positive_pair(
                                        out_dir=out_dir,
                                        campaign_pack=campaign_pack,
                                        morphism_type=morphism_type,
                                        active_case=active_case,
                                    )
                                )
                                rows.append(
                                    _run_negative_case(
                                        out_dir=out_dir,
                                        campaign_pack=campaign_pack,
                                        morphism_type=morphism_type,
                                        variant="negative_missing_proof",
                                        active_case=active_case,
                                        expected_outcome="SAFE_HALT",
                                    )
                                )
                                if morphism_type == "M_T":
                                    rows.append(
                                        _run_negative_case(
                                            out_dir=out_dir,
                                            campaign_pack=campaign_pack,
                                            morphism_type="M_T",
                                            variant="negative_treaty_non_total",
                                            active_case=active_case,
                                            expected_outcome="SAFE_SPLIT",
                                        )
                                    )
                                    rows.append(
                                        _run_negative_case(
                                            out_dir=out_dir,
                                            campaign_pack=campaign_pack,
                                            morphism_type="M_T",
                                            variant="negative_treaty_no_new_acceptance",
                                            active_case=active_case,
                                            expected_outcome="SAFE_SPLIT",
                                        )
                                    )

    summary = {
        "schema_name": "v19_tick_gate_matrix_summary_v1",
        "schema_version": "v19_0",
        "workspace_namespace": workspace_namespace,
        "rows": rows,
        "all_passed": all(bool(row.get("passes", False)) for row in rows),
    }
    write_canon_json(out_dir / "v19_tick_gate_matrix_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v19 tick gate matrix e2e harness")
    parser.add_argument(
        "--out_dir",
        default="runs/v19_tick_gate_matrix_e2e",
        help="Output directory for tick-level gate-matrix artifacts",
    )
    args = parser.parse_args()

    summary = run_tick_gate_matrix(out_dir=Path(args.out_dir))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if bool(summary.get("all_passed", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
