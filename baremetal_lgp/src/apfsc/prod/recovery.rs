use std::path::Path;

use rusqlite::{params, Connection};

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::control_db::list_jobs_by_state;
use crate::apfsc::prod::jobs::now_unix_s;
use crate::apfsc::prod::journal::{append_journal, has_commit_marker, JobState, JournalRecord};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct RecoveryReceipt {
    pub recovered_jobs: Vec<String>,
    pub restarted_jobs: Vec<String>,
    pub ts: u64,
}

pub fn startup_recovery(root: &Path, conn: &Connection) -> Result<RecoveryReceipt> {
    let pending = list_jobs_by_state(conn, &["Leased", "Running", "RecoveryPending"])?;
    let mut recovered = Vec::new();
    let mut restarted = Vec::new();

    for (job_id, _state) in pending {
        if has_commit_marker(root, &job_id)? {
            conn.execute(
                "UPDATE jobs SET state='Committed', finished_at=datetime('now') WHERE job_id=?1",
                params![job_id],
            )
            .map_err(|e| ApfscError::Protocol(e.to_string()))?;
            recovered.push(job_id);
        } else {
            conn.execute(
                "UPDATE jobs SET state='RecoveryPending' WHERE job_id=?1",
                params![job_id],
            )
            .map_err(|e| ApfscError::Protocol(e.to_string()))?;
            append_journal(
                root,
                &JournalRecord {
                    job_id: job_id.clone(),
                    run_id: None,
                    idempotency_key: format!("recover:{}", job_id),
                    stage: "startup_recovery".to_string(),
                    target_entity_hash: None,
                    planned_effects: vec!["restart_from_last_safe_stage".to_string()],
                    created_at: now_unix_s(),
                    state: JobState::RecoveryPending,
                    receipt_hash: None,
                    commit_marker: None,
                },
            )?;
            restarted.push(job_id);
        }
    }

    Ok(RecoveryReceipt {
        recovered_jobs: recovered,
        restarted_jobs: restarted,
        ts: now_unix_s(),
    })
}
