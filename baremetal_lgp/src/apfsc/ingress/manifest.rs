use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_json};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{FamilyKind, PackManifest, RealityMeta, RealityRole};

pub fn load_pack_manifest(path: &Path) -> Result<PackManifest> {
    read_json(path)
}

pub fn compute_manifest_pack_hash(manifest: &PackManifest) -> Result<String> {
    let mut canonical = manifest.clone();
    canonical.pack_hash.clear();
    digest_json(&canonical)
}

pub fn validate_manifest_hash(manifest: &PackManifest) -> Result<()> {
    let expected = compute_manifest_pack_hash(manifest)?;
    if manifest.pack_hash != expected {
        return Err(ApfscError::DigestMismatch(format!(
            "pack hash mismatch: expected {expected}, got {}",
            manifest.pack_hash
        )));
    }
    Ok(())
}

pub fn ensure_manifest_has_hash(mut manifest: PackManifest) -> Result<PackManifest> {
    if manifest.pack_hash.is_empty() {
        manifest.pack_hash = compute_manifest_pack_hash(&manifest)?;
    }
    validate_manifest_hash(&manifest)?;
    Ok(manifest)
}

pub fn finalize_manifest(
    raw_manifest: PackManifest,
    payload_hashes: Vec<String>,
) -> Result<PackManifest> {
    let declared_pack_hash = raw_manifest.pack_hash.clone();
    let declared_payload_hashes = raw_manifest.payload_hashes.clone();

    let mut manifest = raw_manifest;
    manifest.payload_hashes = payload_hashes;
    manifest.pack_hash.clear();
    manifest.pack_hash = compute_manifest_pack_hash(&manifest)?;

    if !declared_payload_hashes.is_empty() && declared_payload_hashes != manifest.payload_hashes {
        return Err(ApfscError::DigestMismatch(
            "payload hashes do not match declared manifest payload hashes".to_string(),
        ));
    }
    if !declared_pack_hash.is_empty() && declared_pack_hash != manifest.pack_hash {
        return Err(ApfscError::DigestMismatch(format!(
            "pack hash mismatch: declared {}, computed {}",
            declared_pack_hash, manifest.pack_hash
        )));
    }

    Ok(manifest)
}

pub fn decode_reality_meta(manifest: &PackManifest) -> Result<RealityMeta> {
    let family_id = manifest
        .meta
        .get("family_id")
        .and_then(|v| v.as_str())
        .map(|v| v.to_string())
        .or_else(|| manifest.family_id.clone())
        .ok_or_else(|| ApfscError::Validation("reality manifest missing family_id".to_string()))?;

    let family_kind = manifest
        .meta
        .get("family_kind")
        .and_then(|v| v.as_str())
        .map(parse_family_kind)
        .transpose()?
        .unwrap_or_else(default_family_kind);

    let role = manifest
        .meta
        .get("role")
        .and_then(|v| v.as_str())
        .map(parse_role)
        .transpose()?
        .unwrap_or(RealityRole::Base);

    let variant_id = manifest
        .meta
        .get("variant_id")
        .and_then(|v| v.as_str())
        .map(|v| v.to_string())
        .unwrap_or_else(|| default_variant_for_role(role));

    let base_family_id = manifest
        .meta
        .get("base_family_id")
        .and_then(|v| v.as_str())
        .map(|v| v.to_string());

    let description = manifest
        .meta
        .get("description")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    Ok(RealityMeta {
        family_id,
        family_kind,
        role,
        variant_id,
        base_family_id,
        description,
    })
}

fn parse_family_kind(v: &str) -> Result<FamilyKind> {
    match v {
        "AlgorithmicSymbolic" | "algorithmic_symbolic" | "det_micro" => {
            Ok(FamilyKind::AlgorithmicSymbolic)
        }
        "TextCodeLog" | "text_code_log" | "text_code" => Ok(FamilyKind::TextCodeLog),
        "SensoryTemporal" | "sensory_temporal" | "sensor_temporal" => {
            Ok(FamilyKind::SensoryTemporal)
        }
        "PhysicalSimulation" | "physical_simulation" | "phys_sim" => {
            Ok(FamilyKind::PhysicalSimulation)
        }
        other => Err(ApfscError::Validation(format!(
            "unknown family_kind '{other}'"
        ))),
    }
}

fn parse_role(v: &str) -> Result<RealityRole> {
    match v {
        "Base" | "base" => Ok(RealityRole::Base),
        "Transfer" | "transfer" => Ok(RealityRole::Transfer),
        "Robust" | "robust" => Ok(RealityRole::Robust),
        "ChallengeStub" | "challenge_stub" => Ok(RealityRole::ChallengeStub),
        other => Err(ApfscError::Validation(format!(
            "unknown reality role '{other}'"
        ))),
    }
}

fn default_variant_for_role(role: RealityRole) -> String {
    match role {
        RealityRole::Base => "base".to_string(),
        RealityRole::Transfer => "transfer".to_string(),
        RealityRole::Robust => "robust".to_string(),
        RealityRole::ChallengeStub => "challenge_stub".to_string(),
    }
}

fn default_family_kind() -> FamilyKind {
    FamilyKind::TextCodeLog
}
