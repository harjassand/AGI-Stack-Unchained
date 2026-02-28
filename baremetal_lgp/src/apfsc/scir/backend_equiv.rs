use crate::apfsc::errors::Result;
use crate::apfsc::scir::graph_backend::{Apf3GraphBackendAdapter, GraphBackendAdapter};
use crate::apfsc::scir::interp::run_program_v2;
use crate::apfsc::types::{BackendEquivReceipt, BackendKind, ScirV2Program};

pub fn evaluate_backend_equivalence(
    candidate_hash: &str,
    canonical_hash: &str,
    lowered_hash: &str,
    program: &ScirV2Program,
    windows: &[Vec<u8>],
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<BackendEquivReceipt> {
    let adapter = Apf3GraphBackendAdapter;
    let plan = adapter.lower_program(program);
    let (eligible, reason) = match &plan {
        Ok(_) => (true, "Eligible".to_string()),
        Err(_) => (false, "InterpreterOnly".to_string()),
    };

    let mut witness_exact_match = true;
    let mut public_exact_match = true;
    let mut max_abs_mass_diff_q16 = 0u32;

    if let Ok(plan) = plan {
        for (ix, w) in windows.iter().enumerate() {
            let interp = run_program_v2(program, w)?;
            let graph = adapter.run_plan(&plan, w, program)?;
            let mut local_max = 0u32;
            for (a, b) in interp.iter().zip(graph.iter()) {
                let diff = a.abs_diff(*b) as u32;
                local_max = local_max.max(diff);
            }
            max_abs_mass_diff_q16 = max_abs_mass_diff_q16.max(local_max);
            let eq = local_max == 0;
            if ix < 4 {
                witness_exact_match &= eq;
            } else {
                public_exact_match &= eq;
            }
        }
    } else {
        witness_exact_match = false;
        public_exact_match = false;
    }

    let exact = witness_exact_match && public_exact_match && max_abs_mass_diff_q16 == 0;

    Ok(BackendEquivReceipt {
        candidate_hash: candidate_hash.to_string(),
        canonical_hash: canonical_hash.to_string(),
        lowered_hash: lowered_hash.to_string(),
        backend_kind: if eligible && exact {
            BackendKind::GraphBackend
        } else {
            BackendKind::InterpTier0
        },
        witness_exact_match,
        public_exact_match,
        max_abs_mass_diff_q16,
        eligible: eligible && exact,
        reason: if eligible && exact {
            reason
        } else {
            "FallbackInterp".to_string()
        },
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    })
}
