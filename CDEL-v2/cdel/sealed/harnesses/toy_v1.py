"""Toy harness implementation for sealed evaluation."""

from __future__ import annotations

import json
import random
from hashlib import blake2b
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
from cdel.kernel.types import BOOL, INT, FunType, ListType, OptionType, PairType, Type

HARNESS_ID = "toy-harness-v1"
HARNESS_HASH = "harness-hash"


class ToyHarness:
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
        oracle_def = defs_env[oracle_symbol]

        baseline_successes = 0
        candidate_successes = 0
        diffs: list[int] = []
        artifact_rows: list[dict] | None = [] if artifact_dir is not None else None
        for episode in range(episodes):
            rng = random.Random(_episode_seed(seed_key, baseline_symbol, candidate_symbol, oracle_symbol, episode))
            args = [
                _random_value(param.typ, rng, int_min, int_max, list_max_len, fun_symbols)
                for param in oracle_def.params
            ]
            oracle_val = _safe_apply(oracle_symbol, args, defs_env, max_steps)
            baseline_val = _safe_apply(baseline_symbol, args, defs_env, max_steps)
            candidate_val = _safe_apply(candidate_symbol, args, defs_env, max_steps)
            baseline_correct = oracle_val is not None and baseline_val == oracle_val
            candidate_correct = oracle_val is not None and candidate_val == oracle_val
            if baseline_correct:
                baseline_successes += 1
            if candidate_correct:
                candidate_successes += 1
            diff = int(candidate_correct) - int(baseline_correct)
            diffs.append(diff)
            if artifact_rows is not None:
                artifact_rows.append(
                    {
                        "episode": episode,
                        "baseline_correct": baseline_correct,
                        "candidate_correct": candidate_correct,
                        "diff": diff,
                    }
                )

        transcript_bytes = _encode_diffs(diffs)
        if artifact_dir is not None:
            transcript_hash = blake3(transcript_bytes).hexdigest()
            _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

        return diffs, baseline_successes, candidate_successes, transcript_bytes


def _safe_apply(symbol: str, args: list[Value], defs: dict, max_steps: int) -> Value | None:
    evaluator = Evaluator(max_steps)
    try:
        return evaluator._apply(FunVal(symbol), args, defs)
    except (EvalError, ValueError):
        return None


def _random_value(
    typ: Type,
    rng: random.Random,
    int_min: int,
    int_max: int,
    list_max_len: int,
    fun_symbols: list[str],
) -> Value:
    if typ == INT:
        return IntVal(rng.randint(int_min, int_max))
    if typ == BOOL:
        return BoolVal(bool(rng.randint(0, 1)))
    if isinstance(typ, ListType):
        length = rng.randint(0, max(0, list_max_len))
        items = tuple(
            _random_value(typ.elem, rng, int_min, int_max, list_max_len, fun_symbols) for _ in range(length)
        )
        return ListVal(items)
    if isinstance(typ, OptionType):
        if rng.randint(0, 1) == 0:
            return OptionVal(False, None)
        return OptionVal(True, _random_value(typ.elem, rng, int_min, int_max, list_max_len, fun_symbols))
    if isinstance(typ, PairType):
        left = _random_value(typ.left, rng, int_min, int_max, list_max_len, fun_symbols)
        right = _random_value(typ.right, rng, int_min, int_max, list_max_len, fun_symbols)
        return PairVal(left, right)
    if isinstance(typ, FunType):
        if not fun_symbols:
            raise ValueError("eval fun_symbols required for function arguments")
        return FunVal(rng.choice(fun_symbols))
    raise ValueError(f"unsupported argument type: {typ}")


def _episode_seed(seed_key: bytes, baseline: str, candidate: str, oracle: str, episode: int) -> int:
    h = blake2b(seed_key, digest_size=8)
    h.update(baseline.encode("utf-8"))
    h.update(candidate.encode("utf-8"))
    h.update(oracle.encode("utf-8"))
    h.update(episode.to_bytes(8, "big"))
    return int.from_bytes(h.digest(), "big")


def _encode_diffs(diffs: list[int]) -> bytes:
    return "\n".join(str(d) for d in diffs).encode("utf-8")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
