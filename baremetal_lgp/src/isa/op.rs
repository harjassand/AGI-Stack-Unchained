#[repr(u8)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Op {
    Halt = 0x00,
    Nop = 0x01,

    FMov = 0x02,
    FAdd = 0x03,
    FSub = 0x04,
    FMul = 0x05,
    FFma = 0x06,
    FAbs = 0x07,
    FNeg = 0x08,

    IMov = 0x09,
    IAdd = 0x0A,
    ISub = 0x0B,
    IAnd = 0x0C,
    IOr = 0x0D,
    IXor = 0x0E,
    IShl = 0x0F,
    IShr = 0x10,

    LdF = 0x11,
    StF = 0x12,

    FConst = 0x13,
    IConst = 0x14,
    LdMU32 = 0x15,
    LdMF32 = 0x16,
    IToF = 0x17,
    FToI = 0x18,

    FTanh = 0x19,
    FSigm = 0x1A,

    Jmp = 0x1B,
    Jz = 0x1C,
    Jnz = 0x1D,
    Loop = 0x1E,

    Call = 0x1F,
    Ret = 0x20,

    VAdd = 0x21,
    VMul = 0x22,
    VFma = 0x23,
    VDot = 0x24,

    VCAdd = 0x25,
    VCMul = 0x26,
    VCDot = 0x27,

    Gemm = 0x28,

    CallLib = 0x3F,
}

impl Op {
    pub fn from_u8(opcode: u8) -> Option<Self> {
        match opcode {
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
