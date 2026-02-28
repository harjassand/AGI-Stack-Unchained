use std::path::Path;

use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json, load_snapshot};
use crate::apfsc::challenge_scheduler::{
    build_hidden_challenge_manifest, load_hidden_challenge_manifest_for_snapshot,
    persist_hidden_challenge_manifest,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::{load_active_constellation, load_constellation};
use crate::apfsc::errors::Result;
use crate::apfsc::types::HiddenChallengeManifest;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct ChallengeRetirementReceipt {
    pub snapshot_hash: String,
    pub constellation_id: String,
    pub retired_family_ids: Vec<String>,
    pub replacement_manifest_hash: String,
    pub reason: String,
}

pub fn rotate_hidden_challenges(
    root: &Path,
    cfg: &Phase1Config,
    current_epoch: u64,
) -> Result<HiddenChallengeManifest> {
    let constellation = load_active_constellation(root)?;
    rotate_hidden_challenges_for(
        root,
        cfg,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        current_epoch,
    )
}

pub fn rotate_hidden_challenges_for(
    root: &Path,
    cfg: &Phase1Config,
    snapshot_hash: &str,
    constellation_id: &str,
    current_epoch: u64,
) -> Result<HiddenChallengeManifest> {
    let constellation = load_constellation(root, constellation_id)?;
    if constellation.snapshot_hash != snapshot_hash {
        return Err(crate::apfsc::errors::ApfscError::Validation(format!(
            "constellation '{}' is bound to snapshot '{}' not '{}'",
            constellation_id, constellation.snapshot_hash, snapshot_hash
        )));
    }
    let _ = load_snapshot(root, snapshot_hash)?;
    let path = root
        .join("snapshots")
        .join(&constellation.snapshot_hash)
        .join("hidden_challenge_manifest.json");

    if !path.exists() {
        let built = build_hidden_challenge_manifest(root, cfg, &constellation, current_epoch)?;
        return Ok(built);
    }

    let mut cur = load_hidden_challenge_manifest_for_snapshot(root, &constellation.snapshot_hash)?;
    let mut retired = Vec::new();
    cur.active_hidden_families.retain(|f| {
        let stale = current_epoch > f.retire_after_epoch;
        if stale {
            retired.push(f.family_id.clone());
        }
        !stale
    });
    cur.retired_hidden_families.extend(retired.clone());

    if cur.active_hidden_families.is_empty() {
        cur = build_hidden_challenge_manifest(root, cfg, &constellation, current_epoch)?;
        cur.retired_hidden_families.extend(retired.clone());
    }

    cur.manifest_hash = digest_json(&cur)?;
    persist_hidden_challenge_manifest(root, &cur)?;

    let receipt = ChallengeRetirementReceipt {
        snapshot_hash: cur.snapshot_hash.clone(),
        constellation_id: cur.constellation_id.clone(),
        retired_family_ids: retired,
        replacement_manifest_hash: cur.manifest_hash.clone(),
        reason: "RotationComplete".to_string(),
    };
    append_jsonl_atomic(&root.join("archives/challenge_retirement.jsonl"), &receipt)?;
    append_jsonl_atomic(
        &root
            .join("challenges")
            .join(&cur.manifest_hash)
            .join("retirement_receipts.jsonl"),
        &receipt,
    )?;

    Ok(cur)
}
