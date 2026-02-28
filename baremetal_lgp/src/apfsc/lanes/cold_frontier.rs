use std::collections::BTreeMap;

use crate::apfsc::candidate::{clone_with_mutation, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{
    LearningLawKind, MemoryLawKind, PromotionClass, SchedulerClass, WarmRefinementPack,
};

pub fn generate(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();

    let mut schedule_warm = active.schedule_pack.clone();
    schedule_warm.scheduler_class = Some(SchedulerClass::EventSparse);
    schedule_warm.memory_law = Some(MemoryLawKind::RingSlots);
    schedule_warm.learning_law = Some(LearningLawKind::ResidualAdaGrad);
    let warm_bridge = WarmRefinementPack {
        observable_map_hash: Some("warm_observable_v1".to_string()),
        state_map_hash: Some("warm_state_v1".to_string()),
        tolerance_spec_hash: Some("warm_tol_v1".to_string()),
        protected_head_ids: vec!["native_head".to_string()],
        protected_families: vec!["det_micro".to_string(), "text_code".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "warm_transition_v1".to_string(),
    };
    out.push(clone_with_mutation(
        active,
        "cold_frontier",
        "pwarm_event_sparse",
        PromotionClass::PWarm,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule_warm,
        Some(warm_bridge),
        BTreeMap::new(),
    )?);

    let mut schedule_cold = active.schedule_pack.clone();
    schedule_cold.scheduler_class = Some(SchedulerClass::TwoPassMemory);
    schedule_cold.memory_law = Some(MemoryLawKind::SelectiveState);
    schedule_cold.learning_law = Some(LearningLawKind::FastWeightDelta);
    out.push(clone_with_mutation(
        active,
        "cold_frontier",
        "pcold_formal_alg",
        PromotionClass::PCold,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule_cold,
        None,
        BTreeMap::new(),
    )?);

    let max_frontier = ((cfg.phase3.budgets.cold_frontier * cfg.lanes.max_public_candidates as f64)
        .round() as usize)
        .max(1);
    out.truncate(max_frontier);
    Ok(out)
}
