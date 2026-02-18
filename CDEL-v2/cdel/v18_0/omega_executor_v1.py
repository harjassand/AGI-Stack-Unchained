"""Dispatch executor for omega daemon v18.0."""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any

from orchestrator.common.run_invoker_v1 import run_module

from .omega_common_v1 import (
    fail,
    repo_root,
    require_no_absolute_paths,
    require_relpath,
    tree_hash,
    validate_schema,
    write_hashed_json,
)
from .omega_observer_index_v1 import update_index_from_subrun_best_effort
from .omega_registry_v2 import resolve_campaign
from .omega_runaway_v1 import resolve_env_overrides, runaway_enabled


_SKIP_VERIFIER_ENV_RE = re.compile(r"^V[0-9][A-Z0-9_]*_SKIP_[A-Z0-9_]+$")
_DEV_BENCHMARK_MODE_ENV = "OMEGA_DEV_BENCHMARK_MODE"
_EXEC_WORKSPACE_ROOT_REL = ".omega_v18_exec_workspace"
_EXEC_WORKSPACE_MAX_DIRS = 256
_EXEC_WORKSPACE_MAX_BYTES = 16 * 1024 * 1024 * 1024
_COPY_MATERIALIZE_CAMPAIGNS = {"rsi_sas_code_v12_0"}
_SUBRUN_PRUNE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
_SUBRUN_PRUNE_FILE_NAMES = (".DS_Store",)
_SUBRUN_PRUNE_CAMPAIGN_ALLOWLIST: dict[str, tuple[str, ...]] = {}


def _pinned_pythonpath(root: Path | None = None) -> str:
    root = (root or repo_root()).resolve()
    # Prefer the tracked agi-orchestrator tree (exists in git worktrees) over untracked Extension-1 overlays.
    ext_root = root / "agi-orchestrator"
    return ":".join(
        [
            str(root),
            str(root / "CDEL-v2"),
            str(ext_root),
        ]
    )


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _dir_size_bytes(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda row: row.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += int(entry.stat(follow_symlinks=False).st_size)
            except OSError:
                continue
    return int(total)


def _prune_exec_workspace(workspace_root: Path, *, preserve: set[str] | None = None) -> None:
    if not workspace_root.exists() or not workspace_root.is_dir():
        return
    keep = set(preserve or set())
    rows: list[tuple[Path, int]] = []
    for row in sorted(workspace_root.iterdir(), key=lambda path: path.name):
        if not row.is_dir() or row.is_symlink():
            continue
        rows.append((row, _dir_size_bytes(row)))
    total_bytes = sum(size for _, size in rows)
    while len(rows) > _EXEC_WORKSPACE_MAX_DIRS or total_bytes > _EXEC_WORKSPACE_MAX_BYTES:
        victim_index = -1
        for idx, (candidate, _candidate_bytes) in enumerate(rows):
            if candidate.name not in keep:
                victim_index = idx
                break
        if victim_index < 0:
            break
        victim, victim_bytes = rows.pop(victim_index)
        _remove_path(victim)
        total_bytes = max(0, total_bytes - victim_bytes)


def _materialize_subrun_root(*, exec_root_abs: Path, subrun_root_abs: Path, mode: str = "auto") -> bool:
    """Materialize subrun root by rename when possible; fallback to copy+delete on EXDEV."""
    _remove_path(subrun_root_abs)
    subrun_root_abs.parent.mkdir(parents=True, exist_ok=True)
    if not exec_root_abs.exists() and not exec_root_abs.is_symlink():
        subrun_root_abs.mkdir(parents=True, exist_ok=True)
        return False
    if mode == "copy":
        shutil.copytree(exec_root_abs, subrun_root_abs, dirs_exist_ok=True)
        return False
    try:
        exec_root_abs.rename(subrun_root_abs)
        return True
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    shutil.copytree(exec_root_abs, subrun_root_abs, dirs_exist_ok=True)
    _remove_path(exec_root_abs)
    return False


def _prune_subrun_root(*, subrun_root_abs: Path, campaign_id: str) -> None:
    if not subrun_root_abs.exists() or not subrun_root_abs.is_dir():
        return

    for dirname in _SUBRUN_PRUNE_DIR_NAMES:
        for path in sorted(subrun_root_abs.rglob(dirname), key=lambda row: row.as_posix()):
            try:
                if path.is_dir() or path.is_symlink():
                    _remove_path(path)
            except OSError:
                continue

    for filename in _SUBRUN_PRUNE_FILE_NAMES:
        for path in sorted(subrun_root_abs.rglob(filename), key=lambda row: row.as_posix()):
            try:
                if path.is_file() or path.is_symlink():
                    _remove_path(path)
            except OSError:
                continue

    for rel in sorted(_SUBRUN_PRUNE_CAMPAIGN_ALLOWLIST.get(str(campaign_id), ())):
        rel_path = require_relpath(rel)
        candidate = subrun_root_abs / rel_path
        if candidate.exists() or candidate.is_symlink():
            _remove_path(candidate)


def _is_skip_verifier_env_key(key: str) -> bool:
    key_norm = key.strip().upper()
    if key_norm == "V16_1_SKIP_DETERMINISM":
        return True
    return _SKIP_VERIFIER_ENV_RE.fullmatch(key_norm) is not None


def _dev_benchmark_mode_enabled() -> bool:
    return str(os.environ.get(_DEV_BENCHMARK_MODE_ENV, "0")).strip() == "1"


def _guard_skip_verifier_env(overrides: dict[str, str]) -> dict[str, str]:
    inherited_blocked = sorted(k for k in os.environ if _is_skip_verifier_env_key(k))
    override_blocked = sorted(k for k in overrides if _is_skip_verifier_env_key(k))
    if not inherited_blocked and not override_blocked:
        return dict(overrides)

    if _dev_benchmark_mode_enabled():
        return dict(overrides)

    fail("FORBIDDEN_SKIP_ENV")
    return {}


def dispatch_campaign(
    *,
    tick_u64: int,
    decision_plan: dict[str, Any],
    registry: dict[str, Any],
    state_root: Path,
    run_seed_u64: int,
    runaway_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    action_kind = str(decision_plan.get("action_kind"))
    if action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
        return None, None, None

    if action_kind == "RUN_CAMPAIGN":
        campaign_id = str(decision_plan.get("campaign_id"))
        cap = resolve_campaign(registry, campaign_id)
    else:
        capability_id = str(decision_plan.get("assigned_capability_id"))
        caps = registry.get("capabilities")
        if not isinstance(caps, list):
            fail("SCHEMA_FAIL")
        rows = sorted(
            [
                row
                for row in caps
                if isinstance(row, dict)
                and bool(row.get("enabled", False))
                and str(row.get("capability_id")) == capability_id
            ],
            key=lambda row: str(row.get("campaign_id")),
        )
        if not rows:
            fail("CAPABILITY_NOT_FOUND")
        preferred_campaign = str(decision_plan.get("campaign_id", "")).strip()
        if preferred_campaign:
            selected = [row for row in rows if str(row.get("campaign_id")) == preferred_campaign]
            if not selected:
                fail("CAPABILITY_NOT_FOUND")
            cap = selected[0]
        else:
            cap = rows[0]
        campaign_id = str(cap.get("campaign_id"))

    py_module = str(cap.get("orchestrator_module"))
    campaign_pack_rel = require_relpath(cap.get("campaign_pack_rel"))
    subrun_state_rel = require_relpath(cap.get("state_dir_rel"))

    action_id = str(decision_plan.get("plan_id", "sha256:0")).split(":", 1)[-1][:16]
    dispatch_dir = state_root / "dispatch" / action_id
    subrun_root_rel_from_state = f"subruns/{action_id}_{campaign_id}"
    subrun_root_abs = state_root / subrun_root_rel_from_state
    omega_repo_root = repo_root().resolve()
    workspace_namespace = str(os.environ.get("OMEGA_EXEC_WORKSPACE_NAMESPACE", "")).strip()
    if workspace_namespace:
        workspace_prefix = hashlib.sha256(workspace_namespace.encode("utf-8")).hexdigest()[:12]
        exec_root_name = f"{workspace_prefix}_{action_id}_{campaign_id}"
    else:
        exec_root_name = f"{action_id}_{campaign_id}"
    exec_root_abs = omega_repo_root / _EXEC_WORKSPACE_ROOT_REL / exec_root_name
    campaign_pack_arg = campaign_pack_rel
    out_dir_arg = f"{_EXEC_WORKSPACE_ROOT_REL}/{exec_root_name}"

    _remove_path(exec_root_abs)
    exec_root_abs.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        "--campaign_pack",
        campaign_pack_arg,
        "--out_dir",
        out_dir_arg,
    ]

    invocation_env_overrides: dict[str, str] | None = None
    declared = decision_plan.get("runaway_env_overrides")
    if runaway_enabled(runaway_cfg) and declared is not None:
        if not isinstance(runaway_cfg, dict):
            fail("SCHEMA_FAIL")
        if not isinstance(declared, dict):
            fail("SCHEMA_FAIL")
        escalation_level = int(decision_plan.get("runaway_escalation_level_u64", 0))
        expected_env = resolve_env_overrides(runaway_cfg, campaign_id, escalation_level)
        declared_env = {str(k): str(v) for k, v in declared.items()}
        if declared_env != expected_env:
            fail("NONDETERMINISTIC")
        invocation_env_overrides = expected_env
    invocation_env_overrides = _guard_skip_verifier_env(dict(invocation_env_overrides or {}))

    run_result = run_module(
        py_module=py_module,
        argv=argv,
        cwd=omega_repo_root,
        output_dir=dispatch_dir,
        extra_env={
            "OMEGA_TICK_U64": str(int(tick_u64)),
            "OMEGA_RUN_SEED_U64": str(run_seed_u64),
            "PYTHONPATH": _pinned_pythonpath(omega_repo_root),
            **(invocation_env_overrides or {}),
        },
    )

    materialize_mode = str(os.environ.get("OMEGA_SUBRUN_MATERIALIZE_MODE", "auto")).strip().lower()
    if campaign_id in _COPY_MATERIALIZE_CAMPAIGNS:
        materialize_mode = "copy"
    if materialize_mode not in {"auto", "copy"}:
        fail("SCHEMA_FAIL")
    _materialize_subrun_root(
        exec_root_abs=exec_root_abs,
        subrun_root_abs=subrun_root_abs,
        mode=materialize_mode,
    )
    if campaign_id not in _COPY_MATERIALIZE_CAMPAIGNS:
        _remove_path(exec_root_abs)
    _prune_exec_workspace(exec_root_abs.parent, preserve={exec_root_abs.name})

    update_index_from_subrun_best_effort(
        campaign_id=campaign_id,
        subrun_root_abs=subrun_root_abs,
    )
    _prune_subrun_root(subrun_root_abs=subrun_root_abs, campaign_id=campaign_id)

    payload = {
        "schema_version": "omega_dispatch_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "campaign_id": campaign_id,
        "capability_id": str(cap.get("capability_id")),
        "invocation": {
            "py_module": py_module,
            "argv": argv,
            "env_fingerprint_hash": run_result["env_fingerprint_hash"],
            **({"env_overrides": invocation_env_overrides or {}} if runaway_enabled(runaway_cfg) else {}),
        },
        "subrun": {
            "subrun_root_rel": subrun_root_rel_from_state,
            "state_dir_rel": subrun_state_rel,
            "subrun_tree_hash": tree_hash(subrun_root_abs),
        },
        "stdout_hash": run_result["stdout_hash"],
        "stderr_hash": run_result["stderr_hash"],
        "return_code": int(run_result["return_code"]),
    }

    require_no_absolute_paths(payload)
    out_path, receipt, digest = write_hashed_json(
        dispatch_dir,
        "omega_dispatch_receipt_v1.json",
        payload,
        id_field="receipt_id",
    )
    validate_schema(receipt, "omega_dispatch_receipt_v1")

    ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "dispatch_receipt_path": out_path,
        "campaign_entry": cap,
        "repo_root_abs": omega_repo_root,
        "exec_root_abs": exec_root_abs,
        "exec_state_rel_repo": f"{_EXEC_WORKSPACE_ROOT_REL}/{exec_root_name}/{subrun_state_rel}",
        "subrun_root_abs": subrun_root_abs,
        "subrun_root_rel_state": subrun_root_rel_from_state,
        "subrun_state_rel_state": f"{subrun_root_rel_from_state}/{subrun_state_rel}",
        "pythonpath": _pinned_pythonpath(omega_repo_root),
        "invocation_env_overrides": dict(invocation_env_overrides or {}),
    }
    return receipt, digest, ctx


__all__ = ["dispatch_campaign"]
