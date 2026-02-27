use crate::abi::{META_P0, META_P1, META_P2};
use crate::isa::op::Op;

#[inline]
fn ceil_div8(x: u32) -> u32 {
    x.div_ceil(8)
}

#[inline]
pub fn extra_cost(op: Op, imm14_u: u16, meta_u32: &[u32; 16]) -> u32 {
    match op {
        Op::Call | Op::Ret | Op::CallLib => 1,
        Op::FTanh | Op::FSigm => 2,
        Op::VAdd | Op::VMul | Op::VFma | Op::VDot => 2 + ceil_div8(u32::from(imm14_u)),
        Op::VCAdd | Op::VCMul | Op::VCDot => {
            let words = u32::from(imm14_u).saturating_mul(2);
            2 + ceil_div8(words)
        }
        Op::Gemm => {
            let m = meta_u32[META_P0];
            let n = meta_u32[META_P1];
            let k = meta_u32[META_P2];
            8 + m.saturating_mul(n).saturating_mul(k) / 16
        }
        _ => 0,
    }
}
