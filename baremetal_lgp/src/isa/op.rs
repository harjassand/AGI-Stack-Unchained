#[repr(u8)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Op {
    Halt = 0x00,
    Nop = 0x01,

    // scalar float
    FMov = 0x02,
    FAdd = 0x03,
    FSub = 0x04,
    FMul = 0x05,
    FFma = 0x06, // f[rd] += f[ra] * f[rb]
    FAbs = 0x07,
    FNeg = 0x08,

    // scalar int
    IMov = 0x09,
    IAdd = 0x0A,
    ISub = 0x0B,
    IAnd = 0x0C,
    IOr = 0x0D,
    IXor = 0x0E,
    IShl = 0x0F, // i[rd] = i[ra] << (imm14_u & 31)
    IShr = 0x10, // i[rd] = i[ra] >> (imm14_u & 31) (arithmetic)

    // loads/stores
    LdF = 0x11, // f[rd] = scratch[i[ra] + imm14_s]
    StF = 0x12, // scratch[i[ra] + imm14_s] = f[rd]

    // constants/meta
    FConst = 0x13, // f[rd] = const_pool[imm14_u & 127]
    IConst = 0x14, // i[rd] = imm14_s
    LdMU32 = 0x15, // i[rd] = meta_u32[imm14_u & 15]
    LdMF32 = 0x16, // f[rd] = meta_f32[imm14_u & 15]
    IToF = 0x17,   // f[rd] = i[ra] as f32
    FToI = 0x18,   // i[rd] = f[ra] as i32 (trunc toward 0)

    // nonlinear
    FTanh = 0x19,
    FSigm = 0x1A,

    // control flow (PC-relative imm14_s)
    Jmp = 0x1B,
    Jz = 0x1C, // if i[ra]==0 pc += imm14_s else pc++
    Jnz = 0x1D,
    Loop = 0x1E, // i[ra] -= 1; if i[ra]!=0 pc += imm14_s else pc++

    Call = 0x1F, // push return; pc += imm14_s
    Ret = 0x20,  // pop return; restore

    // vector real (len = imm14_u)
    VAdd = 0x21, // dst=i[rd], x=i[ra], y=i[rb]
    VMul = 0x22,
    VFma = 0x23, // dst += x*y
    VDot = 0x24, // f[rd] = dot(x,y,len), x=i[ra], y=i[rb]

    // vector complex interleaved, lenC = imm14_u (complex count, not words)
    VCAdd = 0x25, // dst=i[rd], x=i[ra], y=i[rb]
    VCMul = 0x26,
    VCDot = 0x27, // c[rd&7] = conj(x)·y, x=i[ra], y=i[rb]

    // GEMM (dims in meta; imm14 ignored for v0)
    Gemm = 0x28, // C=i[rd], A=i[ra], B=i[rb]

    // reserved: 0x29..0x3E

    // FLAW 2 FIX: library call is explicit, stable, and LAST opcode
    CallLib = 0x3F, // slot = imm14_u & 255
}

impl Op {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            0x00 => Some(Self::Halt),
            0x01 => Some(Self::Nop),
            0x02 => Some(Self::FMov),
            0x03 => Some(Self::FAdd),
            0x04 => Some(Self::FSub),
            0x05 => Some(Self::FMul),
            0x06 => Some(Self::FFma),
            0x07 => Some(Self::FAbs),
            0x08 => Some(Self::FNeg),
            0x09 => Some(Self::IMov),
            0x0A => Some(Self::IAdd),
            0x0B => Some(Self::ISub),
            0x0C => Some(Self::IAnd),
            0x0D => Some(Self::IOr),
            0x0E => Some(Self::IXor),
            0x0F => Some(Self::IShl),
            0x10 => Some(Self::IShr),
            0x11 => Some(Self::LdF),
            0x12 => Some(Self::StF),
            0x13 => Some(Self::FConst),
            0x14 => Some(Self::IConst),
            0x15 => Some(Self::LdMU32),
            0x16 => Some(Self::LdMF32),
            0x17 => Some(Self::IToF),
            0x18 => Some(Self::FToI),
            0x19 => Some(Self::FTanh),
            0x1A => Some(Self::FSigm),
            0x1B => Some(Self::Jmp),
            0x1C => Some(Self::Jz),
            0x1D => Some(Self::Jnz),
            0x1E => Some(Self::Loop),
            0x1F => Some(Self::Call),
            0x20 => Some(Self::Ret),
            0x21 => Some(Self::VAdd),
            0x22 => Some(Self::VMul),
            0x23 => Some(Self::VFma),
            0x24 => Some(Self::VDot),
            0x25 => Some(Self::VCAdd),
            0x26 => Some(Self::VCMul),
            0x27 => Some(Self::VCDot),
            0x28 => Some(Self::Gemm),
            0x3F => Some(Self::CallLib),
            _ => None,
        }
    }
}
