"""Bounded program enumerator for CAOE v1."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402


def _int_literals() -> list[dict[str, int]]:
    return [{"int": 0}, {"int": 1}, {"int": 2}, {"int": 3}, {"int": 4}]


def _zero_literal(io_decl: dict[str, Any]) -> Any:
    typ = io_decl.get("type")
    if typ == "bit":
        return {"bit": 0}
    if typ == "int":
        return {"int": 0}
    if typ == "bitvec":
        width = int(io_decl.get("width", 0))
        return {"bitvec": [0 for _ in range(width)]}
    return 0


def _const_literals(io_decl: dict[str, Any]) -> list[dict[str, Any]]:
    typ = io_decl.get("type")
    if typ == "int":
        return _int_literals()
    return [_zero_literal(io_decl)]


def _compatible_get_inputs(
    out_decl: dict[str, Any],
    inputs: list[dict[str, Any]],
    allowed_inputs_set: set[str],
) -> list[str]:
    matches: list[str] = []
    out_type = out_decl.get("type")
    out_width = out_decl.get("width")
    for inp in inputs:
        name = inp.get("name")
        if not name or name not in allowed_inputs_set:
            continue
        inp_type = inp.get("type")
        inp_width = inp.get("width")
        if out_type == inp_type and out_width == inp_width:
            matches.append(name)
        elif out_type == "int" and inp_type == "bit":
            matches.append(name)
    return matches


def _io_signature(io_decl: dict[str, Any]) -> tuple:
    typ = io_decl.get("type")
    width = io_decl.get("width")
    return (typ, width)


def enumerate_programs(
    *,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    max_ops: int,
    max_constants: int,
    allowed_inputs: list[str] | None = None,
    limit: int = 16,
) -> list[dict[str, Any]]:
    """Enumerate bounded programs in lexicographic order of program bytes.

    Returns a list of dicts with keys: program, bytes.
    """
    max_ops = int(max_ops)
    max_constants = int(max_constants)
    allowed_inputs_set = set(allowed_inputs or [item.get("name") for item in inputs])

    input_by_name = {item.get("name"): item for item in inputs if isinstance(item, dict)}

    candidates: list[dict[str, Any]] = []
    io_by_name = {item.get("name"): item for item in inputs if isinstance(item, dict)}
    seen: set[bytes] = set()
    literal_ints: list[dict[str, int]] = [{"int": 0}, {"int": 1}, {"int": 2}]

    def _int_sources() -> list[Any]:
        sources: list[Any] = []
        for inp in inputs:
            name = inp.get("name")
            if not name or name not in allowed_inputs_set:
                continue
            if inp.get("type") in {"int", "bit"}:
                sources.append(name)
        sources.extend(literal_ints)
        return sources

    def _program_meta(program: dict[str, Any]) -> dict[str, Any]:
        ops = program.get("ops") or []
        uses_inputs: set[str] = set()
        has_const = False
        for op in ops:
            if not isinstance(op, dict):
                continue
            if op.get("op") == "CONST":
                has_const = True
            for arg in op.get("args") or []:
                if isinstance(arg, str) and arg in io_by_name:
                    uses_inputs.add(arg)
        return {
            "uses_inputs": sorted(uses_inputs),
            "has_const": bool(has_const),
            "all_const": bool(ops) and all(op.get("op") == "CONST" for op in ops if isinstance(op, dict)),
            "op_count": len(ops),
        }

    def _add(program: dict[str, Any]) -> None:
        ops = program.get("ops") or []
        dsts = {op.get("dst") for op in ops if isinstance(op, dict)}
        for out in outputs:
            name = out.get("name")
            if not name:
                return
            if name not in input_by_name and name not in dsts:
                return
        data = canonical_json_bytes(program)
        if data in seen:
            return
        seen.add(data)
        candidates.append({"program": program, "bytes": data, "meta": _program_meta(program)})

    # Variant 1: pure passthrough if outputs are already in inputs and allowed.
    passthrough_ok = True
    for out in outputs:
        name = out.get("name")
        if name not in input_by_name:
            passthrough_ok = False
            break
        if _io_signature(out) != _io_signature(input_by_name[name]):
            passthrough_ok = False
            break
        if name not in allowed_inputs_set:
            passthrough_ok = False
            break
    if passthrough_ok:
        program = {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": inputs,
            "outputs": outputs,
            "ops": [],
            "max_ops": max_ops,
        }
        _add(program)

    # Variant 1b: GET rename-copy if input signature matches and allowed.
    for out in outputs:
        out_name = out.get("name")
        if not out_name:
            continue
        for inp_name in _compatible_get_inputs(out, inputs, allowed_inputs_set):
            program = {
                "format": "bounded_program_v1",
                "schema_version": 1,
                "inputs": inputs,
                "outputs": outputs,
                "ops": [{"dst": out_name, "op": "GET", "args": [inp_name]}],
                "max_ops": max_ops,
            }
            if len(program["ops"]) <= max_ops:
                _add(program)

    # Variant 1c: SLICE bit extraction from bitvec inputs.
    for out in outputs:
        if out.get("type") != "bit":
            continue
        out_name = out.get("name")
        if not out_name:
            continue
        for inp in inputs:
            if inp.get("type") != "bitvec":
                continue
            inp_name = inp.get("name")
            if not inp_name or inp_name not in allowed_inputs_set:
                continue
            width = int(inp.get("width", 0))
            for i in range(max(0, min(width, 20))):
                program = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": inputs,
                    "outputs": outputs,
                    "ops": [{"dst": out_name, "op": "SLICE", "args": [inp_name, i, i + 1]}],
                    "max_ops": max_ops,
                }
                if len(program["ops"]) <= max_ops:
                    _add(program)
                program_select = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": inputs,
                    "outputs": outputs,
                    "ops": [{"dst": out_name, "op": "SELECT_BIT", "args": [inp_name, i]}],
                    "max_ops": max_ops,
                }
                if len(program_select["ops"]) <= max_ops:
                    _add(program_select)
                program_xor = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": inputs,
                    "outputs": outputs,
                    "ops": [
                        {"dst": f"{out_name}_slice", "op": "SLICE", "args": [inp_name, i, i + 1]},
                        {"dst": out_name, "op": "XOR", "args": [f"{out_name}_slice", {"bit": 1}]},
                    ],
                    "max_ops": max_ops,
                }
                if len(program_xor["ops"]) <= max_ops:
                    _add(program_xor)

    # Variant 1d: SLICE for all bit outputs from first allowed bitvec input.
    bitvec_inputs = [
        inp
        for inp in inputs
        if inp.get("type") == "bitvec" and inp.get("name") in allowed_inputs_set
    ]
    if bitvec_inputs:
        inp = bitvec_inputs[0]
        inp_name = inp.get("name")
        width = int(inp.get("width", 0))
        if inp_name and width > 0:
            slice_width = max(1, min(width, 20))
            ops_all: list[dict[str, Any]] = []
            idx = 0
            for out in outputs:
                if out.get("type") != "bit":
                    ops_all = []
                    break
                out_name = out.get("name")
                if not out_name:
                    ops_all = []
                    break
                ops_all.append(
                    {
                        "dst": out_name,
                        "op": "SLICE",
                        "args": [inp_name, idx % slice_width, (idx % slice_width) + 1],
                    }
                )
                idx += 1
            if ops_all and len(ops_all) <= max_ops:
                program = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": inputs,
                    "outputs": outputs,
                    "ops": ops_all,
                    "max_ops": max_ops,
                }
                _add(program)

    # Variant 1e: COUNT1 for int outputs from bitvec inputs.
    for out in outputs:
        if out.get("type") != "int":
            continue
        out_name = out.get("name")
        if not out_name:
            continue
        for inp in inputs:
            if inp.get("type") != "bitvec":
                continue
            inp_name = inp.get("name")
            if not inp_name or inp_name not in allowed_inputs_set:
                continue
            program = {
                "format": "bounded_program_v1",
                "schema_version": 1,
                "inputs": inputs,
                "outputs": outputs,
                "ops": [{"dst": out_name, "op": "COUNT1", "args": [inp_name]}],
                "max_ops": max_ops,
            }
            if len(program["ops"]) <= max_ops:
                _add(program)

    # Variant 1f: ARGMIN/ARGMAX for int outputs from int sources.
    int_sources = _int_sources()
    if len(int_sources) >= 2:
        for out in outputs:
            if out.get("type") != "int":
                continue
            out_name = out.get("name")
            if not out_name:
                continue
            for op_name in ("ARGMIN", "ARGMAX"):
                program = {
                    "format": "bounded_program_v1",
                    "schema_version": 1,
                    "inputs": inputs,
                    "outputs": outputs,
                    "ops": [{"dst": out_name, "op": op_name, "args": [int_sources[0], int_sources[1]]}],
                    "max_ops": max_ops,
                }
                if len(program["ops"]) <= max_ops:
                    _add(program)

    # Variant 2: mix passthrough and CONST for outputs.
    ops: list[dict[str, Any]] = []
    const_count = 0
    for out in outputs:
        name = out.get("name")
        if (
            name in input_by_name
            and _io_signature(out) == _io_signature(input_by_name[name])
            and name in allowed_inputs_set
        ):
            # passthrough, no op needed
            continue
        ops.append({"dst": name, "op": "CONST", "args": [_zero_literal(out)]})
        const_count += 1
    if ops and len(ops) <= max_ops and const_count <= max_constants:
        program = {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": inputs,
            "outputs": outputs,
            "ops": ops,
            "max_ops": max_ops,
        }
        _add(program)

    # Variant 2b: single GET with CONST for remaining outputs.
    has_psi_len = any(out.get("name") == "psi_len" for out in outputs)
    has_psi_type = any(out.get("name") == "psi_0_type" for out in outputs)
    psi_len_variants = [{"int": 1}, {"int": 2}, {"int": 3}, {"int": 4}] if has_psi_len else [{"int": 0}]
    psi_type_variants = [{"int": 1}, {"int": 2}] if has_psi_type else [{"int": 0}]
    psi_value_outputs = [out for out in outputs if out.get("name") == "psi_0_value"]
    if psi_value_outputs:
        out = psi_value_outputs[0]
        get_inputs = _compatible_get_inputs(out, inputs, allowed_inputs_set)
        for inp_name in get_inputs:
            for psi_len in psi_len_variants:
                for psi_type in psi_type_variants:
                    ops_mix: list[dict[str, Any]] = []
                    const_count = 0
                    for out2 in outputs:
                        name2 = out2.get("name")
                        if not name2:
                            ops_mix = []
                            break
                        if name2 == "psi_0_value":
                            ops_mix.append({"dst": name2, "op": "GET", "args": [inp_name]})
                            continue
                        if name2 == "psi_len":
                            ops_mix.append({"dst": name2, "op": "CONST", "args": [psi_len]})
                            const_count += 1
                            continue
                        if name2 == "psi_0_type":
                            ops_mix.append({"dst": name2, "op": "CONST", "args": [psi_type]})
                            const_count += 1
                            continue
                        ops_mix.append({"dst": name2, "op": "CONST", "args": [_zero_literal(out2)]})
                        const_count += 1
                    if not ops_mix:
                        continue
                    if len(ops_mix) <= max_ops and const_count <= max_constants:
                        program = {
                            "format": "bounded_program_v1",
                            "schema_version": 1,
                            "inputs": inputs,
                            "outputs": outputs,
                            "ops": ops_mix,
                            "max_ops": max_ops,
                        }
                        _add(program)

    # Variant 3: all CONST (even if passthrough possible), limited variants.
    has_int = any(out.get("type") == "int" for out in outputs)
    int_variants = [{"int": 0}, {"int": 1}] if has_int else [{"int": 0}]
    for int_lit in int_variants:
        ops_all: list[dict[str, Any]] = []
        const_count = 0
        for out in outputs:
            out_name = out.get("name")
            if not out_name:
                continue
            if out.get("type") == "int":
                ops_all.append({"dst": out_name, "op": "CONST", "args": [int_lit]})
            else:
                ops_all.append({"dst": out_name, "op": "CONST", "args": [_zero_literal(out)]})
            const_count += 1
        if len(ops_all) <= max_ops and const_count <= max_constants:
            program = {
                "format": "bounded_program_v1",
                "schema_version": 1,
                "inputs": inputs,
                "outputs": outputs,
                "ops": ops_all,
                "max_ops": max_ops,
            }
            _add(program)

    # Sort by serialized bytes.
    candidates.sort(key=lambda item: item["bytes"])
    return candidates[: max(0, int(limit))]
