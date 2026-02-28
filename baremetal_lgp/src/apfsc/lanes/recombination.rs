use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::candidate::{clone_with_mutation, list_candidates, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::recombination::materialize_recombination_candidate;
use crate::apfsc::types::PromotionClass;

pub fn generate(
    root: &Path,
    active: &CandidateBundle,
    cfg: &Phase1Config,
) -> Result<Vec<CandidateBundle>> {
    let hashes = list_candidates(root)?;
    let parent_b = hashes
        .iter()
        .find(|h| h.as_str() != active.manifest.candidate_hash.as_str())
        .cloned()
        .unwrap_or_else(|| active.manifest.candidate_hash.clone());

    if let Ok((cand, _spec)) = materialize_recombination_candidate(
        root,
        &active.manifest.candidate_hash,
        &parent_b,
        "head_merge",
        cfg,
    ) {
        return Ok(vec![cand]);
    }

    let fallback = clone_with_mutation(
        active,
        "recombination",
        "fallback_head_merge",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        active.bridge_pack.clone(),
        BTreeMap::new(),
    )?;
    Ok(vec![fallback])
}
