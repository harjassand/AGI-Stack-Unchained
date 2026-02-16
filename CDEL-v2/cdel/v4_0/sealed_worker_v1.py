"""Sealed evaluation worker for Omega v4.0.

This module is intended to represent the RE2-only evaluation boundary.
It reads request JSON objects (one per line) from stdin and writes response JSON
objects (one per line) to stdout.

Evaluation is deterministic and MUST depend only on:
  - the sealed task record (from the suitepack),
  - the candidate output file,
  - deterministic scoring rules + secret salt material from sealed config.

It MUST NOT depend on counters like epoch/window/global_task_index.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, loads, sha256_prefixed

ROOT_PREFIX = "@ROOT/"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_root_path(path_str: str) -> Path:
    if path_str.startswith(ROOT_PREFIX):
        return _repo_root() / path_str[len(ROOT_PREFIX) :]
    return Path(path_str)


def _sha256_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _salted_hash_v1(*, salt_value: str, text: str) -> str:
    data = salt_value.encode("utf-8") + b"\0" + text.encode("utf-8")
    return sha256_prefixed(data)


def _load_jsonl_canon(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise CanonError("MISSING_ARTIFACT")
    items: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = loads(raw)
        if not isinstance(obj, dict):
            raise CanonError("SCHEMA_INVALID")
        if canon_bytes(obj).decode("utf-8") != raw:
            raise CanonError("CANON_HASH_MISMATCH")
        items.append(obj)
    return items


@dataclass(frozen=True)
class SealedTask:
    task_id: str
    salt_id: str
    answer_hash: str
    eval_type: str


def _parse_task(task: dict[str, Any]) -> SealedTask:
    if task.get("schema") != "sealed_task_v2":
        raise CanonError("SCHEMA_INVALID")
    task_id = task.get("task_id")
    if not isinstance(task_id, str):
        raise CanonError("SCHEMA_INVALID")
    commitment = task.get("answer_commitment") or {}
    salt_id = commitment.get("salt_id")
    answer_hash = commitment.get("answer_hash")
    if not isinstance(salt_id, str) or not isinstance(answer_hash, str):
        raise CanonError("SCHEMA_INVALID")
    eval_cfg = task.get("eval") or {}
    eval_type = eval_cfg.get("type")
    if not isinstance(eval_type, str):
        raise CanonError("SCHEMA_INVALID")
    return SealedTask(task_id=task_id, salt_id=salt_id, answer_hash=answer_hash, eval_type=eval_type)


def _load_suitepack_index(path: Path) -> dict[str, SealedTask]:
    tasks = _load_jsonl_canon(path)
    index: dict[str, SealedTask] = {}
    for row in tasks:
        parsed = _parse_task(row)
        index[parsed.task_id] = parsed
    return index


def _load_sealed_config(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    if not path.exists():
        raise CanonError("MISSING_ARTIFACT")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sealed = data.get("sealed")
    if not isinstance(sealed, dict):
        raise CanonError("SCHEMA_INVALID")
    salts = data.get("salts") or {}
    if not isinstance(salts, dict):
        raise CanonError("SCHEMA_INVALID")
    salt_map: dict[str, str] = {}
    for k, v in salts.items():
        if isinstance(k, str) and isinstance(v, str):
            salt_map[k] = v
    return sealed, salt_map


def _candidate_output_text(candidate_output_path: Path) -> str:
    payload = load_canon_json(candidate_output_path)
    if not isinstance(payload, dict):
        raise CanonError("SCHEMA_INVALID")
    value = payload.get("output")
    if not isinstance(value, str):
        raise CanonError("SCHEMA_INVALID")
    return value


def _evaluate_exact_match(*, task: SealedTask, salt_value: str, candidate_output_path: Path) -> dict[str, Any]:
    output_text = _candidate_output_text(candidate_output_path)
    cand_hash = _salted_hash_v1(salt_value=salt_value, text=output_text)
    verdict = "PASS" if cand_hash == task.answer_hash else "FAIL"
    score_num = 1 if verdict == "PASS" else 0
    score_den = 1
    compute_used = 10
    receipt = {
        "schema": "sealed_eval_receipt_v1",
        "spec_version": "v4_0",
        "task_id": task.task_id,
        "verdict": verdict,
        "score_num": score_num,
        "score_den": score_den,
        "compute_used": compute_used,
        "candidate_hash": cand_hash,
        "answer_hash": task.answer_hash,
    }
    return {
        "verdict": verdict,
        "score_num": score_num,
        "score_den": score_den,
        "compute_used": compute_used,
        "receipt": receipt,
    }


def _serve(*, sealed_config_path: Path) -> None:
    sealed_cfg, salts = _load_sealed_config(sealed_config_path)
    suitepack_path_str = sealed_cfg.get("suitepack_path")
    suitepack_hash_expected = sealed_cfg.get("suitepack_hash")
    if not isinstance(suitepack_path_str, str) or not isinstance(suitepack_hash_expected, str):
        raise CanonError("SCHEMA_INVALID")
    suitepack_path = _resolve_root_path(suitepack_path_str)
    if not suitepack_path.exists():
        raise CanonError("MISSING_ARTIFACT")
    if _sha256_file(suitepack_path) != suitepack_hash_expected:
        raise CanonError("CANON_HASH_MISMATCH")

    suite_index = _load_suitepack_index(suitepack_path)

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        req = json.loads(raw)
        if not isinstance(req, dict):
            raise CanonError("SCHEMA_INVALID")
        task_id = req.get("task_id")
        candidate_path = req.get("candidate_output_path")
        if not isinstance(task_id, str) or not isinstance(candidate_path, str):
            raise CanonError("SCHEMA_INVALID")
        task = suite_index.get(task_id)
        if task is None:
            raise CanonError("SCHEMA_INVALID")
        salt_value = salts.get(task.salt_id)
        if not isinstance(salt_value, str):
            raise CanonError("SCHEMA_INVALID")
        out = _evaluate_exact_match(task=task, salt_value=salt_value, candidate_output_path=Path(candidate_path))
        sys.stdout.write(json.dumps(out, separators=(",", ":"), ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sealed_config_path", required=True)
    args = parser.parse_args()
    try:
        _serve(sealed_config_path=Path(args.sealed_config_path))
    except CanonError as exc:
        # Fail closed: emit nothing further (verifier should treat as missing receipt).
        sys.stderr.write(f"sealed_worker_error: {exc}\n")
        sys.stderr.flush()
        sys.exit(2)


if __name__ == "__main__":
    main()

