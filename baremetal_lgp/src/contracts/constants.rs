pub const SCRATCH_WORDS_F32: usize = 16_384; // 64KB / 4
pub const SCRATCH_WRAP_MASK: u32 = 0x3FFF;

pub const F_REGS: usize = 16;
pub const I_REGS: usize = 16;

pub const META_U32: usize = 16;
pub const META_F32: usize = 16;

pub const CALLSTACK_DEPTH: usize = 1024;

pub const LIB_SLOTS: usize = 256;
pub const LIB_MAX_INSTRS: usize = 1024;

pub const CONST_POOL_LEN: usize = 128;

// Candidate hard caps (for arena + no-per-candidate-alloc discipline)
pub const MAX_BLOCKS: usize = 128;
pub const MAX_BLOCK_INSTRS: usize = 128;
pub const MAX_TOTAL_INSTRS: usize = 2048;

// Vector backend policy thresholds (exact)
pub const NEON_THRESHOLD_F32: usize = 128; // real len in f32
pub const NEON_THRESHOLD_COMPLEX: usize = 64; // complex len in complex numbers

// Oracle families (exact v0)
pub const ORACLE_FAMILIES: usize = 4;
