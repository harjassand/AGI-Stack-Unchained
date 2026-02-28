use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_json, write_json_atomic};
use crate::apfsc::candidate::{
    clone_with_mutation, load_candidate, save_candidate, CandidateBundle,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::formal_policy::{load_active_formal_policy, seed_formal_policy};
use crate::apfsc::scir::verify::verify_program_with_formal_policy;
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

fn read_candidate_dependency_pack(
    root: &Path,
    candidate_hash: &str,
) -> Result<Option<crate::apfsc::types::DependencyPack>> {
    let path = root
        .join("candidates")
        .join(candidate_hash)
        .join("dependency_pack.json");
    if !path.exists() {
        return Ok(None);
    }
    let dep = read_json(&path)?;
    Ok(Some(dep))
}

fn ensure_parent_dependency_compatibility(
    a: &CandidateBundle,
    _b: &CandidateBundle,
    da: Option<&crate::apfsc::types::DependencyPack>,
    db: Option<&crate::apfsc::types::DependencyPack>,
) -> Result<()> {
    if let (Some(da), Some(db)) = (da, db) {
        if da.snapshot_hash != db.snapshot_hash || da.snapshot_hash != a.manifest.snapshot_hash {
            return Err(ApfscError::Validation(
                "recombination parents have incompatible dependency snapshot roots".to_string(),
            ));
        }
        if da.formal_policy_hash != db.formal_policy_hash {
            return Err(ApfscError::Validation(
                "recombination parents have incompatible formal policy roots".to_string(),
            ));
        }
        if da.macro_registry_hash != db.macro_registry_hash {
            return Err(ApfscError::Validation(
                "recombination parents have incompatible macro registry roots".to_string(),
            ));
        }
    }
    Ok(())
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
    let dep_a = read_candidate_dependency_pack(root, parent_a_hash)?;
    let dep_b = read_candidate_dependency_pack(root, parent_b_hash)?;
    ensure_parent_dependency_compatibility(&a, &b, dep_a.as_ref(), dep_b.as_ref())?;

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

    // Recombination must not bypass formal-policy verification.
    let active_formal = load_active_formal_policy(root).unwrap_or_else(|_| seed_formal_policy());
    verify_program_with_formal_policy(
        &child.arch_program,
        &child.manifest.resource_envelope,
        &active_formal,
    )?;

    crate::apfsc::candidate::rehash_candidate(&mut child)?;
    save_candidate(root, &child)?;

    // If parent dependency packs exist, persist a deterministic compatible pack for the child.
    if dep_a.is_some() || dep_b.is_some() {
        let snapshot_prior_roots = dep_a
            .as_ref()
            .map(|d| d.prior_roots.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.prior_roots.clone()))
            .unwrap_or_default();
        let snapshot_tool_roots = dep_a
            .as_ref()
            .map(|d| d.tool_roots.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.tool_roots.clone()))
            .unwrap_or_default();
        let snapshot_substrate_roots = dep_a
            .as_ref()
            .map(|d| d.substrate_roots.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.substrate_roots.clone()))
            .unwrap_or_default();
        let macro_registry_hash = dep_a
            .as_ref()
            .map(|d| d.macro_registry_hash.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.macro_registry_hash.clone()))
            .unwrap_or_default();
        let formal_policy_hash = dep_a
            .as_ref()
            .map(|d| d.formal_policy_hash.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.formal_policy_hash.clone()))
            .unwrap_or_else(|| "formal_policy_seed_v1".to_string());
        let snapshot_hash = dep_a
            .as_ref()
            .map(|d| d.snapshot_hash.clone())
            .or_else(|| dep_b.as_ref().map(|d| d.snapshot_hash.clone()))
            .unwrap_or_else(|| child.manifest.snapshot_hash.clone());
        if !macro_registry_hash.is_empty() {
            let mut dep = crate::apfsc::types::DependencyPack {
                snapshot_hash,
                prior_roots: snapshot_prior_roots,
                tool_roots: snapshot_tool_roots,
                formal_policy_hash,
                substrate_roots: snapshot_substrate_roots,
                macro_registry_hash,
                manifest_hash: String::new(),
            };
            dep.manifest_hash = digest_json(&dep)?;
            crate::apfsc::dependency_pack::write_candidate_dependency_pack(
                root,
                &child.manifest.candidate_hash,
                &dep,
            )?;
        }
    }

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
