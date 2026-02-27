use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex, RwLock};

use super::promote::ActiveRawKernel;

pub const EPOCH_EVALS: u64 = 50_000;
const KERNEL_HISTORY: usize = 3;

#[derive(Clone, Copy, Debug, Default)]
pub struct EpochHealth {
    pub mean_score: f32,
    pub trap_rate: f32,
    pub timeout_rate: f32,
}

pub struct KernelSwapState {
    active: RwLock<Arc<ActiveRawKernel>>,
    history: RwLock<VecDeque<Arc<ActiveRawKernel>>>,
    eval_counter: AtomicU64,
    epoch_evals: u64,
    last_health: Mutex<Option<EpochHealth>>,
}

impl KernelSwapState {
    pub fn new(initial_words: Vec<u32>) -> Self {
        let initial = ActiveRawKernel::new(initial_words, 0);
        Self {
            active: RwLock::new(initial),
            history: RwLock::new(VecDeque::new()),
            eval_counter: AtomicU64::new(0),
            epoch_evals: EPOCH_EVALS,
            last_health: Mutex::new(None),
        }
    }

    pub fn active_kernel(&self) -> Arc<ActiveRawKernel> {
        self.active.read().expect("active lock poisoned").clone()
    }

    pub fn on_eval_batch(&self, evals: u64) -> bool {
        let total = self
            .eval_counter
            .fetch_add(evals, Relaxed)
            .saturating_add(evals);
        total.is_multiple_of(self.epoch_evals)
    }

    pub fn publish_new_kernel(&self, words: Vec<u32>) -> Arc<ActiveRawKernel> {
        let current = self.active_kernel();
        {
            let mut hist = self.history.write().expect("history lock poisoned");
            hist.push_front(current.clone());
            while hist.len() > KERNEL_HISTORY {
                let _ = hist.pop_back();
            }
        }

        let next_epoch = current.epoch.saturating_add(1);
        let next = ActiveRawKernel::new(words, next_epoch);
        *self.active.write().expect("active lock poisoned") = next.clone();
        next
    }

    pub fn maybe_rollback(
        &self,
        next_health: EpochHealth,
        mean_drop_threshold: f32,
        trap_rate_rise_threshold: f32,
    ) -> bool {
        let mut last = self.last_health.lock().expect("health lock poisoned");
        let should_rollback = if let Some(prev) = *last {
            (next_health.mean_score < (prev.mean_score - mean_drop_threshold))
                || (next_health.trap_rate > (prev.trap_rate + trap_rate_rise_threshold))
                || (next_health.timeout_rate > 0.0)
        } else {
            false
        };

        if should_rollback {
            let rollback = {
                let mut hist = self.history.write().expect("history lock poisoned");
                hist.pop_front()
            };
            if let Some(kernel) = rollback {
                *self.active.write().expect("active lock poisoned") = kernel;
                *last = Some(next_health);
                return true;
            }
        }

        *last = Some(next_health);
        false
    }
}
