use crate::abi::{BLOCK_MAX_INSNS, CAND_MAX_BLOCKS, CAND_MAX_INSNS};
use crate::cfg::ir::{BlockId, CandidateCfg, Terminator};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum VerifyErr {
    EmptyCfg,
    EntryMustBeZero { got: BlockId },
    TooManyBlocks { blocks: usize },
    BlockIdMismatch { index: usize, got: BlockId },
    BlockTooLarge { block: BlockId, insns: usize },
    TooManyInstructions { total: usize },
    InvalidBlockTarget { block: BlockId, target: BlockId },
    InvalidCondReg { block: BlockId, reg: u8 },
    InvalidCounterReg { block: BlockId, reg: u8 },
    InvalidLibSlot { block: BlockId, slot: u8 },
}

pub fn verify(cfg: &CandidateCfg) -> Result<(), VerifyErr> {
    if cfg.blocks.is_empty() {
        return Err(VerifyErr::EmptyCfg);
    }
    if cfg.entry != 0 {
        return Err(VerifyErr::EntryMustBeZero { got: cfg.entry });
    }
    if cfg.blocks.len() > CAND_MAX_BLOCKS {
        return Err(VerifyErr::TooManyBlocks {
            blocks: cfg.blocks.len(),
        });
    }

    let mut total_words = 0usize;
    let block_count_u16 = u16::try_from(cfg.blocks.len()).unwrap_or(u16::MAX);

    for (idx, block) in cfg.blocks.iter().enumerate() {
        if block.id as usize != idx {
            return Err(VerifyErr::BlockIdMismatch {
                index: idx,
                got: block.id,
            });
        }

        if block.instrs.len() > BLOCK_MAX_INSNS {
            return Err(VerifyErr::BlockTooLarge {
                block: block.id,
                insns: block.instrs.len(),
            });
        }

        total_words = total_words.saturating_add(block.instrs.len());
        total_words = total_words.saturating_add(terminator_words(&block.term));

        check_targets(block.id, block_count_u16, &block.term)?;
    }

    if total_words > CAND_MAX_INSNS {
        return Err(VerifyErr::TooManyInstructions { total: total_words });
    }

    Ok(())
}

fn terminator_words(term: &Terminator) -> usize {
    match term {
        Terminator::Jz { .. }
        | Terminator::Jnz { .. }
        | Terminator::Loop { .. }
        | Terminator::Call { .. }
        | Terminator::CallLib { .. } => 2,
        Terminator::Halt | Terminator::Jmp { .. } | Terminator::Ret => 1,
    }
}

fn check_target(block: BlockId, block_count: u16, target: BlockId) -> Result<(), VerifyErr> {
    if target >= block_count {
        return Err(VerifyErr::InvalidBlockTarget { block, target });
    }
    Ok(())
}

fn check_targets(block: BlockId, block_count: u16, term: &Terminator) -> Result<(), VerifyErr> {
    match *term {
        Terminator::Halt | Terminator::Ret => {}
        Terminator::Jmp { target } => check_target(block, block_count, target)?,
        Terminator::Jz { cond, t, f } | Terminator::Jnz { cond, t, f } => {
            if cond >= crate::abi::I_REGS as u8 {
                return Err(VerifyErr::InvalidCondReg { block, reg: cond });
            }
            check_target(block, block_count, t)?;
            check_target(block, block_count, f)?;
        }
        Terminator::Loop {
            counter,
            body,
            exit,
        } => {
            if counter >= crate::abi::I_REGS as u8 {
                return Err(VerifyErr::InvalidCounterReg {
                    block,
                    reg: counter,
                });
            }
            check_target(block, block_count, body)?;
            check_target(block, block_count, exit)?;
        }
        Terminator::Call { target, ret } => {
            check_target(block, block_count, target)?;
            check_target(block, block_count, ret)?;
        }
        Terminator::CallLib { slot, ret } => {
            if usize::from(slot) >= crate::abi::LIB_SLOTS {
                return Err(VerifyErr::InvalidLibSlot { block, slot });
            }
            check_target(block, block_count, ret)?;
        }
    }

    Ok(())
}
