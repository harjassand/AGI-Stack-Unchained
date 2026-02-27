use crate::abi::{META_P0, META_P1, META_P2};
use crate::isa::op::Op;

pub fn extra_vec_real(len_words: u32) -> u32 {
    2 + len_words.div_ceil(8)
}

pub fn extra_vec_complex(len_complex: u32) -> u32 {
    2 + (len_complex.saturating_mul(2)).div_ceil(8)
}

pub fn extra_gemm(m: u32, n: u32, k: u32) -> u32 {
    8 + ((m.saturating_mul(n).saturating_mul(k)) / 16)
}

pub fn instruction_cost(op: Op, imm14_u: u32, meta_u32: &[u32; 16]) -> u32 {
    let extra = match op {
        Op::Call | Op::Ret | Op::CallLib => 1,
        Op::FTanh | Op::FSigm => 2,

        Op::VAdd | Op::VMul | Op::VFma | Op::VDot => extra_vec_real(imm14_u),
        Op::VCAdd | Op::VCMul | Op::VCDot => extra_vec_complex(imm14_u),

        Op::Gemm => {
            let m = meta_u32[META_P0];
            let n = meta_u32[META_P1];
            let k = meta_u32[META_P2];
            extra_gemm(m, n, k)
        }

        _ => 0,
    };

    1 + extra
}
