"""Run GE SH-1 v0.3 optimizer and emit CCAP promotion bundles (staged, disabled by default)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .ccap_runtime_v1 import materialize_repo_snapshot
from .omega_common_v1 import OmegaV18Error, canon_hash_obj, fail, load_canon_dict, repo_root, validate_schema
from .patch_diff_v1 import build_unified_patch_bytes

_DEFAULT_BACKLOG_REGISTRY_REL = "campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json"
_DEFAULT_BACKLOG_GOAL_QUEUE_REL = "campaigns/rsi_omega_daemon_v18_0_prod/goals/omega_goal_queue_v1.json"
_DEFAULT_PREFLIGHT_LOOP_WINDOW_K_U64 = 16
_DEFAULT_PREFLIGHT_LOOP_REPEAT_THRESHOLD_U64 = 3
_DEFAULT_PREFLIGHT_LOOP_DISABLE_TICKS_U64 = 100
_LOOP_BREAKER_STATE_SCHEMA = "ge_preflight_loop_breaker_state_v1"
_LOOP_BREAKER_DIAGNOSTIC_SCHEMA = "ge_preflight_loop_breaker_diagnostic_v1"
_LOOP_BREAKER_GLOBAL_FALLBACK_REL = ".omega_v18_exec_workspace/loop_breaker"
_LOOP_BREAKER_SCOPE_GLOBAL = "GLOBAL"
_LOOP_BREAKER_SCOPE_RESET_ON_LAUNCH = "RESET_ON_LAUNCH"
_DEFAULT_CAPABILITY_BACKLOG: tuple[str, ...] = (
    "RSI_OMEGA_SELF_OPTIMIZE_CORE",
    "RSI_OMEGA_SKILL_TRANSFER",
    "RSI_OMEGA_SKILL_ONTOLOGY",
    "RSI_OMEGA_SKILL_EFF_FLYWHEEL",
    "RSI_OMEGA_SKILL_THERMO",
    "RSI_OMEGA_SKILL_PERSISTENCE",
    "RSI_OMEGA_SKILL_ALIGNMENT",
    "RSI_OMEGA_SKILL_BOUNDLESS_MATH",
    "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE",
    "RSI_OMEGA_SKILL_SWARM",
    "RSI_OMEGA_SKILL_MODEL_GENESIS",
    "RSI_MODEL_GENESIS_V10",
    "RSI_EUDRS_U_INDEX_REBUILD",
    "RSI_EUDRS_U_ONTOLOGY_UPDATE",
    "RSI_EUDRS_U_EVAL_CAC",
    "RSI_EUDRS_U_TRAIN",
)


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1":
        fail("SCHEMA_FAIL")
    return payload


def _discover_runs_root(out_dir: Path) -> Path | None:
    current = out_dir.resolve()
    # When running under the live-wire worktree (which is itself nested under `runs/<series>/`),
    # prefer the current series directory so GE does not scan the entire historical `runs/` corpus.
    for parent in [current, *current.parents]:
        try:
            if parent.parent.name == "runs":
                return parent
        except Exception:  # noqa: BLE001
            continue
    for parent in [current, *current.parents]:
        if parent.name == "runs":
            return parent
    return None


def _canonical_json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _tick_u64() -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "0")).strip() or "0"
    try:
        return max(0, int(raw))
    except Exception:
        return 0


def _loop_breaker_cfg(pack: dict[str, Any]) -> tuple[int, int, int]:
    def _resolve(name_pack: str, name_env: str, default: int) -> int:
        env_raw = str(os.environ.get(name_env, "")).strip()
        if env_raw:
            return max(1, int(env_raw))
        if name_pack in pack:
            return max(1, int(pack.get(name_pack, default)))
        return int(default)

    window_k = _resolve(
        "preflight_loop_window_k_u64",
        "OMEGA_GE_PREFLIGHT_LOOP_WINDOW_K_U64",
        _DEFAULT_PREFLIGHT_LOOP_WINDOW_K_U64,
    )
    repeat_threshold = _resolve(
        "preflight_loop_repeat_threshold_u64",
        "OMEGA_GE_PREFLIGHT_LOOP_REPEAT_THRESHOLD_U64",
        _DEFAULT_PREFLIGHT_LOOP_REPEAT_THRESHOLD_U64,
    )
    disable_ticks = _resolve(
        "preflight_loop_disable_ticks_u64",
        "OMEGA_GE_PREFLIGHT_LOOP_DISABLE_TICKS_U64",
        _DEFAULT_PREFLIGHT_LOOP_DISABLE_TICKS_U64,
    )
    return int(window_k), int(repeat_threshold), int(disable_ticks)


def _looks_like_sha256(value: str) -> bool:
    raw = str(value).strip()
    if not raw.startswith("sha256:"):
        return False
    return len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _loop_breaker_scope_mode(pack: dict[str, Any]) -> str:
    env_raw = str(os.environ.get("OMEGA_LONG_RUN_LOOP_BREAKER_SCOPE_MODE", "")).strip().upper()
    if env_raw in {_LOOP_BREAKER_SCOPE_GLOBAL, _LOOP_BREAKER_SCOPE_RESET_ON_LAUNCH}:
        return env_raw
    pack_raw = str(pack.get("loop_breaker_scope_mode", "")).strip().upper()
    if pack_raw in {_LOOP_BREAKER_SCOPE_GLOBAL, _LOOP_BREAKER_SCOPE_RESET_ON_LAUNCH}:
        return pack_raw
    return _LOOP_BREAKER_SCOPE_GLOBAL


def _loop_breaker_scope_key(*, scope_mode: str, launch_manifest_hash: str | None) -> str:
    if scope_mode == _LOOP_BREAKER_SCOPE_RESET_ON_LAUNCH and isinstance(launch_manifest_hash, str):
        if _looks_like_sha256(launch_manifest_hash):
            return launch_manifest_hash.split(":", 1)[1]
    return "global"


def _loop_breaker_state_path(
    root: Path,
    *,
    scope_mode: str,
    launch_manifest_hash: str | None,
) -> Path:
    daemon_state_root = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT", "")).strip()
    ge_state_root = str(os.environ.get("OMEGA_GE_STATE_ROOT", "")).strip()
    if daemon_state_root:
        base = Path(daemon_state_root).resolve() / "long_run" / "loop_breaker"
    elif ge_state_root:
        base = Path(ge_state_root).resolve() / "long_run" / "loop_breaker"
    else:
        base = root / _LOOP_BREAKER_GLOBAL_FALLBACK_REL
    scope_key = _loop_breaker_scope_key(scope_mode=scope_mode, launch_manifest_hash=launch_manifest_hash)
    return base / f"{scope_key}_rsi_ge_symbiotic_optimizer_sh1_v0_1.loop_breaker_state_v1.json"


def _default_loop_breaker_state(
    *,
    window_k: int,
    repeat_threshold: int,
    disable_ticks: int,
    scope_mode: str,
    scope_key: str,
) -> dict[str, Any]:
    return {
        "schema_version": _LOOP_BREAKER_STATE_SCHEMA,
        "window_k_u64": int(window_k),
        "repeat_threshold_u64": int(repeat_threshold),
        "disable_ticks_u64": int(disable_ticks),
        "scope_mode": str(scope_mode),
        "scope_key": str(scope_key),
        "disabled_until_tick_u64": 0,
        "recent_failure_signature_hashes": [],
        "rolling_window_hash": canon_hash_obj({"schema_version": "ge_preflight_window_v1", "rows": []}),
        "last_reason_code": "",
    }


def _load_loop_breaker_state(
    *,
    root: Path,
    window_k: int,
    repeat_threshold: int,
    disable_ticks: int,
    scope_mode: str,
    launch_manifest_hash: str | None,
) -> dict[str, Any]:
    scope_key = _loop_breaker_scope_key(scope_mode=scope_mode, launch_manifest_hash=launch_manifest_hash)
    path = _loop_breaker_state_path(
        root,
        scope_mode=scope_mode,
        launch_manifest_hash=launch_manifest_hash,
    )
    state = _default_loop_breaker_state(
        window_k=window_k,
        repeat_threshold=repeat_threshold,
        disable_ticks=disable_ticks,
        scope_mode=scope_mode,
        scope_key=scope_key,
    )
    if not path.exists() or not path.is_file():
        return state
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != _LOOP_BREAKER_STATE_SCHEMA:
        return state
    rows = payload.get("recent_failure_signature_hashes")
    if not isinstance(rows, list):
        return state
    if str(payload.get("scope_mode", "")).strip() != scope_mode:
        return state
    if str(payload.get("scope_key", "")).strip() != scope_key:
        return state
    state["disabled_until_tick_u64"] = max(0, int(payload.get("disabled_until_tick_u64", 0)))
    state["recent_failure_signature_hashes"] = [str(row).strip() for row in rows if str(row).strip()][-window_k:]
    state["last_reason_code"] = str(payload.get("last_reason_code", "")).strip()
    state["rolling_window_hash"] = canon_hash_obj(
        {
            "schema_version": "ge_preflight_window_v1",
            "rows": list(state["recent_failure_signature_hashes"]),
        }
    )
    return state


def _write_loop_breaker_state(
    *,
    root: Path,
    state: dict[str, Any],
    scope_mode: str,
    launch_manifest_hash: str | None,
) -> None:
    path = _loop_breaker_state_path(
        root,
        scope_mode=scope_mode,
        launch_manifest_hash=launch_manifest_hash,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, state)


def _preflight_reason_code(reason_text: str) -> str:
    raw = str(reason_text).strip()
    if raw.startswith("INVALID:"):
        raw = raw.split(":", 1)[1]
    parts = [part for part in raw.split(":") if part]
    if not parts:
        return "VERIFY_ERROR:UNKNOWN"
    if parts[0] == "VERIFY_ERROR":
        if len(parts) >= 2:
            return f"VERIFY_ERROR:{parts[1]}"
        return "VERIFY_ERROR"
    return parts[0]


def _record_preflight_failure(
    *,
    root: Path,
    out_dir: Path,
    tick_u64: int,
    reason_text: str,
    state: dict[str, Any],
    scope_mode: str,
    launch_manifest_hash: str | None,
) -> dict[str, Any]:
    reason_code = _preflight_reason_code(reason_text)
    signature_hash = canon_hash_obj(
        {
            "schema_version": "ge_preflight_failure_signature_v1",
            "reason_code": reason_code,
        }
    )
    rows = [str(row).strip() for row in list(state.get("recent_failure_signature_hashes") or []) if str(row).strip()]
    window_k = max(1, int(state.get("window_k_u64", _DEFAULT_PREFLIGHT_LOOP_WINDOW_K_U64)))
    repeat_threshold = max(1, int(state.get("repeat_threshold_u64", _DEFAULT_PREFLIGHT_LOOP_REPEAT_THRESHOLD_U64)))
    disable_ticks = max(1, int(state.get("disable_ticks_u64", _DEFAULT_PREFLIGHT_LOOP_DISABLE_TICKS_U64)))
    rows.append(signature_hash)
    if len(rows) > window_k:
        rows = rows[-window_k:]
    repeat_count = int(sum(1 for row in rows if row == signature_hash))
    disabled_until = int(max(0, int(state.get("disabled_until_tick_u64", 0))))
    diagnostic_only_active_b = repeat_count >= repeat_threshold
    if diagnostic_only_active_b:
        disabled_until = max(disabled_until, int(tick_u64) + int(disable_ticks))
    rolling_window_hash = canon_hash_obj({"schema_version": "ge_preflight_window_v1", "rows": rows})
    state["disabled_until_tick_u64"] = int(disabled_until)
    state["recent_failure_signature_hashes"] = rows
    state["rolling_window_hash"] = rolling_window_hash
    state["last_reason_code"] = reason_code
    _write_loop_breaker_state(
        root=root,
        state=state,
        scope_mode=scope_mode,
        launch_manifest_hash=launch_manifest_hash,
    )

    diagnostic_payload = {
        "schema_version": _LOOP_BREAKER_DIAGNOSTIC_SCHEMA,
        "tick_u64": int(tick_u64),
        "reason_code": reason_code,
        "reason_text": str(reason_text),
        "signature_hash": signature_hash,
        "repeat_count_u64": int(repeat_count),
        "window_k_u64": int(window_k),
        "repeat_threshold_u64": int(repeat_threshold),
        "disable_ticks_u64": int(disable_ticks),
        "disabled_until_tick_u64": int(disabled_until),
        "rolling_window_hash": rolling_window_hash,
        "diagnostic_only_active_b": bool(diagnostic_only_active_b),
    }
    write_canon_json(out_dir / "ge_preflight_loop_breaker_diagnostic_v1.json", diagnostic_payload)
    return diagnostic_payload


def _sanitize_goal_id_piece(capability_id: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(capability_id).strip())
    while "__" in out:
        out = out.replace("__", "_")
    out = out.strip("_")
    return out or "capability"


def _build_goal_id(capability_id: str, ordinal_u64: int) -> str:
    return f"goal_cap_backlog_{_sanitize_goal_id_piece(capability_id)}_{int(ordinal_u64):04d}"


def _build_unified_patch(*, relpath: str, before: str, after: str) -> bytes:
    return build_unified_patch_bytes(relpath=relpath, before_text=before, after_text=after)


def _resolve_capability_backlog(pack: dict[str, Any]) -> list[str]:
    rows = pack.get("capability_backlog")
    if not isinstance(rows, list):
        return list(_DEFAULT_CAPABILITY_BACKLOG)
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        cap_id = str(row).strip()
        if not cap_id or cap_id in seen:
            continue
        seen.add(cap_id)
        out.append(cap_id)
    return out


def _resolve_backlog_relpaths(pack: dict[str, Any]) -> tuple[str, str]:
    registry_rel = str(pack.get("backlog_registry_rel", _DEFAULT_BACKLOG_REGISTRY_REL)).strip() or _DEFAULT_BACKLOG_REGISTRY_REL
    goal_queue_rel = (
        str(pack.get("backlog_goal_queue_rel", _DEFAULT_BACKLOG_GOAL_QUEUE_REL)).strip() or _DEFAULT_BACKLOG_GOAL_QUEUE_REL
    )
    return registry_rel, goal_queue_rel


def _validate_goal_queue_payload_minimal(goal_queue_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if str(goal_queue_payload.get("schema_version", "")).strip() != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    goals = goal_queue_payload.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if not goal_id or not capability_id or not status:
            fail("SCHEMA_FAIL")
        out.append(row)
    return out


def _patch_touches_relpath(*, patch_bytes: bytes, relpath: str) -> bool:
    target = f"+++ b/{str(relpath).strip().replace('\\', '/')}"
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.split("\t", 1)[0].strip()
        if line == target:
            return True
    return False


def _patch_touches_capability_registry(*, patch_bytes: bytes) -> bool:
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.split("\t", 1)[0].strip()
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :]
        if str(rel).endswith("omega_capability_registry_v2.json"):
            return True
    return False


def _patch_head_rows(patch_bytes: bytes, *, max_lines: int = 80) -> list[str]:
    return patch_bytes.decode("utf-8", errors="replace").splitlines()[:max_lines]


def _preflight_merged_patch(*, root: Path, out_dir: Path, merged_patch: bytes) -> None:
    if not merged_patch:
        return
    debug_path = out_dir / "debug_patch_head.txt"
    scratch_root = out_dir / "_preflight_workspace"
    if scratch_root.exists():
        shutil.rmtree(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    try:
        materialize_repo_snapshot(root, scratch_root)
        patch_path = scratch_root / ".merged.patch"
        patch_path.write_bytes(merged_patch)

        init_run = subprocess.run(
            ["git", "init", "-q"],
            cwd=scratch_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if int(init_run.returncode) != 0:
            fail(f"VERIFY_ERROR:PATCH_PREFLIGHT_GIT_INIT_FAILED:status_u64={int(init_run.returncode)}")

        check_run = subprocess.run(
            ["git", "apply", "--check", "-p1", str(patch_path)],
            cwd=scratch_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if int(check_run.returncode) != 0:
            head_rows = _patch_head_rows(merged_patch, max_lines=80)
            head_text = ("\n".join(head_rows) + "\n") if head_rows else ""
            debug_path.write_text(head_text, encoding="utf-8")
            detail = (check_run.stderr or check_run.stdout).strip()
            if not detail:
                detail = f"git apply --check exited with status {int(check_run.returncode)}"
            detail = detail.replace(str(scratch_root.resolve()), "<workspace>")
            detail = detail.replace(str(scratch_root), "<workspace>")
            detail = detail.replace(str(patch_path.resolve()), "<patch>")
            detail = detail.replace(str(patch_path), "<patch>")
            head_inline = "\\n".join(head_rows)
            fail(
                "VERIFY_ERROR:PATCH_PREFLIGHT_APPLY_CHECK_FAILED:"
                f"detail={detail}:debug_patch_head_rel=debug_patch_head.txt:patch_head={head_inline}"
            )
    finally:
        if scratch_root.exists():
            shutil.rmtree(scratch_root, ignore_errors=True)


def _build_capability_backlog_patch(*, root: Path, pack: dict[str, Any], skip_registry_diff: bool = False) -> bytes:
    backlog = _resolve_capability_backlog(pack)
    if not backlog:
        return b""

    registry_rel, goal_queue_rel = _resolve_backlog_relpaths(pack)
    registry_path = root / registry_rel
    goal_queue_path = root / goal_queue_rel
    if not registry_path.exists() or not registry_path.is_file():
        return b""
    if not goal_queue_path.exists() or not goal_queue_path.is_file():
        return b""

    registry_before = registry_path.read_text(encoding="utf-8")
    goal_queue_before = goal_queue_path.read_text(encoding="utf-8")

    registry_payload = load_canon_dict(registry_path)
    goal_queue_payload = load_canon_dict(goal_queue_path)
    validate_schema(registry_payload, "omega_capability_registry_v2")
    # Some v18 installs do not ship a dedicated omega_goal_queue_v1 schema file.
    # Keep deterministic shape checks so backlog injection still runs fail-closed.
    try:
        validate_schema(goal_queue_payload, "omega_goal_queue_v1")
    except Exception:  # noqa: BLE001
        _validate_goal_queue_payload_minimal(goal_queue_payload)

    capabilities = registry_payload.get("capabilities")
    goals = goal_queue_payload.get("goals")
    if not isinstance(capabilities, list) or not isinstance(goals, list):
        fail("SCHEMA_FAIL")

    by_capability_id: dict[str, dict[str, Any]] = {}
    for row in capabilities:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        cap_id = str(row.get("capability_id", "")).strip()
        if cap_id:
            by_capability_id[cap_id] = row

    newly_enabled: list[str] = []
    target_goal_caps: list[str] = []
    for cap_id in backlog:
        row = by_capability_id.get(cap_id)
        if row is None:
            continue
        if bool(row.get("enabled", False)):
            target_goal_caps.append(cap_id)
            continue
        row["enabled"] = True
        newly_enabled.append(cap_id)
        target_goal_caps.append(cap_id)

    existing_goal_ids: set[str] = set()
    existing_goal_caps: set[str] = set()
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        cap_id = str(row.get("capability_id", "")).strip()
        if goal_id:
            existing_goal_ids.add(goal_id)
        if cap_id:
            existing_goal_caps.add(cap_id)

    goals_added: list[str] = []
    for cap_id in target_goal_caps:
        if cap_id in existing_goal_caps:
            continue
        ordinal_u64 = 1
        goal_id = _build_goal_id(cap_id, ordinal_u64)
        while goal_id in existing_goal_ids:
            ordinal_u64 += 1
            goal_id = _build_goal_id(cap_id, ordinal_u64)
        goals.append(
            {
                "capability_id": cap_id,
                "goal_id": goal_id,
                "status": "PENDING",
            }
        )
        existing_goal_ids.add(goal_id)
        existing_goal_caps.add(cap_id)
        goals_added.append(cap_id)

    if not newly_enabled and not goals_added:
        return b""

    registry_after = _canonical_json_text(registry_payload)
    goal_queue_after = _canonical_json_text(goal_queue_payload)

    patch_chunks: list[bytes] = []
    patch_registry = _build_unified_patch(relpath=registry_rel, before=registry_before, after=registry_after)
    if patch_registry and not skip_registry_diff:
        patch_chunks.append(patch_registry)
    patch_goals = _build_unified_patch(relpath=goal_queue_rel, before=goal_queue_before, after=goal_queue_after)
    if patch_goals:
        patch_chunks.append(patch_goals)
    if not patch_chunks:
        return b""
    return b"".join(patch_chunks)


def _inject_capability_backlog_patch(
    *,
    root: Path,
    out_dir: Path,
    pack: dict[str, Any],
    ccap_id: str,
    ccap_relpath: str,
    patch_relpath: str,
) -> tuple[str, str, str, bool, str | None]:
    backlog_patch_bytes = _build_capability_backlog_patch(root=root, pack=pack)
    if not backlog_patch_bytes:
        return ccap_id, ccap_relpath, patch_relpath, False, None

    ccap_path = out_dir / ccap_relpath
    patch_path = out_dir / patch_relpath
    if not ccap_path.exists() or not ccap_path.is_file():
        fail("MISSING_STATE_INPUT")
    if not patch_path.exists() or not patch_path.is_file():
        fail("MISSING_STATE_INPUT")

    ccap_payload = load_canon_dict(ccap_path)
    validate_schema(ccap_payload, "ccap_v1")
    payload = ccap_payload.get("payload")
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if str(payload.get("kind", "")).strip() != "PATCH":
        return ccap_id, ccap_relpath, patch_relpath, False, None

    original_patch = patch_path.read_bytes()
    registry_rel, _goal_queue_rel = _resolve_backlog_relpaths(pack)
    skip_registry_diff = _patch_touches_relpath(patch_bytes=original_patch, relpath=registry_rel)
    if not skip_registry_diff:
        # The proposal space may target either v18_0 or v18_0_prod capability registry paths.
        # If the proposal already edits any capability registry file, do not inject an additional
        # registry diff from backlog state to avoid deterministic preflight merge/apply conflicts.
        skip_registry_diff = _patch_touches_capability_registry(patch_bytes=original_patch)
    backlog_patch_bytes = _build_capability_backlog_patch(root=root, pack=pack, skip_registry_diff=skip_registry_diff)
    if not backlog_patch_bytes:
        return ccap_id, ccap_relpath, patch_relpath, False, None

    merged_patch = original_patch
    if merged_patch and not merged_patch.endswith(b"\n"):
        merged_patch += b"\n"
    merged_patch += backlog_patch_bytes
    try:
        _preflight_merged_patch(root=root, out_dir=out_dir, merged_patch=merged_patch)
    except OmegaV18Error as exc:
        raw = str(exc).strip()
        if "VERIFY_ERROR" not in raw:
            raise
        # Do not hard-fail on backlog injection preflight errors; keep original proposal
        # and let loop-breaker diagnostics decide when to enter diagnostic-only mode.
        return ccap_id, ccap_relpath, patch_relpath, False, raw

    patch_hex = hashlib.sha256(merged_patch).hexdigest()
    next_patch_relpath = f"ccap/blobs/sha256_{patch_hex}.patch"
    next_patch_path = out_dir / next_patch_relpath
    next_patch_path.parent.mkdir(parents=True, exist_ok=True)
    next_patch_path.write_bytes(merged_patch)

    payload["patch_blob_id"] = f"sha256:{patch_hex}"
    ccap_payload["payload"] = payload
    validate_schema(ccap_payload, "ccap_v1")
    next_ccap_id = canon_hash_obj(payload)
    next_ccap_relpath = f"ccap/sha256_{next_ccap_id.split(':', 1)[1]}.ccap_v1.json"
    next_ccap_path = out_dir / next_ccap_relpath
    next_ccap_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(next_ccap_path, ccap_payload)
    return next_ccap_id, next_ccap_relpath, next_patch_relpath, True, None


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()
    out_dir.mkdir(parents=True, exist_ok=True)
    tick_u64 = _tick_u64()
    scope_mode = _loop_breaker_scope_mode(pack)
    launch_manifest_hash = str(os.environ.get("OMEGA_LONG_RUN_LAUNCH_MANIFEST_HASH", "")).strip() or None
    loop_window_k, loop_repeat_threshold, loop_disable_ticks = _loop_breaker_cfg(pack)
    loop_state = _load_loop_breaker_state(
        root=root,
        window_k=loop_window_k,
        repeat_threshold=loop_repeat_threshold,
        disable_ticks=loop_disable_ticks,
        scope_mode=scope_mode,
        launch_manifest_hash=launch_manifest_hash,
    )
    if int(tick_u64) < int(loop_state.get("disabled_until_tick_u64", 0)):
        diagnostic_payload = {
            "schema_version": _LOOP_BREAKER_DIAGNOSTIC_SCHEMA,
            "tick_u64": int(tick_u64),
            "reason_code": "VERIFY_ERROR:DIAGNOSTIC_ONLY_COOLDOWN_ACTIVE",
            "reason_text": "loop breaker cooldown active",
            "signature_hash": canon_hash_obj(
                {
                    "schema_version": "ge_preflight_failure_signature_v1",
                    "reason_code": "VERIFY_ERROR:DIAGNOSTIC_ONLY_COOLDOWN_ACTIVE",
                }
            ),
            "repeat_count_u64": 0,
            "window_k_u64": int(loop_window_k),
            "repeat_threshold_u64": int(loop_repeat_threshold),
            "disable_ticks_u64": int(loop_disable_ticks),
            "disabled_until_tick_u64": int(loop_state.get("disabled_until_tick_u64", 0)),
            "rolling_window_hash": str(loop_state.get("rolling_window_hash", "")),
            "diagnostic_only_active_b": True,
        }
        write_canon_json(out_dir / "ge_preflight_loop_breaker_diagnostic_v1.json", diagnostic_payload)
        print("OK")
        return

    ge_config_rel = str(pack.get("ge_config_path", "tools/genesis_engine/config/ge_config_v1.json")).strip()
    authority_rel = str(pack.get("authority_pins_path", "authority/authority_pins_v1.json")).strip()
    model_id = str(pack.get("model_id", "ge-v0_3")).strip() or "ge-v0_3"
    max_ccaps = max(1, min(8, int(pack.get("max_ccaps", 1))))
    enforce_deterministic_compilation = False

    tool_path = root / "tools" / "genesis_engine" / "ge_symbiotic_optimizer_v0_3.py"
    if not tool_path.exists() or not tool_path.is_file():
        fail("MISSING_STATE_INPUT")

    recent_runs_root = _discover_runs_root(out_dir)
    ge_state_root = str(os.environ.get("OMEGA_GE_STATE_ROOT", "")).strip()
    seed_u64 = max(0, int(str(os.environ.get("OMEGA_RUN_SEED_U64", "0")).strip() or "0"))

    cmd = [
        sys.executable,
        str(tool_path),
        "--subrun_out_dir",
        str(out_dir.resolve()),
        "--ge_config_path",
        ge_config_rel,
        "--authority_pins_path",
        authority_rel,
        "--recent_runs_root",
        str(recent_runs_root.resolve()) if recent_runs_root is not None else "",
        "--ge_state_root",
        ge_state_root,
        "--seed",
        str(seed_u64),
        "--model_id",
        model_id,
        "--max_ccaps",
        str(max_ccaps),
    ]

    run_env = os.environ.copy()
    run_env["OMEGA_ENFORCE_DETERMINISTIC_COMPILATION"] = "1" if enforce_deterministic_compilation else "0"
    # Ensure the GE tool and the rest of the CCAP pipeline are using the same pins payload.
    # (The drill runner sets this env var globally; we also set it here so the campaign is
    # self-contained when invoked outside the runner.)
    run_env["OMEGA_AUTHORITY_PINS_REL"] = authority_rel

    run_result = subprocess.run(
        cmd,
        cwd=root,
        env=run_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if int(run_result.returncode) != 0:
        # Persist subprocess output for drill evidence; the dispatcher only captures this module's stderr.
        try:
            (out_dir / "ge_symbiotic_optimizer_v0_3.stdout.txt").write_text(run_result.stdout or "", encoding="utf-8")
            (out_dir / "ge_symbiotic_optimizer_v0_3.stderr.txt").write_text(run_result.stderr or "", encoding="utf-8")
        except Exception:
            pass
        fail("VERIFY_ERROR")

    summary_path = out_dir / "ge_symbiotic_optimizer_summary_v0_3.json"
    if not summary_path.exists() or not summary_path.is_file():
        fail("MISSING_STATE_INPUT")
    summary = load_canon_dict(summary_path)

    ccaps = summary.get("ccaps")
    if not isinstance(ccaps, list):
        fail("SCHEMA_FAIL")

    promotion_dir = out_dir.resolve() / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    backlog_injected = False
    for row in ccaps:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ccap_id = str(row.get("ccap_id", "")).strip()
        ccap_relpath = str(row.get("ccap_relpath", "")).strip()
        patch_relpath = str(row.get("patch_relpath", "")).strip()
        if not ccap_id or not ccap_relpath or not patch_relpath:
            fail("SCHEMA_FAIL")

        if not backlog_injected:
            ccap_id, ccap_relpath, patch_relpath, backlog_injected, preflight_error = _inject_capability_backlog_patch(
                root=root,
                out_dir=out_dir.resolve(),
                pack=pack,
                ccap_id=ccap_id,
                ccap_relpath=ccap_relpath,
                patch_relpath=patch_relpath,
            )
            if preflight_error is not None:
                diagnostic_payload = _record_preflight_failure(
                    root=root,
                    out_dir=out_dir.resolve(),
                    tick_u64=int(tick_u64),
                    reason_text=str(preflight_error),
                    state=loop_state,
                    scope_mode=scope_mode,
                    launch_manifest_hash=launch_manifest_hash,
                )
                if bool(diagnostic_payload.get("diagnostic_only_active_b", False)):
                    print("OK")
                    return

        bundle = {
            "schema_version": "omega_promotion_bundle_ccap_v1",
            "ccap_id": ccap_id,
            "ccap_relpath": ccap_relpath,
            "patch_relpath": patch_relpath,
            "activation_key": ccap_id,
            "touched_paths": [ccap_relpath, patch_relpath],
        }
        validate_schema(bundle, "omega_promotion_bundle_ccap_v1")
        bundle_hash = canon_hash_obj(bundle)
        bundle_path = promotion_dir / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
        write_canon_json(bundle_path, bundle)

    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="campaign_ge_symbiotic_optimizer_sh1_v0_1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run(
        campaign_pack=Path(args.campaign_pack).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )


if __name__ == "__main__":
    main()
