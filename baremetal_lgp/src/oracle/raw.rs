use crate::contracts::constants::SCRATCH_WORDS_F32;
use crate::jit2::raw_runner::{self, EpisodeLayout, EpisodeSpec as RawEpisodeSpec, RawContext};

use super::funnel;
use super::mixture;
use super::regimes;
use super::{ExecConfig as OracleExecConfig, OracleConfig, SplitMix64};

const NUM_FAMILIES: usize = 4;
const FIXED_PROXY_EPS: usize = 2;
const FIXED_FULL_EPS_PER_FAMILY: usize = 4;
const FIXED_STABILITY_RUNS: usize = 3;
const SCRATCH_ALIGN_WORDS: usize = 64;
const SCRATCH_LAYOUT_TRIES: usize = 16;

#[derive(Clone, Copy, Debug)]
pub struct RawEvalReport {
    pub proxy_mean: f32,
    pub full_mean: Option<f32>,
    pub full_var: Option<f32>,
    pub trap_rate: f32,
    pub timeout_rate: f32,
    pub mean_words: u32,
    pub regime_profile_bits: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct RawStabilityReport {
    pub mean: f32,
    pub var: f32,
    pub trap_rate: f32,
    pub timeout_rate: f32,
}

pub struct RawOracle {
    cfg: OracleConfig,
    rng: SplitMix64,
    mixture: mixture::MixtureState,
    proxy_counter: u64,
}

impl RawOracle {
    pub fn new(cfg: OracleConfig, seed: u64) -> Self {
        let cfg = OracleConfig {
            fuel_max: cfg.fuel_max,
            proxy_eps: FIXED_PROXY_EPS,
            full_eps_per_family: FIXED_FULL_EPS_PER_FAMILY,
            stability_runs: FIXED_STABILITY_RUNS,
            topk_trace: cfg.topk_trace,
        };
        Self {
            cfg,
            rng: SplitMix64::new(seed),
            mixture: mixture::MixtureState::new(),
            proxy_counter: 0,
        }
    }

    pub fn eval_raw_candidate(
        &mut self,
        raw_ctx: &mut RawContext,
        words: &[u32],
        cfg: &OracleExecConfig,
    ) -> RawEvalReport {
        let proxy = self.run_proxy_pair(raw_ctx, words);

        let mut report = RawEvalReport {
            proxy_mean: proxy.mean,
            full_mean: None,
            full_var: None,
            trap_rate: proxy.trap_rate,
            timeout_rate: proxy.timeout_rate,
            mean_words: words.len() as u32,
            regime_profile_bits: 0,
        };

        // Phase-2 crash gating: reject proxy paths with high trap rate.
        if proxy.trap_rate > 0.10 {
            self.mixture.on_candidate_complete();
            return report;
        }

        if cfg.run_full_eval {
            let full = self.run_full_eval(raw_ctx, words);
            report.full_mean = Some(full.mean);
            report.full_var = Some(full.var);
            report.regime_profile_bits = full.regime_profile_bits;

            let total_eps = proxy.episodes.saturating_add(full.episodes);
            if total_eps > 0 {
                let total_traps = proxy.traps.saturating_add(full.traps);
                let total_timeouts = proxy.timeouts.saturating_add(full.timeouts);
                report.trap_rate = total_traps as f32 / total_eps as f32;
                report.timeout_rate = total_timeouts as f32 / total_eps as f32;
            }
        }

        self.mixture.on_candidate_complete();
        report
    }

    pub fn run_stability(&mut self, raw_ctx: &mut RawContext, words: &[u32]) -> RawStabilityReport {
        let runs = self.cfg.stability_runs.max(1);
        let mut means = Vec::with_capacity(runs);
        let mut traps = 0usize;
        let mut timeouts = 0usize;
        let mut episodes = 0usize;

        for _ in 0..runs {
            let full = self.run_full_eval(raw_ctx, words);
            means.push(full.mean);
            traps = traps.saturating_add(full.traps);
            timeouts = timeouts.saturating_add(full.timeouts);
            episodes = episodes.saturating_add(full.episodes);
        }

        let mean = mean(&means);
        RawStabilityReport {
            mean,
            var: variance(&means, mean),
            trap_rate: if episodes == 0 {
                0.0
            } else {
                traps as f32 / episodes as f32
            },
            timeout_rate: if episodes == 0 {
                0.0
            } else {
                timeouts as f32 / episodes as f32
            },
        }
    }

    pub fn stability_passes_promotion(stability: &RawStabilityReport) -> bool {
        stability.trap_rate == 0.0 && stability.timeout_rate == 0.0
    }

    fn run_proxy_pair(&mut self, raw_ctx: &mut RawContext, words: &[u32]) -> BatchStats {
        let weights = self.mixture.weights();
        let (coverage_family, weighted_family) =
            funnel::next_proxy_families(&mut self.proxy_counter, weights, &mut self.rng);

        let first = self.run_episode(coverage_family, raw_ctx, words);
        let second = self.run_episode(weighted_family, raw_ctx, words);

        build_batch_stats(&[first, second])
    }

    fn run_full_eval(&mut self, raw_ctx: &mut RawContext, words: &[u32]) -> BatchStats {
        let mut outcomes =
            Vec::with_capacity(self.cfg.full_eps_per_family.saturating_mul(NUM_FAMILIES));
        for family in 0..NUM_FAMILIES {
            for _ in 0..self.cfg.full_eps_per_family {
                outcomes.push(self.run_episode(family as u8, raw_ctx, words));
            }
        }
        build_batch_stats(&outcomes)
    }

    fn run_episode(&mut self, family: u8, raw_ctx: &mut RawContext, words: &[u32]) -> EpisodeStats {
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

        episode.meta_u32[regimes::META_IN_BASE] = usize_to_u32(layout.in_base);
        episode.meta_u32[regimes::META_IN_LEN] = usize_to_u32(layout.in_len);
        episode.meta_u32[regimes::META_OUT_BASE] = usize_to_u32(layout.out_base);
        episode.meta_u32[regimes::META_OUT_LEN] = usize_to_u32(layout.out_len);
        episode.meta_u32[regimes::META_WORK_BASE] = usize_to_u32(layout.work_base);
        episode.meta_u32[regimes::META_WORK_LEN] = usize_to_u32(layout.work_len);

        // Oracle-owned scoring values are captured before kernel execution.
        let expected_output_len = episode.target.len();
        let target = episode.target.clone();

        let spec = RawEpisodeSpec {
            family,
            layout: EpisodeLayout {
                in_base: layout.in_base,
                in_len: layout.in_len,
                out_base: layout.out_base,
                out_len: layout.out_len,
                work_base: layout.work_base,
                work_len: layout.work_len,
            },
            in_data: episode.in_data,
            target,
            oracle_meta_u32: episode.meta_u32,
            oracle_meta_f32: episode.meta_f32,
            expected_output_len,
            d_hint: expected_output_len as u32,
            flags: 0,
            hidden_seed: self.rng.next_u64(),
            robustness_bonus_scale: episode.robustness_bonus_scale,
        };

        let outcome = raw_runner::run_raw_candidate(raw_ctx, words, &spec);
        self.mixture.observe_episode_score(family, outcome.score);

        EpisodeStats {
            family,
            score: outcome.score,
            trapped: outcome.trap.is_some(),
            timeout: outcome.timeout,
        }
    }
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

#[derive(Clone, Copy, Debug)]
struct EpisodeStats {
    family: u8,
    score: f32,
    trapped: bool,
    timeout: bool,
}

#[derive(Clone, Debug)]
struct BatchStats {
    mean: f32,
    var: f32,
    trap_rate: f32,
    timeout_rate: f32,
    traps: usize,
    timeouts: usize,
    episodes: usize,
    regime_profile_bits: u8,
}

fn build_batch_stats(outcomes: &[EpisodeStats]) -> BatchStats {
    let mut scores = Vec::with_capacity(outcomes.len());
    let mut by_family_sum = [0.0_f32; NUM_FAMILIES];
    let mut by_family_count = [0usize; NUM_FAMILIES];
    let mut traps = 0usize;
    let mut timeouts = 0usize;

    for item in outcomes {
        scores.push(item.score);
        let idx = usize::from(item.family % NUM_FAMILIES as u8);
        by_family_sum[idx] += item.score;
        by_family_count[idx] = by_family_count[idx].saturating_add(1);
        if item.trapped {
            traps = traps.saturating_add(1);
        }
        if item.timeout {
            timeouts = timeouts.saturating_add(1);
        }
    }

    let mut by_family = [0.0_f32; NUM_FAMILIES];
    for idx in 0..NUM_FAMILIES {
        if by_family_count[idx] > 0 {
            by_family[idx] = by_family_sum[idx] / by_family_count[idx] as f32;
        }
    }

    let mean_score = mean(&scores);
    let episodes = outcomes.len();

    BatchStats {
        mean: mean_score,
        var: variance(&scores, mean_score),
        trap_rate: if episodes == 0 {
            0.0
        } else {
            traps as f32 / episodes as f32
        },
        timeout_rate: if episodes == 0 {
            0.0
        } else {
            timeouts as f32 / episodes as f32
        },
        traps,
        timeouts,
        episodes,
        regime_profile_bits: funnel::regime_profile_bits(by_family, mean_score),
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

fn usize_to_u32(value: usize) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}
