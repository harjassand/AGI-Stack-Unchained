use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use serde::de::DeserializeOwned;
use serde::Serialize;

use crate::apf3;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{EpochSnapshot, PackKind};

pub fn ensure_layout(root: &Path) -> Result<()> {
    let dirs = [
        root.join("protocol"),
        root.join("snapshots"),
        root.join("packs/reality"),
        root.join("packs/prior"),
        root.join("packs/substrate"),
        root.join("banks"),
        root.join("candidates"),
        root.join("receipts/ingress"),
        root.join("receipts/public"),
        root.join("receipts/holdout"),
        root.join("receipts/judge"),
        root.join("receipts/canary"),
        root.join("receipts/activation"),
        root.join("pointers"),
        root.join("archive"),
        root.join("queues"),
    ];
    for dir in dirs {
        fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    }
    Ok(())
}

pub fn digest_bytes(bytes: &[u8]) -> String {
    blake3::hash(bytes).to_hex().to_string()
}

pub fn digest_reader(mut r: impl Read) -> Result<String> {
    let mut hasher = blake3::Hasher::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = r
            .read(&mut buf)
            .map_err(|e| ApfscError::Protocol(format!("hash read failed: {e}")))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hasher.finalize().to_hex().to_string())
}

pub fn digest_file(path: &Path) -> Result<String> {
    let f = fs::File::open(path).map_err(|e| io_err(path, e))?;
    digest_reader(f)
}

pub fn digest_json<T: Serialize>(value: &T) -> Result<String> {
    let body = serde_json::to_vec(value)?;
    Ok(digest_bytes(&body))
}

pub fn write_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    apf3::write_atomic(path, bytes).map_err(ApfscError::Protocol)
}

pub fn write_json_atomic<T: Serialize + ?Sized>(path: &Path, value: &T) -> Result<()> {
    let body = serde_json::to_vec_pretty(value)?;
    write_bytes_atomic(path, &body)
}

pub fn read_json<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let body = fs::read(path).map_err(|e| io_err(path, e))?;
    Ok(serde_json::from_slice(&body)?)
}

pub fn append_jsonl_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let mut current = if path.exists() {
        fs::read(path).map_err(|e| io_err(path, e))?
    } else {
        Vec::new()
    };
    let line = serde_json::to_vec(value)?;
    current.extend(line);
    current.push(b'\n');
    write_bytes_atomic(path, &current)
}

pub fn read_jsonl<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let body = fs::read_to_string(path).map_err(|e| io_err(path, e))?;
    let mut out = Vec::new();
    for line in body.lines() {
        if line.trim().is_empty() {
            continue;
        }
        out.push(serde_json::from_str::<T>(line)?);
    }
    Ok(out)
}

pub fn write_pointer(root: &Path, name: &str, value: &str) -> Result<()> {
    let path = root.join("pointers").join(name);
    write_bytes_atomic(&path, value.as_bytes())
}

pub fn read_pointer(root: &Path, name: &str) -> Result<String> {
    let path = root.join("pointers").join(name);
    let body = fs::read_to_string(&path).map_err(|e| io_err(&path, e))?;
    Ok(body.trim().to_string())
}

pub fn pack_kind_dir(kind: PackKind) -> &'static str {
    match kind {
        PackKind::Reality => "reality",
        PackKind::Prior => "prior",
        PackKind::Substrate => "substrate",
    }
}

pub fn pack_dir(root: &Path, kind: PackKind, hash: &str) -> PathBuf {
    root.join("packs").join(pack_kind_dir(kind)).join(hash)
}

pub fn candidate_dir(root: &Path, candidate_hash: &str) -> PathBuf {
    root.join("candidates").join(candidate_hash)
}

pub fn receipt_path(root: &Path, lane: &str, name: &str) -> PathBuf {
    root.join("receipts").join(lane).join(name)
}

pub fn store_snapshot(root: &Path, snapshot: &EpochSnapshot) -> Result<()> {
    let path = root
        .join("snapshots")
        .join(format!("{}.json", snapshot.snapshot_hash));
    write_json_atomic(&path, snapshot)
}

pub fn load_snapshot(root: &Path, snapshot_hash: &str) -> Result<EpochSnapshot> {
    let path = root
        .join("snapshots")
        .join(format!("{}.json", snapshot_hash));
    read_json(&path)
}

pub fn list_pack_hashes(root: &Path, kind: PackKind) -> Result<Vec<String>> {
    let dir = root.join("packs").join(pack_kind_dir(kind));
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut names = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| io_err(&dir, e))? {
        let entry = entry.map_err(|e| io_err(&dir, e))?;
        if entry
            .file_type()
            .map_err(|e| io_err(entry.path(), e))?
            .is_dir()
        {
            names.push(entry.file_name().to_string_lossy().to_string());
        }
    }
    names.sort();
    Ok(names)
}

pub fn list_candidate_hashes(root: &Path) -> Result<Vec<String>> {
    let dir = root.join("candidates");
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut names = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| io_err(&dir, e))? {
        let entry = entry.map_err(|e| io_err(&dir, e))?;
        if entry
            .file_type()
            .map_err(|e| io_err(entry.path(), e))?
            .is_dir()
        {
            names.push(entry.file_name().to_string_lossy().to_string());
        }
    }
    names.sort();
    Ok(names)
}

pub fn copy_file(src: &Path, dst: &Path) -> Result<()> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    let bytes = fs::read(src).map_err(|e| io_err(src, e))?;
    write_bytes_atomic(dst, &bytes)
}
