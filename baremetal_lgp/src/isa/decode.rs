use crate::isa::encoding::{IMM14_MASK, OPCODE_MASK, REG_MASK};
use crate::isa::op::Op;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct DecodedInsn {
    pub opcode_u8: u8,
    pub op: Option<Op>,
    pub rd: u8,
    pub ra: u8,
    pub rb: u8,
    pub imm14_u: u32,
}

pub fn decode(word: u32) -> DecodedInsn {
    let opcode_u8 = (word & OPCODE_MASK) as u8;
    let rd = ((word >> 6) & REG_MASK) as u8;
    let ra = ((word >> 10) & REG_MASK) as u8;
    let rb = ((word >> 14) & REG_MASK) as u8;
    let imm14_u = (word >> 18) & IMM14_MASK;

    DecodedInsn {
        opcode_u8,
        op: Op::from_u8(opcode_u8),
        rd,
        ra,
        rb,
        imm14_u,
    }
}
