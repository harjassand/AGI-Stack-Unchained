from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v19_0.common_v1 import OmegaV19Error
from cdel.v19_0.verify_coordinator_opcode_table_v1 import verify_opcode_table


def _sha(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def test_verify_opcode_table_lifecycle_entries_sorted_and_unique() -> None:
    payload = {
        "schema_version": "coordinator_opcode_table_v1",
        "isa_version": 1,
        "opcode_table_id": "sha256:" + ("0" * 64),
        "table_id": "sha256:" + ("1" * 64),
        "entries": [
            {
                "opcode_u16": 1,
                "opcode_name": "EMIT_PLAN",
                "kind": "BUILTIN",
                "active_b": True,
                "impl": {"impl_kind": "BUILTIN", "module_id": "policy_vm_v1", "function_id": "emit_plan"},
                "introduced_tick_u64": 1,
                "deprecated_tick_u64": 0,
            },
            {
                "opcode_u16": 2,
                "opcode_name": "NOP",
                "kind": "BUILTIN",
                "active_b": True,
                "impl": {"impl_kind": "BUILTIN", "module_id": "policy_vm_v1", "function_id": "nop"},
                "introduced_tick_u64": 1,
                "deprecated_tick_u64": 0,
            },
        ],
        "forbidden_in_phase1": [],
    }
    no_id = dict(payload)
    no_id.pop("opcode_table_id", None)
    payload["opcode_table_id"] = _sha(no_id)
    assert verify_opcode_table(payload) == "VALID"


def test_verify_opcode_table_active_native_requires_blob_present() -> None:
    payload = {
        "schema_version": "coordinator_opcode_table_v1",
        "isa_version": 1,
        "opcode_table_id": "sha256:" + ("0" * 64),
        "table_id": "sha256:" + ("1" * 64),
        "entries": [
            {
                "opcode_u16": 100,
                "opcode_name": "NATIVE_TEST",
                "kind": "NATIVE",
                "active_b": True,
                "impl": {
                    "impl_kind": "NATIVE",
                    "op_id": "omega.native.test",
                    "binary_sha256": "sha256:" + ("f" * 64),
                    "abi_version_u32": 1,
                    "healthcheck_id": "sha256:" + ("e" * 64),
                },
                "introduced_tick_u64": 1,
                "deprecated_tick_u64": 0,
            }
        ],
        "forbidden_in_phase1": [],
    }
    no_id = dict(payload)
    no_id.pop("opcode_table_id", None)
    payload["opcode_table_id"] = _sha(no_id)

    with pytest.raises(OmegaV19Error) as exc:
        verify_opcode_table(payload)
    assert str(exc.value) == "MISSING_STATE_INPUT"
