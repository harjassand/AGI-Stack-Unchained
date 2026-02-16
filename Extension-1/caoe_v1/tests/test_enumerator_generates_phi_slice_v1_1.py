from __future__ import annotations

from sleep.synth.bounded_program_enumerator_v1 import enumerate_programs


def test_enumerator_generates_phi_slice_v1_1() -> None:
    inputs = [{"name": "o_t", "type": "bitvec", "width": 32}]
    outputs = [{"name": "x0", "type": "bit"}]
    programs = enumerate_programs(inputs=inputs, outputs=outputs, max_ops=4, max_constants=4, limit=64)
    found_0 = False
    found_1 = False
    for entry in programs:
        ops = entry["program"].get("ops") or []
        if len(ops) != 1:
            continue
        op = ops[0]
        if op.get("op") != "SLICE" or op.get("dst") != "x0":
            continue
        args = op.get("args") or []
        if args == ["o_t", 0, 1]:
            found_0 = True
        if args == ["o_t", 1, 2]:
            found_1 = True
    assert found_0 and found_1
