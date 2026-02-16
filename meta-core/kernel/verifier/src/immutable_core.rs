use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use crate::canonical_json::{canonical_bytes, canonicalize_bytes, parse_gcj, GcjValue};
use crate::hash::sha256_hex;

const LOCK_SCHEMA: &str = "immutable_core_lock_v1";
const RECEIPT_SCHEMA: &str = "immutable_core_receipt_v1";
const SPEC_VERSION: &str = "v2_3";
const LOCK_HEAD_PLACEHOLDER: &str = "__SELF__";

#[derive(Clone, Debug)]
struct FileEntry {
    relpath: String,
    sha256: String,
    bytes: u64,
}

#[derive(Clone, Debug)]
struct Lock {
    schema: String,
    spec_version: String,
    lock_id: String,
    core_id: String,
    source_roots: Vec<String>,
    excludes: Vec<String>,
    files: Vec<FileEntry>,
    core_tree_hash_v1: String,
    lock_head_hash: String,
}

#[derive(Clone, Debug)]
pub struct Mismatch {
    relpath: String,
    expected_sha256: String,
    observed_sha256: String,
}

#[derive(Clone, Debug)]
pub struct ImmutableCoreReceipt {
    pub schema: String,
    pub spec_version: String,
    pub verdict: String,
    pub reason: String,
    pub repo_root_sha256: String,
    pub lock_path: String,
    pub lock_id: String,
    pub core_id_expected: String,
    pub core_id_observed: String,
    pub mismatches: Vec<Mismatch>,
    pub receipt_head_hash: String,
}

impl ImmutableCoreReceipt {
    pub fn canonical_bytes(&self) -> Vec<u8> {
        canonical_bytes(&self.to_gcj())
    }

    fn to_gcj(&self) -> GcjValue {
        let mut map = BTreeMap::new();
        map.insert("schema".to_string(), GcjValue::Str(self.schema.clone()));
        map.insert("spec_version".to_string(), GcjValue::Str(self.spec_version.clone()));
        map.insert("verdict".to_string(), GcjValue::Str(self.verdict.clone()));
        map.insert("reason".to_string(), GcjValue::Str(self.reason.clone()));
        map.insert("repo_root_sha256".to_string(), GcjValue::Str(self.repo_root_sha256.clone()));
        map.insert("lock_path".to_string(), GcjValue::Str(self.lock_path.clone()));
        map.insert("lock_id".to_string(), GcjValue::Str(self.lock_id.clone()));
        map.insert("core_id_expected".to_string(), GcjValue::Str(self.core_id_expected.clone()));
        map.insert("core_id_observed".to_string(), GcjValue::Str(self.core_id_observed.clone()));
        let mismatches = self
            .mismatches
            .iter()
            .map(|row| {
                let mut obj = BTreeMap::new();
                obj.insert("relpath".to_string(), GcjValue::Str(row.relpath.clone()));
                obj.insert("expected_sha256".to_string(), GcjValue::Str(row.expected_sha256.clone()));
                obj.insert("observed_sha256".to_string(), GcjValue::Str(row.observed_sha256.clone()));
                GcjValue::Object(obj)
            })
            .collect();
        map.insert("mismatches".to_string(), GcjValue::Array(mismatches));
        map.insert("receipt_head_hash".to_string(), GcjValue::Str(self.receipt_head_hash.clone()));
        GcjValue::Object(map)
    }
}

fn sha256_prefixed(bytes: &[u8]) -> String {
    format!("sha256:{}", sha256_hex(bytes))
}

fn receipt_invalid(reason: &str, lock_path: &str, repo_root_sha256: &str) -> ImmutableCoreReceipt {
    let mut receipt = ImmutableCoreReceipt {
        schema: RECEIPT_SCHEMA.to_string(),
        spec_version: SPEC_VERSION.to_string(),
        verdict: "INVALID".to_string(),
        reason: reason.to_string(),
        repo_root_sha256: repo_root_sha256.to_string(),
        lock_path: lock_path.to_string(),
        lock_id: "".to_string(),
        core_id_expected: "".to_string(),
        core_id_observed: "".to_string(),
        mismatches: Vec::new(),
        receipt_head_hash: "".to_string(),
    };
    receipt.receipt_head_hash = compute_receipt_head_hash(&receipt);
    receipt
}

fn compute_receipt_head_hash(receipt: &ImmutableCoreReceipt) -> String {
    let mut map = BTreeMap::new();
    map.insert("schema".to_string(), GcjValue::Str(receipt.schema.clone()));
    map.insert("spec_version".to_string(), GcjValue::Str(receipt.spec_version.clone()));
    map.insert("verdict".to_string(), GcjValue::Str(receipt.verdict.clone()));
    map.insert("reason".to_string(), GcjValue::Str(receipt.reason.clone()));
    map.insert(
        "repo_root_sha256".to_string(),
        GcjValue::Str(receipt.repo_root_sha256.clone()),
    );
    map.insert("lock_path".to_string(), GcjValue::Str(receipt.lock_path.clone()));
    map.insert("lock_id".to_string(), GcjValue::Str(receipt.lock_id.clone()));
    map.insert(
        "core_id_expected".to_string(),
        GcjValue::Str(receipt.core_id_expected.clone()),
    );
    map.insert(
        "core_id_observed".to_string(),
        GcjValue::Str(receipt.core_id_observed.clone()),
    );
    let mismatches = receipt
        .mismatches
        .iter()
        .map(|row| {
            let mut obj = BTreeMap::new();
            obj.insert("relpath".to_string(), GcjValue::Str(row.relpath.clone()));
            obj.insert("expected_sha256".to_string(), GcjValue::Str(row.expected_sha256.clone()));
            obj.insert("observed_sha256".to_string(), GcjValue::Str(row.observed_sha256.clone()));
            GcjValue::Object(obj)
        })
        .collect();
    map.insert("mismatches".to_string(), GcjValue::Array(mismatches));
    let canonical = canonical_bytes(&GcjValue::Object(map));
    sha256_prefixed(&canonical)
}

fn parse_string(value: &GcjValue) -> Result<String, String> {
    match value {
        GcjValue::Str(s) => Ok(s.clone()),
        _ => Err("expected string".to_string()),
    }
}

fn parse_u64(value: &GcjValue) -> Result<u64, String> {
    match value {
        GcjValue::Int(i) if *i >= 0 => Ok(*i as u64),
        _ => Err("expected integer".to_string()),
    }
}

fn parse_string_array(value: &GcjValue) -> Result<Vec<String>, String> {
    match value {
        GcjValue::Array(items) => {
            let mut out = Vec::new();
            for item in items {
                out.push(parse_string(item)?);
            }
            Ok(out)
        }
        _ => Err("expected array".to_string()),
    }
}

fn parse_lock(value: &GcjValue) -> Result<Lock, String> {
    let GcjValue::Object(map) = value else {
        return Err("expected object".to_string());
    };

    let schema = parse_string(map.get("schema").ok_or("schema missing")?)?;
    let spec_version = parse_string(map.get("spec_version").ok_or("spec_version missing")?)?;
    let lock_id = parse_string(map.get("lock_id").ok_or("lock_id missing")?)?;
    let core_id = parse_string(map.get("core_id").ok_or("core_id missing")?)?;
    let source_roots = parse_string_array(map.get("source_roots").ok_or("source_roots missing")?)?;
    let excludes = parse_string_array(map.get("excludes").ok_or("excludes missing")?)?;
    let core_tree_hash_v1 = parse_string(map.get("core_tree_hash_v1").ok_or("core_tree_hash_v1 missing")?)?;
    let lock_head_hash = parse_string(map.get("lock_head_hash").ok_or("lock_head_hash missing")?)?;

    let files_value = map.get("files").ok_or("files missing")?;
    let files = match files_value {
        GcjValue::Array(items) => {
            let mut out = Vec::new();
            for item in items {
                let GcjValue::Object(entry_map) = item else {
                    return Err("file entry invalid".to_string());
                };
                let relpath = parse_string(entry_map.get("relpath").ok_or("relpath missing")?)?;
                let sha256 = parse_string(entry_map.get("sha256").ok_or("sha256 missing")?)?;
                let bytes = parse_u64(entry_map.get("bytes").ok_or("bytes missing")?)?;
                out.push(FileEntry { relpath, sha256, bytes });
            }
            out
        }
        _ => return Err("files invalid".to_string()),
    };

    Ok(Lock {
        schema,
        spec_version,
        lock_id,
        core_id,
        source_roots,
        excludes,
        files,
        core_tree_hash_v1,
        lock_head_hash,
    })
}

fn file_entries_to_gcj(files: &[FileEntry]) -> GcjValue {
    let mut entries = Vec::new();
    for entry in files {
        let mut obj = BTreeMap::new();
        obj.insert("relpath".to_string(), GcjValue::Str(entry.relpath.clone()));
        obj.insert("sha256".to_string(), GcjValue::Str(entry.sha256.clone()));
        obj.insert("bytes".to_string(), GcjValue::Int(entry.bytes as i64));
        entries.push(GcjValue::Object(obj));
    }
    GcjValue::Array(entries)
}

fn compute_core_tree_hash(files: &[FileEntry]) -> String {
    let mut sorted = files.to_vec();
    sorted.sort_by(|a, b| a.relpath.cmp(&b.relpath));
    let mut obj = BTreeMap::new();
    obj.insert("files".to_string(), file_entries_to_gcj(&sorted));
    let canonical = canonical_bytes(&GcjValue::Object(obj));
    sha256_prefixed(&canonical)
}

fn compute_lock_id(lock: &Lock) -> String {
    let mut obj = BTreeMap::new();
    obj.insert("schema".to_string(), GcjValue::Str(lock.schema.clone()));
    obj.insert("spec_version".to_string(), GcjValue::Str(lock.spec_version.clone()));
    obj.insert("core_id".to_string(), GcjValue::Str(lock.core_id.clone()));
    obj.insert("source_roots".to_string(), GcjValue::Array(lock.source_roots.iter().cloned().map(GcjValue::Str).collect()));
    obj.insert("excludes".to_string(), GcjValue::Array(lock.excludes.iter().cloned().map(GcjValue::Str).collect()));
    obj.insert("files".to_string(), file_entries_to_gcj(&lock.files));
    obj.insert("core_tree_hash_v1".to_string(), GcjValue::Str(lock.core_tree_hash_v1.clone()));
    obj.insert("lock_head_hash".to_string(), GcjValue::Str(LOCK_HEAD_PLACEHOLDER.to_string()));
    let canonical = canonical_bytes(&GcjValue::Object(obj));
    sha256_prefixed(&canonical)
}

fn compute_lock_head_hash(lock: &Lock) -> String {
    let mut obj = BTreeMap::new();
    obj.insert("schema".to_string(), GcjValue::Str(lock.schema.clone()));
    obj.insert("spec_version".to_string(), GcjValue::Str(lock.spec_version.clone()));
    obj.insert("lock_id".to_string(), GcjValue::Str(lock.lock_id.clone()));
    obj.insert("core_id".to_string(), GcjValue::Str(lock.core_id.clone()));
    obj.insert("source_roots".to_string(), GcjValue::Array(lock.source_roots.iter().cloned().map(GcjValue::Str).collect()));
    obj.insert("excludes".to_string(), GcjValue::Array(lock.excludes.iter().cloned().map(GcjValue::Str).collect()));
    obj.insert("files".to_string(), file_entries_to_gcj(&lock.files));
    obj.insert("core_tree_hash_v1".to_string(), GcjValue::Str(lock.core_tree_hash_v1.clone()));
    let canonical = canonical_bytes(&GcjValue::Object(obj));
    sha256_prefixed(&canonical)
}

fn is_excluded(relpath: &str, excludes: &[String], lock_relpath: &str) -> bool {
    if relpath == lock_relpath {
        return true;
    }
    for ex in excludes {
        if ex == "*.pyc" && relpath.ends_with(".pyc") {
            return true;
        }
        if !ex.ends_with('/') && ex != "*.pyc" {
            if relpath == ex || relpath.ends_with(&format!("/{ex}")) {
                return true;
            }
        }
        if let Some(prefix) = ex.strip_suffix('/') {
            if relpath == prefix || relpath.starts_with(&format!("{prefix}/")) {
                return true;
            }
            if relpath.contains(&format!("/{prefix}/")) {
                return true;
            }
        }
    }
    false
}

fn collect_files(repo_root: &Path, source_roots: &[String], excludes: &[String], lock_relpath: &str) -> Result<Vec<FileEntry>, String> {
    let mut entries: Vec<FileEntry> = Vec::new();
    for root in source_roots {
        let root_path = repo_root.join(root);
        if !root_path.exists() {
            return Err("missing source root".to_string());
        }
        walk_dir(repo_root, &root_path, excludes, lock_relpath, &mut entries)?;
    }
    entries.sort_by(|a, b| a.relpath.cmp(&b.relpath));
    Ok(entries)
}

fn walk_dir(repo_root: &Path, dir: &Path, excludes: &[String], lock_relpath: &str, entries: &mut Vec<FileEntry>) -> Result<(), String> {
    let read_dir = fs::read_dir(dir).map_err(|_| "read_dir failed".to_string())?;
    for entry in read_dir {
        let entry = entry.map_err(|_| "read_dir entry failed".to_string())?;
        let path = entry.path();
        let relpath = path
            .strip_prefix(repo_root)
            .map_err(|_| "strip_prefix failed".to_string())?
            .to_string_lossy()
            .replace('\\', "/");
        if is_excluded(&relpath, excludes, lock_relpath) {
            continue;
        }
        if path.is_dir() {
            walk_dir(repo_root, &path, excludes, lock_relpath, entries)?;
            continue;
        }
        let data = fs::read(&path).map_err(|_| "read file failed".to_string())?;
        let sha = sha256_prefixed(&data);
        let bytes = data.len() as u64;
        entries.push(FileEntry { relpath, sha256: sha, bytes });
    }
    Ok(())
}

fn compare_files(expected: &[FileEntry], observed: &[FileEntry]) -> Vec<Mismatch> {
    let mut mismatches = Vec::new();
    let mut exp_map = BTreeMap::new();
    for entry in expected {
        exp_map.insert(entry.relpath.clone(), entry.sha256.clone());
    }
    let mut obs_map = BTreeMap::new();
    for entry in observed {
        obs_map.insert(entry.relpath.clone(), entry.sha256.clone());
    }
    for (rel, exp_sha) in exp_map.iter() {
        match obs_map.get(rel) {
            Some(obs_sha) => {
                if obs_sha != exp_sha {
                    mismatches.push(Mismatch {
                        relpath: rel.clone(),
                        expected_sha256: exp_sha.clone(),
                        observed_sha256: obs_sha.clone(),
                    });
                }
            }
            None => mismatches.push(Mismatch {
                relpath: rel.clone(),
                expected_sha256: exp_sha.clone(),
                observed_sha256: "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            }),
        }
    }
    for (rel, obs_sha) in obs_map.iter() {
        if !exp_map.contains_key(rel) {
            mismatches.push(Mismatch {
                relpath: rel.clone(),
                expected_sha256: "sha256:0000000000000000000000000000000000000000000000000000000000000000".to_string(),
                observed_sha256: obs_sha.clone(),
            });
        }
    }
    mismatches
}

pub fn verify_immutable_core(repo_root: &Path, lock_path: &Path) -> ImmutableCoreReceipt {
    let repo_root_sha = sha256_prefixed(repo_root.to_string_lossy().as_bytes());
    let lock_rel = lock_path
        .strip_prefix(repo_root)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| lock_path.to_string_lossy().replace('\\', "/"));

    let raw = match fs::read(lock_path) {
        Ok(data) => data,
        Err(_) => return receipt_invalid("MISSING_ARTIFACT", &lock_rel, &repo_root_sha),
    };

    let canonical = match canonicalize_bytes(&raw) {
        Ok(val) => val,
        Err(_) => return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha),
    };
    if canonical != raw {
        return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha);
    }

    let gcj = match parse_gcj(&raw) {
        Ok(val) => val,
        Err(_) => return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha),
    };
    let lock = match parse_lock(&gcj) {
        Ok(lock) => lock,
        Err(_) => return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha),
    };

    if lock.schema != LOCK_SCHEMA || lock.spec_version != SPEC_VERSION {
        return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha);
    }

    let expected_core_hash = compute_core_tree_hash(&lock.files);
    if lock.core_tree_hash_v1 != expected_core_hash || lock.core_id != expected_core_hash {
        return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha);
    }

    let expected_lock_id = compute_lock_id(&lock);
    if lock.lock_id != expected_lock_id {
        return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha);
    }

    let expected_head = compute_lock_head_hash(&lock);
    if lock.lock_head_hash != expected_head {
        return receipt_invalid("IMMUTABLE_CORE_LOCK_INVALID", &lock_rel, &repo_root_sha);
    }

    let observed_files = match collect_files(repo_root, &lock.source_roots, &lock.excludes, &lock_rel) {
        Ok(entries) => entries,
        Err(_) => return receipt_invalid("MISSING_ARTIFACT", &lock_rel, &repo_root_sha),
    };
    let observed_core_hash = compute_core_tree_hash(&observed_files);

    let mismatches = compare_files(&lock.files, &observed_files);
    if !mismatches.is_empty() || observed_core_hash != lock.core_id {
        let mut receipt = ImmutableCoreReceipt {
            schema: RECEIPT_SCHEMA.to_string(),
            spec_version: SPEC_VERSION.to_string(),
            verdict: "INVALID".to_string(),
            reason: "IMMUTABLE_CORE_MISMATCH".to_string(),
            repo_root_sha256: repo_root_sha,
            lock_path: lock_rel,
            lock_id: lock.lock_id.clone(),
            core_id_expected: lock.core_id.clone(),
            core_id_observed: observed_core_hash,
            mismatches,
            receipt_head_hash: "".to_string(),
        };
        receipt.receipt_head_hash = compute_receipt_head_hash(&receipt);
        return receipt;
    }

    let mut receipt = ImmutableCoreReceipt {
        schema: RECEIPT_SCHEMA.to_string(),
        spec_version: SPEC_VERSION.to_string(),
        verdict: "VALID".to_string(),
        reason: "OK".to_string(),
        repo_root_sha256: repo_root_sha,
        lock_path: lock_rel,
        lock_id: lock.lock_id.clone(),
        core_id_expected: lock.core_id.clone(),
        core_id_observed: observed_core_hash,
        mismatches: Vec::new(),
        receipt_head_hash: "".to_string(),
    };
    receipt.receipt_head_hash = compute_receipt_head_hash(&receipt);
    receipt
}
