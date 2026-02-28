use std::collections::{BTreeMap, BTreeSet};

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::{ScirOp, ScirProgram};
use crate::apfsc::types::{ResourceEnvelope, ScirV2Program};

#[derive(Debug, Clone, PartialEq)]
pub struct VerifySummary {
    pub estimated_state_bytes: u64,
    pub estimated_param_bits: u64,
    pub op_counts: BTreeMap<&'static str, u64>,
}

pub fn verify_program(program: &ScirProgram, env: &ResourceEnvelope) -> Result<VerifySummary> {
    if program.nodes.is_empty() {
        return Err(ApfscError::Validation(
            "SCIR program has no nodes".to_string(),
        ));
    }

    let mut dims: BTreeMap<u32, u32> = BTreeMap::new();
    let mut seen = BTreeSet::new();
    let mut simple_scan_count = 0u32;
    let mut op_counts: BTreeMap<&'static str, u64> = BTreeMap::new();
    let mut param_bits = 0u64;
    let mut state_bytes = 0u64;

    for node in &program.nodes {
        if !seen.insert(node.id) {
            return Err(ApfscError::Validation(format!(
                "duplicate node id {}",
                node.id
            )));
        }

        if node.out_dim == 0 {
            return Err(ApfscError::Validation(format!(
                "node {} has dynamic/zero out_dim",
                node.id
            )));
        }

        for input in &node.inputs {
            if !dims.contains_key(input) {
                return Err(ApfscError::Validation(format!(
                    "node {} has noncausal/unknown input {}",
                    node.id, input
                )));
            }
            if *input >= node.id {
                return Err(ApfscError::Validation(format!(
                    "node {} input {} violates topological order",
                    node.id, input
                )));
            }
        }

        let inferred = infer_node_dim(node, &dims)?;
        if inferred != node.out_dim {
            return Err(ApfscError::Validation(format!(
                "node {} out_dim mismatch: declared {}, inferred {}",
                node.id, node.out_dim, inferred
            )));
        }

        if let ScirOp::SimpleScan { .. } = node.op {
            simple_scan_count += 1;
            if simple_scan_count > 1 {
                return Err(ApfscError::Validation(
                    "more than one scan loop is not allowed".to_string(),
                ));
            }
        }

        let (op_name, p_bits, s_bytes) = op_costs(&node.op, node.out_dim);
        *op_counts.entry(op_name).or_insert(0) += 1;
        param_bits = param_bits.saturating_add(p_bits);
        state_bytes = state_bytes.saturating_add(s_bytes);

        dims.insert(node.id, node.out_dim);
    }

    if !dims.contains_key(&program.outputs.feature_node) {
        return Err(ApfscError::Validation(
            "feature_node output does not exist".to_string(),
        ));
    }

    for shadow in &program.outputs.shadow_feature_nodes {
        if !dims.contains_key(shadow) {
            return Err(ApfscError::Validation(format!(
                "shadow feature node {} missing",
                shadow
            )));
        }
    }

    let feature_op = program
        .nodes
        .iter()
        .find(|n| n.id == program.outputs.feature_node)
        .map(|n| &n.op);
    if matches!(feature_op, Some(ScirOp::ReadoutShadow { .. })) {
        return Err(ApfscError::Validation(
            "shadow heads cannot write into native path".to_string(),
        ));
    }

    if state_bytes > env.max_state_bytes {
        return Err(ApfscError::Validation(format!(
            "state bytes {} exceed envelope {}",
            state_bytes, env.max_state_bytes
        )));
    }
    if param_bits > env.max_param_bits {
        return Err(ApfscError::Validation(format!(
            "param bits {} exceed envelope {}",
            param_bits, env.max_param_bits
        )));
    }

    let steps = (program.nodes.len() as u64).saturating_mul(program.input_len as u64);
    if steps > env.max_steps {
        return Err(ApfscError::Validation(format!(
            "estimated steps {} exceed envelope {}",
            steps, env.max_steps
        )));
    }

    Ok(VerifySummary {
        estimated_state_bytes: state_bytes,
        estimated_param_bits: param_bits,
        op_counts,
    })
}

fn infer_node_dim(
    node: &crate::apfsc::scir::ast::ScirNode,
    dims: &BTreeMap<u32, u32>,
) -> Result<u32> {
    let d = match &node.op {
        ScirOp::ByteEmbedding { dim, .. } => *dim,
        ScirOp::LagBytes { lags } => {
            if lags.is_empty() {
                return Err(ApfscError::Validation(
                    "LagBytes requires at least one lag".to_string(),
                ));
            }
            lags.len() as u32
        }
        ScirOp::Linear { out_dim, .. } => *out_dim,
        ScirOp::Add | ScirOp::Mul => {
            if node.inputs.len() != 2 {
                return Err(ApfscError::Validation(
                    "Add/Mul require exactly two inputs".to_string(),
                ));
            }
            let a = dims
                .get(&node.inputs[0])
                .ok_or_else(|| ApfscError::Validation("missing input dim".to_string()))?;
            let b = dims
                .get(&node.inputs[1])
                .ok_or_else(|| ApfscError::Validation("missing input dim".to_string()))?;
            if a != b {
                return Err(ApfscError::Validation(
                    "Add/Mul dims must match".to_string(),
                ));
            }
            *a
        }
        ScirOp::Tanh | ScirOp::Sigmoid | ScirOp::Relu => {
            if node.inputs.len() != 1 {
                return Err(ApfscError::Validation(
                    "activation op requires one input".to_string(),
                ));
            }
            *dims
                .get(&node.inputs[0])
                .ok_or_else(|| ApfscError::Validation("missing input dim".to_string()))?
        }
        ScirOp::Concat => {
            if node.inputs.is_empty() {
                return Err(ApfscError::Validation("Concat requires inputs".to_string()));
            }
            let mut sum = 0u32;
            for i in &node.inputs {
                sum = sum.saturating_add(
                    *dims
                        .get(i)
                        .ok_or_else(|| ApfscError::Validation("missing input dim".to_string()))?,
                );
            }
            sum
        }
        ScirOp::ReduceMean | ScirOp::ReduceSum => 1,
        ScirOp::ShiftRegister { width } => *width,
        ScirOp::RunLengthBucket { buckets } => *buckets,
        ScirOp::ModCounter { modulus } => *modulus,
        ScirOp::RollingHash { buckets, .. } => *buckets,
        ScirOp::DelimiterReset { .. } => 1,
        ScirOp::SimpleScan { hidden_dim, .. } => *hidden_dim,
        ScirOp::ReadoutNative { in_dim } => *in_dim,
        ScirOp::ReadoutShadow { in_dim, .. } => *in_dim,
    };
    Ok(d)
}

fn op_costs(op: &ScirOp, out_dim: u32) -> (&'static str, u64, u64) {
    match op {
        ScirOp::ByteEmbedding { vocab, dim } => (
            "ByteEmbedding",
            (*vocab as u64) * (*dim as u64) * 32,
            (*dim as u64) * 4,
        ),
        ScirOp::LagBytes { lags } => ("LagBytes", 0, lags.len() as u64),
        ScirOp::Linear {
            in_dim,
            out_dim,
            bias,
        } => {
            let mut params = (*in_dim as u64) * (*out_dim as u64);
            if *bias {
                params += *out_dim as u64;
            }
            ("Linear", params * 32, (*out_dim as u64) * 4)
        }
        ScirOp::SimpleScan { hidden_dim, .. } => (
            "SimpleScan",
            (*hidden_dim as u64) * (*hidden_dim as u64) * 32,
            (*hidden_dim as u64) * 4,
        ),
        ScirOp::ReadoutNative { in_dim } => ("ReadoutNative", (*in_dim as u64) * 32, 0),
        ScirOp::ReadoutShadow { in_dim, .. } => ("ReadoutShadow", (*in_dim as u64) * 32, 0),
        ScirOp::ShiftRegister { width } => ("ShiftRegister", 0, *width as u64),
        ScirOp::RunLengthBucket { buckets } => ("RunLengthBucket", 0, *buckets as u64),
        ScirOp::ModCounter { modulus } => ("ModCounter", 0, *modulus as u64),
        ScirOp::RollingHash { buckets, .. } => ("RollingHash", 0, *buckets as u64),
        ScirOp::DelimiterReset { .. } => ("DelimiterReset", 0, 1),
        ScirOp::Concat => ("Concat", 0, out_dim as u64 * 4),
        ScirOp::Add => ("Add", 0, out_dim as u64 * 4),
        ScirOp::Mul => ("Mul", 0, out_dim as u64 * 4),
        ScirOp::Tanh => ("Tanh", 0, out_dim as u64 * 4),
        ScirOp::Sigmoid => ("Sigmoid", 0, out_dim as u64 * 4),
        ScirOp::Relu => ("Relu", 0, out_dim as u64 * 4),
        ScirOp::ReduceMean => ("ReduceMean", 0, 4),
        ScirOp::ReduceSum => ("ReduceSum", 0, 4),
    }
}

pub fn verify_scir_v2(program: &ScirV2Program) -> Result<()> {
    let core_ops: u32 = program.core_blocks.iter().map(|b| b.ops.len() as u32).sum();
    if core_ops > crate::apfsc::constants::MAX_SCIR_CORE_OPS {
        return Err(ApfscError::Validation(format!(
            "core op count {} exceeds {}",
            core_ops,
            crate::apfsc::constants::MAX_SCIR_CORE_OPS
        )));
    }
    if program.macro_calls.len() as u32 > crate::apfsc::constants::MAX_MACRO_CALLS_PER_PROGRAM {
        return Err(ApfscError::Validation(format!(
            "macro call count {} exceeds {}",
            program.macro_calls.len(),
            crate::apfsc::constants::MAX_MACRO_CALLS_PER_PROGRAM
        )));
    }
    if program.state_schema.bytes > crate::apfsc::constants::STATE_TILE_BYTES_MAX {
        return Err(ApfscError::Validation(format!(
            "state schema bytes {} exceed {}",
            program.state_schema.bytes,
            crate::apfsc::constants::STATE_TILE_BYTES_MAX
        )));
    }
    for b in &program.core_blocks {
        for op in &b.ops {
            if op.op == "MacroCall" || op.op == "RecursiveCall" {
                return Err(ApfscError::Validation(
                    "recursive macro form is forbidden in SCIR-v2".to_string(),
                ));
            }
        }
    }
    Ok(())
}
