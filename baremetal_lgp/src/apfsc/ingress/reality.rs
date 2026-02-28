use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{
    copy_file, digest_file, ensure_layout, list_pack_hashes, pack_dir, store_snapshot,
    write_json_atomic, write_pointer,
};
use crate::apfsc::bank::{build_bank, persist_bank};
use crate::apfsc::candidate::rebase_active_candidate_to_snapshot;
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use crate::apfsc::ingress::receipts::write_ingress_receipt;
use crate::apfsc::protocol::{materialize_snapshot, now_unix_s};
use crate::apfsc::types::{IngressReceipt, PackKind};

pub fn ingest_reality(
    root: &Path,
    cfg: &Phase1Config,
    manifest_path: &Path,
) -> Result<IngressReceipt> {
    ensure_layout(root)?;

    let raw_manifest = load_pack_manifest(manifest_path)?;
    if raw_manifest.pack_kind != PackKind::Reality {
        return Err(ApfscError::Validation(
            "manifest pack_kind must be Reality".to_string(),
        ));
    }

    let family_id = raw_manifest
        .family_id
        .clone()
        .ok_or_else(|| ApfscError::Validation("reality manifest missing family_id".to_string()))?;

    let payload_src = manifest_path
        .parent()
        .ok_or_else(|| ApfscError::Validation("manifest path missing parent".to_string()))?
        .join("payload.bin");
    if !payload_src.exists() {
        return Err(ApfscError::Missing(format!(
            "payload not found: {}",
            payload_src.display()
        )));
    }

    let payload_hash = digest_file(&payload_src)?;
    let manifest = finalize_manifest(raw_manifest, vec![payload_hash])?;

    validate_split_policy(cfg)?;

    let pack_dst = pack_dir(root, PackKind::Reality, &manifest.pack_hash);
    fs::create_dir_all(&pack_dst).map_err(|e| io_err(&pack_dst, e))?;
    write_json_atomic(&pack_dst.join("manifest.json"), &manifest)?;
    copy_file(&payload_src, &pack_dst.join("payload.bin"))?;

    let payload = fs::read(&payload_src).map_err(|e| io_err(&payload_src, e))?;
    let bank = build_bank(
        &family_id,
        &manifest.pack_hash,
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )?;
    persist_bank(root, &bank)?;

    let checks = vec![
        "payload_exists".to_string(),
        "payload_hash_matches_manifest".to_string(),
        "family_id_present".to_string(),
        "split_policy_legal".to_string(),
        "window_bounds_legal".to_string(),
    ];

    let receipt = IngressReceipt {
        pack_hash: manifest.pack_hash.clone(),
        pack_kind: PackKind::Reality,
        validation_checks_passed: checks,
        ingest_time_unix_s: now_unix_s(),
        protocol_version: cfg.protocol.version.clone(),
        snapshot_included: true,
    };

    write_ingress_receipt(root, &receipt)?;
    refresh_active_snapshot(root, cfg)?;
    Ok(receipt)
}

fn validate_split_policy(cfg: &Phase1Config) -> Result<()> {
    let mut sum = 0.0;
    for (k, v) in &cfg.bank.split_ratios {
        if *v < 0.0 || *v > 1.0 {
            return Err(ApfscError::Validation(format!(
                "split ratio out of range for {k}"
            )));
        }
        sum += v;
    }
    if (sum - 1.0).abs() > 1e-9 {
        return Err(ApfscError::Validation(format!(
            "split ratios must sum to 1.0, got {sum}"
        )));
    }
    if cfg.bank.window_len == 0 || cfg.bank.stride == 0 {
        return Err(ApfscError::Validation(
            "window_len and stride must be > 0".to_string(),
        ));
    }
    Ok(())
}

pub fn refresh_active_snapshot(root: &Path, cfg: &Phase1Config) -> Result<()> {
    let reality = list_pack_hashes(root, PackKind::Reality)?;
    let prior = list_pack_hashes(root, PackKind::Prior)?;
    let substrate = list_pack_hashes(root, PackKind::Substrate)?;

    let snapshot = materialize_snapshot(reality, prior, substrate, cfg.protocol.version.clone());
    store_snapshot(root, &snapshot)?;
    write_pointer(root, "active_snapshot", &snapshot.snapshot_hash)?;
    let _ = rebase_active_candidate_to_snapshot(root, &snapshot.snapshot_hash)?;
    write_json_atomic(&root.join("snapshots/latest.json"), &snapshot)?;
    Ok(())
}
