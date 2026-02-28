use baremetal_lgp::apf3::aal_exec::{AALExecutor, ExecStop};
use baremetal_lgp::apf3::aal_ir::{
    AALGraph, NodeId, NodeKind, ParamBankSpec, ParamInit, ParamRef, ParamSpec, ValueTy,
};
use baremetal_lgp::apf3::metachunkpack::{Chunk, MetaChunkPack};

#[test]
fn apf3_support_updates_improve_query_loss() {
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
                NodeKind::Linear {
                    in_len: 1,
                    out_len: 1,
                    w: ParamRef(0),
                    b: ParamRef(1),
                },
            ),
            (
                NodeId(2),
                NodeKind::Target {
                    index: 0,
                    ty: ValueTy::VecF32 { len: 1 },
                },
            ),
            (
                NodeId(3),
                NodeKind::DeltaUpdate {
                    lr: 1.0,
                    w: ParamRef(0),
                    x: (NodeId(0), 0),
                    err: (NodeId(2), 0),
                },
            ),
        ],
        edges: vec![baremetal_lgp::apf3::aal_ir::Edge {
            src: (NodeId(0), 0),
            dst: (NodeId(1), 0),
        }],
        params: ParamBankSpec {
            params: vec![
                ParamSpec {
                    len: 1,
                    init: ParamInit::Zeros,
                },
                ParamSpec {
                    len: 1,
                    init: ParamInit::Zeros,
                },
            ],
        },
        mem: vec![],
        outputs: vec![(NodeId(1), 0)],
    };

    graph.validate().expect("graph must validate");

    let pack = MetaChunkPack::new(
        1,
        vec![Chunk {
            x: vec![1.0],
            y: vec![1.0],
            meta: vec![],
        }],
        vec![Chunk {
            x: vec![1.0],
            y: vec![1.0],
            meta: vec![],
        }],
        7,
    );

    let exec = AALExecutor::default();
    let rep = exec.eval_pack(&graph, &pack, None);
    assert_eq!(rep.stop, ExecStop::Ok);
    assert!(
        rep.query_loss_after_support < rep.query_loss_before_support,
        "expected support adaptation to reduce query loss: before={} after={}",
        rep.query_loss_before_support,
        rep.query_loss_after_support
    );
}
