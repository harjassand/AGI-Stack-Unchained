use std::collections::BTreeMap;

use crate::apfsc::candidate::{clone_with_mutation, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{BackendKind, PromotionClass};

pub fn generate(active: &CandidateBundle, _cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let mut schedule = active.schedule_pack.clone();
    schedule.backend = BackendKind::GraphBackend;
    let cand = clone_with_mutation(
        active,
        "tool_shadow",
        "graph_shadow_candidate",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule,
        active.bridge_pack.clone(),
        BTreeMap::new(),
    )?;
    Ok(vec![cand])
}
