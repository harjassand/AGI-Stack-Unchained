use rusqlite::{params, Connection, OptionalExtension};

use crate::apfsc::errors::{ApfscError, Result};

pub fn acquire_lease(
    conn: &Connection,
    lease_name: &str,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    let expires_at = (now_s + ttl_s) as i64;
    let existing: Option<(String, i64)> = conn
        .query_row(
            "SELECT owner_id, cast(strftime('%s', expires_at) as integer) FROM leases WHERE lease_name=?1",
            [lease_name],
            |r| Ok((r.get(0)?, r.get::<_, Option<i64>>(1)?.unwrap_or(0))),
        )
        .optional()
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;

    match existing {
        None => {
            conn.execute(
                "INSERT INTO leases(lease_name, owner_id, expires_at) VALUES(?1, ?2, datetime(?3, 'unixepoch'))",
                params![lease_name, owner_id, expires_at],
            )
            .map_err(|e| ApfscError::Protocol(e.to_string()))?;
            Ok(true)
        }
        Some((owner, expiry)) if owner == owner_id || expiry <= now_s as i64 => {
            conn.execute(
                "UPDATE leases SET owner_id=?2, expires_at=datetime(?3, 'unixepoch') WHERE lease_name=?1",
                params![lease_name, owner_id, expires_at],
            )
            .map_err(|e| ApfscError::Protocol(e.to_string()))?;
            Ok(true)
        }
        Some(_) => Ok(false),
    }
}

pub fn renew_lease(
    conn: &Connection,
    lease_name: &str,
    owner_id: &str,
    ttl_s: u64,
    now_s: u64,
) -> Result<bool> {
    let updated = conn
        .execute(
            "UPDATE leases SET expires_at=datetime(?3, 'unixepoch') WHERE lease_name=?1 AND owner_id=?2",
            params![lease_name, owner_id, (now_s + ttl_s) as i64],
        )
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    Ok(updated > 0)
}

pub fn release_lease(conn: &Connection, lease_name: &str, owner_id: &str) -> Result<()> {
    conn.execute(
        "DELETE FROM leases WHERE lease_name=?1 AND owner_id=?2",
        params![lease_name, owner_id],
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    Ok(())
}
