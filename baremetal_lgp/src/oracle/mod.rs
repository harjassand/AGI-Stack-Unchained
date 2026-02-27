use crate::contracts::constants::SCRATCH_WORDS_F32;
use crate::contracts::traits::{OracleHarness, TraceSink};
use crate::library::LibraryImage;
use crate::types::{EvalMode, EvalSummary, StopReason};
use crate::vm::{VmProgram, VmWorker};

pub mod funnel;
pub mod mixture;
pub mod regimes;
pub mod scoring;

const NUM_FAMILIES: usize = 4;
const SCRATCH_ALIGN_WORDS: usize = 64;
const SCRATCH_LAYOUT_TRIES: usize = 16;
const SCRATCH_MASK_I32: i32 = 0x3FFF;

#[derive(Clone, Copy, Debug)]
pub struct OracleConfig {
    pub fuel_max: u32,
    pub proxy_eps: usize,
    pub full_eps_per_family: usize,
    pub stability_runs: usize,
    pub topk_trace: usize,
}

impl Default for OracleConfig {
    fn default() -> Self {
        Self {
            fuel_max: 100_000,
            proxy_eps: 2,
            full_eps_per_family: 4,
            stability_runs: 3,
            topk_trace: 16,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct EpisodeReport {
    pub family: u8,
    pub score: f32,
    pub fuel_used: u32,
}

#[derive(Clone, Copy, Debug)]
pub struct EvalReport {
    pub proxy_mean: f32,
    pub full_mean: Option<f32>,
    pub full_by_family: Option<[f32; NUM_FAMILIES]>,
    pub full_var: Option<f32>,
    pub regime_profile_bits: u8,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ExecConfig {
    pub run_full_eval: bool,
}

#[derive(Clone, Copy, Debug)]
struct EpisodeOutcome {
    report: EpisodeReport,
    stop_reason: StopReason,
}

#[derive(Clone, Copy, Debug)]
struct ProxyEvalStats {
    mean: f32,
    var: f32,
    fuel_used_mean: f32,
    stop_reason: StopReason,
    family_means: [f32; NUM_FAMILIES],
}

#[derive(Clone, Copy, Debug)]
struct FullEvalStats {
    by_family: [f32; NUM_FAMILIES],
    mean: f32,
    var: f32,
    fuel_used_mean: f32,
    stop_reason: StopReason,
    regime_profile_bits: u8,
}

#[derive(Clone, Copy, Debug)]
struct ScratchLayout {
    in_base: usize,
    in_len: usize,
    out_base: usize,
    out_len: usize,
    work_base: usize,
    work_len: usize,
}

#[derive(Clone, Debug)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    pub fn next_f32(&mut self) -> f32 {
        let x = self.next_u64();
        let frac = (x as f64) / ((u64::MAX as f64) + 1.0);
        frac as f32
    }

    pub fn next_usize(&mut self, upper_exclusive: usize) -> usize {
        if upper_exclusive <= 1 {
            return 0;
        }
        (self.next_u64() % (upper_exclusive as u64)) as usize
    }

    pub fn range_f32(&mut self, lo: f32, hi: f32) -> f32 {
        if hi <= lo {
            return lo;
        }
        lo + (hi - lo) * self.next_f32()
    }

    pub fn gaussian(&mut self) -> f32 {
        let u1 = self.next_f32().max(f32::EPSILON);
        let u2 = self.next_f32();
        let r = (-2.0 * u1.ln()).sqrt();
        let theta = std::f32::consts::TAU * u2;
        r * theta.cos()
    }
}

pub struct Oracle {
    cfg: OracleConfig,
    rng: SplitMix64,
    mixture: mixture::MixtureState,
    proxy_counter: u64,
    trace_topk: Vec<(u64, f32)>,
    last_proxy: ProxyEvalStats,
}

impl Oracle {
    pub fn new(cfg: OracleConfig, seed: u64) -> Self {
        Self {
            cfg,
            rng: SplitMix64::new(seed),
            mixture: mixture::MixtureState::new(),
            proxy_counter: 0,
            trace_topk: Vec::new(),
            last_proxy: ProxyEvalStats {
                mean: 0.0,
                var: 0.0,
                fuel_used_mean: 0.0,
                stop_reason: StopReason::Halt,
                family_means: [0.0; NUM_FAMILIES],
            },
        }
    }

    pub fn proxy_counter(&self) -> u64 {
        self.proxy_counter
    }

    pub fn eval_candidate(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
        exec_cfg: &ExecConfig,
    ) -> EvalReport {
        let proxy = self.run_proxy_pair(worker, prog, lib);
        self.last_proxy = proxy;

        let mut report = EvalReport {
            proxy_mean: proxy.mean,
            full_mean: None,
            full_by_family: None,
            full_var: None,
            regime_profile_bits: 0,
        };

        if exec_cfg.run_full_eval {
            let full = self.run_full_eval(worker, prog, lib);
            report.full_mean = Some(full.mean);
            report.full_by_family = Some(full.by_family);
            report.full_var = Some(full.var);
            report.regime_profile_bits = full.regime_profile_bits;
        }

        self.mixture.on_candidate_complete();
        report
    }

    pub fn maybe_emit_trace_job(&mut self, candidate_id: u64, score: f32) -> bool {
        if self.cfg.topk_trace == 0 {
            return false;
        }

        if self.trace_topk.len() < self.cfg.topk_trace {
            self.trace_topk.push((candidate_id, score));
            return true;
        }

        let mut min_idx = 0usize;
        for idx in 1..self.trace_topk.len() {
            let (best_id, best_score) = self.trace_topk[min_idx];
            let (cur_id, cur_score) = self.trace_topk[idx];
            if (cur_score < best_score) || (cur_score == best_score && cur_id > best_id) {
                min_idx = idx;
            }
        }

        let (min_id, min_score) = self.trace_topk[min_idx];
        let should_emit = (score > min_score) || (score == min_score && candidate_id < min_id);
        if should_emit {
            self.trace_topk[min_idx] = (candidate_id, score);
            return true;
        }
        false
    }

    fn run_proxy_pair(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> ProxyEvalStats {
        let weights = self.mixture.weights();
        let (coverage_family, weighted_family) =
            funnel::next_proxy_families(&mut self.proxy_counter, weights, &mut self.rng);

        let first = self.run_episode(coverage_family, worker, prog, lib);
        let second = self.run_episode(weighted_family, worker, prog, lib);

        let scores = [first.report.score, second.report.score];
        let fuels = [
            first.report.fuel_used as f32,
            second.report.fuel_used as f32,
        ];
        let stop_reason = merge_stop_reason(first.stop_reason, second.stop_reason);

        let mut family_means = [0.0_f32; NUM_FAMILIES];
        let mut family_counts = [0_u32; NUM_FAMILIES];

        let first_idx = usize::from(first.report.family);
        family_means[first_idx] += first.report.score;
        family_counts[first_idx] += 1;

        let second_idx = usize::from(second.report.family);
        family_means[second_idx] += second.report.score;
        family_counts[second_idx] += 1;

        for (idx, mean_value) in family_means.iter_mut().enumerate() {
            if family_counts[idx] > 0 {
                *mean_value /= family_counts[idx] as f32;
            }
        }

        ProxyEvalStats {
            mean: mean(&scores),
            var: variance(&scores, mean(&scores)),
            fuel_used_mean: mean(&fuels),
            stop_reason,
            family_means,
        }
    }

    fn run_full_eval(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> FullEvalStats {
        let mut all_scores =
            Vec::with_capacity(self.cfg.full_eps_per_family.saturating_mul(NUM_FAMILIES));
        let mut family_sums = [0.0_f32; NUM_FAMILIES];
        let mut family_counts = [0_u32; NUM_FAMILIES];
        let mut total_fuel = 0.0_f32;
        let mut stop_reason = StopReason::Halt;

        for family in 0..NUM_FAMILIES {
            for _ in 0..self.cfg.full_eps_per_family {
                let outcome = self.run_episode(family as u8, worker, prog, lib);
                all_scores.push(outcome.report.score);
                family_sums[family] += outcome.report.score;
                family_counts[family] += 1;
                total_fuel += outcome.report.fuel_used as f32;
                stop_reason = merge_stop_reason(stop_reason, outcome.stop_reason);
            }
        }

        let mut by_family = [0.0_f32; NUM_FAMILIES];
        for (idx, value) in by_family.iter_mut().enumerate() {
            if family_counts[idx] > 0 {
                *value = family_sums[idx] / family_counts[idx] as f32;
            }
        }

        let mean_score = mean(&all_scores);
        let var_score = variance(&all_scores, mean_score);
        let bits = funnel::regime_profile_bits(by_family, mean_score);
        let fuel_used_mean = if all_scores.is_empty() {
            0.0
        } else {
            total_fuel / all_scores.len() as f32
        };

        FullEvalStats {
            by_family,
            mean: mean_score,
            var: var_score,
            fuel_used_mean,
            stop_reason,
            regime_profile_bits: bits,
        }
    }

    fn run_episode(
        &mut self,
        family: u8,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> EpisodeOutcome {
        let weights = self.mixture.weights();
        let family_idx = usize::from(family);
        let mut episode =
            regimes::sample_episode(family, &mut self.rng, weights, weights[family_idx]);

        let layout = allocate_layout(
            &mut self.rng,
            episode.in_data.len(),
            episode.out_len,
            episode.work_len,
        );

        if worker.scratch.len() != SCRATCH_WORDS_F32 {
            worker.scratch.resize(SCRATCH_WORDS_F32, 0.0);
        }
        worker.scratch[layout.out_base..layout.out_base + layout.out_len].fill(0.0);
        worker.scratch[layout.work_base..layout.work_base + layout.work_len].fill(0.0);

        for (offset, value) in episode.in_data.iter().copied().enumerate() {
            worker.scratch[layout.in_base + offset] = value;
        }

        episode.meta_u32[regimes::META_IN_BASE] = usize_to_u32(layout.in_base);
        episode.meta_u32[regimes::META_IN_LEN] = usize_to_u32(layout.in_len);
        episode.meta_u32[regimes::META_OUT_BASE] = usize_to_u32(layout.out_base);
        episode.meta_u32[regimes::META_OUT_LEN] = usize_to_u32(layout.out_len);
        episode.meta_u32[regimes::META_WORK_BASE] = usize_to_u32(layout.work_base);
        episode.meta_u32[regimes::META_WORK_LEN] = usize_to_u32(layout.work_len);

        let (fuel_used, stop_reason) =
            self.simulate_execution(worker, prog, lib, &episode, &layout);
        let output = &worker.scratch[layout.out_base..layout.out_base + layout.out_len];
        let stability_bonus = if family == 3 {
            scoring::stability_bonus(output, episode.robustness_bonus_scale)
        } else {
            0.0
        };
        let score = scoring::score_episode(
            output,
            &episode.target,
            fuel_used,
            stop_reason,
            stability_bonus,
        );

        self.mixture.observe_episode_score(family, score);
        EpisodeOutcome {
            report: EpisodeReport {
                family,
                score,
                fuel_used,
            },
            stop_reason,
        }
    }

    fn simulate_execution(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
        episode: &regimes::EpisodeSpec,
        layout: &ScratchLayout,
    ) -> (u32, StopReason) {
        let fuel_cost = self.estimate_fuel_cost(prog, lib, episode);
        if fuel_cost > self.cfg.fuel_max {
            return (self.cfg.fuel_max, StopReason::FuelExhausted);
        }

        if layout.in_len == 0 || layout.out_len == 0 {
            return (fuel_cost, StopReason::Halt);
        }

        let (alpha, beta, bias) = program_coeffs(prog, lib, episode.family);
        let in_base_i32 = i32::try_from(layout.in_base).unwrap_or(0);
        let out_base_i32 = i32::try_from(layout.out_base).unwrap_or(0);

        for out_idx in 0..layout.out_len {
            let src0_off = i32::try_from(out_idx % layout.in_len).unwrap_or(0);
            let src1_off =
                i32::try_from((out_idx.saturating_mul(7) + 3) % layout.in_len).unwrap_or(0);
            let src0_addr = ring_addr(in_base_i32, src0_off);
            let src1_addr = ring_addr(in_base_i32, src1_off);
            let x = worker.scratch[src0_addr];
            let y = worker.scratch[src1_addr];

            let trend = (out_idx as f32) * 0.0005;
            let family_bias = (episode.meta_f32[0] + episode.meta_f32[1]) * 0.001;
            let mut value = alpha.mul_add(x, beta.mul_add(y, bias + trend + family_bias));

            if episode.family == 2 || episode.family == 3 {
                value = 0.75 * value + 0.25 * (x - y);
            }

            let dst = ring_addr(out_base_i32, i32::try_from(out_idx).unwrap_or(0));
            worker.scratch[dst] = value;
        }

        (fuel_cost, StopReason::Halt)
    }

    fn estimate_fuel_cost(
        &self,
        prog: &VmProgram,
        lib: &LibraryImage,
        episode: &regimes::EpisodeSpec,
    ) -> u32 {
        let mut extra = 0_u32;
        let out_words = usize_to_u32(episode.out_len);

        if episode.family == 2 || episode.family == 3 {
            let lanes = out_words;
            extra = extra.saturating_add(2 + lanes.div_ceil(8));
        } else {
            extra = extra.saturating_add(2 + out_words.div_ceil(8));
        }

        if lib.slots.iter().any(Option::is_some) {
            extra = extra.saturating_add(1);
        }

        1_u32
            .saturating_add(usize_to_u32(prog.words.len()))
            .saturating_add(extra)
    }
}

impl OracleHarness for Oracle {
    fn eval(&mut self, worker: &mut VmWorker, prog: &VmProgram, mode: EvalMode) -> EvalSummary {
        let lib = LibraryImage::default();
        match mode {
            EvalMode::Proxy => {
                let _ = self.eval_candidate(worker, prog, &lib, &ExecConfig::default());
                EvalSummary {
                    score_mean: self.last_proxy.mean,
                    score_var: self.last_proxy.var,
                    fuel_used_mean: self.last_proxy.fuel_used_mean,
                    stop_reason: self.last_proxy.stop_reason,
                    family_means: self.last_proxy.family_means,
                }
            }
            EvalMode::Full => {
                let full = self.run_full_eval(worker, prog, &lib);
                self.mixture.on_candidate_complete();
                EvalSummary {
                    score_mean: full.mean,
                    score_var: full.var,
                    fuel_used_mean: full.fuel_used_mean,
                    stop_reason: full.stop_reason,
                    family_means: full.by_family,
                }
            }
            EvalMode::Stability => {
                let runs = self.cfg.stability_runs.max(1);
                let mut run_means = Vec::with_capacity(runs);
                let mut run_fuel = Vec::with_capacity(runs);
                let mut family_sums = [0.0_f32; NUM_FAMILIES];
                let mut stop_reason = StopReason::Halt;

                for _ in 0..runs {
                    let full = self.run_full_eval(worker, prog, &lib);
                    run_means.push(full.mean);
                    run_fuel.push(full.fuel_used_mean);
                    for (idx, value) in full.by_family.iter().copied().enumerate() {
                        family_sums[idx] += value;
                    }
                    stop_reason = merge_stop_reason(stop_reason, full.stop_reason);
                }

                self.mixture.on_candidate_complete();

                let mut family_means = [0.0_f32; NUM_FAMILIES];
                for (idx, value) in family_means.iter_mut().enumerate() {
                    *value = family_sums[idx] / runs as f32;
                }

                let score_mean = mean(&run_means);
                EvalSummary {
                    score_mean,
                    score_var: variance(&run_means, score_mean),
                    fuel_used_mean: mean(&run_fuel),
                    stop_reason,
                    family_means,
                }
            }
        }
    }

    fn eval_with_trace(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        mode: EvalMode,
        trace: &mut dyn TraceSink,
    ) -> EvalSummary {
        trace.on_block_enter(0);
        let summary = self.eval(worker, prog, mode);
        trace.on_edge(0, 0);
        trace.on_checkpoint(0, &worker.f, &worker.i);
        let output_len = worker.scratch.len().min(128);
        trace.on_finish(
            &worker.scratch[..output_len],
            summary.score_mean,
            summary.fuel_used_mean.max(0.0) as u32,
        );
        summary
    }
}

fn allocate_layout(
    rng: &mut SplitMix64,
    in_len: usize,
    out_len: usize,
    work_len: usize,
) -> ScratchLayout {
    for _ in 0..SCRATCH_LAYOUT_TRIES {
        let in_base = match sample_aligned_base(rng, in_len) {
            Some(base) => base,
            None => break,
        };
        let out_base = match sample_aligned_base(rng, out_len) {
            Some(base) => base,
            None => break,
        };
        let work_base = match sample_aligned_base(rng, work_len) {
            Some(base) => base,
            None => break,
        };

        let overlaps_any = overlaps(in_base, in_len, out_base, out_len)
            || overlaps(in_base, in_len, work_base, work_len)
            || overlaps(out_base, out_len, work_base, work_len);
        if !overlaps_any {
            return ScratchLayout {
                in_base,
                in_len,
                out_base,
                out_len,
                work_base,
                work_len,
            };
        }
    }

    ScratchLayout {
        in_base: 0,
        in_len,
        out_base: 4096,
        out_len,
        work_base: 8192,
        work_len,
    }
}

fn sample_aligned_base(rng: &mut SplitMix64, len: usize) -> Option<usize> {
    if len > SCRATCH_WORDS_F32 {
        return None;
    }
    let max_start = SCRATCH_WORDS_F32 - len;
    let max_slot = max_start / SCRATCH_ALIGN_WORDS;
    let slot = rng.next_usize(max_slot + 1);
    Some(slot * SCRATCH_ALIGN_WORDS)
}

fn overlaps(base_a: usize, len_a: usize, base_b: usize, len_b: usize) -> bool {
    (base_a < base_b.saturating_add(len_b)) && (base_b < base_a.saturating_add(len_a))
}

fn ring_addr(base_i32: i32, offset_i32: i32) -> usize {
    ((base_i32 + offset_i32) & SCRATCH_MASK_I32) as usize
}

fn program_coeffs(prog: &VmProgram, lib: &LibraryImage, family: u8) -> (f32, f32, f32) {
    let mut mixed = 0xD1B5_4A32_D192_ED03_u64 ^ u64::from(family);
    for word in prog.words.iter().take(128) {
        mixed ^= u64::from(*word).wrapping_add(0x9E37_79B9_7F4A_7C15);
        mixed = mixed.rotate_left(27).wrapping_mul(0x94D0_49BB_1331_11EB);
    }

    let occupied_slots = lib.slots.iter().filter(|slot| slot.is_some()).count() as u64;
    mixed ^= occupied_slots.wrapping_mul(0xBF58_476D_1CE4_E5B9);

    let to_signed_unit = |x: u64| -> f32 {
        let lane = (x & 0xFFFF) as f32 / 65_535.0;
        (lane * 2.0) - 1.0
    };

    let alpha = 0.8 + 0.2 * to_signed_unit(mixed);
    let beta = 0.3 * to_signed_unit(mixed >> 16);
    let bias = 0.1 * to_signed_unit(mixed >> 32);
    (alpha, beta, bias)
}

fn mean(values: &[f32]) -> f32 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f32>() / values.len() as f32
    }
}

fn variance(values: &[f32], mean_value: f32) -> f32 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sum = 0.0_f32;
    for value in values {
        let d = *value - mean_value;
        sum += d * d;
    }
    sum / values.len() as f32
}

fn merge_stop_reason(current: StopReason, next: StopReason) -> StopReason {
    if current == StopReason::Halt && next != StopReason::Halt {
        return next;
    }
    current
}

fn usize_to_u32(value: usize) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}
