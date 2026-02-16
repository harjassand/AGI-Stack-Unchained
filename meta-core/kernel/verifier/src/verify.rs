use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::canonical_json::{canonical_bytes, canonicalize_bytes, parse_gcj, GcjValue};
use crate::hash::{hex_to_bytes_32, is_hex_64, sha256, sha256_hex, to_hex};
use crate::ir::ast::{expr_to_gcj, value_from_gcj, Expr, IrError, Value};
use crate::ir::eval::{eval, EvalContext};
use crate::ir::gas::GasCounter;
use crate::ir::static_checks::{check_limits, IrLimits};
use crate::schema_checks::{parse_manifest, parse_proof_bundle_manifest, Manifest};

pub const REASON_OK: &str = "OK";
pub const REASON_MANIFEST_SCHEMA_INVALID: &str = "MANIFEST_SCHEMA_INVALID";
pub const REASON_BLOB_HASH_MISMATCH: &str = "BLOB_HASH_MISMATCH";
pub const REASON_BUNDLE_HASH_MISMATCH: &str = "BUNDLE_HASH_MISMATCH";
pub const REASON_RULESET_HASH_MISMATCH: &str = "RULESET_HASH_MISMATCH";
pub const REASON_META_HASH_MISMATCH: &str = "META_HASH_MISMATCH";
pub const REASON_KERNEL_HASH_MISMATCH: &str = "KERNEL_HASH_MISMATCH";
pub const REASON_IR_PARSE_ERROR: &str = "IR_PARSE_ERROR";
pub const REASON_IR_STATIC_CHECK_FAILED: &str = "IR_STATIC_CHECK_FAILED";
pub const REASON_IR_RUNTIME_ERROR: &str = "IR_RUNTIME_ERROR";
pub const REASON_GAS_LIMIT_EXCEEDED: &str = "GAS_LIMIT_EXCEEDED";
pub const REASON_PROOF_BUNDLE_INVALID: &str = "PROOF_BUNDLE_INVALID";
pub const REASON_DOMINANCE_CHECK_FAILED: &str = "DOMINANCE_CHECK_FAILED";
pub const REASON_MIGRATION_FAILED: &str = "MIGRATION_FAILED";
pub const REASON_TOOLCHAIN_MERKLE_ROOT_MISMATCH: &str = "TOOLCHAIN_MERKLE_ROOT_MISMATCH";
pub const REASON_STATE_SCHEMA_HASH_MISMATCH: &str = "STATE_SCHEMA_HASH_MISMATCH";
pub const REASON_MIGRATION_HASH_MISMATCH: &str = "MIGRATION_HASH_MISMATCH";
pub const REASON_KERNEL_INTERNAL_ERROR: &str = "KERNEL_INTERNAL_ERROR";

const HASH_ZERO: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const RULESET_DELIM: &[u8] = b"\0";
const TOOLCHAIN_FILES: &[&str] = &[
    "kernel/verifier/toolchain.lock",
    "kernel/verifier/Cargo.lock",
    "kernel/verifier/KERNEL_HASH",
    "kernel/verifier/build.sh",
    "meta_constitution/v1/META_HASH",
    "meta_constitution/v1/build_meta_hash.sh",
    "scripts/build.sh",
];

pub struct Receipt {
    pub verdict: String,
    pub bundle_hash: String,
    pub meta_hash: String,
    pub kernel_hash: String,
    pub toolchain_merkle_root: String,
    pub reason_code: String,
    pub details: BTreeMap<String, GcjValue>,
}

impl Receipt {
    pub fn to_gcj(&self) -> GcjValue {
        let mut obj = BTreeMap::new();
        obj.insert("bundle_hash".to_string(), GcjValue::Str(self.bundle_hash.clone()));
        obj.insert("details".to_string(), GcjValue::Object(self.details.clone()));
        obj.insert("format".to_string(), GcjValue::Str("meta_core_receipt_v1".to_string()));
        obj.insert("kernel_hash".to_string(), GcjValue::Str(self.kernel_hash.clone()));
        obj.insert("meta_hash".to_string(), GcjValue::Str(self.meta_hash.clone()));
        obj.insert("toolchain_merkle_root".to_string(), GcjValue::Str(self.toolchain_merkle_root.clone()));
        obj.insert("reason_code".to_string(), GcjValue::Str(self.reason_code.clone()));
        obj.insert("schema_version".to_string(), GcjValue::Str("1".to_string()));
        obj.insert("verdict".to_string(), GcjValue::Str(self.verdict.clone()));
        GcjValue::Object(obj)
    }

    pub fn canonical_bytes(&self) -> Vec<u8> {
        canonical_bytes(&self.to_gcj())
    }
}

#[derive(Debug)]
pub struct VerifyError {
    pub reason_code: String,
    pub details: BTreeMap<String, GcjValue>,
}

impl VerifyError {
    fn new(code: &str) -> Self {
        Self { reason_code: code.to_string(), details: BTreeMap::new() }
    }

    fn with_detail(mut self, key: &str, value: GcjValue) -> Self {
        self.details.insert(key.to_string(), value);
        self
    }
}

#[derive(Clone, Debug)]
struct MetaSpec {
    policy: Policy,
    ir_limits: IrLimits,
    statement_ids: Vec<String>,
}

#[derive(Clone, Debug)]
struct Policy {
    max_blobs: u64,
    max_blob_bytes: u64,
    max_proof_bytes: u64,
    allowed_extensions: Vec<String>,
}

pub fn verify_bundle(bundle_dir: &Path, parent_bundle_dir: Option<&Path>, meta_dir: &Path) -> Receipt {
    let kernel_hash = match compute_kernel_hash() {
        Ok(hash) => hash,
        Err(_) => {
            return Receipt {
                verdict: "INVALID".to_string(),
                bundle_hash: HASH_ZERO.to_string(),
                meta_hash: HASH_ZERO.to_string(),
                kernel_hash: HASH_ZERO.to_string(),
                toolchain_merkle_root: HASH_ZERO.to_string(),
                reason_code: REASON_KERNEL_INTERNAL_ERROR.to_string(),
                details: BTreeMap::new(),
            };
        }
    };
    let mut ctx = ReceiptContext::new(kernel_hash);

    match verify_bundle_inner(bundle_dir, parent_bundle_dir, meta_dir, &mut ctx) {
        Ok(()) => Receipt {
            verdict: "VALID".to_string(),
            bundle_hash: ctx.bundle_hash,
            meta_hash: ctx.meta_hash,
            kernel_hash: ctx.kernel_hash,
            toolchain_merkle_root: ctx.toolchain_merkle_root,
            reason_code: REASON_OK.to_string(),
            details: BTreeMap::new(),
        },
        Err(err) => Receipt {
            verdict: "INVALID".to_string(),
            bundle_hash: ctx.bundle_hash,
            meta_hash: ctx.meta_hash,
            kernel_hash: ctx.kernel_hash,
            toolchain_merkle_root: ctx.toolchain_merkle_root,
            reason_code: err.reason_code,
            details: err.details,
        },
    }
}

fn verify_bundle_inner(
    bundle_dir: &Path,
    parent_bundle_dir: Option<&Path>,
    meta_dir: &Path,
    ctx: &mut ReceiptContext,
) -> Result<(), VerifyError> {
    let (meta_hash, spec) = load_meta_spec(meta_dir).map_err(|e| e.with_detail("stage", GcjValue::Str("meta_spec".to_string())))?;
    ctx.meta_hash = meta_hash.clone();

    let toolchain_merkle_root = compute_toolchain_merkle_root(meta_dir)?;
    ctx.toolchain_merkle_root = toolchain_merkle_root.clone();
    let toolchain_merkle_root_bytes =
        hex_to_bytes_32(&toolchain_merkle_root).ok_or_else(|| VerifyError::new(REASON_KERNEL_INTERNAL_ERROR))?;

    let state_schema_hash = compute_state_schema_hash(meta_dir)?;
    let state_schema_hash_bytes =
        hex_to_bytes_32(&state_schema_hash).ok_or_else(|| VerifyError::new(REASON_KERNEL_INTERNAL_ERROR))?;

    let manifest_bytes = read_file(&bundle_dir.join("constitution.manifest.json"), REASON_MANIFEST_SCHEMA_INVALID)?;
    let manifest_gcj = parse_gcj(&manifest_bytes).map_err(|_| VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID))?;
    let manifest = parse_manifest(&manifest_gcj).map_err(|_| VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID))?;

    ctx.bundle_hash = manifest.bundle_hash.clone();

    if manifest.meta_hash != meta_hash {
        return Err(VerifyError::new(REASON_META_HASH_MISMATCH));
    }
    if manifest.kernel_hash != ctx.kernel_hash {
        return Err(VerifyError::new(REASON_KERNEL_HASH_MISMATCH));
    }
    if manifest.toolchain_merkle_root != toolchain_merkle_root {
        return Err(VerifyError::new(REASON_TOOLCHAIN_MERKLE_ROOT_MISMATCH));
    }
    if manifest.state_schema_hash != state_schema_hash {
        return Err(VerifyError::new(REASON_STATE_SCHEMA_HASH_MISMATCH));
    }

    if manifest.blobs.len() as u64 > spec.policy.max_blobs {
        return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID));
    }

    let manifest_hash = manifest_hash_for_bundle(&manifest_gcj)?;

    let _blob_hashes = verify_blobs(bundle_dir, &manifest, &spec.policy)?;

    let (accept_bytes, accept_expr) = load_ir(bundle_dir.join("ruleset/accept.ir.json"))?;
    let (cost_bytes, cost_expr) = load_ir(bundle_dir.join("ruleset/costvec.ir.json"))?;
    let (migrate_bytes, migrate_expr) = load_ir(bundle_dir.join("ruleset/migrate.ir.json"))?;

    check_limits(&accept_expr, &spec.ir_limits).map_err(|_| VerifyError::new(REASON_IR_STATIC_CHECK_FAILED))?;
    check_limits(&cost_expr, &spec.ir_limits).map_err(|_| VerifyError::new(REASON_IR_STATIC_CHECK_FAILED))?;
    check_limits(&migrate_expr, &spec.ir_limits).map_err(|_| VerifyError::new(REASON_IR_STATIC_CHECK_FAILED))?;

    let ruleset_hash = compute_ruleset_hash(&accept_bytes, &cost_bytes, &migrate_bytes);
    let ruleset_hex = to_hex(&ruleset_hash);
    if manifest.ruleset_hash != ruleset_hex {
        return Err(VerifyError::new(REASON_RULESET_HASH_MISMATCH));
    }

    let proof_bundle_hash =
        verify_proof_bundle(bundle_dir, &manifest, &spec.statement_ids, spec.policy.max_proof_bytes)?;

    let migration_hash = sha256(&migrate_bytes);
    let migration_hex = to_hex(&migration_hash);
    if manifest.migration_hash != migration_hex {
        return Err(VerifyError::new(REASON_MIGRATION_HASH_MISMATCH));
    }

    let computed_bundle_hash = compute_bundle_hash(
        &manifest_hash,
        &ruleset_hash,
        &proof_bundle_hash,
        &migration_hash,
        &state_schema_hash_bytes,
        &toolchain_merkle_root_bytes,
    );
    let computed_bundle_hex = to_hex(&computed_bundle_hash);
    ctx.bundle_hash = computed_bundle_hex.clone();

    if manifest.bundle_hash != computed_bundle_hex {
        return Err(VerifyError::new(REASON_BUNDLE_HASH_MISMATCH));
    }

    if !manifest.parent_bundle_hash.is_empty() {
        if let Some(parent_dir) = parent_bundle_dir {
            let _parent_bundle_hash = verify_parent_bundle(
                parent_dir,
                &manifest.parent_bundle_hash,
                &state_schema_hash_bytes,
                &toolchain_merkle_root_bytes,
            )?;
        } else {
            return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED));
        }
    }

    let accept_cond = extract_accept_cond(&accept_expr)?;

    if !manifest.parent_bundle_hash.is_empty() {
        let parent_dir = parent_bundle_dir.unwrap();
        check_dominance(
            parent_dir,
            &accept_cond,
            bundle_dir,
            &ruleset_hex,
            &meta_hash,
            &spec.ir_limits,
            &state_schema_hash_bytes,
            &toolchain_merkle_root_bytes,
            &manifest,
        )?;
    }

    check_migration(
        bundle_dir,
        &migrate_expr,
        &spec.ir_limits,
        &meta_hash,
        &ruleset_hex,
        &state_schema_hash_bytes,
        &toolchain_merkle_root_bytes,
    )?;

    Ok(())
}

struct ReceiptContext {
    bundle_hash: String,
    meta_hash: String,
    kernel_hash: String,
    toolchain_merkle_root: String,
}

impl ReceiptContext {
    fn new(kernel_hash: String) -> Self {
        Self {
            bundle_hash: HASH_ZERO.to_string(),
            meta_hash: HASH_ZERO.to_string(),
            kernel_hash,
            toolchain_merkle_root: HASH_ZERO.to_string(),
        }
    }
}

fn load_meta_spec(meta_dir: &Path) -> Result<(String, MetaSpec), VerifyError> {
    let meta_hash_path = meta_dir.join("META_HASH");
    let expected_meta_hash = read_file_string(&meta_hash_path, REASON_META_HASH_MISMATCH)?;

    let computed_meta_hash = compute_meta_hash(meta_dir)?;
    if expected_meta_hash.trim() != computed_meta_hash {
        return Err(VerifyError::new(REASON_META_HASH_MISMATCH));
    }

    let policy = parse_policy(&read_gcj(meta_dir.join("spec/policy.json"), REASON_META_HASH_MISMATCH)?)?;
    let ir_limits = parse_ir_limits(&read_gcj(meta_dir.join("spec/ir_limits.json"), REASON_META_HASH_MISMATCH)?)?;
    let statement_ids = parse_statement_set(&read_gcj(meta_dir.join("spec/statement_set.json"), REASON_META_HASH_MISMATCH)?)?;

    Ok((computed_meta_hash, MetaSpec { policy, ir_limits, statement_ids }))
}

fn parse_policy(value: &GcjValue) -> Result<Policy, VerifyError> {
    let obj = expect_object(value, REASON_META_HASH_MISMATCH)?;
    let max_blobs = expect_u64(obj.get("max_blobs"), REASON_META_HASH_MISMATCH)?;
    let max_blob_bytes = expect_u64(obj.get("max_blob_bytes"), REASON_META_HASH_MISMATCH)?;
    let max_proof_bytes = expect_u64(obj.get("max_proof_bytes"), REASON_META_HASH_MISMATCH)?;
    let allowed = match obj.get("allowed_blob_extensions") {
        Some(GcjValue::Array(list)) => list
            .iter()
            .map(|v| match v {
                GcjValue::Str(s) => Ok(s.clone()),
                _ => Err(VerifyError::new(REASON_META_HASH_MISMATCH)),
            })
            .collect::<Result<Vec<_>, _>>()?,
        _ => return Err(VerifyError::new(REASON_META_HASH_MISMATCH)),
    };

    Ok(Policy {
        max_blobs,
        max_blob_bytes,
        max_proof_bytes,
        allowed_extensions: allowed,
    })
}

fn parse_ir_limits(value: &GcjValue) -> Result<IrLimits, VerifyError> {
    let obj = expect_object(value, REASON_META_HASH_MISMATCH)?;
    Ok(IrLimits {
        max_ast_depth: expect_u64(obj.get("max_ast_depth"), REASON_META_HASH_MISMATCH)?,
        max_nodes: expect_u64(obj.get("max_nodes"), REASON_META_HASH_MISMATCH)?,
        max_fuel: expect_i64(obj.get("max_fuel"), REASON_META_HASH_MISMATCH)?,
        max_gas: expect_u64(obj.get("max_gas"), REASON_META_HASH_MISMATCH)?,
    })
}

fn parse_statement_set(value: &GcjValue) -> Result<Vec<String>, VerifyError> {
    let arr = match value {
        GcjValue::Array(arr) => arr,
        _ => return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID)),
    };
    let mut out = Vec::new();
    for item in arr {
        match item {
            GcjValue::Str(s) => out.push(s.clone()),
            _ => return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID)),
        }
    }
    Ok(out)
}

fn verify_blobs(bundle_dir: &Path, manifest: &Manifest, policy: &Policy) -> Result<Vec<[u8; 32]>, VerifyError> {
    let mut seen = BTreeSet::new();
    let mut entries = manifest.blobs.clone();
    entries.sort_by(|a, b| a.path.cmp(&b.path));

    let mut blob_hashes = Vec::new();
    for blob in entries {
        if !is_normalized_rel_path(&blob.path) {
            return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID));
        }
        if !seen.insert(blob.path.clone()) {
            return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID));
        }
        if !policy.allowed_extensions.iter().any(|ext| blob.path.ends_with(ext)) {
            return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID));
        }
        let path = bundle_dir.join(&blob.path);
        let bytes = read_file(&path, REASON_BLOB_HASH_MISMATCH)?;
        if bytes.len() as u64 > policy.max_blob_bytes {
            return Err(VerifyError::new(REASON_BLOB_HASH_MISMATCH));
        }
        if bytes.len() as u64 != blob.bytes {
            return Err(VerifyError::new(REASON_BLOB_HASH_MISMATCH));
        }
        let hash = sha256(&bytes);
        let hash_hex = to_hex(&hash);
        if hash_hex != blob.sha256 {
            return Err(VerifyError::new(REASON_BLOB_HASH_MISMATCH));
        }
        blob_hashes.push(hash);
    }

    let required = [
        "ruleset/accept.ir.json",
        "ruleset/costvec.ir.json",
        "ruleset/migrate.ir.json",
    ];
    for path in required {
        if !seen.contains(path) {
            return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID));
        }
    }

    Ok(blob_hashes)
}

fn compute_bundle_hash(
    manifest_hash: &[u8; 32],
    ruleset_hash: &[u8; 32],
    proof_bundle_hash: &[u8; 32],
    migration_hash: &[u8; 32],
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
) -> [u8; 32] {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(manifest_hash);
    bytes.push(0);
    bytes.extend_from_slice(ruleset_hash);
    bytes.push(0);
    bytes.extend_from_slice(proof_bundle_hash);
    bytes.push(0);
    bytes.extend_from_slice(migration_hash);
    bytes.push(0);
    bytes.extend_from_slice(state_schema_hash);
    bytes.push(0);
    bytes.extend_from_slice(toolchain_merkle_root);
    sha256(&bytes)
}

fn manifest_hash_for_bundle(manifest_gcj: &GcjValue) -> Result<[u8; 32], VerifyError> {
    let mut map = match manifest_gcj {
        GcjValue::Object(map) => map.clone(),
        _ => return Err(VerifyError::new(REASON_MANIFEST_SCHEMA_INVALID)),
    };
    map.insert("bundle_hash".to_string(), GcjValue::Str(String::new()));
    if map.contains_key("manifest_hash") {
        map.insert("manifest_hash".to_string(), GcjValue::Str(String::new()));
    }
    let canonical = canonical_bytes(&GcjValue::Object(map));
    Ok(sha256(&canonical))
}

fn compute_ruleset_hash(accept: &[u8], cost: &[u8], migrate: &[u8]) -> [u8; 32] {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(accept);
    bytes.extend_from_slice(RULESET_DELIM);
    bytes.extend_from_slice(cost);
    bytes.extend_from_slice(RULESET_DELIM);
    bytes.extend_from_slice(migrate);
    sha256(&bytes)
}

fn load_ir(path: PathBuf) -> Result<(Vec<u8>, Expr), VerifyError> {
    let raw = read_file(&path, REASON_IR_PARSE_ERROR)?;
    let canonical = canonicalize_bytes(&raw).map_err(|_| VerifyError::new(REASON_IR_PARSE_ERROR))?;
    let gcj = parse_gcj(&raw).map_err(|_| VerifyError::new(REASON_IR_PARSE_ERROR))?;
    let expr = Expr::from_gcj(&gcj).map_err(|_| VerifyError::new(REASON_IR_PARSE_ERROR))?;
    Ok((canonical, expr))
}

fn verify_proof_bundle(
    bundle_dir: &Path,
    manifest: &Manifest,
    required_statement_ids: &[String],
    max_proof_bytes: u64,
) -> Result<[u8; 32], VerifyError> {
    let proof_manifest_path = bundle_dir.join("proofs/proof_bundle.manifest.json");
    let proof_manifest_bytes = read_file(&proof_manifest_path, REASON_PROOF_BUNDLE_INVALID)?;
    if proof_manifest_bytes.len() as u64 > max_proof_bytes {
        return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID));
    }
    let proof_manifest_gcj = parse_gcj(&proof_manifest_bytes).map_err(|_| VerifyError::new(REASON_PROOF_BUNDLE_INVALID))?;
    let proof_manifest = parse_proof_bundle_manifest(&proof_manifest_gcj).map_err(|_| VerifyError::new(REASON_PROOF_BUNDLE_INVALID))?;

    let proof_hash = sha256(&canonicalize_bytes(&proof_manifest_bytes).map_err(|_| VerifyError::new(REASON_PROOF_BUNDLE_INVALID))?);
    let proof_hash_hex = to_hex(&proof_hash);
    if proof_hash_hex != manifest.proofs.proof_bundle_hash {
        return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID));
    }

    let witness_path = bundle_dir.join("proofs/dominance_witness.json");
    let witness_bytes = read_file(&witness_path, REASON_PROOF_BUNDLE_INVALID)?;
    if witness_bytes.len() as u64 > max_proof_bytes {
        return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID));
    }
    let witness_hash = sha256(&witness_bytes);
    let witness_hex = to_hex(&witness_hash);
    if witness_hex != proof_manifest.dominance_witness_sha256 {
        return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID));
    }

    let required: BTreeSet<_> = required_statement_ids.iter().cloned().collect();
    let provided: BTreeSet<_> = proof_manifest.statement_ids.iter().cloned().collect();
    if required != provided {
        return Err(VerifyError::new(REASON_PROOF_BUNDLE_INVALID));
    }

    Ok(proof_hash)
}

fn accept_non_safe_children(expr: &Expr) -> Result<Vec<Expr>, VerifyError> {
    let list = match expr {
        Expr::And(list) if !list.is_empty() => list,
        _ => return Err(VerifyError::new(REASON_IR_STATIC_CHECK_FAILED)),
    };
    let mut non_safe = Vec::new();
    let mut has_safe = false;
    for child in list {
        if matches!(child, Expr::Safe) {
            has_safe = true;
        } else {
            non_safe.push(child.clone());
        }
    }
    if !has_safe {
        return Err(VerifyError::new(REASON_IR_STATIC_CHECK_FAILED));
    }
    Ok(non_safe)
}

fn compose_conditions(list: Vec<Expr>) -> Expr {
    match list.len() {
        0 => Expr::Bool(true),
        1 => list[0].clone(),
        _ => Expr::And(list),
    }
}

fn extract_accept_cond(expr: &Expr) -> Result<Expr, VerifyError> {
    let non_safe = accept_non_safe_children(expr)?;
    Ok(compose_conditions(non_safe))
}

fn check_dominance(
    parent_dir: &Path,
    candidate_cond: &Expr,
    bundle_dir: &Path,
    ruleset_hash: &str,
    meta_hash: &str,
    ir_limits: &IrLimits,
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
    manifest: &Manifest,
) -> Result<(), VerifyError> {
    let (_, parent_accept_expr) = load_ir(parent_dir.join("ruleset/accept.ir.json"))?;
    let parent_cond = extract_accept_cond(&parent_accept_expr)?;

    let candidate_or = match candidate_cond {
        Expr::Or(list) if list.len() == 2 => list,
        _ => {
            return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED)
                .with_detail("stage", GcjValue::Str("candidate_or".to_string())))
        }
    };
    let parent_cond_hash = sha256(&canonical_bytes(&expr_to_gcj(&parent_cond)));
    let cand_a_hash = sha256(&canonical_bytes(&expr_to_gcj(&candidate_or[0])));
    let cand_b_hash = sha256(&canonical_bytes(&expr_to_gcj(&candidate_or[1])));
    let (cond_a, cond_extra) = if parent_cond_hash == cand_a_hash {
        (&candidate_or[0], &candidate_or[1])
    } else if parent_cond_hash == cand_b_hash {
        (&candidate_or[1], &candidate_or[0])
    } else {
        return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED)
            .with_detail("stage", GcjValue::Str("cond_match".to_string())));
    };

    let witness = read_gcj(bundle_dir.join("proofs/dominance_witness.json"), REASON_DOMINANCE_CHECK_FAILED)?;
    let witness_obj = expect_object(&witness, REASON_DOMINANCE_CHECK_FAILED)?;
    let x_star_val = witness_obj
        .get("x_star")
        .ok_or_else(|| VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
            "stage",
            GcjValue::Str("x_star".to_string()),
        ))?;
    let state_a = witness_obj
        .get("state_a")
        .ok_or_else(|| VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
            "stage",
            GcjValue::Str("state_a".to_string()),
        ))?;
    let condextra_inputs = witness_obj
        .get("condextra_inputs")
        .ok_or_else(|| VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
            "stage",
            GcjValue::Str("condextra_inputs".to_string()),
        ))?;

    let condextra_obj = expect_object(condextra_inputs, REASON_DOMINANCE_CHECK_FAILED)
        .map_err(|e| e.with_detail("stage", GcjValue::Str("condextra_object".to_string())))?;
    let blob_hashes_val = condextra_obj
        .get("blob_hashes")
        .ok_or_else(|| VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
            "stage",
            GcjValue::Str("condextra_blob_hashes".to_string()),
        ))?;
    let blob_hashes = match blob_hashes_val {
        GcjValue::Array(arr) => arr,
        _ => {
            return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED)
                .with_detail("stage", GcjValue::Str("condextra_blob_hashes_type".to_string())))
        }
    };
    let mut allowed_hashes = BTreeSet::new();
    for blob in &manifest.blobs {
        allowed_hashes.insert(blob.sha256.clone());
    }
    for item in blob_hashes {
        match item {
            GcjValue::Str(s) if is_hex_64(s) => {
                if !allowed_hashes.contains(s) {
                    return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
                        "stage",
                        GcjValue::Str("condextra_blob_missing".to_string()),
                    ));
                }
            }
            _ => {
                return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED).with_detail(
                    "stage",
                    GcjValue::Str("condextra_blob_invalid".to_string()),
                ))
            }
        }
    }

    let x_star = value_from_gcj(x_star_val);
    let state_a_val = value_from_gcj(state_a);
    let condextra_val = value_from_gcj(condextra_inputs);

    let safe_fn = build_safe_fn(bundle_dir, ruleset_hash, meta_hash, state_schema_hash, toolchain_merkle_root)?;

    let mut ctx_a = EvalContext {
        vars: env_with(&x_star, &state_a_val),
        gas: GasCounter::new(ir_limits.max_gas),
        safe_fn: &safe_fn,
    };
    let res_a = eval(cond_a, &mut ctx_a).map_err(|e| map_ir_error(e))?;

    let mut ctx_b = EvalContext {
        vars: env_with(&x_star, &condextra_val),
        gas: GasCounter::new(ir_limits.max_gas),
        safe_fn: &safe_fn,
    };
    let res_b = eval(cond_extra, &mut ctx_b).map_err(|e| map_ir_error(e))?;

    if !matches!(res_a, Value::Bool(false)) {
        return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED)
            .with_detail("stage", GcjValue::Str("condA".to_string())));
    }
    if !matches!(res_b, Value::Bool(true)) {
        return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED)
            .with_detail("stage", GcjValue::Str("condExtra".to_string())));
    }

    Ok(())
}

fn check_migration(
    bundle_dir: &Path,
    migrate_expr: &Expr,
    ir_limits: &IrLimits,
    meta_hash: &str,
    ruleset_hash: &str,
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
) -> Result<(), VerifyError> {
    let states = ["state_small.json", "state_edge.json"];
    let safe_fn = build_safe_fn(bundle_dir, ruleset_hash, meta_hash, state_schema_hash, toolchain_merkle_root)?;

    for name in states {
        let state_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(name);
        let state_bytes = read_file(&state_path, REASON_MIGRATION_FAILED)?;
        let state_gcj = parse_gcj(&state_bytes).map_err(|_| VerifyError::new(REASON_MIGRATION_FAILED))?;
        let state_val = value_from_gcj(&state_gcj);

        let mut ctx = EvalContext {
            vars: env_with(&Value::Map(BTreeMap::new()), &state_val),
            gas: GasCounter::new(ir_limits.max_gas),
            safe_fn: &safe_fn,
        };

        let result = eval(migrate_expr, &mut ctx).map_err(|e| map_ir_error(e))?;
        if !is_state_value(&result) {
            return Err(VerifyError::new(REASON_MIGRATION_FAILED));
        }
    }
    Ok(())
}

fn build_safe_fn(
    bundle_dir: &Path,
    ruleset_hash: &str,
    meta_hash: &str,
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
) -> Result<impl Fn(&Value, &Value) -> Result<bool, IrError>, VerifyError> {
    let bundle_hash = compute_bundle_hash_from_dir(bundle_dir, state_schema_hash, toolchain_merkle_root)?;
    let bundle_hex = to_hex(&bundle_hash);
    let ruleset_hash = ruleset_hash.to_string();
    let meta_hash = meta_hash.to_string();

    Ok(move |x: &Value, _state: &Value| match x {
        Value::Map(map) => {
            let bundle_val = map.get("bundle_hash");
            let ruleset_val = map.get("ruleset_hash");
            let meta_val = map.get("meta_hash");
            let ok = match (bundle_val, ruleset_val, meta_val) {
                (Some(Value::Str(b)), Some(Value::Str(r)), Some(Value::Str(m))) => {
                    is_hex_64(b)
                        && is_hex_64(r)
                        && is_hex_64(m)
                        && b == &bundle_hex
                        && r == &ruleset_hash
                        && m == &meta_hash
                }
                _ => false,
            };
            Ok(ok)
        }
        _ => Ok(false),
    })
}

fn compute_bundle_hash_from_dir(
    bundle_dir: &Path,
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
) -> Result<[u8; 32], VerifyError> {
    let manifest_bytes = read_file(&bundle_dir.join("constitution.manifest.json"), REASON_BUNDLE_HASH_MISMATCH)?;
    let manifest_gcj = parse_gcj(&manifest_bytes).map_err(|_| VerifyError::new(REASON_BUNDLE_HASH_MISMATCH))?;
    let manifest = parse_manifest(&manifest_gcj).map_err(|_| VerifyError::new(REASON_BUNDLE_HASH_MISMATCH))?;
    let state_schema_hex = to_hex(state_schema_hash);
    let toolchain_hex = to_hex(toolchain_merkle_root);
    if manifest.state_schema_hash != state_schema_hex {
        return Err(VerifyError::new(REASON_BUNDLE_HASH_MISMATCH));
    }
    if manifest.toolchain_merkle_root != toolchain_hex {
        return Err(VerifyError::new(REASON_BUNDLE_HASH_MISMATCH));
    }
    let manifest_hash = manifest_hash_for_bundle(&manifest_gcj)?;
    let _blob_hashes = verify_blobs(bundle_dir, &manifest, &Policy {
        max_blobs: u64::MAX,
        max_blob_bytes: u64::MAX,
        max_proof_bytes: u64::MAX,
        allowed_extensions: vec![".json".to_string(), ".ir.json".to_string()],
    })?;

    let (accept_bytes, _accept_expr) = load_ir(bundle_dir.join("ruleset/accept.ir.json"))?;
    let (cost_bytes, _cost_expr) = load_ir(bundle_dir.join("ruleset/costvec.ir.json"))?;
    let (migrate_bytes, _migrate_expr) = load_ir(bundle_dir.join("ruleset/migrate.ir.json"))?;
    let ruleset_hash = compute_ruleset_hash(&accept_bytes, &cost_bytes, &migrate_bytes);

    let proof_manifest_path = bundle_dir.join("proofs/proof_bundle.manifest.json");
    let proof_manifest_bytes = read_file(&proof_manifest_path, REASON_BUNDLE_HASH_MISMATCH)?;
    let proof_hash = sha256(&canonicalize_bytes(&proof_manifest_bytes).map_err(|_| VerifyError::new(REASON_BUNDLE_HASH_MISMATCH))?);

    let migration_hash = sha256(&migrate_bytes);

    Ok(compute_bundle_hash(
        &manifest_hash,
        &ruleset_hash,
        &proof_hash,
        &migration_hash,
        state_schema_hash,
        toolchain_merkle_root,
    ))
}

fn verify_parent_bundle(
    parent_dir: &Path,
    expected_hash: &str,
    state_schema_hash: &[u8; 32],
    toolchain_merkle_root: &[u8; 32],
) -> Result<String, VerifyError> {
    let computed = compute_bundle_hash_from_dir(parent_dir, state_schema_hash, toolchain_merkle_root)?;
    let hex = to_hex(&computed);
    if hex != expected_hash {
        return Err(VerifyError::new(REASON_DOMINANCE_CHECK_FAILED));
    }
    Ok(hex)
}

fn is_state_value(value: &Value) -> bool {
    match value {
        Value::Int(_) | Value::Bool(_) | Value::Str(_) => true,
        Value::Bytes(_) => false,
        Value::List(items) => items.iter().all(is_state_value),
        Value::Map(map) => map.values().all(is_state_value),
        Value::Null => false,
    }
}

fn map_ir_error(err: IrError) -> VerifyError {
    match err {
        IrError::Eval(msg) if msg.contains("gas limit") => VerifyError::new(REASON_GAS_LIMIT_EXCEEDED),
        IrError::Eval(_) => VerifyError::new(REASON_IR_RUNTIME_ERROR),
        IrError::Parse(_) => VerifyError::new(REASON_IR_PARSE_ERROR),
    }
}

fn read_gcj(path: PathBuf, reason: &str) -> Result<GcjValue, VerifyError> {
    let bytes = read_file(&path, reason)?;
    parse_gcj(&bytes).map_err(|_| VerifyError::new(reason))
}

fn compute_kernel_hash() -> Result<String, VerifyError> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("KERNEL_HASH");
    let expected = read_file_string(&path, REASON_KERNEL_INTERNAL_ERROR)?;
    if !is_hex_64(&expected) {
        return Err(VerifyError::new(REASON_KERNEL_INTERNAL_ERROR));
    }
    Ok(expected)
}

fn compute_meta_hash(meta_dir: &Path) -> Result<String, VerifyError> {
    let mut parts = Vec::new();
    parts.extend_from_slice(b"META_V1\0");

    let spec_files = [
        "metaconst.json",
        "policy.json",
        "costvec.json",
        "ir_limits.json",
        "statement_set.json",
    ];

    for name in spec_files.iter() {
        let path = meta_dir.join("spec").join(name);
        let bytes = fs::read(path).map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))?;
        parts.extend_from_slice(&sha256(&bytes));
    }

    let schema_dir = meta_dir.join("schemas");
    let mut schema_paths = Vec::new();
    collect_schema_files(&schema_dir, &mut schema_paths)?;
    schema_paths.sort();
    for rel in schema_paths {
        let bytes = fs::read(meta_dir.join(rel)).map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))?;
        parts.extend_from_slice(&sha256(&bytes));
    }

    Ok(sha256_hex(&parts))
}

fn compute_state_schema_hash(meta_dir: &Path) -> Result<String, VerifyError> {
    let path = meta_dir.join("schemas/migration.schema.json");
    let bytes = fs::read(&path).map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))?;
    Ok(sha256_hex(&bytes))
}

fn compute_toolchain_merkle_root(meta_dir: &Path) -> Result<String, VerifyError> {
    let root = meta_dir
        .parent()
        .and_then(|p| p.parent())
        .ok_or_else(|| VerifyError::new(REASON_KERNEL_INTERNAL_ERROR))?;

    let mut entries: Vec<(String, GcjValue)> = Vec::new();
    for rel in TOOLCHAIN_FILES {
        let path = root.join(rel);
        let bytes = fs::read(&path).map_err(|_| VerifyError::new(REASON_KERNEL_INTERNAL_ERROR))?;
        let sha = sha256(&bytes);
        let mut obj = BTreeMap::new();
        obj.insert("path".to_string(), GcjValue::Str((*rel).to_string()));
        obj.insert("sha256".to_string(), GcjValue::Str(to_hex(&sha)));
        obj.insert("bytes".to_string(), GcjValue::Int(bytes.len() as i64));
        entries.push((rel.to_string(), GcjValue::Object(obj)));
    }
    entries.sort_by(|a, b| a.0.cmp(&b.0));
    let files: Vec<GcjValue> = entries.into_iter().map(|(_, v)| v).collect();

    let mut obj = BTreeMap::new();
    obj.insert("version".to_string(), GcjValue::Int(1));
    obj.insert("files".to_string(), GcjValue::Array(files));
    let root_hash = sha256(&canonical_bytes(&GcjValue::Object(obj)));
    Ok(to_hex(&root_hash))
}

fn collect_schema_files(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), VerifyError> {
    for entry in fs::read_dir(dir).map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))? {
        let entry = entry.map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))?;
        let path = entry.path();
        if path.is_dir() {
            collect_schema_files(&path, out)?;
        } else if path.extension().and_then(|s| s.to_str()) == Some("json") {
            let rel = path.strip_prefix(dir.parent().unwrap()).map_err(|_| VerifyError::new(REASON_META_HASH_MISMATCH))?;
            out.push(rel.to_path_buf());
        }
    }
    Ok(())
}

fn read_file(path: &Path, reason: &str) -> Result<Vec<u8>, VerifyError> {
    fs::read(path).map_err(|_| VerifyError::new(reason))
}

fn read_file_string(path: &Path, reason: &str) -> Result<String, VerifyError> {
    let bytes = read_file(path, reason)?;
    let s = String::from_utf8(bytes).map_err(|_| VerifyError::new(reason))?;
    Ok(s.trim().to_string())
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

fn env_with(x: &Value, state: &Value) -> BTreeMap<String, Value> {
    let mut map = BTreeMap::new();
    map.insert("x".to_string(), x.clone());
    map.insert("state".to_string(), state.clone());
    map
}

fn expect_object<'a>(value: &'a GcjValue, reason: &str) -> Result<&'a BTreeMap<String, GcjValue>, VerifyError> {
    match value {
        GcjValue::Object(map) => Ok(map),
        _ => Err(VerifyError::new(reason)),
    }
}

fn expect_u64(value: Option<&GcjValue>, reason: &str) -> Result<u64, VerifyError> {
    match value {
        Some(GcjValue::Int(i)) if *i >= 0 => Ok(*i as u64),
        _ => Err(VerifyError::new(reason)),
    }
}

fn expect_i64(value: Option<&GcjValue>, reason: &str) -> Result<i64, VerifyError> {
    match value {
        Some(GcjValue::Int(i)) => Ok(*i),
        _ => Err(VerifyError::new(reason)),
    }
}
