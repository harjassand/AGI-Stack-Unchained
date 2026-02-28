use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{
    copy_file, digest_file, ensure_layout, pack_dir, read_pointer, write_json_atomic,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::formal_policy::apply_formal_policy;
use crate::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use crate::apfsc::ingress::reality::refresh_active_snapshot;
use crate::apfsc::ingress::receipts::write_ingress_receipt;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{FormalPolicy, IngressReceipt, PackKind};

pub fn ingest_formal(
    root: &Path,
    cfg: &Phase1Config,
    manifest_path: &Path,
) -> Result<(
    IngressReceipt,
    crate::apfsc::types::FormalPackAdmissionReceipt,
)> {
    ensure_layout(root)?;

    let raw_manifest = load_pack_manifest(manifest_path)?;
    if raw_manifest.pack_kind != PackKind::Formal {
        return Err(ApfscError::Validation(
            "manifest pack_kind must be Formal".to_string(),
        ));
    }

    let base_dir = manifest_path
        .parent()
        .ok_or_else(|| ApfscError::Validation("manifest path missing parent".to_string()))?;
    let policy_src = base_dir.join("policy.json");
    if !policy_src.exists() {
        return Err(ApfscError::Missing(
            "formal pack missing policy.json".to_string(),
        ));
    }

    let policy_hash = digest_file(&policy_src)?;
    let manifest = finalize_manifest(raw_manifest, vec![policy_hash])?;

    let mut policy: FormalPolicy =
        serde_json::from_slice(&fs::read(&policy_src).map_err(|e| io_err(&policy_src, e))?)?;
    if policy.manifest_hash.is_empty() {
        policy.manifest_hash = crate::apfsc::artifacts::digest_json(&policy)?;
    }

    let pack_dst = pack_dir(root, PackKind::Formal, &manifest.pack_hash);
    fs::create_dir_all(&pack_dst).map_err(|e| io_err(&pack_dst, e))?;
    write_json_atomic(&pack_dst.join("manifest.json"), &manifest)?;
    copy_file(&policy_src, &pack_dst.join("policy.json"))?;

    let snapshot_hash = read_pointer(root, "active_snapshot").unwrap_or_default();
    let constellation_id = read_pointer(root, "active_constellation").unwrap_or_default();
    let formal_receipt = apply_formal_policy(
        root,
        &manifest.pack_hash,
        policy,
        &snapshot_hash,
        &constellation_id,
        &cfg.protocol.version,
    )?;

    let ingress = IngressReceipt {
        pack_hash: manifest.pack_hash,
        pack_kind: PackKind::Formal,
        validation_checks_passed: vec![
            "policy_schema_valid".to_string(),
            "tightening_only_validation".to_string(),
            "formal_policy_digest_stable".to_string(),
        ],
        ingest_time_unix_s: now_unix_s(),
        protocol_version: cfg.protocol.version.clone(),
        snapshot_included: true,
        family_id: None,
        family_kind: None,
        reality_role: None,
        variant_id: None,
    };

    write_ingress_receipt(root, &ingress)?;
    refresh_active_snapshot(root, cfg)?;

    let rpath = root
        .join("formal_policy")
        .join(&formal_receipt.policy_hash)
        .join("admission_receipt.json");
    write_json_atomic(&rpath, &formal_receipt)?;

    Ok((ingress, formal_receipt))
}
