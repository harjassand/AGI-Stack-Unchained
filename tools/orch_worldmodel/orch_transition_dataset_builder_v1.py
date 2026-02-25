#!/usr/bin/env python3
"""Build deterministic orchestration transition datasets from official run logs (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj

from tools.orch_worldmodel.orch_worldmodel_math_q32_v1 import cost_norm_q32_from_wallclock


_Q32_ONE = 1 << 32
_LANE_KINDS = {"BASELINE", "FRONTIER_HEAVY", "UNKNOWN"}
_PROMOTION_RESULT_KINDS = {
    "PROMOTED_COMMIT",
    "PROMOTED_EXT_QUEUED",
    "REJECTED",
}
_TOXIC_REASON_PREFIXES = (
    "HOLDOUT_",
    "PHASE1_PUBLIC_ONLY_VIOLATION",
    "SANDBOX_",
)
_TOXIC_REASON_EXACT = {
    "CCAP_ALLOWLIST_VIOLATION",
    "CCAP_PATCH_ALLOWLIST_VIOLATION",
    "BUDGET_EXHAUSTED",
}
_ORCH_REWARD_COMMIT_Q32 = _Q32_ONE
_ORCH_REWARD_EXT_Q32 = _Q32_ONE // 2
_ORCH_REWARD_TOXIC_Q32 = -(_Q32_ONE // 2)
_ORCH_REWARD_HEAVY_UTILITY_BONUS_Q32 = _Q32_ONE // 4


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class TickInput:
    tick_u64: int
    state_root: Path
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class TickMaterial:
    run_id: str
    tick_u64: int
    context_key: str
    lane_kind: str
    objective_kind: str
    action_capability_id: str
    reward_q32: int
    cost_norm_q32: int
    toxic_fail_b: bool


def _fail(reason: str) -> None:
    raise BuildError(str(reason))


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _as_nonneg_int(value: Any) -> int:
    return int(max(0, int(value)))


def _normalize_lane_kind(lane_kind: Any) -> str:
    lane = str(lane_kind).strip().upper()
    if lane not in _LANE_KINDS:
        return "UNKNOWN"
    return lane


def _runaway_band_u32(runaway_level_u32: Any) -> int:
    return int(min(_as_nonneg_int(runaway_level_u32), 5))


def _compute_context_key(*, lane_kind: str, runaway_level_u32: int, objective_kind: str) -> str:
    payload = {
        "lane_kind": _normalize_lane_kind(lane_kind),
        "runaway_band_u32": int(_runaway_band_u32(runaway_level_u32)),
        "objective_kind": str(objective_kind),
    }
    return str(canon_hash_obj(payload))


def _normalize_promotion_result_kind(*, result_kind: Any, status: Any, activation_kind: Any) -> str:
    kind = str(result_kind).strip()
    if kind in _PROMOTION_RESULT_KINDS:
        return kind
    normalized_status = str(status).strip().upper()
    if normalized_status == "PROMOTED":
        normalized_activation_kind = str(activation_kind).strip()
        if normalized_activation_kind == "ACTIVATION_KIND_EXT_QUEUED":
            return "PROMOTED_EXT_QUEUED"
        return "PROMOTED_COMMIT"
    return "REJECTED"


def _is_toxic_reason_code(reason_code: Any) -> bool:
    code = str(reason_code).strip()
    if not code:
        return False
    for prefix in _TOXIC_REASON_PREFIXES:
        if code.startswith(prefix):
            return True
    return code in _TOXIC_REASON_EXACT


def _utility_indicates_effect_heavy_ok(utility_receipt: dict[str, Any] | None) -> bool:
    if not isinstance(utility_receipt, dict):
        return False
    return str(utility_receipt.get("effect_class", "")).strip() == "EFFECT_HEAVY_OK"


def _clamp_reward_q32(value: int) -> int:
    if int(value) < -_Q32_ONE:
        return -_Q32_ONE
    if int(value) > _Q32_ONE:
        return _Q32_ONE
    return int(value)


def _compute_reward_q32(
    *,
    promotion_result_kind: str,
    toxic_fail_b: bool,
    lane_kind: str,
    utility_receipt: dict[str, Any] | None,
) -> int:
    if promotion_result_kind == "PROMOTED_COMMIT":
        r_commit_q32 = int(_ORCH_REWARD_COMMIT_Q32)
        r_ext_q32 = 0
    elif promotion_result_kind == "PROMOTED_EXT_QUEUED":
        r_commit_q32 = 0
        r_ext_q32 = int(_ORCH_REWARD_EXT_Q32)
    else:
        r_commit_q32 = 0
        r_ext_q32 = 0

    r_toxic_penalty_q32 = int(_ORCH_REWARD_TOXIC_Q32 if bool(toxic_fail_b) else 0)
    r_heavy_utility_bonus_q32 = int(
        _ORCH_REWARD_HEAVY_UTILITY_BONUS_Q32
        if str(lane_kind).strip() == "FRONTIER_HEAVY" and _utility_indicates_effect_heavy_ok(utility_receipt)
        else 0
    )
    reward_q32 = int(r_commit_q32) + int(r_ext_q32) + int(r_toxic_penalty_q32) + int(r_heavy_utility_bonus_q32)
    return int(_clamp_reward_q32(reward_q32))


def _load_canon_dict(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _load_hashed_payload(*, dir_path: Path, digest: str, suffix: str) -> dict[str, Any] | None:
    if not _is_sha256(digest):
        return None
    hexd = digest.split(":", 1)[1]
    path = dir_path / f"sha256_{hexd}.{suffix}"
    if not path.exists() or not path.is_file():
        return None
    payload = _load_canon_dict(path)
    if str(canon_hash_obj(payload)) != str(digest):
        _fail("NONDETERMINISTIC")
    return payload


def _find_nested_hashed_payload(*, state_root: Path, digest: str, suffix: str) -> dict[str, Any] | None:
    if not _is_sha256(digest):
        return None
    hexd = digest.split(":", 1)[1]
    target = f"sha256_{hexd}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"), key=lambda row: row.as_posix())
    if len(rows) == 0:
        return None
    if len(rows) != 1:
        _fail("NONDETERMINISTIC")
    payload = _load_canon_dict(rows[0])
    if str(canon_hash_obj(payload)) != str(digest):
        _fail("NONDETERMINISTIC")
    return payload


def _resolve_lane_kind(*, state_root: Path, snapshot: dict[str, Any]) -> str:
    lane_hash = snapshot.get("lane_decision_receipt_hash")
    if not _is_sha256(lane_hash):
        return "UNKNOWN"
    lane_payload = _load_hashed_payload(
        dir_path=state_root / "long_run" / "lane",
        digest=str(lane_hash),
        suffix="lane_decision_receipt_v1.json",
    )
    if not isinstance(lane_payload, dict):
        return "UNKNOWN"
    lane_name = str(lane_payload.get("lane_name", "")).strip().upper()
    if lane_name == "FRONTIER":
        return "FRONTIER_HEAVY"
    if lane_name in {"BASELINE", "CANARY"}:
        return "BASELINE"
    return "UNKNOWN"


def _load_tick_perf(*, state_root: Path, tick_u64: int) -> dict[str, Any] | None:
    rows = sorted((state_root / "perf").glob("sha256_*.omega_tick_perf_v1.json"), key=lambda row: row.as_posix())
    for row in rows:
        payload = _load_canon_dict(row)
        if int(payload.get("tick_u64", -1)) != int(tick_u64):
            continue
        expected = "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]
        if str(canon_hash_obj(payload)) != expected:
            _fail("NONDETERMINISTIC")
        return payload
    return None


def _collect_state_dirs(run_dir: Path) -> list[Path]:
    rows: list[Path] = []
    direct = run_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if direct.exists() and direct.is_dir():
        rows.append(direct.resolve())

    for pattern in ("tick_*/daemon/rsi_omega_daemon_v19_0/state", "closure_*/daemon/rsi_omega_daemon_v19_0/state"):
        for row in sorted(run_dir.glob(pattern), key=lambda p: p.as_posix()):
            if row.exists() and row.is_dir():
                rows.append(row.resolve())

    dedup: dict[str, Path] = {}
    for row in rows:
        dedup[row.as_posix()] = row
    return [dedup[key] for key in sorted(dedup.keys())]


def _collect_ticks_for_run(run_dir: Path) -> list[TickInput]:
    by_tick: dict[int, TickInput] = {}
    for state_root in _collect_state_dirs(run_dir):
        snap_dir = state_root / "snapshot"
        if not snap_dir.exists() or not snap_dir.is_dir():
            continue

        snap_rows = sorted(snap_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda p: p.as_posix())
        if not snap_rows:
            plain = snap_dir / "omega_tick_snapshot_v1.json"
            if plain.exists() and plain.is_file():
                snap_rows = [plain]

        for snap_path in snap_rows:
            try:
                snap_payload = _load_canon_dict(snap_path)
            except Exception:
                continue
            if str(snap_payload.get("schema_version", "")).strip() != "omega_tick_snapshot_v1":
                continue
            tick_u64 = int(max(0, int(snap_payload.get("tick_u64", 0))))
            candidate = TickInput(
                tick_u64=tick_u64,
                state_root=state_root,
                snapshot=snap_payload,
            )
            previous = by_tick.get(int(tick_u64))
            if previous is None:
                by_tick[int(tick_u64)] = candidate
                continue
            prev_key = previous.state_root.as_posix()
            cand_key = candidate.state_root.as_posix()
            if cand_key < prev_key:
                by_tick[int(tick_u64)] = candidate

    return [by_tick[key] for key in sorted(by_tick.keys())]


def _event_material_for_tick(
    *,
    run_id: str,
    tick: TickInput,
    cost_scale_ms_u64: int,
) -> tuple[TickMaterial | None, str | None]:
    state_root = tick.state_root
    snapshot = tick.snapshot

    decision_hash = snapshot.get("decision_plan_hash")
    if not _is_sha256(decision_hash):
        return None, "DROP:MISSING_DECISION_PLAN"
    decision = _load_hashed_payload(
        dir_path=state_root / "decisions",
        digest=str(decision_hash),
        suffix="omega_decision_plan_v1.json",
    )
    if not isinstance(decision, dict):
        return None, "DROP:MISSING_DECISION_PLAN"

    objective_kind = str(decision.get("action_kind", "")).strip() or "UNKNOWN"
    runaway_level_u32 = int(max(0, int(decision.get("runaway_escalation_level_u64", 0))))
    lane_kind = _resolve_lane_kind(state_root=state_root, snapshot=snapshot)
    context_key = _compute_context_key(
        lane_kind=lane_kind,
        runaway_level_u32=runaway_level_u32,
        objective_kind=objective_kind,
    )

    routing_hash = snapshot.get("dependency_routing_receipt_hash")
    routing = (
        _load_hashed_payload(
            dir_path=state_root / "long_run" / "debt",
            digest=str(routing_hash),
            suffix="dependency_routing_receipt_v1.json",
        )
        if _is_sha256(routing_hash)
        else None
    )

    action_capability_id = ""
    if isinstance(routing, dict):
        action_capability_id = str(routing.get("selected_capability_id", "")).strip()
    if not action_capability_id:
        action_capability_id = str(decision.get("capability_id", "")).strip()
    if not action_capability_id:
        return None, "DROP:MISSING_ACTION"

    promotion_receipt: dict[str, Any] | None = None
    utility_receipt: dict[str, Any] | None = None
    activation_receipt: dict[str, Any] | None = None

    promotion_hash = snapshot.get("promotion_receipt_hash")
    if _is_sha256(promotion_hash):
        promotion_receipt = _find_nested_hashed_payload(
            state_root=state_root,
            digest=str(promotion_hash),
            suffix="omega_promotion_receipt_v1.json",
        )

    utility_hash = snapshot.get("utility_proof_hash")
    if _is_sha256(utility_hash):
        utility_receipt = _find_nested_hashed_payload(
            state_root=state_root,
            digest=str(utility_hash),
            suffix="utility_proof_receipt_v1.json",
        )

    activation_hash = snapshot.get("activation_receipt_hash")
    if _is_sha256(activation_hash):
        activation_receipt = _find_nested_hashed_payload(
            state_root=state_root,
            digest=str(activation_hash),
            suffix="omega_activation_receipt_v1.json",
        )

    promotion_result_kind = _normalize_promotion_result_kind(
        result_kind=(promotion_receipt or {}).get("result_kind"),
        status=((promotion_receipt or {}).get("result") or {}).get("status"),
        activation_kind=(activation_receipt or {}).get("activation_kind"),
    )
    toxic_fail_b = _is_toxic_reason_code(((promotion_receipt or {}).get("result") or {}).get("reason_code"))
    reward_q32 = _compute_reward_q32(
        promotion_result_kind=promotion_result_kind,
        toxic_fail_b=bool(toxic_fail_b),
        lane_kind=lane_kind,
        utility_receipt=utility_receipt,
    )

    perf_payload = _load_tick_perf(state_root=state_root, tick_u64=tick.tick_u64)
    if not isinstance(perf_payload, dict):
        return None, "DROP:MISSING_TICK_PERF"
    wallclock_ms_u64 = int(max(0, int(perf_payload.get("total_ns", 0)) // 1_000_000))
    cost_norm_q32 = int(
        cost_norm_q32_from_wallclock(
            wallclock_ms_u64=wallclock_ms_u64,
            cost_scale_ms_u64=int(cost_scale_ms_u64),
        )
    )

    return (
        TickMaterial(
            run_id=str(run_id),
            tick_u64=int(tick.tick_u64),
            context_key=str(context_key),
            lane_kind=str(lane_kind),
            objective_kind=str(objective_kind),
            action_capability_id=str(action_capability_id),
            reward_q32=int(reward_q32),
            cost_norm_q32=int(cost_norm_q32),
            toxic_fail_b=bool(toxic_fail_b),
        ),
        None,
    )


def _write_blob_immutable(*, blobs_dir: Path, data: bytes, suffix: str) -> tuple[str, Path]:
    digest_hex = hashlib.sha256(data).hexdigest()
    digest = f"sha256:{digest_hex}"
    path = blobs_dir / f"sha256_{digest_hex}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        if path.read_bytes() != data:
            _fail("IMMUTABLE_BLOB_CONFLICT")
    else:
        path.write_bytes(data)
    return digest, path


def _write_manifest_immutable(*, manifests_dir: Path, payload: dict[str, Any], schema_name: str, id_field: str) -> tuple[str, Path]:
    no_id = dict(payload)
    no_id.pop(id_field, None)
    digest = str(canon_hash_obj(no_id))
    out = dict(no_id)
    out[id_field] = digest
    path = manifests_dir / f"sha256_{digest.split(':', 1)[1]}.{schema_name}.json"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        if path.read_bytes().rstrip(b"\n") != canon_bytes(out):
            _fail("IMMUTABLE_BLOB_CONFLICT")
    else:
        write_canon_json(path, out)
    return digest, path


def _ensure_out_root(out_root: Path, *, repo_root: Path) -> None:
    out_abs = out_root.resolve()
    repo_abs = repo_root.resolve()
    try:
        rel = out_abs.relative_to(repo_abs)
    except Exception as exc:
        raise BuildError("OUT_ROOT_INVALID") from exc
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "daemon" or parts[1] != "orch_policy":
        _fail("OUT_ROOT_INVALID")


def _runs_root_rel(*, runs_root: Path, repo_root: Path) -> str:
    try:
        return runs_root.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return runs_root.resolve().as_posix()


def build_transition_dataset(
    *,
    runs_root: Path,
    out_root: Path,
    ek_id: str,
    kernel_ledger_id: str,
    max_runs_u64: int,
    max_events_u64: int,
    cost_scale_ms_u64: int,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = (repo_root or _REPO_ROOT).resolve()
    runs_abs = runs_root.resolve()
    out_abs = out_root.resolve()

    if not runs_abs.exists() or not runs_abs.is_dir():
        _fail("MISSING_RUNS_ROOT")
    _ensure_out_root(out_abs, repo_root=root)
    if not _is_sha256(ek_id) or not _is_sha256(kernel_ledger_id):
        _fail("SCHEMA_FAIL")

    blobs_dir = out_abs / "store" / "blobs" / "sha256"
    manifests_dir = out_abs / "store" / "manifests"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted([row for row in runs_abs.iterdir() if row.is_dir()], key=lambda row: row.name)

    max_runs = _as_nonneg_int(max_runs_u64)
    max_events = _as_nonneg_int(max_events_u64)
    if max_events <= 0:
        _fail("MAX_EVENTS_INVALID")
    scale = _as_nonneg_int(cost_scale_ms_u64)
    if scale <= 0:
        _fail("SCHEMA_FAIL")

    drop_hist: dict[str, int] = {}
    included_run_ids: list[str] = []
    events: list[dict[str, Any]] = []
    runs_scanned = 0
    max_events_hit = False

    for run_dir in run_dirs:
        if runs_scanned >= max_runs:
            break
        runs_scanned += 1
        run_id = run_dir.name

        ticks = _collect_ticks_for_run(run_dir)
        if not ticks:
            drop_hist["DROP:NO_TICKS"] = int(drop_hist.get("DROP:NO_TICKS", 0)) + 1
            continue

        materials: list[tuple[int, TickMaterial | None]] = []
        for tick in ticks:
            material, reason = _event_material_for_tick(
                run_id=run_id,
                tick=tick,
                cost_scale_ms_u64=scale,
            )
            if reason is not None:
                drop_hist[reason] = int(drop_hist.get(reason, 0)) + 1
                materials.append((int(tick.tick_u64), None))
            else:
                materials.append((int(tick.tick_u64), material))

        run_events_before = len(events)
        for idx, row in enumerate(materials):
            tick_u64, material = int(row[0]), row[1]
            if material is None:
                continue
            if idx + 1 >= len(materials):
                drop_hist["DROP:NO_NEXT_CONTEXT"] = int(drop_hist.get("DROP:NO_NEXT_CONTEXT", 0)) + 1
                continue

            next_tick_u64, next_material = int(materials[idx + 1][0]), materials[idx + 1][1]
            if next_material is None or int(next_tick_u64) != int(tick_u64 + 1):
                drop_hist["DROP:NO_NEXT_CONTEXT"] = int(drop_hist.get("DROP:NO_NEXT_CONTEXT", 0)) + 1
                continue

            event_no_id = {
                "schema_version": "orch_transition_event_v1",
                "run_id": str(material.run_id),
                "tick_u64": int(tick_u64),
                "context_key": str(material.context_key),
                "lane_kind": str(material.lane_kind),
                "objective_kind": str(material.objective_kind),
                "action_capability_id": str(material.action_capability_id),
                "reward_q32": int(material.reward_q32),
                "cost_norm_q32": int(material.cost_norm_q32),
                "toxic_fail_b": bool(material.toxic_fail_b),
                "next_context_key": str(next_material.context_key),
            }
            event_id = str(canon_hash_obj(event_no_id))
            event = dict(event_no_id)
            event["event_id"] = event_id
            events.append(event)

            if len(events) >= max_events:
                drop_hist["DROP:MAX_EVENTS"] = int(drop_hist.get("DROP:MAX_EVENTS", 0)) + 1
                max_events_hit = True
                break

        if len(events) > run_events_before:
            included_run_ids.append(str(run_id))

        if max_events_hit:
            break

    events = sorted(
        events,
        key=lambda row: (
            str(row.get("run_id", "")),
            int(row.get("tick_u64", 0)),
            str(row.get("event_id", "")),
        ),
    )

    jsonl_path = out_abs / "transition_events.jsonl"
    with jsonl_path.open("wb") as handle:
        for row in events:
            handle.write(canon_bytes(row) + b"\n")

    blob_data = jsonl_path.read_bytes()
    blob_id, blob_path = _write_blob_immutable(
        blobs_dir=blobs_dir,
        data=blob_data,
        suffix="orch_transition_events_v1.jsonl",
    )

    runs_included = len(included_run_ids)
    dropped_rows_u64 = sum(int(v) for v in drop_hist.values())

    manifest_no_id = {
        "schema_version": "orch_transition_dataset_manifest_v1",
        "ek_id": str(ek_id),
        "kernel_ledger_id": str(kernel_ledger_id),
        "runs_root_rel": _runs_root_rel(runs_root=runs_abs, repo_root=root),
        "included_run_ids": sorted(set(included_run_ids)),
        "transition_events_blob_id": str(blob_id),
        "transition_events_relpath": blob_path.resolve().relative_to(root).as_posix(),
        "transition_events_sha256": str(blob_id),
        "counts": {
            "runs_scanned_u64": int(runs_scanned),
            "runs_included_u64": int(runs_included),
            "events_included_u64": int(len(events)),
            "dropped_rows_u64": int(dropped_rows_u64),
        },
        "build_params": {
            "max_runs_u64": int(max_runs),
            "max_events_u64": int(max_events),
            "cost_scale_ms_u64": int(scale),
        },
        "drop_reason_histogram": {k: int(v) for k, v in sorted(drop_hist.items())},
        "created_unix_s64": int(max(0, int(time.time()))),
    }
    manifest_id, manifest_path = _write_manifest_immutable(
        manifests_dir=manifests_dir,
        payload=manifest_no_id,
        schema_name="orch_transition_dataset_manifest_v1",
        id_field="dataset_manifest_id",
    )

    receipt = {
        "schema_version": "orch_transition_dataset_build_receipt_v1",
        "dataset_manifest_id": str(manifest_id),
        "status": "OK",
        "reason_code": "OK",
        "runs_scanned_u64": int(runs_scanned),
        "runs_included_u64": int(runs_included),
        "events_included_u64": int(len(events)),
        "dropped_rows_u64": int(dropped_rows_u64),
        "drop_reason_histogram": {k: int(v) for k, v in sorted(drop_hist.items())},
        "output_paths": [
            jsonl_path.as_posix(),
            blob_path.as_posix(),
            manifest_path.as_posix(),
        ],
    }
    write_canon_json(out_abs / "orch_transition_dataset_build_receipt_v1.json", receipt)

    return {
        "dataset_manifest_id": str(manifest_id),
        "dataset_manifest_path": manifest_path.as_posix(),
        "transition_events_blob_id": str(blob_id),
        "transition_events_blob_path": blob_path.as_posix(),
        "events_included_u64": int(len(events)),
        "runs_scanned_u64": int(runs_scanned),
        "runs_included_u64": int(runs_included),
        "dropped_rows_u64": int(dropped_rows_u64),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orch_transition_dataset_builder_v1")
    parser.add_argument("--runs_root", required=True)
    parser.add_argument("--out_root", required=True)
    parser.add_argument("--ek_id", required=True)
    parser.add_argument("--kernel_ledger_id", required=True)
    parser.add_argument("--max_runs_u64", type=int, default=5000)
    parser.add_argument("--max_events_u64", type=int, default=200000)
    parser.add_argument("--cost_scale_ms_u64", type=int, default=60000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    summary = build_transition_dataset(
        runs_root=Path(str(args.runs_root)).resolve(),
        out_root=Path(str(args.out_root)).resolve(),
        ek_id=str(args.ek_id).strip(),
        kernel_ledger_id=str(args.kernel_ledger_id).strip(),
        max_runs_u64=int(args.max_runs_u64),
        max_events_u64=int(args.max_events_u64),
        cost_scale_ms_u64=int(args.cost_scale_ms_u64),
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
