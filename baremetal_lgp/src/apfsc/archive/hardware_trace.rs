use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::types::{ByteScoreReceipt, CanaryBatchReport, JudgeBatchReport};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HardwareTraceRow {
    pub time_unix_s: u64,
    pub phase: String,
    pub candidate_hash: String,
    pub peak_rss_bytes: u64,
    pub wall_ms: u64,
    pub total_bits: Option<f64>,
}

pub fn append_public(root: &Path, receipt: &ByteScoreReceipt) -> Result<()> {
    let row = HardwareTraceRow {
        time_unix_s: now_unix_s(),
        phase: "public".to_string(),
        candidate_hash: receipt.candidate_hash.clone(),
        peak_rss_bytes: receipt.peak_rss_bytes,
        wall_ms: receipt.wall_ms,
        total_bits: Some(receipt.total_bits),
    };
    append_jsonl_atomic(&root.join("archive/hardware_trace.jsonl"), &row)
}

pub fn append_epoch(
    root: &Path,
    public_receipts: &[ByteScoreReceipt],
    judge_report: &JudgeBatchReport,
    canary_report: &CanaryBatchReport,
) -> Result<()> {
    for p in public_receipts {
        append_public(root, p)?;
    }
    for r in &judge_report.receipts {
        let row = HardwareTraceRow {
            time_unix_s: now_unix_s(),
            phase: "judge".to_string(),
            candidate_hash: r.candidate_hash.clone(),
            peak_rss_bytes: 0,
            wall_ms: 0,
            total_bits: Some(r.holdout_delta_bits),
        };
        append_jsonl_atomic(&root.join("archive/hardware_trace.jsonl"), &row)?;
    }
    for c in &canary_report.evaluated {
        let row = HardwareTraceRow {
            time_unix_s: now_unix_s(),
            phase: "canary".to_string(),
            candidate_hash: c.clone(),
            peak_rss_bytes: 0,
            wall_ms: 0,
            total_bits: None,
        };
        append_jsonl_atomic(&root.join("archive/hardware_trace.jsonl"), &row)?;
    }
    Ok(())
}
