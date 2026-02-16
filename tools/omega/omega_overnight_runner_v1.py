#!/usr/bin/env python3
"""Time-bounded omega live runner with live-wire branch/worktree safety."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

_ORIGINAL_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _ORIGINAL_REPO_ROOT
for entry in [_REPO_ROOT, _REPO_ROOT / "CDEL-v2"]:
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tools.omega.make_meta_core_sandbox_v1 import create_meta_core_sandbox
from tools.omega import omega_llm_router_v1
from tools.omega.omega_gate_loader_v1 import load_gate_statuses
from tools.omega.omega_replay_bundle_v1 import write_replay_manifest
from tools.omega.omega_verifier_client_v1 import OmegaVerifierClient


_RUNAWAY_BLOCKED_PCT_RE = re.compile(r"% RUNAWAY_BLOCKED NOOP:\s+\*\*([0-9]+(?:\.[0-9]+)?)%\*\*")
_SHADOW_WORKER_MAX = 4
_REQUIRED_PASS_GATES_FULL = ("A", "B", "C", "D", "E", "F", "P", "Q")
_REQUIRED_PASS_GATES_REFINERY = ("A", "B", "C", "F", "P", "Q")
_REQUIRED_PASS_GATES_UNIFIED = ("A", "B", "C", "D", "E", "F", "P", "Q")
_REQUIRED_PASS_GATES_UNIFIED_NO_POLYMATH = ("A", "B", "C", "D", "E", "F")
_GOAL_QUEUE_MAX_LEN_U64 = 300
_GE_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
_GE_CAPABILITY_ID = "RSI_GE_SH1_OPTIMIZER"
_MODEL_GENESIS_CAMPAIGN_ID = "rsi_model_genesis_v10_0"
_MODEL_GENESIS_CAPABILITY_ID = "RSI_MODEL_GENESIS_V10"
_VOID_TO_GOALS_MAX_GOALS_U64 = 2
_POLYMATH_VOID_REPORT_REL = "polymath/registry/polymath_void_report_v1.jsonl"
_CANONICAL_VOID_REPORT_PATH_REL = _POLYMATH_VOID_REPORT_REL
_POLYMATH_SCOUT_CAMPAIGN_ID = "rsi_polymath_scout_v1"
_POLYMATH_BOOTSTRAP_CAMPAIGN_ID = "rsi_polymath_bootstrap_domain_v1"
_POLYMATH_CONQUER_CAMPAIGN_ID = "rsi_polymath_conquer_domain_v1"
_POLYMATH_BOOTSTRAP_CAPABILITY_ID = "RSI_POLYMATH_BOOTSTRAP_DOMAIN"
_POLYMATH_CONQUER_CAPABILITY_ID = "RSI_POLYMATH_CONQUER_DOMAIN"
_POLYMATH_STALL_P_TICK_U64 = 10
_POLYMATH_STALL_Q_TICK_U64 = 30
_POLYMATH_ROUTER_BOOTSTRAP_GOAL_ID = "goal_auto_00_polymath_router_bootstrap_0001"
_POLYMATH_ROUTER_CONQUER_GOAL_ID = "goal_auto_00_polymath_router_conquer_0001"
_VAL_V17_CAMPAIGN_ID = "rsi_sas_val_v17_0"
_VAL_V17_V16_FIXTURE_REL = Path("workload/v16_1_fixture/v16_1_state_fixture.tar.gz")
_VAL_V17_V16_FIXTURE_STATE_DIR_IN_TAR_DEFAULT = "rsi_sas_metasearch_v16_1/state"
_GATE_A_ENFORCE_TICK_U64 = 20
_UNIFIED_SKILL_ROWS: tuple[tuple[str, str, str], ...] = (
    ("rsi_omega_skill_transfer_v1", "RSI_OMEGA_SKILL_TRANSFER", "goal_auto_00_unified_skill_transfer_0001"),
    ("rsi_omega_skill_ontology_v1", "RSI_OMEGA_SKILL_ONTOLOGY", "goal_auto_00_unified_skill_ontology_0001"),
    (
        "rsi_omega_skill_eff_flywheel_v1",
        "RSI_OMEGA_SKILL_EFF_FLYWHEEL",
        "goal_auto_00_unified_skill_eff_flywheel_0001",
    ),
    ("rsi_omega_skill_thermo_v1", "RSI_OMEGA_SKILL_THERMO", "goal_auto_00_unified_skill_thermo_0001"),
    (
        "rsi_omega_skill_persistence_v1",
        "RSI_OMEGA_SKILL_PERSISTENCE",
        "goal_auto_00_unified_skill_persistence_0001",
    ),
    (
        "rsi_omega_skill_alignment_v1",
        "RSI_OMEGA_SKILL_ALIGNMENT",
        "goal_auto_00_unified_skill_alignment_0001",
    ),
    (
        "rsi_omega_skill_boundless_math_v1",
        "RSI_OMEGA_SKILL_BOUNDLESS_MATH",
        "goal_auto_00_unified_skill_boundless_math_0001",
    ),
    (
        "rsi_omega_skill_boundless_science_v1",
        "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE",
        "goal_auto_00_unified_skill_boundless_science_0001",
    ),
    (
        "rsi_omega_skill_swarm_v1",
        "RSI_OMEGA_SKILL_SWARM",
        "goal_auto_00_unified_skill_swarm_0001",
    ),
    (
        "rsi_omega_skill_model_genesis_v1",
        "RSI_OMEGA_SKILL_MODEL_GENESIS",
        "goal_auto_00_unified_skill_model_genesis_0001",
    ),
)
_UNIFIED_SKILL_CAPABILITY_IDS: tuple[str, ...] = tuple(
    sorted({str(capability_id) for _campaign_id, capability_id, _goal_id in _UNIFIED_SKILL_ROWS})
)


def _state_dir(run_dir: Path) -> Path:
    return run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash_file_sha256_prefixed(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    count_u64 = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:  # noqa: BLE001
            return 0
        if not isinstance(payload, dict):
            return 0
        count_u64 += 1
    return int(count_u64)


def _jsonl_row_stats(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"rows_u64": 0, "strict_valid_b": True}
    rows_u64 = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:  # noqa: BLE001
            return {"rows_u64": 0, "strict_valid_b": False}
        if not isinstance(payload, dict):
            return {"rows_u64": 0, "strict_valid_b": False}
        rows_u64 += 1
    return {"rows_u64": int(rows_u64), "strict_valid_b": True}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json_object(path: Path) -> tuple[bool, dict[str, Any] | None, str]:
    if not path.exists() or not path.is_file():
        return False, None, "MISSING"
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        return False, None, f"INVALID_JSON:{exc}"
    if not isinstance(payload, dict):
        return False, None, "NOT_JSON_OBJECT"
    return True, payload, "OK"


def _preflight_contract(
    *,
    run_dir: Path,
    campaign_pack: Path,
    repo_root: Path,
    overlay_error: str = "",
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    campaign_pack_abs = campaign_pack.expanduser().resolve()
    campaign_ok, _campaign_payload, campaign_detail = _load_json_object(campaign_pack_abs)
    checks.append(
        {
            "check_id": "campaign_pack_json_object",
            "ok_b": bool(campaign_ok),
            "detail": f"{campaign_pack_abs.as_posix()}:{campaign_detail}",
        }
    )

    registry_path = campaign_pack_abs.parent / "omega_capability_registry_v2.json"
    registry_ok, registry_payload, registry_detail = _load_json_object(registry_path)
    checks.append(
        {
            "check_id": "capability_registry_json_object",
            "ok_b": bool(registry_ok),
            "detail": f"{registry_path.as_posix()}:{registry_detail}",
        }
    )

    polymath_enabled_rows: list[dict[str, Any]] = []
    if registry_ok and isinstance(registry_payload, dict):
        capabilities = registry_payload.get("capabilities")
        rows = capabilities if isinstance(capabilities, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("enabled", False)):
                continue
            campaign_id = str(row.get("campaign_id", "")).strip()
            if campaign_id in {_POLYMATH_SCOUT_CAMPAIGN_ID, _POLYMATH_BOOTSTRAP_CAMPAIGN_ID}:
                polymath_enabled_rows.append(row)

    polymath_void_ok = True
    polymath_details: list[str] = []
    for row in sorted(polymath_enabled_rows, key=lambda item: str(item.get("campaign_id", ""))):
        campaign_id = str(row.get("campaign_id", "")).strip() or "UNKNOWN_CAMPAIGN"
        pack_rel = str(row.get("campaign_pack_rel", "")).strip()
        if not pack_rel:
            polymath_details.append(f"{campaign_id}:UNVERIFIED_NO_CAMPAIGN_PACK_REL")
            continue
        pack_path = Path(pack_rel)
        if not pack_path.is_absolute():
            pack_path = (repo_root / pack_path).resolve()
        pack_ok, pack_payload, pack_detail = _load_json_object(pack_path)
        if not pack_ok or not isinstance(pack_payload, dict):
            polymath_details.append(f"{campaign_id}:UNVERIFIED_PACK_{pack_detail}")
            continue
        void_rel = str(pack_payload.get("void_report_path_rel", "")).strip()
        if not void_rel:
            polymath_void_ok = False
            polymath_details.append(f"{campaign_id}:MISSING_void_report_path_rel")
            continue
        if void_rel != _CANONICAL_VOID_REPORT_PATH_REL:
            polymath_void_ok = False
            polymath_details.append(f"{campaign_id}:NON_CANONICAL:{void_rel}")

    if not polymath_enabled_rows:
        polymath_details.append("polymath_disabled")
    checks.append(
        {
            "check_id": "polymath_void_report_path_canonical",
            "ok_b": bool(polymath_void_ok),
            "detail": ";".join(polymath_details),
        }
    )

    goal_queue_effective_path = run_dir / "_overnight_pack" / "goals" / "omega_goal_queue_effective_v1.json"
    if not goal_queue_effective_path.exists() or not goal_queue_effective_path.is_file():
        checks.append(
            {
                "check_id": "goal_queue_effective_json_object",
                "ok_b": True,
                "detail": f"{goal_queue_effective_path.as_posix()}:OPTIONAL_MISSING",
            }
        )
    else:
        goal_ok, _goal_payload, goal_detail = _load_json_object(goal_queue_effective_path)
        checks.append(
            {
                "check_id": "goal_queue_effective_json_object",
                "ok_b": bool(goal_ok),
                "detail": f"{goal_queue_effective_path.as_posix()}:{goal_detail}",
            }
        )

    if str(overlay_error).strip():
        checks.append(
            {
                "check_id": "overlay_prep",
                "ok_b": False,
                "detail": str(overlay_error),
            }
        )

    fail_reason = ""
    for row in checks:
        if not bool(row.get("ok_b", False)):
            fail_reason = str(row.get("check_id", "PREFLIGHT_FAIL"))
            break
    return {
        "schema_version": "OMEGA_PREFLIGHT_REPORT_v1",
        "ok_b": fail_reason == "",
        "fail_reason": fail_reason,
        "checks": checks,
    }


def _latest_payload(perf_dir: Path, suffix: str) -> dict[str, Any] | None:
    rows = sorted(perf_dir.glob(f"sha256_*.{suffix}"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = _load_json(row)
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best = payload
    return best


def _bundle_hashes(meta_core_root: Path) -> set[str]:
    store = meta_core_root / "store" / "bundles"
    if not store.exists() or not store.is_dir():
        return set()
    out: set[str] = set()
    for row in sorted(store.iterdir()):
        if not row.is_dir():
            continue
        name = row.name
        if len(name) == 64 and all(ch in "0123456789abcdef" for ch in name):
            out.add(name)
    return out


def _activated_capability_ids(state_dir: Path) -> set[str]:
    out: set[str] = set()
    for activation_path in sorted(state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json")):
        payload = _load_json(activation_path)
        if not bool(payload.get("activation_success", False)):
            continue
        binding_path = activation_path.parent.parent / "promotion" / "omega_activation_binding_v1.json"
        if not binding_path.exists() or not binding_path.is_file():
            continue
        binding = _load_json(binding_path)
        capability_id = str(binding.get("capability_id", "")).strip()
        if capability_id:
            out.add(capability_id)
    return out


def _rolling_snapshot(run_dir: Path, *, series_prefix: str, tick_u64: int, deadline_utc: str) -> None:
    perf_dir = _state_dir(run_dir) / "perf"
    scorecard = _latest_payload(perf_dir, "omega_run_scorecard_v1.json")
    payload = {
        "schema_version": "OMEGA_OVERNIGHT_ROLLING_SUMMARY_v1",
        "series_prefix": series_prefix,
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "tick_u64": int(tick_u64),
        "deadline_utc": deadline_utc,
        "scorecard_snapshot": scorecard or {},
    }
    _write_json(run_dir / "OMEGA_OVERNIGHT_ROLLING_SUMMARY_v1.json", payload)


def _run_benchmark_summary(run_dir: Path, runs_root: Path) -> None:
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "omega" / "omega_benchmark_suite_v1.py"),
        "--existing_run_dir",
        str(run_dir),
        "--runs_root",
        str(runs_root),
        "--no_simulate_activation",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    subprocess.run(cmd, cwd=_REPO_ROOT, env=env, check=True, capture_output=True, text=True)


def _run_ge_audit_report(*, runs_root: Path, run_dir: Path, ge_config_path: Path) -> tuple[Path, Path]:
    out_json = run_dir / "GE_AUDIT_REPORT_v1.json"
    out_md = run_dir / "GE_AUDIT_REPORT.md"
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "genesis_engine" / "ge_audit_report_sh1_v0_1.py"),
        "--runs_root",
        str(runs_root),
        "--ge_config_path",
        str(ge_config_path),
        "--out_json",
        str(out_json),
        "--out_md",
        str(out_md),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    subprocess.run(cmd, cwd=_REPO_ROOT, env=env, check=True, capture_output=True, text=True)
    return out_json, out_md


def _top_stage_contributors(timings_agg: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    stage_overall = timings_agg.get("stage_overall")
    if not isinstance(stage_overall, dict):
        return []
    rows: list[dict[str, Any]] = []
    for stage, stats in stage_overall.items():
        if not isinstance(stage, str) or not isinstance(stats, dict):
            continue
        mean_ns = float(stats.get("mean_ns", 0.0))
        rows.append({"stage": stage, "mean_ns": mean_ns})
    rows.sort(key=lambda row: (-float(row["mean_ns"]), str(row["stage"])))
    return rows[:limit]


def _extract_runaway_blocked_pct(summary_path: Path) -> float:
    if not summary_path.exists() or not summary_path.is_file():
        return 0.0
    text = summary_path.read_text(encoding="utf-8")
    match = _RUNAWAY_BLOCKED_PCT_RE.search(text)
    if not match:
        return 0.0
    try:
        return max(0.0, float(match.group(1)))
    except Exception:  # noqa: BLE001
        return 0.0


def _required_pass_gates(profile: str, *, polymath_enabled: bool = True) -> tuple[str, ...]:
    normalized = str(profile).strip().lower()
    if normalized == "refinery":
        return _REQUIRED_PASS_GATES_REFINERY
    if normalized == "unified":
        if polymath_enabled:
            return _REQUIRED_PASS_GATES_UNIFIED
        return _REQUIRED_PASS_GATES_UNIFIED_NO_POLYMATH
    return _REQUIRED_PASS_GATES_FULL


def _llm_backend_is_replay_like(backend: str) -> bool:
    value = str(backend).strip().lower()
    return value == "replay" or value.endswith("_replay")


def _all_required_gates_pass(gate_status: dict[str, str], *, required_gates: tuple[str, ...]) -> bool:
    if not gate_status:
        return False
    for gate in required_gates:
        if str(gate_status.get(gate, "SKIP")) != "PASS":
            return False
    return True


def _q32_to_float(value_q32: int) -> float:
    return float(int(value_q32)) / float(1 << 32)


def _git_head_sha(repo_root: Path) -> str:
    run = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if int(run.returncode) != 0:
        return ""
    return str(run.stdout).strip()


def _git_hard_reset(repo_root: Path, target_sha: str) -> bool:
    target = str(target_sha).strip()
    if not target:
        return False
    run = subprocess.run(
        ["git", "reset", "--hard", target],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return int(run.returncode) == 0


def _path_allowed_in_dirty_status(path: str) -> bool:
    value = path.strip().strip('"').replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    return (
        value == "runs"
        or value.startswith("runs/")
        or value == ".omega_cache"
        or value.startswith(".omega_cache/")
        or value == ".omega_v18_exec_workspace"
        or value.startswith(".omega_v18_exec_workspace/")
    )


def _assert_livewire_repo_clean(repo_root: Path) -> None:
    run = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    bad_paths: list[str] = []
    for raw in run.stdout.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        payload = line[3:].strip()
        if not payload:
            continue
        paths = [payload]
        if " -> " in payload:
            left, right = payload.split(" -> ", 1)
            paths = [left.strip(), right.strip()]
        for path in paths:
            if not _path_allowed_in_dirty_status(path):
                bad_paths.append(path)
    if bad_paths:
        preview = ", ".join(sorted(set(bad_paths))[:8])
        raise RuntimeError(f"repo must be clean before live-wire run (except runs/ and .omega_cache/): {preview}")


def _git_branch_exists(repo_root: Path, branch: str) -> bool:
    run = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return int(run.returncode) == 0


def _prepare_livewire_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:
    worktree_dir = worktree_dir.resolve()
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_dir)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    shutil.rmtree(worktree_dir, ignore_errors=True)
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    if not _git_branch_exists(repo_root, branch):
        subprocess.run(
            ["git", "branch", branch, "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )

    subprocess.run(
        ["git", "worktree", "add", "-B", branch, str(worktree_dir), "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    _materialize_worktree_submodules(source_repo_root=repo_root, worktree_dir=worktree_dir)
    return worktree_dir


def _submodule_paths(repo_root: Path) -> list[str]:
    gitmodules_path = repo_root / ".gitmodules"
    if not gitmodules_path.exists() or not gitmodules_path.is_file():
        return []
    run = subprocess.run(
        ["git", "config", "-f", str(gitmodules_path), "--get-regexp", r"^submodule\..*\.path$"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if int(run.returncode) != 0:
        return []
    out: list[str] = []
    for raw in run.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        rel = parts[1].strip()
        if not rel:
            continue
        rel_path = Path(rel)
        if rel_path.is_absolute() or any(part == ".." for part in rel_path.parts):
            continue
        out.append(rel_path.as_posix())
    return sorted(set(out))


def _materialize_worktree_submodules(*, source_repo_root: Path, worktree_dir: Path) -> None:
    paths = _submodule_paths(source_repo_root)
    if not paths:
        return
    # Best-effort init when submodule commit is fetchable.
    subprocess.run(
        ["git", "submodule", "update", "--init", "--recursive"],
        cwd=worktree_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    # Always overlay submodule trees from source so local-only commits still run.
    for rel in paths:
        src = (source_repo_root / rel).resolve()
        if not src.exists() or not src.is_dir():
            continue
        dst = (worktree_dir / rel).resolve()
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))


def _write_deterministic_tar_gz_from_tree(*, source_dir: Path, arc_root: str, dst_tar_gz: Path) -> bool:
    source_dir_resolved = source_dir.resolve()
    if not source_dir_resolved.exists() or not source_dir_resolved.is_dir():
        return False
    arc_root_value = str(arc_root).strip()
    if not arc_root_value:
        return False
    arc_root_path = Path(arc_root_value)
    if arc_root_path.is_absolute() or any(part == ".." for part in arc_root_path.parts):
        return False

    dst_tar_gz.parent.mkdir(parents=True, exist_ok=True)
    tmp_tar_gz = dst_tar_gz.with_name(f".{dst_tar_gz.name}.tmp")

    members = [source_dir_resolved]
    members.extend(sorted(source_dir_resolved.rglob("*"), key=lambda row: row.as_posix()))

    with tmp_tar_gz.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tf:
                for path in members:
                    rel = path.relative_to(source_dir_resolved)
                    arcname = (
                        arc_root_path
                        if rel.as_posix() == "."
                        else arc_root_path / rel
                    ).as_posix()
                    info = tf.gettarinfo(str(path), arcname=arcname)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    if path.is_file():
                        with path.open("rb") as handle:
                            tf.addfile(info, fileobj=handle)
                    else:
                        tf.addfile(info)
    tmp_tar_gz.replace(dst_tar_gz)
    return True


def _materialize_missing_fixture_tarball(
    *,
    repo_root: Path,
    campaign_id: str,
    fixture_rel: Path,
    state_dir_in_tar: str,
) -> bool:
    if campaign_id != _VAL_V17_CAMPAIGN_ID:
        return False
    if fixture_rel.as_posix() != _VAL_V17_V16_FIXTURE_REL.as_posix():
        return False

    campaign_pack = (
        repo_root / "campaigns" / "rsi_sas_metasearch_v16_1" / "rsi_sas_metasearch_pack_v16_1.json"
    ).resolve()
    if not campaign_pack.exists() or not campaign_pack.is_file():
        return False

    tar_dst = (repo_root / "campaigns" / campaign_id / fixture_rel).resolve()
    if tar_dst.exists() and tar_dst.is_file():
        return True

    arc_root = str(state_dir_in_tar).strip() or _VAL_V17_V16_FIXTURE_STATE_DIR_IN_TAR_DEFAULT
    arc_root_path = Path(arc_root)
    if arc_root_path.is_absolute() or any(part == ".." for part in arc_root_path.parts):
        return False

    env = dict(os.environ)
    py_entries = [str(repo_root.resolve()), str((repo_root / "CDEL-v2").resolve())]
    existing_pythonpath = str(env.get("PYTHONPATH", "")).strip()
    if existing_pythonpath:
        py_entries.append(existing_pythonpath)
    env["PYTHONPATH"] = ":".join(py_entries)

    with tempfile.TemporaryDirectory(prefix="omega_v16_fixture_") as tmp:
        tmp_root = Path(tmp)
        fixture_run_root = (tmp_root / "metasearch_fixture_run").resolve()
        run = subprocess.run(
            [
                "python3",
                "-m",
                "orchestrator.rsi_sas_metasearch_v16_1",
                "--campaign_pack",
                str(campaign_pack),
                "--out_dir",
                str(fixture_run_root),
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if int(run.returncode) != 0:
            return False
        campaign_run_root = fixture_run_root / "daemon" / "rsi_sas_metasearch_v16_1"
        state_dir = campaign_run_root / "state"
        config_dir = campaign_run_root / "config"
        if not state_dir.exists() or not state_dir.is_dir():
            return False
        if not config_dir.exists() or not config_dir.is_dir():
            return False

        arc_campaign_root = arc_root_path.parent
        if arc_campaign_root.as_posix() in {"", "."}:
            return _write_deterministic_tar_gz_from_tree(
                source_dir=state_dir,
                arc_root=arc_root_path.as_posix(),
                dst_tar_gz=tar_dst,
            )
        return _write_deterministic_tar_gz_from_tree(
            source_dir=campaign_run_root,
            arc_root=arc_campaign_root.as_posix(),
            dst_tar_gz=tar_dst,
        )


def _sync_campaign_fixtures_into_worktree(*, source_repo_root: Path, repo_root: Path) -> None:
    """Ensure gitignored fixture artifacts exist inside the live-wire worktree.

    Some campaigns (notably SAS-VAL) reference tarball fixtures that are ignored by git
    and therefore won't exist in a fresh `git worktree add` checkout. We copy any
    fixture tarballs referenced by `campaigns/**/fixture_locator_v1.json` from the
    original repo into the worktree before the first tick.
    """

    source_campaigns = (source_repo_root / "campaigns").resolve()
    if not source_campaigns.exists():
        return

    for locator in sorted(source_campaigns.glob("**/fixture_locator_v1.json"), key=lambda row: row.as_posix()):
        try:
            rel = locator.relative_to(source_campaigns)
        except ValueError:
            continue
        if not rel.parts:
            continue
        campaign_id = rel.parts[0]
        try:
            payload = _load_json(locator)
        except Exception:  # noqa: BLE001
            continue
        fixture_tar_rel = payload.get("fixture_tar_rel")
        if not isinstance(fixture_tar_rel, str):
            continue
        fixture_tar_rel = fixture_tar_rel.strip()
        if not fixture_tar_rel:
            continue
        fixture_rel = Path(fixture_tar_rel)
        if fixture_rel.is_absolute() or any(part == ".." for part in fixture_rel.parts):
            continue

        dst = (repo_root / "campaigns" / campaign_id / fixture_rel).resolve()
        if dst.exists():
            continue

        src = (source_campaigns / campaign_id / fixture_rel).resolve()
        if src.exists() and src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            continue

        state_dir_in_tar = str(payload.get("state_dir_in_tar", "")).strip()
        _materialize_missing_fixture_tarball(
            repo_root=repo_root,
            campaign_id=campaign_id,
            fixture_rel=fixture_rel,
            state_dir_in_tar=state_dir_in_tar,
        )

    # Live-wire worktrees need the active bundle bytes to perform activation.
    active_hash_path = (source_repo_root / "meta-core" / "active" / "ACTIVE_BUNDLE").resolve()
    if active_hash_path.exists() and active_hash_path.is_file():
        active_hash = active_hash_path.read_text(encoding="utf-8").strip()
        if len(active_hash) == 64 and all(ch in "0123456789abcdef" for ch in active_hash):
            for rel in [Path("meta-core/active/ACTIVE_BUNDLE"), Path("meta-core/active/PREV_ACTIVE_BUNDLE")]:
                src = (source_repo_root / rel).resolve()
                if not src.exists() or not src.is_file():
                    continue
                dst = (repo_root / rel).resolve()
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            src_bundle_dir = (source_repo_root / "meta-core" / "store" / "bundles" / active_hash).resolve()
            dst_bundle_dir = (repo_root / "meta-core" / "store" / "bundles" / active_hash).resolve()
            if src_bundle_dir.exists() and src_bundle_dir.is_dir() and not dst_bundle_dir.exists():
                dst_bundle_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_bundle_dir, dst_bundle_dir, dirs_exist_ok=True)


def _ensure_router_shims(*, repo_root: Path) -> None:
    shim_dir = (repo_root / "Extension-1" / "agi-orchestrator" / "orchestrator").resolve()
    shim_dir.mkdir(parents=True, exist_ok=True)

    kernel_dispatch_path = shim_dir / "kernel_dispatch_v1.py"
    run_campaign_path = shim_dir / "run_campaign_v1.py"

    kernel_dispatch_src = """\"\"\"Deterministic kernel dispatch shim.\"\"\"\n\nfrom __future__ import annotations\n\nfrom pathlib import Path\nfrom typing import Any\n\n\ndef build_dispatch_payload(*, campaign_id: str, capability_id: str, tick_u64: int, out_dir: str) -> dict[str, Any]:\n    out_path = Path(out_dir)\n    return {\n        \"schema_version\": \"kernel_dispatch_v1\",\n        \"dispatch_id\": f\"{campaign_id}:{capability_id}:{int(tick_u64)}\",\n        \"campaign_id\": str(campaign_id),\n        \"capability_id\": str(capability_id),\n        \"tick_u64\": int(tick_u64),\n        \"out_dir\": out_path.as_posix(),\n    }\n\n\n__all__ = [\"build_dispatch_payload\"]\n"""

    run_campaign_src = """\"\"\"Deterministic campaign runner shim.\n\nThis module intentionally routes through `kernel_dispatch_v1`.\n\"\"\"\n\nfrom __future__ import annotations\n\nimport argparse\nimport json\nfrom pathlib import Path\nfrom typing import Any\n\nimport kernel_dispatch_v1\n\n\ndef run_campaign(*, campaign_id: str, capability_id: str, tick_u64: int, out_json: str) -> dict[str, Any]:\n    out_path = Path(out_json)\n    payload = kernel_dispatch_v1.build_dispatch_payload(\n        campaign_id=campaign_id,\n        capability_id=capability_id,\n        tick_u64=int(tick_u64),\n        out_dir=out_path.parent.as_posix(),\n    )\n    out_path.parent.mkdir(parents=True, exist_ok=True)\n    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(\",\", \":\")) + \"\\n\", encoding=\"utf-8\")\n    return payload\n\n\ndef _parse_args() -> argparse.Namespace:\n    parser = argparse.ArgumentParser(description=\"Kernel campaign shim\")\n    parser.add_argument(\"--campaign_id\", required=True)\n    parser.add_argument(\"--capability_id\", required=True)\n    parser.add_argument(\"--tick_u64\", type=int, required=True)\n    parser.add_argument(\"--out_json\", required=True)\n    return parser.parse_args()\n\n\ndef main() -> int:\n    ns = _parse_args()\n    payload = run_campaign(\n        campaign_id=str(ns.campaign_id),\n        capability_id=str(ns.capability_id),\n        tick_u64=int(ns.tick_u64),\n        out_json=str(ns.out_json),\n    )\n    print(payload[\"dispatch_id\"])\n    return 0\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"""

    kernel_dispatch_path.write_text(kernel_dispatch_src, encoding="utf-8")
    run_campaign_path.write_text(run_campaign_src, encoding="utf-8")


def _ensure_repo_import_path(repo_root: Path) -> None:
    for entry in [repo_root / "CDEL-v2", repo_root]:
        value = str(entry)
        while value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)


def _purge_repo_runtime_modules() -> None:
    for name in list(sys.modules.keys()):
        if name == "orchestrator" or name.startswith("orchestrator."):
            sys.modules.pop(name, None)
        elif name == "cdel" or name.startswith("cdel."):
            sys.modules.pop(name, None)


def _load_run_tick(repo_root: Path) -> Callable[..., dict[str, Any]]:
    _ensure_repo_import_path(repo_root)
    _purge_repo_runtime_modules()
    module = importlib.import_module("orchestrator.omega_v18_0.coordinator_v1")
    run_tick = getattr(module, "run_tick", None)
    if not callable(run_tick):
        raise RuntimeError("missing run_tick in worktree coordinator")
    return run_tick


def _resolve_campaign_pack_for_repo(*, campaign_pack: Path, source_repo_root: Path, repo_root: Path) -> Path:
    campaign_pack_abs = campaign_pack.resolve()
    try:
        rel = campaign_pack_abs.relative_to(source_repo_root.resolve())
    except ValueError:
        return campaign_pack_abs
    mapped = (repo_root / rel).resolve()
    if mapped.exists() and mapped.is_file():
        return mapped
    return campaign_pack_abs


def _resolve_goal_queue_overlay_path(*, overlay_pack_path: Path, overlay_root: Path) -> Path:
    goal_rel_default = "goals/omega_goal_queue_v1.json"
    try:
        pack_payload = _load_json(overlay_pack_path)
    except Exception:  # noqa: BLE001
        pack_payload = {}
    goal_rel = str(pack_payload.get("goal_queue_rel", goal_rel_default)).strip() if isinstance(pack_payload, dict) else goal_rel_default
    if not goal_rel:
        goal_rel = goal_rel_default
    rel = Path(goal_rel)
    if rel.is_absolute() or ".." in rel.parts:
        goal_rel = goal_rel_default
    return (overlay_root / goal_rel).resolve()


def _inject_pending_goals(*, goal_queue_path: Path, pending_goals: list[tuple[str, str]]) -> None:
    if goal_queue_path.exists() and goal_queue_path.is_file():
        payload = _load_json(goal_queue_path)
    else:
        payload = {"schema_version": "omega_goal_queue_v1", "goals": []}
    if not isinstance(payload, dict):
        payload = {"schema_version": "omega_goal_queue_v1", "goals": []}
    if payload.get("schema_version") != "omega_goal_queue_v1":
        payload["schema_version"] = "omega_goal_queue_v1"
    goals = payload.get("goals")
    if not isinstance(goals, list):
        goals = []
        payload["goals"] = goals
    existing_pending_caps = {
        str(row.get("capability_id", "")).strip()
        for row in goals
        if isinstance(row, dict) and str(row.get("status", "")).strip() == "PENDING"
    }
    unique_requested_caps: set[str] = set()
    to_add: list[dict[str, str]] = []
    for goal_id, capability_id in pending_goals:
        goal_id_value = str(goal_id).strip()
        capability_id_value = str(capability_id).strip()
        if not goal_id_value or not capability_id_value:
            continue
        if capability_id_value in existing_pending_caps:
            continue
        if capability_id_value in unique_requested_caps:
            continue
        unique_requested_caps.add(capability_id_value)
        to_add.append(
            {
                "goal_id": goal_id_value,
                "capability_id": capability_id_value,
                "status": "PENDING",
            }
        )
    if not to_add:
        _write_json(goal_queue_path, payload)
        return
    # Keep injected goals inside the synthesizer cap (goal_synthesizer_v1 _MAX_GOALS_U64=300).
    over_limit = (len(goals) + len(to_add)) - _GOAL_QUEUE_MAX_LEN_U64
    if over_limit > 0:
        del goals[-over_limit:]
    goals.extend(to_add)
    _write_json(goal_queue_path, payload)


def _inject_pending_goal(*, goal_queue_path: Path, goal_id: str, capability_id: str) -> None:
    _inject_pending_goals(
        goal_queue_path=goal_queue_path,
        pending_goals=[(goal_id, capability_id)],
    )


def _count_ge_sh1_artifacts(run_dir: Path) -> dict[str, int]:
    state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    dispatch_root = state_dir / "dispatch"
    if not dispatch_root.exists() or not dispatch_root.is_dir():
        return {"ge_dispatch_u64": 0, "ccap_receipts_u64": 0}

    ge_dispatch_dirs: list[Path] = []
    for dispatch_dir in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
        if not dispatch_dir.is_dir():
            continue
        matched_ge = False
        for dispatch_path in sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix()):
            try:
                dispatch_payload = _load_json(dispatch_path)
            except Exception:  # noqa: BLE001
                continue
            if str(dispatch_payload.get("campaign_id", "")).strip() == _GE_CAMPAIGN_ID:
                matched_ge = True
                break
        if matched_ge:
            ge_dispatch_dirs.append(dispatch_dir)

    ccap_ids: set[str] = set()
    fallback_count = 0
    for dispatch_dir in ge_dispatch_dirs:
        verifier_dir = dispatch_dir / "verifier"
        if not verifier_dir.exists() or not verifier_dir.is_dir():
            continue
        for path in sorted(verifier_dir.glob("*ccap_receipt_v1.json"), key=lambda row: row.as_posix()):
            try:
                receipt_payload = _load_json(path)
            except Exception:  # noqa: BLE001
                fallback_count += 1
                continue
            ccap_id = str(receipt_payload.get("ccap_id", "")).strip()
            if ccap_id.startswith("sha256:"):
                ccap_ids.add(ccap_id)
            else:
                fallback_count += 1
    ccap_receipts_u64 = len(ccap_ids) if ccap_ids else fallback_count
    return {
        "ge_dispatch_u64": int(len(ge_dispatch_dirs)),
        "ccap_receipts_u64": int(ccap_receipts_u64),
    }


def _run_relpath(*, run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return path.resolve().as_posix()


def _safe_load_json_payload(
    *,
    path: Path,
    run_dir: Path,
    evidence_errors: list[str],
    context: str,
) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        evidence_errors.append(
            f"MISSING:{context}:{_run_relpath(run_dir=run_dir, path=path)}"
        )
        return None
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        evidence_errors.append(
            f"INVALID_JSON:{context}:{_run_relpath(run_dir=run_dir, path=path)}:{type(exc).__name__}"
        )
        return None
    if not isinstance(payload, dict):
        evidence_errors.append(
            f"NOT_OBJECT:{context}:{_run_relpath(run_dir=run_dir, path=path)}"
        )
        return None
    return payload


def _resolve_capability_id_for_dispatch_dir(
    *,
    dispatch_dir: Path,
    run_dir: Path,
    evidence_errors: list[str],
    context: str,
) -> str:
    binding_path = dispatch_dir / "promotion" / "omega_activation_binding_v1.json"
    if binding_path.exists() and binding_path.is_file():
        binding_payload = _safe_load_json_payload(
            path=binding_path,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context=f"{context}:binding",
        )
        if isinstance(binding_payload, dict):
            capability_id = str(binding_payload.get("capability_id", "")).strip()
            if capability_id:
                return capability_id

    for dispatch_path in sorted(
        dispatch_dir.glob("sha256_*.omega_dispatch_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        dispatch_payload = _safe_load_json_payload(
            path=dispatch_path,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context=f"{context}:dispatch_receipt",
        )
        if not isinstance(dispatch_payload, dict):
            continue
        capability_id = str(dispatch_payload.get("capability_id", "")).strip()
        if capability_id:
            return capability_id

    evidence_errors.append(
        f"MISSING_CAPABILITY_ID:{context}:{_run_relpath(run_dir=run_dir, path=dispatch_dir)}"
    )
    return ""


def _build_capability_usage_payload(*, run_dir: Path) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    evidence_errors: list[str] = []
    dispatch_root = state_dir / "dispatch"

    dispatch_counts_by_capability_raw: dict[str, dict[str, Any]] = {}
    dispatch_counts_by_campaign_raw: dict[str, int] = {}
    promotion_counts_raw: dict[str, dict[str, int]] = {}
    activation_counts_raw: dict[str, dict[str, int]] = {}
    skill_subruns_by_capability: dict[str, set[str]] = {
        capability_id: set() for capability_id in _UNIFIED_SKILL_CAPABILITY_IDS
    }
    skill_report_paths_by_capability: dict[str, set[str]] = {
        capability_id: set() for capability_id in _UNIFIED_SKILL_CAPABILITY_IDS
    }

    if not state_dir.exists() or not state_dir.is_dir():
        evidence_errors.append(
            f"MISSING_STATE_DIR:{_run_relpath(run_dir=run_dir, path=state_dir)}"
        )
    elif dispatch_root.exists() and dispatch_root.is_dir():
        for dispatch_entry in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
            if not dispatch_entry.is_dir():
                evidence_errors.append(
                    f"MALFORMED_DISPATCH_ENTRY:{_run_relpath(run_dir=run_dir, path=dispatch_entry)}"
                )
    elif dispatch_root.exists() and not dispatch_root.is_dir():
        evidence_errors.append(
            f"MALFORMED_DISPATCH_ROOT:{_run_relpath(run_dir=run_dir, path=dispatch_root)}"
        )

    for dispatch_path in sorted(
        state_dir.glob("dispatch/*/sha256_*.omega_dispatch_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        payload = _safe_load_json_payload(
            path=dispatch_path,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context="dispatch_receipt",
        )
        if not isinstance(payload, dict):
            continue
        capability_id = str(payload.get("capability_id", "")).strip()
        campaign_id = str(payload.get("campaign_id", "")).strip()
        if not capability_id:
            evidence_errors.append(
                f"MISSING_CAPABILITY_ID:dispatch_receipt:{_run_relpath(run_dir=run_dir, path=dispatch_path)}"
            )
            continue
        row = dispatch_counts_by_capability_raw.setdefault(
            capability_id,
            {"dispatch_u64": 0, "campaign_ids": set()},
        )
        row["dispatch_u64"] = int(row.get("dispatch_u64", 0)) + 1
        if campaign_id:
            campaign_ids = row.get("campaign_ids")
            if isinstance(campaign_ids, set):
                campaign_ids.add(campaign_id)
            dispatch_counts_by_campaign_raw[campaign_id] = int(
                dispatch_counts_by_campaign_raw.get(campaign_id, 0)
            ) + 1
        if capability_id in skill_subruns_by_capability:
            subrun_obj = payload.get("subrun")
            if not isinstance(subrun_obj, dict):
                evidence_errors.append(
                    f"MISSING_SUBRUN:dispatch_receipt:{_run_relpath(run_dir=run_dir, path=dispatch_path)}"
                )
                continue
            subrun_root_rel = str(subrun_obj.get("subrun_root_rel", "")).strip()
            if not subrun_root_rel:
                evidence_errors.append(
                    f"MISSING_SUBRUN_ROOT_REL:dispatch_receipt:{_run_relpath(run_dir=run_dir, path=dispatch_path)}"
                )
                continue
            skill_subruns_by_capability[capability_id].add(subrun_root_rel)

    for promotion_path in sorted(
        state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        payload = _safe_load_json_payload(
            path=promotion_path,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context="promotion_receipt",
        )
        if not isinstance(payload, dict):
            continue
        result = payload.get("result")
        status = str(result.get("status", "")).strip() if isinstance(result, dict) else ""
        if status not in {"PROMOTED", "REJECTED", "SKIPPED"}:
            evidence_errors.append(
                f"INVALID_PROMOTION_STATUS:{_run_relpath(run_dir=run_dir, path=promotion_path)}:{status}"
            )
            continue
        dispatch_dir = promotion_path.parent.parent
        capability_id = _resolve_capability_id_for_dispatch_dir(
            dispatch_dir=dispatch_dir,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context="promotion_receipt",
        )
        if not capability_id:
            continue
        counts = promotion_counts_raw.setdefault(
            capability_id,
            {"promoted_u64": 0, "rejected_u64": 0, "skipped_u64": 0},
        )
        if status == "PROMOTED":
            counts["promoted_u64"] = int(counts.get("promoted_u64", 0)) + 1
        elif status == "REJECTED":
            counts["rejected_u64"] = int(counts.get("rejected_u64", 0)) + 1
        else:
            counts["skipped_u64"] = int(counts.get("skipped_u64", 0)) + 1

    for activation_path in sorted(
        state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        payload = _safe_load_json_payload(
            path=activation_path,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context="activation_receipt",
        )
        if not isinstance(payload, dict):
            continue
        dispatch_dir = activation_path.parent.parent
        capability_id = _resolve_capability_id_for_dispatch_dir(
            dispatch_dir=dispatch_dir,
            run_dir=run_dir,
            evidence_errors=evidence_errors,
            context="activation_receipt",
        )
        if not capability_id:
            continue
        counts = activation_counts_raw.setdefault(
            capability_id,
            {
                "activation_success_u64": 0,
                "activation_denied_u64": 0,
                "activation_other_fail_u64": 0,
            },
        )
        if bool(payload.get("activation_success", False)):
            counts["activation_success_u64"] = int(counts.get("activation_success_u64", 0)) + 1
            continue
        reasons_obj = payload.get("reasons")
        reason_set: set[str] = set()
        if isinstance(reasons_obj, list):
            reason_set = {str(row).strip() for row in reasons_obj if str(row).strip()}
        elif reasons_obj is not None:
            evidence_errors.append(
                f"INVALID_ACTIVATION_REASONS:{_run_relpath(run_dir=run_dir, path=activation_path)}"
            )
        if "META_CORE_DENIED" in reason_set:
            counts["activation_denied_u64"] = int(counts.get("activation_denied_u64", 0)) + 1
        else:
            counts["activation_other_fail_u64"] = int(
                counts.get("activation_other_fail_u64", 0)
            ) + 1

    for capability_id in _UNIFIED_SKILL_CAPABILITY_IDS:
        subrun_roots = sorted(skill_subruns_by_capability.get(capability_id, set()))
        for subrun_root_rel in subrun_roots:
            rel_path = Path(subrun_root_rel)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                evidence_errors.append(
                    f"INVALID_SUBRUN_PATH:{capability_id}:{subrun_root_rel}"
                )
                continue
            subrun_root = (state_dir / rel_path).resolve()
            if not subrun_root.exists() or not subrun_root.is_dir():
                evidence_errors.append(
                    f"MISSING_SUBRUN_DIR:{capability_id}:{_run_relpath(run_dir=run_dir, path=subrun_root)}"
                )
                continue
            for pattern in (
                "**/state/reports/omega_skill_report_v1.json",
                "**/state/reports/sha256_*.omega_skill_report_v1.json",
            ):
                for report_path in sorted(subrun_root.glob(pattern), key=lambda row: row.as_posix()):
                    if report_path.exists() and report_path.is_file():
                        skill_report_paths_by_capability[capability_id].add(
                            _run_relpath(run_dir=run_dir, path=report_path)
                        )

    all_capability_ids = sorted(
        set(dispatch_counts_by_capability_raw.keys())
        | set(promotion_counts_raw.keys())
        | set(activation_counts_raw.keys())
    )

    dispatch_counts_by_capability: list[dict[str, Any]] = []
    for capability_id in sorted(dispatch_counts_by_capability_raw.keys()):
        row = dispatch_counts_by_capability_raw.get(capability_id, {})
        campaigns = row.get("campaign_ids")
        dispatch_counts_by_capability.append(
            {
                "capability_id": capability_id,
                "dispatch_u64": int(row.get("dispatch_u64", 0)),
                "campaign_ids": sorted(
                    str(campaign_id)
                    for campaign_id in (campaigns if isinstance(campaigns, set) else set())
                ),
            }
        )

    dispatch_counts_by_campaign = [
        {"campaign_id": campaign_id, "dispatch_u64": int(dispatch_counts_by_campaign_raw[campaign_id])}
        for campaign_id in sorted(dispatch_counts_by_campaign_raw.keys())
    ]

    promotion_counts_by_capability: list[dict[str, Any]] = []
    activation_counts_by_capability: list[dict[str, Any]] = []
    for capability_id in all_capability_ids:
        promotion = promotion_counts_raw.get(capability_id, {})
        promotion_counts_by_capability.append(
            {
                "capability_id": capability_id,
                "promoted_u64": int(promotion.get("promoted_u64", 0)),
                "rejected_u64": int(promotion.get("rejected_u64", 0)),
                "skipped_u64": int(promotion.get("skipped_u64", 0)),
            }
        )
        activation = activation_counts_raw.get(capability_id, {})
        activation_counts_by_capability.append(
            {
                "capability_id": capability_id,
                "activation_success_u64": int(activation.get("activation_success_u64", 0)),
                "activation_denied_u64": int(activation.get("activation_denied_u64", 0)),
                "activation_other_fail_u64": int(activation.get("activation_other_fail_u64", 0)),
            }
        )

    observed_skill_capabilities = set(
        dispatch_counts_by_capability_raw.keys()
        | promotion_counts_raw.keys()
        | activation_counts_raw.keys()
        | {
            capability_id
            for capability_id, report_paths in skill_report_paths_by_capability.items()
            if isinstance(report_paths, set) and report_paths
        }
    )
    observed_skill_reports = [
        {
            "capability_id": capability_id,
            "report_present_b": bool(skill_report_paths_by_capability.get(capability_id)),
            "report_paths": sorted(skill_report_paths_by_capability.get(capability_id, set())),
        }
        for capability_id in sorted(observed_skill_capabilities)
    ]

    polymath_progress = _collect_polymath_progress(run_dir)
    ge_snapshot = _count_ge_sh1_artifacts(run_dir)
    normalized_errors = sorted({str(error).strip() for error in evidence_errors if str(error).strip()})
    return {
        "schema_version": "OMEGA_CAPABILITY_USAGE_v1",
        "ok_b": len(normalized_errors) == 0,
        "evidence_errors": normalized_errors,
        "dispatch_counts_by_capability": dispatch_counts_by_capability,
        "dispatch_counts_by_campaign": dispatch_counts_by_campaign,
        "promotion_counts_by_capability": promotion_counts_by_capability,
        "activation_counts_by_capability": activation_counts_by_capability,
        "observed_skill_reports": observed_skill_reports,
        "polymath_progress_snapshot": {
            "top_void_score_delta_q32": int(polymath_progress.get("top_void_score_delta_q32", 0)),
            "coverage_ratio_delta_q32": int(polymath_progress.get("coverage_ratio_delta_q32", 0)),
            "domains_bootstrapped_delta_u64": int(polymath_progress.get("domains_bootstrapped_delta_u64", 0)),
        },
        "ge_sh1_snapshot": {
            "ge_dispatch_u64": int(ge_snapshot.get("ge_dispatch_u64", 0)),
            "ccap_receipts_u64": int(ge_snapshot.get("ccap_receipts_u64", 0)),
        },
    }


def _write_capability_usage_artifact(*, run_dir: Path) -> Path:
    out_path = run_dir / "OMEGA_CAPABILITY_USAGE_v1.json"
    payload = _build_capability_usage_payload(run_dir=run_dir)
    _write_json(out_path, payload)
    return out_path


def _overlay_polymath_enablement(campaign_pack: Path) -> dict[str, bool]:
    out = {
        "polymath_enabled": False,
        "scout_enabled": False,
        "bootstrap_enabled": False,
        "conquer_enabled": False,
    }
    registry_path = campaign_pack.parent / "omega_capability_registry_v2.json"
    if not registry_path.exists() or not registry_path.is_file():
        return out
    try:
        payload = _load_json(registry_path)
    except Exception:  # noqa: BLE001
        return out
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        return out
    for row in capabilities:
        if not isinstance(row, dict):
            continue
        campaign_id = str(row.get("campaign_id", "")).strip()
        enabled_b = bool(row.get("enabled", False))
        if campaign_id == _POLYMATH_SCOUT_CAMPAIGN_ID:
            out["scout_enabled"] = enabled_b
        elif campaign_id == _POLYMATH_BOOTSTRAP_CAMPAIGN_ID:
            out["bootstrap_enabled"] = enabled_b
        elif campaign_id == _POLYMATH_CONQUER_CAMPAIGN_ID:
            out["conquer_enabled"] = enabled_b
    out["polymath_enabled"] = bool(
        out["scout_enabled"] or out["bootstrap_enabled"] or out["conquer_enabled"]
    )
    return out


def _dispatch_receipt_payloads(state_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(state_dir.glob("dispatch/*/sha256_*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix()):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        out.append(dict(payload))
    return out


def _dispatch_summary_by_campaign(state_dir: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for payload in _dispatch_receipt_payloads(state_dir):
        campaign_id = str(payload.get("campaign_id", "")).strip()
        if not campaign_id:
            continue
        out[campaign_id] = int(out.get(campaign_id, 0)) + 1
    out.setdefault(_POLYMATH_SCOUT_CAMPAIGN_ID, 0)
    out.setdefault(_POLYMATH_BOOTSTRAP_CAMPAIGN_ID, 0)
    out.setdefault(_POLYMATH_CONQUER_CAMPAIGN_ID, 0)
    return {key: int(out[key]) for key in sorted(out.keys())}


def _promotion_reason_counts(state_dir: Path) -> dict[str, int]:
    out: dict[str, int] = {
        "ALREADY_ACTIVE": 0,
        "NO_PROMOTION_BUNDLE": 0,
    }
    for path in sorted(state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"), key=lambda row: row.as_posix()):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        result = payload.get("result")
        if not isinstance(result, dict):
            continue
        reason = str(result.get("reason_code", "")).strip()
        if not reason:
            continue
        out[reason] = int(out.get(reason, 0)) + 1
    return {key: int(out[key]) for key in sorted(out.keys())}


def _load_benchmark_gates_payload(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "OMEGA_BENCHMARK_GATES_v1.json"
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = _load_json(path)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _gate_status_map_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        return {}
    out: dict[str, str] = {}
    for gate, row in gates.items():
        if not isinstance(row, dict):
            continue
        gate_name = str(gate).strip()
        status = str(row.get("status", "")).strip()
        if gate_name and status:
            out[gate_name] = status
    return out


def _gate_details_map_from_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    gates = payload.get("gates")
    if not isinstance(gates, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for gate, row in gates.items():
        if not isinstance(row, dict):
            continue
        gate_name = str(gate).strip()
        if not gate_name:
            continue
        details = row.get("details")
        out[gate_name] = dict(details) if isinstance(details, dict) else {}
    return out


def _latest_observation_metrics(state_dir: Path) -> dict[str, int]:
    latest_tick = -1
    latest_metrics: dict[str, Any] = {}
    for path in sorted(
        (state_dir / "observations").glob("sha256_*.omega_observation_report_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < latest_tick:
            continue
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            continue
        latest_tick = tick_u64
        latest_metrics = dict(metrics)

    top_void_obj = latest_metrics.get("top_void_score_q32")
    top_void_q32 = int(top_void_obj.get("q", 0)) if isinstance(top_void_obj, dict) else 0
    return {
        "observation_tick_u64": int(max(0, latest_tick)),
        "top_void_score_q32": int(max(0, top_void_q32)),
        "domains_ready_for_conquer_u64": int(max(0, int(latest_metrics.get("domains_ready_for_conquer_u64", 0)))),
        "domains_bootstrapped_u64": int(max(0, int(latest_metrics.get("domains_bootstrapped_u64", 0)))),
    }


def _scout_dispatch_void_hash_stats(state_dir: Path) -> dict[str, Any]:
    scout_rows: list[tuple[int, str, Path]] = []
    scout_dispatch_u64 = 0
    last_scout_tick_u64 = 0
    for payload in _dispatch_receipt_payloads(state_dir):
        if str(payload.get("campaign_id", "")) != _POLYMATH_SCOUT_CAMPAIGN_ID:
            continue
        if int(payload.get("return_code", 1)) != 0:
            continue
        scout_dispatch_u64 += 1
        tick_u64 = max(0, int(payload.get("tick_u64", 0)))
        last_scout_tick_u64 = max(last_scout_tick_u64, tick_u64)
        subrun_obj = payload.get("subrun")
        if not isinstance(subrun_obj, dict):
            continue
        subrun_root_rel = str(subrun_obj.get("subrun_root_rel", "")).strip()
        if not subrun_root_rel:
            continue
        void_path = state_dir / subrun_root_rel / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
        scout_rows.append((tick_u64, subrun_root_rel, void_path))

    void_hash_history: list[str] = []
    for _tick_u64, subrun_root_rel, void_path in sorted(scout_rows, key=lambda row: (int(row[0]), str(row[1]))):
        if not void_path.exists() or not void_path.is_file():
            continue
        row_count = _count_jsonl_rows(void_path)
        if row_count <= 0:
            continue
        digest = _hash_file_sha256_prefixed(void_path)
        if not digest:
            continue
        void_hash_history.append(digest)

    void_hash_changed_b = False
    for idx in range(1, len(void_hash_history)):
        if void_hash_history[idx] != void_hash_history[idx - 1]:
            void_hash_changed_b = True
            break
    return {
        "scout_dispatch_u64": int(scout_dispatch_u64),
        "last_scout_tick_u64": int(last_scout_tick_u64),
        "void_hash_history_u64": int(len(void_hash_history)),
        "void_hash_first": str(void_hash_history[0]) if void_hash_history else "",
        "void_hash_last": str(void_hash_history[-1]) if void_hash_history else "",
        "void_hash_changed_b": bool(void_hash_changed_b),
    }


def _top_void_from_registry(repo_root: Path) -> dict[str, Any]:
    void_path = repo_root / _POLYMATH_VOID_REPORT_REL
    if not void_path.exists() or not void_path.is_file():
        return {"top_void_score_q32": 0, "candidate_domain_id": ""}
    top_q32 = 0
    top_candidate_domain_id = ""
    for raw in void_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:  # noqa: BLE001
            return {"top_void_score_q32": 0, "candidate_domain_id": ""}
        if not isinstance(payload, dict):
            return {"top_void_score_q32": 0, "candidate_domain_id": ""}
        void_obj = payload.get("void_score_q32")
        void_q32 = int(void_obj.get("q", 0)) if isinstance(void_obj, dict) else 0
        candidate_domain_id = str(payload.get("candidate_domain_id", "")).strip()
        if int(void_q32) > int(top_q32):
            top_q32 = int(void_q32)
            top_candidate_domain_id = candidate_domain_id
        elif int(void_q32) == int(top_q32) and candidate_domain_id and candidate_domain_id < top_candidate_domain_id:
            top_candidate_domain_id = candidate_domain_id
    return {
        "top_void_score_q32": int(max(0, top_q32)),
        "candidate_domain_id": str(top_candidate_domain_id),
    }


def _append_void_to_goals_invocation(*, run_dir: Path, payload: dict[str, Any]) -> None:
    report_path = run_dir / "OMEGA_VOID_TO_GOALS_REPORT_v1.json"
    if report_path.exists() and report_path.is_file():
        merged = _load_json(report_path)
    else:
        merged = {
            "schema_version": "OMEGA_VOID_TO_GOALS_REPORT_v1",
            "invocations": [],
            "goals_injected_total_u64": 0,
        }
    invocations = merged.get("invocations")
    if not isinstance(invocations, list):
        invocations = []
    invocations.append(dict(payload))
    merged["invocations"] = invocations
    merged["goals_injected_total_u64"] = int(
        sum(int(row.get("goals_injected_u64", 0)) for row in invocations if isinstance(row, dict))
    )
    _write_json(report_path, merged)


def _route_polymath_progress_goal(
    *,
    run_dir: Path,
    repo_root: Path,
    state_dir: Path,
    out_goal_queue_effective_path: Path,
    tick_u64: int,
) -> dict[str, Any]:
    latest_metrics = _latest_observation_metrics(state_dir)
    top_void_row = _top_void_from_registry(repo_root)
    top_void_q32 = int(max(int(top_void_row.get("top_void_score_q32", 0)), int(latest_metrics.get("top_void_score_q32", 0))))
    domains_ready_for_conquer_u64 = int(max(0, int(latest_metrics.get("domains_ready_for_conquer_u64", 0))))
    pending_goals: list[tuple[str, str]] = []
    if domains_ready_for_conquer_u64 > 0:
        pending_goals.append((_POLYMATH_ROUTER_CONQUER_GOAL_ID, _POLYMATH_CONQUER_CAPABILITY_ID))
    elif top_void_q32 > 0:
        pending_goals.append((_POLYMATH_ROUTER_BOOTSTRAP_GOAL_ID, _POLYMATH_BOOTSTRAP_CAPABILITY_ID))
    if pending_goals:
        _inject_pending_goals(goal_queue_path=out_goal_queue_effective_path, pending_goals=pending_goals)
    invocation_payload: dict[str, Any] = {
        "schema_version": "omega_void_to_goals_report_v1",
        "invocation_label": "progress_router",
        "tick_u64": int(max(0, tick_u64)),
        "top_void_score_q32": int(top_void_q32),
        "domains_ready_for_conquer_u64": int(domains_ready_for_conquer_u64),
        "max_goals_u64": 1,
        "rows_scanned_u64": int(_count_jsonl_rows(repo_root / _POLYMATH_VOID_REPORT_REL)),
        "goals_injected_u64": int(len(pending_goals)),
        "injected_goals": [
            {
                "goal_id": goal_id,
                "capability_id": capability_id,
                "status": "PENDING",
            }
            for goal_id, capability_id in pending_goals
        ],
        "out_goal_queue_effective_path": out_goal_queue_effective_path.as_posix(),
    }
    _append_void_to_goals_invocation(run_dir=run_dir, payload=invocation_payload)
    return invocation_payload


def _collect_polymath_checkpoint_snapshot(*, run_dir: Path, repo_root: Path) -> dict[str, Any]:
    state_dir = _state_dir(run_dir)
    benchmark_payload = _load_benchmark_gates_payload(run_dir)
    gate_details = _gate_details_map_from_payload(benchmark_payload)
    gate_q_details = gate_details.get("Q", {})
    dispatch_by_campaign = _dispatch_summary_by_campaign(state_dir)
    scout_stats = _scout_dispatch_void_hash_stats(state_dir)
    latest_observation_metrics = _latest_observation_metrics(state_dir)
    progress = _collect_polymath_progress(run_dir)
    void_path = repo_root / _POLYMATH_VOID_REPORT_REL
    void_stats = _jsonl_row_stats(void_path)
    return {
        "dispatch_by_campaign_id": dispatch_by_campaign,
        "promotion_by_reason": _promotion_reason_counts(state_dir),
        "scout_dispatch_u64": int(scout_stats.get("scout_dispatch_u64", 0)),
        "last_scout_tick_u64": int(scout_stats.get("last_scout_tick_u64", 0)),
        "void_hash_history_u64": int(scout_stats.get("void_hash_history_u64", 0)),
        "void_hash_first": str(scout_stats.get("void_hash_first", "")),
        "void_hash_last": str(scout_stats.get("void_hash_last", "")),
        "void_hash_changed_b": bool(scout_stats.get("void_hash_changed_b", False)),
        "void_report_path": _POLYMATH_VOID_REPORT_REL,
        "void_report_exists_b": bool(void_path.exists() and void_path.is_file()),
        "void_report_bytes_sha256": _hash_file_sha256_prefixed(void_path),
        "void_rows_u64": int(void_stats.get("rows_u64", 0)),
        "void_jsonl_strict_valid_b": bool(void_stats.get("strict_valid_b", False)),
        "top_void_score_q32": int(latest_observation_metrics.get("top_void_score_q32", 0)),
        "domains_ready_for_conquer_u64": int(latest_observation_metrics.get("domains_ready_for_conquer_u64", 0)),
        "domains_bootstrapped_delta_u64": int(
            max(
                int(gate_q_details.get("domains_bootstrapped_delta_u64", 0)),
                int(progress.get("domains_bootstrapped_delta_u64", 0)),
            )
        ),
        "conquer_improved_u64": int(gate_q_details.get("conquer_improved_u64", 0)),
        "bootstrap_dispatch_u64": int(dispatch_by_campaign.get(_POLYMATH_BOOTSTRAP_CAMPAIGN_ID, 0)),
        "conquer_dispatch_u64": int(dispatch_by_campaign.get(_POLYMATH_CONQUER_CAMPAIGN_ID, 0)),
    }


def _write_diagnostic_packet(
    *,
    run_dir: Path,
    series_prefix: str,
    meta_core_mode: str,
    repo_root: Path,
    profile: str,
    tick_u64: int,
    safe_halt: bool,
    termination_reason: str,
    verifier_failures: list[dict[str, Any]],
    required_pass_gates: tuple[str, ...],
    latest_gate_status: dict[str, str],
    llm_router_failures: list[dict[str, Any]] | None = None,
    preflight_report: dict[str, Any] | None = None,
    checkpoint_kind: str = "final",
    capability_usage_path: Path | None = None,
) -> Path:
    benchmark_payload = _load_benchmark_gates_payload(run_dir)
    gate_status_from_payload = _gate_status_map_from_payload(benchmark_payload)
    gate_details = _gate_details_map_from_payload(benchmark_payload)
    gate_status = dict(gate_status_from_payload)
    gate_status.update({str(key): str(value) for key, value in latest_gate_status.items()})
    snapshot = _collect_polymath_checkpoint_snapshot(run_dir=run_dir, repo_root=repo_root)

    gate_failures: list[dict[str, Any]] = []
    for gate in sorted({str(gate).strip() for gate in required_pass_gates if str(gate).strip()}):
        status = str(gate_status.get(gate, "FAIL")).strip() or "FAIL"
        if status == "PASS":
            continue
        if gate == "P":
            scout_dispatch_u64 = int(snapshot.get("scout_dispatch_u64", 0))
            void_exists_b = bool(snapshot.get("void_report_exists_b", False))
            void_rows_u64 = int(snapshot.get("void_rows_u64", 0))
            void_hash_changed_b = bool(snapshot.get("void_hash_changed_b", False))
            reason = "VOID_HASH_NOT_CHANGED"
            if scout_dispatch_u64 <= 0:
                reason = "SCOUT_NOT_DISPATCHED"
            elif not void_exists_b:
                reason = "VOID_REPORT_MISSING"
            elif void_rows_u64 <= 0:
                reason = "VOID_REPORT_EMPTY"
            elif not bool(snapshot.get("void_jsonl_strict_valid_b", False)):
                reason = "VOID_REPORT_INVALID_JSONL"
            next_actions = [
                {
                    "kind": "RUN_CAMPAIGN",
                    "campaign_id": _POLYMATH_SCOUT_CAMPAIGN_ID,
                    "detail": "ensure scout writes non-empty deterministic row to polymath/registry/polymath_void_report_v1.jsonl",
                }
            ]
            gate_failures.append(
                {
                    "gate": "P",
                    "reason": reason,
                    "evidence": {
                        "void_report_path": str(snapshot.get("void_report_path", _POLYMATH_VOID_REPORT_REL)),
                        "void_report_exists_b": bool(void_exists_b),
                        "void_report_bytes_sha256": str(snapshot.get("void_report_bytes_sha256", "")),
                        "void_rows_u64": int(void_rows_u64),
                        "last_scout_tick_u64": int(snapshot.get("last_scout_tick_u64", 0)),
                        "void_hash_changed_b": bool(void_hash_changed_b),
                        "void_hash_first": str(snapshot.get("void_hash_first", "")),
                        "void_hash_last": str(snapshot.get("void_hash_last", "")),
                        "scout_dispatch_u64": int(scout_dispatch_u64),
                    },
                    "next_actions": next_actions,
                }
            )
            continue
        if gate == "Q":
            domains_ready_for_conquer_u64 = int(snapshot.get("domains_ready_for_conquer_u64", 0))
            domains_bootstrapped_delta_u64 = int(snapshot.get("domains_bootstrapped_delta_u64", 0))
            conquer_improved_u64 = int(snapshot.get("conquer_improved_u64", 0))
            if domains_ready_for_conquer_u64 <= 0 and domains_bootstrapped_delta_u64 <= 0:
                reason = "NO_DOMAINS_ELIGIBLE"
            elif conquer_improved_u64 <= 0 and domains_bootstrapped_delta_u64 <= 0:
                reason = "NO_BOOTSTRAP_OR_CONQUER_PROGRESS"
            else:
                reason = "GATE_Q_UNSATISFIED"
            if domains_ready_for_conquer_u64 > 0:
                next_actions = [
                    {
                        "kind": "RUN_CAMPAIGN",
                        "campaign_id": _POLYMATH_CONQUER_CAMPAIGN_ID,
                        "detail": "execute deterministic conquer on ready domain(s)",
                    }
                ]
            else:
                next_actions = [
                    {
                        "kind": "RUN_CAMPAIGN",
                        "campaign_id": _POLYMATH_BOOTSTRAP_CAMPAIGN_ID,
                        "detail": "bootstrap top void candidate deterministically",
                    }
                ]
            gate_failures.append(
                {
                    "gate": "Q",
                    "reason": reason,
                    "evidence": {
                        "domains_ready_for_conquer_u64": int(domains_ready_for_conquer_u64),
                        "domains_bootstrapped_delta_u64": int(domains_bootstrapped_delta_u64),
                        "conquer_improved_u64": int(conquer_improved_u64),
                        "bootstrap_dispatch_u64": int(snapshot.get("bootstrap_dispatch_u64", 0)),
                        "conquer_dispatch_u64": int(snapshot.get("conquer_dispatch_u64", 0)),
                    },
                    "next_actions": next_actions,
                }
            )
            continue
        details = gate_details.get(gate, {})
        gate_failures.append(
            {
                "gate": gate,
                "reason": f"GATE_{gate}_FAIL",
                "evidence": dict(details),
                "next_actions": [
                    {
                        "kind": "INSPECT_GATE_PROOF",
                        "campaign_id": "",
                        "detail": f"inspect OMEGA_GATE_PROOF_v1.json inputs for gate {gate}",
                    }
                ],
            }
        )

    by_campaign_id = dict(snapshot.get("dispatch_by_campaign_id", {}))
    for campaign_id in (
        _POLYMATH_SCOUT_CAMPAIGN_ID,
        _POLYMATH_BOOTSTRAP_CAMPAIGN_ID,
        _POLYMATH_CONQUER_CAMPAIGN_ID,
    ):
        by_campaign_id.setdefault(campaign_id, 0)
    promotion_by_reason = dict(snapshot.get("promotion_by_reason", {}))
    promotion_by_reason.setdefault("NO_PROMOTION_BUNDLE", 0)
    promotion_by_reason.setdefault("ALREADY_ACTIVE", 0)

    gate_proof_path = run_dir / "OMEGA_GATE_PROOF_v1.json"
    router_failures = [dict(row) for row in (llm_router_failures or []) if isinstance(row, dict)]
    next_actions: list[dict[str, Any]] = []
    for row in gate_failures:
        if not isinstance(row, dict):
            continue
        actions = row.get("next_actions")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    next_actions.append(dict(action))
    for row in router_failures:
        if not isinstance(row, dict):
            continue
        actions = row.get("next_actions")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    next_actions.append(dict(action))
    capability_usage_exists = capability_usage_path is not None and capability_usage_path.exists()
    payload = {
        "schema_version": "OMEGA_DIAGNOSTIC_PACKET_v1",
        "created_at_utc": "",
        "created_from_tick_u64": int(max(0, tick_u64)),
        "series_prefix": str(series_prefix),
        "meta_core_mode": str(meta_core_mode),
        "tick_u64": int(max(0, tick_u64)),
        "checkpoint_kind": str(checkpoint_kind),
        "profile": str(profile),
        "safe_halt": bool(safe_halt),
        "termination_reason": str(termination_reason),
        "failure_reason": str(termination_reason),
        "required_pass_gates": [str(gate) for gate in required_pass_gates],
        "latest_gate_status": {str(key): str(value) for key, value in sorted(gate_status.items())},
        "gate_failures": sorted(gate_failures, key=lambda row: str(row.get("gate", ""))),
        "llm_router_failures": sorted(
            router_failures,
            key=lambda row: (int(row.get("tick_u64", 0)), str(row.get("reason", ""))),
        ),
        "next_actions": next_actions,
        "verifier_failures": list(verifier_failures),
        "preflight_ok_b": bool((preflight_report or {}).get("ok_b", False)),
        "preflight_fail_reason": str((preflight_report or {}).get("fail_reason", "")),
        "dispatch_summary": {
            "by_campaign_id": {str(key): int(by_campaign_id[key]) for key in sorted(by_campaign_id.keys())},
            "promotion_by_reason": {
                str(key): int(promotion_by_reason[key]) for key in sorted(promotion_by_reason.keys())
            },
        },
        "evidence": {
            "gate_proof_json": {
                "path": gate_proof_path.as_posix() if gate_proof_path.exists() else "",
                "sha256": _hash_file_sha256_prefixed(gate_proof_path),
            },
            "capability_usage_json": {
                "path": capability_usage_path.as_posix() if capability_usage_exists and capability_usage_path is not None else "",
                "sha256": _hash_file_sha256_prefixed(capability_usage_path)
                if capability_usage_exists and capability_usage_path is not None
                else "",
            },
        },
        "gate_proof_ref": {
            "path": gate_proof_path.as_posix() if gate_proof_path.exists() else "",
            "sha256": _hash_file_sha256_prefixed(gate_proof_path),
        },
    }
    out_path = run_dir / "OMEGA_DIAGNOSTIC_PACKET_v1.json"
    _write_json(out_path, payload)
    return out_path


def _write_skill_manifest_artifacts(*, run_dir: Path, repo_root: Path) -> tuple[Path, Path]:
    from tools.omega.omega_skill_manifest_v1 import generate_skill_manifest

    payload = generate_skill_manifest(repo_root=repo_root)
    run_artifact_path = run_dir / "OMEGA_SKILL_MANIFEST_v1.json"
    worktree_artifact_path = run_dir / "_worktree" / "OMEGA_SKILL_MANIFEST_v1.json"
    _write_json(run_artifact_path, payload)
    _write_json(worktree_artifact_path, payload)
    return run_artifact_path, worktree_artifact_path


def _prepare_campaign_pack_overlay(
    *,
    campaign_pack: Path,
    run_dir: Path,
    enable_self_optimize_core: bool,
    enable_polymath_drive: bool,
    enable_polymath_bootstrap: bool,
    enable_ge_sh1_optimizer: bool,
    ge_pack_overrides: dict[str, Any] | None,
    profile: str,
    promo_focus: bool = False,
) -> Path:
    profile_norm = str(profile).strip().lower()
    if not enable_self_optimize_core and not enable_polymath_bootstrap and not enable_polymath_drive and not enable_ge_sh1_optimizer:
        if profile_norm not in {"refinery", "unified"}:
            return campaign_pack
    src_root = campaign_pack.parent
    dst_root = run_dir / "_overnight_pack"
    shutil.rmtree(dst_root, ignore_errors=True)
    shutil.copytree(src_root, dst_root)
    overlay_pack_path = dst_root / campaign_pack.name
    registry_path = dst_root / "omega_capability_registry_v2.json"
    registry = _load_json(registry_path)
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        raise RuntimeError("invalid capability registry in campaign pack overlay")
    if enable_self_optimize_core:
        found = False
        for row in caps:
            if isinstance(row, dict) and str(row.get("campaign_id", "")) == "rsi_omega_self_optimize_core_v1":
                row["enabled"] = True
                found = True
        if not found:
            raise RuntimeError("missing rsi_omega_self_optimize_core_v1 capability in registry")

    if enable_polymath_bootstrap or enable_polymath_drive:
        found_scout = False
        found_bootstrap = False
        found_conquer = False
        for row in caps:
            if not isinstance(row, dict):
                continue
            campaign_id = str(row.get("campaign_id", ""))
            if campaign_id == "rsi_polymath_scout_v1":
                row["enabled"] = True
                if profile_norm == "unified":
                    row["enable_ccap"] = 0
                    row["verifier_module"] = "cdel.v18_0.verify_rsi_polymath_scout_v1"
                    row["promotion_bundle_rel"] = (
                        "daemon/rsi_polymath_scout_v1/state/promotion/*.polymath_scout_promotion_bundle_v1.json"
                    )
                    if promo_focus:
                        row["cooldown_ticks_u64"] = min(3, max(1, int(row.get("cooldown_ticks_u64", 3))))
                found_scout = True
            if campaign_id == "rsi_polymath_bootstrap_domain_v1":
                row["enabled"] = True
                if profile_norm == "unified" and promo_focus:
                    row["cooldown_ticks_u64"] = min(3, max(1, int(row.get("cooldown_ticks_u64", 3))))
                found_bootstrap = True
            if campaign_id == "rsi_polymath_conquer_domain_v1":
                row["enabled"] = True
                if profile_norm == "unified" and promo_focus:
                    row["cooldown_ticks_u64"] = min(3, max(1, int(row.get("cooldown_ticks_u64", 3))))
                found_conquer = True
        if enable_polymath_drive and not found_scout:
            raise RuntimeError("missing rsi_polymath_scout_v1 capability in registry")
        if not found_bootstrap:
            raise RuntimeError("missing rsi_polymath_bootstrap_domain_v1 capability in registry")
        if not found_conquer:
            raise RuntimeError("missing rsi_polymath_conquer_domain_v1 capability in registry")
    if enable_ge_sh1_optimizer:
        ge_row: dict[str, Any] | None = None
        for row in caps:
            if not isinstance(row, dict):
                continue
            if str(row.get("campaign_id", "")) == _GE_CAMPAIGN_ID:
                row["enabled"] = True
                row["enable_ccap"] = 1
                ge_row = row
                break
        if ge_row is None:
            raise RuntimeError("missing rsi_ge_symbiotic_optimizer_sh1_v0_1 capability in registry")

        ge_src = (
            _REPO_ROOT
            / "campaigns"
            / _GE_CAMPAIGN_ID
            / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json"
        ).resolve()
        if not ge_src.exists() or not ge_src.is_file():
            raise FileNotFoundError(f"missing GE campaign pack: {ge_src}")
        ge_dst = dst_root / ge_src.name
        shutil.copy2(ge_src, ge_dst)

        ge_pack_payload = _load_json(ge_dst)
        if not isinstance(ge_pack_payload, dict):
            raise RuntimeError("invalid GE campaign pack payload")
        overrides = ge_pack_overrides or {}
        if "max_ccaps" in overrides:
            ge_pack_payload["max_ccaps"] = max(1, min(8, int(overrides["max_ccaps"])))
        if "model_id" in overrides:
            model_id = str(overrides["model_id"]).strip()
            if model_id:
                ge_pack_payload["model_id"] = model_id
        _write_json(ge_dst, ge_pack_payload)

        # The executor resolves campaign packs relative to the live-wire worktree root.
        # Mirror the GE overlay pack into worktree-local `runs/.../_overnight_pack/` so
        # `campaign_pack_rel` remains repo-relative and deterministic.
        ge_worktree_dst = (_REPO_ROOT / "runs" / run_dir.name / "_overnight_pack" / ge_dst.name).resolve()
        ge_worktree_dst.parent.mkdir(parents=True, exist_ok=True)
        _write_json(ge_worktree_dst, ge_pack_payload)

        ge_row["campaign_pack_rel"] = f"runs/{run_dir.name}/_overnight_pack/{ge_dst.name}"
    if profile_norm == "refinery":
        allowed_campaign_ids = {
            "rsi_sas_code_v12_0",
            "rsi_polymath_scout_v1",
            "rsi_polymath_bootstrap_domain_v1",
            "rsi_polymath_conquer_domain_v1",
        }
        if enable_self_optimize_core:
            allowed_campaign_ids.add("rsi_omega_self_optimize_core_v1")
        if enable_ge_sh1_optimizer:
            allowed_campaign_ids.add(_GE_CAMPAIGN_ID)

        found_metasearch = False
        for row in caps:
            if not isinstance(row, dict):
                continue
            campaign_id = str(row.get("campaign_id", ""))
            if campaign_id == "rsi_sas_metasearch_v16_1":
                found_metasearch = True
            if campaign_id not in allowed_campaign_ids:
                row["enabled"] = False
        if not found_metasearch:
            raise RuntimeError("missing rsi_sas_metasearch_v16_1 capability in registry")
    elif profile_norm == "unified":
        unified_required_campaign_ids = [
            "rsi_sas_code_v12_0",
            "rsi_sas_science_v13_0",
            "rsi_sas_system_v14_0",
            "rsi_sas_kernel_v15_0",
            "rsi_sas_metasearch_v16_1",
            "rsi_sas_val_v17_0",
            "rsi_polymath_scout_v1",
            "rsi_polymath_bootstrap_domain_v1",
            "rsi_polymath_conquer_domain_v1",
            _MODEL_GENESIS_CAMPAIGN_ID,
            *[campaign_id for campaign_id, _capability_id, _goal_id in _UNIFIED_SKILL_ROWS],
        ]
        if enable_ge_sh1_optimizer:
            unified_required_campaign_ids.append(_GE_CAMPAIGN_ID)
        found_campaign_ids: set[str] = set()
        allowed_campaign_ids = set(unified_required_campaign_ids)
        if enable_self_optimize_core:
            allowed_campaign_ids.add("rsi_omega_self_optimize_core_v1")

        for row in caps:
            if not isinstance(row, dict):
                continue
            campaign_id = str(row.get("campaign_id", "")).strip()
            if campaign_id in allowed_campaign_ids:
                row["enabled"] = True
            else:
                row["enabled"] = False
            if campaign_id == "rsi_polymath_scout_v1":
                row["enable_ccap"] = 0
                row["verifier_module"] = "cdel.v18_0.verify_rsi_polymath_scout_v1"
                row["promotion_bundle_rel"] = (
                    "daemon/rsi_polymath_scout_v1/state/promotion/*.polymath_scout_promotion_bundle_v1.json"
                )
                if promo_focus:
                    row["cooldown_ticks_u64"] = min(3, max(1, int(row.get("cooldown_ticks_u64", 3))))
            if promo_focus and campaign_id in {
                "rsi_polymath_bootstrap_domain_v1",
                "rsi_polymath_conquer_domain_v1",
            }:
                row["cooldown_ticks_u64"] = min(3, max(1, int(row.get("cooldown_ticks_u64", 3))))
            if campaign_id in unified_required_campaign_ids:
                found_campaign_ids.add(campaign_id)

        missing = sorted(set(unified_required_campaign_ids) - found_campaign_ids)
        if missing:
            raise RuntimeError(f"unified profile missing capabilities: {','.join(missing)}")

    goal_queue_path = _resolve_goal_queue_overlay_path(overlay_pack_path=overlay_pack_path, overlay_root=dst_root)
    if enable_ge_sh1_optimizer and profile_norm != "unified":
        _inject_pending_goal(
            goal_queue_path=goal_queue_path,
            goal_id="goal_auto_00_ge_sh1_optimizer_0001",
            capability_id=_GE_CAPABILITY_ID,
        )
    if profile_norm == "unified":
        unified_goals = [
            ("goal_auto_00_unified_code_0001", "RSI_SAS_CODE"),
            ("goal_auto_00_unified_science_0001", "RSI_SAS_SCIENCE"),
            ("goal_auto_00_unified_system_0001", "RSI_SAS_SYSTEM"),
            ("goal_auto_00_unified_kernel_0001", "RSI_SAS_KERNEL"),
            ("goal_auto_00_unified_metasearch_0001", "RSI_SAS_METASEARCH"),
            ("goal_auto_00_unified_val_0001", "RSI_SAS_VAL"),
            ("goal_auto_00_unified_polymath_scout_0001", "RSI_POLYMATH_SCOUT"),
            ("goal_auto_00_unified_polymath_bootstrap_0001", "RSI_POLYMATH_BOOTSTRAP_DOMAIN"),
            ("goal_auto_00_unified_polymath_conquer_0001", "RSI_POLYMATH_CONQUER_DOMAIN"),
        ]
        unified_goals.extend(
            (goal_id, capability_id)
            for _campaign_id, capability_id, goal_id in _UNIFIED_SKILL_ROWS
        )
        unified_goals.append(("goal_auto_00_unified_model_genesis_v10_0001", _MODEL_GENESIS_CAPABILITY_ID))
        if enable_ge_sh1_optimizer:
            unified_goals.append(("goal_auto_00_unified_ge_sh1_0001", _GE_CAPABILITY_ID))
        _inject_pending_goals(
            goal_queue_path=goal_queue_path,
            pending_goals=unified_goals,
        )
        enabled_campaign_ids = sorted(
            str(row.get("campaign_id", "")).strip()
            for row in caps
            if isinstance(row, dict) and bool(row.get("enabled", False))
        )
        injected_goals = [
            {
                "goal_id": str(goal_id),
                "capability_id": str(capability_id),
                "status": "PENDING",
            }
            for goal_id, capability_id in unified_goals
        ]
        _write_json(
            run_dir / "OMEGA_UNIFIED_PROFILE_PLAN_v1.json",
            {
                "schema_version": "OMEGA_UNIFIED_PROFILE_PLAN_v1",
                "enabled_campaign_ids": enabled_campaign_ids,
                "injected_goals": injected_goals,
            },
        )

    _write_json(registry_path, registry)
    return overlay_pack_path


def _run_shadow_proposer(*, series_prefix: str, runs_root: Path, workers: int) -> Path | None:
    if workers <= 0:
        return None
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "tools" / "omega" / "omega_shadow_proposer_v1.py"),
        "--series_prefix",
        series_prefix,
        "--runs_root",
        str(runs_root),
        "--workers",
        str(max(1, int(workers))),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False)
    if int(run.returncode) != 0:
        return None
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    path = Path(lines[-1]).resolve()
    if not path.exists() or not path.is_file():
        return None
    return path


def _collect_shadow_proposals(run_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted((run_dir / "shadow" / "proposals").glob("*/proposal_v1.json"), key=lambda row: row.as_posix()):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload["_path"] = path.as_posix()
        out.append(payload)
    return out


def _write_shadow_proposals_summary_md(run_dir: Path) -> Path:
    proposals = _collect_shadow_proposals(run_dir)
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for row in proposals:
        risk_tag = str(row.get("risk_tag", ""))
        fast_gates = bool(row.get("fast_gates_pass_b", False))
        if risk_tag == "LOW" and fast_gates and bool(row.get("accepted_b", False)):
            accepted_rows.append(row)
            continue
        reason = "INTAKE_NOT_ACCEPTED"
        if risk_tag != "LOW":
            reason = "HIGH_RISK"
        elif not fast_gates:
            reason = "FAST_GATES_FAIL"
        out = dict(row)
        out["reject_reason"] = reason
        rejected_rows.append(out)

    lines = [
        "# OMEGA Shadow Proposals Summary",
        "",
        f"- Total proposals: **{int(len(proposals))}**",
        f"- Accepted: **{int(len(accepted_rows))}**",
        f"- Rejected: **{int(len(rejected_rows))}**",
        "",
        "## Top Expected STPS Deltas",
    ]
    top_rows = sorted(
        proposals,
        key=lambda row: (-max(0, int(row.get("expected_stps_delta_q32", 0))), str(row.get("proposal_id", ""))),
    )[:10]
    if top_rows:
        for row in top_rows:
            lines.append(
                "- "
                f"`{row.get('proposal_id', '')}` "
                f"delta_q32={int(row.get('expected_stps_delta_q32', 0))} "
                f"risk={row.get('risk_tag', '')} "
                f"fast_gates={bool(row.get('fast_gates_pass_b', False))}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Rejected Reasons"])
    if rejected_rows:
        reason_counts: dict[str, int] = {}
        for row in rejected_rows:
            key = str(row.get("reject_reason", "UNKNOWN"))
            reason_counts[key] = int(reason_counts.get(key, 0)) + 1
        for key in sorted(reason_counts.keys()):
            lines.append(f"- `{key}`: {int(reason_counts[key])}")
    else:
        lines.append("- (none)")

    out_path = run_dir / "OMEGA_SHADOW_PROPOSALS_SUMMARY.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def _write_core_opt_reports_summary_md(run_dir: Path) -> Path:
    state_dir = _state_dir(run_dir)
    report_paths = sorted(state_dir.glob("subruns/**/reports/core_opt_report_v1.json"), key=lambda row: row.as_posix())
    lines = [
        "# OMEGA Core Optimization Reports Summary",
        "",
        f"- Reports found: **{int(len(report_paths))}**",
        "",
    ]
    if not report_paths:
        lines.append("- (none)")
    else:
        for path in report_paths[:20]:
            try:
                payload = _load_json(path)
            except Exception:  # noqa: BLE001
                continue
            before_after = payload.get("before_after") if isinstance(payload, dict) else {}
            stps = (before_after or {}).get("stps_non_noop_q32") if isinstance(before_after, dict) else {}
            dispatch = (before_after or {}).get("dispatch_ns_median_u64") if isinstance(before_after, dict) else {}
            subverify = (before_after or {}).get("subverify_ns_median_u64") if isinstance(before_after, dict) else {}
            lines.append(
                "- "
                f"`{path.as_posix()}` "
                f"hotspot={payload.get('hotspot_stage_id', '')} "
                f"stps_before={int((stps or {}).get('before_q32', 0))} "
                f"stps_after={int((stps or {}).get('after_q32', 0))} "
                f"dispatch_before={int((dispatch or {}).get('before_u64', 0))} "
                f"dispatch_after={int((dispatch or {}).get('after_u64', 0))} "
                f"subverify_before={int((subverify or {}).get('before_u64', 0))} "
                f"subverify_after={int((subverify or {}).get('after_u64', 0))}"
            )
    out_path = run_dir / "OMEGA_CORE_OPT_REPORTS_SUMMARY.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def _tick_iso_utc(*, tick_u64: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (base + timedelta(seconds=max(0, int(tick_u64)))).replace(microsecond=0).isoformat()


def _write_polymath_scout_fallback_row(*, repo_root: Path, tick_u64: int, reason_code: str) -> None:
    void_path = repo_root / _POLYMATH_VOID_REPORT_REL
    void_path.parent.mkdir(parents=True, exist_ok=True)

    source_url = f"offline://omega_runner_polymath_scout/{str(reason_code).strip() or 'UNKNOWN'}/tick/{int(tick_u64)}"
    source_sha = "sha256:" + hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    row = {
        "schema_version": "polymath_void_report_v1",
        "row_id": "sha256:" + ("0" * 64),
        "scanned_at_utc": _tick_iso_utc(tick_u64=int(tick_u64)),
        "topic_id": "offline_chemistry",
        "topic_name": "chemistry offline fallback",
        "candidate_domain_id": f"chemistry_offline_{int(max(0, int(tick_u64))):06d}",
        "trend_score_q32": {"q": 1},
        "coverage_score_q32": {"q": 0},
        "void_score_q32": {"q": 1},
        "source_evidence": [
            {
                "url": source_url,
                "sha256": source_sha,
                "receipt_sha256": source_sha,
            }
        ],
    }
    no_id = dict(row)
    no_id.pop("row_id", None)
    row["row_id"] = "sha256:" + hashlib.sha256(
        json.dumps(no_id, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    void_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _run_polymath_scout(*, repo_root: Path, mailto: str | None = None, tick_u64: int = 0) -> bool:
    store_root_env = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    store_root = Path(store_root_env).expanduser().resolve() if store_root_env else (repo_root / "polymath" / "store")
    void_path = repo_root / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "polymath" / "polymath_scout_v1.py"),
        "--registry_path",
        str(repo_root / "polymath" / "registry" / "polymath_domain_registry_v1.json"),
        "--void_report_path",
        str(void_path),
        "--store_root",
        str(store_root),
        "--max_topics",
        "4",
        "--delay_seconds",
        "0",
    ]
    if mailto:
        cmd.extend(["--mailto", str(mailto)])
    run = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    rows_written_u64 = 0
    if int(run.returncode) == 0:
        lines = [line.strip() for line in str(run.stdout or "").splitlines() if line.strip()]
        if lines:
            try:
                payload = json.loads(lines[-1])
            except Exception:  # noqa: BLE001
                payload = None
            if isinstance(payload, dict):
                rows_written_u64 = max(0, int(payload.get("rows_written_u64", 0)))

    void_stats = _jsonl_row_stats(void_path)
    if int(run.returncode) == 0 and rows_written_u64 > 0 and int(void_stats.get("rows_u64", 0)) > 0 and bool(
        void_stats.get("strict_valid_b", False)
    ):
        return True

    fallback_reason = "SCOUT_EMPTY_OUTPUT" if int(run.returncode) == 0 else "SCOUT_RUN_FAIL"
    try:
        _write_polymath_scout_fallback_row(repo_root=repo_root, tick_u64=int(tick_u64), reason_code=fallback_reason)
    except Exception:  # noqa: BLE001
        return False
    return True


def _run_polymath_void_to_goals(
    *,
    repo_root: Path,
    run_dir: Path,
    tick_u64: int,
    invocation_label: str,
    out_goal_queue_effective_path: Path,
    max_goals: int,
) -> dict[str, Any] | None:
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "polymath" / "polymath_void_to_goals_v1.py"),
        "--void_report_path",
        str(repo_root / "polymath" / "registry" / "polymath_void_report_v1.jsonl"),
        "--out_goal_queue_effective_path",
        str(out_goal_queue_effective_path),
        "--router_path",
        str(repo_root / "polymath" / "registry" / "void_topic_router_v1.json"),
        "--max_goals",
        str(max(0, int(max_goals))),
        "--tick_u64",
        str(max(0, int(tick_u64))),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    if int(run.returncode) != 0:
        return None
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    payload = dict(payload)
    payload["invocation_label"] = str(invocation_label)
    _append_void_to_goals_invocation(run_dir=run_dir, payload=payload)
    return payload


def _run_polymath_refinery_proposer(
    *,
    repo_root: Path,
    store_root: Path,
    workers: int,
    max_domains: int,
    summary_path: Path,
) -> dict[str, Any] | None:
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "polymath" / "polymath_refinery_proposer_v1.py"),
        "--registry_path",
        str(repo_root / "polymath" / "registry" / "polymath_domain_registry_v1.json"),
        "--store_root",
        str(store_root),
        "--workers",
        str(max(1, int(workers))),
        "--max_domains",
        str(max(0, int(max_domains))),
        "--summary_path",
        str(summary_path),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    if int(run.returncode) != 0:
        return None
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    summary_path = Path(lines[-1]).expanduser().resolve()
    if not summary_path.exists() or not summary_path.is_file():
        return None
    try:
        payload = _load_json(summary_path)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    out = dict(payload)
    out["_summary_path"] = summary_path.as_posix()
    return out


def _run_polymath_seed_flagships(
    *,
    repo_root: Path,
    store_root: Path,
    summary_path: Path,
) -> dict[str, Any] | None:
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "polymath" / "polymath_seed_flagships_v1.py"),
        "--store_root",
        str(store_root),
        "--summary_path",
        str(summary_path),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    if int(run.returncode) != 0:
        return None
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    out_path = Path(lines[-1]).expanduser().resolve()
    if not out_path.exists() or not out_path.is_file():
        return None
    try:
        payload = _load_json(out_path)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    out = dict(payload)
    out["_summary_path"] = out_path.as_posix()
    return out


def _normalized_llm_router_goals(goal_rows: Any) -> list[dict[str, Any]]:
    if not isinstance(goal_rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in goal_rows:
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("capability_id", "")).strip()
        goal_id = str(row.get("goal_id", "")).strip()
        if not capability_id or not goal_id:
            continue
        priority_u8 = max(0, min(255, int(row.get("priority_u8", 0))))
        reason = str(row.get("reason", "")).strip()
        out.append(
            {
                "capability_id": capability_id,
                "goal_id": goal_id,
                "priority_u8": int(priority_u8),
                "reason": reason,
            }
        )
    out.sort(
        key=lambda row: (
            -int(row.get("priority_u8", 0)),
            str(row.get("capability_id", "")),
            str(row.get("goal_id", "")),
        )
    )
    return out


def _apply_llm_router_result(
    *,
    tick_u64: int,
    goal_queue_path: Path,
    router_result: dict[str, Any],
    llm_router_invocations: list[dict[str, Any]],
    llm_router_failures: list[dict[str, Any]],
    llm_router_required: bool,
) -> bool:
    status = str(router_result.get("status", "")).strip()
    error_reason = str(router_result.get("error_reason", "")).strip()
    goals = _normalized_llm_router_goals(router_result.get("goal_injections"))
    for row in goals:
        _inject_pending_goal(
            goal_queue_path=goal_queue_path,
            goal_id=str(row.get("goal_id", "")),
            capability_id=str(row.get("capability_id", "")),
        )

    web_queries = router_result.get("web_queries")
    if isinstance(web_queries, list):
        web_query_failures = sorted(
            [
                {
                    "provider": str(row.get("provider", "")),
                    "query": str(row.get("query", "")),
                    "error": str(row.get("error", "")),
                }
                for row in web_queries
                if isinstance(row, dict) and str(row.get("error", "")).strip()
            ],
            key=lambda row: (
                str(row.get("provider", "")),
                str(row.get("query", "")),
                str(row.get("error", "")),
            ),
        )
    else:
        web_query_failures = []

    llm_router_invocations.append(
        {
            "tick_u64": int(max(0, tick_u64)),
            "status": status,
            "error_reason": error_reason,
            "backend": str(router_result.get("backend", "")),
            "provider": str(router_result.get("provider", "")),
            "model": str(router_result.get("model", "")),
            "prompt_sha256": str(router_result.get("prompt_sha256", "")),
            "response_sha256": str(router_result.get("response_sha256", "")),
            "plan_path": str(router_result.get("plan_path", "")),
            "trace_path": str(router_result.get("trace_path", "")),
            "goal_injections_injected_u64": int(len(goals)),
            "web_queries_u64": int(len(web_queries) if isinstance(web_queries, list) else 0),
            "web_query_failures_u64": int(len(web_query_failures)),
        }
    )

    if web_query_failures:
        llm_router_failures.append(
            {
                "tick_u64": int(max(0, tick_u64)),
                "reason": "WEB_QUERY_FAILURE",
                "errors": web_query_failures,
                "next_actions": [
                    {
                        "kind": "CHECK_NET_OR_CACHE",
                        "campaign_id": "",
                        "detail": "set OMEGA_NET_LIVE_OK=1 or pre-populate polymath store cache for planned web queries",
                    }
                ],
            }
        )

    if status == "OK":
        return False

    reason = error_reason or "LLM_ROUTER_FAIL"
    if "LLM_REPLAY_MISS" in reason:
        action_detail = "add replay row to ORCH_LLM_REPLAY_PATH for this prompt hash"
    elif "LLM_ROUTER_INVALID_JSON" in reason:
        action_detail = "fix replay/mock response to be valid JSON for omega_llm_router_plan_v1"
    else:
        action_detail = "inspect OMEGA_LLM_TOOL_TRACE_v1.jsonl and router diagnostics for failure cause"
    llm_router_failures.append(
        {
            "tick_u64": int(max(0, tick_u64)),
            "reason": reason,
            "next_actions": [
                {
                    "kind": "CHECK_LLM_ROUTER",
                    "campaign_id": "",
                    "detail": action_detail,
                }
            ],
        }
    )
    return bool(llm_router_required)


def _collect_polymath_bootstrap_reports(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    state_dir = _state_dir(run_dir)
    for path in sorted(
        state_dir.glob("subruns/**/daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        out = dict(payload)
        out["_path"] = path.as_posix()
        rows.append(out)
    return rows


def _collect_polymath_conquer_reports(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    state_dir = _state_dir(run_dir)
    for path in sorted(
        state_dir.glob("subruns/**/daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json"),
        key=lambda row: row.as_posix(),
    ):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        out = dict(payload)
        out["_path"] = path.as_posix()
        rows.append(out)
    return rows


def _collect_polymath_progress(run_dir: Path) -> dict[str, Any]:
    observations_dir = _state_dir(run_dir) / "observations"
    rows: list[tuple[int, int, int, int]] = []
    for path in sorted(observations_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda row: row.as_posix()):
        try:
            payload = _load_json(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        tick_u64 = max(0, int(payload.get("tick_u64", 0)))
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            continue
        top_void_q32 = max(0, int(((metrics.get("top_void_score_q32") or {}).get("q", 0))))
        coverage_q32 = max(0, int(((metrics.get("domain_coverage_ratio") or {}).get("q", 0))))
        domains_bootstrapped_u64 = max(0, int(metrics.get("domains_bootstrapped_u64", 0)))
        rows.append((tick_u64, top_void_q32, coverage_q32, domains_bootstrapped_u64))

    if not rows:
        return {
            "first_tick_u64": 0,
            "last_tick_u64": 0,
            "top_void_score_first_q32": 0,
            "top_void_score_last_q32": 0,
            "top_void_score_delta_q32": 0,
            "top_void_score_drop_b": False,
            "coverage_ratio_first_q32": 0,
            "coverage_ratio_last_q32": 0,
            "coverage_ratio_delta_q32": 0,
            "coverage_ratio_increase_b": False,
            "domains_bootstrapped_first_u64": 0,
            "domains_bootstrapped_last_u64": 0,
            "domains_bootstrapped_delta_u64": 0,
            "samples_u64": 0,
        }

    rows.sort(key=lambda row: row[0])
    first_tick, first_void, first_cov, first_domains = rows[0]
    last_tick, last_void, last_cov, last_domains = rows[-1]
    return {
        "first_tick_u64": int(first_tick),
        "last_tick_u64": int(last_tick),
        "top_void_score_first_q32": int(first_void),
        "top_void_score_last_q32": int(last_void),
        "top_void_score_delta_q32": int(last_void - first_void),
        "top_void_score_drop_b": int(last_void) < int(first_void),
        "coverage_ratio_first_q32": int(first_cov),
        "coverage_ratio_last_q32": int(last_cov),
        "coverage_ratio_delta_q32": int(last_cov - first_cov),
        "coverage_ratio_increase_b": int(last_cov) > int(first_cov),
        "domains_bootstrapped_first_u64": int(first_domains),
        "domains_bootstrapped_last_u64": int(last_domains),
        "domains_bootstrapped_delta_u64": int(max(0, int(last_domains) - int(first_domains))),
        "samples_u64": int(len(rows)),
    }


def _write_polymath_void_report_md(*, run_dir: Path, repo_root: Path) -> Path:
    void_path = repo_root / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
    rows: list[dict[str, Any]] = []
    if void_path.exists() and void_path.is_file():
        for raw in void_path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(payload, dict):
                rows.append(payload)

    rows_sorted = sorted(
        rows,
        key=lambda row: (-int(((row.get("void_score_q32") or {}).get("q", 0))), str(row.get("candidate_domain_id", ""))),
    )[:10]
    lines = [
        "# OMEGA Polymath Void Report",
        "",
        f"- Rows scanned: **{int(len(rows))}**",
        "",
        "## Top Voids",
    ]
    if rows_sorted:
        for row in rows_sorted:
            evidence = row.get("source_evidence")
            evidence_rows = evidence if isinstance(evidence, list) else []
            evidence_hashes = [
                str(item.get("sha256", ""))
                for item in evidence_rows
                if isinstance(item, dict) and str(item.get("sha256", "")).startswith("sha256:")
            ]
            lines.append(
                "- "
                f"`{row.get('candidate_domain_id', '')}` "
                f"topic=`{row.get('topic_name', '')}` "
                f"void_q32={int((row.get('void_score_q32') or {}).get('q', 0))} "
                f"evidence={','.join(evidence_hashes[:4])}"
            )
    else:
        lines.append("- (none)")

    out_path = run_dir / "OMEGA_POLYMATH_VOID_REPORT.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def _write_new_domain_report_md(*, run_dir: Path, bootstrap_reports: list[dict[str, Any]]) -> Path:
    lines = [
        "# OMEGA New Domain Report",
        "",
        f"- Bootstrap reports: **{int(len(bootstrap_reports))}**",
        "",
    ]
    if not bootstrap_reports:
        lines.append("- (none)")
    else:
        for row in bootstrap_reports:
            lines.append(
                "- "
                f"status=`{row.get('status', '')}` "
                f"domain=`{row.get('domain_id', '')}` "
                f"topic=`{row.get('topic_name', row.get('domain_name', ''))}` "
                f"pack=`{row.get('domain_pack_rel', '')}`"
            )
    out_path = run_dir / "OMEGA_NEW_DOMAIN_REPORT.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def _write_domain_conquer_report_md(*, run_dir: Path, conquer_reports: list[dict[str, Any]]) -> Path:
    lines = [
        "# OMEGA Domain Conquer Report",
        "",
        f"- Conquer reports: **{int(len(conquer_reports))}**",
        "",
    ]
    if not conquer_reports:
        lines.append("- (none)")
    else:
        for row in conquer_reports:
            lines.append(
                "- "
                f"status=`{row.get('status', '')}` "
                f"domain=`{row.get('domain_id', '')}` "
                f"metric=`{row.get('metric_id', '')}` "
                f"baseline_q32={int(row.get('baseline_metric_q32', 0))} "
                f"improved_q32={int(row.get('improved_metric_q32', 0))}"
            )
    out_path = run_dir / "OMEGA_DOMAIN_CONQUER_REPORT.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def _tick_activation_binding(state_dir: Path, tick_u64: int) -> dict[str, str] | None:
    for activation_path in sorted(state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json")):
        activation = _load_json(activation_path)
        if int(activation.get("tick_u64", -1)) != int(tick_u64):
            continue
        if not bool(activation.get("activation_success", False)):
            continue
        if str(activation.get("before_active_manifest_hash", "")) == str(activation.get("after_active_manifest_hash", "")):
            continue

        binding_path = activation_path.parent.parent / "promotion" / "omega_activation_binding_v1.json"
        if not binding_path.exists() or not binding_path.is_file():
            continue
        binding = _load_json(binding_path)
        capability_id = str(binding.get("capability_id", "")).strip()
        activation_key = str(binding.get("activation_key", "")).strip()
        if not capability_id or not activation_key:
            continue
        return {
            "capability_id": capability_id,
            "activation_key": activation_key,
        }
    return None


def _stage_and_commit_livewire_tick(*, repo_root: Path, state_dir: Path, tick_u64: int) -> dict[str, Any] | None:
    binding = _tick_activation_binding(state_dir, tick_u64)
    if binding is None:
        return None

    subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    # Keep runtime artifacts out of the live-wire commit even if they are unignored.
    subprocess.run(
        ["git", "restore", "--staged", "--", "runs", ".omega_cache"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    changed_files = [row.strip() for row in staged.stdout.splitlines() if row.strip()]
    if not changed_files:
        return None

    message = (
        f"omega tick={int(tick_u64)} cap={binding['capability_id']} "
        f"activation_key={binding['activation_key']}"
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    commit_sha = head.stdout.strip()
    return {
        "tick_u64": int(tick_u64),
        "commit_sha": commit_sha,
        "capability_id": binding["capability_id"],
        "activation_key": binding["activation_key"],
        "message": message,
        "changed_files": changed_files,
    }


def _write_livewire_git_summary(*, run_dir: Path, branch: str, commit_rows: list[dict[str, Any]]) -> Path:
    changed_file_counts: dict[str, int] = {}
    for row in commit_rows:
        for path in row.get("changed_files", []):
            key = str(path)
            changed_file_counts[key] = int(changed_file_counts.get(key, 0)) + 1

    payload = {
        "schema_version": "OMEGA_LIVEWIRE_GIT_SUMMARY_v1",
        "branch": branch,
        "commit_count_u64": int(len(commit_rows)),
        "commits": commit_rows,
        "changed_file_summary": [
            {"path": key, "count_u64": int(changed_file_counts[key])}
            for key in sorted(changed_file_counts.keys())
        ],
    }
    out_path = run_dir / "OMEGA_LIVEWIRE_GIT_SUMMARY_v1.json"
    _write_json(out_path, payload)
    return out_path


def _write_morning_diff(
    *,
    run_dir: Path,
    branch: str,
    commit_rows: list[dict[str, Any]],
    promotion_summary: dict[str, Any],
    refinery_summary: dict[str, Any] | None,
    conquer_reports: list[dict[str, Any]],
) -> Path:
    top_touched = promotion_summary.get("top_touched_paths")
    touched_rows = top_touched if isinstance(top_touched, list) else []

    lines = [
        "# OMEGA Morning Diff",
        "",
        f"- Branch: `{branch}`",
        f"- Commits created: **{int(len(commit_rows))}**",
        f"- Activation successes: **{int(promotion_summary.get('activation_success_u64', 0))}**",
        f"- Capability family coverage: **{int(promotion_summary.get('unique_promoted_families_u64', 0))}**",
        "",
        "## Families",
    ]
    families = promotion_summary.get("unique_promoted_families")
    family_rows = families if isinstance(families, list) else []
    if family_rows:
        for family in family_rows:
            lines.append(f"- `{str(family)}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Commits"])
    if commit_rows:
        for row in commit_rows:
            lines.append(
                "- "
                f"`{row.get('commit_sha', '')}` "
                f"tick={int(row.get('tick_u64', 0))} "
                f"cap={row.get('capability_id', '')} "
                f"activation_key={row.get('activation_key', '')}"
            )
    else:
        lines.append("- (none)")

    lines.extend(["", "## Top Touched Paths"])
    if touched_rows:
        for row in touched_rows[:20]:
            lines.append(f"- `{row.get('path', '')}`: {int(row.get('count_u64', 0))}")
    else:
        lines.append("- (none)")

    cache_hit_reports_u64 = sum(1 for row in conquer_reports if bool(row.get("refinery_cache_hit_b", False)))
    cache_hit_rate_pct = (
        (100.0 * float(cache_hit_reports_u64) / float(len(conquer_reports)))
        if conquer_reports
        else 0.0
    )
    lines.extend(["", "## Polymath Refinery"])
    if isinstance(refinery_summary, dict):
        lines.append(f"- Proposals generated: **{int(refinery_summary.get('proposals_generated_u64', 0))}**")
        lines.append(f"- Conquer cache-hit reports: **{int(cache_hit_reports_u64)} / {int(len(conquer_reports))}**")
        lines.append(f"- Conquer cache-hit rate: **{cache_hit_rate_pct:.2f}%**")
        top_domains = refinery_summary.get("top_domains_expected_val_delta")
        top_rows = top_domains if isinstance(top_domains, list) else []
        if top_rows:
            lines.append("- Top domains by expected val delta:")
            for row in top_rows[:10]:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "- "
                    f"`{row.get('domain_id', '')}` "
                    f"delta_q32={int(row.get('expected_val_delta_q32', 0))} "
                    f"proposal_id={row.get('proposal_id', '')}"
                )
        else:
            lines.append("- Top domains by expected val delta: (none)")
    else:
        lines.append("- Proposer summary: (disabled or unavailable)")
        lines.append(f"- Conquer cache-hit reports: **{int(cache_hit_reports_u64)} / {int(len(conquer_reports))}**")
        lines.append(f"- Conquer cache-hit rate: **{cache_hit_rate_pct:.2f}%**")

    out_path = run_dir / "OMEGA_MORNING_DIFF.md"
    _write_md(out_path, "\n".join(lines) + "\n")
    return out_path


def main() -> None:
    global _REPO_ROOT

    parser = argparse.ArgumentParser(prog="omega_overnight_runner_v1")
    parser.add_argument("--hours", type=float, default=10.0)
    parser.add_argument("--series_prefix", default="")
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument(
        "--campaign_pack",
        default="campaigns/rsi_omega_daemon_v18_0_prod/rsi_omega_daemon_pack_v1.json",
    )
    parser.add_argument("--meta_core_mode", choices=("production", "sandbox"), default="production")
    parser.add_argument("--git_branch", default="")
    parser.add_argument("--worktree_dir", default="")
    parser.add_argument("--push", type=int, default=0)
    parser.add_argument("--shadow_workers", type=int, default=0)
    parser.add_argument("--enable_shadow_proposals", type=int, default=0)
    parser.add_argument("--enable_self_optimize_core", type=int, default=0)
    parser.add_argument("--enable_polymath_drive", type=int, default=0)
    parser.add_argument("--enable_polymath_scout", type=int, default=0)
    parser.add_argument("--enable_polymath_bootstrap", type=int, default=0)
    parser.add_argument("--enable_polymath_refinery_proposer", type=int, default=0)
    parser.add_argument("--enable_ge_sh1_optimizer", type=int, default=0)
    parser.add_argument("--enable_llm_router", type=int, default=0)
    parser.add_argument("--ge_max_ccaps", type=int, default=3)
    parser.add_argument("--ge_model_id", default="ge-v0_3")
    parser.add_argument("--ge_state_root", default="")
    parser.add_argument("--ge_audit", type=int, default=None)
    parser.add_argument("--max_new_domains", type=int, default=1)
    parser.add_argument("--polymath_scout_every_ticks", type=int, default=50)
    parser.add_argument("--polymath_max_new_domains_per_run", type=int, default=1)
    parser.add_argument("--polymath_conquer_budget_ticks", type=int, default=30)
    parser.add_argument("--polymath_refinery_workers", type=int, default=6)
    parser.add_argument("--polymath_refinery_max_domains", type=int, default=32)
    parser.add_argument("--require_activation_success", type=int, default=0)
    parser.add_argument("--require_new_domain_registered", type=int, default=0)
    parser.add_argument("--polymath_mailto", default="")
    parser.add_argument("--min_activation_successes", type=int, default=0)
    parser.add_argument("--stall_watchdog_checkpoints", type=int, default=3)
    parser.add_argument("--stall_watchdog_runaway_blocked_pct", type=float, default=90.0)
    parser.add_argument("--profile", choices=("full", "refinery", "unified"), default="full")
    parser.add_argument("--promo_focus", type=int, default=0)
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    series_prefix = str(args.series_prefix).strip()
    if not series_prefix:
        series_prefix = f"omega_overnight_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"
    enable_polymath_drive = bool(int(args.enable_polymath_drive))
    enable_polymath_scout = bool(int(args.enable_polymath_scout)) or enable_polymath_drive
    enable_polymath_bootstrap = bool(int(args.enable_polymath_bootstrap)) or enable_polymath_drive
    enable_polymath_refinery_proposer = bool(int(args.enable_polymath_refinery_proposer))
    enable_ge_sh1_optimizer = bool(int(args.enable_ge_sh1_optimizer))
    enable_llm_router = bool(int(args.enable_llm_router))
    ge_max_ccaps = max(1, min(8, int(args.ge_max_ccaps)))
    ge_model_id = str(args.ge_model_id).strip() or "ge-v0_3"
    ge_state_root_raw = str(args.ge_state_root).strip()
    ge_state_root = (
        Path(ge_state_root_raw).expanduser().resolve()
        if ge_state_root_raw
        else (_ORIGINAL_REPO_ROOT / ".omega_cache" / "genesis_engine").resolve()
    )
    ge_state_root.mkdir(parents=True, exist_ok=True)
    if args.ge_audit is None:
        ge_audit = bool(enable_ge_sh1_optimizer)
    else:
        ge_audit = bool(int(args.ge_audit)) and bool(enable_ge_sh1_optimizer)
    manual_polymath_scout = bool(enable_polymath_scout and not enable_polymath_drive)
    min_activation_successes = max(0, int(args.min_activation_successes))
    if int(args.require_activation_success) != 0 and min_activation_successes <= 0:
        min_activation_successes = 1
    benchmark_every_ticks = max(1, int(args.polymath_scout_every_ticks))
    max_new_domains = max(0, int(args.polymath_max_new_domains_per_run))
    conquer_budget_ticks = max(1, int(args.polymath_conquer_budget_ticks))
    polymath_refinery_workers = max(1, int(args.polymath_refinery_workers))
    polymath_refinery_max_domains = max(0, int(args.polymath_refinery_max_domains))
    require_new_domain_registered = bool(int(args.require_new_domain_registered))
    stall_watchdog_checkpoints = max(1, int(args.stall_watchdog_checkpoints))
    stall_watchdog_runaway_blocked_pct = max(0.0, float(args.stall_watchdog_runaway_blocked_pct))
    profile = str(args.profile).strip().lower()
    promo_focus = bool(int(args.promo_focus))
    promo_focus_unified_b = bool(profile == "unified" and promo_focus)
    required_pass_gates = _required_pass_gates(profile, polymath_enabled=True)
    halt_on_gate_failures = bool((profile != "refinery") and (not promo_focus_unified_b))

    campaign_pack_input = Path(args.campaign_pack).resolve()

    run_dir = runs_root / series_prefix
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    llm_router_required = str(os.environ.get("OMEGA_LLM_ROUTER_REQUIRED", "")).strip() == "1"
    llm_router_backend = str(os.environ.get("ORCH_LLM_BACKEND", "mock")).strip() or "mock"
    llm_router_preflight_reason = ""
    if enable_llm_router and _llm_backend_is_replay_like(llm_router_backend):
        replay_path_raw = str(os.environ.get("ORCH_LLM_REPLAY_PATH", "")).strip()
        replay_path = Path(replay_path_raw).expanduser().resolve() if replay_path_raw else None
        if replay_path is None or not replay_path.exists() or not replay_path.is_file():
            llm_router_preflight_reason = "LLM_REPLAY_PATH_MISSING"

    branch = str(args.git_branch).strip()
    if not branch:
        branch = f"omega/livewire_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"

    worktree_dir_raw = str(args.worktree_dir).strip()
    if worktree_dir_raw:
        worktree_dir = Path(worktree_dir_raw).resolve()
    else:
        worktree_dir = (run_dir / "_worktree").resolve()

    prev_polymath_store_root = os.environ.get("OMEGA_POLYMATH_STORE_ROOT")
    prev_ge_state_root = os.environ.get("OMEGA_GE_STATE_ROOT")
    prev_promo_focus = os.environ.get("OMEGA_PROMO_FOCUS")
    os.environ["OMEGA_GE_STATE_ROOT"] = str(ge_state_root)
    if promo_focus:
        os.environ["OMEGA_PROMO_FOCUS"] = "1"
    else:
        os.environ.pop("OMEGA_PROMO_FOCUS", None)
    store_root_env = str(prev_polymath_store_root or "").strip()
    canonical_polymath_store: Path | None = None
    if profile == "refinery" and enable_polymath_refinery_proposer:
        if store_root_env:
            canonical_polymath_store = Path(store_root_env).expanduser().resolve()
        else:
            canonical_polymath_store = (_ORIGINAL_REPO_ROOT / ".omega_cache" / "polymath" / "store").resolve()
            os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(canonical_polymath_store)
        canonical_polymath_store.mkdir(parents=True, exist_ok=True)
    if enable_llm_router:
        canonical_polymath_store = (run_dir / "polymath" / "store").resolve()
        canonical_polymath_store.mkdir(parents=True, exist_ok=True)
        os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(canonical_polymath_store)
        os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(canonical_polymath_store)
    else:
        if store_root_env:
            canonical_polymath_store = Path(store_root_env).expanduser().resolve()
        else:
            canonical_polymath_store = (_ORIGINAL_REPO_ROOT / ".omega_cache" / "polymath" / "store").resolve()
            os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(canonical_polymath_store)
        canonical_polymath_store.mkdir(parents=True, exist_ok=True)

    _assert_livewire_repo_clean(_ORIGINAL_REPO_ROOT)
    _REPO_ROOT = _prepare_livewire_worktree(repo_root=_ORIGINAL_REPO_ROOT, branch=branch, worktree_dir=worktree_dir)
    _sync_campaign_fixtures_into_worktree(source_repo_root=_ORIGINAL_REPO_ROOT, repo_root=_REPO_ROOT)
    _ensure_router_shims(repo_root=_REPO_ROOT)

    campaign_pack = _resolve_campaign_pack_for_repo(
        campaign_pack=campaign_pack_input,
        source_repo_root=_ORIGINAL_REPO_ROOT,
        repo_root=_REPO_ROOT,
    )
    overlay_error = ""
    try:
        if campaign_pack.exists() and campaign_pack.is_file():
            campaign_pack = _prepare_campaign_pack_overlay(
                campaign_pack=campaign_pack,
                run_dir=run_dir,
                enable_self_optimize_core=bool(int(args.enable_self_optimize_core)),
                enable_polymath_drive=enable_polymath_drive,
                enable_polymath_bootstrap=enable_polymath_bootstrap,
                enable_ge_sh1_optimizer=enable_ge_sh1_optimizer,
                ge_pack_overrides={
                    "max_ccaps": ge_max_ccaps,
                    "model_id": ge_model_id,
                }
                if enable_ge_sh1_optimizer
                else None,
                profile=profile,
                promo_focus=bool(promo_focus),
            )
    except Exception as exc:  # noqa: BLE001
        overlay_error = f"{type(exc).__name__}:{exc}"
    preflight_report = _preflight_contract(
        run_dir=run_dir,
        campaign_pack=campaign_pack,
        repo_root=_REPO_ROOT,
        overlay_error=overlay_error,
    )
    preflight_report_path = run_dir / "OMEGA_PREFLIGHT_REPORT_v1.json"
    _write_json(preflight_report_path, preflight_report)

    capability_registry_path = campaign_pack.parent / "omega_capability_registry_v2.json"
    if not capability_registry_path.exists() or not capability_registry_path.is_file():
        capability_registry_path = None
    goal_queue_effective_path = run_dir / "_overnight_pack" / "goals" / "omega_goal_queue_effective_v1.json"
    if not goal_queue_effective_path.exists() or not goal_queue_effective_path.is_file():
        goal_queue_effective_path = None
    replay_manifest_path = write_replay_manifest(
        run_dir=run_dir,
        series_prefix=series_prefix,
        profile=profile,
        meta_core_mode=str(args.meta_core_mode),
        campaign_pack_path=campaign_pack,
        capability_registry_path=capability_registry_path,
        goal_queue_effective_path=goal_queue_effective_path,
    )
    polymath_enablement = _overlay_polymath_enablement(campaign_pack)
    required_pass_gates = _required_pass_gates(
        profile,
        polymath_enabled=bool(polymath_enablement.get("polymath_enabled", False)),
    )
    polymath_gate_failfast_enabled = bool(
        profile in {"unified", "refinery"} and polymath_enablement.get("polymath_enabled", False)
    )
    if promo_focus_unified_b:
        polymath_gate_failfast_enabled = False
    polymath_stall_p_tick_u64 = int(_POLYMATH_STALL_P_TICK_U64)
    polymath_stall_q_tick_u64 = int(_POLYMATH_STALL_Q_TICK_U64)
    if polymath_gate_failfast_enabled and bool(promo_focus):
        polymath_stall_p_tick_u64 = max(polymath_stall_p_tick_u64, 20)
        polymath_stall_q_tick_u64 = max(polymath_stall_q_tick_u64, 40)

    void_goal_queue_effective_path = (run_dir / "_overnight_pack" / "goals" / "omega_goal_queue_effective_v1.json").resolve()

    if str(args.meta_core_mode) == "production":
        meta_core_root = (_REPO_ROOT / "meta-core").resolve()
    else:
        meta_core_root = create_meta_core_sandbox(runs_root=runs_root, series=series_prefix).resolve()
    if not meta_core_root.exists() or not meta_core_root.is_dir():
        raise FileNotFoundError(f"missing meta-core root: {meta_core_root}")

    bundle_hashes_before = _bundle_hashes(meta_core_root)

    prev_meta_core_root = os.environ.get("OMEGA_META_CORE_ROOT")
    prev_meta_core_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow_sim = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")

    os.environ["OMEGA_META_CORE_ROOT"] = str(meta_core_root)
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "live"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "0"

    run_started_monotonic = time.monotonic()
    deadline = datetime.now(UTC) + timedelta(hours=max(0.01, float(args.hours)))
    deadline_monotonic = time.monotonic() + max(36.0, float(args.hours) * 3600.0)

    tick_u64 = 0
    prev_state_dir: Path | None = None
    safe_halt = False
    termination_reason = "DEADLINE_EXPIRED"
    verifier_failures: list[dict[str, Any]] = []
    gate_failures: list[dict[str, Any]] = []
    commit_rows: list[dict[str, Any]] = []
    shadow_summary_paths: list[str] = []
    latest_gate_status: dict[str, str] = {}
    gate_regression_or_failure_b = False
    diagnostic_packet_path: Path | None = None
    capability_usage_path: Path | None = None
    llm_router_invocations: list[dict[str, Any]] = []
    llm_router_failures: list[dict[str, Any]] = []

    baseline_head_sha = _git_head_sha(_REPO_ROOT)
    last_good_head_sha = baseline_head_sha
    rollback_applied_b = False
    rollback_target_sha = ""

    stall_checkpoint_streak_u64 = 0
    prev_checkpoint_promoted_u64: int | None = None
    prev_checkpoint_activation_success_u64: int | None = None

    refinery_proposer_summary: dict[str, Any] | None = None
    refinery_proposer_summary_path = ""
    seed_flagships_summary_path = ""
    preloop_abort_b = False
    if not bool(preflight_report.get("ok_b", False)):
        preloop_abort_b = True
        safe_halt = False
        termination_reason = "PREFLIGHT_FAIL"
        preflight_fail_reason = str(preflight_report.get("fail_reason", "")).strip()
        gate_failures.append(
            {
                "tick_u64": 0,
                "reason": f"PREFLIGHT_FAIL:{preflight_fail_reason}" if preflight_fail_reason else "PREFLIGHT_FAIL",
            }
        )
    if llm_router_preflight_reason:
        safe_halt = True
        termination_reason = "PREFLIGHT_FAIL"
        preloop_abort_b = True
        llm_router_failures.append(
            {
                "tick_u64": 0,
                "reason": str(llm_router_preflight_reason),
                "next_actions": [
                    {
                        "kind": "SET_ENV",
                        "campaign_id": "",
                        "detail": "set ORCH_LLM_REPLAY_PATH to an existing replay jsonl when using replay backends",
                    }
                ],
            }
        )

    run_tick = _load_run_tick(_REPO_ROOT) if not preloop_abort_b else (lambda **kwargs: {"safe_halt": False})

    if profile == "refinery" and enable_polymath_refinery_proposer:
        if canonical_polymath_store is None:
            safe_halt = True
            termination_reason = "MISSING_POLYMATH_STORE_ROOT"
            preloop_abort_b = True
        else:
            conquer_pack_path = (
                _REPO_ROOT
                / "campaigns"
                / "rsi_polymath_conquer_domain_v1"
                / "rsi_polymath_conquer_domain_pack_v1.json"
            )
            if conquer_pack_path.exists() and conquer_pack_path.is_file():
                try:
                    conquer_pack = _load_json(conquer_pack_path)
                    if isinstance(conquer_pack, dict):
                        conquer_pack["target_domain_id"] = "pubchem_weight300"
                        _write_json(conquer_pack_path, conquer_pack)
                except Exception:  # noqa: BLE001
                    pass

            seed_summary_path = run_dir / "OMEGA_POLYMATH_SEED_FLAGSHIPS_SUMMARY_v1.json"
            seed_flagships_summary_path = seed_summary_path.as_posix()
            seed_summary = _run_polymath_seed_flagships(
                repo_root=_REPO_ROOT,
                store_root=canonical_polymath_store,
                summary_path=seed_summary_path,
            )
            if seed_summary is None or str(seed_summary.get("status", "")) != "OK":
                safe_halt = True
                termination_reason = "SEED_FLAGSHIPS_FAIL"
                preloop_abort_b = True
            else:
                proposer_summary_path = run_dir / "OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1.json"
                refinery_proposer_summary_path = proposer_summary_path.as_posix()
                refinery_proposer_summary = _run_polymath_refinery_proposer(
                    repo_root=_REPO_ROOT,
                    store_root=canonical_polymath_store,
                    workers=polymath_refinery_workers,
                    max_domains=polymath_refinery_max_domains,
                    summary_path=proposer_summary_path,
                )
    elif (not preloop_abort_b) and enable_polymath_refinery_proposer:
        if canonical_polymath_store is None:
            canonical_polymath_store = (_ORIGINAL_REPO_ROOT / ".omega_cache" / "polymath" / "store").resolve()
            canonical_polymath_store.mkdir(parents=True, exist_ok=True)
            os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(canonical_polymath_store)
        proposer_summary_path = run_dir / "OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1.json"
        refinery_proposer_summary_path = proposer_summary_path.as_posix()
        refinery_proposer_summary = _run_polymath_refinery_proposer(
            repo_root=_REPO_ROOT,
            store_root=canonical_polymath_store,
            workers=polymath_refinery_workers,
            max_domains=polymath_refinery_max_domains,
            summary_path=proposer_summary_path,
        )

    verifier_client = OmegaVerifierClient(repo_root=_REPO_ROOT) if not preloop_abort_b else None
    if not preloop_abort_b and manual_polymath_scout:
        _run_polymath_scout(
            repo_root=_REPO_ROOT,
            mailto=str(args.polymath_mailto).strip() or None,
            tick_u64=0,
        )
    if not preloop_abort_b and enable_polymath_drive:
        _run_polymath_scout(
            repo_root=_REPO_ROOT,
            mailto=str(args.polymath_mailto).strip() or None,
            tick_u64=0,
        )
        _run_polymath_void_to_goals(
            repo_root=_REPO_ROOT,
            run_dir=run_dir,
            tick_u64=0,
            invocation_label="preloop",
            out_goal_queue_effective_path=void_goal_queue_effective_path,
            max_goals=_VOID_TO_GOALS_MAX_GOALS_U64,
        )
    if not preloop_abort_b and polymath_gate_failfast_enabled:
        _route_polymath_progress_goal(
            run_dir=run_dir,
            repo_root=_REPO_ROOT,
            state_dir=_state_dir(run_dir),
            out_goal_queue_effective_path=void_goal_queue_effective_path,
            tick_u64=0,
        )
    if not preloop_abort_b and enable_llm_router:
        router_result = omega_llm_router_v1.run_failsoft(
            run_dir=run_dir,
            tick_u64=0,
            store_root=canonical_polymath_store,
        )
        should_halt = _apply_llm_router_result(
            tick_u64=0,
            goal_queue_path=void_goal_queue_effective_path,
            router_result=router_result,
            llm_router_invocations=llm_router_invocations,
            llm_router_failures=llm_router_failures,
            llm_router_required=llm_router_required,
        )
        if should_halt:
            safe_halt = True
            termination_reason = "LLM_ROUTER_FAIL"
            preloop_abort_b = True
    bootstrap_first_tick_u64: int | None = None
    try:
        while (not preloop_abort_b) and time.monotonic() < deadline_monotonic:
            tick_u64 += 1
            try:
                tick_result = run_tick(
                    campaign_pack=campaign_pack,
                    out_dir=run_dir,
                    tick_u64=tick_u64,
                    prev_state_dir=prev_state_dir,
                )
            except Exception as exc:  # noqa: BLE001
                verifier_failures.append(
                    {
                        "tick_u64": int(tick_u64),
                        "reason": "RUN_TICK_EXCEPTION",
                        "output": str(exc),
                    }
                )
                termination_reason = "RUN_TICK_EXCEPTION"
                break
            prev_state_dir = _state_dir(run_dir)
            safe_halt = bool(tick_result.get("safe_halt", False))

            if verifier_client is None:
                verifier_failures.append(
                    {
                        "tick_u64": int(tick_u64),
                        "reason": "VERIFY_CLIENT_UNAVAILABLE",
                        "output": "",
                    }
                )
                termination_reason = "VERIFIER_FAIL"
                break
            ok, verdict_or_reason, verify_output = verifier_client.verify(prev_state_dir)
            if not ok:
                verifier_failures.append(
                    {
                        "tick_u64": int(tick_u64),
                        "reason": str(verdict_or_reason),
                        "output": verify_output,
                    }
                )
                termination_reason = "VERIFIER_FAIL"
                break

            commit_row = _stage_and_commit_livewire_tick(repo_root=_REPO_ROOT, state_dir=prev_state_dir, tick_u64=tick_u64)
            if commit_row is not None:
                commit_rows.append(commit_row)

            checkpoint_due_b = bool(
                (tick_u64 % benchmark_every_ticks == 0)
                or (
                    polymath_gate_failfast_enabled
                    and tick_u64 in {int(polymath_stall_p_tick_u64), int(polymath_stall_q_tick_u64)}
                )
                or (enable_llm_router and tick_u64 in {_POLYMATH_STALL_P_TICK_U64, _POLYMATH_STALL_Q_TICK_U64})
            )
            if checkpoint_due_b:
                _rolling_snapshot(
                    run_dir,
                    series_prefix=series_prefix,
                    tick_u64=tick_u64,
                    deadline_utc=deadline.isoformat(),
                )
                checkpoint_scout_allowed = not (
                    bool(promo_focus) and profile == "unified" and bool(enable_polymath_drive)
                )
                scout_attempted_b = False
                if checkpoint_scout_allowed and (manual_polymath_scout or enable_polymath_drive):
                    scout_attempted_b = True
                    _run_polymath_scout(
                        repo_root=_REPO_ROOT,
                        mailto=str(args.polymath_mailto).strip() or None,
                        tick_u64=int(tick_u64),
                    )
                if enable_polymath_drive and scout_attempted_b:
                    _run_polymath_void_to_goals(
                        repo_root=_REPO_ROOT,
                        run_dir=run_dir,
                        tick_u64=int(tick_u64),
                        invocation_label="checkpoint",
                        out_goal_queue_effective_path=void_goal_queue_effective_path,
                        max_goals=_VOID_TO_GOALS_MAX_GOALS_U64,
                    )
                if polymath_gate_failfast_enabled:
                    _route_polymath_progress_goal(
                        run_dir=run_dir,
                        repo_root=_REPO_ROOT,
                        state_dir=prev_state_dir or _state_dir(run_dir),
                        out_goal_queue_effective_path=void_goal_queue_effective_path,
                        tick_u64=int(tick_u64),
                    )
                if enable_llm_router and tick_u64 in {_POLYMATH_STALL_P_TICK_U64, _POLYMATH_STALL_Q_TICK_U64}:
                    router_result = omega_llm_router_v1.run_failsoft(
                        run_dir=run_dir,
                        tick_u64=int(tick_u64),
                        store_root=canonical_polymath_store,
                    )
                    should_halt = _apply_llm_router_result(
                        tick_u64=int(tick_u64),
                        goal_queue_path=void_goal_queue_effective_path,
                        router_result=router_result,
                        llm_router_invocations=llm_router_invocations,
                        llm_router_failures=llm_router_failures,
                        llm_router_required=llm_router_required,
                    )
                    if should_halt:
                        safe_halt = True
                        termination_reason = "LLM_ROUTER_FAIL"
                        break
                try:
                    _run_benchmark_summary(run_dir, runs_root)
                except Exception as exc:  # noqa: BLE001
                    verifier_failures.append(
                        {
                            "tick_u64": int(tick_u64),
                            "reason": "BENCHMARK_EXCEPTION",
                            "output": str(exc),
                        }
                    )
                    termination_reason = "BENCHMARK_EXCEPTION"
                    break
                if bool(int(args.enable_shadow_proposals)):
                    shadow_summary = _run_shadow_proposer(
                        series_prefix=series_prefix,
                        runs_root=runs_root,
                        workers=min(_SHADOW_WORKER_MAX, max(1, int(args.shadow_workers))),
                    )
                    if shadow_summary is not None:
                        shadow_summary_paths.append(shadow_summary.as_posix())
                summary_path = run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md"
                gate_status = load_gate_statuses(run_dir)
                if latest_gate_status:
                    for gate, prev_status in sorted(latest_gate_status.items()):
                        if gate not in required_pass_gates:
                            continue
                        next_status = gate_status.get(gate, "SKIP")
                        if prev_status == "PASS" and next_status == "FAIL":
                            gate_failures.append(
                                {
                                    "tick_u64": int(tick_u64),
                                    "reason": f"GATE_REGRESSION_{gate}",
                                    "before": prev_status,
                                    "after": next_status,
                                }
                            )
                            if halt_on_gate_failures:
                                gate_regression_or_failure_b = True
                                termination_reason = "GATE_REGRESSION"
                                safe_halt = True
                                break
                    if safe_halt:
                        if termination_reason == "DEADLINE_EXPIRED":
                            termination_reason = "SAFE_HALT"
                        break
                latest_gate_status = dict(gate_status)
                if _all_required_gates_pass(gate_status, required_gates=required_pass_gates):
                    head_now = _git_head_sha(_REPO_ROOT)
                    if head_now:
                        last_good_head_sha = head_now

                promotion_summary_tick_path = run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json"
                promotion_summary_tick = _load_json(promotion_summary_tick_path) if promotion_summary_tick_path.exists() else {}
                promoted_u64 = int(promotion_summary_tick.get("promoted_u64", 0))
                activation_successes = int(promotion_summary_tick.get("activation_success_u64", 0))
                runaway_blocked_pct = _extract_runaway_blocked_pct(summary_path)
                if float(runaway_blocked_pct) >= float(stall_watchdog_runaway_blocked_pct):
                    if prev_checkpoint_promoted_u64 is None or prev_checkpoint_activation_success_u64 is None:
                        stall_checkpoint_streak_u64 = 1
                    elif (
                        int(promoted_u64) == int(prev_checkpoint_promoted_u64)
                        and int(activation_successes) == int(prev_checkpoint_activation_success_u64)
                    ):
                        stall_checkpoint_streak_u64 += 1
                    else:
                        stall_checkpoint_streak_u64 = 1
                else:
                    stall_checkpoint_streak_u64 = 0
                prev_checkpoint_promoted_u64 = int(promoted_u64)
                prev_checkpoint_activation_success_u64 = int(activation_successes)
                if stall_checkpoint_streak_u64 >= stall_watchdog_checkpoints:
                    safe_halt = True
                    termination_reason = "STALL_NO_PROGRESS"
                    break

                gate_a = gate_status.get("A")
                gate_b = gate_status.get("B")
                gate_a_enforced_b = int(tick_u64) >= int(_GATE_A_ENFORCE_TICK_U64)
                gate_a_failed_b = bool(gate_a_enforced_b and gate_a == "FAIL")
                if gate_a_failed_b or gate_b == "FAIL":
                    gate_failures.append(
                        {
                            "tick_u64": int(tick_u64),
                            "gate_a": gate_a,
                            "gate_a_enforced_b": bool(gate_a_enforced_b),
                            "gate_b": gate_b,
                        }
                    )
                    if halt_on_gate_failures:
                        gate_regression_or_failure_b = True
                        termination_reason = "GATE_FAIL"
                        safe_halt = True
                        break
                if min_activation_successes > 0:
                    gate_d = gate_status.get("D")
                    if (
                        activation_successes >= min_activation_successes
                        and gate_a == "PASS"
                        and gate_b == "PASS"
                        and gate_d == "PASS"
                    ):
                        termination_reason = "MIN_ACTIVATION_SUCCESS_REACHED"
                        break
                bootstrap_reports_tick = _collect_polymath_bootstrap_reports(run_dir)
                bootstrapped_domains = sorted(
                    {
                        str(row.get("domain_id", "")).strip()
                        for row in bootstrap_reports_tick
                        if str(row.get("status", "")) == "BOOTSTRAPPED" and str(row.get("domain_id", "")).strip()
                    }
                )
                if (not promo_focus_unified_b) and max_new_domains > 0 and len(bootstrapped_domains) >= max_new_domains:
                    termination_reason = "MAX_NEW_DOMAINS_REACHED"
                    break
                if bootstrapped_domains and bootstrap_first_tick_u64 is None:
                    bootstrap_first_tick_u64 = int(tick_u64)
                if (
                    enable_polymath_drive
                    and profile == "refinery"
                    and bootstrap_first_tick_u64 is not None
                    and int(tick_u64) >= int(bootstrap_first_tick_u64) + int(conquer_budget_ticks)
                ):
                    termination_reason = "CONQUER_BUDGET_REACHED"
                    break
                if require_new_domain_registered and bootstrapped_domains:
                    gate_d = gate_status.get("D")
                    if gate_a == "PASS" and gate_b == "PASS" and gate_d == "PASS":
                        termination_reason = "NEW_DOMAIN_REGISTERED"
                        break
                checkpoint_snapshot = _collect_polymath_checkpoint_snapshot(run_dir=run_dir, repo_root=_REPO_ROOT)
                if polymath_gate_failfast_enabled and int(tick_u64) == int(polymath_stall_p_tick_u64):
                    stall_p_b = str(gate_status.get("P", "FAIL")).strip().upper() != "PASS"
                    if stall_p_b:
                        safe_halt = True
                        termination_reason = "POLYMATH_STALL_P"
                if polymath_gate_failfast_enabled and int(tick_u64) == int(polymath_stall_q_tick_u64):
                    stall_q_b = str(gate_status.get("Q", "FAIL")).strip().upper() != "PASS"
                    if stall_q_b:
                        safe_halt = True
                        termination_reason = "POLYMATH_STALL_Q"
                capability_usage_path = _write_capability_usage_artifact(run_dir=run_dir)
                diagnostic_packet_path = _write_diagnostic_packet(
                    run_dir=run_dir,
                    series_prefix=series_prefix,
                    meta_core_mode=str(args.meta_core_mode),
                    repo_root=_REPO_ROOT,
                    profile=profile,
                    tick_u64=int(tick_u64),
                    safe_halt=safe_halt,
                    termination_reason=termination_reason,
                    verifier_failures=verifier_failures,
                    required_pass_gates=required_pass_gates,
                    latest_gate_status=latest_gate_status,
                    llm_router_failures=llm_router_failures,
                    preflight_report=preflight_report,
                    checkpoint_kind="tick_checkpoint",
                    capability_usage_path=capability_usage_path,
                )
                replay_manifest_path = write_replay_manifest(
                    run_dir=run_dir,
                    series_prefix=series_prefix,
                    profile=profile,
                    meta_core_mode=str(args.meta_core_mode),
                    campaign_pack_path=campaign_pack,
                    capability_registry_path=capability_registry_path,
                    goal_queue_effective_path=goal_queue_effective_path,
                )
            if safe_halt:
                if termination_reason == "DEADLINE_EXPIRED":
                    termination_reason = "SAFE_HALT"
                break
    finally:
        if verifier_client is not None:
            verifier_client.close()

    if not preloop_abort_b:
        try:
            _run_benchmark_summary(run_dir, runs_root)
        except Exception as exc:  # noqa: BLE001
            verifier_failures.append(
                {
                    "tick_u64": int(tick_u64),
                    "reason": "BENCHMARK_EXCEPTION",
                    "output": str(exc),
                }
            )
            termination_reason = "BENCHMARK_EXCEPTION"
    latest_gate_status = load_gate_statuses(run_dir)
    capability_usage_path = _write_capability_usage_artifact(run_dir=run_dir)
    diagnostic_packet_path = _write_diagnostic_packet(
        run_dir=run_dir,
        series_prefix=series_prefix,
        meta_core_mode=str(args.meta_core_mode),
        repo_root=_REPO_ROOT,
        profile=profile,
        tick_u64=int(tick_u64),
        safe_halt=safe_halt,
        termination_reason=termination_reason,
        verifier_failures=verifier_failures,
        required_pass_gates=required_pass_gates,
        latest_gate_status=latest_gate_status,
        llm_router_failures=llm_router_failures,
        preflight_report=preflight_report,
        checkpoint_kind="final",
        capability_usage_path=capability_usage_path,
    )
    replay_manifest_path = write_replay_manifest(
        run_dir=run_dir,
        series_prefix=series_prefix,
        profile=profile,
        meta_core_mode=str(args.meta_core_mode),
        campaign_pack_path=campaign_pack,
        capability_registry_path=capability_registry_path,
        goal_queue_effective_path=goal_queue_effective_path,
    )
    ge_audit_report_json_path: Path | None = None
    ge_audit_report_md_path: Path | None = None
    ge_config_rel = "tools/genesis_engine/config/ge_config_v1.json"
    ge_config_path = (_REPO_ROOT / ge_config_rel).resolve()
    if enable_ge_sh1_optimizer and ge_audit:
        ge_audit_report_json_path, ge_audit_report_md_path = _run_ge_audit_report(
            runs_root=runs_root,
            run_dir=run_dir,
            ge_config_path=ge_config_path,
        )
    ge_sh1_counts = _count_ge_sh1_artifacts(run_dir)
    if enable_ge_sh1_optimizer and profile == "refinery":
        ge_dispatch_u64 = int(ge_sh1_counts.get("ge_dispatch_u64", 0))
        ge_ccap_receipts_u64 = int(ge_sh1_counts.get("ccap_receipts_u64", 0))
        if ge_dispatch_u64 == 0:
            termination_reason = "GE_NOT_DISPATCHED"
            safe_halt = True
        elif ge_ccap_receipts_u64 == 0:
            termination_reason = "GE_NO_CCAP_RECEIPTS"
            safe_halt = True

    if gate_regression_or_failure_b:
        rollback_target_sha = str(last_good_head_sha or baseline_head_sha).strip()
        rollback_applied_b = _git_hard_reset(_REPO_ROOT, rollback_target_sha)

    if int(args.push) != 0 and commit_rows:
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    promotion_summary_path = run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json"
    timings_agg_path = run_dir / "OMEGA_TIMINGS_AGG_v1.json"
    summary_md_path = run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md"
    promotion_summary = _load_json(promotion_summary_path) if promotion_summary_path.exists() else {}
    timings_agg = _load_json(timings_agg_path) if timings_agg_path.exists() else {}

    bundle_hashes_after = _bundle_hashes(meta_core_root)
    new_bundle_hashes = sorted(bundle_hashes_after - bundle_hashes_before)
    state_dir = _state_dir(run_dir)
    activated_capability_ids = sorted(_activated_capability_ids(state_dir))
    top_stage_contributors = _top_stage_contributors(timings_agg)
    polymath_bootstrap_reports = _collect_polymath_bootstrap_reports(run_dir)
    polymath_conquer_reports = _collect_polymath_conquer_reports(run_dir)

    livewire_summary_path = _write_livewire_git_summary(run_dir=run_dir, branch=branch, commit_rows=commit_rows)
    morning_diff_path = _write_morning_diff(
        run_dir=run_dir,
        branch=branch,
        commit_rows=commit_rows,
        promotion_summary=promotion_summary,
        refinery_summary=refinery_proposer_summary,
        conquer_reports=polymath_conquer_reports,
    )
    shadow_summary_md_path = _write_shadow_proposals_summary_md(run_dir)
    core_opt_summary_md_path = _write_core_opt_reports_summary_md(run_dir)
    polymath_void_report_md_path = _write_polymath_void_report_md(run_dir=run_dir, repo_root=_REPO_ROOT)
    void_to_goals_report_json_path = run_dir / "OMEGA_VOID_TO_GOALS_REPORT_v1.json"
    void_to_goals_report = _load_json(void_to_goals_report_json_path) if void_to_goals_report_json_path.exists() else {}
    if isinstance(void_to_goals_report, dict) and isinstance(void_to_goals_report.get("invocations"), list):
        void_to_goals_invocations_u64 = int(len(void_to_goals_report.get("invocations", [])))
    else:
        void_to_goals_invocations_u64 = 0
    if isinstance(void_to_goals_report, dict):
        void_to_goals_injected_total_u64 = int(void_to_goals_report.get("goals_injected_total_u64", 0))
    else:
        void_to_goals_injected_total_u64 = 0
    skill_manifest_json_path, skill_manifest_worktree_json_path = _write_skill_manifest_artifacts(
        run_dir=run_dir,
        repo_root=_REPO_ROOT,
    )
    polymath_progress = _collect_polymath_progress(run_dir)
    new_domain_report_md_path = _write_new_domain_report_md(run_dir=run_dir, bootstrap_reports=polymath_bootstrap_reports)
    domain_conquer_report_md_path = _write_domain_conquer_report_md(run_dir=run_dir, conquer_reports=polymath_conquer_reports)
    conquer_cache_hit_reports_u64 = sum(1 for row in polymath_conquer_reports if bool(row.get("refinery_cache_hit_b", False)))
    conquer_cache_hit_rate_q32 = (
        int((int(conquer_cache_hit_reports_u64) * (1 << 32)) // max(1, len(polymath_conquer_reports)))
        if polymath_conquer_reports
        else 0
    )
    refinery_summary_path = (
        str(refinery_proposer_summary_path)
        if str(refinery_proposer_summary_path).strip()
        else str((refinery_proposer_summary or {}).get("_summary_path", ""))
    )
    refinery_proposals_generated_u64 = int((refinery_proposer_summary or {}).get("proposals_generated_u64", 0))
    refinery_top_domains = (
        list((refinery_proposer_summary or {}).get("top_domains_expected_val_delta", []))
        if isinstance((refinery_proposer_summary or {}).get("top_domains_expected_val_delta", []), list)
        else []
    )
    bootstrapped_domain_ids = sorted(
        {
            str(row.get("domain_id", "")).strip()
            for row in polymath_bootstrap_reports
            if str(row.get("status", "")) == "BOOTSTRAPPED" and str(row.get("domain_id", "")).strip()
        }
    )
    if require_new_domain_registered and not bootstrapped_domain_ids:
        gate_failures.append(
            {
                "tick_u64": int(tick_u64),
                "reason": "REQUIRE_NEW_DOMAIN_REGISTERED_UNMET",
            }
        )

    elapsed_seconds = max(0.001, float(time.monotonic() - run_started_monotonic))
    promoted_u64 = int(promotion_summary.get("promoted_u64", 0))
    activation_success_u64 = int(promotion_summary.get("activation_success_u64", 0))
    rolling_summary_path = run_dir / "OMEGA_OVERNIGHT_ROLLING_SUMMARY_v1.json"
    rolling_summary = _load_json(rolling_summary_path) if rolling_summary_path.exists() else {}
    scorecard_snapshot = rolling_summary.get("scorecard_snapshot") if isinstance(rolling_summary, dict) else {}
    run_scorecard_path = run_dir / "OMEGA_RUN_SCORECARD_v1.json"
    run_scorecard = _load_json(run_scorecard_path) if run_scorecard_path.exists() else {}
    median_stps_non_noop_q32 = 0
    if isinstance(scorecard_snapshot, dict):
        median_stps_non_noop_q32 = int(scorecard_snapshot.get("median_stps_non_noop_q32", 0))
    if median_stps_non_noop_q32 <= 0 and isinstance(run_scorecard, dict):
        median_stps_non_noop_q32 = int(run_scorecard.get("median_stps_non_noop_q32", 0))

    perf_rates = {
        "elapsed_seconds": float(elapsed_seconds),
        "promotions_per_min_wall": float(promoted_u64 * 60.0 / elapsed_seconds),
        "activation_successes_per_min_wall": float(activation_success_u64 * 60.0 / elapsed_seconds),
        "median_stps_non_noop_q32": int(median_stps_non_noop_q32),
        "median_stps_non_noop_float": float(_q32_to_float(median_stps_non_noop_q32)),
        "non_noop_ticks_per_min_tick_based": float(timings_agg.get("non_noop_ticks_per_min", 0.0)),
        "promotion_ticks_per_min_tick_based": float(timings_agg.get("promotion_ticks_per_min", 0.0)),
    }

    ge_sh1_report: dict[str, Any] = {
        "enabled": bool(enable_ge_sh1_optimizer),
        "ge_state_root": ge_state_root.as_posix(),
        "ge_config_path": ge_config_rel,
        "ge_dispatch_u64": int(ge_sh1_counts.get("ge_dispatch_u64", 0)),
        "ccap_receipts_u64": int(ge_sh1_counts.get("ccap_receipts_u64", 0)),
        "audit_report_json": ge_audit_report_json_path.as_posix() if ge_audit_report_json_path is not None else "",
        "audit_report_md": ge_audit_report_md_path.as_posix() if ge_audit_report_md_path is not None else "",
    }
    llm_router_plan_path = run_dir / "OMEGA_LLM_ROUTER_PLAN_v1.json"
    llm_router_trace_path = run_dir / "OMEGA_LLM_TOOL_TRACE_v1.jsonl"

    report_json = {
        "schema_version": "OMEGA_OVERNIGHT_REPORT_v1",
        "series_prefix": series_prefix,
        "run_dir": run_dir.as_posix(),
        "campaign_pack": campaign_pack.as_posix(),
        "meta_core_mode": str(args.meta_core_mode),
        "profile": str(profile),
        "promo_focus_enabled_b": bool(promo_focus),
        "required_pass_gates": [str(gate) for gate in required_pass_gates],
        "meta_core_root": meta_core_root.as_posix(),
        "livewire_branch": branch,
        "livewire_worktree_dir": _REPO_ROOT.as_posix(),
        "deadline_utc": deadline.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "ticks_completed_u64": int(tick_u64),
        "safe_halt": bool(safe_halt),
        "termination_reason": str(termination_reason),
        "verifier_failures": verifier_failures,
        "gate_failures": gate_failures,
        "livewire_commits_u64": int(len(commit_rows)),
        "livewire_commit_shas": [str(row.get("commit_sha", "")) for row in commit_rows],
        "promotions_u64": int(promoted_u64),
        "activation_successes_u64": int(activation_success_u64),
        "unique_capability_ids_activated_u64": int(len(activated_capability_ids)),
        "unique_capability_ids_activated": activated_capability_ids,
        "unique_promotions_u64": int(promotion_summary.get("unique_promotions_u64", 0)),
        "unique_activations_applied_u64": int(promotion_summary.get("unique_activations_applied_u64", 0)),
        "top_activation_failure_reasons": promotion_summary.get("activation_failure_reason_counts", []),
        "top_stage_time_contributors": top_stage_contributors,
        "new_bundle_hashes": new_bundle_hashes,
        "latest_gate_status": latest_gate_status,
        "perf_rates": perf_rates,
        "auto_rollback": {
            "baseline_head_sha": str(baseline_head_sha),
            "last_good_head_sha": str(last_good_head_sha),
            "rollback_applied_b": bool(rollback_applied_b),
            "rollback_target_sha": str(rollback_target_sha),
            "triggered_by_gate_regression_or_failure_b": bool(gate_regression_or_failure_b),
        },
        "shadow_summary_paths": shadow_summary_paths,
        "llm_router": {
            "enabled": bool(enable_llm_router),
            "required_b": bool(llm_router_required),
            "backend": str(llm_router_backend),
            "invocations_u64": int(len(llm_router_invocations)),
            "failures_u64": int(len(llm_router_failures)),
            "invocations": llm_router_invocations,
            "failures": llm_router_failures,
            "plan_path": llm_router_plan_path.as_posix() if llm_router_plan_path.exists() else "",
            "tool_trace_path": llm_router_trace_path.as_posix() if llm_router_trace_path.exists() else "",
        },
        "polymath": {
            "overlay_enablement": {
                "polymath_enabled": bool(polymath_enablement.get("polymath_enabled", False)),
                "scout_enabled": bool(polymath_enablement.get("scout_enabled", False)),
                "bootstrap_enabled": bool(polymath_enablement.get("bootstrap_enabled", False)),
                "conquer_enabled": bool(polymath_enablement.get("conquer_enabled", False)),
            },
            "failfast_enabled_b": bool(polymath_gate_failfast_enabled),
            "enable_polymath_drive": bool(enable_polymath_drive),
            "enable_polymath_scout": bool(enable_polymath_scout),
            "enable_polymath_bootstrap": bool(enable_polymath_bootstrap),
            "polymath_scout_every_ticks_u64": int(benchmark_every_ticks),
            "polymath_conquer_budget_ticks_u64": int(conquer_budget_ticks),
            "max_new_domains_u64": int(max_new_domains),
            "require_new_domain_registered": bool(require_new_domain_registered),
            "stall_watchdog_checkpoints_u64": int(stall_watchdog_checkpoints),
            "stall_watchdog_runaway_blocked_pct_f64": float(stall_watchdog_runaway_blocked_pct),
            "bootstrapped_domains_u64": int(len(bootstrapped_domain_ids)),
            "bootstrapped_domain_ids": bootstrapped_domain_ids,
            "conquer_reports_u64": int(len(polymath_conquer_reports)),
            "conquer_cache_hit_reports_u64": int(conquer_cache_hit_reports_u64),
            "conquer_cache_hit_rate_q32": int(conquer_cache_hit_rate_q32),
            "seed_flagships_summary_path": str(seed_flagships_summary_path),
            "refinery_proposer": {
                "enabled": bool(enable_polymath_refinery_proposer),
                "workers_u64": int(polymath_refinery_workers),
                "max_domains_u64": int(polymath_refinery_max_domains),
                "summary_path": refinery_summary_path,
                "proposals_generated_u64": int(refinery_proposals_generated_u64),
                "top_domains_expected_val_delta": refinery_top_domains,
            },
            "progress": polymath_progress,
            "void_to_goals": {
                "report_path": void_to_goals_report_json_path.as_posix()
                if void_to_goals_report_json_path.exists()
                else "",
                "invocations_u64": int(void_to_goals_invocations_u64),
                "goals_injected_total_u64": int(void_to_goals_injected_total_u64),
            },
        },
        "artifacts": {
            "benchmark_summary_md": summary_md_path.as_posix(),
            "benchmark_gates_json": (run_dir / "OMEGA_BENCHMARK_GATES_v1.json").as_posix(),
            "gate_proof_json": (run_dir / "OMEGA_GATE_PROOF_v1.json").as_posix(),
            "diagnostic_packet_json": diagnostic_packet_path.as_posix() if diagnostic_packet_path is not None else "",
            "preflight_report_json": preflight_report_path.as_posix(),
            "replay_manifest_json": replay_manifest_path.as_posix(),
            "capability_usage_json": capability_usage_path.as_posix() if capability_usage_path is not None else "",
            "timings_agg_json": timings_agg_path.as_posix(),
            "promotion_summary_json": promotion_summary_path.as_posix(),
            "run_scorecard_json": (run_dir / "OMEGA_RUN_SCORECARD_v1.json").as_posix(),
            "noop_counts_json": (run_dir / "OMEGA_NOOP_REASON_COUNTS_v1.json").as_posix(),
            "livewire_git_summary_json": livewire_summary_path.as_posix(),
            "morning_diff_md": morning_diff_path.as_posix(),
            "shadow_proposals_summary_md": shadow_summary_md_path.as_posix(),
            "core_opt_reports_summary_md": core_opt_summary_md_path.as_posix(),
            "polymath_void_report_md": polymath_void_report_md_path.as_posix(),
            "void_to_goals_report_json": void_to_goals_report_json_path.as_posix()
            if void_to_goals_report_json_path.exists()
            else "",
            "new_domain_report_md": new_domain_report_md_path.as_posix(),
            "domain_conquer_report_md": domain_conquer_report_md_path.as_posix(),
            "skill_manifest_json": skill_manifest_json_path.as_posix(),
            "skill_manifest_worktree_json": skill_manifest_worktree_json_path.as_posix(),
            "llm_router_plan_json": llm_router_plan_path.as_posix() if llm_router_plan_path.exists() else "",
            "llm_router_tool_trace_jsonl": llm_router_trace_path.as_posix() if llm_router_trace_path.exists() else "",
        },
    }
    report_json["ge_sh1"] = ge_sh1_report
    artifacts = report_json.get("artifacts")
    if isinstance(artifacts, dict):
        artifacts["ge_audit_report_json"] = str(ge_sh1_report.get("audit_report_json", ""))
        artifacts["ge_audit_report_md"] = str(ge_sh1_report.get("audit_report_md", ""))
    report_json_path = run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json"
    _write_json(report_json_path, report_json)

    md_lines = [
        f"# OMEGA Overnight Report ({series_prefix})",
        "",
        f"- Run dir: `{run_dir.as_posix()}`",
        f"- Live-wire branch: `{branch}`",
        f"- Live-wire worktree: `{_REPO_ROOT.as_posix()}`",
        f"- Meta-core mode: `{str(args.meta_core_mode)}`",
        f"- Profile: `{profile}` required gates={','.join(required_pass_gates)}",
        f"- Promo focus: `{bool(promo_focus)}`",
        f"- Meta-core root: `{meta_core_root.as_posix()}`",
        f"- Ticks completed: **{int(tick_u64)}**",
        f"- Termination reason: `{termination_reason}`",
        f"- Promotions: **{int(report_json['promotions_u64'])}**",
        f"- Activation successes: **{int(report_json['activation_successes_u64'])}**",
        (
            "- Wall rates: "
            f"promotions/min={float(perf_rates.get('promotions_per_min_wall', 0.0)):.4f} "
            f"activations/min={float(perf_rates.get('activation_successes_per_min_wall', 0.0)):.4f}"
        ),
        (
            "- STPS median (non-NOOP): "
            f"q32={int(perf_rates.get('median_stps_non_noop_q32', 0))} "
            f"float={float(perf_rates.get('median_stps_non_noop_float', 0.0)):.6f}"
        ),
        f"- Commits created: **{int(len(commit_rows))}**",
        f"- New domains bootstrapped: **{int(len(bootstrapped_domain_ids))}**",
        (
            "- Auto rollback: "
            f"applied={bool(rollback_applied_b)} "
            f"target=`{str(rollback_target_sha)}` "
            f"baseline=`{str(baseline_head_sha)}` "
            f"last_good=`{str(last_good_head_sha)}`"
        ),
        (
            "- Polymath progress: "
            f"domains_delta={int(polymath_progress.get('domains_bootstrapped_delta_u64', 0))} "
            f"top_void_delta_q32={int(polymath_progress.get('top_void_score_delta_q32', 0))} "
            f"coverage_delta_q32={int(polymath_progress.get('coverage_ratio_delta_q32', 0))}"
        ),
        (
            "- Polymath void->goals: "
            f"invocations={int(void_to_goals_invocations_u64)} "
            f"injected_total={int(void_to_goals_injected_total_u64)}"
        ),
        (
            "- Polymath refinery: "
            f"enabled={bool(enable_polymath_refinery_proposer)} "
            f"proposals_generated={int(refinery_proposals_generated_u64)} "
            f"conquer_cache_hit_rate_q32={int(conquer_cache_hit_rate_q32)}"
        ),
        (
            "- GE SH-1 optimizer: "
            f"enabled={bool(enable_ge_sh1_optimizer)} "
            f"max_ccaps={int(ge_max_ccaps)} "
            f"model_id={ge_model_id} "
            f"audit={bool(ge_audit)} "
            f"dispatches={int(ge_sh1_counts.get('ge_dispatch_u64', 0))} "
            f"ccap_receipts={int(ge_sh1_counts.get('ccap_receipts_u64', 0))}"
        ),
        (
            "- LLM router: "
            f"enabled={bool(enable_llm_router)} "
            f"required={bool(llm_router_required)} "
            f"backend={str(llm_router_backend)} "
            f"invocations={int(len(llm_router_invocations))} "
            f"failures={int(len(llm_router_failures))}"
        ),
        "",
        "## Top Bottlenecks",
    ]
    if top_stage_contributors:
        for row in top_stage_contributors:
            md_lines.append(f"- `{row['stage']}` mean_ns={float(row['mean_ns']):.2f}")
    else:
        md_lines.append("- (none)")
    md_lines.extend(["", "## Polymath Refinery"])
    md_lines.append(
        f"- Seed flagships summary path: `{seed_flagships_summary_path}`"
        if seed_flagships_summary_path
        else "- Seed flagships summary path: (none)"
    )
    md_lines.append(f"- Proposer summary path: `{refinery_summary_path}`" if refinery_summary_path else "- Proposer summary path: (none)")
    md_lines.append(f"- Proposals generated: **{int(refinery_proposals_generated_u64)}**")
    md_lines.append(f"- Conquer cache-hit reports: **{int(conquer_cache_hit_reports_u64)} / {int(len(polymath_conquer_reports))}**")
    if refinery_top_domains:
        for row in refinery_top_domains[:10]:
            if not isinstance(row, dict):
                continue
            md_lines.append(
                "- "
                f"`{row.get('domain_id', '')}` "
                f"delta_q32={int(row.get('expected_val_delta_q32', 0))} "
                f"proposal_id={row.get('proposal_id', '')}"
            )
    else:
        md_lines.append("- Top domains by expected val delta: (none)")
    md_lines.extend(["", "## GE SH-1"])
    if not bool(ge_sh1_report.get("enabled", False)):
        md_lines.append("- GE audit report: (disabled or unavailable)")
    else:
        md_lines.append(f"- GE config path: `{ge_sh1_report['ge_config_path']}`")
        md_lines.append(f"- GE state root: `{ge_sh1_report['ge_state_root']}`")
        md_lines.append(f"- GE dispatches: **{int(ge_sh1_report.get('ge_dispatch_u64', 0))}**")
        md_lines.append(f"- GE CCAP receipts: **{int(ge_sh1_report.get('ccap_receipts_u64', 0))}**")
        md_lines.append(
            f"- GE audit JSON: `{ge_sh1_report['audit_report_json']}`"
            if str(ge_sh1_report.get("audit_report_json", "")).strip()
            else "- GE audit JSON: (disabled or unavailable)"
        )
        md_lines.append(
            f"- GE audit MD: `{ge_sh1_report['audit_report_md']}`"
            if str(ge_sh1_report.get("audit_report_md", "")).strip()
            else "- GE audit MD: (disabled or unavailable)"
        )
    md_lines.extend(
        [
            "",
            "## New Bundle Hashes",
        ]
    )
    if new_bundle_hashes:
        for bundle_hash in new_bundle_hashes:
            md_lines.append(f"- `{bundle_hash}`")
    else:
        md_lines.append("- (none)")
    md_lines.extend(
        [
            "",
            "## Artifacts",
            f"- `{report_json_path.as_posix()}`",
            f"- `{preflight_report_path.as_posix()}`",
            f"- `{replay_manifest_path.as_posix()}`",
            f"- `{capability_usage_path.as_posix()}`" if capability_usage_path is not None else "- (capability usage report not emitted)",
            f"- `{summary_md_path.as_posix()}`",
            f"- `{(run_dir / 'OMEGA_GATE_PROOF_v1.json').as_posix()}`",
            f"- `{diagnostic_packet_path.as_posix()}`" if diagnostic_packet_path is not None else "- (diagnostic packet not emitted)",
            f"- `{timings_agg_path.as_posix()}`",
            f"- `{promotion_summary_path.as_posix()}`",
            f"- `{livewire_summary_path.as_posix()}`",
            f"- `{morning_diff_path.as_posix()}`",
            f"- `{shadow_summary_md_path.as_posix()}`",
            f"- `{core_opt_summary_md_path.as_posix()}`",
            f"- `{polymath_void_report_md_path.as_posix()}`",
            f"- `{void_to_goals_report_json_path.as_posix()}`" if void_to_goals_report_json_path.exists() else "- (void-to-goals report not emitted)",
            f"- `{new_domain_report_md_path.as_posix()}`",
            f"- `{domain_conquer_report_md_path.as_posix()}`",
            f"- `{skill_manifest_json_path.as_posix()}`",
            f"- `{skill_manifest_worktree_json_path.as_posix()}`",
            f"- `{llm_router_plan_path.as_posix()}`" if llm_router_plan_path.exists() else "- (llm router plan not emitted)",
            f"- `{llm_router_trace_path.as_posix()}`" if llm_router_trace_path.exists() else "- (llm router trace not emitted)",
        ]
    )
    if str(ge_sh1_report.get("audit_report_json", "")).strip():
        md_lines.append(f"- `{ge_sh1_report['audit_report_json']}`")
    if str(ge_sh1_report.get("audit_report_md", "")).strip():
        md_lines.append(f"- `{ge_sh1_report['audit_report_md']}`")
    _write_md(run_dir / "OMEGA_OVERNIGHT_REPORT.md", "\n".join(md_lines) + "\n")

    if prev_meta_core_root is None:
        os.environ.pop("OMEGA_META_CORE_ROOT", None)
    else:
        os.environ["OMEGA_META_CORE_ROOT"] = prev_meta_core_root
    if prev_meta_core_mode is None:
        os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
    else:
        os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_meta_core_mode
    if prev_allow_sim is None:
        os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
    else:
        os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow_sim
    if prev_polymath_store_root is None:
        os.environ.pop("OMEGA_POLYMATH_STORE_ROOT", None)
    else:
        os.environ["OMEGA_POLYMATH_STORE_ROOT"] = prev_polymath_store_root
    if prev_ge_state_root is None:
        os.environ.pop("OMEGA_GE_STATE_ROOT", None)
    else:
        os.environ["OMEGA_GE_STATE_ROOT"] = prev_ge_state_root
    if prev_promo_focus is None:
        os.environ.pop("OMEGA_PROMO_FOCUS", None)
    else:
        os.environ["OMEGA_PROMO_FOCUS"] = prev_promo_focus

    print(report_json_path.as_posix())
    print((run_dir / "OMEGA_OVERNIGHT_REPORT.md").as_posix())


if __name__ == "__main__":
    main()
