use crate::apfsc::config::Phase1Config;
use crate::apfsc::types::{BackendKind, PredictedCost, SchedulePack};

pub fn default_schedule(cfg: &Phase1Config) -> SchedulePack {
    SchedulePack {
        backend: BackendKind::InterpTier0,
        tile_bytes: cfg.limits.state_tile_bytes_max,
        segment_bytes: cfg.limits.segment_bytes,
        scheduler_class: Some(crate::apfsc::types::SchedulerClass::SerialScan),
        memory_law: Some(crate::apfsc::types::MemoryLawKind::FlatState),
        learning_law: Some(crate::apfsc::types::LearningLawKind::HeadOnlyAdaGrad),
        predicted_cost: None,
    }
}

pub fn with_predicted_cost(mut schedule: SchedulePack, cost: PredictedCost) -> SchedulePack {
    schedule.predicted_cost = Some(cost);
    schedule
}
