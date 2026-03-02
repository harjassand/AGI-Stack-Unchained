use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::path::{Path, PathBuf};

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::apfsc::artifacts::{read_json, read_pointer, write_json_atomic};
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{CandidateManifest, EpochSnapshot, PackKind};

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
    let tmp_dir = backup_root.join(format!(".inflight-{}", backup_id));
    let final_dir = backup_root.join(&backup_id);
    std::fs::create_dir_all(backup_root).map_err(|e| io_err(backup_root, e))?;
    if tmp_dir.exists() {
        std::fs::remove_dir_all(&tmp_dir).map_err(|e| io_err(&tmp_dir, e))?;
    }
    std::fs::create_dir_all(&tmp_dir).map_err(|e| io_err(&tmp_dir, e))?;

    let control_snapshot = tmp_dir.join("control").join("control.db");
    snapshot_control_db(conn, &control_snapshot)?;
    // Compatibility shim for older tooling/tests expecting backup-root control snapshot.
    copy_file(&control_snapshot, &tmp_dir.join("control.db.zst"))?;
    copy_pointer_files(root, &tmp_dir)?;
    copy_required_chunks(root, &tmp_dir)?;

    let mut files = BTreeMap::new();
    for e in walk_files(&tmp_dir)? {
        let rel = e
            .strip_prefix(&tmp_dir)
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
    write_json_atomic(&tmp_dir.join("manifest.json"), &manifest)?;

    if final_dir.exists() {
        return Err(ApfscError::Validation(format!(
            "backup target already exists: {}",
            final_dir.display()
        )));
    }
    std::fs::rename(&tmp_dir, &final_dir).map_err(|e| io_err(&tmp_dir, e))?;

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
    let manifest: BackupManifest = read_json(&dir.join("manifest.json"))?;
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

fn snapshot_control_db(conn: &Connection, dst: &Path) -> Result<()> {
    if let Some(parent) = dst.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    if dst.exists() {
        std::fs::remove_file(dst).map_err(|e| io_err(dst, e))?;
    }
    let escaped = dst
        .display()
        .to_string()
        .replace('\'', "''")
        .replace('\\', "\\\\");
    conn.execute_batch(&format!("VACUUM main INTO '{escaped}'"))
        .map_err(|e| ApfscError::Protocol(format!("control db snapshot failed: {e}")))?;
    Ok(())
}

fn copy_pointer_files(root: &Path, backup_dir: &Path) -> Result<()> {
    let pointer_root = root.join("pointers");
    let out = backup_dir.join("pointers");
    std::fs::create_dir_all(&out).map_err(|e| io_err(&out, e))?;
    if !pointer_root.exists() {
        return Ok(());
    }
    for e in std::fs::read_dir(&pointer_root).map_err(|e| io_err(&pointer_root, e))? {
        let e = e.map_err(|e| io_err(&pointer_root, e))?;
        let p = e.path();
        if !e.file_type().map_err(|e| io_err(&p, e))?.is_file() {
            continue;
        }
        copy_file(&p, &out.join(e.file_name()))?;
    }
    Ok(())
}

fn copy_required_chunks(root: &Path, backup_dir: &Path) -> Result<()> {
    let mut copied_dirs = BTreeSet::<PathBuf>::new();
    let mut copied_files = BTreeSet::<PathBuf>::new();

    let mut candidate_roots = Vec::<String>::new();
    for p in ["active_candidate", "rollback_candidate"] {
        if let Ok(v) = read_pointer(root, p) {
            candidate_roots.push(v);
        }
    }

    let mut all_candidates = BTreeSet::<String>::new();
    for c in candidate_roots {
        collect_candidate_closure(root, &c, &mut all_candidates)?;
    }
    for cand in all_candidates {
        let src = root.join("candidates").join(&cand);
        if src.exists() {
            copy_tree_once(&src, &backup_dir.join("candidates").join(&cand), &mut copied_dirs)?;
        }
    }

    if let Ok(snapshot_hash) = read_pointer(root, "active_snapshot") {
        let snap_path = root
            .join("snapshots")
            .join(format!("{}.json", snapshot_hash));
        if snap_path.exists() {
            copy_file_once(
                &snap_path,
                &backup_dir
                    .join("snapshots")
                    .join(format!("{}.json", snapshot_hash)),
                &mut copied_files,
            )?;
            let snapshot: EpochSnapshot = read_json(&snap_path)?;
            for h in snapshot.reality_roots {
                copy_pack_if_exists(root, backup_dir, PackKind::Reality, &h, &mut copied_dirs)?;
            }
            for h in snapshot.prior_roots {
                copy_pack_if_exists(root, backup_dir, PackKind::Prior, &h, &mut copied_dirs)?;
            }
            for h in snapshot.substrate_roots {
                copy_pack_if_exists(root, backup_dir, PackKind::Substrate, &h, &mut copied_dirs)?;
            }
            for h in snapshot.formal_roots {
                copy_pack_if_exists(root, backup_dir, PackKind::Formal, &h, &mut copied_dirs)?;
            }
            for h in snapshot.tool_roots {
                copy_pack_if_exists(root, backup_dir, PackKind::Tool, &h, &mut copied_dirs)?;
            }
        }
    }

    if let Ok(constellation_id) = read_pointer(root, "active_constellation") {
        let src = root
            .join("constellations")
            .join(format!("{}.json", constellation_id));
        if src.exists() {
            copy_file_once(
                &src,
                &backup_dir
                    .join("constellations")
                    .join(format!("{}.json", constellation_id)),
                &mut copied_files,
            )?;
        }
    }
    if let Ok(search_law) = read_pointer(root, "active_search_law") {
        let src = root.join("search_laws").join(format!("{}.json", search_law));
        if src.exists() {
            copy_file_once(
                &src,
                &backup_dir
                    .join("search_laws")
                    .join(format!("{}.json", search_law)),
                &mut copied_files,
            )?;
        }
    }
    if let Ok(formal_policy) = read_pointer(root, "active_formal_policy") {
        let src = root
            .join("formal_policy")
            .join(format!("{}.json", formal_policy));
        if src.exists() {
            copy_file_once(
                &src,
                &backup_dir
                    .join("formal_policy")
                    .join(format!("{}.json", formal_policy)),
                &mut copied_files,
            )?;
        }
    }
    Ok(())
}

fn collect_candidate_closure(root: &Path, hash: &str, out: &mut BTreeSet<String>) -> Result<()> {
    if !out.insert(hash.to_string()) {
        return Ok(());
    }
    let manifest_path = root.join("candidates").join(hash).join("manifest.json");
    if !manifest_path.exists() {
        return Ok(());
    }
    let manifest: CandidateManifest = read_json(&manifest_path)?;
    for parent in manifest.parent_hashes {
        collect_candidate_closure(root, &parent, out)?;
    }
    Ok(())
}

fn copy_pack_if_exists(
    root: &Path,
    backup_dir: &Path,
    kind: PackKind,
    hash: &str,
    copied_dirs: &mut BTreeSet<PathBuf>,
) -> Result<()> {
    let kind_dir = crate::apfsc::artifacts::pack_kind_dir(kind);
    let src = root
        .join("packs")
        .join(kind_dir)
        .join(hash);
    if src.exists() {
        copy_tree_once(
            &src,
            &backup_dir
                .join("packs")
                .join(kind_dir)
                .join(hash),
            copied_dirs,
        )?;
    }
    Ok(())
}

fn copy_tree_once(src: &Path, dst: &Path, copied: &mut BTreeSet<PathBuf>) -> Result<()> {
    let canonical = src.to_path_buf();
    if !copied.insert(canonical) {
        return Ok(());
    }
    copy_tree(src, dst)
}

fn copy_file_once(src: &Path, dst: &Path, copied: &mut BTreeSet<PathBuf>) -> Result<()> {
    let canonical = src.to_path_buf();
    if !copied.insert(canonical) {
        return Ok(());
    }
    copy_file(src, dst)
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
