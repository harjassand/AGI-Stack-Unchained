#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import hash_file_stream, load_canon_dict
from cdel.v19_0.common_v1 import canon_hash_obj, validate_schema

from tools.macro_miner.operator_bank_store_v1 import (
    utc_now_rfc3339,
    write_operator_bank,
    write_operator_bank_pointer,
)


_TOKEN_RE = re.compile(r"^OP_[A-Z0-9_]{3,64}$")
_MIN_LEN = 4
_MAX_LEN = 24
_TOP_K = 64
_MAX_MACROS = 32
_MIN_COUNT = 2


@dataclass(frozen=True)
class Candidate:
    candidate_ir_hash: str
    reward_q32: int


@dataclass
class WindowStats:
    count_u64: int
    reward_sum_q64: int
    reward_max_q32: int
    norm: list[dict[str, Any]]
    sample_window: list[dict[str, Any]]
    sample_ops: list[str]
    sample_ir_hash: str


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha_obj(obj: Any) -> str:
    return "sha256:" + __import__("hashlib").sha256(_canon_bytes(obj)).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _parse_candidates(path: Path) -> list[Candidate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        rows = list(payload.get("candidates") or [])
    else:
        raise RuntimeError("SCHEMA_FAIL:candidates")
    out: list[Candidate] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:candidate_row")
        c_hash = str(row.get("candidate_ir_hash", "")).strip()
        if not _is_sha256(c_hash):
            raise RuntimeError("SCHEMA_FAIL:candidate_ir_hash")
        reward = int(row.get("reward_q32", 0))
        out.append(Candidate(candidate_ir_hash=c_hash, reward_q32=reward))
    out.sort(key=lambda c: c.candidate_ir_hash)
    return out


def _find_ir_by_hash(*, ir_root: Path, digest: str) -> Path:
    hex64 = digest.split(":", 1)[1]
    direct = ir_root / f"sha256_{hex64}.polymath_restricted_ir_v1.json"
    if direct.exists() and direct.is_file():
        return direct.resolve()
    matches = sorted(ir_root.rglob(f"sha256_{hex64}.polymath_restricted_ir_v1.json"), key=lambda p: p.as_posix())
    if len(matches) != 1:
        raise RuntimeError(f"MISSING_STATE_INPUT:ir:{digest}")
    return matches[0].resolve()


def _load_ops_from_ir(path: Path) -> list[dict[str, Any]]:
    payload = load_canon_dict(path)
    schema_version = str(payload.get("schema_version", "")).strip()
    schema_id = str(payload.get("schema_id", "")).strip()
    ops_raw: Any
    mode: str
    if schema_version == "polymath_restricted_ir_v1" and isinstance(payload.get("operations"), list):
        ops_raw = payload.get("operations")
        mode = "legacy"
    elif schema_id == "polymath_restricted_ir_v1" and isinstance(payload.get("ops"), list):
        ops_raw = payload.get("ops")
        mode = "compact"
    else:
        raise RuntimeError("SCHEMA_FAIL:polymath_restricted_ir_v1")

    out: list[dict[str, Any]] = []
    for row in list(ops_raw or []):
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:operation_row")
        op = str(row.get("op", "")).strip()
        if not op:
            raise RuntimeError("SCHEMA_FAIL:operation")

        args_raw = row.get("args")
        args: list[int]
        if isinstance(args_raw, list):
            args = [int(v) for v in args_raw]
        elif mode == "legacy":
            raise RuntimeError("SCHEMA_FAIL:operation_args")
        elif mode == "compact":
            if op == "ARG":
                if row.get("idx") is None:
                    raise RuntimeError("SCHEMA_FAIL:operation_args")
                args = [int(row.get("idx"))]
            elif op == "CONST":
                if row.get("value_q32") is None:
                    raise RuntimeError("SCHEMA_FAIL:operation_args")
                args = [int(row.get("value_q32"))]
            elif op == "RET" and row.get("idx") is not None:
                args = [int(row.get("idx"))]
            else:
                args = []
        else:
            args = []

        out.append({"op": op, "args": args})
    return out


def _normalize_window_v1(window: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in window:
        op = str(row.get("op", "")).strip()
        args = list(row.get("args") or [])
        if op == "CONST" and len(args) == 1:
            out.append({"op": op, "args": ["CONST_PLACEHOLDER"]})
        else:
            out.append({"op": op, "args": [int(v) for v in args]})
    return out


def _window_ops(window: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("op", "")).strip() for row in window]


def _compression_gain_q16(length_u64: int) -> int:
    if length_u64 <= 0:
        return 0
    return max(0, int(((int(length_u64) - 1) << 16) // int(length_u64)))


def _score_q32(*, avg_reward_q32: int, count_u64: int, gain_q16: int) -> int:
    count_q32 = int(count_u64) << 32
    weighted = (int(avg_reward_q32) * int(count_q32)) >> 32
    return int(weighted) + (int(gain_q16) << 16)


def _is_subsequence(small: list[str], big: list[str]) -> bool:
    if not small:
        return True
    if len(small) > len(big):
        return False
    limit = len(big) - len(small) + 1
    for i in range(0, limit):
        if big[i : i + len(small)] == small:
            return True
    return False


def _violates_overlap_policy(candidate_ops: list[str], selected_ops: list[list[str]]) -> bool:
    for existing in selected_ops:
        if _is_subsequence(candidate_ops, existing):
            return True
    return False


def _macro_arity(window: list[dict[str, Any]]) -> int:
    arg_idxs: list[int] = []
    for row in window:
        if str(row.get("op", "")) != "ARG":
            continue
        args = row.get("args")
        if isinstance(args, list) and len(args) == 1:
            arg_idxs.append(int(args[0]))
    return int(max(arg_idxs) + 1) if arg_idxs else 0


def _materialize_macro(*, key: str, index_u64: int, stats: WindowStats) -> dict[str, Any]:
    arity = _macro_arity(stats.sample_window)
    placeholders = [f"ARG{i}" for i in range(arity)]
    token = f"OP_MACRO_{int(index_u64):03d}_{key.split(':', 1)[1][:8].upper()}"
    if _TOKEN_RE.fullmatch(token) is None:
        raise RuntimeError("SCHEMA_FAIL:macro_token")

    expansion_ops: list[dict[str, Any]] = []
    for row in stats.sample_window:
        op = str(row.get("op", "")).strip()
        args = [int(v) for v in list(row.get("args") or [])]
        expansion_ops.append({"op": op, "args": args})

    count = int(stats.count_u64)
    avg_q32 = int(stats.reward_sum_q64 // max(1, count))
    gain_q16 = _compression_gain_q16(len(stats.sample_window))

    macro = {
        "macro_id": "sha256:" + ("0" * 64),
        "token": token,
        "description": f"Mined macro from {stats.sample_ir_hash} (window_len={len(stats.sample_window)})",
        "arity_u64": int(arity),
        "placeholders": placeholders,
        "expansion_ir": {
            "schema_id": "polymath_restricted_ir_v1",
            "numeric_mode": "Q32",
            "ops": expansion_ops,
        },
        "mined_stats": {
            "count_u64": count,
            "avg_reward_q32": avg_q32,
            "compression_gain_q16": gain_q16,
        },
    }
    macro["macro_id"] = canon_hash_obj({k: v for k, v in macro.items() if k != "macro_id"})
    return macro


def mine_macros_v1(*, candidates: list[Candidate], ir_root: Path, created_at_utc: str | None = None) -> dict[str, Any]:
    stats: dict[str, WindowStats] = {}

    for cand in sorted(candidates, key=lambda c: c.candidate_ir_hash):
        ir_path = _find_ir_by_hash(ir_root=ir_root, digest=cand.candidate_ir_hash)
        ops = _load_ops_from_ir(ir_path)
        max_len = min(_MAX_LEN, len(ops))
        for length in range(_MIN_LEN, max_len + 1):
            for i in range(0, len(ops) - length + 1):
                window = ops[i : i + length]
                norm = _normalize_window_v1(window)
                key = _sha_obj(norm)
                row = stats.get(key)
                if row is None:
                    stats[key] = WindowStats(
                        count_u64=1,
                        reward_sum_q64=int(cand.reward_q32),
                        reward_max_q32=int(cand.reward_q32),
                        norm=norm,
                        sample_window=[dict(x) for x in window],
                        sample_ops=_window_ops(window),
                        sample_ir_hash=cand.candidate_ir_hash,
                    )
                else:
                    row.count_u64 = int(row.count_u64) + 1
                    row.reward_sum_q64 = int(row.reward_sum_q64) + int(cand.reward_q32)
                    row.reward_max_q32 = max(int(row.reward_max_q32), int(cand.reward_q32))
                    if cand.candidate_ir_hash < row.sample_ir_hash:
                        row.sample_ir_hash = cand.candidate_ir_hash
                        row.sample_window = [dict(x) for x in window]
                        row.sample_ops = _window_ops(window)

    scored: list[tuple[int, str, WindowStats]] = []
    for key, row in stats.items():
        if int(row.count_u64) < _MIN_COUNT:
            continue
        avg_q32 = int(row.reward_sum_q64 // int(row.count_u64))
        gain_q16 = _compression_gain_q16(len(row.sample_window))
        score = _score_q32(avg_reward_q32=avg_q32, count_u64=int(row.count_u64), gain_q16=gain_q16)
        scored.append((int(score), str(key), row))

    scored.sort(key=lambda x: (-int(x[0]), str(x[1])))
    scored = scored[:_TOP_K]

    macros: list[dict[str, Any]] = []
    selected_ops: list[list[str]] = []
    for _score, key, row in scored:
        if len(macros) >= _MAX_MACROS:
            break
        if _violates_overlap_policy(row.sample_ops, selected_ops):
            continue
        macro = _materialize_macro(key=key, index_u64=len(macros), stats=row)
        macros.append(macro)
        selected_ops.append(list(row.sample_ops))

    bank = {
        "schema_id": "oracle_operator_bank_v1",
        "id": "sha256:" + ("0" * 64),
        "created_at_utc": str(created_at_utc or utc_now_rfc3339()),
        "bank_version_u64": 1,
        "macros": macros,
    }
    bank["id"] = canon_hash_obj({k: v for k, v in bank.items() if k != "id"})
    validate_schema(bank, "oracle_operator_bank_v1")
    return bank


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="macro_miner_v1")
    ap.add_argument("--candidates_json", required=True)
    ap.add_argument("--ir_root", default=".")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--created_at_utc", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    candidates = _parse_candidates(Path(args.candidates_json).resolve())
    bank = mine_macros_v1(
        candidates=candidates,
        ir_root=Path(args.ir_root).resolve(),
        created_at_utc=(str(args.created_at_utc).strip() or None),
    )

    out_dir = Path(args.out_dir).resolve()
    bank_dir = out_dir / "bank"
    pointer_dir = out_dir / "pointer"
    bank_path, bank_obj, bank_hash = write_operator_bank(out_dir=bank_dir, bank_payload=bank)

    write_operator_bank_pointer(
        pointer_dir=pointer_dir,
        bank_hash=bank_hash,
        bank_relpath=bank_path.as_posix(),
        created_at_utc=str(bank_obj.get("created_at_utc", utc_now_rfc3339())),
        bank_version_u64=int(bank_obj.get("bank_version_u64", 1)),
    )

    summary = {
        "schema_version": "macro_miner_summary_v1",
        "bank_hash": bank_hash,
        "bank_path": bank_path.as_posix(),
        "bank_file_hash": hash_file_stream(bank_path),
        "macro_count_u64": int(len(list(bank_obj.get("macros") or []))),
        "candidate_count_u64": int(len(candidates)),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
