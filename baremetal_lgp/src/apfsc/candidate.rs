use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{
    candidate_dir, create_dir_all_if_persistent, digest_bytes, digest_json, list_candidate_hashes,
    path_exists, read_bytes, read_json, read_pointer, write_bytes_atomic, write_json_atomic,
    write_pointer,
};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::ScirProgram;
use crate::apfsc::types::{self, HeadPack};
use crate::apfsc::types::{
    CandidateManifest, PromotionClass, ResourceEnvelope, SchedulePack, StatePack,
    WarmRefinementPack,
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BuildMeta {
    pub lane: String,
    pub mutation_type: String,
    pub created_unix_s: u64,
    pub notes: Option<String>,
    #[serde(default)]
    pub phase2: Option<types::CandidateBuildMeta>,
    #[serde(default)]
    pub phase3: Option<types::CandidatePhase3Meta>,
    #[serde(default)]
    pub phase4: Option<types::CandidatePhase4Meta>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateBundle {
    pub manifest: CandidateManifest,
    pub arch_program: ScirProgram,
    pub state_pack: StatePack,
    pub head_pack: HeadPack,
    pub bridge_pack: Option<WarmRefinementPack>,
    pub schedule_pack: SchedulePack,
    pub build_meta: BuildMeta,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CandidateBuildInput {
    pub parent_hashes: Vec<String>,
    pub snapshot_hash: String,
    pub promotion_class: PromotionClass,
    pub arch_program: ScirProgram,
    pub state_pack: StatePack,
    pub head_pack: HeadPack,
    pub bridge_pack: Option<WarmRefinementPack>,
    pub schedule_pack: SchedulePack,
    pub prior_deps: Vec<String>,
    pub substrate_deps: Vec<String>,
    pub resource_envelope: ResourceEnvelope,
    pub build_meta: BuildMeta,
}

pub fn build_candidate(input: CandidateBuildInput) -> Result<CandidateBundle> {
    let arch_hash = digest_json(&input.arch_program)?;
    let state_bytes = bincode::serialize(&input.state_pack)
        .map_err(|e| ApfscError::Protocol(format!("state pack encode failed: {e}")))?;
    let state_hash = digest_bytes(&state_bytes);
    let head_bytes = bincode::serialize(&input.head_pack)
        .map_err(|e| ApfscError::Protocol(format!("head pack encode failed: {e}")))?;
    let head_hash = digest_bytes(&head_bytes);

    let bridge_hash = match &input.bridge_pack {
        Some(b) => Some(digest_json(b)?),
        None => None,
    };
    let schedule_hash = digest_json(&input.schedule_pack)?;
    let build_meta_hash = digest_json(&input.build_meta)?;

    let interface_pack_hash = digest_bytes(b"apfsc_interface_pack_v1");

    let mut manifest = CandidateManifest {
        candidate_hash: String::new(),
        parent_hashes: input.parent_hashes,
        snapshot_hash: input.snapshot_hash,
        promotion_class: input.promotion_class,
        interface_pack_hash,
        arch_program_hash: arch_hash,
        state_pack_hash: state_hash,
        head_pack_hash: head_hash,
        bridge_pack_hash: bridge_hash,
        schedule_pack_hash: schedule_hash,
        prior_deps: input.prior_deps,
        substrate_deps: input.substrate_deps,
        resource_envelope: input.resource_envelope,
        build_meta_hash,
    };
    manifest.candidate_hash = digest_json(&manifest)?;

    Ok(CandidateBundle {
        manifest,
        arch_program: input.arch_program,
        state_pack: input.state_pack,
        head_pack: input.head_pack,
        bridge_pack: input.bridge_pack,
        schedule_pack: input.schedule_pack,
        build_meta: input.build_meta,
    })
}

pub fn save_candidate(root: &Path, bundle: &CandidateBundle) -> Result<()> {
    let dir = candidate_dir(root, &bundle.manifest.candidate_hash);
    create_dir_all_if_persistent(&dir)?;

    write_json_atomic(&dir.join("manifest.json"), &bundle.manifest)?;
    write_json_atomic(&dir.join("arch_program.json"), &bundle.arch_program)?;

    let state_bytes = bincode::serialize(&bundle.state_pack)
        .map_err(|e| ApfscError::Protocol(format!("state pack encode failed: {e}")))?;
    write_bytes_atomic(&dir.join("state_pack.bin"), &state_bytes)?;

    let head_bytes = bincode::serialize(&bundle.head_pack)
        .map_err(|e| ApfscError::Protocol(format!("head pack encode failed: {e}")))?;
    write_bytes_atomic(&dir.join("head_pack.bin"), &head_bytes)?;

    if let Some(bridge) = &bundle.bridge_pack {
        write_json_atomic(&dir.join("bridge_pack.json"), bridge)?;
    }
    write_json_atomic(&dir.join("schedule_pack.json"), &bundle.schedule_pack)?;
    write_json_atomic(&dir.join("build_meta.json"), &bundle.build_meta)?;
    Ok(())
}

pub fn load_candidate(root: &Path, candidate_hash: &str) -> Result<CandidateBundle> {
    let dir = candidate_dir(root, candidate_hash);
    let manifest: CandidateManifest = read_json(&dir.join("manifest.json"))?;
    let arch_program: ScirProgram = read_json(&dir.join("arch_program.json"))?;

    let state_bytes = read_bytes(&dir.join("state_pack.bin"))?;
    let state_pack: StatePack = bincode::deserialize(&state_bytes)
        .map_err(|e| ApfscError::Protocol(format!("state pack decode failed: {e}")))?;

    let head_bytes = read_bytes(&dir.join("head_pack.bin"))?;
    let head_pack: HeadPack = bincode::deserialize(&head_bytes)
        .map_err(|e| ApfscError::Protocol(format!("head pack decode failed: {e}")))?;

    let bridge_pack = {
        let p = dir.join("bridge_pack.json");
        if path_exists(&p) {
            Some(read_json(&p)?)
        } else {
            None
        }
    };

    let schedule_pack: SchedulePack = read_json(&dir.join("schedule_pack.json"))?;
    let build_meta: BuildMeta = read_json(&dir.join("build_meta.json"))?;

    Ok(CandidateBundle {
        manifest,
        arch_program,
        state_pack,
        head_pack,
        bridge_pack,
        schedule_pack,
        build_meta,
    })
}

pub fn load_active_candidate(root: &Path) -> Result<CandidateBundle> {
    let active = read_pointer(root, "active_candidate")?;
    load_candidate(root, &active)
}

pub fn list_candidates(root: &Path) -> Result<Vec<String>> {
    list_candidate_hashes(root)
}

pub fn validate_candidate_artifacts(root: &Path, candidate_hash: &str) -> Result<()> {
    let dir = candidate_dir(root, candidate_hash);
    if !path_exists(&dir) {
        return Err(ApfscError::Missing(format!(
            "candidate dir missing: {}",
            dir.display()
        )));
    }

    let bundle = load_candidate(root, candidate_hash)?;
    if bundle.manifest.candidate_hash != candidate_hash {
        return Err(ApfscError::DigestMismatch(format!(
            "candidate hash mismatch between path and manifest: {} != {}",
            candidate_hash, bundle.manifest.candidate_hash
        )));
    }

    let arch_hash = digest_json(&bundle.arch_program)?;
    if arch_hash != bundle.manifest.arch_program_hash {
        return Err(ApfscError::DigestMismatch(
            "arch_program_hash mismatch".to_string(),
        ));
    }

    let state_bytes = bincode::serialize(&bundle.state_pack)
        .map_err(|e| ApfscError::Protocol(format!("state pack encode failed: {e}")))?;
    let state_hash = digest_bytes(&state_bytes);
    if state_hash != bundle.manifest.state_pack_hash {
        return Err(ApfscError::DigestMismatch(
            "state_pack_hash mismatch".to_string(),
        ));
    }

    let head_bytes = bincode::serialize(&bundle.head_pack)
        .map_err(|e| ApfscError::Protocol(format!("head pack encode failed: {e}")))?;
    let head_hash = digest_bytes(&head_bytes);
    if head_hash != bundle.manifest.head_pack_hash {
        return Err(ApfscError::DigestMismatch(
            "head_pack_hash mismatch".to_string(),
        ));
    }

    let schedule_hash = digest_json(&bundle.schedule_pack)?;
    if schedule_hash != bundle.manifest.schedule_pack_hash {
        return Err(ApfscError::DigestMismatch(
            "schedule_pack_hash mismatch".to_string(),
        ));
    }

    let meta_hash = digest_json(&bundle.build_meta)?;
    if meta_hash != bundle.manifest.build_meta_hash {
        return Err(ApfscError::DigestMismatch(
            "build_meta_hash mismatch".to_string(),
        ));
    }

    match (&bundle.bridge_pack, &bundle.manifest.bridge_pack_hash) {
        (Some(bridge), Some(expected)) => {
            let got = digest_json(bridge)?;
            if &got != expected {
                return Err(ApfscError::DigestMismatch(
                    "bridge_pack_hash mismatch".to_string(),
                ));
            }
        }
        (None, None) => {}
        _ => {
            return Err(ApfscError::DigestMismatch(
                "bridge pack presence mismatch".to_string(),
            ));
        }
    }

    let mut manifest_for_hash = bundle.manifest.clone();
    manifest_for_hash.candidate_hash.clear();
    let expected_candidate_hash = digest_json(&manifest_for_hash)?;
    if expected_candidate_hash != bundle.manifest.candidate_hash {
        return Err(ApfscError::DigestMismatch(
            "candidate_hash digest mismatch".to_string(),
        ));
    }

    Ok(())
}

pub fn default_resource_envelope() -> ResourceEnvelope {
    ResourceEnvelope {
        max_steps: 1_000_000,
        max_state_bytes: 8 * 1024 * 1024,
        max_param_bits: crate::apfsc::constants::PARAM_BITS_MAX,
        max_wall_ms: 60_000,
        peak_rss_limit_bytes: crate::apfsc::constants::RSS_HARD_LIMIT_BYTES,
        max_mapped_bytes: crate::apfsc::constants::MAX_CONCURRENT_MAPPED_BYTES,
        backend: types::BackendKind::InterpTier0,
        batch_shape: (1, 1),
    }
}

pub fn clone_with_mutation(
    base: &CandidateBundle,
    lane: &str,
    mutation_type: &str,
    promotion_class: PromotionClass,
    arch_program: ScirProgram,
    head_pack: HeadPack,
    state_pack: StatePack,
    schedule_pack: SchedulePack,
    bridge_pack: Option<WarmRefinementPack>,
    deps: BTreeMap<&str, Vec<String>>,
) -> Result<CandidateBundle> {
    let input = CandidateBuildInput {
        parent_hashes: vec![base.manifest.candidate_hash.clone()],
        snapshot_hash: base.manifest.snapshot_hash.clone(),
        promotion_class,
        arch_program,
        state_pack,
        head_pack,
        bridge_pack,
        schedule_pack,
        prior_deps: deps.get("prior").cloned().unwrap_or_default(),
        substrate_deps: deps.get("substrate").cloned().unwrap_or_default(),
        resource_envelope: base.manifest.resource_envelope.clone(),
        build_meta: BuildMeta {
            lane: lane.to_string(),
            mutation_type: mutation_type.to_string(),
            created_unix_s: 0,
            notes: None,
            phase2: None,
            phase3: None,
            phase4: None,
        },
    };
    build_candidate(input)
}

pub fn set_phase2_build_meta(
    bundle: &mut CandidateBundle,
    target_families: Vec<String>,
    source_lane: &str,
    phase2_profile: &str,
) -> Result<()> {
    bundle.build_meta.phase2 = Some(types::CandidateBuildMeta {
        target_families,
        source_lane: source_lane.to_string(),
        phase2_profile: phase2_profile.to_string(),
    });
    rehash_candidate(bundle)
}

pub fn set_phase3_build_meta(
    bundle: &mut CandidateBundle,
    meta: types::CandidatePhase3Meta,
) -> Result<()> {
    bundle.build_meta.phase3 = Some(meta);
    rehash_candidate(bundle)
}

pub fn set_phase4_build_meta(
    bundle: &mut CandidateBundle,
    meta: types::CandidatePhase4Meta,
) -> Result<()> {
    bundle.build_meta.phase4 = Some(meta);
    rehash_candidate(bundle)
}

pub fn rehash_candidate(bundle: &mut CandidateBundle) -> Result<()> {
    bundle.manifest.arch_program_hash = digest_json(&bundle.arch_program)?;

    let state_bytes = bincode::serialize(&bundle.state_pack)
        .map_err(|e| ApfscError::Protocol(format!("state pack encode failed: {e}")))?;
    bundle.manifest.state_pack_hash = digest_bytes(&state_bytes);

    let head_bytes = bincode::serialize(&bundle.head_pack)
        .map_err(|e| ApfscError::Protocol(format!("head pack encode failed: {e}")))?;
    bundle.manifest.head_pack_hash = digest_bytes(&head_bytes);

    bundle.manifest.schedule_pack_hash = digest_json(&bundle.schedule_pack)?;
    bundle.manifest.build_meta_hash = digest_json(&bundle.build_meta)?;
    bundle.manifest.bridge_pack_hash = match &bundle.bridge_pack {
        Some(b) => Some(digest_json(b)?),
        None => None,
    };

    bundle.manifest.candidate_hash.clear();
    bundle.manifest.candidate_hash = digest_json(&bundle.manifest)?;
    Ok(())
}

pub fn rebase_active_candidate_to_snapshot(
    root: &Path,
    snapshot_hash: &str,
) -> Result<Option<String>> {
    let active = match read_pointer(root, "active_candidate") {
        Ok(v) => v,
        Err(_) => return Ok(None),
    };
    let mut bundle = load_candidate(root, &active)?;
    if bundle.manifest.snapshot_hash == snapshot_hash {
        return Ok(Some(bundle.manifest.candidate_hash));
    }

    bundle.manifest.snapshot_hash = snapshot_hash.to_string();
    rehash_candidate(&mut bundle)?;
    save_candidate(root, &bundle)?;
    write_pointer(root, "active_candidate", &bundle.manifest.candidate_hash)?;
    write_pointer(root, "rollback_candidate", &bundle.manifest.candidate_hash)?;
    Ok(Some(bundle.manifest.candidate_hash))
}
