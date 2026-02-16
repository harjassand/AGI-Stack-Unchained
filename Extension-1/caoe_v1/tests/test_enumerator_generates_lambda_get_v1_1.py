from __future__ import annotations

from sleep.synth.bounded_program_enumerator_v1 import enumerate_programs


def test_enumerator_generates_lambda_get_v1_1() -> None:
    inputs = [{"name": "psi_0_value", "type": "bit"}]
    outputs = [{"name": "x0", "type": "bit"}]
    programs = enumerate_programs(inputs=inputs, outputs=outputs, max_ops=4, max_constants=4, limit=16)
    found = False
    for entry in programs:
        prog = entry["program"]
        ops = prog.get("ops") or []
        if len(ops) != 1:
            continue
        op = ops[0]
        if op.get("op") == "GET" and op.get("dst") == "x0" and op.get("args") == ["psi_0_value"]:
            found = True
            break
    assert found
