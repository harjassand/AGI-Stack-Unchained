use crate::abi::{CALLSTACK_DEPTH, META_P0, META_P1, META_P2, SCRATCH_MASK_I32};
use crate::accel;
use crate::bytecode::program::BytecodeProgram;
use crate::isa::decode;
use crate::isa::encoding::imm14_s;
use crate::isa::op::Op;
use crate::library::bank::LibraryBank;
use crate::vm::gas;
use crate::vm::{ExecConfig, ExecResult, StopReason, VmWorker};

#[cfg(feature = "trace")]
use crate::vm::trace::{RegSnapshot, TraceState, TRACE_MAX_SNAPSHOTS};

pub fn run_candidate(
    worker: &mut VmWorker,
    prog: &BytecodeProgram,
    lib: &LibraryBank,
    cfg: &ExecConfig,
) -> ExecResult {
    worker.pc = 0;
    worker.fuel = cfg.fuel_max;
    worker.call_sp = 0;
    worker.halted = false;
    worker.stop_reason = StopReason::Halt;

    #[cfg(feature = "trace")]
    {
        if cfg.trace {
            let block_count = prog
                .pc_to_block
                .iter()
                .copied()
                .max()
                .map(|m| usize::from(m) + 1)
                .unwrap_or(1);
            worker.trace = TraceState::new(block_count);
        } else {
            worker.trace = TraceState::default();
        }
    }
    #[cfg(not(feature = "trace"))]
    {
        let _ = (cfg.trace, cfg.trace_budget_bytes);
    }

    let mut current_kind: u16 = 0;
    let mut current_prog = prog;

    loop {
        let pc_usize = match usize::try_from(worker.pc) {
            Ok(v) => v,
            Err(_) => {
                stop(worker, StopReason::PcOutOfRange);
                break;
            }
        };

        if pc_usize >= current_prog.words.len() {
            stop(worker, StopReason::PcOutOfRange);
            break;
        }

        #[cfg(feature = "trace")]
        if cfg.trace {
            trace_block_enter(worker, current_prog, pc_usize);
        }

        let word = current_prog.words[pc_usize];
        let (op, rd, ra, rb, imm14_u) = match decode::decode_word(word) {
            Ok(v) => v,
            Err(decode::DecodeErr::InvalidOpcode(bad)) => {
                stop(worker, StopReason::InvalidOpcode(bad));
                break;
            }
        };

        let cost = 1u32.saturating_add(gas::extra_cost(op, imm14_u, &worker.meta_u32));
        if worker.fuel < cost {
            stop(worker, StopReason::FuelExhausted);
            break;
        }
        worker.fuel -= cost;

        match op {
            Op::Halt => {
                stop(worker, StopReason::Halt);
                break;
            }
            Op::Nop => {
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FMov => {
                worker.f[rd as usize] = worker.f[ra as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FAdd => {
                worker.f[rd as usize] = worker.f[ra as usize] + worker.f[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FSub => {
                worker.f[rd as usize] = worker.f[ra as usize] - worker.f[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FMul => {
                worker.f[rd as usize] = worker.f[ra as usize] * worker.f[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FFma => {
                worker.f[rd as usize] += worker.f[ra as usize] * worker.f[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FAbs => {
                worker.f[rd as usize] = worker.f[ra as usize].abs();
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FNeg => {
                worker.f[rd as usize] = -worker.f[ra as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IMov => {
                worker.i[rd as usize] = worker.i[ra as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IAdd => {
                worker.i[rd as usize] = worker.i[ra as usize].wrapping_add(worker.i[rb as usize]);
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::ISub => {
                worker.i[rd as usize] = worker.i[ra as usize].wrapping_sub(worker.i[rb as usize]);
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IAnd => {
                worker.i[rd as usize] = worker.i[ra as usize] & worker.i[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IOr => {
                worker.i[rd as usize] = worker.i[ra as usize] | worker.i[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IXor => {
                worker.i[rd as usize] = worker.i[ra as usize] ^ worker.i[rb as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IShl => {
                let sh = u32::from(imm14_u & 31);
                worker.i[rd as usize] = worker.i[ra as usize].wrapping_shl(sh);
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IShr => {
                let sh = u32::from(imm14_u & 31);
                worker.i[rd as usize] = worker.i[ra as usize] >> sh;
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::LdF => {
                let addr = scratch_addr(worker.i[ra as usize], imm14_s(imm14_u));
                worker.f[rd as usize] = worker.scratch[addr];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::StF => {
                let addr = scratch_addr(worker.i[ra as usize], imm14_s(imm14_u));
                worker.scratch[addr] = worker.f[rd as usize];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FConst => {
                let idx = usize::from(imm14_u & 127);
                worker.f[rd as usize] = current_prog.const_pool[idx];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IConst => {
                worker.i[rd as usize] = imm14_s(imm14_u);
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::LdMU32 => {
                let idx = usize::from(imm14_u & 15);
                worker.i[rd as usize] = worker.meta_u32[idx] as i32;
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::LdMF32 => {
                let idx = usize::from(imm14_u & 15);
                worker.f[rd as usize] = worker.meta_f32[idx];
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::IToF => {
                worker.f[rd as usize] = worker.i[ra as usize] as f32;
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FToI => {
                worker.i[rd as usize] = worker.f[ra as usize] as i32;
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FTanh => {
                worker.f[rd as usize] = worker.f[ra as usize].tanh();
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::FSigm => {
                let x = worker.f[ra as usize];
                worker.f[rd as usize] = 1.0 / (1.0 + (-x).exp());
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::Jmp => {
                worker.pc = pc_rel(worker.pc, imm14_s(imm14_u));
            }
            Op::Jz => {
                if worker.i[ra as usize] == 0 {
                    worker.pc = pc_rel(worker.pc, imm14_s(imm14_u));
                } else {
                    worker.pc = worker.pc.wrapping_add(1);
                }
            }
            Op::Jnz => {
                if worker.i[ra as usize] != 0 {
                    worker.pc = pc_rel(worker.pc, imm14_s(imm14_u));
                } else {
                    worker.pc = worker.pc.wrapping_add(1);
                }
            }
            Op::Loop => {
                let ctr = &mut worker.i[ra as usize];
                *ctr = ctr.wrapping_sub(1);
                if *ctr != 0 {
                    worker.pc = pc_rel(worker.pc, imm14_s(imm14_u));
                } else {
                    worker.pc = worker.pc.wrapping_add(1);
                }
            }
            Op::Call => {
                if worker.call_sp >= CALLSTACK_DEPTH {
                    stop(worker, StopReason::CallStackOverflow);
                    break;
                }
                worker.call_kind[worker.call_sp] = current_kind;
                worker.call_pc[worker.call_sp] = worker.pc.wrapping_add(1);
                worker.call_sp += 1;
                worker.pc = pc_rel(worker.pc, imm14_s(imm14_u));
            }
            Op::Ret => {
                if worker.call_sp == 0 {
                    stop(worker, StopReason::CallStackUnderflow);
                    break;
                }
                worker.call_sp -= 1;
                let ret_kind = worker.call_kind[worker.call_sp];
                let ret_pc = worker.call_pc[worker.call_sp];

                current_kind = ret_kind;
                if ret_kind == 0 {
                    current_prog = prog;
                } else {
                    let slot = usize::from(ret_kind - 1);
                    let Some(next_prog) = lib.get_slot(slot) else {
                        stop(worker, StopReason::InvalidLibSlot(slot as u16));
                        break;
                    };
                    current_prog = next_prog;
                }
                worker.pc = ret_pc;
            }
            Op::VAdd => {
                accel::vadd_ring(
                    &mut worker.scratch,
                    worker.i[rd as usize],
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VMul => {
                accel::vmul_ring(
                    &mut worker.scratch,
                    worker.i[rd as usize],
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VFma => {
                accel::vfma_ring(
                    &mut worker.scratch,
                    worker.i[rd as usize],
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VDot => {
                worker.f[rd as usize] = accel::vdot_ring(
                    &worker.scratch,
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VCAdd => {
                accel::vcadd_ring(
                    &mut worker.scratch,
                    worker.i[rd as usize],
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VCMul => {
                accel::vcmul_ring(
                    &mut worker.scratch,
                    worker.i[rd as usize],
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::VCDot => {
                let (re, im) = accel::vcdot_ring(
                    &worker.scratch,
                    worker.i[ra as usize],
                    worker.i[rb as usize],
                    usize::from(imm14_u),
                );
                let k = usize::from(rd & 7);
                worker.f[k * 2] = re;
                worker.f[k * 2 + 1] = im;
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::Gemm => {
                exec_gemm(worker, rd, ra, rb);
                worker.pc = worker.pc.wrapping_add(1);
            }
            Op::CallLib => {
                let slot = usize::from(imm14_u & 0x00FF);
                let Some(next_prog) = lib.get_slot(slot) else {
                    stop(worker, StopReason::InvalidLibSlot(slot as u16));
                    break;
                };

                if worker.call_sp >= CALLSTACK_DEPTH {
                    stop(worker, StopReason::CallStackOverflow);
                    break;
                }

                worker.call_kind[worker.call_sp] = current_kind;
                worker.call_pc[worker.call_sp] = worker.pc.wrapping_add(1);
                worker.call_sp += 1;

                current_kind = u16::try_from(slot + 1).unwrap_or(u16::MAX);
                current_prog = next_prog;
                worker.pc = 0;
            }
        }

        #[cfg(feature = "trace")]
        if cfg.trace {
            trace_post_step(worker, cfg.trace_budget_bytes);
        }
    }

    ExecResult {
        stop_reason: worker.stop_reason,
        fuel_used: cfg.fuel_max.saturating_sub(worker.fuel),
        pc_end: worker.pc,
    }
}

#[inline]
fn scratch_addr(base: i32, imm: i32) -> usize {
    (base.wrapping_add(imm) & SCRATCH_MASK_I32) as usize
}

#[inline]
fn pc_rel(pc: u32, rel: i32) -> u32 {
    ((pc as i32).wrapping_add(rel)) as u32
}

fn stop(worker: &mut VmWorker, reason: StopReason) {
    worker.halted = true;
    worker.stop_reason = reason;
}

fn exec_gemm(worker: &mut VmWorker, rd: u8, ra: u8, rb: u8) {
    let c_base = worker.i[rd as usize];
    let a_base = worker.i[ra as usize];
    let b_base = worker.i[rb as usize];

    let m = worker.meta_u32[META_P0] as usize;
    let n = worker.meta_u32[META_P1] as usize;
    let k = worker.meta_u32[META_P2] as usize;

    for mi in 0..m {
        for nj in 0..n {
            let mut sum = 0.0f32;
            for kk in 0..k {
                let a_idx = ring_index_word(a_base, mi.saturating_mul(k).saturating_add(kk));
                let b_idx = ring_index_word(b_base, kk.saturating_mul(n).saturating_add(nj));
                sum += worker.scratch[a_idx] * worker.scratch[b_idx];
            }
            let c_idx = ring_index_word(c_base, mi.saturating_mul(n).saturating_add(nj));
            worker.scratch[c_idx] = sum;
        }
    }
}

#[inline]
fn ring_index_word(base: i32, off: usize) -> usize {
    (base.wrapping_add(i32::try_from(off).unwrap_or(i32::MAX)) & SCRATCH_MASK_I32) as usize
}

#[cfg(feature = "trace")]
fn trace_block_enter(worker: &mut VmWorker, current_prog: &BytecodeProgram, pc: usize) {
    if pc < current_prog.pc_to_block.len() {
        let block = usize::from(current_prog.pc_to_block[pc]);
        if block < worker.trace.block_counts.len() {
            worker.trace.block_counts[block] = worker.trace.block_counts[block].saturating_add(1);
        }
    }
}

#[cfg(feature = "trace")]
fn trace_post_step(worker: &mut VmWorker, budget_bytes: usize) {
    worker.trace.steps = worker.trace.steps.saturating_add(1);
    let stride = worker.trace.snapshot_stride.max(1);
    if worker.trace.steps % stride != 0 {
        return;
    }
    if worker.trace.snapshots.len() >= TRACE_MAX_SNAPSHOTS {
        return;
    }

    let next_count = worker.trace.snapshots.len().saturating_add(1);
    let needed = next_count.saturating_mul(std::mem::size_of::<RegSnapshot>());
    if needed > budget_bytes {
        return;
    }

    worker.trace.snapshots.push(RegSnapshot {
        step: worker.trace.steps,
        f: worker.f,
        i: worker.i,
    });
}
