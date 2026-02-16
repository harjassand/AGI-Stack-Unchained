from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api_v1 import canonical_json_bytes  # noqa: E402
from sleep.synth.guided_program_order_v1_2 import order_programs  # noqa: E402


def _program(ops: list[dict]) -> dict:
    return {
        "format": "bounded_program_v1",
        "schema_version": 1,
        "inputs": [
            {"name": "o_t", "type": "bitvec", "width": 4},
            {"name": "o_t_minus_1", "type": "bitvec", "width": 4},
        ],
        "outputs": [{"name": "x", "type": "bit"}],
        "ops": ops,
        "max_ops": 16,
    }


def test_guided_program_order_determinism_v1_2() -> None:
    fixture_path = BASE_DIR / "tests" / "fixtures" / "anomaly_buffer_guided_order_v1_2.json"
    anomaly_buffer = json.loads(fixture_path.read_text(encoding="utf-8"))

    prog_a = _program(
        [
            {"dst": "cur", "op": "SELECT_BIT", "args": ["o_t", 1]},
            {"dst": "prev", "op": "SELECT_BIT", "args": ["o_t_minus_1", 1]},
            {"dst": "x", "op": "DEBOUNCE2", "args": ["cur", "prev"]},
        ]
    )
    prog_b = _program(
        [
            {"dst": "x", "op": "SELECT_BIT", "args": ["o_t", 0]},
        ]
    )
    prog_c = _program(
        [
            {"dst": "bit", "op": "SELECT_BIT", "args": ["o_t", 3]},
            {"dst": "x", "op": "GET", "args": ["bit"]},
        ]
    )
    entries = [
        {"name": "prog_b", "program": prog_b, "bytes": canonical_json_bytes(prog_b)},
        {"name": "prog_a", "program": prog_a, "bytes": canonical_json_bytes(prog_a)},
        {"name": "prog_c", "program": prog_c, "bytes": canonical_json_bytes(prog_c)},
    ]

    ordered1 = order_programs(entries, anomaly_buffer=anomaly_buffer)
    ordered2 = order_programs(entries, anomaly_buffer=anomaly_buffer)

    bytes1 = [canonical_json_bytes(entry["program"]) for entry in ordered1]
    bytes2 = [canonical_json_bytes(entry["program"]) for entry in ordered2]
    assert bytes1 == bytes2
    assert ordered1[-1]["name"] == "prog_b"
