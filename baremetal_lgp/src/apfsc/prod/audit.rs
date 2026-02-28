use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json};
use crate::apfsc::errors::{ApfscError, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AuditEvent {
    pub seq: u64,
    pub prev_hash: Option<String>,
    pub event_hash: String,
    pub actor: String,
    pub role: String,
    pub command: String,
    pub request_digest: String,
    pub result: String,
    pub ts: u64,
    pub body_redacted_json: serde_json::Value,
}

pub fn audit_path(root: &Path) -> std::path::PathBuf {
    root.join("archives").join("audit_events.jsonl")
}

pub fn append_audit_event(
    root: &Path,
    conn: &Connection,
    mut event: AuditEvent,
) -> Result<AuditEvent> {
    let prev: Option<String> = conn
        .query_row(
            "SELECT event_hash FROM audit_events ORDER BY seq DESC LIMIT 1",
            [],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    event.prev_hash = prev;
    event.event_hash = digest_json(&(
        &event.prev_hash,
        &event.actor,
        &event.role,
        &event.command,
        &event.request_digest,
        &event.result,
        event.ts,
        &event.body_redacted_json,
    ))?;

    conn.execute(
        "INSERT INTO audit_events(prev_hash, event_hash, event_type, actor, ts, body_json)
         VALUES(?1, ?2, ?3, ?4, datetime(?5, 'unixepoch'), ?6)",
        params![
            event.prev_hash,
            event.event_hash,
            event.command,
            event.actor,
            event.ts as i64,
            serde_json::to_string(&event.body_redacted_json)
                .map_err(|e| ApfscError::Protocol(e.to_string()))?
        ],
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    append_jsonl_atomic(&audit_path(root), &event)?;
    Ok(event)
}

pub fn verify_audit_chain(root: &Path) -> Result<()> {
    let events: Vec<AuditEvent> = crate::apfsc::artifacts::read_jsonl(&audit_path(root))?;
    let mut prev: Option<String> = None;
    for ev in events {
        if ev.prev_hash != prev {
            return Err(ApfscError::Validation(
                "audit chain prev_hash mismatch".to_string(),
            ));
        }
        let expect = digest_json(&(
            &ev.prev_hash,
            &ev.actor,
            &ev.role,
            &ev.command,
            &ev.request_digest,
            &ev.result,
            ev.ts,
            &ev.body_redacted_json,
        ))?;
        if ev.event_hash != expect {
            return Err(ApfscError::Validation(
                "audit event hash mismatch".to_string(),
            ));
        }
        prev = Some(ev.event_hash.clone());
    }
    Ok(())
}
