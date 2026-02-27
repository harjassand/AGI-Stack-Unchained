/// Instruction word format (u32, little-endian):
/// bits 0..7: opcode: u8
/// bits 8..11: rd: u8 (0..15)
/// bits 12..15: ra: u8 (0..15)
/// bits 16..19: rb: u8 (0..15)
/// bits 20..23: rc: u8 (0..15)
/// bits 24..31: imm8: u8
///
/// Immediate conventions:
/// imm16_s: signed 16-bit immediate = sign_extend16((rb << 12) | (rc << 8) | imm8)
/// rel16_s: same as imm16_s, interpreted as PC-relative in instruction words.
/// imm12_s is not used in v0 contracts (reserved), to prevent scalar scratch reach traps.
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Op {
    Nop = 0x00,
    Halt = 0x01,

    // Float scalar
    FAdd = 0x10, // f[rd]=f[ra]+f[rb]
    FSub = 0x11,
    FMul = 0x12,
    FFma = 0x13, // f[rd]=f[ra]*f[rb]+f[rc]
    FAbs = 0x14, // f[rd]=abs(f[ra])
    FNeg = 0x15, // f[rd]=-f[ra]
    Tanh = 0x16, // f[rd]=fast_tanh(f[ra])  extra +2
    Sigm = 0x17, // f[rd]=fast_sigm(f[ra])  extra +2
    Ldc = 0x18,  // f[rd]=const_pool[imm8 % CONST_POOL_LEN]

    // Int scalar
    IAdd = 0x20, // i[rd]=i[ra]+i[rb]
    ISub = 0x21,
    IAnd = 0x22,
    IOr = 0x23,
    IXor = 0x24,
    ShlI = 0x25, // i[rd]=i[ra] << (imm8 & 31)
    ShrI = 0x26, // logical
    SarI = 0x27, // arithmetic
    Li16 = 0x28, // i[rd]=sign_extend16(imm16_s)

    // Meta loads (read-only ABI)
    MetaU32 = 0x30, // i[rd]=meta_u32[imm8 & 15]
    MetaF32 = 0x31, // f[rd]=meta_f32[imm8 & 15]

    // Scratch scalar (wrap addressing) -- UPDATED: uses imm16_s
    LdF = 0x38, // f[rd] = scratch[(i[ra] + imm16_s) & MASK]
    StF = 0x39, // scratch[(i[ra] + imm16_s) & MASK] = f[rd]

    // Control flow (rel16)
    Jmp = 0x3A, // pc += rel16_s
    JzI = 0x3B, // if i[rd]==0 pc += rel16_s
    JnzI = 0x3C,
    Loop = 0x3D,    // i[rd] -= 1; if i[rd]!=0 pc += rel16_s
    Call = 0x3E,    // push (prog,pc); pc += rel16_s   extra +1
    Ret = 0x3F,     // pop -> (prog,pc)                extra +1
    CallLib = 0x37, // NEW: call library slot imm8 (extra +1)

    // Vector real (len in i[rc]) extra = 2 + ceil(len/8)
    VAdd = 0x40, // dst=i[rd], x=i[ra], y=i[rb], len=i[rc]
    VMul = 0x41,
    VFma = 0x42, // dst += x*y
    VDot = 0x43, // f[rd] = dot(x,y,len)

    // Vector complex (lenC in i[rc]) extra = based on 2*lenC
    VCAdd = 0x50, // dst=i[rd], x=i[ra], y=i[rb], lenC=i[rc]
    VCMul = 0x51,
    VCDot = 0x52, // outputs: f[rd]=re, f[(rd+1)&15]=im (Hermitian conj(x)·y)

    // GEMM (row-major contiguous, no wrap allowed) extra=extra_gemm(m,n,k)
    SGemm = 0x60, // dst=i[rd], a=i[ra], b=i[rb], m=i[rc], n=imm8, k=meta_u32[META_SHIFT]
    SGemmAcc = 0x61, // dst += A*B
}

/// GEMM operands (unambiguous):
/// dst_base = i[rd]
/// a_base = i[ra]
/// b_base = i[rb]
/// m = i[rc]
/// n = imm8
/// k = meta_u32[META_SHIFT] (always set)
///
/// Row-major contiguous:
/// A at a_base, shape m×k
/// B at b_base, shape k×n
/// C at dst_base, shape m×n
pub struct GemmLayoutDoc;
