use rusqlite::{params, Connection, OptionalExtension};

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::control_db::with_busy_retry;

pub const LEASE_ORCHESTRATOR: &str = "orchestrator";
pub const LEASE_JUDGE: &str = "judge";
pub const LEASE_ACTIVATION: &str = "activation";

fn lease_row(conn: &Connection, lease_name: &str) -> Result<Option<(String, i64)>> {
    with_busy_retry(|| {
        conn.query_row(
            "SELECT owner_id, cast(strftime('%s', expires_at) as integer)
             FROM leases WHERE lease_name=?1",
            [lease_name],
            |r| Ok((r.get(0)?, r.get::<_, Option<i64>>(1)?.unwrap_or(0))),
        )
        .optional()
    })
}

fn acquire_single_lease_tx(
    conn: &Connection,
    lease_name: &str,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    let expires_at = (now_s + ttl_s) as i64;
    match lease_row(conn, lease_name)? {
        None => {
            with_busy_retry(|| {
                conn.execute(
                    "INSERT INTO leases(lease_name, owner_id, expires_at)
                     VALUES(?1, ?2, datetime(?3, 'unixepoch'))",
                    params![lease_name, owner_id, expires_at],
                )
            })?;
            Ok(true)
        }
        Some((owner, expiry)) if owner == owner_id || expiry <= now_s as i64 => {
            with_busy_retry(|| {
                conn.execute(
                    "UPDATE leases
                     SET owner_id=?2, expires_at=datetime(?3, 'unixepoch')
                     WHERE lease_name=?1",
                    params![lease_name, owner_id, expires_at],
                )
            })?;
            Ok(true)
        }
        Some(_) => Ok(false),
    }
}

fn judge_held_by_owner(conn: &Connection, owner_id: &str, now_s: u64) -> Result<bool> {
    Ok(matches!(
        lease_row(conn, LEASE_JUDGE)?,
        Some((owner, expiry)) if owner == owner_id && expiry > now_s as i64
    ))
}

pub fn acquire_lease(
    conn: &Connection,
    lease_name: &str,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    with_busy_retry(|| conn.execute_batch("BEGIN IMMEDIATE TRANSACTION"))?;
    let acquired = acquire_single_lease_tx(conn, lease_name, owner_id, ttl_s, now_s)?;
    if acquired {
        with_busy_retry(|| conn.execute_batch("COMMIT"))?;
        Ok(true)
    } else {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        Ok(false)
    }
}

pub fn acquire_orchestrator_lease(
    conn: &Connection,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    acquire_lease(conn, LEASE_ORCHESTRATOR, owner_id, ttl_s, now_s)
}

pub fn acquire_judge_lease(
    conn: &Connection,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    acquire_lease(conn, LEASE_JUDGE, owner_id, ttl_s, now_s)
}

pub fn acquire_activation_lease(
    conn: &Connection,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    with_busy_retry(|| conn.execute_batch("BEGIN IMMEDIATE TRANSACTION"))?;

    // Critical invariant:
    // activation may only be leased if the same owner actively holds judge.
    if !judge_held_by_owner(conn, owner_id, now_s)? {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        return Err(ApfscError::Validation(
            "activation lease requires a live judge lease by the same owner".to_string(),
        ));
    }

    let acquired = acquire_single_lease_tx(conn, LEASE_ACTIVATION, owner_id, ttl_s, now_s)?;
    if acquired {
        with_busy_retry(|| conn.execute_batch("COMMIT"))?;
        Ok(true)
    } else {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        Ok(false)
    }
}

pub fn acquire_epoch_critical_section(
    conn: &Connection,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    with_busy_retry(|| conn.execute_batch("BEGIN IMMEDIATE TRANSACTION"))?;

    if !acquire_single_lease_tx(conn, LEASE_ORCHESTRATOR, owner_id, ttl_s, now_s)?
        || !acquire_single_lease_tx(conn, LEASE_JUDGE, owner_id, ttl_s, now_s)?
    {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        return Ok(false);
    }

    if !judge_held_by_owner(conn, owner_id, now_s)? {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        return Err(ApfscError::Validation(
            "judge lease must be held before activation lease".to_string(),
        ));
    }
    if !acquire_single_lease_tx(conn, LEASE_ACTIVATION, owner_id, ttl_s, now_s)? {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        return Ok(false);
    }

    with_busy_retry(|| conn.execute_batch("COMMIT"))?;
    Ok(true)
}

pub fn renew_lease(
    conn: &Connection,
    lease_name: &str,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    let updated = with_busy_retry(|| {
        conn.execute(
            "UPDATE leases
             SET expires_at=datetime(?3, 'unixepoch')
             WHERE lease_name=?1 AND owner_id=?2",
            params![lease_name, owner_id, (now_s + ttl_s) as i64],
        )
    })?;
    Ok(updated > 0)
}

pub fn renew_epoch_critical_section(
    conn: &Connection,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    with_busy_retry(|| conn.execute_batch("BEGIN IMMEDIATE TRANSACTION"))?;
    let ok = renew_lease(conn, LEASE_ORCHESTRATOR, owner_id, ttl_s, now_s)?
        && renew_lease(conn, LEASE_JUDGE, owner_id, ttl_s, now_s)?
        && renew_lease(conn, LEASE_ACTIVATION, owner_id, ttl_s, now_s)?;
    if ok {
        with_busy_retry(|| conn.execute_batch("COMMIT"))?;
        Ok(true)
    } else {
        let _ = with_busy_retry(|| conn.execute_batch("ROLLBACK"));
        Ok(false)
    }
}

pub fn release_lease(conn: &Connection, lease_name: &str, owner_id: &str) -> Result<()> {
    with_busy_retry(|| {
        conn.execute(
            "DELETE FROM leases WHERE lease_name=?1 AND owner_id=?2",
            params![lease_name, owner_id],
        )
    })?;
    Ok(())
}

pub fn release_epoch_critical_section(conn: &Connection, owner_id: &str) -> Result<()> {
    with_busy_retry(|| conn.execute_batch("BEGIN IMMEDIATE TRANSACTION"))?;
    release_lease(conn, LEASE_ACTIVATION, owner_id)?;
    release_lease(conn, LEASE_JUDGE, owner_id)?;
    release_lease(conn, LEASE_ORCHESTRATOR, owner_id)?;
    with_busy_retry(|| conn.execute_batch("COMMIT"))?;
    Ok(())
}
