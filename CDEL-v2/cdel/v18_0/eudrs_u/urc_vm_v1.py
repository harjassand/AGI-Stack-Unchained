"""URC-VM v1 (capsule runtime) for EUDRS-U Phase 7.

Phase 7 directive (normative, condensed):
  - Decode/encode URC1 capsule binaries (stateful VM).
  - Execute URC_ISA_V1 minimal opcode set deterministically.
  - Integrate deterministic URC Merkle memory (pages + page-table nodes).
  - Enforce per-call budgets from urc_capsule_def_v1.
  - Produce URD1 step digest records and an H_urc tail digest chain.
  - Provide a universality certificate recomputation harness over pinned golden vectors.

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Any, Callable, Final

from ..omega_common_v1 import OmegaV18Error, ensure_sha256, fail, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from .urc_merkle_v1 import ZERO32, urc_mem_read64_v1, urc_mem_write64_v1


_REASON_CAPSULE_DECODE_FAIL: Final[str] = "EUDRSU_URC_CAPSULE_DECODE_FAIL"
_REASON_INVARIANT_FAIL: Final[str] = "EUDRSU_URC_INVARIANT_FAIL"
_REASON_BUDGET_EXCEEDED: Final[str] = "EUDRSU_URC_BUDGET_EXCEEDED"
_REASON_EXEC_FAIL: Final[str] = "EUDRSU_URC_EXEC_FAIL"

_REASON_GOLDEN_MISMATCH: Final[str] = "EUDRSU_URC_GOLDEN_TRACE_MISMATCH"

_URC_REGS_DOMAIN: Final[bytes] = b"URC_REGS_V1"
_URC_WRITES_DOMAIN: Final[bytes] = b"URC_WRITES_V1"
_URC_WRITES_EMPTY_DOMAIN: Final[bytes] = b"URC_WRITES_EMPTY_V1"

_URD_MAGIC: Final[bytes] = b"URD1"

# Capsule layout structs.
_URC1_HDR = struct.Struct("<4sIIIIIIII")  # magic, ver, isa_id, reg_count, page_shift, call_cap, res, pc, flags
_U64_16 = struct.Struct("<16Q")
_CALL_HDR = struct.Struct("<II")  # call_depth_u32, reserved_u32
_CALL_STACK = struct.Struct("<16I")
_CODE_HDR = struct.Struct("<II")  # instr_count_u32, reserved_u32


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _u32_le(v: int) -> bytes:
    if not isinstance(v, int) or v < 0 or v > 0xFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return struct.pack("<I", int(v) & 0xFFFFFFFF)


def _u64_le(v: int) -> bytes:
    if not isinstance(v, int) or v < 0 or v > 0xFFFFFFFFFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    return struct.pack("<Q", int(v) & 0xFFFFFFFFFFFFFFFF)


def _require_bytes32(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        fail(_REASON_INVARIANT_FAIL)
    b = bytes(value)
    if len(b) != 32:
        fail(_REASON_INVARIANT_FAIL)
    return b


def _imm_u32(imm_i32: int) -> int:
    return int(imm_i32) & 0xFFFFFFFF


def _imm_u64(imm_i32: int) -> int:
    return int(imm_i32) & 0xFFFFFFFFFFFFFFFF


@dataclass(frozen=True, slots=True)
class URCInstrV1:
    opcode_u8: int
    rd_u8: int
    rs_u8: int
    rt_u8: int
    imm_i32: int
    raw8: bytes


@dataclass(frozen=True, slots=True)
class URCCapsuleV1:
    pc_u32: int
    flags_u32: int
    pt_root_hash32: bytes
    regs_u64: list[int]  # len=16
    call_depth_u32: int
    call_stack_u32: list[int]  # len=16
    instr_count_u32: int
    instr_bytes: bytes  # len=instr_count*8


def urc_parse_capsule_v1(capsule_bytes: bytes) -> URCCapsuleV1:
    if not isinstance(capsule_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    b = bytes(capsule_bytes)
    if len(b) < (0x010C + 8):
        fail(_REASON_CAPSULE_DECODE_FAIL)

    magic, ver_u32, isa_id_u32, reg_count_u32, page_shift_u32, call_cap_u32, r0_u32, pc_u32, flags_u32 = _URC1_HDR.unpack_from(b, 0)
    if bytes(magic) != b"URC1":
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(ver_u32) != 1:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(isa_id_u32) != 1:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(reg_count_u32) != 16:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(page_shift_u32) != 12:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(call_cap_u32) != 16:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if int(r0_u32) != 0:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    pc = int(pc_u32) & 0xFFFFFFFF
    flags = int(flags_u32) & 0xFFFFFFFF
    if flags & ~0x3:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    halted_b = bool(flags & 0x1)
    error_b = bool(flags & 0x2)
    if halted_b and error_b:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    pt_root = b[0x0024 : 0x0024 + 32]
    if len(pt_root) != 32:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    regs_off = 0x0044
    regs_end = regs_off + _U64_16.size
    if regs_end > len(b):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    regs = [int(x) & 0xFFFFFFFFFFFFFFFF for x in _U64_16.unpack_from(b, regs_off)]

    call_off = 0x00C4
    call_hdr_end = call_off + _CALL_HDR.size
    if call_hdr_end > len(b):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    call_depth_u32, r1_u32 = _CALL_HDR.unpack_from(b, call_off)
    if int(r1_u32) != 0:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    call_depth = int(call_depth_u32) & 0xFFFFFFFF
    if call_depth > 16:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    stack_off = 0x00CC
    stack_end = stack_off + _CALL_STACK.size
    if stack_end > len(b):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    call_stack = [int(x) & 0xFFFFFFFF for x in _CALL_STACK.unpack_from(b, stack_off)]
    for i in range(int(call_depth), 16):
        if int(call_stack[i]) != 0:
            fail(_REASON_CAPSULE_DECODE_FAIL)

    code_hdr_off = 0x010C
    code_hdr_end = code_hdr_off + _CODE_HDR.size
    if code_hdr_end > len(b):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    instr_count_u32, r2_u32 = _CODE_HDR.unpack_from(b, code_hdr_off)
    if int(r2_u32) != 0:
        fail(_REASON_CAPSULE_DECODE_FAIL)
    instr_count = int(instr_count_u32) & 0xFFFFFFFF
    if instr_count < 0:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    instr_bytes_off = code_hdr_end
    instr_bytes_end = instr_bytes_off + (int(instr_count) * 8)
    if instr_bytes_end != len(b):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    instr_bytes = bytes(b[instr_bytes_off:instr_bytes_end])

    # pc_u32 <= instr_count_u32; pc==instr_count allowed only if HALTED==1.
    if pc > int(instr_count):
        fail(_REASON_CAPSULE_DECODE_FAIL)
    if pc == int(instr_count) and not halted_b:
        fail(_REASON_CAPSULE_DECODE_FAIL)

    return URCCapsuleV1(
        pc_u32=int(pc),
        flags_u32=int(flags),
        pt_root_hash32=bytes(pt_root),
        regs_u64=list(regs),
        call_depth_u32=int(call_depth),
        call_stack_u32=list(call_stack),
        instr_count_u32=int(instr_count),
        instr_bytes=bytes(instr_bytes),
    )


def urc_encode_capsule_v1(capsule: URCCapsuleV1) -> bytes:
    if not isinstance(capsule, URCCapsuleV1):
        fail(_REASON_INVARIANT_FAIL)

    pc = int(capsule.pc_u32)
    flags = int(capsule.flags_u32) & 0xFFFFFFFF
    if pc < 0 or pc > 0xFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    if flags & ~0x3:
        fail(_REASON_INVARIANT_FAIL)
    halted_b = bool(flags & 0x1)
    error_b = bool(flags & 0x2)
    if halted_b and error_b:
        fail(_REASON_INVARIANT_FAIL)

    pt_root = _require_bytes32(capsule.pt_root_hash32)

    regs = list(capsule.regs_u64)
    if len(regs) != 16 or any((not isinstance(x, int) or x < 0 or x > 0xFFFFFFFFFFFFFFFF) for x in regs):
        fail(_REASON_INVARIANT_FAIL)

    call_depth = int(capsule.call_depth_u32)
    call_stack = list(capsule.call_stack_u32)
    if call_depth < 0 or call_depth > 16:
        fail(_REASON_INVARIANT_FAIL)
    if len(call_stack) != 16 or any((not isinstance(x, int) or x < 0 or x > 0xFFFFFFFF) for x in call_stack):
        fail(_REASON_INVARIANT_FAIL)
    for i in range(int(call_depth), 16):
        if int(call_stack[i]) != 0:
            fail(_REASON_INVARIANT_FAIL)

    instr_count = int(capsule.instr_count_u32)
    if instr_count < 0 or instr_count > 0xFFFFFFFF:
        fail(_REASON_INVARIANT_FAIL)
    instr_bytes = bytes(capsule.instr_bytes)
    if len(instr_bytes) != int(instr_count) * 8:
        fail(_REASON_INVARIANT_FAIL)

    if pc > int(instr_count):
        fail(_REASON_INVARIANT_FAIL)
    if pc == int(instr_count) and not halted_b:
        fail(_REASON_INVARIANT_FAIL)

    out = bytearray()
    out += _URC1_HDR.pack(
        b"URC1",
        1,
        1,  # isa_id_u32
        16,  # reg_count_u32
        12,  # page_shift_u32
        16,  # call_depth_cap_u32
        0,  # reserved_u32
        int(pc) & 0xFFFFFFFF,
        int(flags) & 0xFFFFFFFF,
    )
    out += bytes(pt_root)
    if len(out) != 0x0044:
        fail(_REASON_INVARIANT_FAIL)
    out += _U64_16.pack(*[int(x) & 0xFFFFFFFFFFFFFFFF for x in regs])
    if len(out) != 0x00C4:
        fail(_REASON_INVARIANT_FAIL)
    out += _CALL_HDR.pack(int(call_depth) & 0xFFFFFFFF, 0)
    out += _CALL_STACK.pack(*[int(x) & 0xFFFFFFFF for x in call_stack])
    if len(out) != 0x010C:
        fail(_REASON_INVARIANT_FAIL)
    out += _CODE_HDR.pack(int(instr_count) & 0xFFFFFFFF, 0)
    out += bytes(instr_bytes)
    expected_len = 0x010C + 8 + (int(instr_count) * 8)
    if len(out) != int(expected_len):
        fail(_REASON_INVARIANT_FAIL)
    return bytes(out)


def _decode_instr_v1(raw8: bytes) -> URCInstrV1:
    if not isinstance(raw8, (bytes, bytearray, memoryview)):
        fail(_REASON_INVARIANT_FAIL)
    b = bytes(raw8)
    if len(b) != 8:
        fail(_REASON_INVARIANT_FAIL)
    opcode = int(b[0])
    rd = int(b[1])
    rs = int(b[2])
    rt = int(b[3])
    imm = int(struct.unpack_from("<i", b, 4)[0])
    return URCInstrV1(opcode_u8=opcode, rd_u8=rd, rs_u8=rs, rt_u8=rt, imm_i32=imm, raw8=b)


def _regs_hash32(*, pc_after_u32: int, flags_u32: int, regs_u64: list[int], call_depth_u32: int, call_stack_u32: list[int]) -> bytes:
    if len(regs_u64) != 16 or len(call_stack_u32) != 16:
        fail(_REASON_INVARIANT_FAIL)
    out = bytearray()
    out += _URC_REGS_DOMAIN
    out += _u32_le(int(pc_after_u32) & 0xFFFFFFFF)
    out += _u32_le(int(flags_u32) & 0xFFFFFFFF)
    for r in regs_u64:
        out += _u64_le(int(r) & 0xFFFFFFFFFFFFFFFF)
    out += _u32_le(int(call_depth_u32) & 0xFFFFFFFF)
    for x in call_stack_u32:
        out += _u32_le(int(x) & 0xFFFFFFFF)
    return _sha25632(bytes(out))


def _writes_hash32(*, writes: dict[int, bytes]) -> bytes:
    if not writes:
        return _sha25632(_URC_WRITES_EMPTY_DOMAIN)
    items = sorted(((int(pid), _require_bytes32(h)) for pid, h in writes.items()), key=lambda t: t[0])
    out = bytearray()
    out += _URC_WRITES_DOMAIN
    out += _u32_le(len(items))
    for page_id, page_hash32 in items:
        out += _u32_le(int(page_id) & 0xFFFFFFFF)
        out += bytes(page_hash32)
    return _sha25632(bytes(out))


def _urd_bytes_v1(
    *,
    step_index_u64: int,
    pc_before_u32: int,
    pc_after_u32: int,
    instr_bytes_8: bytes,
    regs_hash32: bytes,
    memroot_hash32: bytes,
    writes_hash32: bytes,
) -> bytes:
    if not isinstance(instr_bytes_8, (bytes, bytearray, memoryview)) or len(bytes(instr_bytes_8)) != 8:
        fail(_REASON_INVARIANT_FAIL)
    if len(regs_hash32) != 32 or len(memroot_hash32) != 32 or len(writes_hash32) != 32:
        fail(_REASON_INVARIANT_FAIL)
    out = bytearray()
    out += _URD_MAGIC
    out += struct.pack("<I", 1)  # version_u32
    out += struct.pack("<Q", int(step_index_u64) & 0xFFFFFFFFFFFFFFFF)
    out += _u32_le(int(pc_before_u32) & 0xFFFFFFFF)
    out += _u32_le(int(pc_after_u32) & 0xFFFFFFFF)
    out += bytes(instr_bytes_8)
    out += bytes(regs_hash32)
    out += bytes(memroot_hash32)
    out += bytes(writes_hash32)
    out += _u32_le(0)
    out += _u32_le(0)
    if len(out) != 136:
        fail(_REASON_INVARIANT_FAIL)
    return bytes(out)


def _require_capsule_def_v1(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        fail(_REASON_INVARIANT_FAIL)
    try:
        validate_schema(obj, "urc_capsule_def_v1")
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_INVARIANT_FAIL)
    if str(obj.get("schema_id", "")).strip() != "urc_capsule_def_v1":
        fail(_REASON_INVARIANT_FAIL)

    capsule_def_id = ensure_sha256(obj.get("capsule_def_id"), reason=_REASON_INVARIANT_FAIL)
    tmp = dict(obj)
    tmp["capsule_def_id"] = "sha256:" + ("0" * 64)
    computed = sha256_prefixed(gcj1_canon_bytes(tmp))
    if str(computed) != str(capsule_def_id):
        fail(_REASON_INVARIANT_FAIL)

    if str(obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(_REASON_INVARIANT_FAIL)
    opset_id = str(obj.get("opset_id", "")).strip()
    if not opset_id.startswith("opset:eudrs_u_v1:sha256:"):
        fail(_REASON_INVARIANT_FAIL)
    handle = str(obj.get("handle", "")).strip()
    if not handle.startswith("capsule/"):
        fail(_REASON_INVARIANT_FAIL)

    if str(obj.get("isa_kind", "")).strip() != "URC_ISA_V1":
        fail(_REASON_INVARIANT_FAIL)

    # Fixed Phase-7 constants.
    if int(obj.get("page_shift_u32", -1)) != 12:
        fail(_REASON_INVARIANT_FAIL)
    if int(obj.get("pt_fanout_u32", -1)) != 256:
        fail(_REASON_INVARIANT_FAIL)
    if int(obj.get("pt_depth_u32", -1)) != 4:
        fail(_REASON_INVARIANT_FAIL)
    if int(obj.get("call_depth_cap_u32", -1)) != 16:
        fail(_REASON_INVARIANT_FAIL)

    budgets = obj.get("budgets")
    if not isinstance(budgets, dict):
        fail(_REASON_INVARIANT_FAIL)
    required_budget_keys = {"instr_step_cap_u64", "mem_write_ops_cap_u64", "mem_write_pages_cap_u32"}
    if set(budgets.keys()) != required_budget_keys:
        fail(_REASON_INVARIANT_FAIL)

    def _u64(name: str, *, min_v: int) -> int:
        v = budgets.get(name)
        if not isinstance(v, int) or v < int(min_v) or v > 0xFFFFFFFFFFFFFFFF:
            fail(_REASON_INVARIANT_FAIL)
        return int(v)

    def _u32(name: str, *, min_v: int) -> int:
        v = budgets.get(name)
        if not isinstance(v, int) or v < int(min_v) or v > 0xFFFFFFFF:
            fail(_REASON_INVARIANT_FAIL)
        return int(v)

    _u64("instr_step_cap_u64", min_v=1)
    _u64("mem_write_ops_cap_u64", min_v=0)
    _u32("mem_write_pages_cap_u32", min_v=0)

    capsule_bin_ref = require_artifact_ref_v1(obj.get("capsule_bin_ref"), reason=_REASON_INVARIANT_FAIL)
    if not str(capsule_bin_ref.get("artifact_relpath", "")).endswith(".urc_capsule_v1.bin"):
        fail(_REASON_INVARIANT_FAIL)

    return dict(obj)


def urc_step_capsule_v1(
    *,
    capsule_bytes: bytes,
    capsule_def_obj: dict,
    step_budget_u64: int,
    load_bytes_by_hash32: Callable[[bytes, str], bytes],
) -> tuple[
    bytes,  # capsule_after_bytes
    bytes,  # pt_root_after32
    bytes,  # h_urc_tail32
    int,  # steps_executed_u64
    dict[bytes, bytes],  # new_pages_by_hash32
    dict[bytes, bytes],  # new_ptnodes_by_hash32
]:
    if not callable(load_bytes_by_hash32):
        fail(_REASON_INVARIANT_FAIL)

    cap_def = _require_capsule_def_v1(capsule_def_obj)
    budgets = dict(cap_def["budgets"])
    instr_step_cap_u64 = int(budgets["instr_step_cap_u64"])
    mem_write_ops_cap_u64 = int(budgets["mem_write_ops_cap_u64"])
    mem_write_pages_cap_u32 = int(budgets["mem_write_pages_cap_u32"])

    if not isinstance(step_budget_u64, int) or int(step_budget_u64) < 1:
        fail(_REASON_INVARIANT_FAIL)
    step_budget = int(step_budget_u64)
    if step_budget > int(instr_step_cap_u64):
        fail(_REASON_BUDGET_EXCEEDED)

    cap = urc_parse_capsule_v1(capsule_bytes)

    # Local overlay cache for newly created pages/nodes (required for intra-call LOAD after STORE).
    overlay: dict[bytes, bytes] = {}

    def _load(hash32: bytes, kind: str) -> bytes:
        h = _require_bytes32(hash32)
        if h in overlay:
            return bytes(overlay[h])
        raw = load_bytes_by_hash32(h, str(kind))
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            fail(_REASON_INVARIANT_FAIL)
        b = bytes(raw)
        if _sha25632(b) != bytes(h):
            fail(_REASON_EXEC_FAIL)
        return b

    regs = list(cap.regs_u64)
    call_depth = int(cap.call_depth_u32)
    call_stack = list(cap.call_stack_u32)
    pc = int(cap.pc_u32)
    flags = int(cap.flags_u32)
    pt_root = bytes(cap.pt_root_hash32)

    instr_count = int(cap.instr_count_u32)
    instr_bytes = bytes(cap.instr_bytes)

    steps_executed = 0
    store_ops = 0
    modified_page_ids: set[int] = set()

    H = ZERO32

    new_pages_total: dict[bytes, bytes] = {}
    new_nodes_total: dict[bytes, bytes] = {}

    while steps_executed < int(step_budget):
        if flags & 0x1:  # HALTED
            break

        if int(pc) >= int(instr_count):
            flags |= 0x2  # ERROR
            fail(_REASON_EXEC_FAIL)

        pc_before = int(pc) & 0xFFFFFFFF
        ins_off = int(pc_before) * 8
        raw8 = instr_bytes[ins_off : ins_off + 8]
        if len(raw8) != 8:
            flags |= 0x2
            fail(_REASON_EXEC_FAIL)
        ins = _decode_instr_v1(raw8)

        writes_this_step: dict[int, bytes] = {}

        opcode = int(ins.opcode_u8)
        if opcode == 0x00:  # NOP
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x01:  # HALT
            flags |= 0x1
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x02:  # MOVI
            rd = int(ins.rd_u8)
            if rd < 0 or rd >= 16:
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            regs[rd] = _imm_u64(ins.imm_i32)
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x03:  # ADD
            rd, rs, rt = int(ins.rd_u8), int(ins.rs_u8), int(ins.rt_u8)
            if any(x < 0 or x >= 16 for x in (rd, rs, rt)):
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            regs[rd] = (int(regs[rs]) + int(regs[rt])) & 0xFFFFFFFFFFFFFFFF
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x0C:  # LOAD64
            rd, rs = int(ins.rd_u8), int(ins.rs_u8)
            if any(x < 0 or x >= 16 for x in (rd, rs)):
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            addr_u64 = (int(regs[rs]) + int(_imm_u64(ins.imm_i32))) & 0xFFFFFFFFFFFFFFFF
            # urc_mem_read64_v1 enforces alignment.
            val_u64 = urc_mem_read64_v1(pt_root_hash32=pt_root, addr_u64=int(addr_u64), load_bytes_by_hash32=_load)
            regs[rd] = int(val_u64) & 0xFFFFFFFFFFFFFFFF
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x0D:  # STORE64
            rs, rt = int(ins.rs_u8), int(ins.rt_u8)
            if any(x < 0 or x >= 16 for x in (rs, rt)):
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            if int(store_ops) + 1 > int(mem_write_ops_cap_u64):
                flags |= 0x2
                fail(_REASON_BUDGET_EXCEEDED)
            addr_u64 = (int(regs[rs]) + int(_imm_u64(ins.imm_i32))) & 0xFFFFFFFFFFFFFFFF
            page_id_u32 = (int(addr_u64) >> 12) & 0xFFFFFFFF
            modified_page_ids.add(int(page_id_u32))
            if len(modified_page_ids) > int(mem_write_pages_cap_u32):
                flags |= 0x2
                fail(_REASON_BUDGET_EXCEEDED)

            pt_root_after32, new_pages, new_nodes = urc_mem_write64_v1(
                pt_root_hash32=pt_root,
                addr_u64=int(addr_u64),
                value_u64=int(regs[rt]),
                load_bytes_by_hash32=_load,
            )
            pt_root = bytes(pt_root_after32)

            # Track page hash for writes_hash32.
            if len(new_pages) != 1:
                flags |= 0x2
                fail(_REASON_INVARIANT_FAIL)
            (page_hash_after32, page_bytes_after) = next(iter(new_pages.items()))
            if _sha25632(bytes(page_bytes_after)) != bytes(page_hash_after32):
                flags |= 0x2
                fail(_REASON_INVARIANT_FAIL)
            writes_this_step[int(page_id_u32)] = bytes(page_hash_after32)

            # Merge artifacts + publish to overlay for subsequent loads in this call.
            for h, bb in new_pages.items():
                overlay[bytes(h)] = bytes(bb)
                new_pages_total[bytes(h)] = bytes(bb)
            for h, bb in new_nodes.items():
                overlay[bytes(h)] = bytes(bb)
                new_nodes_total[bytes(h)] = bytes(bb)

            store_ops += 1
            pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x0E:  # BEQ
            rs, rt = int(ins.rs_u8), int(ins.rt_u8)
            if any(x < 0 or x >= 16 for x in (rs, rt)):
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            if int(regs[rs]) == int(regs[rt]):
                pc = (int(pc) + 1 + int(ins.imm_i32)) & 0xFFFFFFFF
            else:
                pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x0F:  # BNE
            rs, rt = int(ins.rs_u8), int(ins.rt_u8)
            if any(x < 0 or x >= 16 for x in (rs, rt)):
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            if int(regs[rs]) != int(regs[rt]):
                pc = (int(pc) + 1 + int(ins.imm_i32)) & 0xFFFFFFFF
            else:
                pc = (int(pc) + 1) & 0xFFFFFFFF

        elif opcode == 0x12:  # JMP
            pc = _imm_u32(ins.imm_i32)

        elif opcode == 0x13:  # CALL
            if int(call_depth) >= 16:
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            ret_addr = (int(pc) + 1) & 0xFFFFFFFF
            call_stack[int(call_depth)] = int(ret_addr)
            call_depth += 1
            pc = _imm_u32(ins.imm_i32)

        elif opcode == 0x14:  # RET
            if int(call_depth) <= 0:
                flags |= 0x2
                fail(_REASON_EXEC_FAIL)
            call_depth -= 1
            pc = int(call_stack[int(call_depth)]) & 0xFFFFFFFF
            call_stack[int(call_depth)] = 0

        else:
            flags |= 0x2
            fail(_REASON_EXEC_FAIL)

        # URD digest for this step uses state AFTER executing the instruction.
        regs_hash32 = _regs_hash32(
            pc_after_u32=int(pc),
            flags_u32=int(flags),
            regs_u64=regs,
            call_depth_u32=int(call_depth),
            call_stack_u32=call_stack,
        )
        writes_hash32 = _writes_hash32(writes=writes_this_step)
        urd = _urd_bytes_v1(
            step_index_u64=int(steps_executed),
            pc_before_u32=int(pc_before),
            pc_after_u32=int(pc),
            instr_bytes_8=raw8,
            regs_hash32=regs_hash32,
            memroot_hash32=bytes(pt_root),
            writes_hash32=writes_hash32,
        )
        H = _sha25632(bytes(H) + urd)
        steps_executed += 1

    cap_after = URCCapsuleV1(
        pc_u32=int(pc) & 0xFFFFFFFF,
        flags_u32=int(flags) & 0xFFFFFFFF,
        pt_root_hash32=bytes(pt_root),
        regs_u64=list(regs),
        call_depth_u32=int(call_depth) & 0xFFFFFFFF,
        call_stack_u32=list(call_stack),
        instr_count_u32=int(instr_count) & 0xFFFFFFFF,
        instr_bytes=bytes(instr_bytes),
    )
    capsule_after_bytes = urc_encode_capsule_v1(cap_after)

    return (
        bytes(capsule_after_bytes),
        bytes(pt_root),
        bytes(H),
        int(steps_executed),
        dict(new_pages_total),
        dict(new_nodes_total),
    )


def verify_universality_cert_v1(
    *,
    universality_cert_obj: dict,
    load_bytes_by_artifact_id: Callable[[str], bytes],
    load_bytes_by_hash32: Callable[[bytes, str], bytes],
) -> tuple[bool, str]:
    """
    Returns (valid, reason_code).
    Must recompute each golden vector by executing the capsule_before for max_steps_u64,
    requiring HALT, and matching capsule_after hash, memroot, and h_urc_tail32 exactly.
    """

    try:
        if not callable(load_bytes_by_artifact_id) or not callable(load_bytes_by_hash32):
            return False, _REASON_GOLDEN_MISMATCH

        if not isinstance(universality_cert_obj, dict):
            return False, _REASON_GOLDEN_MISMATCH
        try:
            validate_schema(universality_cert_obj, "universality_cert_v1")
        except Exception:  # noqa: BLE001
            return False, _REASON_GOLDEN_MISMATCH
        if str(universality_cert_obj.get("schema_id", "")).strip() != "universality_cert_v1":
            return False, _REASON_GOLDEN_MISMATCH

        if not isinstance(universality_cert_obj.get("epoch_u64"), int):
            return False, _REASON_GOLDEN_MISMATCH
        if str(universality_cert_obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
            return False, _REASON_GOLDEN_MISMATCH
        opset_id = str(universality_cert_obj.get("opset_id", "")).strip()
        if not opset_id.startswith("opset:eudrs_u_v1:sha256:"):
            return False, _REASON_GOLDEN_MISMATCH

        urc_vm = universality_cert_obj.get("urc_vm")
        if not isinstance(urc_vm, dict):
            return False, _REASON_GOLDEN_MISMATCH
        if str(urc_vm.get("isa_kind", "")).strip() != "URC_ISA_V1":
            return False, _REASON_GOLDEN_MISMATCH
        if int(urc_vm.get("isa_id_u32", -1)) != 1:
            return False, _REASON_GOLDEN_MISMATCH
        if int(urc_vm.get("page_shift_u32", -1)) != 12:
            return False, _REASON_GOLDEN_MISMATCH
        if int(urc_vm.get("pt_fanout_u32", -1)) != 256:
            return False, _REASON_GOLDEN_MISMATCH
        if int(urc_vm.get("pt_depth_u32", -1)) != 4:
            return False, _REASON_GOLDEN_MISMATCH
        if int(urc_vm.get("call_depth_cap_u32", -1)) != 16:
            return False, _REASON_GOLDEN_MISMATCH

        golden = urc_vm.get("golden_vectors")
        if not isinstance(golden, list):
            return False, _REASON_GOLDEN_MISMATCH

        # Sorted, unique vector names.
        prev: str | None = None
        seen: set[str] = set()
        for row in golden:
            if not isinstance(row, dict):
                return False, _REASON_GOLDEN_MISMATCH
            name = str(row.get("vector_name", ""))
            if prev is not None and name < prev:
                return False, _REASON_GOLDEN_MISMATCH
            prev = name
            if name in seen:
                return False, _REASON_GOLDEN_MISMATCH
            seen.add(name)

            before_id = ensure_sha256(row.get("capsule_before_id"), reason=_REASON_INVARIANT_FAIL)
            after_id = ensure_sha256(row.get("capsule_after_id"), reason=_REASON_INVARIANT_FAIL)
            max_steps_u64 = row.get("max_steps_u64")
            if not isinstance(max_steps_u64, int) or int(max_steps_u64) < 1:
                return False, _REASON_GOLDEN_MISMATCH

            exp_memroot_hex = str(row.get("expected_memroot_after32_hex", "")).strip()
            exp_tail_hex = str(row.get("expected_h_urc_tail32_hex", "")).strip()
            if len(exp_memroot_hex) != 64 or len(exp_tail_hex) != 64:
                return False, _REASON_GOLDEN_MISMATCH
            try:
                exp_memroot = bytes.fromhex(exp_memroot_hex)
                exp_tail = bytes.fromhex(exp_tail_hex)
            except Exception:
                return False, _REASON_GOLDEN_MISMATCH
            if len(exp_memroot) != 32 or len(exp_tail) != 32:
                return False, _REASON_GOLDEN_MISMATCH

            # Load + verify capsule_before bytes by artifact_id.
            before_bytes = load_bytes_by_artifact_id(str(before_id))
            if not isinstance(before_bytes, (bytes, bytearray, memoryview)):
                return False, _REASON_GOLDEN_MISMATCH
            before_bin = bytes(before_bytes)
            if sha256_prefixed(before_bin) != str(before_id):
                return False, _REASON_GOLDEN_MISMATCH
            _ = urc_parse_capsule_v1(before_bin)

            # Load + verify expected capsule_after bytes by artifact_id (defense-in-depth).
            after_bytes = load_bytes_by_artifact_id(str(after_id))
            if not isinstance(after_bytes, (bytes, bytearray, memoryview)):
                return False, _REASON_GOLDEN_MISMATCH
            after_bin = bytes(after_bytes)
            if sha256_prefixed(after_bin) != str(after_id):
                return False, _REASON_GOLDEN_MISMATCH
            _ = urc_parse_capsule_v1(after_bin)

            # Synthetic capsule_def for this vector (budgets only need to permit the run).
            before_hex = str(before_id).split(":", 1)[1]
            capsule_def_obj = {
                "schema_id": "urc_capsule_def_v1",
                "capsule_def_id": "sha256:" + ("0" * 64),
                "dc1_id": "dc1:q32_v1",
                "opset_id": opset_id,
                "handle": f"capsule/universality/{name.lower()}",
                "isa_kind": "URC_ISA_V1",
                "page_shift_u32": 12,
                "pt_fanout_u32": 256,
                "pt_depth_u32": 4,
                "call_depth_cap_u32": 16,
                "budgets": {
                    "instr_step_cap_u64": int(max_steps_u64),
                    "mem_write_ops_cap_u64": int(max_steps_u64),
                    "mem_write_pages_cap_u32": 256,
                },
                "capsule_bin_ref": {
                    "artifact_id": str(before_id),
                    "artifact_relpath": f"polymath/registry/eudrs_u/capsules/sha256_{before_hex}.urc_capsule_v1.bin",
                },
            }
            tmp = dict(capsule_def_obj)
            tmp["capsule_def_id"] = "sha256:" + ("0" * 64)
            capsule_def_obj["capsule_def_id"] = sha256_prefixed(gcj1_canon_bytes(tmp))

            capsule_after_bytes, memroot_after32, h_tail32, _steps, _new_pages, _new_nodes = urc_step_capsule_v1(
                capsule_bytes=before_bin,
                capsule_def_obj=capsule_def_obj,
                step_budget_u64=int(max_steps_u64),
                load_bytes_by_hash32=load_bytes_by_hash32,
            )

            # Require HALT.
            cap_after = urc_parse_capsule_v1(capsule_after_bytes)
            if not (int(cap_after.flags_u32) & 0x1):
                return False, _REASON_GOLDEN_MISMATCH
            if int(cap_after.flags_u32) & 0x2:
                return False, _REASON_GOLDEN_MISMATCH

            if bytes(memroot_after32) != bytes(exp_memroot):
                return False, _REASON_GOLDEN_MISMATCH
            if bytes(h_tail32) != bytes(exp_tail):
                return False, _REASON_GOLDEN_MISMATCH

            computed_after_id = sha256_prefixed(bytes(capsule_after_bytes))
            if str(computed_after_id) != str(after_id):
                return False, _REASON_GOLDEN_MISMATCH

        return True, "OK"

    except OmegaV18Error:
        return False, _REASON_GOLDEN_MISMATCH
    except Exception:  # noqa: BLE001 - fail-closed
        return False, _REASON_GOLDEN_MISMATCH


__all__ = [
    "URCCapsuleV1",
    "URCInstrV1",
    "urc_encode_capsule_v1",
    "urc_parse_capsule_v1",
    "urc_step_capsule_v1",
    "verify_universality_cert_v1",
]
