// Base cost: every instruction costs 1 fuel.
// Extra costs:
pub const EXTRA_CALL_RET: u32 = 1;
pub const EXTRA_NONLINEAR: u32 = 2;

// Vector ops: extra = 2 + ceil(len/8)
pub fn extra_vec(len: u32) -> u32 {
    2 + ((len + 7) / 8)
}

// Complex vector ops use lenC (complex count), but charge by underlying f32 lanes
pub fn extra_vec_complex(len_c: u32) -> u32 {
    // treat as 2*len_c f32
    extra_vec(len_c.saturating_mul(2))
}

// GEMM tile ops: extra = 8 + (m*n*k)/16 (coarse)
pub fn extra_gemm(m: u32, n: u32, k: u32) -> u32 {
    8 + ((m.saturating_mul(n).saturating_mul(k) + 15) / 16)
}
