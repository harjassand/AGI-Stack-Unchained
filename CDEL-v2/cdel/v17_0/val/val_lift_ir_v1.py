"""Deterministic lifter from decoded trace to compact VAL IR."""

from __future__ import annotations

from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed


class ValLiftError(ValueError):
    pass


def _lift_py_ops(decoded_trace: dict[str, Any]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for insn in decoded_trace.get("instructions", []):
        mnemonic = str(insn.get("mnemonic", "")).lower()
        operands = [str(x) for x in insn.get("operands_norm", [])]
        pc = int(insn.get("pc_u32", -1))

        if mnemonic == "ldr":
            ops.append({"op": "Load32", "pc_u32": pc, "args": operands})
        elif mnemonic == "str":
            ops.append({"op": "Store32", "pc_u32": pc, "args": operands})
        elif mnemonic in {"ld1", "st1"}:
            op_name = "LoadVec" if mnemonic == "ld1" else "StoreVec"
            ops.append({"op": op_name, "pc_u32": pc, "args": operands})
        elif mnemonic == "sha256h":
            ops.append({"op": "Sha256H", "pc_u32": pc, "args": operands})
        elif mnemonic == "sha256h2":
            ops.append({"op": "Sha256H2", "pc_u32": pc, "args": operands})
        elif mnemonic == "sha256su0":
            ops.append({"op": "Sha256Su0", "pc_u32": pc, "args": operands})
        elif mnemonic == "sha256su1":
            ops.append({"op": "Sha256Su1", "pc_u32": pc, "args": operands})
        elif mnemonic == "subs":
            ops.append({"op": "CounterDec", "pc_u32": pc, "args": operands})
        elif mnemonic == "b.ne":
            ops.append({"op": "CounterDecAndBranch", "pc_u32": pc, "args": operands})
        elif mnemonic == "ret":
            ops.append({"op": "Ret", "pc_u32": pc, "args": []})
        else:
            ops.append({"op": "IntOp", "pc_u32": pc, "args": [mnemonic, *operands]})
    return ops


def _lift_rs_ops(decoded_trace: dict[str, Any]) -> list[dict[str, Any]]:
    # Alternate check-order path to harden against verifier backdoors.
    ops: list[dict[str, Any]] = []
    mapping = {
        "ldr": "Load32",
        "str": "Store32",
        "ld1": "LoadVec",
        "st1": "StoreVec",
        "sha256h": "Sha256H",
        "sha256h2": "Sha256H2",
        "sha256su0": "Sha256Su0",
        "sha256su1": "Sha256Su1",
        "subs": "CounterDec",
        "b.ne": "CounterDecAndBranch",
        "ret": "Ret",
    }
    for insn in decoded_trace.get("instructions", []):
        mnemonic = str(insn.get("mnemonic", "")).lower()
        op = mapping.get(mnemonic, "IntOp")
        args = [str(x) for x in insn.get("operands_norm", [])]
        if op == "IntOp":
            args = [mnemonic, *args]
        ops.append(
            {
                "op": op,
                "pc_u32": int(insn.get("pc_u32", -1)),
                "args": args,
            }
        )
    return ops


def lift_ir_py(decoded_trace: dict[str, Any]) -> dict[str, Any]:
    if decoded_trace.get("schema_version") != "val_decoded_trace_v1":
        raise ValLiftError("INVALID:SCHEMA_FAIL")
    return {
        "schema_version": "val_lift_ir_v1",
        "ops": _lift_py_ops(decoded_trace),
    }


def lift_ir_rs(decoded_trace: dict[str, Any]) -> dict[str, Any]:
    if decoded_trace.get("schema_version") != "val_decoded_trace_v1":
        raise ValLiftError("INVALID:SCHEMA_FAIL")
    return {
        "schema_version": "val_lift_ir_v1",
        "ops": _lift_rs_ops(decoded_trace),
    }


def lift_ir_hash(lifted_ir: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(lifted_ir))


__all__ = [
    "ValLiftError",
    "lift_ir_hash",
    "lift_ir_py",
    "lift_ir_rs",
]
