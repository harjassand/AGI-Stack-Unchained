use std::path::Path;

use crate::apfsc::errors::{io_err, Result};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct RetentionPolicy {
    pub receipt_days: u64,
    pub public_trace_days: u64,
    pub candidate_tmp_hours: u64,
    pub tombstone_days: u64,
    pub backup_keep_last: usize,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct RetentionReport {
    pub removed: usize,
}

pub fn apply_retention(
    root: &Path,
    policy: &RetentionPolicy,
    now_s: u64,
) -> Result<RetentionReport> {
    let mut removed = 0usize;
    let cutoff = now_s.saturating_sub(policy.receipt_days * 86400);
    let receipts = root.join("receipts");
    if receipts.exists() {
        removed += prune_older_than(&receipts, cutoff)?;
    }
    Ok(RetentionReport { removed })
}

fn prune_older_than(root: &Path, cutoff_unix_s: u64) -> Result<usize> {
    let mut removed = 0usize;
    for e in std::fs::read_dir(root).map_err(|e| io_err(root, e))? {
        let e = e.map_err(|e| io_err(root, e))?;
        let p = e.path();
        let ty = e.file_type().map_err(|e| io_err(&p, e))?;
        if ty.is_dir() {
            removed += prune_older_than(&p, cutoff_unix_s)?;
            continue;
        }
        let m = std::fs::metadata(&p).map_err(|e| io_err(&p, e))?;
        let mt = m
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(u64::MAX);
        if mt < cutoff_unix_s {
            std::fs::remove_file(&p).map_err(|e| io_err(&p, e))?;
            removed += 1;
        }
    }
    Ok(removed)
}
