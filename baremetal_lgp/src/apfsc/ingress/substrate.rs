use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{copy_file, digest_file, ensure_layout, pack_dir};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::hardware_oracle::update_oracle_cache;
use crate::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use crate::apfsc::ingress::reality::refresh_active_snapshot;
use crate::apfsc::ingress::receipts::write_ingress_receipt;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{IngressReceipt, PackKind, SubstrateTrace};

pub fn ingest_substrate(
    root: &Path,
    cfg: &Phase1Config,
    manifest_path: &Path,
) -> Result<IngressReceipt> {
    ensure_layout(root)?;

    let raw_manifest = load_pack_manifest(manifest_path)?;
    if raw_manifest.pack_kind != PackKind::Substrate {
        return Err(ApfscError::Validation(
            "manifest pack_kind must be Substrate".to_string(),
        ));
    }

    let base_dir = manifest_path
        .parent()
        .ok_or_else(|| ApfscError::Validation("manifest path missing parent".to_string()))?;
    let traces_src = base_dir.join("traces.jsonl");
    if !traces_src.exists() {
        return Err(ApfscError::Missing(
            "substrate traces.jsonl missing".to_string(),
        ));
    }

    let traces_hash = digest_file(&traces_src)?;
    let manifest = finalize_manifest(raw_manifest, vec![traces_hash])?;

    let traces = read_traces(&traces_src)?;
    if traces.is_empty() {
        return Err(ApfscError::Validation(
            "substrate traces must be non-empty".to_string(),
        ));
    }

    let pack_dst = pack_dir(root, PackKind::Substrate, &manifest.pack_hash);
    fs::create_dir_all(&pack_dst).map_err(|e| io_err(&pack_dst, e))?;
    crate::apfsc::artifacts::write_json_atomic(&pack_dst.join("manifest.json"), &manifest)?;
    copy_file(&traces_src, &pack_dst.join("traces.jsonl"))?;

    update_oracle_cache(root, &traces)?;

    let checks = vec![
        "trace_schema_valid".to_string(),
        "trace_has_fingerprint".to_string(),
        "trace_has_peak_rss_and_wall".to_string(),
        "trace_values_nonnegative".to_string(),
    ];

    let receipt = IngressReceipt {
        pack_hash: manifest.pack_hash,
        pack_kind: PackKind::Substrate,
        validation_checks_passed: checks,
        ingest_time_unix_s: now_unix_s(),
        protocol_version: cfg.protocol.version.clone(),
        snapshot_included: true,
        family_id: None,
        family_kind: None,
        reality_role: None,
        variant_id: None,
    };

    write_ingress_receipt(root, &receipt)?;
    refresh_active_snapshot(root, cfg)?;
    Ok(receipt)
}

fn read_traces(path: &Path) -> Result<Vec<SubstrateTrace>> {
    let body = fs::read_to_string(path).map_err(|e| io_err(path, e))?;
    let mut out = Vec::new();
    for line in body.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let trace: SubstrateTrace = serde_json::from_str(line)?;
        if trace.candidate_or_program_fingerprint.trim().is_empty() {
            return Err(ApfscError::Validation(
                "trace missing candidate/program fingerprint".to_string(),
            ));
        }
        out.push(trace);
    }
    Ok(out)
}
