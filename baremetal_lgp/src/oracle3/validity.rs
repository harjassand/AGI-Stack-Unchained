use crate::bytecode::program::BytecodeProgram;
use crate::isa::encoding::encode;
use crate::isa::op::Op;
use crate::library::bank::LibraryBank;
use crate::oracle3::chunkpack::ChunkPack;
use crate::vm::{run_candidate, ExecConfig, VmProgram, VmWorker};

use super::compile::{compile_chunkpack, CompileError, VALIDITY_COMPILE_CFG};
use super::cost::{compute_cost, CostViolation};
use super::spec::RegimeSpec;

pub const DELTA_VALID: f32 = 0.05;
pub const DELTA_LEAK: f32 = 0.02;
pub const VALIDITY_COMPILE_SEED: u64 = 0xB3A7_1EED_0000_0001;
pub const VALIDITY_FUEL_MAX: u32 = 200_000;

pub type LinkedProgram = VmProgram;

pub struct VMChampSet {
    pub champs: Vec<LinkedProgram>,
}

pub enum ValidityVerdict {
    Valid {
        s_star: f32,
        s_trivial: f32,
        s_rand: f32,
    },
    InvalidCost(CostViolation),
    InvalidCompile(CompileError),
    InvalidBaseline {
        s_star: f32,
        s_rand: f32,
    },
    InvalidLeak {
        s_star: f32,
        s_trivial: f32,
    },
}

pub fn phase1_vm_champ_set() -> VMChampSet {
    let bank = LibraryBank::new_seeded();
    let mut champs = vec![champ_scale_input2()];
    for (slot, program) in bank.slots.iter().enumerate() {
        if program.is_some() {
            champs.push(champ_calllib(slot as u16));
        }
    }

    if champs.is_empty() {
        champs.push(make_program(vec![encode(Op::Halt, 0, 0, 0, 0)], &[]));
    }

    VMChampSet { champs }
}

pub fn evaluate_validity(spec: &RegimeSpec, champs: &VMChampSet) -> ValidityVerdict {
    if let Err(err) = compute_cost(spec) {
        return ValidityVerdict::InvalidCost(err);
    }

    let chunk = match compile_chunkpack(spec, VALIDITY_COMPILE_SEED, VALIDITY_COMPILE_CFG) {
        Ok(v) => v,
        Err(err) => return ValidityVerdict::InvalidCompile(err),
    };

    let lib = LibraryBank::new_seeded();

    let s_rand = score_program(&constant_zero_baseline(chunk.output_len), &chunk, &lib);

    let mut s_star = f32::NEG_INFINITY;
    for champ in &champs.champs {
        s_star = s_star.max(score_program(champ, &chunk, &lib));
    }

    if s_star < s_rand + DELTA_VALID {
        return ValidityVerdict::InvalidBaseline { s_star, s_rand };
    }

    let trivial = [
        zero_out_trivial(chunk.output_len),
        copy_input_trivial(chunk.input_len, chunk.output_len),
        copy_meta_f32_trivial(chunk.output_len, chunk.meta_f32_len),
    ];

    let mut s_trivial = f32::NEG_INFINITY;
    for prog in &trivial {
        s_trivial = s_trivial.max(score_program(prog, &chunk, &lib));
    }

    if s_star < s_trivial + DELTA_LEAK {
        return ValidityVerdict::InvalidLeak { s_star, s_trivial };
    }

    ValidityVerdict::Valid {
        s_star,
        s_trivial,
        s_rand,
    }
}

pub fn constant_zero_baseline(output_len: u32) -> LinkedProgram {
    zero_out_program(output_len)
}

fn zero_out_trivial(output_len: u32) -> LinkedProgram {
    zero_out_program(output_len)
}

fn zero_out_program(output_len: u32) -> LinkedProgram {
    if output_len == 0 {
        return make_program(vec![encode(Op::Halt, 0, 0, 0, 0)], &[]);
    }

    // i0 = out_base, i1 = out_len, i2 = 1, f0 = 0.0; loop store+advance.
    make_program(
        vec![
            encode(Op::LdMU32, 0, 0, 0, 1),
            encode(Op::LdMU32, 1, 0, 0, 4),
            encode(Op::IConst, 2, 0, 0, 1),
            encode(Op::FConst, 0, 0, 0, 0),
            encode(Op::StF, 0, 0, 0, 0),
            encode(Op::IAdd, 0, 0, 2, 0),
            encode(Op::Loop, 1, 1, 0, imm14_s(-2)),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        &[(0, 0.0)],
    )
}

fn copy_input_trivial(input_len: u32, output_len: u32) -> LinkedProgram {
    let copy_len = input_len.min(output_len);
    if copy_len == 0 {
        return make_program(vec![encode(Op::Halt, 0, 0, 0, 0)], &[]);
    }

    // i0 = in_base, i1 = out_base, i2 = 1, i3 = copy_len
    make_program(
        vec![
            encode(Op::LdMU32, 0, 0, 0, 0),
            encode(Op::LdMU32, 1, 0, 0, 1),
            encode(Op::IConst, 2, 0, 0, 1),
            encode(Op::IConst, 3, 0, 0, copy_len as u16),
            encode(Op::LdF, 0, 0, 0, 0),
            encode(Op::StF, 0, 1, 0, 0),
            encode(Op::IAdd, 0, 0, 2, 0),
            encode(Op::IAdd, 1, 1, 2, 0),
            encode(Op::Loop, 3, 3, 0, imm14_s(-4)),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn copy_meta_f32_trivial(output_len: u32, meta_f32_len: u32) -> LinkedProgram {
    let copy_len = output_len.min(meta_f32_len).min(16);
    if copy_len == 0 {
        return make_program(vec![encode(Op::Halt, 0, 0, 0, 0)], &[]);
    }

    let mut words = Vec::with_capacity(2 + copy_len as usize * 3 + 1);
    words.push(encode(Op::LdMU32, 0, 0, 0, 1));
    words.push(encode(Op::IConst, 1, 0, 0, 1));
    for idx in 0..copy_len {
        words.push(encode(Op::LdMF32, 0, 0, 0, idx as u16));
        words.push(encode(Op::StF, 0, 0, 0, 0));
        words.push(encode(Op::IAdd, 0, 0, 1, 0));
    }
    words.push(encode(Op::Halt, 0, 0, 0, 0));
    make_program(words, &[])
}

fn champ_calllib(slot: u16) -> LinkedProgram {
    make_program(
        vec![
            encode(Op::CallLib, 0, 0, 0, slot),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn champ_scale_input2() -> LinkedProgram {
    make_program(
        vec![
            encode(Op::LdMU32, 0, 0, 0, 0),
            encode(Op::LdMU32, 1, 0, 0, 1),
            encode(Op::LdF, 0, 0, 0, 0),
            encode(Op::FConst, 1, 0, 0, 0),
            encode(Op::FMul, 0, 0, 1, 0),
            encode(Op::StF, 0, 1, 0, 0),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        &[(0, 2.0)],
    )
}

fn make_program(words: Vec<u32>, const_entries: &[(usize, f32)]) -> LinkedProgram {
    let mut const_pool = [0.0_f32; crate::abi::CONST_POOL_WORDS];
    for &(idx, value) in const_entries {
        if idx < const_pool.len() {
            const_pool[idx] = value;
        }
    }
    BytecodeProgram {
        words,
        const_pool,
        #[cfg(feature = "trace")]
        pc_to_block: Vec::new(),
    }
}

fn score_program(program: &LinkedProgram, chunk: &ChunkPack, lib: &LibraryBank) -> f32 {
    if chunk.episode_count == 0 {
        return 0.0;
    }

    let exec_cfg = ExecConfig {
        fuel_max: VALIDITY_FUEL_MAX,
        trace: false,
        trace_budget_bytes: 0,
    };

    let mut sum = 0.0_f32;
    for ep in 0..chunk.episode_count {
        let mut worker = VmWorker::default();

        let meta_u32 = chunk.meta_u32(ep);
        let meta_f32 = chunk.meta_f32(ep);
        let input = chunk.input(ep);
        let target = chunk.target(ep);

        for (dst, src) in worker.meta_u32.iter_mut().zip(meta_u32.iter().copied()) {
            *dst = src;
        }
        for (dst, src) in worker.meta_f32.iter_mut().zip(meta_f32.iter().copied()) {
            *dst = src;
        }

        let in_base = meta_u32[0] as usize;
        let out_base = meta_u32[1] as usize;

        if in_base.saturating_add(input.len()) > worker.scratch.len() {
            return 0.0;
        }
        if out_base.saturating_add(target.len()) > worker.scratch.len() {
            return 0.0;
        }

        worker.scratch[in_base..in_base + input.len()].copy_from_slice(input);
        worker.scratch[out_base..out_base + target.len()].fill(0.0);

        let res = run_candidate(&mut worker, program, lib, &exec_cfg);
        if res.stop_reason != crate::vm::StopReason::Halt {
            return 0.0;
        }

        let output = &worker.scratch[out_base..out_base + target.len()];
        let mse = mse(output, target);
        sum += 1.0 / (1.0 + mse);
    }

    sum / chunk.episode_count as f32
}

fn mse(output: &[f32], target: &[f32]) -> f32 {
    if output.is_empty() || target.is_empty() {
        return 0.0;
    }
    let len = output.len().min(target.len());
    let mut acc = 0.0_f32;
    for i in 0..len {
        let d = output[i] - target[i];
        acc += d * d;
    }
    acc / len as f32
}

fn imm14_s(value: i32) -> u16 {
    (value as i16 as u16) & 0x3FFF
}
