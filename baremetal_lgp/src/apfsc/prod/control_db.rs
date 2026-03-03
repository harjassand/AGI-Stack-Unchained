use std::path::Path;
use std::thread::sleep;
use std::time::Duration;

use rusqlite::{params, Connection, OpenFlags, OptionalExtension};

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::versioning::CONTROL_DB_SCHEMA_VERSION;

pub fn open_control_db(path: &Path) -> Result<Connection> {
    let path_s = path.to_string_lossy();
    let is_uri = path_s.starts_with("file:");
    if !is_uri {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| crate::apfsc::errors::io_err(parent, e))?;
            }
        }
    }
    let conn = if is_uri {
        Connection::open_with_flags(
            path_s.as_ref(),
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_CREATE
                | OpenFlags::SQLITE_OPEN_URI,
        )
        .map_err(|e| ApfscError::Protocol(e.to_string()))?
    } else {
        Connection::open(path).map_err(|e| ApfscError::Protocol(e.to_string()))?
    };
    conn.pragma_update(None, "journal_mode", "WAL")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.pragma_update(None, "synchronous", "NORMAL")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.pragma_update(None, "busy_timeout", 5000i64)
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.busy_timeout(Duration::from_millis(5_000))
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    init_schema(&conn)?;
    ensure_compat_schema(&conn)?;
    verify_schema_checksums(&conn)?;
    Ok(conn)
}

fn is_busy_error(err: &rusqlite::Error) -> bool {
    match err {
        rusqlite::Error::SqliteFailure(code, msg) => {
            matches!(
                code.code,
                rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked
            ) || msg
                .as_deref()
                .map(|m| m.contains("database is locked") || m.contains("database is busy"))
                .unwrap_or(false)
        }
        _ => {
            let s = err.to_string();
            s.contains("database is locked") || s.contains("database is busy")
        }
    }
}

pub fn with_busy_retry<T, F>(mut op: F) -> Result<T>
where
    F: FnMut() -> std::result::Result<T, rusqlite::Error>,
{
    let max_attempts = 3usize;
    let mut backoff_ms = 100u64;
    for attempt in 0..max_attempts {
        match op() {
            Ok(v) => return Ok(v),
            Err(e) if is_busy_error(&e) && attempt + 1 < max_attempts => {
                sleep(Duration::from_millis(backoff_ms));
                backoff_ms = backoff_ms.saturating_mul(2);
            }
            Err(e) => return Err(ApfscError::Protocol(e.to_string())),
        }
    }
    Err(ApfscError::Protocol(
        "sqlite busy retry exhausted without terminal error".to_string(),
    ))
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
          target_epochs INTEGER NOT NULL DEFAULT 0,
          completed_epochs INTEGER NOT NULL DEFAULT 0,
          last_receipt_hash TEXT,
          last_stage TEXT,
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

fn ensure_compat_schema(conn: &Connection) -> Result<()> {
    ensure_column(conn, "runs", "target_epochs", "INTEGER NOT NULL DEFAULT 0")?;
    ensure_column(
        conn,
        "runs",
        "completed_epochs",
        "INTEGER NOT NULL DEFAULT 0",
    )?;
    ensure_column(conn, "runs", "last_receipt_hash", "TEXT")?;
    ensure_column(conn, "runs", "last_stage", "TEXT")?;
    Ok(())
}

fn ensure_column(conn: &Connection, table: &str, column: &str, ddl: &str) -> Result<()> {
    let mut stmt = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let mut rows = stmt
        .query([])
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    while let Some(row) = rows
        .next()
        .map_err(|e| ApfscError::Protocol(e.to_string()))?
    {
        let name: String = row
            .get(1)
            .map_err(|e| ApfscError::Protocol(e.to_string()))?;
        if name == column {
            return Ok(());
        }
    }
    conn.execute(
        &format!("ALTER TABLE {table} ADD COLUMN {column} {ddl}"),
        [],
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;
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
    with_busy_retry(|| {
        let placeholders = (0..states.len()).map(|_| "?").collect::<Vec<_>>().join(",");
        let sql = format!(
            "SELECT job_id, state FROM jobs WHERE state IN ({}) ORDER BY job_id",
            placeholders
        );
        let mut stmt = conn.prepare(&sql)?;
        let mut rows = stmt.query(rusqlite::params_from_iter(states.iter().copied()))?;
        let mut out = Vec::new();
        while let Some(row) = rows.next()? {
            out.push((row.get(0)?, row.get(1)?));
        }
        Ok(out)
    })
}

fn verify_schema_checksums(conn: &Connection) -> Result<()> {
    let mut stmt = conn
        .prepare("SELECT version, checksum FROM schema_migrations ORDER BY version")
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let rows = stmt
        .query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)))
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    for row in rows {
        let (version, checksum) = row.map_err(|e| ApfscError::Protocol(e.to_string()))?;
        let expected = format!("v{}", version);
        if checksum != expected {
            return Err(ApfscError::Validation(format!(
                "schema checksum mismatch for version {}: {} != {}",
                version, checksum, expected
            )));
        }
    }
    Ok(())
}
