use crate::isa::encoding;
use crate::isa::op::Op;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum DecodeErr {
    InvalidOpcode(u8),
}

pub fn decode_op(opcode: u8) -> Result<Op, DecodeErr> {
    match opcode {
        0x00 => Ok(Op::Halt),
        0x01 => Ok(Op::Nop),
        0x02 => Ok(Op::FMov),
        0x03 => Ok(Op::FAdd),
        0x04 => Ok(Op::FSub),
        0x05 => Ok(Op::FMul),
        0x06 => Ok(Op::FFma),
        0x07 => Ok(Op::FAbs),
        0x08 => Ok(Op::FNeg),
        0x09 => Ok(Op::IMov),
        0x0A => Ok(Op::IAdd),
        0x0B => Ok(Op::ISub),
        0x0C => Ok(Op::IAnd),
        0x0D => Ok(Op::IOr),
        0x0E => Ok(Op::IXor),
        0x0F => Ok(Op::IShl),
        0x10 => Ok(Op::IShr),
        0x11 => Ok(Op::LdF),
        0x12 => Ok(Op::StF),
        0x13 => Ok(Op::FConst),
        0x14 => Ok(Op::IConst),
        0x15 => Ok(Op::LdMU32),
        0x16 => Ok(Op::LdMF32),
        0x17 => Ok(Op::IToF),
        0x18 => Ok(Op::FToI),
        0x19 => Ok(Op::FTanh),
        0x1A => Ok(Op::FSigm),
        0x1B => Ok(Op::Jmp),
        0x1C => Ok(Op::Jz),
        0x1D => Ok(Op::Jnz),
        0x1E => Ok(Op::Loop),
        0x1F => Ok(Op::Call),
        0x20 => Ok(Op::Ret),
        0x21 => Ok(Op::VAdd),
        0x22 => Ok(Op::VMul),
        0x23 => Ok(Op::VFma),
        0x24 => Ok(Op::VDot),
        0x25 => Ok(Op::VCAdd),
        0x26 => Ok(Op::VCMul),
        0x27 => Ok(Op::VCDot),
        0x28 => Ok(Op::Gemm),
        0x3F => Ok(Op::CallLib),
        _ => Err(DecodeErr::InvalidOpcode(opcode)),
    }
}

pub fn decode_word(word: u32) -> Result<(Op, u8, u8, u8, u16), DecodeErr> {
    let opcode = (word & 0x3F) as u8;
    let op = decode_op(opcode)?;
    let (_, rd, ra, rb, imm14_u) = encoding::decode(word);
    Ok((op, rd, ra, rb, imm14_u))
}
