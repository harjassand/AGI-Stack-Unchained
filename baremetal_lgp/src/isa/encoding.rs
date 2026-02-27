use crate::isa::op::Op;

pub fn encode(op: Op, rd: u8, ra: u8, rb: u8, imm14_u: u16) -> u32 {
    (op as u32)
        | ((u32::from(rd) & 0x0F) << 6)
        | ((u32::from(ra) & 0x0F) << 10)
        | ((u32::from(rb) & 0x0F) << 14)
        | ((u32::from(imm14_u) & 0x3FFF) << 18)
}

pub fn decode(word: u32) -> (Op, u8, u8, u8, u16) {
    let opcode = (word & 0x3F) as u8;
    let op = Op::from_u8(opcode)
        .unwrap_or_else(|| panic!("invalid opcode in encoding::decode: {opcode:#04x}"));
    let rd = ((word >> 6) & 0x0F) as u8;
    let ra = ((word >> 10) & 0x0F) as u8;
    let rb = ((word >> 14) & 0x0F) as u8;
    let imm14_u = ((word >> 18) & 0x3FFF) as u16;
    (op, rd, ra, rb, imm14_u)
}

pub fn imm14_s(imm14_u: u16) -> i32 {
    ((i32::from(imm14_u)) << 18) >> 18
}
