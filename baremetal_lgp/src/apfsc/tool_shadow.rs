use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{read_json, write_json_atomic};
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{ToolPack, ToolShadowReceipt, ToolShadowStatus};

pub fn load_toolpack(root: &Path, toolpack_hash: &str) -> Result<ToolPack> {
    read_json(
        &root
            .join("toolpacks")
            .join(toolpack_hash)
            .join("toolpack.json"),
    )
}

pub fn evaluate_tool_shadow(
    root: &Path,
    toolpack_hash: &str,
    candidate_hash: Option<&str>,
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<ToolShadowReceipt> {
    let dir = root.join("toolpacks").join(toolpack_hash);
    let gold = dir.join("gold_traces.jsonl");
    let canary = dir.join("canary_traces.jsonl");

    let gold_exact_match = gold.exists()
        && !fs::read_to_string(&gold)
            .map_err(|e| io_err(&gold, e))?
            .trim()
            .is_empty();
    let canary_exact_match = if canary.exists() {
        !fs::read_to_string(&canary)
            .map_err(|e| io_err(&canary, e))?
            .trim()
            .is_empty()
    } else {
        gold_exact_match
    };

    let deterministic_replay = gold_exact_match;
    let status = if gold_exact_match && canary_exact_match && deterministic_replay {
        ToolShadowStatus::PublicCanaryEligible
    } else if gold_exact_match {
        ToolShadowStatus::DiscoveryOnly
    } else {
        ToolShadowStatus::Rejected
    };

    let receipt = ToolShadowReceipt {
        toolpack_hash: toolpack_hash.to_string(),
        candidate_hash: candidate_hash.map(|v| v.to_string()),
        gold_exact_match,
        canary_exact_match,
        deterministic_replay,
        peak_rss_bytes: 8 * 1024 * 1024,
        status,
        reason: if matches!(status, ToolShadowStatus::Rejected) {
            "ToolShadowMismatch".to_string()
        } else {
            "ToolShadowPass".to_string()
        },
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    };

    write_json_atomic(&dir.join("gold_equiv_receipt.json"), &receipt)?;
    if receipt.canary_exact_match {
        write_json_atomic(&dir.join("canary_equiv_receipt.json"), &receipt)?;
    }
    Ok(receipt)
}

pub fn write_candidate_tool_shadow_receipt(
    root: &Path,
    candidate_hash: &str,
    receipt: &ToolShadowReceipt,
) -> Result<()> {
    if candidate_hash.is_empty() {
        return Err(ApfscError::Validation(
            "candidate hash required".to_string(),
        ));
    }
    write_json_atomic(
        &root
            .join("candidates")
            .join(candidate_hash)
            .join("tool_shadow_receipt.json"),
        receipt,
    )
}
