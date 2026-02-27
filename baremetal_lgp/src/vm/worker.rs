use crate::abi::{CALLSTACK_DEPTH, F_REGS, I_REGS, SCRATCH_WORDS};

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
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

pub struct VmWorker {
    pub f: [f32; F_REGS],
    pub i: [i32; I_REGS],

    pub scratch: [f32; SCRATCH_WORDS],

    pub meta_u32: [u32; 16],
    pub meta_f32: [f32; 16],

    pub fuel: u32,
    pub pc: u32,

    // call stack frames: store (kind, pc)
    // kind: 0 => candidate; 1..=256 => library slot + 1
    pub call_kind: [u16; CALLSTACK_DEPTH],
    pub call_pc: [u32; CALLSTACK_DEPTH],
    pub call_sp: usize,

    pub halted: bool,
    pub stop_reason: StopReason,

    // trace is only allocated/used if trace enabled for this run
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

impl VmWorker {
    pub fn reset_runtime(&mut self, fuel: u32) {
        self.f = [0.0; F_REGS];
        self.i = [0; I_REGS];
        self.scratch = [0.0; SCRATCH_WORDS];
        self.meta_u32 = [0; 16];
        self.meta_f32 = [0.0; 16];
        self.fuel = fuel;
        self.pc = 0;
        self.call_kind = [0; CALLSTACK_DEPTH];
        self.call_pc = [0; CALLSTACK_DEPTH];
        self.call_sp = 0;
        self.halted = false;
        self.stop_reason = StopReason::Halt;
        #[cfg(feature = "trace")]
        {
            self.trace = crate::vm::trace::TraceState::default();
        }
    }
}
