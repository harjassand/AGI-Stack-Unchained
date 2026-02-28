use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, read_jsonl};
use crate::apfsc::errors::Result;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum JobState {
    Planned,
    Leased,
    Running,
    Succeeded,
    Committed,
    Failed,
    Cancelled,
    RecoveryPending,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JournalRecord {
    pub job_id: String,
    pub run_id: Option<String>,
    pub idempotency_key: String,
    pub stage: String,
    pub target_entity_hash: Option<String>,
    pub planned_effects: Vec<String>,
    pub created_at: u64,
    pub state: JobState,
    pub receipt_hash: Option<String>,
    pub commit_marker: Option<String>,
}

pub fn journal_path(root: &Path) -> std::path::PathBuf {
    root.join("control").join("journal.jsonl")
}

pub fn append_journal(root: &Path, record: &JournalRecord) -> Result<()> {
    append_jsonl_atomic(&journal_path(root), record)
}

pub fn load_journal(root: &Path) -> Result<Vec<JournalRecord>> {
    read_jsonl(&journal_path(root))
}

pub fn has_commit_marker(root: &Path, job_id: &str) -> Result<bool> {
    let rows = load_journal(root)?;
    Ok(rows
        .iter()
        .rev()
        .find(|r| r.job_id == job_id)
        .and_then(|r| r.commit_marker.as_ref())
        .is_some())
}

pub fn has_committed_idempotency(root: &Path, idempotency_key: &str) -> Result<bool> {
    let rows = load_journal(root)?;
    Ok(rows.iter().rev().any(|r| {
        r.idempotency_key == idempotency_key
            && (matches!(r.state, JobState::Committed) || r.commit_marker.is_some())
    }))
}
