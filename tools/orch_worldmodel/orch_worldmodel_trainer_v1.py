#!/usr/bin/env python3
"""Train deterministic orchestration world-model policy tables (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj

from tools.orch_worldmodel.orch_worldmodel_math_q32_v1 import (
    Q32_HALF,
    Q32_ONE,
    q32_mean_from_sum,
    q32_mul,
    q32_ratio_u64,
)


_DEFAULT_MAX_CONTEXTS_U32 = 256
_DEFAULT_MAX_ACTIONS_U32 = 64
_DEFAULT_HORIZON_U32 = 3
_DEFAULT_DISCOUNT_Q32 = 3865470566
_DEFAULT_PLANNER_KIND = "TABULAR_MPC_V1"
_DEFAULT_SEED_U64 = 0
_MAX_RANKED_ACTIONS_U32 = 16


class TrainError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise TrainError(str(reason))


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TrainError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception as exc:
            raise TrainError("SCHEMA_FAIL") from exc
        if not isinstance(payload, dict):
            _fail("SCHEMA_FAIL")
        out.append(payload)
    return out


def _resolve_rel_or_abs(path_value: str, *, repo_root: Path) -> Path:
    raw = str(path_value).strip()
    if not raw:
        _fail("MISSING_STATE_INPUT")
    p = Path(raw)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (repo_root / p).resolve()
    if not resolved.exists() or not resolved.is_file():
        _fail("MISSING_STATE_INPUT")
    return resolved


def _normalize_train_config(raw: dict[str, Any]) -> dict[str, Any]:
    if str(raw.get("schema_version", "")).strip() not in {"", "orch_worldmodel_train_config_v1"}:
        _fail("SCHEMA_FAIL")

    planner_kind = str(raw.get("planner_kind", _DEFAULT_PLANNER_KIND)).strip() or _DEFAULT_PLANNER_KIND
    if planner_kind not in {"TABULAR_MPC_V1", "NEURAL_MPC_V1"}:
        _fail("SCHEMA_FAIL")

    cfg = {
        "schema_version": "orch_worldmodel_train_config_v1",
        "max_contexts_u32": int(max(1, int(raw.get("max_contexts_u32", _DEFAULT_MAX_CONTEXTS_U32)))),
        "max_actions_u32": int(max(1, int(raw.get("max_actions_u32", _DEFAULT_MAX_ACTIONS_U32)))),
        "horizon_u32": int(max(1, int(raw.get("horizon_u32", _DEFAULT_HORIZON_U32)))),
        "discount_q32": int(max(0, min(Q32_ONE, int(raw.get("discount_q32", _DEFAULT_DISCOUNT_Q32))))),
        "planner_kind": planner_kind,
        "seed_u64": int(max(0, int(raw.get("seed_u64", _DEFAULT_SEED_U64)))),
    }
    return cfg


def _event_key(event: dict[str, Any]) -> tuple[str, str]:
    context_key = str(event.get("context_key", "")).strip()
    action_capability_id = str(event.get("action_capability_id", "")).strip()
    if not context_key or not action_capability_id:
        _fail("SCHEMA_FAIL")
    return context_key, action_capability_id


def _build_tabular_model(
    *,
    events: list[dict[str, Any]],
    max_contexts_u32: int,
    max_actions_u32: int,
) -> tuple[dict[str, dict[str, dict[str, Any]]], set[str]]:
    model: dict[str, dict[str, dict[str, Any]]] = {}
    all_actions: set[str] = set()

    for event in events:
        if str(event.get("schema_version", "")).strip() != "orch_transition_event_v1":
            _fail("SCHEMA_FAIL")
        context_key, action_capability_id = _event_key(event)
        next_context_key = str(event.get("next_context_key", "")).strip()
        if not next_context_key:
            _fail("SCHEMA_FAIL")

        if context_key not in model and len(model) >= int(max_contexts_u32):
            _fail("FAIL:MAX_CONTEXTS")
        context_row = model.setdefault(context_key, {})
        if action_capability_id not in context_row and len(context_row) >= int(max_actions_u32):
            _fail("FAIL:MAX_ACTIONS")

        action_stats = context_row.setdefault(
            action_capability_id,
            {
                "count_u64": 0,
                "reward_sum_q64": 0,
                "toxic_sum_u64": 0,
                "next_counts": {},
            },
        )
        action_stats["count_u64"] = int(action_stats.get("count_u64", 0)) + 1
        action_stats["reward_sum_q64"] = int(action_stats.get("reward_sum_q64", 0)) + int(event.get("reward_q32", 0))
        action_stats["toxic_sum_u64"] = int(action_stats.get("toxic_sum_u64", 0)) + (1 if bool(event.get("toxic_fail_b", False)) else 0)

        next_counts = action_stats.get("next_counts")
        if not isinstance(next_counts, dict):
            _fail("SCHEMA_FAIL")
        next_counts[next_context_key] = int(next_counts.get(next_context_key, 0)) + 1
        if len(next_counts) > int(max_contexts_u32):
            _fail("FAIL:MAX_CONTEXTS")

        all_actions.add(action_capability_id)

    summarized: dict[str, dict[str, dict[str, Any]]] = {}
    for context_key in sorted(model.keys()):
        summarized[context_key] = {}
        action_rows = model[context_key]
        for action_capability_id in sorted(action_rows.keys()):
            stats = action_rows[action_capability_id]
            count = int(max(1, int(stats.get("count_u64", 0))))
            reward_sum = int(stats.get("reward_sum_q64", 0))
            toxic_sum = int(max(0, int(stats.get("toxic_sum_u64", 0))))
            next_counts = stats.get("next_counts")
            if not isinstance(next_counts, dict):
                _fail("SCHEMA_FAIL")

            next_rows = sorted(
                [(str(key), int(value)) for key, value in next_counts.items() if str(key).strip()],
                key=lambda row: (-int(row[1]), str(row[0])),
            )
            next_top1 = str(next_rows[0][0]) if next_rows else ""

            summarized[context_key][action_capability_id] = {
                "count_u64": int(count),
                "mean_reward_q32": int(q32_mean_from_sum(sum_q32=reward_sum, count_u64=count)),
                "mean_toxic_fail_q32": int(q32_ratio_u64(numer_u64=toxic_sum, denom_u64=count)),
                "next_top1_context_key": str(next_top1),
            }

    return summarized, all_actions


def _expected_returns_q32(
    *,
    model: dict[str, dict[str, dict[str, Any]]],
    horizon_u32: int,
    discount_q32: int,
) -> dict[tuple[str, str], int]:
    value_prev: dict[str, int] = {context_key: 0 for context_key in model.keys()}
    q_last: dict[tuple[str, str], int] = {}

    for _step in range(1, int(horizon_u32) + 1):
        q_step: dict[tuple[str, str], int] = {}
        value_curr: dict[str, int] = {}
        for context_key in sorted(model.keys()):
            best_q: int | None = None
            for action_capability_id in sorted(model[context_key].keys()):
                row = model[context_key][action_capability_id]
                immediate_q32 = int(row.get("mean_reward_q32", 0))
                next_context_key = str(row.get("next_top1_context_key", "")).strip()
                future_q32 = int(value_prev.get(next_context_key, 0)) if next_context_key else 0
                q_val = int(immediate_q32) + int(q32_mul(int(discount_q32), int(future_q32)))
                q_step[(context_key, action_capability_id)] = int(q_val)
                if best_q is None or int(q_val) > int(best_q):
                    best_q = int(q_val)
            value_curr[context_key] = int(best_q if best_q is not None else 0)
        value_prev = value_curr
        q_last = q_step

    return q_last


def _compile_policy_table(
    *,
    model: dict[str, dict[str, dict[str, Any]]],
    expected_return_q32: dict[tuple[str, str], int],
    ek_id: str,
    kernel_ledger_id: str,
) -> dict[str, Any]:
    context_rows: list[dict[str, Any]] = []

    for context_key in sorted(model.keys()):
        ranked_actions: list[dict[str, Any]] = []
        for action_capability_id in sorted(model[context_key].keys()):
            row = model[context_key][action_capability_id]
            toxic_prob_q32 = int(row.get("mean_toxic_fail_q32", 0))
            expected_q32 = int(expected_return_q32.get((context_key, action_capability_id), 0))
            toxic_penalty_q32 = int(q32_mul(Q32_HALF, toxic_prob_q32))
            score_q32 = int(expected_q32) - int(toxic_penalty_q32)
            ranked_actions.append(
                {
                    "capability_id": str(action_capability_id),
                    "score_q32": int(score_q32),
                }
            )

        ranked_actions.sort(key=lambda row: (-int(row.get("score_q32", 0)), str(row.get("capability_id", ""))))
        ranked_actions = ranked_actions[:_MAX_RANKED_ACTIONS_U32]
        context_rows.append(
            {
                "context_key": str(context_key),
                "ranked_actions": ranked_actions,
            }
        )

    policy_no_id = {
        "schema_version": "orch_policy_table_v1",
        "ek_id": str(ek_id),
        "kernel_ledger_id": str(kernel_ledger_id),
        "mode": "ADD_BONUS_V1",
        "context_rows": context_rows,
        "defaults": {
            "unknown_context_bonus_q32": 0,
            "max_ranked_actions_u32": _MAX_RANKED_ACTIONS_U32,
        },
    }
    policy = dict(policy_no_id)
    policy["policy_id"] = str(canon_hash_obj(policy_no_id))
    return policy


def train_worldmodel_policy(
    *,
    dataset_manifest_path: Path,
    train_config_path: Path,
    out_dir: Path,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = (repo_root or _REPO_ROOT).resolve()
    manifest = _load_json(dataset_manifest_path.resolve())
    if str(manifest.get("schema_version", "")).strip() != "orch_transition_dataset_manifest_v1":
        _fail("SCHEMA_FAIL")

    manifest_id = str(manifest.get("dataset_manifest_id", "")).strip()
    if not _is_sha256(manifest_id):
        _fail("SCHEMA_FAIL")

    train_config_raw = _load_json(train_config_path.resolve())
    train_config = _normalize_train_config(train_config_raw)
    train_config_id = str(canon_hash_obj(train_config))

    planner_kind = str(train_config.get("planner_kind", _DEFAULT_PLANNER_KIND))
    if planner_kind == "NEURAL_MPC_V1":
        _fail("FAIL:NEURAL_NOT_ENABLED")
    if planner_kind != "TABULAR_MPC_V1":
        _fail("SCHEMA_FAIL")

    relpath = str(manifest.get("transition_events_relpath", "")).strip()
    events_path = _resolve_rel_or_abs(relpath, repo_root=root)
    declared_blob_id = str(manifest.get("transition_events_blob_id", "")).strip()
    if not _is_sha256(declared_blob_id):
        _fail("SCHEMA_FAIL")
    observed_blob_id = "sha256:" + hashlib_sha256_file(events_path)
    if declared_blob_id != observed_blob_id:
        _fail("BLOB_HASH_MISMATCH")

    events = _load_jsonl(events_path)
    model, all_actions = _build_tabular_model(
        events=events,
        max_contexts_u32=int(train_config["max_contexts_u32"]),
        max_actions_u32=int(train_config["max_actions_u32"]),
    )

    expected_return_q32 = _expected_returns_q32(
        model=model,
        horizon_u32=int(train_config["horizon_u32"]),
        discount_q32=int(train_config["discount_q32"]),
    )

    policy = _compile_policy_table(
        model=model,
        expected_return_q32=expected_return_q32,
        ek_id=str(manifest.get("ek_id", "")),
        kernel_ledger_id=str(manifest.get("kernel_ledger_id", "")),
    )

    out_abs = out_dir.resolve()
    out_abs.mkdir(parents=True, exist_ok=True)
    policy_path = out_abs / "orch_policy_table_v1.json"
    write_canon_json(policy_path, policy)

    receipt = {
        "schema_version": "orch_worldmodel_train_receipt_v1",
        "status": "OK",
        "reason_code": "OK",
        "train_config_id": str(train_config_id),
        "transition_dataset_manifest_id": str(manifest_id),
        "policy_table_id": str(policy.get("policy_id", "")),
        "planner_kind": str(planner_kind),
        "contexts_u32": int(len(model)),
        "actions_u32": int(len(all_actions)),
        "rows_written_u32": int(len(list(policy.get("context_rows") or []))),
        "output_paths": [policy_path.as_posix()],
    }
    receipt_path = out_abs / "orch_worldmodel_train_receipt_v1.json"
    write_canon_json(receipt_path, receipt)

    return {
        "train_config_id": str(train_config_id),
        "transition_dataset_manifest_id": str(manifest_id),
        "policy_table_id": str(policy.get("policy_id", "")),
        "policy_table_path": policy_path.as_posix(),
        "train_receipt_path": receipt_path.as_posix(),
    }


def hashlib_sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="orch_worldmodel_trainer_v1")
    parser.add_argument("--dataset_manifest", required=True)
    parser.add_argument("--train_config", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    summary = train_worldmodel_policy(
        dataset_manifest_path=Path(str(args.dataset_manifest)).resolve(),
        train_config_path=Path(str(args.train_config)).resolve(),
        out_dir=Path(str(args.out_dir)).resolve(),
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
