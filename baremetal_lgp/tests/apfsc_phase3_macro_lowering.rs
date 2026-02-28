use std::collections::BTreeMap;

use baremetal_lgp::apfsc::macro_lib::build_seed_registry;
use baremetal_lgp::apfsc::scir::canonical::canonicalize_v2;
use baremetal_lgp::apfsc::scir::lower::lower_v2_with_macros;
use baremetal_lgp::apfsc::types::{
    BackendKind, BoundSpec, ChannelDef, CoreBlock, CoreOp, MacroCall, MacroDef, MacroOriginKind,
    MacroRegistry, PortSpec, ReadoutDef, ScheduleDef, SchedulerClass, ScirV2Program, StateSchema,
};

fn base_program(macro_calls: Vec<MacroCall>) -> ScirV2Program {
    ScirV2Program {
        version: "scir-v2".to_string(),
        state_schema: StateSchema {
            schema_id: "state".to_string(),
            bytes: 256,
        },
        channels: vec![ChannelDef {
            id: "byte".to_string(),
            width: 1,
        }],
        core_blocks: vec![CoreBlock {
            id: "main".to_string(),
            ops: vec![CoreOp {
                op: "LinearMix".to_string(),
                args: BTreeMap::new(),
            }],
        }],
        macro_calls,
        schedule: ScheduleDef {
            scheduler_class: SchedulerClass::SerialScan,
            backend_hint: BackendKind::InterpTier0,
        },
        readouts: vec![ReadoutDef {
            id: "o".to_string(),
            head: "native_head".to_string(),
        }],
        adapt_hooks: Vec::new(),
        bounds: BoundSpec {
            max_core_ops: 4096,
            max_state_bytes: 2 * 1024 * 1024,
            max_macro_calls: 16,
        },
    }
}

#[test]
fn macro_lowering_is_deterministic_and_charged() {
    let reg = build_seed_registry("snap", "v", "seed").expect("registry");
    let with_macro = base_program(vec![MacroCall {
        call_id: "c1".to_string(),
        macro_id: "RingDelayTap".to_string(),
        arg_bindings: BTreeMap::new(),
        instance_seed: 1,
    }]);
    let no_macro = base_program(Vec::new());

    let (_, with_receipt1) =
        lower_v2_with_macros("cand", &canonicalize_v2(with_macro.clone()), &reg).expect("lower1");
    let (_, with_receipt2) =
        lower_v2_with_macros("cand", &canonicalize_v2(with_macro), &reg).expect("lower2");
    let (_, no_receipt) =
        lower_v2_with_macros("cand", &canonicalize_v2(no_macro), &reg).expect("lower no macro");

    assert_eq!(with_receipt1.lowered_hash, with_receipt2.lowered_hash);
    assert!(with_receipt1.core_op_count > no_receipt.core_op_count);
}

#[test]
fn recursive_macro_is_rejected() {
    let recursive_macro = MacroDef {
        macro_id: "Recursive".to_string(),
        version: 1,
        origin_kind: MacroOriginKind::SeedPrior,
        origin_hash: "seed".to_string(),
        input_ports: vec![PortSpec {
            name: "x".to_string(),
            width: 1,
        }],
        output_ports: vec![PortSpec {
            name: "y".to_string(),
            width: 1,
        }],
        local_state_bytes: 0,
        expansion_hash: "h".to_string(),
        expansion_core: vec![CoreOp {
            op: "RecursiveCall".to_string(),
            args: BTreeMap::new(),
        }],
        max_expansion_ops: 1,
        canonical_hash: "c".to_string(),
    };
    let reg = MacroRegistry {
        registry_id: "r".to_string(),
        snapshot_hash: "s".to_string(),
        macro_defs: vec![recursive_macro],
        protocol_version: "v".to_string(),
        manifest_hash: "m".to_string(),
    };

    let p = base_program(vec![MacroCall {
        call_id: "c1".to_string(),
        macro_id: "Recursive".to_string(),
        arg_bindings: BTreeMap::new(),
        instance_seed: 0,
    }]);

    assert!(lower_v2_with_macros("cand", &p, &reg).is_err());
}
