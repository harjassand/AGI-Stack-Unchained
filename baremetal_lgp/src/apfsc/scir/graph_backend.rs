use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::scir::interp::run_program_v2;
use crate::apfsc::types::{BackendKind, ScirV2Program};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct GraphExecPlan {
    pub plan_hash: String,
    pub op_count: u32,
}

pub trait GraphBackendAdapter {
    fn lower_program(&self, prog: &ScirV2Program) -> Result<GraphExecPlan>;
    fn run_plan(
        &self,
        plan: &GraphExecPlan,
        window: &[u8],
        prog: &ScirV2Program,
    ) -> Result<Vec<u16>>;
}

#[derive(Debug, Clone, Default)]
pub struct Apf3GraphBackendAdapter;

impl GraphBackendAdapter for Apf3GraphBackendAdapter {
    fn lower_program(&self, prog: &ScirV2Program) -> Result<GraphExecPlan> {
        let graph_safe = prog
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
        if !graph_safe {
            return Err(ApfscError::Validation(
                crate::apfsc::types::JudgeRejectReason::UnsupportedBackendPlan.as_reason(),
            ));
        }
        let op_count: u32 = prog.core_blocks.iter().map(|b| b.ops.len() as u32).sum();
        Ok(GraphExecPlan {
            plan_hash: crate::apfsc::artifacts::digest_json(&(
                op_count,
                prog.schedule.scheduler_class,
            ))?,
            op_count,
        })
    }

    fn run_plan(
        &self,
        _plan: &GraphExecPlan,
        window: &[u8],
        prog: &ScirV2Program,
    ) -> Result<Vec<u16>> {
        // Phase-3 MVP adapter keeps semantics anchored to interpreter.
        run_program_v2(prog, window)
    }
}

pub fn backend_from_plan(eligible: bool) -> BackendKind {
    if eligible {
        BackendKind::GraphBackend
    } else {
        BackendKind::InterpTier0
    }
}
