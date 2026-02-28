use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_pointer, write_json_atomic};
use crate::apfsc::errors::Result;
use crate::apfsc::types::DependencyPack;

pub fn build_dependency_pack(
    root: &Path,
    prior_roots: Vec<String>,
    tool_roots: Vec<String>,
    substrate_roots: Vec<String>,
    macro_registry_hash: &str,
) -> Result<DependencyPack> {
    let snapshot_hash = read_pointer(root, "active_snapshot")?;
    let formal_policy_hash = read_pointer(root, "active_formal_policy")
        .unwrap_or_else(|_| "formal_policy_seed_v1".to_string());
    let mut dep = DependencyPack {
        snapshot_hash,
        prior_roots,
        tool_roots,
        formal_policy_hash,
        substrate_roots,
        macro_registry_hash: macro_registry_hash.to_string(),
        manifest_hash: String::new(),
    };
    dep.manifest_hash = digest_json(&dep)?;
    Ok(dep)
}

pub fn write_candidate_dependency_pack(
    root: &Path,
    candidate_hash: &str,
    dep: &DependencyPack,
) -> Result<()> {
    write_json_atomic(
        &root
            .join("candidates")
            .join(candidate_hash)
            .join("dependency_pack.json"),
        dep,
    )
}
