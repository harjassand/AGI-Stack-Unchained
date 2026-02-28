use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_json};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::PackManifest;

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
