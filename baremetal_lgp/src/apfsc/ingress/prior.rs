use std::collections::BTreeSet;
use std::fs;
use std::path::Path;

use crate::apfsc::artifacts::{copy_file, digest_file, ensure_layout, pack_dir};
use crate::apfsc::candidate::default_resource_envelope;
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use crate::apfsc::ingress::reality::refresh_active_snapshot;
use crate::apfsc::ingress::receipts::write_ingress_receipt;
use crate::apfsc::protocol::now_unix_s;
use crate::apfsc::scir::ast::{ProgramOutputs, ScirBounds, ScirNode, ScirOp, ScirProgram};
use crate::apfsc::scir::verify::verify_program;
use crate::apfsc::types::{IngressReceipt, PackKind};

pub fn ingest_prior(
    root: &Path,
    cfg: &Phase1Config,
    manifest_path: &Path,
) -> Result<IngressReceipt> {
    ensure_layout(root)?;

    let raw_manifest = load_pack_manifest(manifest_path)?;
    if raw_manifest.pack_kind != PackKind::Prior {
        return Err(ApfscError::Validation(
            "manifest pack_kind must be Prior".to_string(),
        ));
    }

    let base_dir = manifest_path
        .parent()
        .ok_or_else(|| ApfscError::Validation("manifest path missing parent".to_string()))?;
    let ops_src = base_dir.join("ops.json");
    let macros_src = base_dir.join("macros.json");

    if !ops_src.exists() || !macros_src.exists() {
        return Err(ApfscError::Missing(
            "prior pack requires ops.json and macros.json".to_string(),
        ));
    }

    let ops_hash = digest_file(&ops_src)?;
    let macros_hash = digest_file(&macros_src)?;
    let manifest = finalize_manifest(raw_manifest, vec![ops_hash, macros_hash])?;

    let ops_text = fs::read_to_string(&ops_src).map_err(|e| io_err(&ops_src, e))?;
    let macros_text = fs::read_to_string(&macros_src).map_err(|e| io_err(&macros_src, e))?;

    let ops_json: serde_json::Value = serde_json::from_str(&ops_text)?;
    let macros_json: serde_json::Value = serde_json::from_str(&macros_text)?;

    let op_names = extract_names(&ops_json, "ops")?;
    let macro_names = extract_names(&macros_json, "macros")?;

    validate_ops(&op_names)?;
    validate_macros(&macro_names)?;
    validate_macro_expansions(&macro_names)?;

    if op_names.is_empty() && macro_names.is_empty() {
        return Err(ApfscError::Validation(
            "prior proof-of-use failed: no legal op or macro".to_string(),
        ));
    }

    let pack_dst = pack_dir(root, PackKind::Prior, &manifest.pack_hash);
    fs::create_dir_all(&pack_dst).map_err(|e| io_err(&pack_dst, e))?;
    crate::apfsc::artifacts::write_json_atomic(&pack_dst.join("manifest.json"), &manifest)?;
    copy_file(&ops_src, &pack_dst.join("ops.json"))?;
    copy_file(&macros_src, &pack_dst.join("macros.json"))?;

    let checks = vec![
        "ops_map_to_supported_scir_ops".to_string(),
        "macros_expand_to_legal_scir_graphs".to_string(),
        "parameter_sizes_within_bounds".to_string(),
        "macro_expansion_deterministic".to_string(),
        "prior_proof_of_use".to_string(),
    ];
    let receipt = IngressReceipt {
        pack_hash: manifest.pack_hash,
        pack_kind: PackKind::Prior,
        validation_checks_passed: checks,
        ingest_time_unix_s: now_unix_s(),
        protocol_version: cfg.protocol.version.clone(),
        snapshot_included: true,
        family_id: None,
        family_kind: None,
        reality_role: None,
        variant_id: None,
    };

    write_ingress_receipt(root, &receipt)?;
    refresh_active_snapshot(root, cfg)?;
    Ok(receipt)
}

fn extract_names(v: &serde_json::Value, key: &str) -> Result<Vec<String>> {
    let arr = v
        .get(key)
        .and_then(|x| x.as_array())
        .ok_or_else(|| ApfscError::Validation(format!("missing {key} array")))?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        let name = item
            .as_str()
            .ok_or_else(|| ApfscError::Validation(format!("{key} entries must be strings")))?;
        out.push(name.to_string());
    }
    Ok(out)
}

fn validate_ops(op_names: &[String]) -> Result<()> {
    let allowed: BTreeSet<&'static str> = [
        "lag_1",
        "lag_2",
        "lag_4",
        "lag_8",
        "lag_16",
        "rolling_hash_2",
        "rolling_hash_3",
        "run_length_bucket",
        "mod_counter_2",
        "mod_counter_4",
        "mod_counter_8",
        "delimiter_reset_newline",
        "simple_scan_small",
        "simple_scan_medium",
        "hdc_bind",
        "hdc_bundle",
        "hdc_permute",
        "hdc_threshold",
        "sparse_event_queue",
        "sparse_router",
        "symbolic_stack",
        "symbolic_tape",
    ]
    .into_iter()
    .collect();
    for op in op_names {
        if !allowed.contains(op.as_str()) {
            return Err(ApfscError::Validation(format!(
                "unsupported prior op: {op}"
            )));
        }
    }
    Ok(())
}

fn validate_macros(macro_names: &[String]) -> Result<()> {
    let allowed: BTreeSet<&'static str> = [
        "copy_detector_macro",
        "periodicity_macro",
        "delimiter_segment_macro",
        "text_local_context_macro",
        "sidecar_memory_macro",
        "EventSparseAccumulator",
        "RingDelayTap",
        "SelectiveStateCell",
        "ResetOnDelimiter",
        "HdcAssociativeMemory",
        "SparseEventRouter",
        "SymbolicTapeExecutor",
    ]
    .into_iter()
    .collect();
    for m in macro_names {
        if !allowed.contains(m.as_str()) {
            return Err(ApfscError::Validation(format!(
                "unsupported prior macro: {m}"
            )));
        }
    }
    Ok(())
}

fn validate_macro_expansions(macro_names: &[String]) -> Result<()> {
    let env = default_resource_envelope();
    for name in macro_names {
        let op = match name.as_str() {
            "copy_detector_macro" => ScirOp::RunLengthBucket { buckets: 8 },
            "periodicity_macro" => ScirOp::ModCounter { modulus: 8 },
            "delimiter_segment_macro" => ScirOp::DelimiterReset { byte: b'\n' },
            "text_local_context_macro" => ScirOp::LagBytes {
                lags: vec![1, 2, 4, 8],
            },
            "sidecar_memory_macro" => ScirOp::ShiftRegister { width: 8 },
            "EventSparseAccumulator" => ScirOp::SimpleScan {
                in_dim: 8,
                hidden_dim: 16,
            },
            "RingDelayTap" => ScirOp::ShiftRegister { width: 16 },
            "SelectiveStateCell" => ScirOp::SimpleScan {
                in_dim: 8,
                hidden_dim: 12,
            },
            "ResetOnDelimiter" => ScirOp::DelimiterReset { byte: b'|' },
            "HdcAssociativeMemory" => ScirOp::HdcBundle,
            "SparseEventRouter" => ScirOp::SparseRouter {
                experts: 16,
                topk: 2,
            },
            "SymbolicTapeExecutor" => ScirOp::SymbolicTape { cells: 32 },
            _ => {
                return Err(ApfscError::Validation(format!(
                    "unsupported macro expansion for {name}"
                )));
            }
        };

        let out_dim = match &op {
            ScirOp::RunLengthBucket { buckets } => *buckets,
            ScirOp::ModCounter { modulus } => *modulus,
            ScirOp::DelimiterReset { .. } => 1,
            ScirOp::LagBytes { lags } => lags.len() as u32,
            ScirOp::ShiftRegister { width } => *width,
            ScirOp::SimpleScan { hidden_dim, .. } => *hidden_dim,
            ScirOp::HdcBind => 16,
            ScirOp::HdcBundle => 16,
            ScirOp::HdcPermute { .. } => 16,
            ScirOp::HdcThreshold { .. } => 16,
            ScirOp::SparseEventQueue { slots } => *slots,
            ScirOp::SparseRouter { experts, .. } => *experts,
            ScirOp::SymbolicStack { depth } => *depth,
            ScirOp::SymbolicTape { cells } => *cells,
            _ => 1,
        };

        let (macro_node_id, probe_node_id, mut nodes) = match &op {
            ScirOp::HdcBind | ScirOp::HdcBundle => (
                3u32,
                3u32,
                vec![
                    ScirNode {
                        id: 1,
                        op: ScirOp::ShiftRegister { width: out_dim },
                        inputs: Vec::new(),
                        out_dim,
                        mutable: false,
                    },
                    ScirNode {
                        id: 2,
                        op: ScirOp::RollingHash {
                            n: 4,
                            buckets: out_dim,
                        },
                        inputs: Vec::new(),
                        out_dim,
                        mutable: false,
                    },
                    ScirNode {
                        id: 3,
                        op: op.clone(),
                        inputs: vec![1, 2],
                        out_dim,
                        mutable: false,
                    },
                ],
            ),
            ScirOp::SparseRouter { .. } => (
                2u32,
                2u32,
                vec![
                    ScirNode {
                        id: 1,
                        op: ScirOp::ShiftRegister { width: 16 },
                        inputs: Vec::new(),
                        out_dim: 16,
                        mutable: false,
                    },
                    ScirNode {
                        id: 2,
                        op: op.clone(),
                        inputs: vec![1],
                        out_dim,
                        mutable: false,
                    },
                ],
            ),
            _ => (
                1u32,
                1u32,
                vec![ScirNode {
                    id: 1,
                    op: op.clone(),
                    inputs: Vec::new(),
                    out_dim,
                    mutable: false,
                }],
            ),
        };
        let linear_id = macro_node_id + 1;
        nodes.push(ScirNode {
            id: linear_id,
            op: ScirOp::Linear {
                in_dim: out_dim,
                out_dim,
                bias: false,
            },
            inputs: vec![macro_node_id],
            out_dim,
            mutable: false,
        });

        let program = ScirProgram {
            input_len: 256,
            nodes,
            outputs: ProgramOutputs {
                feature_node: linear_id,
                shadow_feature_nodes: Vec::new(),
                probe_nodes: vec![probe_node_id],
            },
            bounds: ScirBounds {
                max_state_bytes: env.max_state_bytes,
                max_param_bits: env.max_param_bits,
                max_steps: env.max_steps,
            },
        };
        verify_program(&program, &env)?;
    }
    Ok(())
}
