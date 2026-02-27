use std::ffi::c_void;

use crate::contracts::constants::{META_F32, META_U32, SCRATCH_WORDS_F32};
use crate::oracle::scoring;
use crate::types::StopReason;

use super::abi::RuntimeState;
use super::arena::JitArena;
use super::constants::{MAX_STALL_US, RAW_MAX_WORDS, RAW_MIN_WORDS};
use super::ffi::{self, TrapInfo};
use super::sniper::{self, WorkerWatch};

pub const TRAP_SIGALRM: u32 = 4;
pub const SNIPER_USEC: i64 = 50_000;

#[derive(Clone, Copy, Debug, Default)]
pub struct FaultKindCounts {
    pub sigill: u32,
    pub sigsegv: u32,
    pub sigbus: u32,
    pub sigalrm: u32,
    pub other: u32,
}

#[derive(Clone, Copy, Debug)]
pub struct EpisodeLayout {
    pub in_base: usize,
    pub in_len: usize,
    pub out_base: usize,
    pub out_len: usize,
    pub work_base: usize,
    pub work_len: usize,
}

#[derive(Clone, Debug)]
pub struct EpisodeSpec {
    pub family: u8,
    pub layout: EpisodeLayout,
    pub in_data: Vec<f32>,
    pub target: Vec<f32>,
    pub oracle_meta_u32: [u32; META_U32],
    pub oracle_meta_f32: [f32; META_F32],
    pub expected_output_len: usize,
    pub d_hint: u32,
    pub flags: u32,
    pub hidden_seed: u64,
    pub robustness_bonus_scale: f32,
}

impl EpisodeSpec {
    #[inline(always)]
    pub fn write_inputs(&self, state: &mut RuntimeState) {
        let max = SCRATCH_WORDS_F32;
        let len = self
            .in_data
            .len()
            .min(self.layout.in_len)
            .min(max.saturating_sub(self.layout.in_base));
        let dst = &mut state.scratch[self.layout.in_base..self.layout.in_base + len];
        dst.copy_from_slice(&self.in_data[..len]);
    }

    #[inline(always)]
    pub fn write_meta(&self, state: &mut RuntimeState) {
        state.meta_u32.copy_from_slice(&self.oracle_meta_u32);
        state.meta_f32.copy_from_slice(&self.oracle_meta_f32);
    }

    #[inline(always)]
    pub fn clear_out_and_work(&self, state: &mut RuntimeState) {
        let out_len = self
            .layout
            .out_len
            .min(SCRATCH_WORDS_F32.saturating_sub(self.layout.out_base));
        state.scratch[self.layout.out_base..self.layout.out_base + out_len].fill(0.0);

        let work_len = self
            .layout
            .work_len
            .min(SCRATCH_WORDS_F32.saturating_sub(self.layout.work_base));
        state.scratch[self.layout.work_base..self.layout.work_base + work_len].fill(0.0);
    }
}

#[derive(Clone, Debug)]
pub struct EpisodeOutcome {
    pub trap: Option<TrapInfo>,
    pub returned: bool,
    pub score: f32,
    pub trap_kind: u32,
    pub timeout: bool,
    pub fault_kind_counts: FaultKindCounts,
}

pub struct RawContext {
    pub arena: JitArena,
    pub state: Box<RuntimeState>,
    pub installed_epoch: u64,
    pub installed_hash: [u8; 32],
    watch_ptr: *const WorkerWatch,
}

pub fn raw_thread_init(watch: &WorkerWatch) -> RawContext {
    raw_thread_init_with_stall_us(watch, MAX_STALL_US)
}

pub fn raw_thread_init_with_stall_us(watch: &WorkerWatch, max_stall_us: u64) -> RawContext {
    // SAFETY: initializes per-thread trap + signal stack state.
    unsafe { ffi::jit_trap_thread_init() };

    let arena = JitArena::new().expect("failed to create MAP_JIT arena");

    sniper::start_once(max_stall_us);
    sniper::register_worker(watch);

    RawContext {
        arena,
        state: Box::new(RuntimeState::default()),
        installed_epoch: 0,
        installed_hash: [0; 32],
        watch_ptr: watch as *const WorkerWatch,
    }
}

pub fn run_raw_candidate(
    ctx: &mut RawContext,
    candidate_words: &[u32],
    episode_spec: &EpisodeSpec,
) -> EpisodeOutcome {
    if candidate_words.len() < RAW_MIN_WORDS || candidate_words.len() > RAW_MAX_WORDS {
        return EpisodeOutcome {
            trap: Some(TrapInfo {
                kind: 15,
                sig: 0,
                fault_pc: 0,
                fault_addr: 0,
            }),
            returned: false,
            score: 0.0,
            trap_kind: 15,
            timeout: false,
            fault_kind_counts: FaultKindCounts {
                other: 1,
                ..FaultKindCounts::default()
            },
        };
    }

    // Fatal-flaw fix: full wipe before every episode, even after normal return.
    ctx.state.wipe_all();
    episode_spec.write_inputs(&mut ctx.state);
    episode_spec.write_meta(&mut ctx.state);
    episode_spec.clear_out_and_work(&mut ctx.state);
    ctx.state.status_u32 = 0;

    let slot_ptr = match ctx.arena.write_candidate(candidate_words) {
        Ok(ptr) => ptr,
        Err(_) => {
            return EpisodeOutcome {
                trap: Some(TrapInfo {
                    kind: 15,
                    sig: 0,
                    fault_pc: 0,
                    fault_addr: 0,
                }),
                returned: false,
                score: 0.0,
                trap_kind: 15,
                timeout: false,
                fault_kind_counts: FaultKindCounts {
                    other: 1,
                    ..FaultKindCounts::default()
                },
            };
        }
    };

    let mut trap = TrapInfo::default();
    // SAFETY: watch_ptr is set during raw_thread_init and remains valid for the thread lifetime.
    let watch = unsafe { &*ctx.watch_ptr };

    watch.arm_for_candidate();
    // SAFETY: slot_ptr points at JIT code with signature void(void*), state is valid.
    let rc = unsafe {
        let entry: ffi::JitEntry = std::mem::transmute::<*mut u8, ffi::JitEntry>(slot_ptr);
        ffi::run_jit_candidate(
            entry,
            (&mut *ctx.state as *mut RuntimeState).cast::<c_void>(),
            &mut trap as *mut TrapInfo,
        )
    };
    watch.disarm_after_candidate();

    if rc != 0 {
        let mut counts = FaultKindCounts::default();
        match trap.kind {
            1 => counts.sigill = 1,
            2 => counts.sigsegv = 1,
            3 => counts.sigbus = 1,
            4 => counts.sigalrm = 1,
            _ => counts.other = 1,
        }
        return EpisodeOutcome {
            trap: Some(trap),
            returned: false,
            score: 0.0,
            trap_kind: trap.kind,
            timeout: trap.kind == TRAP_SIGALRM,
            fault_kind_counts: counts,
        };
    }

    let out_len = episode_spec
        .expected_output_len
        .min(episode_spec.layout.out_len)
        .min(SCRATCH_WORDS_F32.saturating_sub(episode_spec.layout.out_base));
    let output = &ctx.state.scratch
        [episode_spec.layout.out_base..episode_spec.layout.out_base.saturating_add(out_len)];

    let stability_bonus = if episode_spec.family == 3 {
        scoring::stability_bonus(output, episode_spec.robustness_bonus_scale)
    } else {
        0.0
    };

    // Scoring uses only oracle-owned locals captured before kernel execution.
    let score = scoring::score_episode(
        output,
        &episode_spec.target,
        candidate_words.len() as u32,
        StopReason::Halt,
        stability_bonus,
    );

    EpisodeOutcome {
        trap: None,
        returned: true,
        score,
        trap_kind: 0,
        timeout: false,
        fault_kind_counts: FaultKindCounts::default(),
    }
}
