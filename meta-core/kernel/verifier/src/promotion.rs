use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::canonical_json::{canonical_bytes, canonicalize_bytes, parse_gcj, GcjValue};
use crate::hash::{is_hex_64, sha256, to_hex};

const HASH_ZERO: &str = "0000000000000000000000000000000000000000000000000000000000000000";

pub const REASON_OK: &str = "OK";
pub const REASON_MANIFEST_MISSING: &str = "MANIFEST_MISSING";
pub const REASON_MANIFEST_INVALID: &str = "MANIFEST_INVALID";
pub const REASON_MANIFEST_NON_CANONICAL: &str = "MANIFEST_NON_CANONICAL";
pub const REASON_MANIFEST_SCHEMA_MISMATCH: &str = "MANIFEST_SCHEMA_MISMATCH";
pub const REASON_META_HASH_MISSING: &str = "META_HASH_MISSING";
pub const REASON_KERNEL_HASH_MISSING: &str = "KERNEL_HASH_MISSING";
pub const REASON_CONSTANTS_MISSING: &str = "CONSTANTS_MISSING";
pub const REASON_META_HASH_MISMATCH: &str = "META_HASH_MISMATCH";
pub const REASON_KERNEL_HASH_MISMATCH: &str = "KERNEL_HASH_MISMATCH";
pub const REASON_CONSTANTS_HASH_MISMATCH: &str = "CONSTANTS_HASH_MISMATCH";
pub const REASON_BLOB_ENTRY_INVALID: &str = "BLOB_ENTRY_INVALID";
pub const REASON_BLOB_PATH_INVALID: &str = "BLOB_PATH_INVALID";
pub const REASON_BLOB_MISSING: &str = "BLOB_MISSING";
pub const REASON_BLOB_BYTES_MISMATCH: &str = "BLOB_BYTES_MISMATCH";
pub const REASON_BLOB_HASH_MISMATCH: &str = "BLOB_HASH_MISMATCH";
pub const REASON_BLOB_NON_CANONICAL: &str = "BLOB_NON_CANONICAL";
pub const REASON_BUNDLE_HASH_MISMATCH: &str = "BUNDLE_HASH_MISMATCH";
pub const REASON_PROOFS_MISSING: &str = "PROOFS_MISSING";
pub const REASON_DOMINANCE_WITNESS_MISSING: &str = "DOMINANCE_WITNESS_MISSING";
pub const REASON_DOMINANCE_WITNESS_HASH_MISMATCH: &str = "DOMINANCE_WITNESS_HASH_MISMATCH";
pub const REASON_DOMINANCE_WITNESS_SCHEMA_INVALID: &str = "DOMINANCE_WITNESS_SCHEMA_INVALID";

#[derive(Clone, Debug)]
struct PromotionBlob {
    path: String,
    sha256: String,
    bytes: u64,
}

#[derive(Clone, Debug)]
struct PromotionProofs {
    dominance_witness_hash: String,
}

#[derive(Clone, Debug)]
struct PromotionManifest {
    promotion_type: String,
    meta_hash: String,
    kernel_hash: String,
    constants_hash: String,
    proofs: PromotionProofs,
    blobs: Vec<PromotionBlob>,
    bundle_hash: String,
}

#[derive(Clone, Debug)]
pub struct PromotionReceipt {
    pub verdict: String,
    pub bundle_hash: String,
    pub reason_codes: Vec<String>,
    pub receipt_hash: String,
}

impl PromotionReceipt {
    pub fn new(verdict: String, reason_codes: Vec<String>, bundle_hash: Option<String>) -> Self {
        let mut obj = BTreeMap::new();
        obj.insert("schema".to_string(), GcjValue::Str("promotion_receipt_v1".to_string()));
        obj.insert("schema_version".to_string(), GcjValue::Int(1));
        obj.insert("verdict".to_string(), GcjValue::Str(verdict.clone()));
        let reasons = reason_codes
            .iter()
            .cloned()
            .map(GcjValue::Str)
            .collect::<Vec<_>>();
        obj.insert("reason_codes".to_string(), GcjValue::Array(reasons));
        if let Some(hash) = bundle_hash.clone() {
            obj.insert("bundle_hash".to_string(), GcjValue::Str(hash.clone()));
        }
        let receipt_hash = sha256_prefixed(&canonical_bytes(&GcjValue::Object(obj)));
        let bundle_hash_value = bundle_hash.unwrap_or_else(|| format!("sha256:{HASH_ZERO}"));
        Self {
            verdict,
            bundle_hash: bundle_hash_value,
            reason_codes,
            receipt_hash,
        }
    }

    pub fn to_gcj(&self) -> GcjValue {
        let mut obj = BTreeMap::new();
        obj.insert("schema".to_string(), GcjValue::Str("promotion_receipt_v1".to_string()));
        obj.insert("schema_version".to_string(), GcjValue::Int(1));
        obj.insert("verdict".to_string(), GcjValue::Str(self.verdict.clone()));
        let reasons = self
            .reason_codes
            .iter()
            .cloned()
            .map(GcjValue::Str)
            .collect::<Vec<_>>();
        obj.insert("reason_codes".to_string(), GcjValue::Array(reasons));
        if self.bundle_hash != format!("sha256:{HASH_ZERO}") {
            obj.insert("bundle_hash".to_string(), GcjValue::Str(self.bundle_hash.clone()));
        }
        obj.insert("receipt_hash".to_string(), GcjValue::Str(self.receipt_hash.clone()));
        GcjValue::Object(obj)
    }

    pub fn canonical_bytes(&self) -> Vec<u8> {
        canonical_bytes(&self.to_gcj())
    }
}

fn find_meta_constitution_dir(meta_core_root: &Path, expected_meta_hash: &str) -> Option<PathBuf> {
    let root = meta_core_root.join("meta_constitution");
    let entries = fs::read_dir(&root).ok()?;
    for entry in entries {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue,
        };
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let meta_hash_path = path.join("META_HASH");
        let meta_hash = match read_file_string(&meta_hash_path) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if meta_hash == expected_meta_hash {
            return Some(path);
        }
    }
    None
}

pub fn verify_promotion_bundle(bundle_dir: &Path, meta_core_root: &Path) -> PromotionReceipt {
    let mut reasons: Vec<String> = Vec::new();
    let mut bundle_hash: Option<String> = None;

    let manifest_path = bundle_dir.join("promotion_bundle_manifest_v1.json");
    if !manifest_path.exists() {
        reasons.push(REASON_MANIFEST_MISSING.to_string());
        return PromotionReceipt::new("INVALID".to_string(), reasons, None);
    }

    let manifest_bytes = match read_file(&manifest_path) {
        Ok(bytes) => bytes,
        Err(_) => {
            reasons.push(REASON_MANIFEST_INVALID.to_string());
            return PromotionReceipt::new("INVALID".to_string(), reasons, None);
        }
    };

    if let Ok(canonical) = canonicalize_bytes(&manifest_bytes) {
        if canonical != manifest_bytes {
            reasons.push(REASON_MANIFEST_NON_CANONICAL.to_string());
        }
    } else {
        reasons.push(REASON_MANIFEST_INVALID.to_string());
        return PromotionReceipt::new("INVALID".to_string(), reasons, None);
    }

    let manifest_gcj = match parse_gcj(&manifest_bytes) {
        Ok(val) => val,
        Err(_) => {
            reasons.push(REASON_MANIFEST_INVALID.to_string());
            return PromotionReceipt::new("INVALID".to_string(), reasons, None);
        }
    };

    let manifest = match parse_manifest(&manifest_gcj) {
        Ok(manifest) => manifest,
        Err(reason) => {
            reasons.push(reason);
            return PromotionReceipt::new("INVALID".to_string(), reasons, None);
        }
    };
    if manifest.promotion_type.trim().is_empty() {
        reasons.push(REASON_MANIFEST_SCHEMA_MISMATCH.to_string());
    }

    let kernel_hash_path = meta_core_root.join("kernel").join("verifier").join("KERNEL_HASH");
    let meta_constitution_dir = find_meta_constitution_dir(meta_core_root, &manifest.meta_hash);
    let meta_hash_path = meta_constitution_dir.as_ref().map(|dir| dir.join("META_HASH"));
    let constants_path = meta_constitution_dir.as_ref().map(|dir| dir.join("constants_v1.json"));

    if meta_constitution_dir.is_none() {
        reasons.push(REASON_META_HASH_MISMATCH.to_string());
        reasons.push(REASON_CONSTANTS_HASH_MISMATCH.to_string());
    }
    if !kernel_hash_path.exists() {
        reasons.push(REASON_KERNEL_HASH_MISSING.to_string());
    }

    if let Some(meta_hash_path) = &meta_hash_path {
        if !meta_hash_path.exists() {
            reasons.push(REASON_META_HASH_MISSING.to_string());
        } else if let Ok(meta_hash) = read_file_string(meta_hash_path) {
            if manifest.meta_hash != meta_hash {
                reasons.push(REASON_META_HASH_MISMATCH.to_string());
            }
        } else {
            reasons.push(REASON_META_HASH_MISMATCH.to_string());
        }
    }

    if kernel_hash_path.exists() {
        if let Ok(kernel_hash) = read_file_string(&kernel_hash_path) {
            if manifest.kernel_hash != kernel_hash {
                reasons.push(REASON_KERNEL_HASH_MISMATCH.to_string());
            }
        } else {
            reasons.push(REASON_KERNEL_HASH_MISMATCH.to_string());
        }
    }

    if let Some(constants_path) = &constants_path {
        if !constants_path.exists() {
            reasons.push(REASON_CONSTANTS_MISSING.to_string());
        } else if let Ok(const_bytes) = read_file(constants_path) {
            if let Ok(constants_gcj) = parse_gcj(&const_bytes) {
                let canon = canonical_bytes(&constants_gcj);
                let const_hash = sha256_prefixed(&canon);
                if manifest.constants_hash != const_hash {
                    reasons.push(REASON_CONSTANTS_HASH_MISMATCH.to_string());
                }
            } else {
                reasons.push(REASON_CONSTANTS_HASH_MISMATCH.to_string());
            }
        } else {
            reasons.push(REASON_CONSTANTS_HASH_MISMATCH.to_string());
        }
    }

    let mut blob_bytes: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    let mut seen_paths: BTreeSet<String> = BTreeSet::new();
    let mut witness_blob_path: Option<PathBuf> = None;
    let mut witness_blob_hash: Option<String> = None;
    for blob in &manifest.blobs {
        if !is_normalized_rel_path(&blob.path) {
            reasons.push(REASON_BLOB_PATH_INVALID.to_string());
            continue;
        }
        if !seen_paths.insert(blob.path.clone()) {
            reasons.push(REASON_BLOB_ENTRY_INVALID.to_string());
            continue;
        }
        let full_path = bundle_dir.join(&blob.path);
        if !full_path.exists() {
            reasons.push(REASON_BLOB_MISSING.to_string());
            continue;
        }
        let data = match read_file(&full_path) {
            Ok(data) => data,
            Err(_) => {
                reasons.push(REASON_BLOB_MISSING.to_string());
                continue;
            }
        };
        if blob.path.ends_with(".json") {
            match canonicalize_bytes(&data) {
                Ok(canon) => {
                    if canon != data {
                        reasons.push(REASON_BLOB_NON_CANONICAL.to_string());
                    }
                }
                Err(_) => {
                    reasons.push(REASON_BLOB_NON_CANONICAL.to_string());
                }
            }
        }
        if data.len() as u64 != blob.bytes {
            reasons.push(REASON_BLOB_BYTES_MISMATCH.to_string());
        }
        let calc_hash = sha256_prefixed(&data);
        if calc_hash != blob.sha256 {
            reasons.push(REASON_BLOB_HASH_MISMATCH.to_string());
        }
        if blob.path.ends_with("dominance_witness_v1.json") {
            witness_blob_path = Some(full_path);
            witness_blob_hash = Some(calc_hash.clone());
        }
        blob_bytes.insert(calc_hash.clone(), data);
    }

    if let Some(path) = witness_blob_path {
        if let Some(actual_hash) = witness_blob_hash {
            if actual_hash != manifest.proofs.dominance_witness_hash {
                reasons.push(REASON_DOMINANCE_WITNESS_HASH_MISMATCH.to_string());
            }
        }
        if let Ok(witness_bytes) = read_file(&path) {
            if let Ok(canon) = canonicalize_bytes(&witness_bytes) {
                if canon != witness_bytes {
                    reasons.push(REASON_DOMINANCE_WITNESS_SCHEMA_INVALID.to_string());
                } else if let Ok(witness_gcj) = parse_gcj(&witness_bytes) {
                    if !dominance_witness_schema_ok(&witness_gcj) {
                        reasons.push(REASON_DOMINANCE_WITNESS_SCHEMA_INVALID.to_string());
                    }
                } else {
                    reasons.push(REASON_DOMINANCE_WITNESS_SCHEMA_INVALID.to_string());
                }
            } else {
                reasons.push(REASON_DOMINANCE_WITNESS_SCHEMA_INVALID.to_string());
            }
        }
    } else {
        reasons.push(REASON_DOMINANCE_WITNESS_MISSING.to_string());
    }

    if manifest.proofs.dominance_witness_hash.is_empty() {
        reasons.push(REASON_PROOFS_MISSING.to_string());
    }

    if let Ok(computed) = compute_bundle_hash(&manifest_gcj, &blob_bytes) {
        bundle_hash = Some(computed.clone());
        if computed != manifest.bundle_hash {
            reasons.push(REASON_BUNDLE_HASH_MISMATCH.to_string());
        }
    } else {
        reasons.push(REASON_BUNDLE_HASH_MISMATCH.to_string());
    }

    let verdict = if reasons.is_empty() { "VALID" } else { "INVALID" };
    PromotionReceipt::new(verdict.to_string(), reasons, bundle_hash)
}

fn parse_manifest(value: &GcjValue) -> Result<PromotionManifest, String> {
    let obj = expect_object(value, REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let schema = expect_string(obj.get("schema"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    if schema != "promotion_bundle_manifest_v1" {
        return Err(REASON_MANIFEST_SCHEMA_MISMATCH.to_string());
    }
    let schema_version = expect_u64(obj.get("schema_version"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    if schema_version != 1 {
        return Err(REASON_MANIFEST_SCHEMA_MISMATCH.to_string());
    }
    let promotion_type = expect_string(obj.get("promotion_type"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let meta_hash = expect_hex(obj.get("META_HASH"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let kernel_hash = expect_hex(obj.get("KERNEL_HASH"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let constants_hash = expect_sha256_prefixed(obj.get("constants_hash"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let bundle_hash = expect_sha256_prefixed(obj.get("bundle_hash"), REASON_MANIFEST_SCHEMA_MISMATCH)?;

    let proofs_val = obj.get("proofs").ok_or_else(|| REASON_MANIFEST_SCHEMA_MISMATCH.to_string())?;
    let proofs_obj = expect_object(proofs_val, REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let dominance_witness_hash =
        expect_sha256_prefixed(proofs_obj.get("dominance_witness_hash"), REASON_MANIFEST_SCHEMA_MISMATCH)?;

    let blobs_val = obj.get("blobs").ok_or_else(|| REASON_MANIFEST_SCHEMA_MISMATCH.to_string())?;
    let arr = expect_array(blobs_val, REASON_MANIFEST_SCHEMA_MISMATCH)?;
    let mut blobs = Vec::new();
    for item in arr {
        let blob_obj = expect_object(item, REASON_MANIFEST_SCHEMA_MISMATCH)?;
        let path = expect_string(blob_obj.get("path"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
        let sha256 = expect_sha256_prefixed(blob_obj.get("sha256"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
        let bytes = expect_u64(blob_obj.get("bytes"), REASON_MANIFEST_SCHEMA_MISMATCH)?;
        blobs.push(PromotionBlob { path, sha256, bytes });
    }

    Ok(PromotionManifest {
        promotion_type,
        meta_hash,
        kernel_hash,
        constants_hash,
        proofs: PromotionProofs { dominance_witness_hash },
        blobs,
        bundle_hash,
    })
}

fn dominance_witness_schema_ok(value: &GcjValue) -> bool {
    let obj = match value {
        GcjValue::Object(map) => map,
        _ => return false,
    };
    match obj.get("schema") {
        Some(GcjValue::Str(s)) if s == "dominance_witness_v1" => {}
        _ => return false,
    }
    match obj.get("schema_version") {
        Some(GcjValue::Int(i)) if *i == 1 => {}
        _ => return false,
    }
    obj.contains_key("epoch_id") && obj.contains_key("decisions")
}

fn compute_bundle_hash(manifest_gcj: &GcjValue, blobs: &BTreeMap<String, Vec<u8>>) -> Result<String, ()> {
    let obj = match manifest_gcj {
        GcjValue::Object(map) => map,
        _ => return Err(()),
    };
    let mut map = obj.clone();
    map.remove("bundle_hash");
    let manifest_bytes = canonical_bytes(&GcjValue::Object(map));
    let mut parts = Vec::new();
    parts.extend_from_slice(&manifest_bytes);
    for (_hash, bytes) in blobs {
        parts.extend_from_slice(bytes);
    }
    Ok(sha256_prefixed(&parts))
}

fn sha256_prefixed(bytes: &[u8]) -> String {
    format!("sha256:{}", to_hex(&sha256(bytes)))
}

fn read_file(path: &Path) -> Result<Vec<u8>, ()> {
    fs::read(path).map_err(|_| ())
}

fn read_file_string(path: &Path) -> Result<String, ()> {
    let bytes = read_file(path)?;
    let s = String::from_utf8(bytes).map_err(|_| ())?;
    Ok(s.trim().to_string())
}

fn expect_object<'a>(value: &'a GcjValue, reason: &str) -> Result<&'a BTreeMap<String, GcjValue>, String> {
    match value {
        GcjValue::Object(map) => Ok(map),
        _ => Err(reason.to_string()),
    }
}

fn expect_array<'a>(value: &'a GcjValue, reason: &str) -> Result<&'a Vec<GcjValue>, String> {
    match value {
        GcjValue::Array(arr) => Ok(arr),
        _ => Err(reason.to_string()),
    }
}

fn expect_string(value: Option<&GcjValue>, reason: &str) -> Result<String, String> {
    match value {
        Some(GcjValue::Str(s)) => Ok(s.clone()),
        _ => Err(reason.to_string()),
    }
}

fn expect_hex(value: Option<&GcjValue>, reason: &str) -> Result<String, String> {
    let s = expect_string(value, reason)?;
    if !is_hex_64(&s) {
        return Err(reason.to_string());
    }
    Ok(s)
}

fn expect_sha256_prefixed(value: Option<&GcjValue>, reason: &str) -> Result<String, String> {
    let s = expect_string(value, reason)?;
    if let Some(rest) = s.strip_prefix("sha256:") {
        if is_hex_64(rest) {
            return Ok(s);
        }
    }
    Err(reason.to_string())
}

fn expect_u64(value: Option<&GcjValue>, reason: &str) -> Result<u64, String> {
    match value {
        Some(GcjValue::Int(i)) if *i >= 0 => Ok(*i as u64),
        _ => Err(reason.to_string()),
    }
}

fn is_normalized_rel_path(path: &str) -> bool {
    if path.is_empty() || path.starts_with('/') || path.contains('\\') {
        return false;
    }
    for segment in path.split('/') {
        if segment.is_empty() || segment == "." || segment == ".." {
            return false;
        }
    }
    true
}
