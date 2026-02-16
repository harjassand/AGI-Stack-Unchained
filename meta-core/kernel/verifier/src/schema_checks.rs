use std::collections::BTreeMap;
use std::fmt;

use crate::canonical_json::GcjValue;
use crate::hash::is_hex_64;

#[derive(Debug)]
pub enum SchemaError {
    Invalid(String),
}

impl fmt::Display for SchemaError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SchemaError::Invalid(msg) => write!(f, "{msg}"),
        }
    }
}

#[derive(Clone, Debug)]
pub struct BlobEntry {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Clone, Debug)]
pub struct Proofs {
    pub proof_bundle_hash: String,
}

#[derive(Clone, Debug)]
pub struct Manifest {
    pub bundle_hash: String,
    pub parent_bundle_hash: String,
    pub meta_hash: String,
    pub kernel_hash: String,
    pub ruleset_hash: String,
    pub migration_hash: String,
    pub state_schema_hash: String,
    pub toolchain_merkle_root: String,
    pub blobs: Vec<BlobEntry>,
    pub proofs: Proofs,
}

#[derive(Clone, Debug)]
pub struct ProofBundleManifest {
    pub dominance_witness_sha256: String,
    pub statement_ids: Vec<String>,
}

pub fn parse_manifest(value: &GcjValue) -> Result<Manifest, SchemaError> {
    let obj = expect_object(value, "manifest")?;

    let format = expect_string(obj.get("format"), "format")?;
    if format != "meta_core_bundle_v1" {
        return Err(SchemaError::Invalid("invalid format".to_string()));
    }
    let schema_version = expect_string(obj.get("schema_version"), "schema_version")?;
    if schema_version != "1" {
        return Err(SchemaError::Invalid("invalid schema_version".to_string()));
    }

    let bundle_hash = expect_hex(obj.get("bundle_hash"), "bundle_hash")?;
    let parent_bundle_hash = expect_string(obj.get("parent_bundle_hash"), "parent_bundle_hash")?;
    if !parent_bundle_hash.is_empty() && !is_hex_64(&parent_bundle_hash) {
        return Err(SchemaError::Invalid("parent_bundle_hash must be hex64 or empty".to_string()));
    }
    let meta_hash = expect_hex(obj.get("meta_hash"), "meta_hash")?;
    let kernel_hash = expect_hex(obj.get("kernel_hash"), "kernel_hash")?;
    let ruleset_hash = expect_hex(obj.get("ruleset_hash"), "ruleset_hash")?;
    let migration_hash = expect_hex(obj.get("migration_hash"), "migration_hash")?;
    let state_schema_hash = expect_hex(obj.get("state_schema_hash"), "state_schema_hash")?;
    let toolchain_merkle_root = expect_hex(obj.get("toolchain_merkle_root"), "toolchain_merkle_root")?;

    let blobs_val = obj.get("blobs").ok_or_else(|| SchemaError::Invalid("missing blobs".to_string()))?;
    let blobs_arr = expect_array(blobs_val, "blobs")?;
    let mut blobs = Vec::new();
    for item in blobs_arr {
        let item_obj = expect_object(item, "blobs[]")?;
        let path = expect_string(item_obj.get("path"), "path")?;
        let sha256 = expect_hex(item_obj.get("sha256"), "sha256")?;
        let bytes = expect_u64(item_obj.get("bytes"), "bytes")?;
        blobs.push(BlobEntry { path, sha256, bytes });
    }

    let proofs_val = obj.get("proofs").ok_or_else(|| SchemaError::Invalid("missing proofs".to_string()))?;
    let proofs_obj = expect_object(proofs_val, "proofs")?;
    let proof_bundle_hash = expect_hex(proofs_obj.get("proof_bundle_hash"), "proof_bundle_hash")?;

    Ok(Manifest {
        bundle_hash,
        parent_bundle_hash,
        meta_hash,
        kernel_hash,
        ruleset_hash,
        migration_hash,
        state_schema_hash,
        toolchain_merkle_root,
        blobs,
        proofs: Proofs { proof_bundle_hash },
    })
}

pub fn parse_proof_bundle_manifest(value: &GcjValue) -> Result<ProofBundleManifest, SchemaError> {
    let obj = expect_object(value, "proof_bundle_manifest")?;
    let format = expect_string(obj.get("format"), "format")?;
    if format != "meta_core_proof_bundle_v1" {
        return Err(SchemaError::Invalid("invalid proof bundle format".to_string()));
    }
    let schema_version = expect_string(obj.get("schema_version"), "schema_version")?;
    if schema_version != "1" {
        return Err(SchemaError::Invalid("invalid proof bundle schema_version".to_string()));
    }

    let dominance_witness_sha256 = expect_hex(obj.get("dominance_witness_sha256"), "dominance_witness_sha256")?;
    let statement_ids_val = obj.get("statement_ids").ok_or_else(|| SchemaError::Invalid("missing statement_ids".to_string()))?;
    let arr = expect_array(statement_ids_val, "statement_ids")?;
    let mut statement_ids = Vec::new();
    for item in arr {
        match item {
            GcjValue::Str(s) => statement_ids.push(s.clone()),
            _ => return Err(SchemaError::Invalid("statement_ids must be strings".to_string())),
        }
    }
    Ok(ProofBundleManifest { dominance_witness_sha256, statement_ids })
}

fn expect_object<'a>(value: &'a GcjValue, name: &str) -> Result<&'a BTreeMap<String, GcjValue>, SchemaError> {
    match value {
        GcjValue::Object(map) => Ok(map),
        _ => Err(SchemaError::Invalid(format!("{name} must be object"))),
    }
}

fn expect_array<'a>(value: &'a GcjValue, name: &str) -> Result<&'a Vec<GcjValue>, SchemaError> {
    match value {
        GcjValue::Array(arr) => Ok(arr),
        _ => Err(SchemaError::Invalid(format!("{name} must be array"))),
    }
}

fn expect_string(value: Option<&GcjValue>, name: &str) -> Result<String, SchemaError> {
    match value {
        Some(GcjValue::Str(s)) => Ok(s.clone()),
        _ => Err(SchemaError::Invalid(format!("{name} must be string"))),
    }
}

fn expect_hex(value: Option<&GcjValue>, name: &str) -> Result<String, SchemaError> {
    let s = expect_string(value, name)?;
    if !is_hex_64(&s) {
        return Err(SchemaError::Invalid(format!("{name} must be hex64")));
    }
    Ok(s)
}

fn expect_u64(value: Option<&GcjValue>, name: &str) -> Result<u64, SchemaError> {
    match value {
        Some(GcjValue::Int(i)) if *i >= 0 => Ok(*i as u64),
        _ => Err(SchemaError::Invalid(format!("{name} must be non-negative integer"))),
    }
}
