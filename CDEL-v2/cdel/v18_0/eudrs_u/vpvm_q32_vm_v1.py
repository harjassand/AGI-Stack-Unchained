"""VPVM Q32 VM (v1).

This is a deterministic reference interpreter for the VPVM Q32 ISA described in
the PCLP / STARK-VM v1 spec. It is intended for:
  - witness/trace generation (prover-side)
  - golden tests for instruction semantics

The STARK AIR for this VM is implemented separately; this module is the source
of truth for concrete execution semantics.

Determinism/fail-closed:
  - no floats
  - strict bytecode decoding (reserved bytes MUST be zero)
  - strict caps enforcement for memory ops
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Any, Final

from .eudrs_u_q32ops_v1 import S64_MAX, S64_MIN, add_sat, mul_q32, sat64


# -----------------
# ISA opcode values
# -----------------

OP_NOP: Final[int] = 0x0000
OP_HALT: Final[int] = 0x0001
OP_MOV: Final[int] = 0x0010
OP_LOADI: Final[int] = 0x0011
OP_ADD_SAT: Final[int] = 0x0020
OP_SUB_SAT: Final[int] = 0x0021
OP_MUL_Q32_SAT: Final[int] = 0x0030
OP_MEM_LOAD_S64: Final[int] = 0x0040
OP_MEM_STORE_S64: Final[int] = 0x0041
OP_CMP_GT_S64: Final[int] = 0x0050
OP_CMP_EQ_S64: Final[int] = 0x0051
OP_CMOV: Final[int] = 0x0052
OP_ASSERT1: Final[int] = 0x0060


_U64_MASK: Final[int] = 0xFFFFFFFFFFFFFFFF
_OFF_MASK_U56: Final[int] = 0x00FFFFFFFFFFFFFF

# 16 bytes: opcode_u16, rd_u8, ra_u8, rb_u8, imm_s64, reserved_u16, reserved_u8
# NOTE: The spec states reserved_u16; we additionally require the final pad byte to be zero
# to preserve fixed-width 16-byte encoding.
_INSTR: Final[struct.Struct] = struct.Struct("<HBBBqHB")


class VpvmQ32VmError(Exception):
    """Deterministic VM execution error (fail-closed at the integration layer)."""


@dataclass(frozen=True, slots=True)
class VpvmInstrV1:
    opcode_u16: int
    rd_u8: int
    ra_u8: int
    rb_u8: int
    imm_s64: int


@dataclass(frozen=True, slots=True)
class VpvmStateV1:
    pc_u32: int
    halted: bool
    regs_s64: tuple[int, ...]  # length 16
    mem_u64: dict[int, int]  # full u64 addr -> u64 value


@dataclass(frozen=True, slots=True)
class VpvmTraceV1:
    pc_u32: list[int]
    halted_u8: list[int]
    opcode_u16: list[int]
    rd_u8: list[int]
    ra_u8: list[int]
    rb_u8: list[int]
    imm_s64: list[int]
    regs_s64_rows: list[tuple[int, ...]]  # pre-state for each step (len 16 tuples)
    mem_en_u8: list[int]
    mem_is_write_u8: list[int]
    mem_addr_u64: list[int]
    mem_val_u64: list[int]
    mem_old_u64: list[int]
    mem_seg_u8: list[int]


def encode_vpvm_instr_v1(*, opcode_u16: int, rd_u8: int = 0, ra_u8: int = 0, rb_u8: int = 0, imm_s64: int = 0) -> bytes:
    """Encode one VPVM v1 instruction (16 bytes)."""

    op = int(opcode_u16) & 0xFFFF
    rd = int(rd_u8) & 0xFF
    ra = int(ra_u8) & 0xFF
    rb = int(rb_u8) & 0xFF
    imm = int(imm_s64)
    if imm < S64_MIN or imm > S64_MAX:
        # imm is encoded as s64; reject out-of-range for determinism.
        raise VpvmQ32VmError("imm_s64 out of s64 range")
    return bytes(_INSTR.pack(op, rd, ra, rb, imm, 0, 0))


def decode_vpvm_program_v1(program_bytes: bytes) -> list[VpvmInstrV1]:
    mv = memoryview(bytes(program_bytes))
    if mv.ndim != 1 or (len(mv) % _INSTR.size) != 0:
        raise VpvmQ32VmError("program length not multiple of 16 bytes")
    out: list[VpvmInstrV1] = []
    for off in range(0, len(mv), _INSTR.size):
        opcode_u16, rd_u8, ra_u8, rb_u8, imm_s64, reserved_u16, reserved_u8 = _INSTR.unpack_from(mv, off)
        if int(reserved_u16) != 0 or int(reserved_u8) != 0:
            raise VpvmQ32VmError("reserved bytes non-zero")
        out.append(
            VpvmInstrV1(
                opcode_u16=int(opcode_u16),
                rd_u8=int(rd_u8),
                ra_u8=int(ra_u8),
                rb_u8=int(rb_u8),
                imm_s64=int(imm_s64),
            )
        )
    return out


def _require_reg_index_u8(x: int) -> int:
    r = int(x)
    if r < 0 or r >= 16:
        raise VpvmQ32VmError("reg index out of range")
    return int(r)


def _u64_from_s64(x: int) -> int:
    return int(x) & _U64_MASK


def _s64_from_u64(u: int) -> int:
    x = int(u) & _U64_MASK
    if x >= (1 << 63):
        return int(x - (1 << 64))
    return int(x)


def _caps_mem_limits_v1(caps: dict[str, Any]) -> tuple[int, set[int], dict[int, int]]:
    if not isinstance(caps, dict):
        raise VpvmQ32VmError("caps not dict")
    mem = caps.get("mem")
    if not isinstance(mem, dict):
        raise VpvmQ32VmError("caps.mem not dict")
    max_addr_u64 = mem.get("max_addr_u64")
    if not isinstance(max_addr_u64, int) or max_addr_u64 < 0 or max_addr_u64 > _U64_MASK:
        raise VpvmQ32VmError("caps.mem.max_addr_u64 invalid")
    allowed_segs_u8 = mem.get("allowed_segs_u8")
    if not isinstance(allowed_segs_u8, list) or not allowed_segs_u8:
        raise VpvmQ32VmError("caps.mem.allowed_segs_u8 invalid")
    allowed = set()
    for s in allowed_segs_u8:
        if not isinstance(s, int) or s < 0 or s > 255:
            raise VpvmQ32VmError("caps.mem.allowed_segs_u8 invalid")
        allowed.add(int(s))
    seg_limits = mem.get("seg_limits")
    if not isinstance(seg_limits, list) or not seg_limits:
        raise VpvmQ32VmError("caps.mem.seg_limits invalid")
    limits: dict[int, int] = {}
    for row in seg_limits:
        if not isinstance(row, dict):
            raise VpvmQ32VmError("caps.mem.seg_limits invalid")
        seg = row.get("seg_u8")
        lim = row.get("max_addr_u64")
        if not isinstance(seg, int) or seg < 0 or seg > 255:
            raise VpvmQ32VmError("caps.mem.seg_limits invalid")
        if not isinstance(lim, int) or lim < 0 or lim > int(max_addr_u64):
            raise VpvmQ32VmError("caps.mem.seg_limits invalid")
        limits[int(seg)] = int(lim)
    # Enforce deterministic closure: limits must cover exactly allowed set.
    if set(limits.keys()) != set(allowed):
        raise VpvmQ32VmError("caps.mem.seg_limits mismatch allowed_segs_u8")
    return int(max_addr_u64), set(allowed), dict(limits)


def _addr_seg_off(addr_u64: int) -> tuple[int, int]:
    a = int(addr_u64) & _U64_MASK
    seg = (a >> 56) & 0xFF
    off = a & _OFF_MASK_U56
    return int(seg), int(off)


def execute_and_trace_vpvm_q32_v1(
    *,
    program_bytes: bytes,
    initial_memory_image: dict[tuple[int, int], int] | None,
    caps: dict[str, Any],
    max_steps: int,
) -> VpvmTraceV1:
    """Execute `program_bytes` and return a deterministic trace.

    Memory image keys are (seg_u8, addr_u64) where addr_u64 is the *offset* within the segment.
    Internally, the VM uses a single u64 address space where the segment id is derived from the top byte.
    """

    instrs = decode_vpvm_program_v1(program_bytes)
    if not isinstance(max_steps, int) or int(max_steps) <= 0:
        raise VpvmQ32VmError("max_steps invalid")
    max_addr_u64, allowed_segs, seg_limits = _caps_mem_limits_v1(caps)

    mem: dict[int, int] = {}
    if initial_memory_image is not None:
        if not isinstance(initial_memory_image, dict):
            raise VpvmQ32VmError("initial_memory_image not dict")
        for (seg, off), v in initial_memory_image.items():
            if not isinstance(seg, int) or seg < 0 or seg > 255:
                raise VpvmQ32VmError("initial_memory_image seg invalid")
            if not isinstance(off, int) or off < 0 or off > _OFF_MASK_U56:
                raise VpvmQ32VmError("initial_memory_image addr invalid")
            if int(off) & 7:
                raise VpvmQ32VmError("initial_memory_image addr unaligned")
            if int(seg) not in allowed_segs:
                raise VpvmQ32VmError("initial_memory_image seg not allowed")
            if int(off) > int(seg_limits[int(seg)]):
                raise VpvmQ32VmError("initial_memory_image addr exceeds seg limit")
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            mem[int(full)] = int(v) & _U64_MASK

    regs = [0] * 16
    pc = 0
    halted = False

    tr = VpvmTraceV1(
        pc_u32=[],
        halted_u8=[],
        opcode_u16=[],
        rd_u8=[],
        ra_u8=[],
        rb_u8=[],
        imm_s64=[],
        regs_s64_rows=[],
        mem_en_u8=[],
        mem_is_write_u8=[],
        mem_addr_u64=[],
        mem_val_u64=[],
        mem_old_u64=[],
        mem_seg_u8=[],
    )

    steps = 0
    while True:
        if steps >= int(max_steps):
            raise VpvmQ32VmError("max_steps exceeded")
        if halted:
            break
        if pc < 0 or pc >= len(instrs):
            raise VpvmQ32VmError("pc out of range")
        ins = instrs[pc]

        # Record pre-state row.
        tr.pc_u32.append(int(pc) & 0xFFFFFFFF)
        tr.halted_u8.append(1 if halted else 0)
        tr.opcode_u16.append(int(ins.opcode_u16) & 0xFFFF)
        tr.rd_u8.append(int(ins.rd_u8) & 0xFF)
        tr.ra_u8.append(int(ins.ra_u8) & 0xFF)
        tr.rb_u8.append(int(ins.rb_u8) & 0xFF)
        tr.imm_s64.append(int(ins.imm_s64))
        tr.regs_s64_rows.append(tuple(int(x) for x in regs))

        mem_en = 0
        mem_is_write = 0
        mem_addr = 0
        mem_val = 0
        mem_old = 0
        mem_seg = 0

        op = int(ins.opcode_u16) & 0xFFFF
        rd = _require_reg_index_u8(ins.rd_u8)
        ra = _require_reg_index_u8(ins.ra_u8)
        rb = _require_reg_index_u8(ins.rb_u8)
        imm = int(ins.imm_s64)

        def _set_reg(r: int, v: int) -> None:
            regs[r] = int(sat64(int(v)))

        if op == OP_NOP:
            pc += 1
        elif op == OP_HALT:
            halted = True
            pc += 1
        elif op == OP_MOV:
            _set_reg(rd, regs[ra])
            pc += 1
        elif op == OP_LOADI:
            _set_reg(rd, imm)
            pc += 1
        elif op == OP_ADD_SAT:
            _set_reg(rd, add_sat(regs[ra], regs[rb]))
            pc += 1
        elif op == OP_SUB_SAT:
            _set_reg(rd, sat64(int(regs[ra]) - int(regs[rb])))
            pc += 1
        elif op == OP_MUL_Q32_SAT:
            _set_reg(rd, mul_q32(regs[ra], regs[rb]))
            pc += 1
        elif op == OP_MEM_LOAD_S64:
            mem_en = 1
            mem_is_write = 0
            base_u64 = _u64_from_s64(regs[ra])
            addr_u64 = (base_u64 + int(imm)) & _U64_MASK
            seg, off = _addr_seg_off(addr_u64)
            if seg not in allowed_segs:
                raise VpvmQ32VmError("mem seg not allowed")
            if off > int(seg_limits[int(seg)]) or off > int(max_addr_u64):
                raise VpvmQ32VmError("mem addr exceeds cap")
            if off & 7:
                raise VpvmQ32VmError("mem addr unaligned")
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            old_u64 = int(mem.get(int(full), 0)) & _U64_MASK
            mem_addr = int(full)
            mem_old = int(old_u64)
            mem_val = int(old_u64)
            mem_seg = int(seg)
            _set_reg(rd, _s64_from_u64(old_u64))
            pc += 1
        elif op == OP_MEM_STORE_S64:
            mem_en = 1
            mem_is_write = 1
            base_u64 = _u64_from_s64(regs[ra])
            addr_u64 = (base_u64 + int(imm)) & _U64_MASK
            seg, off = _addr_seg_off(addr_u64)
            if seg not in allowed_segs:
                raise VpvmQ32VmError("mem seg not allowed")
            if off > int(seg_limits[int(seg)]) or off > int(max_addr_u64):
                raise VpvmQ32VmError("mem addr exceeds cap")
            if off & 7:
                raise VpvmQ32VmError("mem addr unaligned")
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            old_u64 = int(mem.get(int(full), 0)) & _U64_MASK
            val_u64 = _u64_from_s64(regs[rb])
            mem[int(full)] = int(val_u64)
            mem_addr = int(full)
            mem_old = int(old_u64)
            mem_val = int(val_u64)
            mem_seg = int(seg)
            pc += 1
        elif op == OP_CMP_GT_S64:
            _set_reg(rd, 1 if int(regs[ra]) > int(regs[rb]) else 0)
            pc += 1
        elif op == OP_CMP_EQ_S64:
            _set_reg(rd, 1 if int(regs[ra]) == int(regs[rb]) else 0)
            pc += 1
        elif op == OP_CMOV:
            if int(regs[ra]) != 0:
                _set_reg(rd, regs[rb])
            pc += 1
        elif op == OP_ASSERT1:
            if int(regs[ra]) != 1:
                raise VpvmQ32VmError("ASSERT1 failed")
            pc += 1
        else:
            raise VpvmQ32VmError("invalid opcode")

        tr.mem_en_u8.append(int(mem_en))
        tr.mem_is_write_u8.append(int(mem_is_write))
        tr.mem_addr_u64.append(int(mem_addr) & _U64_MASK)
        tr.mem_val_u64.append(int(mem_val) & _U64_MASK)
        tr.mem_old_u64.append(int(mem_old) & _U64_MASK)
        tr.mem_seg_u8.append(int(mem_seg) & 0xFF)

        steps += 1

    return tr


def execute_vpvm_q32_v1(
    *,
    program_bytes: bytes,
    initial_memory_image: dict[tuple[int, int], int] | None,
    caps: dict[str, Any],
    max_steps: int,
) -> VpvmStateV1:
    """Execute VPVM program and return the final state (no trace)."""

    tr = execute_and_trace_vpvm_q32_v1(program_bytes=program_bytes, initial_memory_image=initial_memory_image, caps=caps, max_steps=max_steps)
    # Re-run deterministically to obtain final regs/mem without storing all state; this is fine for v1 tests.
    # (Avoids keeping mutable state in the trace object.)
    instrs = decode_vpvm_program_v1(program_bytes)
    max_addr_u64, allowed_segs, seg_limits = _caps_mem_limits_v1(caps)
    mem: dict[int, int] = {}
    if initial_memory_image:
        for (seg, off), v in initial_memory_image.items():
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            mem[int(full)] = int(v) & _U64_MASK
    regs = [0] * 16
    pc = 0
    halted = False
    steps = 0
    while True:
        if steps >= int(max_steps):
            raise VpvmQ32VmError("max_steps exceeded")
        if halted:
            break
        if pc < 0 or pc >= len(instrs):
            raise VpvmQ32VmError("pc out of range")
        ins = instrs[pc]
        op = int(ins.opcode_u16) & 0xFFFF
        rd = _require_reg_index_u8(ins.rd_u8)
        ra = _require_reg_index_u8(ins.ra_u8)
        rb = _require_reg_index_u8(ins.rb_u8)
        imm = int(ins.imm_s64)

        def _set_reg(r: int, v: int) -> None:
            regs[r] = int(sat64(int(v)))

        if op == OP_NOP:
            pc += 1
        elif op == OP_HALT:
            halted = True
            pc += 1
        elif op == OP_MOV:
            _set_reg(rd, regs[ra])
            pc += 1
        elif op == OP_LOADI:
            _set_reg(rd, imm)
            pc += 1
        elif op == OP_ADD_SAT:
            _set_reg(rd, add_sat(regs[ra], regs[rb]))
            pc += 1
        elif op == OP_SUB_SAT:
            _set_reg(rd, sat64(int(regs[ra]) - int(regs[rb])))
            pc += 1
        elif op == OP_MUL_Q32_SAT:
            _set_reg(rd, mul_q32(regs[ra], regs[rb]))
            pc += 1
        elif op == OP_MEM_LOAD_S64:
            base_u64 = _u64_from_s64(regs[ra])
            addr_u64 = (base_u64 + int(imm)) & _U64_MASK
            seg, off = _addr_seg_off(addr_u64)
            if seg not in allowed_segs or off > int(seg_limits[int(seg)]) or off > int(max_addr_u64) or (off & 7):
                raise VpvmQ32VmError("mem cap fail")
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            _set_reg(rd, _s64_from_u64(int(mem.get(int(full), 0)) & _U64_MASK))
            pc += 1
        elif op == OP_MEM_STORE_S64:
            base_u64 = _u64_from_s64(regs[ra])
            addr_u64 = (base_u64 + int(imm)) & _U64_MASK
            seg, off = _addr_seg_off(addr_u64)
            if seg not in allowed_segs or off > int(seg_limits[int(seg)]) or off > int(max_addr_u64) or (off & 7):
                raise VpvmQ32VmError("mem cap fail")
            full = ((int(seg) & 0xFF) << 56) | (int(off) & _OFF_MASK_U56)
            mem[int(full)] = _u64_from_s64(regs[rb])
            pc += 1
        elif op == OP_CMP_GT_S64:
            _set_reg(rd, 1 if int(regs[ra]) > int(regs[rb]) else 0)
            pc += 1
        elif op == OP_CMP_EQ_S64:
            _set_reg(rd, 1 if int(regs[ra]) == int(regs[rb]) else 0)
            pc += 1
        elif op == OP_CMOV:
            if int(regs[ra]) != 0:
                _set_reg(rd, regs[rb])
            pc += 1
        elif op == OP_ASSERT1:
            if int(regs[ra]) != 1:
                raise VpvmQ32VmError("ASSERT1 failed")
            pc += 1
        else:
            raise VpvmQ32VmError("invalid opcode")
        steps += 1

    _ = tr  # keep deterministic execution order; trace already validated.
    return VpvmStateV1(pc_u32=int(pc) & 0xFFFFFFFF, halted=bool(halted), regs_s64=tuple(int(x) for x in regs), mem_u64=dict(mem))


__all__ = [
    # ISA / encoding
    "OP_ADD_SAT",
    "OP_ASSERT1",
    "OP_CMP_EQ_S64",
    "OP_CMP_GT_S64",
    "OP_CMOV",
    "OP_HALT",
    "OP_LOADI",
    "OP_MEM_LOAD_S64",
    "OP_MEM_STORE_S64",
    "OP_MOV",
    "OP_MUL_Q32_SAT",
    "OP_NOP",
    "OP_SUB_SAT",
    "VpvmInstrV1",
    "VpvmQ32VmError",
    "decode_vpvm_program_v1",
    "encode_vpvm_instr_v1",
    # Execution
    "VpvmStateV1",
    "VpvmTraceV1",
    "execute_and_trace_vpvm_q32_v1",
    "execute_vpvm_q32_v1",
]
