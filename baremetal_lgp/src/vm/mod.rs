pub mod exec;
pub mod gas;
#[cfg(feature = "trace")]
pub mod trace;

use crate::abi::{CALLSTACK_DEPTH, F_REGS, I_REGS, SCRATCH_WORDS};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    Halt,
    FuelExhausted,
    PcOutOfRange,
    CallStackOverflow,
    CallStackUnderflow,
    InvalidOpcode(u8),
    InvalidLibSlot(u16),
    NaNTrap,
}

#[derive(Clone, Debug)]
pub struct VmWorker {
    pub f: [f32; F_REGS],
    pub i: [i32; I_REGS],

    pub scratch: [f32; SCRATCH_WORDS],

    pub meta_u32: [u32; 16],
    pub meta_f32: [f32; 16],

    pub fuel: u32,
    pub pc: u32,

    pub call_kind: [u16; CALLSTACK_DEPTH],
    pub call_pc: [u32; CALLSTACK_DEPTH],
    pub call_sp: usize,

    pub halted: bool,
    pub stop_reason: StopReason,

    #[cfg(feature = "trace")]
    pub trace: crate::vm::trace::TraceState,
}

impl Default for VmWorker {
    fn default() -> Self {
        Self {
            f: [0.0; F_REGS],
            i: [0; I_REGS],
            scratch: [0.0; SCRATCH_WORDS],
            meta_u32: [0; 16],
            meta_f32: [0.0; 16],
            fuel: 0,
            pc: 0,
            call_kind: [0; CALLSTACK_DEPTH],
            call_pc: [0; CALLSTACK_DEPTH],
            call_sp: 0,
            halted: false,
            stop_reason: StopReason::Halt,
            #[cfg(feature = "trace")]
            trace: crate::vm::trace::TraceState::default(),
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ExecConfig {
    pub fuel_max: u32,
    pub trace: bool,
    pub trace_budget_bytes: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct ExecResult {
    pub stop_reason: StopReason,
    pub fuel_used: u32,
    pub pc_end: u32,
}

pub fn run_candidate(
    worker: &mut VmWorker,
    prog: &crate::bytecode::program::BytecodeProgram,
    lib: &crate::library::bank::LibraryBank,
    cfg: &ExecConfig,
) -> ExecResult {
    exec::run_candidate(worker, prog, lib, cfg)
}

pub type VmProgram = crate::bytecode::program::BytecodeProgram;
