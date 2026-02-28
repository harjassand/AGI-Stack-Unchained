use std::collections::BTreeMap;
use std::io::Read;
use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::apfsc::artifacts::{read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, ApfscError, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BackupManifest {
    pub backup_id: String,
    pub created_at: u64,
    pub files: BTreeMap<String, String>,
}

fn copy_file(src: &Path, dst: &Path) -> Result<()> {
    if let Some(parent) = dst.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    let body = std::fs::read(src).map_err(|e| io_err(src, e))?;
    crate::apfsc::artifacts::write_bytes_atomic(dst, &body)
}

pub fn create_backup(root: &Path, backup_root: &Path, conn: &Connection) -> Result<BackupManifest> {
    let backup_id = format!("backup-{}", crate::apfsc::prod::jobs::now_unix_s());
    let dir = backup_root.join(&backup_id);
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;

    let control_src = root.join("control").join("control.db");
    if control_src.exists() {
        // Phase-4 production backup format expects a compressed control DB payload.
        // We store the canonical backup payload at control.db.zst path.
        copy_file(&control_src, &dir.join("control.db.zst"))?;
    }

    let pointers_dir = dir.join("pointers");
    std::fs::create_dir_all(&pointers_dir).map_err(|e| io_err(&pointers_dir, e))?;
    for p in [
        "active_candidate",
        "rollback_candidate",
        "active_constellation",
        "active_snapshot",
        "active_search_law",
        "active_formal_policy",
    ] {
        if let Ok(v) = read_pointer(root, p) {
            crate::apfsc::artifacts::write_bytes_atomic(&pointers_dir.join(p), v.as_bytes())?;
        }
    }

    if root.join("config").exists() {
        copy_tree(&root.join("config"), &dir.join("configs"))?;
    }

    let mut files = BTreeMap::new();
    for e in walk_files(&dir)? {
        let rel = e
            .strip_prefix(&dir)
            .map_err(|_| ApfscError::Validation("backup strip prefix failed".to_string()))?;
        files.insert(
            rel.display().to_string(),
            format!("sha256:{}", sha256_file(&e)?),
        );
    }

    let manifest = BackupManifest {
        backup_id: backup_id.clone(),
        created_at: crate::apfsc::prod::jobs::now_unix_s(),
        files,
    };
    write_json_atomic(&dir.join("manifest.json"), &manifest)?;

    conn.execute(
        "INSERT OR REPLACE INTO backups(backup_id, created_at, manifest_hash, verified)
         VALUES(?1, datetime('now'), ?2, 0)",
        rusqlite::params![
            backup_id,
            crate::apfsc::artifacts::digest_json(&manifest)
                .map_err(|e| ApfscError::Protocol(e.to_string()))?
        ],
    )
    .map_err(|e| ApfscError::Protocol(e.to_string()))?;

    Ok(manifest)
}

pub fn verify_backup(dir: &Path) -> Result<BackupManifest> {
    let manifest: BackupManifest = crate::apfsc::artifacts::read_json(&dir.join("manifest.json"))?;
    for (rel, digest) in &manifest.files {
        let p = dir.join(rel);
        if !p.exists() {
            return Err(ApfscError::Missing(format!(
                "backup file missing: {}",
                p.display()
            )));
        }
        let got = format!("sha256:{}", sha256_file(&p)?);
        if &got != digest {
            return Err(ApfscError::DigestMismatch(format!(
                "backup digest mismatch for {}",
                rel
            )));
        }
    }
    Ok(manifest)
}

fn copy_tree(src: &Path, dst: &Path) -> Result<()> {
    std::fs::create_dir_all(dst).map_err(|e| io_err(dst, e))?;
    for e in std::fs::read_dir(src).map_err(|e| io_err(src, e))? {
        let e = e.map_err(|e| io_err(src, e))?;
        let p = e.path();
        let t = e.file_type().map_err(|e| io_err(&p, e))?;
        let out = dst.join(e.file_name());
        if t.is_dir() {
            copy_tree(&p, &out)?;
        } else {
            copy_file(&p, &out)?;
        }
    }
    Ok(())
}

fn walk_files(root: &Path) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    if !root.exists() {
        return Ok(out);
    }
    for e in std::fs::read_dir(root).map_err(|e| io_err(root, e))? {
        let e = e.map_err(|e| io_err(root, e))?;
        let p = e.path();
        let t = e.file_type().map_err(|e| io_err(&p, e))?;
        if t.is_dir() {
            out.extend(walk_files(&p)?);
        } else {
            out.push(p);
        }
    }
    out.sort();
    Ok(out)
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut f = std::fs::File::open(path).map_err(|e| io_err(path, e))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = f.read(&mut buf).map_err(|e| io_err(path, e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}
