use crate::abi::CAND_MAX_INSNS;
use crate::bytecode::program::BytecodeProgram;
use crate::cfg::ir::{BlockId, CandidateCfg, Terminator};
use crate::cfg::verify::{self, VerifyErr};
use crate::isa::encoding::encode;
use crate::isa::op::Op;

#[derive(Default)]
pub struct LinkerArena {
    pub words: Vec<u32>,
    #[cfg(feature = "trace")]
    pub pc_to_block: Vec<u16>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LinkErr {
    Verify(VerifyErr),
    TooManyInstructions {
        total: usize,
    },
    PcRelOutOfRange {
        from_pc: i32,
        to_pc: i32,
        delta: i32,
    },
}

pub fn link(cfg: &CandidateCfg, arena: &mut LinkerArena) -> Result<BytecodeProgram, LinkErr> {
    verify::verify(cfg).map_err(LinkErr::Verify)?;

    let layout = dfs_layout(cfg);
    let mut block_pc = vec![0usize; cfg.blocks.len()];

    let mut cursor = 0usize;
    for &block in &layout {
        block_pc[usize::from(block)] = cursor;
        let b = &cfg.blocks[usize::from(block)];
        cursor = cursor.saturating_add(b.instrs.len());
        cursor = cursor.saturating_add(term_words(&b.term));
    }

    if cursor > CAND_MAX_INSNS {
        return Err(LinkErr::TooManyInstructions { total: cursor });
    }

    arena.words.clear();
    arena.words.reserve(cursor);
    #[cfg(feature = "trace")]
    {
        arena.pc_to_block.clear();
        arena.pc_to_block.reserve(cursor);
    }

    let mut pc = 0usize;
    for &block in &layout {
        let b = &cfg.blocks[usize::from(block)];

        for ins in &b.instrs {
            arena
                .words
                .push(encode(ins.op, ins.rd, ins.ra, ins.rb, ins.imm14));
            #[cfg(feature = "trace")]
            arena.pc_to_block.push(block);
            pc = pc.saturating_add(1);
        }

        emit_terminator(b, &block_pc, &mut pc, arena)?;
    }

    Ok(BytecodeProgram {
        words: arena.words.clone(),
        const_pool: cfg.const_pool,
        #[cfg(feature = "trace")]
        pc_to_block: arena.pc_to_block.clone(),
    })
}

fn dfs_layout(cfg: &CandidateCfg) -> Vec<BlockId> {
    let mut layout = Vec::with_capacity(cfg.blocks.len());
    let mut visited = vec![false; cfg.blocks.len()];

    fn visit(cfg: &CandidateCfg, b: BlockId, visited: &mut [bool], layout: &mut Vec<BlockId>) {
        let bi = usize::from(b);
        if visited[bi] {
            return;
        }
        visited[bi] = true;
        layout.push(b);

        match cfg.blocks[bi].term {
            Terminator::Halt | Terminator::Ret => {}
            Terminator::Jmp { target } => visit(cfg, target, visited, layout),
            Terminator::Jz { t, f, .. } | Terminator::Jnz { t, f, .. } => {
                visit(cfg, t, visited, layout);
                visit(cfg, f, visited, layout);
            }
            Terminator::Loop { body, exit, .. } => {
                visit(cfg, body, visited, layout);
                visit(cfg, exit, visited, layout);
            }
            Terminator::Call { target, ret } => {
                visit(cfg, target, visited, layout);
                visit(cfg, ret, visited, layout);
            }
            Terminator::CallLib { ret, .. } => visit(cfg, ret, visited, layout),
        }
    }

    visit(cfg, cfg.entry, &mut visited, &mut layout);

    for idx in 0..cfg.blocks.len() {
        if !visited[idx] {
            visit(cfg, idx as BlockId, &mut visited, &mut layout);
        }
    }

    layout
}

fn term_words(term: &Terminator) -> usize {
    match term {
        Terminator::Jz { .. }
        | Terminator::Jnz { .. }
        | Terminator::Loop { .. }
        | Terminator::Call { .. }
        | Terminator::CallLib { .. } => 2,
        Terminator::Halt | Terminator::Jmp { .. } | Terminator::Ret => 1,
    }
}

fn pc_rel(from_pc: usize, target_pc: usize) -> Result<u16, LinkErr> {
    let from = i32::try_from(from_pc).unwrap_or(i32::MAX);
    let to = i32::try_from(target_pc).unwrap_or(i32::MAX);
    let delta = to.saturating_sub(from);
    if !(-8192..=8191).contains(&delta) {
        return Err(LinkErr::PcRelOutOfRange {
            from_pc: from,
            to_pc: to,
            delta,
        });
    }
    Ok(((delta as i16) as u16) & 0x3FFF)
}

fn emit_terminator(
    block: &crate::cfg::ir::Block,
    block_pc: &[usize],
    pc: &mut usize,
    arena: &mut LinkerArena,
) -> Result<(), LinkErr> {
    let emit = |arena: &mut LinkerArena, pc: &mut usize, bid: BlockId, word: u32| {
        #[cfg(not(feature = "trace"))]
        let _ = bid;
        arena.words.push(word);
        #[cfg(feature = "trace")]
        arena.pc_to_block.push(bid);
        *pc = pc.saturating_add(1);
    };

    let bid = block.id;
    match block.term {
        Terminator::Halt => {
            emit(arena, pc, bid, encode(Op::Halt, 0, 0, 0, 0));
        }
        Terminator::Ret => {
            emit(arena, pc, bid, encode(Op::Ret, 0, 0, 0, 0));
        }
        Terminator::Jmp { target } => {
            let imm = pc_rel(*pc, block_pc[usize::from(target)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, imm));
        }
        Terminator::Jz { cond, t, f } => {
            let jz_imm = pc_rel(*pc, block_pc[usize::from(t)])?;
            emit(arena, pc, bid, encode(Op::Jz, 0, cond, 0, jz_imm));

            let jmp_imm = pc_rel(*pc, block_pc[usize::from(f)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, jmp_imm));
        }
        Terminator::Jnz { cond, t, f } => {
            let jnz_imm = pc_rel(*pc, block_pc[usize::from(t)])?;
            emit(arena, pc, bid, encode(Op::Jnz, 0, cond, 0, jnz_imm));

            let jmp_imm = pc_rel(*pc, block_pc[usize::from(f)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, jmp_imm));
        }
        Terminator::Loop {
            counter,
            body,
            exit,
        } => {
            let loop_imm = pc_rel(*pc, block_pc[usize::from(body)])?;
            emit(arena, pc, bid, encode(Op::Loop, 0, counter, 0, loop_imm));

            let jmp_imm = pc_rel(*pc, block_pc[usize::from(exit)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, jmp_imm));
        }
        Terminator::Call { target, ret } => {
            let call_imm = pc_rel(*pc, block_pc[usize::from(target)])?;
            emit(arena, pc, bid, encode(Op::Call, 0, 0, 0, call_imm));

            let jmp_imm = pc_rel(*pc, block_pc[usize::from(ret)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, jmp_imm));
        }
        Terminator::CallLib { slot, ret } => {
            emit(
                arena,
                pc,
                bid,
                encode(Op::CallLib, 0, 0, 0, u16::from(slot)),
            );

            let jmp_imm = pc_rel(*pc, block_pc[usize::from(ret)])?;
            emit(arena, pc, bid, encode(Op::Jmp, 0, 0, 0, jmp_imm));
        }
    }

    Ok(())
}
