use super::funnel::NUM_FAMILIES;

pub const WEIGHT_MIN: f32 = 0.05;
pub const WEIGHT_MAX: f32 = 0.80;
pub const WEIGHT_UPDATE_PERIOD: u64 = 4096;

const WEIGHT_DELTA: f32 = 0.02;
const GAMED_MEAN_THRESHOLD: f32 = -0.05;

#[derive(Clone, Debug)]
pub struct MixtureState {
    weights: [f32; NUM_FAMILIES],
    recent_score_sum: [f32; NUM_FAMILIES],
    recent_score_count: [u32; NUM_FAMILIES],
    evaluated_candidates: u64,
}

impl MixtureState {
    pub fn new() -> Self {
        Self {
            weights: [1.0 / NUM_FAMILIES as f32; NUM_FAMILIES],
            recent_score_sum: [0.0; NUM_FAMILIES],
            recent_score_count: [0; NUM_FAMILIES],
            evaluated_candidates: 0,
        }
    }

    pub fn weights(&self) -> [f32; NUM_FAMILIES] {
        self.weights
    }

    pub fn observe_episode_score(&mut self, family: u8, score: f32) {
        let idx = usize::from(family % NUM_FAMILIES as u8);
        self.recent_score_sum[idx] += score;
        self.recent_score_count[idx] = self.recent_score_count[idx].saturating_add(1);
    }

    pub fn on_candidate_complete(&mut self) {
        self.evaluated_candidates = self.evaluated_candidates.saturating_add(1);
        if self
            .evaluated_candidates
            .is_multiple_of(WEIGHT_UPDATE_PERIOD)
        {
            self.update_weights();
        }
    }

    fn update_weights(&mut self) {
        for idx in 0..NUM_FAMILIES {
            let mean = if self.recent_score_count[idx] == 0 {
                0.0
            } else {
                self.recent_score_sum[idx] / self.recent_score_count[idx] as f32
            };

            if mean > GAMED_MEAN_THRESHOLD {
                self.weights[idx] += WEIGHT_DELTA;
            } else {
                self.weights[idx] -= WEIGHT_DELTA;
            }
        }

        renormalize_and_clamp(&mut self.weights);
        self.recent_score_sum = [0.0; NUM_FAMILIES];
        self.recent_score_count = [0; NUM_FAMILIES];
    }
}

impl Default for MixtureState {
    fn default() -> Self {
        Self::new()
    }
}

fn renormalize_and_clamp(weights: &mut [f32; NUM_FAMILIES]) {
    for _ in 0..2 {
        for weight in weights.iter_mut() {
            *weight = weight.clamp(WEIGHT_MIN, WEIGHT_MAX);
        }

        let total: f32 = weights.iter().sum();
        if total <= f32::EPSILON {
            let uniform = 1.0 / NUM_FAMILIES as f32;
            for weight in weights.iter_mut() {
                *weight = uniform;
            }
        } else {
            for weight in weights.iter_mut() {
                *weight /= total;
            }
        }
    }

    for weight in weights.iter_mut() {
        *weight = weight.clamp(WEIGHT_MIN, WEIGHT_MAX);
    }
}
