use std::fs;
use std::io;
use std::path::Path;

use crate::search::mutate::MUTATION_OPERATOR_COUNT;
use crate::search::rng::Rng;

#[derive(Clone, Debug)]
pub struct Exp3Bandit {
    pub weights: [f32; MUTATION_OPERATOR_COUNT],
    pub gamma: f32,
    pub evaluation_counter: u64,
}

impl Exp3Bandit {
    pub fn new(initial_weights: [f32; MUTATION_OPERATOR_COUNT], gamma: f32) -> Self {
        let mut bandit = Self {
            weights: initial_weights,
            gamma: gamma.clamp(0.0001, 0.99),
            evaluation_counter: 0,
        };
        bandit.renormalize();
        bandit
    }

    pub fn probabilities(&self) -> [f32; MUTATION_OPERATOR_COUNT] {
        let mut probs = [0.0_f32; MUTATION_OPERATOR_COUNT];
        let total = self.weights.iter().sum::<f32>().max(f32::MIN_POSITIVE);
        let k = MUTATION_OPERATOR_COUNT as f32;
        for (idx, prob) in probs.iter_mut().enumerate() {
            let exploit = self.weights[idx] / total;
            *prob = (1.0 - self.gamma) * exploit + self.gamma / k;
        }
        probs
    }

    pub fn sample_operator(&self, rng: &mut Rng) -> usize {
        let probs = self.probabilities();
        rng.sample_weighted_index(&probs).unwrap_or(0)
    }

    pub fn update_from_reward(&mut self, operator_idx: usize, wins_per_hour_delta: f32) {
        if operator_idx >= MUTATION_OPERATOR_COUNT {
            return;
        }
        self.evaluation_counter = self.evaluation_counter.saturating_add(1);
        let probs = self.probabilities();
        let p = probs[operator_idx].max(1e-6);
        let reward_hat = wins_per_hour_delta / p;
        let k = MUTATION_OPERATOR_COUNT as f32;
        let factor = (self.gamma * reward_hat / k).exp();
        self.weights[operator_idx] = (self.weights[operator_idx] * factor).max(1e-6);
        self.renormalize();
    }

    pub fn apply_batch_updates(&mut self, rewards: &[(usize, f32)]) {
        for &(op_idx, reward) in rewards {
            self.update_from_reward(op_idx, reward);
        }
    }

    pub fn write_weights_file(&self, run_dir: impl AsRef<Path>) -> io::Result<()> {
        let path = run_dir.as_ref().join("mutation_weights.json");
        let mut body = String::from("{\"weights\":[");
        for (idx, weight) in self.weights.iter().enumerate() {
            if idx > 0 {
                body.push(',');
            }
            body.push_str(&format!("{weight:.8}"));
        }
        body.push_str("],\"eval_counter\":");
        body.push_str(&self.evaluation_counter.to_string());
        body.push('}');
        fs::write(path, body)
    }

    fn renormalize(&mut self) {
        let total = self.weights.iter().sum::<f32>();
        if total <= f32::EPSILON {
            self.weights = [1.0 / MUTATION_OPERATOR_COUNT as f32; MUTATION_OPERATOR_COUNT];
            return;
        }
        for value in &mut self.weights {
            *value = (*value / total).max(1e-6);
        }
        let final_total = self.weights.iter().sum::<f32>().max(f32::MIN_POSITIVE);
        for value in &mut self.weights {
            *value /= final_total;
        }
    }
}
