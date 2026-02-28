use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::ast::{ScirNode, ScirOp, ScirProgram};

pub fn insert_identity_linear(program: &ScirProgram) -> Result<ScirProgram> {
    let mut out = program.clone();
    let feature_id = out.outputs.feature_node;
    let feature_dim = out
        .nodes
        .iter()
        .find(|n| n.id == feature_id)
        .ok_or_else(|| ApfscError::Validation("feature node missing".to_string()))?
        .out_dim;

    let next_id = out
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);

    out.nodes.push(ScirNode {
        id: next_id,
        op: ScirOp::Linear {
            in_dim: feature_dim,
            out_dim: feature_dim,
            bias: false,
        },
        inputs: vec![feature_id],
        out_dim: feature_dim,
        mutable: false,
    });
    out.outputs.feature_node = next_id;
    Ok(out)
}

pub fn remove_identity_linear(program: &ScirProgram) -> Result<ScirProgram> {
    let mut out = program.clone();
    let feature_id = out.outputs.feature_node;
    if let Some(node) = out.nodes.iter().find(|n| n.id == feature_id) {
        if let ScirOp::Linear {
            in_dim,
            out_dim,
            bias,
        } = node.op
        {
            if !node.mutable && !bias && in_dim == out_dim && node.inputs.len() == 1 {
                out.outputs.feature_node = node.inputs[0];
                return Ok(out);
            }
        }
    }
    Ok(out)
}

pub fn widen_with_zero_channels(program: &ScirProgram, extra: u32) -> Result<ScirProgram> {
    let mut out = program.clone();
    let base_feature = out.outputs.feature_node;
    let base_dim = out
        .nodes
        .iter()
        .find(|n| n.id == base_feature)
        .ok_or_else(|| ApfscError::Validation("feature node missing".to_string()))?
        .out_dim;

    // For MVP equivalence we attach an identity pass-through and keep native feature unchanged.
    let next_id = out
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);

    out.nodes.push(ScirNode {
        id: next_id,
        op: ScirOp::Linear {
            in_dim: base_dim,
            out_dim: base_dim,
            bias: false,
        },
        inputs: vec![base_feature],
        out_dim: base_dim,
        mutable: false,
    });
    // Preserve semantics by keeping base feature; widened channels are shadow-only metadata.
    if extra > 0 {
        out.outputs.shadow_feature_nodes.push(next_id);
    }
    Ok(out)
}

pub fn split_linear_identity(program: &ScirProgram) -> Result<ScirProgram> {
    let with_one = insert_identity_linear(program)?;
    insert_identity_linear(&with_one)
}
