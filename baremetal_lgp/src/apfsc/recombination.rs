use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::artifacts::{digest_json, write_json_atomic};
use crate::apfsc::candidate::{
    clone_with_mutation, load_candidate, save_candidate, CandidateBundle,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{PromotionClass, RecombinationSpec};

fn blend_vec(a: &[f32], b: &[f32]) -> Vec<f32> {
    let n = a.len().min(b.len());
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        out.push((a[i] + b[i]) * 0.5);
    }
    if n == 0 {
        return a.to_vec();
    }
    out
}

fn dedup_sorted(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut set = BTreeSet::new();
    for v in values {
        set.insert(v);
    }
    set.into_iter().collect()
}

pub fn materialize_recombination_candidate(
    root: &Path,
    parent_a_hash: &str,
    parent_b_hash: &str,
    mode: &str,
    _cfg: &Phase1Config,
) -> Result<(CandidateBundle, RecombinationSpec)> {
    if !matches!(mode, "block_swap" | "head_merge" | "macro_mix") {
        return Err(ApfscError::Validation(format!(
            "unsupported recombination mode '{mode}'"
        )));
    }

    let a = load_candidate(root, parent_a_hash)?;
    let b = load_candidate(root, parent_b_hash)?;
    if a.manifest.snapshot_hash != b.manifest.snapshot_hash {
        return Err(ApfscError::Validation(
            "recombination parents must share snapshot".to_string(),
        ));
    }

    let mut arch = a.arch_program.clone();
    let mut head = a.head_pack.clone();
    let mut state = a.state_pack.clone();
    let mut sched = a.schedule_pack.clone();

    match mode {
        "block_swap" => {
            if !b.arch_program.nodes.is_empty() {
                arch = b.arch_program.clone();
            }
            sched = b.schedule_pack.clone();
        }
        "head_merge" => {
            head.native_head.weights = blend_vec(
                &a.head_pack.native_head.weights,
                &b.head_pack.native_head.weights,
            );
            head.native_head.bias =
                blend_vec(&a.head_pack.native_head.bias, &b.head_pack.native_head.bias);
            head.residual_head.weights = blend_vec(
                &a.head_pack.residual_head.weights,
                &b.head_pack.residual_head.weights,
            );
            state.resid_weights =
                blend_vec(&a.state_pack.resid_weights, &b.state_pack.resid_weights);
        }
        "macro_mix" => {
            state.core_weights = blend_vec(&a.state_pack.core_weights, &b.state_pack.core_weights);
            state.resid_weights =
                blend_vec(&a.state_pack.resid_weights, &b.state_pack.resid_weights);
        }
        _ => {}
    }

    let mut deps = BTreeMap::new();
    deps.insert(
        "prior",
        dedup_sorted(
            a.manifest
                .prior_deps
                .iter()
                .cloned()
                .chain(b.manifest.prior_deps.iter().cloned()),
        ),
    );
    deps.insert(
        "substrate",
        dedup_sorted(
            a.manifest
                .substrate_deps
                .iter()
                .cloned()
                .chain(b.manifest.substrate_deps.iter().cloned()),
        ),
    );

    let mut child = clone_with_mutation(
        &a,
        "recombination",
        mode,
        PromotionClass::A,
        arch,
        head,
        state,
        sched,
        a.bridge_pack.clone(),
        deps,
    )?;
    crate::apfsc::candidate::rehash_candidate(&mut child)?;
    save_candidate(root, &child)?;

    let mut spec = RecombinationSpec {
        parent_candidate_hashes: vec![
            a.manifest.candidate_hash.clone(),
            b.manifest.candidate_hash.clone(),
        ],
        parent_contribution_ranges: BTreeMap::from([
            ("parent_a".to_string(), vec!["0..50".to_string()]),
            ("parent_b".to_string(), vec!["50..100".to_string()]),
        ]),
        merge_mode: mode.to_string(),
        compatibility_hash: String::new(),
    };
    spec.parent_candidate_hashes.sort();
    spec.compatibility_hash = digest_json(&(
        &spec.parent_candidate_hashes,
        &spec.merge_mode,
        &child.manifest.snapshot_hash,
    ))?;
    write_json_atomic(
        &root
            .join("candidates")
            .join(&child.manifest.candidate_hash)
            .join("recombination_spec.json"),
        &spec,
    )?;

    Ok((child, spec))
}
