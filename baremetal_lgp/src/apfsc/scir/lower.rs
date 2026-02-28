use crate::apfsc::artifacts::digest_json;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{CoreBlock, LoweringReceipt, MacroRegistry, ScirV2Program};

pub fn lower_v2_with_macros(
    candidate_hash: &str,
    program: &ScirV2Program,
    registry: &MacroRegistry,
) -> Result<(ScirV2Program, LoweringReceipt)> {
    if program.macro_calls.len() as u32 > crate::apfsc::constants::MAX_MACRO_CALLS_PER_PROGRAM {
        return Err(ApfscError::Validation(
            crate::apfsc::types::JudgeRejectReason::MacroLoweringFail.as_reason(),
        ));
    }

    let mut lowered = program.clone();
    let mut added_core_blocks = Vec::new();
    for call in &program.macro_calls {
        let def = registry
            .macro_defs
            .iter()
            .find(|m| m.macro_id == call.macro_id)
            .ok_or_else(|| {
                ApfscError::Validation(format!(
                    "{}: unknown macro {}",
                    crate::apfsc::types::JudgeRejectReason::MacroLoweringFail.as_reason(),
                    call.macro_id
                ))
            })?;
        if def
            .expansion_core
            .iter()
            .any(|op| op.op == "MacroCall" || op.op == "RecursiveCall")
        {
            return Err(ApfscError::Validation(
                crate::apfsc::types::JudgeRejectReason::MacroLoweringFail.as_reason(),
            ));
        }
        if def.expansion_core.len() as u32 > crate::apfsc::constants::MAX_MACRO_EXPANSION_OPS {
            return Err(ApfscError::Validation(
                crate::apfsc::types::JudgeRejectReason::MacroLoweringFail.as_reason(),
            ));
        }
        added_core_blocks.push(CoreBlock {
            id: format!("macro_{}_{}", call.call_id, def.macro_id),
            ops: def.expansion_core.clone(),
        });
    }
    lowered.core_blocks.extend(added_core_blocks);
    lowered.macro_calls.clear();

    let canonical_hash = digest_json(program)?;
    let lowered_hash = digest_json(&lowered)?;
    let scir_hash = canonical_hash.clone();

    let core_op_count: u32 = lowered.core_blocks.iter().map(|b| b.ops.len() as u32).sum();
    let state_bytes_estimate = lowered.state_schema.bytes;
    let graph_backend_eligible = lowered
        .core_blocks
        .iter()
        .flat_map(|b| b.ops.iter())
        .all(|op| {
            matches!(
                op.op.as_str(),
                "LinearMix"
                    | "AffineBias"
                    | "ElementwiseGate"
                    | "StateUpdate"
                    | "ScanReduce"
                    | "HeadReadout"
            )
        });

    let receipt = LoweringReceipt {
        candidate_hash: candidate_hash.to_string(),
        scir_hash,
        canonical_hash,
        lowered_hash,
        macro_registry_hash: registry.registry_id.clone(),
        core_op_count,
        state_bytes_estimate,
        graph_backend_eligible,
        replay_hash: digest_json(&(candidate_hash, &lowered))?,
    };
    Ok((lowered, receipt))
}
