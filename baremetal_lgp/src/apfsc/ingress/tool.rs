use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{copy_file, digest_file, ensure_layout, pack_dir, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use crate::apfsc::ingress::reality::refresh_active_snapshot;
use crate::apfsc::ingress::receipts::write_ingress_receipt;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{
    IngressReceipt, PackKind, ToolPack, ToolShadowReceipt, ToolShadowStatus,
};

pub fn ingest_tool(
    root: &Path,
    cfg: &Phase1Config,
    manifest_path: &Path,
) -> Result<(IngressReceipt, ToolShadowReceipt)> {
    ensure_layout(root)?;

    let raw_manifest = load_pack_manifest(manifest_path)?;
    if raw_manifest.pack_kind != PackKind::Tool {
        return Err(ApfscError::Validation(
            "manifest pack_kind must be Tool".to_string(),
        ));
    }

    let base_dir = manifest_path
        .parent()
        .ok_or_else(|| ApfscError::Validation("manifest path missing parent".to_string()))?;
    let toolpack_src = base_dir.join("toolpack.json");
    let gold_src = base_dir.join("gold_traces.jsonl");
    if !toolpack_src.exists() {
        return Err(ApfscError::Missing(
            "tool pack missing toolpack.json".to_string(),
        ));
    }

    let mut payload_hashes = vec![digest_file(&toolpack_src)?];
    if gold_src.exists() {
        payload_hashes.push(digest_file(&gold_src)?);
    }
    let manifest = finalize_manifest(raw_manifest, payload_hashes)?;

    let toolpack: ToolPack =
        serde_json::from_slice(&fs::read(&toolpack_src).map_err(|e| io_err(&toolpack_src, e))?)?;

    let dir = pack_dir(root, PackKind::Tool, &manifest.pack_hash);
    fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    write_json_atomic(&dir.join("manifest.json"), &manifest)?;
    copy_file(&toolpack_src, &dir.join("toolpack.json"))?;
    if gold_src.exists() {
        copy_file(&gold_src, &dir.join("gold_traces.jsonl"))?;
    }

    let tool_dir = root.join("toolpacks").join(&manifest.pack_hash);
    fs::create_dir_all(&tool_dir).map_err(|e| io_err(&tool_dir, e))?;
    write_json_atomic(&tool_dir.join("toolpack.json"), &toolpack)?;
    if gold_src.exists() {
        copy_file(&gold_src, &tool_dir.join("gold_traces.jsonl"))?;
    }

    let ingress = IngressReceipt {
        pack_hash: manifest.pack_hash.clone(),
        pack_kind: PackKind::Tool,
        validation_checks_passed: vec![
            "toolpack_schema_valid".to_string(),
            "quarantined_before_shadow".to_string(),
            "dependency_digests_present".to_string(),
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

    let quarantine = ToolShadowReceipt {
        toolpack_hash: manifest.pack_hash,
        candidate_hash: None,
        gold_exact_match: false,
        canary_exact_match: false,
        deterministic_replay: false,
        peak_rss_bytes: 0,
        status: ToolShadowStatus::Quarantined,
        reason: "Quarantined".to_string(),
        snapshot_hash: crate::apfsc::artifacts::read_pointer(root, "active_snapshot")
            .unwrap_or_default(),
        constellation_id: crate::apfsc::artifacts::read_pointer(root, "active_constellation")
            .unwrap_or_default(),
        protocol_version: cfg.protocol.version.clone(),
    };
    write_json_atomic(&tool_dir.join("admission_receipt.json"), &quarantine)?;

    refresh_active_snapshot(root, cfg)?;
    Ok((ingress, quarantine))
}
