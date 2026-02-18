"""Phase 3 CCAP market-rules self-mutation campaign (v1).

Targets `orchestrator/omega_bid_market_v1.py` and requires determinism/soak + v19 replay VALID
before emitting a CCAP bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_no_absolute_paths
from cdel.v19_0 import verify_rsi_omega_daemon_v1 as v19_replay_verifier
from orchestrator.llm_backend import get_backend

_PACK_SCHEMA = "rsi_market_rules_mutator_pack_v1"
_BENCH_PACK_DEFAULT = "campaigns/rsi_omega_daemon_v19_0_phase3_market_toy/rsi_omega_daemon_pack_v1.json"


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _parse_patch_touched_paths(patch_bytes: bytes) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("+++ "):
            continue
        if line == "+++ /dev/null":
            continue
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :]
        rel = rel.split("\t", 1)[0].strip()
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1]
        rel = rel.replace("\\", "/").lstrip("./")
        if rel and rel not in seen:
            touched.append(rel)
            seen.add(rel)
    return touched


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    return float(statistics.median(xs))


def _fmt_f64(value: float) -> str:
    return format(float(value), ".12f")


def _latest_glob(root: Path, pattern: str) -> Path:
    rows = sorted(root.glob(pattern), key=lambda p: p.as_posix())
    if not rows:
        raise RuntimeError("MISSING_STATE_INPUT")
    return rows[-1]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _git(repo_root: Path, args: list[str]) -> None:
    run = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(msg or "git failed")


def _first_build_recipe_id(repo_root: Path) -> str:
    payload = load_canon_dict(repo_root / "authority" / "build_recipes" / "build_recipes_v1.json", reason="MISSING_STATE_INPUT")
    recipes = payload.get("recipes")
    if payload.get("schema_version") != "build_recipes_v1" or not isinstance(recipes, list) or not recipes:
        fail("SCHEMA_FAIL")
    ids = sorted(str(row.get("recipe_id", "")).strip() for row in recipes if isinstance(row, dict))
    ids = [row for row in ids if row.startswith("sha256:")]
    if not ids:
        fail("SCHEMA_FAIL")
    return ids[0]


def _run_daemon_loop(
    *,
    repo_root: Path,
    campaign_pack_rel: str,
    out_root: Path,
    tick_start_u64: int,
    ticks_u64: int,
    run_seed_u64: int,
    deterministic_timing: bool,
) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_pattern = str((out_root / "tick_{tick}").resolve())
    env = dict(os.environ)
    env["OMEGA_RUN_SEED_U64"] = str(int(run_seed_u64))
    env["OMEGA_V19_DETERMINISTIC_TIMING"] = ("1" if deterministic_timing else "0")
    env["OMEGA_PHASE3_MUTATION_SIGNAL"] = "0"
    env["OMEGA_DEV_DEATH_INJECTION_OK"] = "0"
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "Extension-1" / "agi-orchestrator") if host_root else "Extension-1/agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack_rel),
        "--out_dir",
        out_pattern,
        "--mode",
        "loop",
        "--tick_u64",
        str(int(tick_start_u64)),
        "--ticks",
        str(int(ticks_u64)),
    ]
    run = subprocess.run(cmd, cwd=str(repo_root), env=env, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        detail = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(f"DAEMON_RUN_FAILED:{detail[:4000]}")
    last_tick = int(tick_start_u64) + int(ticks_u64) - 1
    last_out = out_root / f"tick_{last_tick}"
    state_dir = last_out / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")
    return state_dir


def _run_daemon_loop_measured(
    *,
    repo_root: Path,
    campaign_pack_rel: str,
    out_root: Path,
    tick_start_u64: int,
    ticks_u64: int,
    run_seed_u64: int,
    deterministic_timing: bool,
    sample_period_s: float = 0.25,
) -> tuple[Path, dict[str, Any]]:
    out_root.mkdir(parents=True, exist_ok=True)
    out_pattern = str((out_root / "tick_{tick}").resolve())
    env = dict(os.environ)
    env["OMEGA_RUN_SEED_U64"] = str(int(run_seed_u64))
    env["OMEGA_V19_DETERMINISTIC_TIMING"] = ("1" if deterministic_timing else "0")
    env["OMEGA_PHASE3_MUTATION_SIGNAL"] = "0"
    env["OMEGA_DEV_DEATH_INJECTION_OK"] = "0"
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "Extension-1" / "agi-orchestrator") if host_root else "Extension-1/agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack_rel),
        "--out_dir",
        out_pattern,
        "--mode",
        "loop",
        "--tick_u64",
        str(int(tick_start_u64)),
        "--ticks",
        str(int(ticks_u64)),
    ]

    stdout_path = out_root / "stdout.log"
    stderr_path = out_root / "stderr.log"

    def _rss_kb(pid: int) -> int | None:
        run = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            return None
        try:
            return int(str(run.stdout or "").strip().split()[0])
        except Exception:
            return None

    def _fd_count(pid: int) -> int | None:
        if subprocess.run(["command", "-v", "lsof"], capture_output=True, text=True).returncode != 0:
            return None
        run = subprocess.run(["lsof", "-p", str(pid)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            return None
        lines = (run.stdout or "").splitlines()
        return max(0, len(lines) - 1) if lines else 0

    with stdout_path.open("w", encoding="utf-8") as out_h, stderr_path.open("w", encoding="utf-8") as err_h:
        proc = subprocess.Popen(cmd, cwd=str(repo_root), env=env, stdout=out_h, stderr=err_h)
        pid = int(proc.pid)
        rss_start = _rss_kb(pid)
        fd_start = _fd_count(pid)
        rss_max = rss_start
        fd_max = fd_start
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            rss_now = _rss_kb(pid)
            fd_now = _fd_count(pid)
            if rss_now is not None:
                rss_max = rss_now if rss_max is None else max(rss_max, rss_now)
            if fd_now is not None:
                fd_max = fd_now if fd_max is None else max(fd_max, fd_now)
            time.sleep(max(0.05, float(sample_period_s)))
        rc = int(proc.returncode or 0)

    if rc != 0:
        raise RuntimeError("DAEMON_RUN_FAILED")

    last_tick = int(tick_start_u64) + int(ticks_u64) - 1
    last_out = out_root / f"tick_{last_tick}"
    state_dir = last_out / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")

    rss_delta_bytes = None
    if rss_start is not None and rss_max is not None:
        rss_delta_bytes = max(0, int(rss_max - rss_start)) * 1024
    fd_delta = None
    if fd_start is not None and fd_max is not None:
        fd_delta = max(0, int(fd_max - fd_start))
    return state_dir, {
        "return_code": rc,
        "rss_start_kb": rss_start,
        "rss_max_kb": rss_max,
        "rss_delta_bytes_u64": rss_delta_bytes,
        "fd_start_u64": fd_start,
        "fd_max_u64": fd_max,
        "fd_delta_u64": fd_delta,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _score_metric_q32(state_dir: Path, *, metric: str) -> int:
    if metric != "median_stps_non_noop_q32":
        raise RuntimeError("SCHEMA_FAIL")
    score_path = _latest_glob(state_dir / "perf", "sha256_*.omega_run_scorecard_v1.json")
    score = _load_json(score_path)
    return max(0, int(score.get("median_stps_non_noop_q32", 0)))


def _disk_usage_mb(root: Path) -> int:
    total = 0
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            continue
        if path.is_file():
            try:
                total += int(path.stat().st_size)
            except OSError:
                continue
    return int((total + (1024 * 1024) - 1) // (1024 * 1024))


def _structural_validate(
    *,
    candidate_worktree: Path,
    bench_pack_rel: str,
    soak_ticks_u64: int,
    seed_u64: int,
    max_disk_mb_u64: int,
    max_fd_delta_u64: int,
    max_rss_delta_bytes_u64: int,
    require_tree_hash_match_b: bool,
    out_dir: Path,
) -> tuple[dict[str, Any], Path]:
    from cdel.v18_0.omega_common_v1 import tree_hash

    run_root = out_dir / "structural"
    run_a, meas_a = _run_daemon_loop_measured(
        repo_root=candidate_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=run_root / "run_a",
        tick_start_u64=1,
        ticks_u64=soak_ticks_u64,
        run_seed_u64=seed_u64,
        deterministic_timing=True,
    )
    run_b, meas_b = _run_daemon_loop_measured(
        repo_root=candidate_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=run_root / "run_b",
        tick_start_u64=1,
        ticks_u64=soak_ticks_u64,
        run_seed_u64=seed_u64,
        deterministic_timing=True,
    )
    hash_a = tree_hash(run_a)
    hash_b = tree_hash(run_b)
    disk_a = _disk_usage_mb(run_a)
    disk_b = _disk_usage_mb(run_b)
    if disk_a > int(max_disk_mb_u64) or disk_b > int(max_disk_mb_u64):
        raise RuntimeError("STRUCTURAL_DISK_CAP_EXCEEDED")
    if require_tree_hash_match_b and hash_a != hash_b:
        raise RuntimeError("STRUCTURAL_TREE_HASH_MISMATCH")

    fd_delta_a = meas_a.get("fd_delta_u64")
    fd_delta_b = meas_b.get("fd_delta_u64")
    rss_delta_a = meas_a.get("rss_delta_bytes_u64")
    rss_delta_b = meas_b.get("rss_delta_bytes_u64")
    if fd_delta_a is None or fd_delta_b is None or rss_delta_a is None or rss_delta_b is None:
        raise RuntimeError("STRUCTURAL_MEASUREMENT_MISSING")
    if int(fd_delta_a) > int(max_fd_delta_u64) or int(fd_delta_b) > int(max_fd_delta_u64):
        raise RuntimeError("STRUCTURAL_FD_DELTA_EXCEEDED")
    if int(rss_delta_a) > int(max_rss_delta_bytes_u64) or int(rss_delta_b) > int(max_rss_delta_bytes_u64):
        raise RuntimeError("STRUCTURAL_RSS_DELTA_EXCEEDED")

    receipt = {
        "schema_version": "market_rules_mutator_structural_receipt_v1",
        "soak_ticks_u64": int(soak_ticks_u64),
        "seed_u64": int(seed_u64),
        "max_fd_delta_u64": int(max_fd_delta_u64),
        "max_rss_delta_bytes_u64": int(max_rss_delta_bytes_u64),
        "tree_hash_a": str(hash_a),
        "tree_hash_b": str(hash_b),
        "disk_mb_a_u64": int(disk_a),
        "disk_mb_b_u64": int(disk_b),
        "measured_a": dict(meas_a),
        "measured_b": dict(meas_b),
    }
    return receipt, run_a


def _emit_ccap(*, repo_root: Path, out_dir: Path, patch_bytes: bytes) -> tuple[str, str, str, str]:
    out_dir = out_dir.resolve()
    pins = load_authority_pins(repo_root)
    base_tree_id = compute_repo_base_tree_id(repo_root)
    build_recipe_id = _first_build_recipe_id(repo_root)

    patch_hex = hashlib.sha256(patch_bytes).hexdigest()
    patch_blob_id = f"sha256:{patch_hex}"
    patch_relpath = f"ccap/blobs/sha256_{patch_hex}.patch"

    ccap: dict[str, Any] = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": str(pins["active_dsbx_profile_ids"][0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(pins["active_op_pool_ids"][0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {"build_recipe_id": build_recipe_id, "build_targets": [], "artifact_bindings": {}},
        "eval": {
            "stages": [{"stage_name": "REALIZE"}, {"stage_name": "SCORE"}, {"stage_name": "FINAL_AUDIT"}],
            "final_suite_id": "sha256:" + ("1" * 64),
        },
        "budgets": {
            "cpu_ms_max": 180_000,
            "wall_ms_max": 180_000,
            "mem_mb_max": 4096,
            "disk_mb_max": 8192,
            "fds_max": 512,
            "procs_max": 256,
            "threads_max": 512,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap)
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"

    (out_dir / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)
    (out_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (out_dir / "ccap").mkdir(parents=True, exist_ok=True)

    (out_dir / patch_relpath).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / patch_relpath).write_bytes(patch_bytes)
    write_canon_json(out_dir / ccap_relpath, ccap)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_relpath,
        "patch_relpath": patch_relpath,
        "touched_paths": [ccap_relpath, patch_relpath],
        "activation_key": ccap_id,
    }
    require_no_absolute_paths(bundle)
    bundle_hash = canon_hash_obj(bundle)
    write_canon_json(
        out_dir / "promotion" / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json",
        bundle,
    )
    return ccap_id, ccap_relpath, patch_relpath, bundle_hash


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = load_canon_dict(campaign_pack, reason="SCHEMA_FAIL")
    if str(pack.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    target_relpath = str(pack.get("target_relpath", "")).strip().replace("\\", "/").lstrip("./")
    if not target_relpath or Path(target_relpath).is_absolute() or ".." in Path(target_relpath).parts:
        fail("SCHEMA_FAIL")
    repo_root = Path.cwd().resolve()
    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        fail("MISSING_STATE_INPUT")
    target_text = target_path.read_text(encoding="utf-8")

    tick_u64 = max(0, int(os.environ.get("OMEGA_TICK_U64", "0") or "0"))
    run_seed_u64 = max(0, int(os.environ.get("OMEGA_RUN_SEED_U64", "0") or "0"))

    resource_caps = pack.get("resource_caps") if isinstance(pack.get("resource_caps"), dict) else {}
    max_patch_bytes_u64 = max(1, int(resource_caps.get("max_patch_bytes_u64", 200_000)))

    benchmark = pack.get("benchmark") if isinstance(pack.get("benchmark"), dict) else {}
    ticks_per_trial_u64 = max(1, int(benchmark.get("ticks_per_trial_u64", 15)))
    trials_u64 = max(1, int(benchmark.get("trials_u64", 5)))
    seed_base_u64 = int(benchmark.get("seed_base_u64", 424242))
    metric = str(benchmark.get("metric", "median_stps_non_noop_q32")).strip() or "median_stps_non_noop_q32"

    structural = pack.get("structural_validator") if isinstance(pack.get("structural_validator"), dict) else {}
    soak_ticks_u64 = max(1, int(structural.get("soak_ticks_u64", 120)))
    require_tree_hash_match_b = bool(structural.get("require_tree_hash_match_b", True))
    max_disk_mb_u64 = max(1, int(structural.get("max_disk_mb_u64", 2048)))
    max_fd_delta_u64 = max(0, int(structural.get("max_fd_delta_u64", 50)))
    max_rss_delta_bytes_u64 = max(0, int(structural.get("max_rss_delta_bytes_u64", 268435456)))

    bench_pack_rel = str(pack.get("bench_pack_rel", _BENCH_PACK_DEFAULT)).strip() or _BENCH_PACK_DEFAULT

    backend = get_backend()
    task = (
        "Propose a deterministic, replay-valid patch that changes only the target file. "
        "Focus on market scoring/selection/settlement behavior while preserving determinism and schema compatibility. "
        "Keep the patch small and avoid adding new dependencies."
    )
    prompt = _canonical_dumps(
        {
            "schema_version": "rsi_market_rules_mutator_prompt_v1",
            "tick_u64": int(tick_u64),
            "run_seed_u64": int(run_seed_u64),
            "task": task,
            "target_relpath": str(target_relpath),
            "constraints": {"output_format": "json", "json_schema": {"unified_diff": "string"}},
            "target_file_head": target_text[:20000],
        }
    )
    response = backend.generate(prompt)
    obj = json.loads(str(response or "{}"))
    if not isinstance(obj, dict) or not isinstance(obj.get("unified_diff"), str):
        raise RuntimeError("LLM_RESPONSE_INVALID")
    patch_text = str(obj["unified_diff"])
    if not patch_text.endswith("\n"):
        patch_text += "\n"
    patch_bytes = patch_text.encode("utf-8")
    if len(patch_bytes) > max_patch_bytes_u64:
        fail("VERIFY_ERROR")

    touched = _parse_patch_touched_paths(patch_bytes)
    if set(touched) != {target_relpath}:
        fail("VERIFY_ERROR")

    out_dir = out_dir.resolve()
    reports_dir = out_dir / "daemon" / "rsi_market_rules_mutator_v1" / "state" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="phase3_market_mutator_", dir=str(out_dir)) as scratch_raw:
        scratch = Path(scratch_raw)
        baseline_wt = scratch / "baseline"
        candidate_wt = scratch / "candidate"
        _git(repo_root, ["worktree", "add", "--detach", str(baseline_wt), "HEAD"])
        _git(repo_root, ["worktree", "add", "--detach", str(candidate_wt), "HEAD"])
        try:
            patch_path = scratch / "candidate.patch"
            patch_path.write_bytes(patch_bytes)
            _git(candidate_wt, ["apply", "--check", "-p1", str(patch_path)])
            _git(candidate_wt, ["apply", "-p1", str(patch_path)])

            improvements: list[float] = []
            trials_out: list[dict[str, Any]] = []
            for idx in range(int(trials_u64)):
                seed = int(seed_base_u64) + idx
                base_state = _run_daemon_loop(
                    repo_root=baseline_wt,
                    campaign_pack_rel=bench_pack_rel,
                    out_root=out_dir / "bench" / f"trial_{idx+1:02d}" / "baseline",
                    tick_start_u64=1,
                    ticks_u64=ticks_per_trial_u64,
                    run_seed_u64=seed,
                    deterministic_timing=False,
                )
                cand_state = _run_daemon_loop(
                    repo_root=candidate_wt,
                    campaign_pack_rel=bench_pack_rel,
                    out_root=out_dir / "bench" / f"trial_{idx+1:02d}" / "candidate",
                    tick_start_u64=1,
                    ticks_u64=ticks_per_trial_u64,
                    run_seed_u64=seed,
                    deterministic_timing=False,
                )
                base_score = _score_metric_q32(base_state, metric=metric)
                cand_score = _score_metric_q32(cand_state, metric=metric)
                improvement = (float(cand_score) - float(base_score)) / max(float(base_score), 1e-9)
                improvements.append(float(improvement))
                trials_out.append(
                    {
                        "trial_u64": int(idx + 1),
                        "seed_u64": int(seed),
                        "baseline_score_q32": int(base_score),
                        "candidate_score_q32": int(cand_score),
                        "improvement_frac_f64": _fmt_f64(float(improvement)),
                    }
                )

            bench_receipt = {
                "schema_version": "market_rules_mutator_bench_receipt_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "metric": metric,
                "ticks_per_trial_u64": int(ticks_per_trial_u64),
                "trials_u64": int(trials_u64),
                "seed_base_u64": int(seed_base_u64),
                "trials": trials_out,
                "median_improvement_frac_f64": _fmt_f64(float(_median(improvements))),
            }
            bench_receipt["receipt_id"] = canon_hash_obj({k: v for k, v in bench_receipt.items() if k != "receipt_id"})
            write_canon_json(out_dir / "market_rules_mutator_bench_receipt_v1.json", bench_receipt)

            try:
                structural_receipt, structural_state_dir = _structural_validate(
                    candidate_worktree=candidate_wt,
                    bench_pack_rel=bench_pack_rel,
                    soak_ticks_u64=soak_ticks_u64,
                    seed_u64=int(seed_base_u64),
                    max_disk_mb_u64=max_disk_mb_u64,
                    max_fd_delta_u64=max_fd_delta_u64,
                    max_rss_delta_bytes_u64=max_rss_delta_bytes_u64,
                    require_tree_hash_match_b=require_tree_hash_match_b,
                    out_dir=out_dir,
                )
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_structural_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_structural_failure_v1.json", failure)
                return
            structural_receipt["receipt_id"] = canon_hash_obj(
                {k: v for k, v in structural_receipt.items() if k != "receipt_id"}
            )
            write_canon_json(out_dir / "market_rules_mutator_structural_receipt_v1.json", structural_receipt)

            try:
                verdict = v19_replay_verifier.verify(structural_state_dir, mode="full")
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_replay_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_replay_failure_v1.json", failure)
                return
            if str(verdict).strip() != "VALID":
                return

            ccap_id, _ccap_relpath, _patch_relpath, bundle_hash = _emit_ccap(
                repo_root=repo_root,
                out_dir=out_dir,
                patch_bytes=patch_bytes,
            )
            report = {
                "schema_version": "market_rules_mutator_report_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "ccap_id": ccap_id,
                "bundle_hash": bundle_hash,
                "patch_sha256": _sha256_prefixed(patch_bytes),
                "touched_paths": touched,
            }
            require_no_absolute_paths(report)
            report["report_id"] = canon_hash_obj({k: v for k, v in report.items() if k != "report_id"})
            write_canon_json(reports_dir / "market_rules_mutator_report_v1.json", report)
        finally:
            try:
                _git(repo_root, ["worktree", "remove", "-f", str(baseline_wt)])
            except Exception:
                pass
            try:
                _git(repo_root, ["worktree", "remove", "-f", str(candidate_wt)])
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rsi_market_rules_mutator_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args(argv)
    run(campaign_pack=Path(args.campaign_pack).resolve(), out_dir=Path(args.out_dir).resolve())
    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
