use std::collections::BTreeMap;

use baremetal_lgp::apfsc::scir::backend_equiv::evaluate_backend_equivalence;
use baremetal_lgp::apfsc::types::{
    AdaptHook, BackendKind, BoundSpec, ChannelDef, CoreBlock, CoreOp, ReadoutDef, ScheduleDef,
    SchedulerClass, ScirV2Program, StateSchema,
};

fn program_with_ops(ops: Vec<&str>) -> ScirV2Program {
    ScirV2Program {
        version: "scir-v2".to_string(),
        state_schema: StateSchema {
            schema_id: "s".to_string(),
            bytes: 128,
        },
        channels: vec![ChannelDef {
            id: "byte".to_string(),
            width: 1,
        }],
        core_blocks: vec![CoreBlock {
            id: "main".to_string(),
            ops: ops
                .into_iter()
                .map(|op| CoreOp {
                    op: op.to_string(),
                    args: BTreeMap::new(),
                })
                .collect(),
        }],
        macro_calls: Vec::new(),
        schedule: ScheduleDef {
            scheduler_class: SchedulerClass::SerialScan,
            backend_hint: BackendKind::GraphBackend,
        },
        readouts: vec![ReadoutDef {
            id: "o".to_string(),
            head: "native_head".to_string(),
        }],
        adapt_hooks: vec![AdaptHook {
            id: "h".to_string(),
            target: "nuisance_head".to_string(),
        }],
        bounds: BoundSpec {
            max_core_ops: 4096,
            max_state_bytes: 2 * 1024 * 1024,
            max_macro_calls: 16,
        },
    }
}

#[test]
fn graph_backend_equivalence_and_fallback_behavior() {
    let safe = program_with_ops(vec!["LinearMix", "StateUpdate", "HeadReadout"]);
    let windows = vec![
        b"abc123".to_vec(),
        b"zxy987".to_vec(),
        b"pqrst".to_vec(),
        b"uvw".to_vec(),
    ];

    let ok =
        evaluate_backend_equivalence("cand", "canon", "low", &safe, &windows, "snap", "cid", "v")
            .expect("equiv ok");
    assert!(ok.eligible);
    assert_eq!(ok.backend_kind, BackendKind::GraphBackend);
    assert_eq!(ok.max_abs_mass_diff_q16, 0);

    let unsafe_prog = program_with_ops(vec!["SlotRead", "HeadReadout"]);
    let bad = evaluate_backend_equivalence(
        "cand",
        "canon",
        "low",
        &unsafe_prog,
        &windows,
        "snap",
        "cid",
        "v",
    )
    .expect("equiv fallback");
    assert!(!bad.eligible);
    assert_eq!(bad.backend_kind, BackendKind::InterpTier0);
}
