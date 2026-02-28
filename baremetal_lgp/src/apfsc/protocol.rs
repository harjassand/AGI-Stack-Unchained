use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{digest_json, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::types::EpochSnapshot;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProtocolVersionDoc {
    pub protocol_version: String,
    pub initialized_unix_s: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JudgePolicyDoc {
    pub public_min_delta_bits: f64,
    pub holdout_min_delta_bits: f64,
    pub anchor_max_regress_bits: f64,
    pub mini_transfer_min_delta_bits: f64,
    pub require_canary_for_a: bool,
}

pub fn now_unix_s() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn initialize_protocol_files(root: &Path, cfg: &Phase1Config) -> Result<()> {
    let protocol_dir = root.join("protocol");
    std::fs::create_dir_all(&protocol_dir)
        .map_err(|e| crate::apfsc::errors::io_err(&protocol_dir, e))?;

    let version = ProtocolVersionDoc {
        protocol_version: cfg.protocol.version.clone(),
        initialized_unix_s: now_unix_s(),
    };
    write_json_atomic(&protocol_dir.join("version.json"), &version)?;

    let policy = JudgePolicyDoc {
        public_min_delta_bits: cfg.judge.public_min_delta_bits,
        holdout_min_delta_bits: cfg.judge.holdout_min_delta_bits,
        anchor_max_regress_bits: cfg.judge.anchor_max_regress_bits,
        mini_transfer_min_delta_bits: cfg.judge.mini_transfer_min_delta_bits,
        require_canary_for_a: cfg.judge.require_canary_for_a,
    };
    write_json_atomic(&protocol_dir.join("judge_policy.json"), &policy)?;
    Ok(())
}

pub fn materialize_snapshot(
    reality_roots: Vec<String>,
    prior_roots: Vec<String>,
    substrate_roots: Vec<String>,
    formal_roots: Vec<String>,
    tool_roots: Vec<String>,
    protocol_version: String,
) -> EpochSnapshot {
    let mut snap = EpochSnapshot {
        snapshot_hash: String::new(),
        reality_roots,
        prior_roots,
        substrate_roots,
        formal_roots,
        tool_roots,
        protocol_version,
    };
    snap.snapshot_hash = digest_json(&snap).unwrap_or_else(|_| "snapshot_digest_error".to_string());
    snap
}
