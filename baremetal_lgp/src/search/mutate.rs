use crate::contracts::abi::{META_IN_BASE, META_OUT_BASE};
use crate::search::archive::Archive;
use crate::search::ir::{
    Block, CandidateCfg, Instruction, OpClass, Opcode, Terminator, CAND_MAX_BLOCKS,
};
use crate::search::rng::Rng;

pub const MUT_W_OP_TWEAK: f32 = 0.18;
pub const MUT_W_REG_REMAP: f32 = 0.12;
pub const MUT_W_IMM_DELTA: f32 = 0.12;
pub const MUT_W_CONST_PERT: f32 = 0.10;
pub const MUT_W_BLOCK_SPLICE: f32 = 0.10;
pub const MUT_W_BLOCK_DELETE: f32 = 0.06;
pub const MUT_W_EDGE_RETARGET: f32 = 0.10;
pub const MUT_W_INSERT_CALL_LIB: f32 = 0.12;
pub const MUT_W_TERM_TRANSFORM: f32 = 0.10;
pub const MUTATION_OPERATOR_COUNT: usize = 9;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MutationOp {
    OpTweak = 0,
    RegRemap = 1,
    ImmDelta = 2,
    ConstPerturb = 3,
    BlockSplice = 4,
    BlockDelete = 5,
    EdgeRetarget = 6,
    InsertCallLib = 7,
    TermTransform = 8,
}

pub const DEFAULT_MUTATION_WEIGHTS: [f32; MUTATION_OPERATOR_COUNT] = [
    MUT_W_OP_TWEAK,
    MUT_W_REG_REMAP,
    MUT_W_IMM_DELTA,
    MUT_W_CONST_PERT,
    MUT_W_BLOCK_SPLICE,
    MUT_W_BLOCK_DELETE,
    MUT_W_EDGE_RETARGET,
    MUT_W_INSERT_CALL_LIB,
    MUT_W_TERM_TRANSFORM,
];

pub fn mutate_candidate(
    parent: &CandidateCfg,
    archive: &Archive,
    rng: &mut Rng,
    weights: &[f32; MUTATION_OPERATOR_COUNT],
) -> CandidateCfg {
    for _attempt in 0..8 {
        let mut child = parent.clone();
        let mutation_count = rng.gen_range_usize(1..5);
        for _ in 0..mutation_count {
            let op = select_operator(rng, weights);
            apply_operator(op, &mut child, archive, rng);
        }
        if child.verify().is_ok() {
            return child;
        }
    }
    parent.clone()
}

fn select_operator(rng: &mut Rng, weights: &[f32; MUTATION_OPERATOR_COUNT]) -> MutationOp {
    match rng.sample_weighted_index(weights).unwrap_or(0) {
        0 => MutationOp::OpTweak,
        1 => MutationOp::RegRemap,
        2 => MutationOp::ImmDelta,
        3 => MutationOp::ConstPerturb,
        4 => MutationOp::BlockSplice,
        5 => MutationOp::BlockDelete,
        6 => MutationOp::EdgeRetarget,
        7 => MutationOp::InsertCallLib,
        8 => MutationOp::TermTransform,
        _ => MutationOp::OpTweak,
    }
}

fn apply_operator(op: MutationOp, child: &mut CandidateCfg, archive: &Archive, rng: &mut Rng) {
    match op {
        MutationOp::OpTweak => mut_opcode_tweak(child, rng),
        MutationOp::RegRemap => mut_reg_remap(child, rng),
        MutationOp::ImmDelta => mut_imm_delta(child, rng),
        MutationOp::ConstPerturb => mut_const_perturb(child, rng),
        MutationOp::BlockSplice => mut_block_splice(child, archive, rng),
        MutationOp::BlockDelete => mut_block_delete(child, rng),
        MutationOp::EdgeRetarget => mut_edge_retarget(child, rng),
        MutationOp::InsertCallLib => mut_insert_call_lib(child, rng),
        MutationOp::TermTransform => mut_term_transform(child, rng),
    }
}

fn mut_opcode_tweak(child: &mut CandidateCfg, rng: &mut Rng) {
    let Some((block_idx, insn_idx)) = random_insn_index(child, rng) else {
        return;
    };
    let insn = &mut child.blocks[block_idx].insns[insn_idx];
    let ops = match insn.opcode.class() {
        OpClass::FloatScalar => &FLOAT_SCALAR_OPS[..],
        OpClass::IntScalar => &INT_SCALAR_OPS[..],
        OpClass::Mem => &MEM_OPS[..],
        OpClass::NonLinear => &NON_LINEAR_OPS[..],
        OpClass::VectorReal => &VECTOR_REAL_OPS[..],
        OpClass::VectorComplex => &VECTOR_COMPLEX_OPS[..],
        OpClass::Control | OpClass::Other => return,
    };
    if ops.len() <= 1 {
        return;
    }
    let mut chosen = ops[rng.gen_range_usize(0..ops.len())];
    if chosen == insn.opcode {
        chosen = ops[(rng.gen_range_usize(0..ops.len() - 1) + 1) % ops.len()];
    }
    insn.opcode = chosen;
}

fn mut_reg_remap(child: &mut CandidateCfg, rng: &mut Rng) {
    let Some(block_idx) = rng.choose_index(child.blocks.len()) else {
        return;
    };
    let block = &mut child.blocks[block_idx];
    let mut map = [0_u8; 16];
    for (i, slot) in map.iter_mut().enumerate() {
        *slot = i as u8;
    }

    let swaps = rng.gen_range_usize(2..5);
    for _ in 0..swaps {
        let a = rng.gen_range_usize(0..16);
        let mut b = rng.gen_range_usize(0..16);
        if b == a {
            b = (b + 1) % 16;
        }
        map.swap(a, b);
    }

    for insn in &mut block.insns {
        insn.rd = map[usize::from(insn.rd & 0x0F)];
        insn.ra = map[usize::from(insn.ra & 0x0F)];
        insn.rb = map[usize::from(insn.rb & 0x0F)];
    }
    if let Some(reg) = block.term.control_reg_mut() {
        *reg = map[usize::from(*reg & 0x0F)];
    }
}

fn mut_imm_delta(child: &mut CandidateCfg, rng: &mut Rng) {
    let total_insns: usize = child.blocks.iter().map(|b| b.insns.len()).sum();
    let term_imm_count = child
        .blocks
        .iter()
        .filter(|b| {
            matches!(
                b.term,
                Terminator::Jump { .. }
                    | Terminator::CondZero { .. }
                    | Terminator::CondNonZero { .. }
                    | Terminator::Loop { .. }
            )
        })
        .count();
    let total_choices = total_insns + term_imm_count;
    if total_choices == 0 {
        return;
    }
    let choice = rng.gen_range_usize(0..total_choices);
    let delta = sample_imm_delta(rng);

    if choice < total_insns {
        let mut cursor = choice;
        for block in &mut child.blocks {
            if cursor < block.insns.len() {
                apply_delta_imm14(&mut block.insns[cursor].imm14, delta);
                return;
            }
            cursor -= block.insns.len();
        }
        return;
    }

    let mut remaining = choice - total_insns;
    for block in &mut child.blocks {
        if let Some(imm14) = block.term.imm14_mut() {
            if remaining == 0 {
                apply_delta_imm14(imm14, delta);
                return;
            }
            remaining -= 1;
        }
    }
}

fn mut_const_perturb(child: &mut CandidateCfg, rng: &mut Rng) {
    let idx = rng.gen_range_usize(0..child.const_pool.len());
    let sigma = if rng.gen_bool(0.80) { 0.01 } else { 0.1 };
    let value = child.const_pool[idx] + rng.sample_normal(sigma);
    child.const_pool[idx] = value.clamp(-4.0, 4.0);
}

fn mut_block_splice(child: &mut CandidateCfg, archive: &Archive, rng: &mut Rng) {
    if child.blocks.len() >= CAND_MAX_BLOCKS {
        return;
    }
    let Some(donor_bin) = archive.random_filled_bin(rng) else {
        return;
    };
    let Some(donor) = archive.get(donor_bin) else {
        return;
    };
    let Some(block_idx) = rng.choose_index(donor.candidate.blocks.len()) else {
        return;
    };
    let donor_block = donor.candidate.blocks[block_idx].clone();
    let new_block_id = child.blocks.len() as u16;
    child.blocks.push(donor_block);
    patch_any_edge_to_target(child, new_block_id, rng);
}

fn mut_block_delete(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.len() <= 1 {
        return;
    }
    let entry = usize::from(child.entry);
    let mut remove = rng.gen_range_usize(0..child.blocks.len());
    if remove == entry {
        remove = (remove + 1) % child.blocks.len();
        if remove == entry {
            return;
        }
    }

    child.blocks.remove(remove);
    if usize::from(child.entry) > remove {
        child.entry = child.entry.saturating_sub(1);
    }
    repair_targets_after_delete(child, remove as u16);
}

fn mut_edge_retarget(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.is_empty() {
        return;
    }
    let mut with_targets = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        if block.term.target_count() > 0 {
            with_targets.push(idx);
        }
    }
    let Some(choice) = rng.choose_index(with_targets.len()) else {
        return;
    };
    let block_idx = with_targets[choice];
    let target = rng.gen_range_usize(0..child.blocks.len()) as u16;
    retarget_one(&mut child.blocks[block_idx].term, target, rng);
}

fn mut_insert_call_lib(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.len() >= CAND_MAX_BLOCKS {
        return;
    }
    let Some(back_target_idx) = rng.choose_index(child.blocks.len()) else {
        return;
    };
    let back_target = back_target_idx as u16;
    let slot = rng.gen_range_u32(0..256) as u16;

    let call_block = Block {
        insns: vec![
            Instruction {
                opcode: Opcode::LdMU32,
                rd: 0,
                ra: 0,
                rb: 0,
                imm14: META_IN_BASE as u16,
            },
            Instruction {
                opcode: Opcode::LdMU32,
                rd: 1,
                ra: 0,
                rb: 0,
                imm14: META_OUT_BASE as u16,
            },
            Instruction {
                opcode: Opcode::CallLib,
                rd: 0,
                ra: 0,
                rb: 0,
                imm14: slot,
            },
        ],
        term: Terminator::Jump {
            target: back_target,
            imm14: 0,
        },
    };
    let new_block_id = child.blocks.len() as u16;
    child.blocks.push(call_block);
    patch_any_edge_to_target(child, new_block_id, rng);
}

fn mut_term_transform(child: &mut CandidateCfg, rng: &mut Rng) {
    let mut candidates = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        match block.term {
            Terminator::CondZero { .. }
            | Terminator::CondNonZero { .. }
            | Terminator::Loop { .. } => {
                candidates.push(idx);
            }
            Terminator::Halt | Terminator::Jump { .. } | Terminator::Return => {}
        }
    }
    let Some(choice) = rng.choose_index(candidates.len()) else {
        return;
    };
    let block_idx = candidates[choice];
    match &mut child.blocks[block_idx].term {
        Terminator::CondZero { .. } | Terminator::CondNonZero { .. } => {
            child.blocks[block_idx].term.swap_conditional_targets();
        }
        Terminator::Loop {
            body_target,
            exit_target,
            ..
        } => {
            if rng.gen_bool(0.3) {
                core::mem::swap(body_target, exit_target);
            }
        }
        Terminator::Halt | Terminator::Jump { .. } | Terminator::Return => {}
    }
}

fn random_insn_index(candidate: &CandidateCfg, rng: &mut Rng) -> Option<(usize, usize)> {
    let mut populated = Vec::new();
    for (block_idx, block) in candidate.blocks.iter().enumerate() {
        if !block.insns.is_empty() {
            populated.push(block_idx);
        }
    }
    let block_choice = rng.choose_index(populated.len())?;
    let block_idx = populated[block_choice];
    let insn_idx = rng.gen_range_usize(0..candidate.blocks[block_idx].insns.len());
    Some((block_idx, insn_idx))
}

fn sample_imm_delta(rng: &mut Rng) -> i32 {
    let p = rng.next_f32();
    if p < 0.70 {
        rng.gen_range_i32_inclusive(-8, 8)
    } else if p < 0.95 {
        rng.gen_range_i32_inclusive(-64, 64)
    } else {
        rng.gen_range_i32_inclusive(-1024, 1024)
    }
}

fn apply_delta_imm14(imm14: &mut u16, delta: i32) {
    let value = (i32::from(*imm14) + delta) & 0x3FFF;
    *imm14 = value as u16;
}

fn patch_any_edge_to_target(child: &mut CandidateCfg, new_target: u16, rng: &mut Rng) {
    let mut sources = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        if block.term.target_count() > 0 {
            sources.push(idx);
        }
    }
    if let Some(choice) = rng.choose_index(sources.len()) {
        let idx = sources[choice];
        if retarget_one(&mut child.blocks[idx].term, new_target, rng) {
            return;
        }
    }
    if let Some(entry) = child.blocks.get_mut(usize::from(child.entry)) {
        entry.term = Terminator::Jump {
            target: new_target,
            imm14: 0,
        };
    }
}

fn retarget_one(term: &mut Terminator, target: u16, rng: &mut Rng) -> bool {
    match term {
        Terminator::Jump { target: edge, .. } => {
            *edge = target;
            true
        }
        Terminator::CondZero {
            true_target,
            false_target,
            ..
        }
        | Terminator::CondNonZero {
            true_target,
            false_target,
            ..
        } => {
            if rng.gen_bool(0.5) {
                *true_target = target;
            } else {
                *false_target = target;
            }
            true
        }
        Terminator::Loop {
            body_target,
            exit_target,
            ..
        } => {
            if rng.gen_bool(0.5) {
                *body_target = target;
            } else {
                *exit_target = target;
            }
            true
        }
        Terminator::Halt | Terminator::Return => false,
    }
}

fn repair_targets_after_delete(child: &mut CandidateCfg, removed_block: u16) {
    for block in &mut child.blocks {
        block.term.for_each_target_mut(|target| {
            if *target == removed_block {
                *target = 0;
            } else if *target > removed_block {
                *target = target.saturating_sub(1);
            }
        });
    }
}

const FLOAT_SCALAR_OPS: [Opcode; 9] = [
    Opcode::FMov,
    Opcode::FAdd,
    Opcode::FSub,
    Opcode::FMul,
    Opcode::FFma,
    Opcode::FAbs,
    Opcode::FNeg,
    Opcode::IToF,
    Opcode::FToI,
];

const INT_SCALAR_OPS: [Opcode; 9] = [
    Opcode::IMov,
    Opcode::IAdd,
    Opcode::ISub,
    Opcode::IAnd,
    Opcode::IOr,
    Opcode::IXor,
    Opcode::IShl,
    Opcode::IShr,
    Opcode::IConst,
];

const MEM_OPS: [Opcode; 5] = [
    Opcode::LdF,
    Opcode::StF,
    Opcode::FConst,
    Opcode::LdMU32,
    Opcode::LdMF32,
];

const NON_LINEAR_OPS: [Opcode; 2] = [Opcode::FTanh, Opcode::FSigm];
const VECTOR_REAL_OPS: [Opcode; 5] = [
    Opcode::VAdd,
    Opcode::VMul,
    Opcode::VFma,
    Opcode::VDot,
    Opcode::Gemm,
];
const VECTOR_COMPLEX_OPS: [Opcode; 3] = [Opcode::VCAdd, Opcode::VCMul, Opcode::VCDot];
