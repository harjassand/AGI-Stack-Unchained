use crate::bytecode::program::Program;
use crate::cfg::ir::CandidateCfg;
use crate::cfg::verify;

pub fn link(cfg: &CandidateCfg) -> Result<Program, verify::VerifyError> {
    verify::verify(cfg)?;
    let mut words = Vec::new();
    for block in &cfg.blocks {
        words.extend_from_slice(&block.insns);
    }
    Ok(Program {
        words,
        const_pool: [0.0; crate::abi::CONST_POOL_WORDS],
    })
}
