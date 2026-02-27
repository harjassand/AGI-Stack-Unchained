use crate::abi::SCRATCH_MASK_I32;

pub const OPCODE_MASK: u32 = 0x3F;
pub const REG_MASK: u32 = 0x0F;
pub const IMM14_MASK: u32 = 0x3FFF;

pub fn imm14_s(imm14_u: u32) -> i32 {
    ((imm14_u as i32) << 18) >> 18
}

pub fn ring_addr(base_i32: i32, imm14_u: u32) -> usize {
    ((base_i32 + imm14_s(imm14_u)) & SCRATCH_MASK_I32) as usize
}

pub fn encode(opcode: u8, rd: u8, ra: u8, rb: u8, imm14_u: u16) -> u32 {
    (u32::from(opcode) & OPCODE_MASK)
        | ((u32::from(rd) & REG_MASK) << 6)
        | ((u32::from(ra) & REG_MASK) << 10)
        | ((u32::from(rb) & REG_MASK) << 14)
        | ((u32::from(imm14_u) & IMM14_MASK) << 18)
}
