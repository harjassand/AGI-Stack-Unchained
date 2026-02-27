pub const SCRATCH_WORDS: usize = 16_384;
pub const SCRATCH_MASK_U32: u32 = 0x3FFF;
pub const SCRATCH_MASK_I32: i32 = 0x3FFF;

pub const F_REGS: usize = 16;
pub const I_REGS: usize = 16;

pub const C_REGS: usize = 8;

pub const CALLSTACK_DEPTH: usize = 1024;

pub const CONST_POOL_WORDS: usize = 128;
pub const LIB_SLOTS: usize = 256;
pub const LIB_MAX_INSNS: usize = 1024;

pub const CAND_MAX_BLOCKS: usize = 256;
pub const CAND_MAX_INSNS: usize = 4096;
pub const BLOCK_MAX_INSNS: usize = 1024;

pub const META_IN_BASE: usize = 0;
pub const META_IN_LEN: usize = 1;
pub const META_OUT_BASE: usize = 2;
pub const META_OUT_LEN: usize = 3;
pub const META_WORK_BASE: usize = 4;
pub const META_WORK_LEN: usize = 5;

pub const META_P0: usize = 6;
pub const META_P1: usize = 7;
pub const META_P2: usize = 8;
pub const META_P3: usize = 9;
pub const META_P4: usize = 10;
pub const META_P5: usize = 11;
pub const META_P6: usize = 12;
pub const META_P7: usize = 13;
pub const META_P8: usize = 14;
pub const META_P9: usize = 15;
