use std::collections::BTreeMap;

use crate::apfsc::bank::window_bytes;
use crate::apfsc::bytecoder::score_panel;
use crate::apfsc::candidate::{clone_with_mutation, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::rewrite::{
    insert_identity_linear, remove_identity_linear, split_linear_identity, widen_with_zero_channels,
};
use crate::apfsc::types::{PromotionClass, WindowRef};

pub fn generate(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "insert_identity_linear",
        PromotionClass::S,
        insert_identity_linear(&active.arch_program)?,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "remove_identity_linear",
        PromotionClass::S,
        remove_identity_linear(&active.arch_program)?,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "widen_zero_channels",
        PromotionClass::A,
        widen_with_zero_channels(&active.arch_program, 8)?,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "split_linear_identity",
        PromotionClass::S,
        split_linear_identity(&active.arch_program)?,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "split_readout_zero_init",
        PromotionClass::S,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.push(clone_with_mutation(
        active,
        "equivalence",
        "macro_expand_refold",
        PromotionClass::S,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?);

    out.truncate(cfg.lanes.max_equivalence_candidates);
    Ok(out)
}

pub fn filter_witness_equality(
    active: &CandidateBundle,
    candidates: Vec<CandidateBundle>,
    witnesses: &[WindowRef],
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
) -> Result<Vec<CandidateBundle>> {
    let tol = 1e-6;
    let parent = score_panel(
        &active.arch_program,
        &active.head_pack,
        payloads_by_seq_hash,
        witnesses,
    )?;

    let mut out = Vec::new();
    for cand in candidates {
        let csum = score_panel(
            &cand.arch_program,
            &cand.head_pack,
            payloads_by_seq_hash,
            witnesses,
        )?;
        let delta_per_byte = if witnesses.is_empty() {
            0.0
        } else {
            (csum.total_bits - parent.total_bits).abs() / witnesses.len() as f64
        };
        if delta_per_byte <= tol {
            out.push(cand);
        }
    }
    Ok(out)
}

pub fn witness_preserves_output(
    parent: &CandidateBundle,
    rewritten: &CandidateBundle,
    witness_window: &WindowRef,
    payload: &[u8],
) -> Result<bool> {
    let input = window_bytes(payload, witness_window)?;
    let p = crate::apfsc::scir::interp::run_program(&parent.arch_program, input)?;
    let r = crate::apfsc::scir::interp::run_program(&rewritten.arch_program, input)?;
    if p.feature.len() != r.feature.len() {
        return Err(ApfscError::Validation(
            "feature dims differ in witness preservation check".to_string(),
        ));
    }
    let mut max_abs = 0.0f32;
    for (a, b) in p.feature.iter().zip(r.feature.iter()) {
        max_abs = max_abs.max((a - b).abs());
    }
    Ok(max_abs <= 1e-6)
}
