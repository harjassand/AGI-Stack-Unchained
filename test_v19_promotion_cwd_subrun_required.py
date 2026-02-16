from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
_ORDERED_PATHS = [str(REPO_ROOT / "CDEL-v2"), str(REPO_ROOT)]
for _path in _ORDERED_PATHS:
    while _path in sys.path:
        sys.path.remove(_path)
for _path in reversed(_ORDERED_PATHS):
    sys.path.insert(0, _path)

import cdel.v18_0.omega_executor_v1 as v18_executor
from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, hash_file, validate_schema as validate_v18_schema, write_hashed_json
from cdel.v18_0.omega_tick_outcome_v1 import load_latest_tick_outcome
from orchestrator.omega_v18_0 import applier_v1 as applier_v18
from orchestrator.omega_v19_0 import coordinator_v1


def _load_gate_matrix_module():
    module_path = REPO_ROOT / "tools" / "v19_smoke" / "run_gate_matrix_e2e.py"
    spec = importlib.util.spec_from_file_location("v19_gate_matrix_e2e_module_for_promotion_cwd_test", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_exec_workspace_namespace(namespace: str) -> None:
    workspace_root = REPO_ROOT / ".omega_v18_exec_workspace"
    if not workspace_root.exists() or not workspace_root.is_dir():
        return
    # Matches the same prefixing scheme used by cdel.v18_0.omega_executor_v1.dispatch_campaign.
    import hashlib

    prefix = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:12] + "_"
    for path in sorted(workspace_root.iterdir(), key=lambda row: row.as_posix()):
        if not path.is_dir() or path.is_symlink():
            continue
        if not path.name.startswith(prefix):
            continue
        # Best-effort cleanup. Dispatch/prune should handle this too, but we want isolation.
        import shutil

        shutil.rmtree(path, ignore_errors=True)


def _prepare_campaign_pack(root: Path) -> Path:
    import shutil

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
                    "goal_id": "goal_promotion_cwd_0001",
                    "capability_id": "RSI_SAS_CODE",
                    "status": "PENDING",
                }
            ],
        },
    )
    return dst / "rsi_omega_daemon_pack_v1.json"


def test_v19_promotion_requires_subrun_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: v19 promoter loads continuity artifacts from Path('.'), which must be the subrun root."""

    gate_matrix = _load_gate_matrix_module()
    campaign_pack = _prepare_campaign_pack(tmp_path)
    out_dir = tmp_path / "run"

    workspace_namespace = "test_v19_promotion_cwd_subrun_required"
    _clear_exec_workspace_namespace(workspace_namespace)
    monkeypatch.setenv("OMEGA_EXEC_WORKSPACE_NAMESPACE", workspace_namespace)
    monkeypatch.setenv("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")
    monkeypatch.setenv("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")

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
    ) -> dict[str, object]:
        if str(py_module).strip() != "orchestrator.rsi_sas_code_v12_0":
            raise RuntimeError(f"UNEXPECTED_CAMPAIGN_MODULE:{py_module}")

        out_dir_arg = _arg_value(argv, "--out_dir")
        exec_root = (Path(cwd) / out_dir_arg).resolve()
        promotion_dir = exec_root / "daemon" / "rsi_sas_code_v12_0" / "state" / "promotion"
        promotion_dir.mkdir(parents=True, exist_ok=True)

        # This mirrors the tick gate-matrix harness: ensure touched paths trigger v19 axis-bundle requirements.
        bundle_payload = {
            "schema_version": "sas_code_promotion_bundle_v1",
            "candidate_algo_id": "sha256:" + ("1" * 64),
            "touched_paths": ["CDEL-v2/cdel/v12_0/verify_rsi_sas_code_v1.py"],
        }
        write_canon_json(promotion_dir / "sha256_feedface.sas_code_promotion_bundle_v1.json", bundle_payload)

        # Writes axis bundle + continuity artifacts under the exec_root (later materialized into subrun_root_abs).
        gate_matrix._build_axis_case(
            subrun_root=exec_root,
            promotion_dir=promotion_dir,
            morphism_type="M_SIGMA",
            variant="positive",
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        stdout_path.write_text("DISPATCH_OK\n", encoding="utf-8")
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

    monkeypatch.setattr(v18_executor, "run_module", _fake_run_module)

    def _fake_run_subverifier(
        *,
        tick_u64: int,
        dispatch_ctx: dict[str, object] | None,
    ) -> tuple[dict[str, object] | None, str | None]:
        if dispatch_ctx is None:
            return None, None
        campaign_entry = dispatch_ctx.get("campaign_entry")
        if not isinstance(campaign_entry, dict):
            raise RuntimeError("SCHEMA_FAIL")
        out_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
        payload: dict[str, object] = {
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
            payload,  # type: ignore[arg-type]
            id_field="receipt_id",
        )
        validate_v18_schema(receipt, "omega_subverifier_receipt_v1")
        return receipt, digest

    monkeypatch.setattr(coordinator_v1, "run_subverifier", _fake_run_subverifier)

    # Ensure activation runs in "simulate" mode (and doesn't mutate meta-core).
    original_activation = coordinator_v1.run_activation

    def _wrapped_run_activation(**kwargs):  # noqa: ANN003
        return original_activation(**kwargs)

    monkeypatch.setattr(coordinator_v1, "run_activation", _wrapped_run_activation)
    monkeypatch.setattr(applier_v18, "run_activation", _wrapped_run_activation)

    coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=out_dir,
        tick_u64=1,
        prev_state_dir=None,
    )

    state_root = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    tick_outcome = load_latest_tick_outcome(state_root / "perf")
    assert isinstance(tick_outcome, dict)
    assert str(tick_outcome.get("promotion_status", "")) == "PROMOTED"
