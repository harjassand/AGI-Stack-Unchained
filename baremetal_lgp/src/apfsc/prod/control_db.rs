use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::versioning::CONTROL_DB_SCHEMA_VERSION;

pub fn open_control_db(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| crate::apfsc::errors::io_err(parent, e))?;
    }
    let conn = Connection::open(path).map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.pragma_update(None, "journal_mode", "WAL")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    init_schema(&conn)?;
    Ok(conn)
}

pub fn init_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL,
          checksum TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          snapshot_hash TEXT NOT NULL,
          profile TEXT NOT NULL,
          state TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          active_before TEXT,
          active_after TEXT,
          replay_digest TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
          job_id TEXT PRIMARY KEY,
          run_id TEXT,
          kind TEXT NOT NULL,
          entity_hash TEXT,
          state TEXT NOT NULL,
          lease_owner TEXT,
          attempt INTEGER NOT NULL,
          receipt_hash TEXT,
          error_code TEXT,
          started_at TEXT,
          finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS leases (
          lease_name TEXT PRIMARY KEY,
          owner_id TEXT NOT NULL,
          expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS packs (
          pack_hash TEXT PRIMARY KEY,
          pack_kind TEXT NOT NULL,
          admitted_at TEXT NOT NULL,
          receipt_hash TEXT,
          source_id TEXT,
          operator TEXT
        );

        CREATE TABLE IF NOT EXISTS active_pointer_mirror (
          name TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backups (
          backup_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          manifest_hash TEXT NOT NULL,
          verified INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS releases (
          release_id TEXT PRIMARY KEY,
          version TEXT NOT NULL,
          state TEXT NOT NULL,
          manifest_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS baselines (
          suite_name TEXT PRIMARY KEY,
          baseline_hash TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,
          prev_hash TEXT,
          event_hash TEXT NOT NULL,
          event_type TEXT NOT NULL,
          actor TEXT NOT NULL,
          ts TEXT NOT NULL,
          body_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS maintenance_events (
          event_id TEXT PRIMARY KEY,
          kind TEXT NOT NULL,
          state TEXT NOT NULL,
          details_json TEXT,
          created_at TEXT NOT NULL
        );
    ",
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;

    let exists: Option<i64> = conn
        .query_row(
            "SELECT version FROM schema_migrations WHERE version = ?1",
            [CONTROL_DB_SCHEMA_VERSION],
            |r| r.get(0),
        )
        .optional()
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    if exists.is_none() {
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES(?1, datetime('now'), ?2)",
            params![CONTROL_DB_SCHEMA_VERSION, format!("v{}", CONTROL_DB_SCHEMA_VERSION)],
        )
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    }
    Ok(())
}

pub fn control_db_schema_version(conn: &Connection) -> Result<u32> {
    let v: i64 = conn
        .query_row("SELECT max(version) FROM schema_migrations", [], |r| {
            r.get::<_, Option<i64>>(0)
        })
        .map_err(|e| ApfscError::Protocol(e.to_string()))?
        .unwrap_or(0);
    Ok(v as u32)
}

pub fn mirror_pointer(conn: &Connection, name: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO active_pointer_mirror(name, value, updated_at)
         VALUES(?1, ?2, datetime('now'))
         ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
        params![name, value],
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    Ok(())
}

pub fn list_jobs_by_state(conn: &Connection, states: &[&str]) -> Result<Vec<(String, String)>> {
    if states.is_empty() {
        return Ok(Vec::new());
    }
    let placeholders = (0..states.len()).map(|_| "?").collect::<Vec<_>>().join(",");
    let sql = format!(
        "SELECT job_id, state FROM jobs WHERE state IN ({}) ORDER BY job_id",
        placeholders
    );
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let mut rows = stmt
        .query(rusqlite::params_from_iter(states.iter().copied()))
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let mut out = Vec::new();
    while let Some(row) = rows
        .next()
        .map_err(|e| ApfscError::Protocol(e.to_string()))?
    {
        out.push((
            row.get(0)
                .map_err(|e| ApfscError::Protocol(e.to_string()))?,
            row.get(1)
                .map_err(|e| ApfscError::Protocol(e.to_string()))?,
        ));
    }
    Ok(out)
}
