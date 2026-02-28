use crate::apfsc::config::Phase1Config;
use crate::apfsc::types::{BackendKind, PredictedCost, SchedulePack};

pub fn default_schedule(cfg: &Phase1Config) -> SchedulePack {
    SchedulePack {
        backend: BackendKind::Tier0Cpu,
        tile_bytes: cfg.limits.state_tile_bytes_max,
        segment_bytes: cfg.limits.segment_bytes,
        predicted_cost: None,
    }
}

pub fn with_predicted_cost(mut schedule: SchedulePack, cost: PredictedCost) -> SchedulePack {
    schedule.predicted_cost = Some(cost);
    schedule
}
