use crate::abi::{BLOCK_MAX_INSNS, CAND_MAX_BLOCKS, CAND_MAX_INSNS};
use crate::cfg::ir::CandidateCfg;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum VerifyError {
    TooManyBlocks {
        got: usize,
        max: usize,
    },
    BlockTooLarge {
        block_index: usize,
        got: usize,
        max: usize,
    },
    TooManyInstructions {
        got: usize,
        max: usize,
    },
}

pub fn verify(cfg: &CandidateCfg) -> Result<(), VerifyError> {
    if cfg.blocks.len() > CAND_MAX_BLOCKS {
        return Err(VerifyError::TooManyBlocks {
            got: cfg.blocks.len(),
            max: CAND_MAX_BLOCKS,
        });
    }

    let mut total = 0usize;
    for (idx, block) in cfg.blocks.iter().enumerate() {
        let n = block.insns.len();
        if n > BLOCK_MAX_INSNS {
            return Err(VerifyError::BlockTooLarge {
                block_index: idx,
                got: n,
                max: BLOCK_MAX_INSNS,
            });
        }
        total += n;
    }

    if total > CAND_MAX_INSNS {
        return Err(VerifyError::TooManyInstructions {
            got: total,
            max: CAND_MAX_INSNS,
        });
    }

    Ok(())
}
