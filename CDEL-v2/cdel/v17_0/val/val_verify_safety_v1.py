"""Fail-closed safety verifier for VAL lifted programs."""

from __future__ import annotations

import re
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed
from .val_isa_v1 import ALWAYS_FORBIDDEN_MNEMONICS, allowed_mnemonics_for_policy, extract_registers

MEM_RE = re.compile(r"^\[(x[0-9]+|sp)(?:,#([0-9]+))?\](?:,#([0-9]+))?$", re.IGNORECASE)


class ValSafetyError(ValueError):
    pass


def _fail(code: str) -> ValSafetyError:
    return ValSafetyError(code)


def _canonical_patch_id(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("patch_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _trace_head(decoded_trace: dict[str, Any]) -> str:
    prev = "GENESIS"
    for row in decoded_trace.get("instructions", []):
        payload = {
            "pc_u32": int(row["pc_u32"]),
            "opcode_u32": int(row["opcode_u32"]),
            "mnemonic": str(row["mnemonic"]),
            "operands_norm": [str(x) for x in row.get("operands_norm", [])],
            "prev_hash": prev,
        }
        prev = sha256_prefixed(canon_bytes(payload))
    return prev


def _parse_mem_operand(operand: str) -> tuple[str, int, int | None] | None:
    match = MEM_RE.fullmatch(operand.replace(" ", ""))
    if not match:
        return None
    base = str(match.group(1)).lower()
    imm = int(match.group(2) or "0")
    post_inc = int(match.group(3)) if match.group(3) is not None else None
    return base, imm, post_inc


def _verify_memory(decoded_trace: dict[str, Any]) -> tuple[dict[str, int], str | None]:
    state_max_read = 0
    state_max_write = 0
    blocks_max_read = 0

    for row in decoded_trace.get("instructions", []):
        mnemonic = str(row.get("mnemonic", "")).lower()
        operands = [str(x) for x in row.get("operands_norm", [])]
        if mnemonic not in {"ldr", "str", "ld1", "st1"}:
            continue

        mem_operand = next((op for op in operands if "[" in op and "]" in op), "")
        parsed = _parse_mem_operand(mem_operand)
        if parsed is None:
            return {}, "INVALID:VAL_MEMORY_OOB"
        base, imm, post_inc = parsed

        if base == "x0":
            if mnemonic in {"ldr", "str"}:
                if imm not in {0, 4, 8, 12, 16, 20, 24, 28} or post_inc not in (None, 0):
                    return {}, "INVALID:VAL_MEMORY_OOB"
                end = imm + 4
            else:
                if imm != 0 or post_inc not in (16,):
                    return {}, "INVALID:VAL_MEMORY_OOB"
                end = 16
            if mnemonic in {"str", "st1"}:
                state_max_write = max(state_max_write, end)
            else:
                state_max_read = max(state_max_read, end)
        elif base == "x1":
            if imm != 0:
                return {}, "INVALID:VAL_MEMORY_OOB"
            if post_inc not in (None, 16, 64):
                return {}, "INVALID:VAL_MEMORY_OOB"
            # Per-iteration bound; checked against blocks_len during execution precondition.
            blocks_max_read = max(blocks_max_read, int(post_inc or 16))
        else:
            return {}, "INVALID:VAL_MEMORY_OOB"

    summary = {
        "state_max_read_end_bytes": int(state_max_read),
        "state_max_write_end_bytes": int(state_max_write),
        "blocks_max_read_end_bytes": int(blocks_max_read),
    }
    return summary, None


def _verify_control_flow(decoded_trace: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    insns = list(decoded_trace.get("instructions", []))
    if not insns:
        return {}, "INVALID:VAL_CONTROL_FLOW"

    if str(insns[-1].get("mnemonic", "")).lower() != "ret":
        return {}, "INVALID:VAL_CONTROL_FLOW"

    loop_rows = [row for row in insns if str(row.get("mnemonic", "")).lower() == "b.ne"]
    if len(loop_rows) > 1:
        return {}, "INVALID:VAL_CONTROL_FLOW"
    if not loop_rows:
        return {"loop_count": 0, "backedge_pc_u32": None}, None

    loop_row = loop_rows[0]
    branch_pc = int(loop_row.get("pc_u32", -1))
    operands = [str(x) for x in loop_row.get("operands_norm", [])]
    if len(operands) != 1:
        return {}, "INVALID:VAL_CONTROL_FLOW"

    try:
        delta = int(operands[0])
    except Exception:
        return {}, "INVALID:VAL_CONTROL_FLOW"

    target_pc = branch_pc + delta
    if target_pc >= branch_pc:
        return {}, "INVALID:VAL_CONTROL_FLOW"
    all_pcs = {int(row.get("pc_u32", -1)) for row in insns}
    if target_pc not in all_pcs:
        return {}, "INVALID:VAL_CONTROL_FLOW"

    idx = next((i for i, row in enumerate(insns) if int(row.get("pc_u32", -1)) == branch_pc), -1)
    if idx <= 0:
        return {}, "INVALID:VAL_NONTERMINATING"
    prev = insns[idx - 1]
    if str(prev.get("mnemonic", "")).lower() != "subs":
        return {}, "INVALID:VAL_NONTERMINATING"
    prev_ops = [str(x) for x in prev.get("operands_norm", [])]
    if len(prev_ops) != 3 or prev_ops[2] != "#1":
        return {}, "INVALID:VAL_NONTERMINATING"
    if prev_ops[0] not in {"x2", "x3"} or prev_ops[1] != prev_ops[0]:
        return {}, "INVALID:VAL_NONTERMINATING"

    return {"loop_count": 1, "backedge_pc_u32": branch_pc}, None


def _instruction_gate(decoded_trace: dict[str, Any], policy: Any) -> str | None:
    allowed = allowed_mnemonics_for_policy(policy)
    forbidden = set(x.lower() for x in policy.forbidden_insn_mnemonics)
    for row in decoded_trace.get("instructions", []):
        mnemonic = str(row.get("mnemonic", "")).lower()
        if mnemonic in ALWAYS_FORBIDDEN_MNEMONICS or mnemonic in forbidden:
            return f"INVALID:VAL_FORBIDDEN_INSN:{mnemonic}"
        if mnemonic not in allowed:
            return f"INVALID:VAL_FORBIDDEN_INSN:{mnemonic}"
    return None


def _register_gate(decoded_trace: dict[str, Any], policy: Any) -> str | None:
    forbidden = set(x.lower() for x in policy.forbidden_regs)
    for row in decoded_trace.get("instructions", []):
        regs = extract_registers([str(x) for x in row.get("operands_norm", [])])
        for reg in sorted(regs):
            if reg in forbidden:
                return f"INVALID:VAL_FORBIDDEN_REG:{reg}"
    return None


def verify_safety(
    *,
    decoded_trace: dict[str, Any],
    lifted_ir: dict[str, Any],
    patch_manifest: dict[str, Any],
    policy: Any,
) -> dict[str, Any]:
    patch_id = str(patch_manifest.get("patch_id", ""))
    if patch_id != _canonical_patch_id(patch_manifest):
        raise _fail("INVALID:SCHEMA_FAIL")

    ir_hash = sha256_prefixed(canon_bytes(lifted_ir))
    fail_code: str | None = None

    for gate in (
        lambda: _instruction_gate(decoded_trace, policy),
        lambda: _register_gate(decoded_trace, policy),
    ):
        fail_code = gate()
        if fail_code is not None:
            break

    cfg_summary: dict[str, Any] = {"loop_count": 0, "backedge_pc_u32": None}
    mem_summary = {
        "state_max_read_end_bytes": 0,
        "state_max_write_end_bytes": 0,
        "blocks_max_read_end_bytes": 0,
    }
    if fail_code is None:
        mem_summary, fail_code = _verify_memory(decoded_trace)

    if fail_code is None:
        cfg_summary, fail_code = _verify_control_flow(decoded_trace)

    if fail_code is None and mem_summary["state_max_read_end_bytes"] > 32:
        fail_code = "INVALID:VAL_MEMORY_OOB"
    if fail_code is None and mem_summary["state_max_write_end_bytes"] > 32:
        fail_code = "INVALID:VAL_MEMORY_OOB"

    return {
        "schema_version": "val_safety_receipt_v1",
        "ir_hash": ir_hash,
        "patch_id": patch_id,
        "policy_hash": policy.policy_hash,
        "status": "SAFE" if fail_code is None else "UNSAFE",
        "pass": fail_code is None,
        "fail_code": fail_code,
        "mem_bounds_summary": mem_summary,
        "cfg_summary": cfg_summary,
        "trace_hash_chain_head": _trace_head(decoded_trace),
    }


def verify_safety_shadow(
    *,
    decoded_trace: dict[str, Any],
    lifted_ir: dict[str, Any],
    patch_manifest: dict[str, Any],
    policy: Any,
) -> dict[str, Any]:
    # Alternate ordering to catch hidden dependency bugs.
    patch_id = str(patch_manifest.get("patch_id", ""))
    if patch_id != _canonical_patch_id(patch_manifest):
        raise _fail("INVALID:SCHEMA_FAIL")

    ir_hash = sha256_prefixed(canon_bytes(lifted_ir))
    fail_code = _register_gate(decoded_trace, policy)
    if fail_code is None:
        fail_code = _instruction_gate(decoded_trace, policy)

    mem_summary = {
        "state_max_read_end_bytes": 0,
        "state_max_write_end_bytes": 0,
        "blocks_max_read_end_bytes": 0,
    }
    cfg_summary: dict[str, Any] = {"loop_count": 0, "backedge_pc_u32": None}

    if fail_code is None:
        mem_summary, fail_code = _verify_memory(decoded_trace)
    if fail_code is None:
        cfg_summary, fail_code = _verify_control_flow(decoded_trace)
    if fail_code is None and (
        mem_summary["state_max_read_end_bytes"] > 32 or mem_summary["state_max_write_end_bytes"] > 32
    ):
        fail_code = "INVALID:VAL_MEMORY_OOB"

    return {
        "schema_version": "val_safety_receipt_v1",
        "ir_hash": ir_hash,
        "patch_id": patch_id,
        "policy_hash": policy.policy_hash,
        "status": "SAFE" if fail_code is None else "UNSAFE",
        "pass": fail_code is None,
        "fail_code": fail_code,
        "mem_bounds_summary": mem_summary,
        "cfg_summary": cfg_summary,
        "trace_hash_chain_head": _trace_head(decoded_trace),
    }


__all__ = [
    "ValSafetyError",
    "verify_safety",
    "verify_safety_shadow",
]
