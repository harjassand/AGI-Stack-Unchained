"""Hermetic repository realization harness (H1-lite)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from ...v1_7r.canon import write_canon_json
from ..authority.authority_hash_v1 import load_authority_pins
from ..ccap_runtime_v1 import compute_workspace_tree_id, workspace_disk_mb
from ..omega_common_v1 import canon_hash_obj, hash_bytes, load_canon_dict


def _wall_ms_now() -> int:
    return int(time.time() * 1000)


def _load_build_recipes(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "authority" / "build_recipes" / "build_recipes_v1.json"
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "build_recipes_v1":
        raise RuntimeError("EVAL_STAGE_FAIL")
    recipes = payload.get("recipes")
    if not isinstance(recipes, list):
        raise RuntimeError("EVAL_STAGE_FAIL")
    by_id: dict[str, dict[str, Any]] = {}
    for row in recipes:
        if not isinstance(row, dict):
            raise RuntimeError("EVAL_STAGE_FAIL")
        recipe_id = str(row.get("recipe_id", "")).strip()
        if not recipe_id.startswith("sha256:"):
            raise RuntimeError("EVAL_STAGE_FAIL")
        if recipe_id in by_id:
            raise RuntimeError("EVAL_STAGE_FAIL")
        by_id[recipe_id] = row
    return by_id


def _resolve_cwd(work_dir: Path, cwd_policy: str) -> Path:
    policy = str(cwd_policy).strip()
    if policy == "repo_root":
        return work_dir
    if policy.startswith("subdir:"):
        rel = policy.split(":", 1)[1].strip()
        p = work_dir / rel
        if not p.exists() or not p.is_dir():
            raise RuntimeError("EVAL_STAGE_FAIL")
        return p
    raise RuntimeError("EVAL_STAGE_FAIL")


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _capture_outputs(*, work_dir: Path, out_dir: Path, out_capture_policy: dict[str, Any]) -> None:
    mode = str(out_capture_policy.get("mode", "")).strip()
    if mode == "none":
        return
    if mode != "copy_glob":
        raise RuntimeError("EVAL_STAGE_FAIL")
    patterns = out_capture_policy.get("patterns")
    if not isinstance(patterns, list):
        raise RuntimeError("EVAL_STAGE_FAIL")
    copied = set()
    for pattern_any in patterns:
        pattern = str(pattern_any).strip()
        if not pattern:
            continue
        for candidate in sorted(work_dir.glob(pattern), key=lambda row: row.as_posix()):
            if not candidate.exists():
                continue
            rel = candidate.relative_to(work_dir).as_posix()
            if rel in copied:
                continue
            if candidate.is_symlink():
                continue
            _copy_path(candidate, out_dir / rel)
            copied.add(rel)


def _build_env(*, allowlist: list[str], out_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "PYTHONHASHSEED": "0",
        "LC_ALL": "C",
        "LANG": "C",
        "OMEGA_OUT_DIR": str(out_dir),
    }
    allowed = {str(row).strip() for row in allowlist if str(row).strip()}
    for key in sorted(allowed):
        if key in os.environ:
            env[key] = str(os.environ[key])
    if "PYTHONPATH" in allowed and "PYTHONPATH" not in env:
        env["PYTHONPATH"] = "CDEL-v2:."
    return env


def _zero_cost() -> dict[str, int]:
    return {
        "cpu_ms": 0,
        "wall_ms": 0,
        "mem_mb": 0,
        "disk_mb": 0,
        "fds": 0,
        "procs": 0,
        "threads": 0,
    }


def run_repo_harness(
    *,
    repo_root: Path,
    applied_tree_checkout_dir: Path,
    build_recipe_id: str,
    budgets: dict[str, Any],
    env_contract_id: str,
    dsbx_profile_id: str,
    toolchain_root_id: str,
    sandbox_root: Path,
) -> dict[str, Any]:
    """Run pinned recipe commands in an isolated sandbox and hash outputs."""
    if str(budgets.get("net", "")) != "forbidden":
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "network access must remain forbidden"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }

    pins = load_authority_pins(repo_root)
    if str(pins.get("env_contract_id", "")) != str(env_contract_id):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "env_contract_id does not match authority pins"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }
    if str(pins.get("toolchain_root_id", "")) != str(toolchain_root_id):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "toolchain_root_id does not match authority pins"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }
    active_dsbx = pins.get("active_dsbx_profile_ids")
    if not isinstance(active_dsbx, list) or str(dsbx_profile_id) not in {str(row) for row in active_dsbx}:
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "dsbx_profile_id is not active"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }

    recipes = _load_build_recipes(repo_root)
    recipe = recipes.get(str(build_recipe_id))
    if recipe is None:
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "unknown build_recipe_id"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }

    commands = recipe.get("commands")
    allowlist = recipe.get("env_allowlist")
    out_capture_policy = recipe.get("out_capture_policy")
    if not isinstance(commands, list) or not isinstance(allowlist, list) or not isinstance(out_capture_policy, dict):
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "invalid build recipe shape"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }

    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    work_dir = sandbox_root / "work"
    out_dir = sandbox_root / "out"
    transcript_dir = sandbox_root / "transcript"
    shutil.copytree(applied_tree_checkout_dir, work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_dir.mkdir(parents=True, exist_ok=True)

    wall_start_ms = _wall_ms_now()
    events: list[dict[str, Any]] = []
    command_fail_evidence: list[str] = []
    env = _build_env(allowlist=[str(row) for row in allowlist], out_dir=out_dir)
    try:
        cwd = _resolve_cwd(work_dir, str(recipe.get("cwd_policy", "")))
    except RuntimeError:
        return {
            "ok": False,
            "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "invalid cwd_policy"},
            "out_tree_id": "sha256:" + ("0" * 64),
            "transcript_id": "sha256:" + ("0" * 64),
            "logs_hash": hash_bytes(b""),
            "cost_vector": _zero_cost(),
        }

    wall_budget_ms = int(budgets.get("wall_ms_max", 0))
    if wall_budget_ms <= 0:
        wall_budget_ms = 1

    for idx, argv_any in enumerate(commands):
        if not isinstance(argv_any, list) or not argv_any:
            return {
                "ok": False,
                "refutation": {"code": "EVAL_STAGE_FAIL", "detail": "recipe command is invalid"},
                "out_tree_id": "sha256:" + ("0" * 64),
                "transcript_id": "sha256:" + ("0" * 64),
                "logs_hash": hash_bytes(b""),
                "cost_vector": _zero_cost(),
            }
        argv = [str(x) for x in argv_any]

        elapsed_ms = _wall_ms_now() - wall_start_ms
        remaining_ms = max(1, wall_budget_ms - elapsed_ms)
        if remaining_ms <= 0:
            return {
                "ok": False,
                "refutation": {"code": "BUDGET_EXCEEDED", "detail": "wall_ms budget exhausted"},
                "out_tree_id": "sha256:" + ("0" * 64),
                "transcript_id": "sha256:" + ("0" * 64),
                "logs_hash": hash_bytes(b""),
                "cost_vector": {
                    **_zero_cost(),
                    "wall_ms": max(0, elapsed_ms),
                    "disk_mb": workspace_disk_mb(sandbox_root),
                },
            }
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=False,
                check=False,
                timeout=max(1.0, remaining_ms / 1000.0),
            )
            stdout = proc.stdout
            stderr = proc.stderr
            rc = int(proc.returncode)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
            rc = 124

        stdout_hash = hash_bytes(stdout)
        stderr_hash = hash_bytes(stderr)
        stdout_path = transcript_dir / f"step_{idx:04d}.stdout.bin"
        stderr_path = transcript_dir / f"step_{idx:04d}.stderr.bin"
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        event = {
            "step_u64": int(idx),
            "argv": argv,
            "cwd_rel": cwd.relative_to(work_dir).as_posix() if cwd != work_dir else ".",
            "return_code": rc,
            # Avoid unstable timing data in transcript hash inputs.
            "wall_ms_u64": 0,
            "stdout_hash": stdout_hash,
            "stderr_hash": stderr_hash,
        }
        events.append(event)
        command_fail_evidence.extend([stdout_hash, stderr_hash])
        if rc != 0:
            break

    events_payload = {
        "schema_version": "repo_harness_events_v1",
        "build_recipe_id": str(build_recipe_id),
        "events": events,
    }
    write_canon_json(transcript_dir / "events_v1.json", events_payload)

    _capture_outputs(
        work_dir=work_dir,
        out_dir=out_dir,
        out_capture_policy=out_capture_policy,
    )
    out_tree_id = compute_workspace_tree_id(out_dir)
    transcript_id = compute_workspace_tree_id(transcript_dir)
    logs_hash = canon_hash_obj(
        {
            "schema_version": "repo_harness_log_index_v1",
            "out_tree_id": out_tree_id,
            "transcript_id": transcript_id,
            "events_hash": canon_hash_obj(events_payload),
        }
    )

    wall_ms = max(0, _wall_ms_now() - wall_start_ms)
    cost_vector = {
        "cpu_ms": 0,
        "wall_ms": int(wall_ms),
        "mem_mb": 0,
        "disk_mb": workspace_disk_mb(sandbox_root),
        "fds": 0,
        "procs": 0,
        "threads": 0,
    }

    fail_index = next((idx for idx, row in enumerate(events) if int(row.get("return_code", 0)) != 0), None)
    if fail_index is not None:
        return {
            "ok": False,
            "refutation": {
                "code": "EVAL_STAGE_FAIL",
                "detail": f"recipe command failed at step {fail_index}",
                "evidence_hashes": command_fail_evidence[: min(4, len(command_fail_evidence))],
            },
            "out_tree_id": out_tree_id,
            "transcript_id": transcript_id,
            "logs_hash": logs_hash,
            "cost_vector": cost_vector,
        }
    if int(cost_vector["wall_ms"]) > int(budgets.get("wall_ms_max", 0)):
        return {
            "ok": False,
            "refutation": {"code": "BUDGET_EXCEEDED", "detail": "wall_ms budget exceeded"},
            "out_tree_id": out_tree_id,
            "transcript_id": transcript_id,
            "logs_hash": logs_hash,
            "cost_vector": cost_vector,
        }
    if int(cost_vector["disk_mb"]) > int(budgets.get("disk_mb_max", 0)):
        return {
            "ok": False,
            "refutation": {"code": "BUDGET_EXCEEDED", "detail": "disk_mb budget exceeded"},
            "out_tree_id": out_tree_id,
            "transcript_id": transcript_id,
            "logs_hash": logs_hash,
            "cost_vector": cost_vector,
        }
    return {
        "ok": True,
        "out_tree_id": out_tree_id,
        "transcript_id": transcript_id,
        "logs_hash": logs_hash,
        "cost_vector": cost_vector,
    }


__all__ = ["run_repo_harness"]
