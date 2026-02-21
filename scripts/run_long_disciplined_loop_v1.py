#!/usr/bin/env python3
"""Deterministic long-run harness with index-backed resume and pruning."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict


TICK_INDEX_NAME = "long_run_tick_index_v1.jsonl"
PRUNE_INDEX_NAME = "long_run_prune_index_v1.jsonl"
HEAD_NAME = "long_run_head_v1.json"
ENV_RECEIPT_NAME = "run_env_receipt_v1.json"

DEFAULT_PACK = "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json"
DEFAULT_RUN_ROOT = "runs/long_disciplined_v1"
DEFAULT_MAX_DISK_BYTES = 20 * 1024 * 1024 * 1024
DEFAULT_RETAIN_LAST = 200
DEFAULT_ANCHOR_EVERY = 100
DEFAULT_CANARY_EVERY = 10
DEFAULT_HIST_WINDOW = 50

ENV_ALLOWLIST = (
    "PYTHONPATH",
    "OMEGA_NET_LIVE_OK",
    "OMEGA_META_CORE_ACTIVATION_MODE",
    "OMEGA_ALLOW_SIMULATE_ACTIVATION",
    "OMEGA_BLACKBOX",
    "OMEGA_DISABLE_FORCED_RUNAWAY",
    "OMEGA_RUN_SEED_U64",
    "OMEGA_LONG_RUN_FORCE_LANE",
    "OMEGA_LONG_RUN_FORCE_EVAL",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canon_bytes(payload) + b"\n")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canon_bytes(payload) + b"\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            out.append(row)
    return out


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += int(file_path.stat().st_size)
            except FileNotFoundError:
                continue
    return int(total)


def _latest_payload(dir_path: Path, suffix: str) -> tuple[dict[str, Any] | None, str | None]:
    if not dir_path.exists() or not dir_path.is_dir():
        return None, None
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if not rows:
        return None, None
    payload = load_canon_dict(rows[-1])
    digest = "sha256:" + rows[-1].name.split(".", 1)[0].split("_", 1)[1]
    return payload, digest


def _build_subprocess_env(*, force_lane: str | None, force_eval: bool) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    for key in ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.setdefault("PYTHONPATH", ".:CDEL-v2:Extension-1/agi-orchestrator")
    env.setdefault("OMEGA_NET_LIVE_OK", "0")
    if force_lane:
        env["OMEGA_LONG_RUN_FORCE_LANE"] = force_lane
    else:
        env.pop("OMEGA_LONG_RUN_FORCE_LANE", None)
    if force_eval:
        env["OMEGA_LONG_RUN_FORCE_EVAL"] = "1"
    else:
        env.pop("OMEGA_LONG_RUN_FORCE_EVAL", None)
    return env


def _env_receipt(*, env: dict[str, str]) -> dict[str, Any]:
    selected = {key: env[key] for key in sorted(env.keys()) if key in ENV_ALLOWLIST or key in {"PYTHONPATH"}}
    payload = {
        "schema_name": "run_env_receipt_v1",
        "schema_version": "v1",
        "created_unix_s": int(time.time()),
        "env": selected,
    }
    payload["receipt_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "receipt_id"})
    return payload


def _authority_pins_hash() -> str:
    payload = load_canon_dict(REPO_ROOT / "authority" / "authority_pins_v1.json")
    return canon_hash_obj(payload)


def _reason_hist(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("promotion_reason_code", "")).strip() or "none"
        key = reason.lower()
        out[key] = int(out.get(key, 0)) + 1
    return {key: out[key] for key in sorted(out.keys())}


def _write_canary_summary(
    *,
    run_root: Path,
    tick_row: dict[str, Any],
    live_rows: list[dict[str, Any]],
    pins_hash_initial: str,
    canary_every: int,
) -> None:
    tick_u64 = int(tick_row["tick_u64"])
    if tick_u64 <= 0 or (tick_u64 % int(canary_every)) != 0:
        return
    state_dir = Path(str(tick_row["state_dir"]))
    verify_cmd = [
        sys.executable,
        "-m",
        "cdel.v19_0.verify_rsi_omega_daemon_v1",
        "--mode",
        "full",
        "--state_dir",
        str(state_dir),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = ".:CDEL-v2:Extension-1/agi-orchestrator"
    verify = subprocess.run(
        verify_cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    replay_valid_b = verify.returncode == 0 and "VALID" in (verify.stdout or "")
    pins_hash_now = _authority_pins_hash()
    pins_drift_b = pins_hash_now != pins_hash_initial
    tail = [row for row in live_rows if int(row.get("tick_u64", -1)) <= tick_u64]
    tail = tail[-DEFAULT_HIST_WINDOW :]
    prev_tail = tail[:-1]
    hist_now = _reason_hist(tail)
    hist_prev = _reason_hist(prev_tail)
    histogram_stable_b = hist_now == hist_prev if prev_tail else True
    payload = {
        "schema_name": "long_run_canary_summary_v1",
        "schema_version": "v1",
        "summary_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "state_dir": str(state_dir),
        "replay_valid_b": bool(replay_valid_b),
        "pins_hash_initial": pins_hash_initial,
        "pins_hash_now": pins_hash_now,
        "pins_drift_b": bool(pins_drift_b),
        "reason_hist_window_u64": int(len(tail)),
        "reason_histogram_now": hist_now,
        "reason_histogram_prev": hist_prev,
        "histogram_stable_b": bool(histogram_stable_b),
    }
    payload["summary_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "summary_id"})
    out_dir = run_root / "canary"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"sha256_{payload['summary_id'].split(':',1)[1]}.long_run_canary_summary_v1.json"
    _write_json(out_path, payload)


def _read_indexes(index_dir: Path) -> tuple[list[dict[str, Any]], set[int]]:
    tick_rows = _load_jsonl(index_dir / TICK_INDEX_NAME)
    prune_rows = _load_jsonl(index_dir / PRUNE_INDEX_NAME)
    pruned_ticks = {int(row.get("tick_u64", -1)) for row in prune_rows if isinstance(row, dict)}
    return tick_rows, pruned_ticks


def _live_rows(tick_rows: list[dict[str, Any]], pruned_ticks: set[int]) -> list[dict[str, Any]]:
    rows = [row for row in tick_rows if int(row.get("tick_u64", -1)) >= 0 and int(row.get("tick_u64", -1)) not in pruned_ticks]
    rows.sort(key=lambda row: int(row.get("tick_u64", -1)))
    return rows


def _compute_live_disk_bytes(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        total += int(max(0, int(row.get("disk_bytes_u64", 0))))
    return int(total)


def _read_head(head_path: Path) -> dict[str, Any] | None:
    if not head_path.exists() or not head_path.is_file():
        return None
    payload = json.loads(head_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _write_head(head_path: Path, row: dict[str, Any]) -> None:
    payload = {
        "schema_name": "long_run_head_v1",
        "schema_version": "v1",
        "tick_u64": int(row["tick_u64"]),
        "state_dir": str(row["state_dir"]),
        "out_dir": str(row["out_dir"]),
        "snapshot_hash": row.get("snapshot_hash"),
    }
    payload["head_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "head_id"})
    _write_json(head_path, payload)


def _retention_keep_ticks(*, live_rows: list[dict[str, Any]], retain_last_u64: int, anchor_every_u64: int) -> set[int]:
    keep: set[int] = set()
    if not live_rows:
        return keep
    tail_rows = live_rows[-max(1, int(retain_last_u64)) :]
    for row in tail_rows:
        keep.add(int(row["tick_u64"]))
    for row in live_rows:
        tick = int(row["tick_u64"])
        if int(anchor_every_u64) > 0 and tick % int(anchor_every_u64) == 0:
            keep.add(tick)
    keep.add(int(live_rows[-1]["tick_u64"]))
    return keep


def _prune_if_needed(
    *,
    run_root: Path,
    max_disk_bytes: int,
    retain_last_u64: int,
    anchor_every_u64: int,
) -> None:
    index_dir = run_root / "index"
    tick_rows, pruned_ticks = _read_indexes(index_dir)
    live_rows = _live_rows(tick_rows, pruned_ticks)
    current_bytes = _compute_live_disk_bytes(live_rows)
    if current_bytes <= int(max_disk_bytes):
        return
    keep_ticks = _retention_keep_ticks(
        live_rows=live_rows,
        retain_last_u64=retain_last_u64,
        anchor_every_u64=anchor_every_u64,
    )
    for row in live_rows:
        tick = int(row["tick_u64"])
        if current_bytes <= int(max_disk_bytes):
            break
        if tick in keep_ticks:
            continue
        out_dir = Path(str(row.get("out_dir", "")))
        if out_dir.exists() and out_dir.is_dir():
            shutil.rmtree(out_dir)
        pruned_ticks.add(tick)
        current_bytes -= int(max(0, int(row.get("disk_bytes_u64", 0))))
        _append_jsonl(
            index_dir / PRUNE_INDEX_NAME,
            {
                "schema_name": "long_run_prune_event_v1",
                "schema_version": "v1",
                "tick_u64": int(tick),
                "out_dir": str(out_dir),
                "reason_code": "DISK_CAP",
            },
        )


def run_tick(
    *,
    campaign_pack: Path,
    run_root: Path,
    tick_u64: int,
    prev_state_dir: Path | None,
    force_lane: str | None,
    force_eval: bool,
) -> dict[str, Any]:
    out_dir = run_root / f"tick_{int(tick_u64):06d}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack),
        "--out_dir",
        str(out_dir),
        "--mode",
        "once",
        "--tick_u64",
        str(int(tick_u64)),
    ]
    if prev_state_dir is not None:
        cmd.extend(["--prev_state_dir", str(prev_state_dir)])
    env = _build_subprocess_env(force_lane=force_lane, force_eval=force_eval)
    started = int(time.time())
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    snapshot_payload, snapshot_hash = _latest_payload(state_dir / "snapshot", "omega_tick_snapshot_v1.json")
    tick_outcome_payload, _tick_outcome_hash = _latest_payload(state_dir / "perf", "omega_tick_outcome_v1.json")
    lane_name = None
    lane_payload, _lane_hash = _latest_payload(state_dir / "long_run" / "lane", "lane_decision_receipt_v1.json")
    if isinstance(lane_payload, dict):
        lane_name = lane_payload.get("lane_name")
    row = {
        "schema_name": "long_run_tick_index_row_v1",
        "schema_version": "v1",
        "tick_u64": int(tick_u64),
        "out_dir": str(out_dir),
        "state_dir": str(state_dir),
        "status": "OK" if proc.returncode == 0 and state_dir.exists() else "ERROR",
        "exit_code": int(proc.returncode),
        "snapshot_hash": snapshot_hash,
        "lane_name": lane_name,
        "mission_goal_ingest_receipt_hash": (snapshot_payload or {}).get("mission_goal_ingest_receipt_hash"),
        "eval_report_hash": (snapshot_payload or {}).get("eval_report_hash"),
        "subverifier_status": (tick_outcome_payload or {}).get("subverifier_status"),
        "promotion_reason_code": (tick_outcome_payload or {}).get("promotion_reason_code"),
        "disk_bytes_u64": int(_dir_size_bytes(out_dir)) if out_dir.exists() else 0,
        "started_unix_s": int(started),
        "finished_unix_s": int(time.time()),
    }
    if proc.stdout:
        row["stdout_tail"] = proc.stdout.strip().splitlines()[-5:]
    if proc.stderr:
        row["stderr_tail"] = proc.stderr.strip().splitlines()[-5:]
    return row


def run_loop(
    *,
    campaign_pack: Path,
    run_root: Path,
    start_tick_u64: int,
    max_ticks: int,
    max_disk_bytes: int,
    retain_last_u64: int,
    anchor_every_u64: int,
    canary_every_u64: int,
    force_lane: str | None,
    force_eval: bool,
    stop_on_error: bool,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    index_dir = run_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    env_receipt = _env_receipt(env=_build_subprocess_env(force_lane=force_lane, force_eval=force_eval))
    _write_json(run_root / ENV_RECEIPT_NAME, env_receipt)
    pins_hash_initial = _authority_pins_hash()

    tick_rows, pruned_ticks = _read_indexes(index_dir)
    live_rows = _live_rows(tick_rows, pruned_ticks)
    head = _read_head(index_dir / HEAD_NAME)
    prev_state_dir: Path | None = None
    tick_u64 = int(start_tick_u64)
    if head is not None:
        head_tick = int(head.get("tick_u64", -1))
        head_state_dir = Path(str(head.get("state_dir", "")))
        if head_tick >= 0 and head_state_dir.exists():
            tick_u64 = head_tick + 1
            prev_state_dir = head_state_dir
    elif live_rows:
        last = live_rows[-1]
        prev_state_dir = Path(str(last["state_dir"]))
        tick_u64 = int(last["tick_u64"]) + 1

    ticks_run = 0
    while max_ticks <= 0 or ticks_run < max_ticks:
        row = run_tick(
            campaign_pack=campaign_pack,
            run_root=run_root,
            tick_u64=tick_u64,
            prev_state_dir=prev_state_dir,
            force_lane=force_lane,
            force_eval=force_eval,
        )
        _append_jsonl(index_dir / TICK_INDEX_NAME, row)
        _write_head(index_dir / HEAD_NAME, row)
        tick_rows.append(row)
        if int(row.get("status") == "OK"):
            prev_state_dir = Path(str(row["state_dir"]))
        _prune_if_needed(
            run_root=run_root,
            max_disk_bytes=max_disk_bytes,
            retain_last_u64=retain_last_u64,
            anchor_every_u64=anchor_every_u64,
        )
        tick_rows, pruned_ticks = _read_indexes(index_dir)
        live_rows = _live_rows(tick_rows, pruned_ticks)
        _write_canary_summary(
            run_root=run_root,
            tick_row=row,
            live_rows=live_rows,
            pins_hash_initial=pins_hash_initial,
            canary_every=canary_every_u64,
        )
        if row.get("status") != "OK" and stop_on_error:
            break
        tick_u64 += 1
        ticks_run += 1


def main() -> None:
    ap = argparse.ArgumentParser(prog="run_long_disciplined_loop_v1")
    ap.add_argument("--campaign_pack", default=DEFAULT_PACK)
    ap.add_argument("--run_root", default=DEFAULT_RUN_ROOT)
    ap.add_argument("--start_tick_u64", type=int, default=1)
    ap.add_argument("--max_ticks", type=int, default=0, help="0 means run forever")
    ap.add_argument("--max_disk_bytes", type=int, default=DEFAULT_MAX_DISK_BYTES)
    ap.add_argument("--retain_last_u64", type=int, default=DEFAULT_RETAIN_LAST)
    ap.add_argument("--anchor_every_u64", type=int, default=DEFAULT_ANCHOR_EVERY)
    ap.add_argument("--canary_every_u64", type=int, default=DEFAULT_CANARY_EVERY)
    ap.add_argument("--force_lane", choices=["BASELINE", "CANARY", "FRONTIER"])
    ap.add_argument("--force_eval", action="store_true")
    ap.add_argument("--stop_on_error", action="store_true")
    args = ap.parse_args()

    run_loop(
        campaign_pack=(REPO_ROOT / args.campaign_pack).resolve(),
        run_root=(REPO_ROOT / args.run_root).resolve(),
        start_tick_u64=int(args.start_tick_u64),
        max_ticks=int(args.max_ticks),
        max_disk_bytes=int(args.max_disk_bytes),
        retain_last_u64=int(args.retain_last_u64),
        anchor_every_u64=int(args.anchor_every_u64),
        canary_every_u64=int(args.canary_every_u64),
        force_lane=args.force_lane,
        force_eval=bool(args.force_eval),
        stop_on_error=bool(args.stop_on_error),
    )


if __name__ == "__main__":
    main()
