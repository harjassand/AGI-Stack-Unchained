pub mod ast;
pub mod chunkpack;
pub mod compile;
pub mod cost;
pub mod spec;
pub mod validity;

use crate::jit2::raw_runner::{
    self, raw_thread_init_with_stall_us, EpisodeLayout, EpisodeSpec, RawContext, TRAP_SIGALRM,
};
use crate::jit2::sniper::WorkerWatch;

use self::chunkpack::ChunkPack;

pub struct ChunkScoreReport {
    pub score_mean: f32,
    pub faulted: bool,
    pub sigalrm: u32,
    pub sigill: u32,
    pub sigsegv: u32,
    pub sigbus: u32,
    pub other_fault: u32,
    pub episodes_scored: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecFault {
    Sigalrm,
    Sigill,
    Sigsegv,
    Sigbus,
    Other,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecOutcome {
    Success,
    Fault(ExecFault),
}

pub trait ExecEngine<Candidate> {
    fn run_episode(
        &mut self,
        candidate: &Candidate,
        chunk: &ChunkPack,
        episode: u32,
        output: &mut [f32],
    ) -> ExecOutcome;
}

pub fn score_candidate_on_chunk<Candidate, E: ExecEngine<Candidate>>(
    engine: &mut E,
    candidate: &Candidate,
    chunk: &ChunkPack,
) -> ChunkScoreReport {
    let mut report = ChunkScoreReport {
        score_mean: 0.0,
        faulted: false,
        sigalrm: 0,
        sigill: 0,
        sigsegv: 0,
        sigbus: 0,
        other_fault: 0,
        episodes_scored: 0,
    };

    if chunk.episode_count == 0 {
        return report;
    }

    let mut sum = 0.0_f32;
    let mut output_buf = vec![0.0_f32; chunk.output_len as usize];

    for ep in 0..chunk.episode_count {
        output_buf.fill(0.0);
        match engine.run_episode(candidate, chunk, ep, &mut output_buf) {
            ExecOutcome::Success => {
                let mse = mse(&output_buf, chunk.target(ep));
                let score_ep = 1.0 / (1.0 + mse);
                sum += score_ep;
                report.episodes_scored = report.episodes_scored.saturating_add(1);
            }
            ExecOutcome::Fault(kind) => {
                report.faulted = true;
                match kind {
                    ExecFault::Sigalrm => report.sigalrm = report.sigalrm.saturating_add(1),
                    ExecFault::Sigill => report.sigill = report.sigill.saturating_add(1),
                    ExecFault::Sigsegv => report.sigsegv = report.sigsegv.saturating_add(1),
                    ExecFault::Sigbus => report.sigbus = report.sigbus.saturating_add(1),
                    ExecFault::Other => report.other_fault = report.other_fault.saturating_add(1),
                }
                report.score_mean = 0.0;
                return report;
            }
        }
    }

    if report.episodes_scored > 0 {
        report.score_mean = sum / report.episodes_scored as f32;
    }
    report
}

fn mse(output: &[f32], target: &[f32]) -> f32 {
    if output.is_empty() || target.is_empty() {
        return 0.0;
    }
    let len = output.len().min(target.len());
    let mut sum = 0.0_f32;
    for i in 0..len {
        let d = output[i] - target[i];
        sum += d * d;
    }
    sum / len as f32
}

pub struct RawJitExecEngine {
    ctx: RawContext,
    _watch: &'static WorkerWatch,
}

impl RawJitExecEngine {
    pub fn new(sniper_usec: i64) -> Self {
        let watch = Box::leak(Box::new(WorkerWatch::new()));
        let ctx = raw_thread_init_with_stall_us(watch, sniper_usec.max(1) as u64);
        Self { ctx, _watch: watch }
    }
}

impl ExecEngine<Vec<u32>> for RawJitExecEngine {
    fn run_episode(
        &mut self,
        candidate: &Vec<u32>,
        chunk: &ChunkPack,
        episode: u32,
        output: &mut [f32],
    ) -> ExecOutcome {
        if output.len() < chunk.output_len as usize {
            return ExecOutcome::Fault(ExecFault::Other);
        }

        let meta_u32_slice = chunk.meta_u32(episode);
        let meta_f32_slice = chunk.meta_f32(episode);
        if meta_u32_slice.len() < 6 {
            return ExecOutcome::Fault(ExecFault::Other);
        }

        let in_base = meta_u32_slice[0] as usize;
        let out_base = meta_u32_slice[1] as usize;
        let work_base = meta_u32_slice[2] as usize;
        let in_len = meta_u32_slice[3] as usize;
        let out_len = meta_u32_slice[4] as usize;
        let work_len = meta_u32_slice[5] as usize;

        let mut meta_u32 = [0_u32; 16];
        for (dst, src) in meta_u32.iter_mut().zip(meta_u32_slice.iter().copied()) {
            *dst = src;
        }

        let mut meta_f32 = [0.0_f32; 16];
        for (dst, src) in meta_f32.iter_mut().zip(meta_f32_slice.iter().copied()) {
            *dst = src;
        }

        let spec = EpisodeSpec {
            family: 0,
            layout: EpisodeLayout {
                in_base,
                in_len,
                out_base,
                out_len,
                work_base,
                work_len,
            },
            in_data: chunk.input(episode).to_vec(),
            target: chunk.target(episode).to_vec(),
            oracle_meta_u32: meta_u32,
            oracle_meta_f32: meta_f32,
            expected_output_len: chunk.output_len as usize,
            d_hint: chunk.output_len,
            flags: 0,
            hidden_seed: u64::from(episode),
            robustness_bonus_scale: 0.0,
        };

        let outcome = raw_runner::run_raw_candidate(&mut self.ctx, candidate, &spec);
        if !outcome.returned {
            let kind = match outcome.trap_kind {
                1 => ExecFault::Sigill,
                2 => ExecFault::Sigsegv,
                3 => ExecFault::Sigbus,
                TRAP_SIGALRM => ExecFault::Sigalrm,
                _ => ExecFault::Other,
            };
            return ExecOutcome::Fault(kind);
        }

        let out_end = out_base.saturating_add(chunk.output_len as usize);
        if out_end > self.ctx.state.scratch.len() {
            return ExecOutcome::Fault(ExecFault::Other);
        }
        output[..chunk.output_len as usize]
            .copy_from_slice(&self.ctx.state.scratch[out_base..out_end]);
        ExecOutcome::Success
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::Ordering;

    use crate::oracle3::ast::{AstNode, AstOp, AstProgram, AstShape, AST_EVAL_CALLS};
    use crate::oracle3::compile::{compile_chunkpack, FULL_COMPILE_CFG, SPEC_VERSION};
    use crate::oracle3::spec::{InputDistSpec, PiecewiseScheduleSpec, RegimeSpec};

    use super::{score_candidate_on_chunk, ExecEngine, ExecOutcome};

    fn scale2_spec() -> RegimeSpec {
        RegimeSpec {
            version: SPEC_VERSION,
            spec_seed_salt: 7,
            input_len: 1,
            output_len: 1,
            meta_u32_len: 16,
            meta_f32_len: 16,
            episode_param_count: 4,
            input_dist: InputDistSpec::Uniform { lo: -1.0, hi: 1.0 },
            ast: AstProgram {
                nodes: vec![
                    AstNode {
                        op: AstOp::InputVector,
                        shape: AstShape::Vector(1),
                    },
                    AstNode {
                        op: AstOp::ConstF32(2.0),
                        shape: AstShape::Scalar,
                    },
                    AstNode {
                        op: AstOp::Mul { a: 0, b: 1 },
                        shape: AstShape::Vector(1),
                    },
                ],
                output: 2,
            },
            schedule: PiecewiseScheduleSpec { segments: vec![] },
        }
    }

    #[test]
    fn no_ast_calls_during_candidate_scoring() {
        AST_EVAL_CALLS.store(0, Ordering::Relaxed);

        let spec = scale2_spec();
        let chunk = compile_chunkpack(&spec, 321, FULL_COMPILE_CFG).expect("compile");
        assert!(AST_EVAL_CALLS.load(Ordering::Relaxed) > 0);

        AST_EVAL_CALLS.store(0, Ordering::Relaxed);

        struct PerfectEngine;
        impl ExecEngine<()> for PerfectEngine {
            fn run_episode(
                &mut self,
                _candidate: &(),
                chunk: &crate::oracle3::chunkpack::ChunkPack,
                episode: u32,
                output: &mut [f32],
            ) -> ExecOutcome {
                output.copy_from_slice(chunk.target(episode));
                ExecOutcome::Success
            }
        }

        let mut engine = PerfectEngine;
        let report = score_candidate_on_chunk(&mut engine, &(), &chunk);
        assert!(report.score_mean > 0.99);
        assert_eq!(AST_EVAL_CALLS.load(Ordering::Relaxed), 0);
    }
}
