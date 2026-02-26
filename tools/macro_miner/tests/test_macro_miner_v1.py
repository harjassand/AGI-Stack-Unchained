from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.macro_miner.macro_miner_v1 import Candidate, mine_macros_v1
from tools.macro_miner.operator_bank_runtime_v1 import MacroRuntimeError, expand_macros


def _canon_bytes(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_mine_macros_accepts_compact_stack_ops(tmp_path: Path) -> None:
    ir_payload = {
        "schema_id": "polymath_restricted_ir_v1",
        "numeric_mode": "Q32",
        "ops": [
            {"op": "ARG", "idx": 0},
            {"op": "ARG", "idx": 1},
            {"op": "MUL_Q32"},
            {"op": "CONST", "value_q32": 5},
            {"op": "ADD_I64"},
            {"op": "RET"},
        ],
    }
    ir_hash = "sha256:" + hashlib.sha256(_canon_bytes(ir_payload)).hexdigest()
    ir_root = tmp_path / "ir"
    ir_root.mkdir(parents=True, exist_ok=True)
    ir_path = ir_root / f"sha256_{ir_hash.split(':', 1)[1]}.polymath_restricted_ir_v1.json"
    ir_path.write_bytes(_canon_bytes(ir_payload))

    bank = mine_macros_v1(
        candidates=[
            Candidate(candidate_ir_hash=ir_hash, reward_q32=10),
            Candidate(candidate_ir_hash=ir_hash, reward_q32=20),
        ],
        ir_root=ir_root,
        created_at_utc="2026-02-26T00:00:00Z",
    )

    assert bank["schema_id"] == "oracle_operator_bank_v1"
    assert str(bank["id"]).startswith("sha256:")
    assert isinstance(bank["macros"], list)


def test_expand_macros_fails_closed_on_unknown_token() -> None:
    bank = {
        "schema_id": "oracle_operator_bank_v1",
        "id": "sha256:" + ("0" * 64),
        "created_at_utc": "2026-02-26T00:00:00Z",
        "bank_version_u64": 1,
        "macros": [],
    }
    bank["id"] = "sha256:" + hashlib.sha256(_canon_bytes({k: v for k, v in bank.items() if k != "id"})).hexdigest()

    ir_payload = {
        "schema_id": "polymath_restricted_ir_v1",
        "numeric_mode": "Q32",
        "ops": [
            {"op": "OP_DOES_NOT_EXIST", "args": [1, 2]},
            {"op": "RET"},
        ],
    }
    with pytest.raises(MacroRuntimeError, match="UNKNOWN_MACRO_TOKEN"):
        expand_macros(ir_payload, bank)

