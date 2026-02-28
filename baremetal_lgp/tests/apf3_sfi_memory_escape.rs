#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use baremetal_lgp::apf3::aal_exec::{AALExecutor, ExecStop};
use baremetal_lgp::apf3::aal_ir::{
    AALGraph, NodeId, NodeKind, ParamBankSpec, ParamInit, ParamSpec, ValueTy,
};
use baremetal_lgp::apf3::metachunkpack::{Chunk, MetaChunkPack};
use baremetal_lgp::apf3::nativeblock::{NativeBlockRegistry, NativeBlockSpec};

#[test]
fn apf3_sfi_memory_escape_returns_nativeblock_failure_and_zero_score() {
    let mut registry = NativeBlockRegistry::new();

    // movz x1, #0 ; str w0, [x1] ; ret
    let spec = NativeBlockSpec {
        words: vec![0xD280_0001_u32, 0xB900_0020_u32, 0xD65F_03C0_u32],
        declared_stack: 0,
    };
    let digest = registry.install(&spec).expect("install native block");

    let graph = AALGraph {
        version: 1,
        nodes: vec![
            (
                NodeId(0),
                NodeKind::Input {
                    index: 0,
                    ty: ValueTy::VecF32 { len: 1 },
                },
            ),
            (
                NodeId(1),
                NodeKind::NativeBlock {
                    spec_digest: digest,
                    len: 1,
                },
            ),
        ],
        edges: vec![baremetal_lgp::apf3::aal_ir::Edge {
            src: (NodeId(0), 0),
            dst: (NodeId(1), 0),
        }],
        params: ParamBankSpec {
            params: vec![ParamSpec {
                len: 1,
                init: ParamInit::Zeros,
            }],
        },
        mem: vec![],
        outputs: vec![(NodeId(1), 0)],
    };

    let pack = MetaChunkPack::new(
        1,
        vec![],
        vec![Chunk {
            x: vec![1.0],
            y: vec![1.0],
            meta: vec![],
        }],
        3,
    );

    let exec = AALExecutor::default();
    let rep = exec.eval_pack(&graph, &pack, Some(&registry));

    assert!(
        matches!(
            rep.stop,
            ExecStop::NativeBlockFault | ExecStop::NativeBlockTimeout
        ),
        "expected native block fault/timeout, got {:?}",
        rep.stop
    );
    assert_eq!(rep.query_score_mean, 0.0);
    assert_eq!(rep.failure_label, Some("NativeBlockFailure"));
}
