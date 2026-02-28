use std::collections::BTreeMap;

use baremetal_lgp::apfsc::artifacts::digest_json;
use baremetal_lgp::apfsc::macro_lib::build_seed_registry;
use baremetal_lgp::apfsc::scir::canonical::canonicalize_v2;
use baremetal_lgp::apfsc::scir::lower::lower_v2_with_macros;
use baremetal_lgp::apfsc::scir::verify::verify_scir_v2;
use baremetal_lgp::apfsc::types::{
    AdaptHook, BackendKind, BoundSpec, ChannelDef, CoreBlock, CoreOp, MacroCall, ReadoutDef,
    ScirV2Program, SchedulerClass, ScheduleDef, StateSchema,
};

fn sample_program_with_macro() -> ScirV2Program {
    ScirV2Program {
        version: "scir-v2".to_string(),
        state_schema: StateSchema {
            schema_id: "state".to_string(),
            bytes: 1024,
        },
        channels: vec![ChannelDef {
            id: "byte_in".to_string(),
            width: 1,
        }],
        core_blocks: vec![CoreBlock {
            id: "main".to_string(),
            ops: vec![CoreOp {
                op: "LinearMix".to_string(),
                args: BTreeMap::new(),
            }],
        }],
        macro_calls: vec![MacroCall {
            call_id: "m1".to_string(),
            macro_id: "EventSparseAccumulator".to_string(),
            arg_bindings: BTreeMap::new(),
            instance_seed: 7,
        }],
        schedule: ScheduleDef {
            scheduler_class: SchedulerClass::EventSparse,
            backend_hint: BackendKind::GraphBackend,
        },
        readouts: vec![ReadoutDef {
            id: "out".to_string(),
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
fn scir_v2_canonical_lower_verify_is_deterministic() {
    let registry = build_seed_registry("snap", "apfsc-phase3-mvp-v1", "seed").expect("registry");
    let p = sample_program_with_macro();

    let c1 = canonicalize_v2(p.clone());
    let c2 = canonicalize_v2(p);
    assert_eq!(digest_json(&c1).expect("hash1"), digest_json(&c2).expect("hash2"));

    let (l1, r1) = lower_v2_with_macros("cand", &c1, &registry).expect("lower 1");
    let (l2, r2) = lower_v2_with_macros("cand", &c2, &registry).expect("lower 2");
    verify_scir_v2(&l1).expect("verify 1");
    verify_scir_v2(&l2).expect("verify 2");

    assert_eq!(r1.lowered_hash, r2.lowered_hash);
    assert_eq!(r1.core_op_count, r2.core_op_count);
    assert_eq!(l1, l2);
}
