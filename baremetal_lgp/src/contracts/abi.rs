// meta_u32 index assignments (fixed)
pub const META_IN_BASE: usize = 0;
pub const META_IN_LEN: usize = 1;
pub const META_OUT_BASE: usize = 2;
pub const META_OUT_LEN: usize = 3;
pub const META_WORK_BASE: usize = 4;
pub const META_WORK_LEN: usize = 5;

// regime-shared meta (always set, family does not change presence)
pub const META_DIM_D: usize = 6;
pub const META_STEPS_T: usize = 7;
pub const META_FLAGS: usize = 8;
pub const META_SHIFT: usize = 9; // always set; only used by some families (also GEMM-k operand)

// fixed scratch layout (oracle sets these every episode)
pub const FIXED_IN_BASE: u32 = 0;
pub const FIXED_OUT_BASE: u32 = 8_192;
pub const FIXED_WORK_BASE: u32 = 12_288;

pub const FIXED_OUT_LIMIT: u32 = 12_288;
pub const FIXED_WORK_LEN: u32 = 16_384 - 12_288; // 4096

// META_FLAGS bitfield (fixed)
pub const FLAG_COMPLEX: u32 = 1 << 0; // interleaved complex in/out
pub const FLAG_HAS_AUX: u32 = 1 << 1; // auxiliary tensor exists in input region
pub const FLAG_RESERVED2: u32 = 1 << 2;
