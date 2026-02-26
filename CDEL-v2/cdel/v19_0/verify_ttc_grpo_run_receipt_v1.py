"""Structural fail-closed verifier for TTC-GRPO run receipts (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, load_canon_dict
from .common_v1 import validate_schema as validate_schema_v19
from ..v18_0.omega_common_v1 import validate_schema as validate_schema_v18

_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _fail(reason: str) -> None:
    text = str(reason).strip() or "SCHEMA_FAIL"
    if not text.startswith("INVALID:"):
        text = f"INVALID:{text}"
    raise OmegaV18Error(text)


def _ensure_sha(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if _SHA_RE.fullmatch(text) is None:
        _fail(f"SCHEMA_FAIL:{field}")
    return text


def _hash_from_filename(path: Path, suffix: str) -> str:
    name = path.name
    if not name.startswith("sha256_") or not name.endswith(suffix):
        _fail("SCHEMA_FAIL:FILENAME")
    digest = name[len("sha256_") : -len(suffix)]
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail("SCHEMA_FAIL:FILENAME")
    return f"sha256:{digest}"


def _resolve_state_root(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_proposer_arena_grpo_ttc_v1" / "state" / "ttc_grpo",
        root / "ttc_grpo",
        root,
    ]
    for candidate in candidates:
        if (candidate / "receipt").exists() and (candidate / "candidate_eval").exists():
            return candidate
    _fail("MISSING_STATE_INPUT")
    return root


def _latest(path: Path, pattern: str) -> Path | None:
    rows = sorted(path.glob(pattern), key=lambda p: p.as_posix())
    return rows[-1] if rows else None


def _find_by_hash(root: Path, *, digest: str, suffix: str) -> Path:
    needle = f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    matches = sorted(root.rglob(needle), key=lambda p: p.as_posix())
    if len(matches) != 1:
        _fail("MISSING_STATE_INPUT")
    return matches[0]


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise OmegaV18Error("INVALID:SCHEMA_FAIL:JSONL") from exc
        if not isinstance(payload, dict):
            _fail("SCHEMA_FAIL:JSONL")
        rows.append(payload)
    return rows


def _mean_q32(values: list[int]) -> int:
    return int(sum(values) // len(values)) if values else 0


def _quantile_q32(values: list[int], *, pct: int) -> int:
    if not values:
        return 0
    rows = sorted(values)
    idx = (len(rows) - 1) * int(pct) // 100
    return int(rows[idx])


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("MODE_UNSUPPORTED")

    state_root = _resolve_state_root(state_dir)

    receipt_path = _latest(state_root / "receipt", "sha256_*.ttc_grpo_run_receipt_v1.json")
    if receipt_path is None:
        _fail("MISSING_STATE_INPUT")
    receipt = load_canon_dict(receipt_path)
    validate_schema_v19(receipt, "ttc_grpo_run_receipt_v1")

    declared_receipt_id = _ensure_sha(receipt.get("id"), field="receipt.id")
    if canon_hash_obj({k: v for k, v in receipt.items() if k != "id"}) != declared_receipt_id:
        _fail("ID_MISMATCH")
    if _hash_from_filename(receipt_path, ".ttc_grpo_run_receipt_v1.json") != declared_receipt_id:
        _fail("NONDETERMINISTIC")

    config_hash = _ensure_sha(receipt.get("config_hash"), field="config_hash")
    config_path = _find_by_hash(state_root / "config", digest=config_hash, suffix="ttc_grpo_run_config_v1.json")
    config = load_canon_dict(config_path)
    validate_schema_v19(config, "ttc_grpo_run_config_v1")
    if _ensure_sha(config.get("id"), field="config.id") != config_hash:
        _fail("NONDETERMINISTIC")
    if canon_hash_obj({k: v for k, v in config.items() if k != "id"}) != config_hash:
        _fail("ID_MISMATCH")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict):
        _fail("SCHEMA_FAIL:artifacts")
    index_hash = _ensure_sha(artifacts.get("candidate_eval_index_jsonl_hash"), field="artifacts.candidate_eval_index_jsonl_hash")
    logs_hash = _ensure_sha(artifacts.get("logs_hash"), field="artifacts.logs_hash")

    index_path = state_root / "indexes" / "candidate_eval_index.ttc_grpo_candidate_eval_index_v1.jsonl"
    if not index_path.exists() or not index_path.is_file():
        _fail("MISSING_STATE_INPUT")
    index_bytes = index_path.read_bytes()
    if _hash_bytes(index_bytes) != index_hash:
        _fail("NONDETERMINISTIC")
    index_rows = _load_jsonl(index_path)
    for row in index_rows:
        validate_schema_v19(row, "ttc_grpo_candidate_eval_index_row_v1")

    if int(receipt.get("num_candidates_u64", -1)) != len(index_rows):
        _fail("NONDETERMINISTIC")

    rewards: list[int] = []
    best_reward = -(1 << 62)
    best_index = 0
    best_ir_hash = "sha256:" + ("0" * 64)
    best_cac_hash = "sha256:" + ("0" * 64)
    num_valid = 0
    num_evaluated = 0

    seen_indexes: set[int] = set()
    for row in index_rows:
        eval_hash = _ensure_sha(row.get("candidate_eval_hash"), field="index.candidate_eval_hash")
        eval_path = _find_by_hash(state_root / "candidate_eval", digest=eval_hash, suffix="ttc_grpo_candidate_eval_v1.json")
        eval_obj = load_canon_dict(eval_path)
        validate_schema_v19(eval_obj, "ttc_grpo_candidate_eval_v1")

        if _ensure_sha(eval_obj.get("id"), field="candidate_eval.id") != eval_hash:
            _fail("NONDETERMINISTIC")
        if canon_hash_obj({k: v for k, v in eval_obj.items() if k != "id"}) != eval_hash:
            _fail("ID_MISMATCH")

        idx = int(eval_obj.get("candidate_index_u64", -1))
        if idx < 0:
            _fail("SCHEMA_FAIL")
        if idx in seen_indexes:
            _fail("NONDETERMINISTIC")
        seen_indexes.add(idx)

        reward_q32 = int(eval_obj.get("reward_q32", 0))
        rewards.append(reward_q32)

        valid_ir = bool(eval_obj.get("valid_ir_b", False))
        candidate_ir_hash = eval_obj.get("candidate_ir_hash")
        cac_hash_row = eval_obj.get("cac_hash")
        plan_hash_row = eval_obj.get("dmpl_plan_result_hash")
        if valid_ir:
            num_valid += 1
        if isinstance(plan_hash_row, str) and isinstance(cac_hash_row, str):
            num_evaluated += 1
            plan_hash = _ensure_sha(plan_hash_row, field="candidate_eval.dmpl_plan_result_hash")
            plan_path = _find_by_hash(state_root / "dmpl" / "plan", digest=plan_hash, suffix="dmpl_action_receipt_v1.json")
            plan_obj = load_canon_dict(plan_path)
            validate_schema_v18(plan_obj, "dmpl_action_receipt_v1")

            cac_hash = _ensure_sha(cac_hash_row, field="candidate_eval.cac_hash")
            cac_path = _find_by_hash(state_root / "dmpl" / "cac", digest=cac_hash, suffix="cac_v1.json")
            cac_obj = load_canon_dict(cac_path)
            validate_schema_v18(cac_obj, "cac_v1")

            if str(cac_obj.get("dmpl_plan_result_hash", "")).strip() != str(plan_hash):
                _fail("NONDETERMINISTIC")
            if isinstance(candidate_ir_hash, str):
                if str(cac_obj.get("candidate_ir_hash", "")).strip() != str(candidate_ir_hash):
                    _fail("NONDETERMINISTIC")

        elif plan_hash_row is not None or cac_hash_row is not None:
            _fail("SCHEMA_FAIL")
        if valid_ir and isinstance(candidate_ir_hash, str) and isinstance(cac_hash_row, str):
            if reward_q32 > best_reward:
                best_reward = int(reward_q32)
                best_index = int(idx)
                best_ir_hash = str(candidate_ir_hash)
                best_cac_hash = str(cac_hash_row)

    expected_indexes = set(range(int(receipt.get("num_candidates_u64", 0))))
    if seen_indexes != expected_indexes:
        _fail("NONDETERMINISTIC")

    if int(receipt.get("num_valid_u64", -1)) != int(num_valid):
        _fail("NONDETERMINISTIC")

    if int(receipt.get("num_evaluated_u64", -1)) != int(num_evaluated):
        _fail("NONDETERMINISTIC")

    best = receipt.get("best")
    if not isinstance(best, dict):
        _fail("SCHEMA_FAIL:best")
    if int(best.get("candidate_index_u64", -1)) != int(best_index):
        _fail("NONDETERMINISTIC")
    if str(best.get("candidate_ir_hash", "")) != str(best_ir_hash):
        _fail("NONDETERMINISTIC")
    if str(best.get("cac_hash", "")) != str(best_cac_hash):
        _fail("NONDETERMINISTIC")
    if int(best.get("reward_q32", 0)) != int(best_reward):
        _fail("NONDETERMINISTIC")

    stats = receipt.get("reward_stats")
    if not isinstance(stats, dict):
        _fail("SCHEMA_FAIL:reward_stats")
    if not rewards:
        rewards = [0]
    if int(stats.get("mean_q32", 0)) != _mean_q32(rewards):
        _fail("NONDETERMINISTIC")
    if int(stats.get("p50_q32", 0)) != _quantile_q32(rewards, pct=50):
        _fail("NONDETERMINISTIC")
    if int(stats.get("p90_q32", 0)) != _quantile_q32(rewards, pct=90):
        _fail("NONDETERMINISTIC")
    if int(stats.get("max_q32", 0)) != int(max(rewards)):
        _fail("NONDETERMINISTIC")

    logs_path = state_root / "logs" / "ttc_grpo_run.log.jsonl"
    if not logs_path.exists() or not logs_path.is_file():
        _fail("MISSING_STATE_INPUT")
    log_bytes = logs_path.read_bytes()
    if _hash_bytes(log_bytes) != logs_hash:
        _fail("NONDETERMINISTIC")
    for row in _load_jsonl(logs_path):
        validate_schema_v19(row, "ttc_grpo_log_row_v1")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_ttc_grpo_run_receipt_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
