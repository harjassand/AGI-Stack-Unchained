"""I/O supervised harness for sealed evaluation."""

from __future__ import annotations

import json
import os
from pathlib import Path

from blake3 import blake3

from cdel.kernel.eval import (
    BoolVal,
    Evaluator,
    EvalError,
    FunVal,
    IntVal,
    ListVal,
    OptionVal,
    PairVal,
    Value,
)
from cdel.sealed.suites import compute_suite_hash_bytes

HARNESS_ID = "io-harness-v1"
HARNESS_HASH = "io-harness-v1-hash"


class IOHarness:
    harness_id = HARNESS_ID
    harness_hash = HARNESS_HASH

    def run_episodes(
        self,
        *,
        eval_cfg: dict,
        defs_env: dict[str, object],
        baseline_symbol: str,
        candidate_symbol: str,
        oracle_symbol: str,
        seed_key: bytes,
        project_root: Path,
        int_min: int,
        int_max: int,
        list_max_len: int,
        fun_symbols: list[str],
        artifact_dir: Path | None,
    ) -> tuple[list[int], int, int, bytes]:
        episodes = eval_cfg["episodes"]
        max_steps = eval_cfg["max_steps"]
        eval_suite_hash = eval_cfg["eval_suite_hash"]

        suites_dir = os.environ.get("CDEL_SUITES_DIR")
        if suites_dir:
            suite_path = Path(suites_dir) / f"{eval_suite_hash}.jsonl"
        else:
            suite_path = project_root / "sealed_suites" / f"{eval_suite_hash}.jsonl"
        try:
            suite_bytes = suite_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"suite file not found: {suite_path}") from exc

        actual_hash = compute_suite_hash_bytes(suite_bytes)
        if actual_hash != eval_suite_hash:
            raise ValueError("suite hash mismatch")

        rows = _parse_suite_rows(suite_bytes)
        if len(rows) < episodes:
            raise ValueError("suite has fewer episodes than requested")

        baseline_successes = 0
        candidate_successes = 0
        diffs: list[int] = []
        artifact_rows: list[dict] | None = [] if artifact_dir is not None else None

        for episode in range(episodes):
            args_raw, target_raw = rows[episode]
            args = [_decode_value(item) for item in args_raw]
            target = _decode_value(target_raw)
            baseline_val = _safe_apply(baseline_symbol, args, defs_env, max_steps)
            candidate_val = _safe_apply(candidate_symbol, args, defs_env, max_steps)
            baseline_success = baseline_val is not None and baseline_val == target
            candidate_success = candidate_val is not None and candidate_val == target
            if baseline_success:
                baseline_successes += 1
            if candidate_success:
                candidate_successes += 1
            diff = int(candidate_success) - int(baseline_success)
            diffs.append(diff)
            if artifact_rows is not None:
                artifact_rows.append(
                    {
                        "episode": episode,
                        "args": args_raw,
                        "target": target_raw,
                        "args_hash": _value_hash(args_raw),
                        "target_hash": _value_hash(target_raw),
                        "baseline_success": baseline_success,
                        "candidate_success": candidate_success,
                        "diff": diff,
                    }
                )

        transcript_bytes = _encode_transcript(eval_suite_hash, episodes, diffs)
        if artifact_dir is not None:
            transcript_hash = blake3(transcript_bytes).hexdigest()
            _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

        return diffs, baseline_successes, candidate_successes, transcript_bytes


def _parse_suite_rows(suite_bytes: bytes) -> list[tuple[list[object], object]]:
    rows: list[tuple[list[object], object]] = []
    for line in suite_bytes.splitlines():
        if not line:
            continue
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("suite row must be object")
        args = payload.get("args")
        if not isinstance(args, list):
            raise ValueError("suite row args must be list")
        if "target" not in payload:
            raise ValueError("suite row target missing")
        target = payload.get("target")
        rows.append((args, target))
    return rows


def _decode_value(raw: object) -> Value:
    if not isinstance(raw, dict):
        raise ValueError("value must be object")
    tag = raw.get("tag")
    if tag == "int":
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("int value must be int")
        return IntVal(value)
    if tag == "bool":
        value = raw.get("value")
        if not isinstance(value, bool):
            raise ValueError("bool value must be bool")
        return BoolVal(value)
    if tag == "list":
        items = raw.get("items")
        if not isinstance(items, list):
            raise ValueError("list items must be list")
        return ListVal(tuple(_decode_value(item) for item in items))
    if tag == "none":
        return OptionVal(False, None)
    if tag == "some":
        if "value" not in raw:
            raise ValueError("some value missing")
        return OptionVal(True, _decode_value(raw["value"]))
    if tag == "pair":
        if "left" not in raw or "right" not in raw:
            raise ValueError("pair missing fields")
        return PairVal(_decode_value(raw["left"]), _decode_value(raw["right"]))
    if tag == "fun":
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("fun name missing")
        return FunVal(name)
    raise ValueError("unknown value tag")


def _safe_apply(symbol: str, args: list[Value], defs: dict, max_steps: int) -> Value | None:
    evaluator = Evaluator(max_steps)
    try:
        return evaluator._apply(FunVal(symbol), args, defs)
    except Exception:
        return None


def _encode_transcript(suite_hash: str, episodes: int, diffs: list[int]) -> bytes:
    payload = {
        "harness_id": HARNESS_ID,
        "suite_hash": suite_hash,
        "episodes": episodes,
        "diffs": diffs,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _value_hash(payload: object) -> str:
    return blake3(_canonical_json(payload)).hexdigest()


def _canonical_json(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
