from __future__ import annotations

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_q32ops_v1 import S64_MAX, add_sat, mul_q32
from cdel.v18_0.eudrs_u.vpvm_q32_vm_v1 import (
    OP_ADD_SAT,
    OP_ASSERT1,
    OP_CMP_EQ_S64,
    OP_HALT,
    OP_LOADI,
    OP_MEM_LOAD_S64,
    OP_MEM_STORE_S64,
    OP_MUL_Q32_SAT,
    VpvmQ32VmError,
    decode_vpvm_program_v1,
    encode_vpvm_instr_v1,
    execute_vpvm_q32_v1,
)


def _caps_all() -> dict:
    max_off = 0x00FFFFFFFFFFFFFF
    return {
        "mem": {
            "max_addr_u64": 0xFFFFFFFFFFFFFFFF,
            "allowed_segs_u8": [0, 1, 2, 3],
            "seg_limits": [
                {"seg_u8": 0, "max_addr_u64": max_off},
                {"seg_u8": 1, "max_addr_u64": max_off},
                {"seg_u8": 2, "max_addr_u64": max_off},
                {"seg_u8": 3, "max_addr_u64": max_off},
            ],
        }
    }


def test_vpvm_q32_vm_v1_golden_add_mul_mem_fast() -> None:
    q32_one = 1 << 32
    a = q32_one
    b = 2 * q32_one
    exp_mul = mul_q32(a, b)
    exp_add = add_sat(S64_MAX, 1)
    assert exp_add == S64_MAX  # saturating

    seg1_base = 1 << 56
    val = 0x12345678

    prog = b"".join(
        [
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=0, imm_s64=S64_MAX),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=1, imm_s64=1),
            encode_vpvm_instr_v1(opcode_u16=OP_ADD_SAT, rd_u8=2, ra_u8=0, rb_u8=1),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=3, imm_s64=S64_MAX),
            encode_vpvm_instr_v1(opcode_u16=OP_CMP_EQ_S64, rd_u8=4, ra_u8=2, rb_u8=3),
            encode_vpvm_instr_v1(opcode_u16=OP_ASSERT1, ra_u8=4),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=5, imm_s64=a),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=6, imm_s64=b),
            encode_vpvm_instr_v1(opcode_u16=OP_MUL_Q32_SAT, rd_u8=7, ra_u8=5, rb_u8=6),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=8, imm_s64=exp_mul),
            encode_vpvm_instr_v1(opcode_u16=OP_CMP_EQ_S64, rd_u8=9, ra_u8=7, rb_u8=8),
            encode_vpvm_instr_v1(opcode_u16=OP_ASSERT1, ra_u8=9),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=10, imm_s64=seg1_base),
            encode_vpvm_instr_v1(opcode_u16=OP_LOADI, rd_u8=11, imm_s64=val),
            encode_vpvm_instr_v1(opcode_u16=OP_MEM_STORE_S64, ra_u8=10, rb_u8=11, imm_s64=0),
            encode_vpvm_instr_v1(opcode_u16=OP_MEM_LOAD_S64, rd_u8=12, ra_u8=10, imm_s64=0),
            encode_vpvm_instr_v1(opcode_u16=OP_CMP_EQ_S64, rd_u8=13, ra_u8=12, rb_u8=11),
            encode_vpvm_instr_v1(opcode_u16=OP_ASSERT1, ra_u8=13),
            encode_vpvm_instr_v1(opcode_u16=OP_HALT),
        ]
    )

    st = execute_vpvm_q32_v1(program_bytes=prog, initial_memory_image=None, caps=_caps_all(), max_steps=1024)
    assert st.halted is True
    assert st.regs_s64[2] == S64_MAX
    assert st.regs_s64[7] == exp_mul
    # Full address uses segment in the top byte.
    full_addr = (1 << 56) | 0
    assert st.mem_u64.get(full_addr) == val


def test_vpvm_q32_vm_v1_reserved_bytes_fail_fast() -> None:
    # Make one instruction with a non-zero reserved byte.
    bad = bytearray(encode_vpvm_instr_v1(opcode_u16=OP_HALT))
    bad[-1] = 1
    with pytest.raises(VpvmQ32VmError):
        _ = decode_vpvm_program_v1(bytes(bad))

