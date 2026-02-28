use baremetal_lgp::apf3::aal_exec::AALExecutor;
use baremetal_lgp::apf3::aal_ir::{
    AALGraph, ActParamTemplate, NodeId, NodeKind, ParamBankSpec, ParamInit, ParamRef, ParamSpec,
    ValueTy,
};
use baremetal_lgp::apf3::metachunkpack::{Chunk, MetaChunkPack};
use baremetal_lgp::apf3::morphisms::{
    identity_check, AllowedMorphisms, ArchitectureDiff, Morphism, ResidualTemplate,
};

fn base_graph() -> AALGraph {
    AALGraph {
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
            (NodeId(2), NodeKind::ActTanh),
            (
                NodeId(3),
                NodeKind::Linear {
                    in_len: 1,
                    out_len: 1,
                    w: ParamRef(2),
                    b: ParamRef(3),
                },
            ),
        ],
        edges: vec![
            baremetal_lgp::apf3::aal_ir::Edge {
                src: (NodeId(0), 0),
                dst: (NodeId(1), 0),
            },
            baremetal_lgp::apf3::aal_ir::Edge {
                src: (NodeId(1), 0),
                dst: (NodeId(2), 0),
            },
            baremetal_lgp::apf3::aal_ir::Edge {
                src: (NodeId(0), 0),
                dst: (NodeId(3), 0),
            },
        ],
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
        outputs: vec![(NodeId(2), 0)],
    }
}

#[test]
fn apf3_identity_gate_accepts_allowed_morphisms() {
    let base = base_graph();
    base.validate().expect("base graph valid");

    let probe = vec![MetaChunkPack::new(
        1,
        vec![Chunk {
            x: vec![0.5],
            y: vec![0.0],
            meta: vec![],
        }],
        vec![Chunk {
            x: vec![0.5],
            y: vec![0.0],
            meta: vec![],
        }],
        11,
    )];

    let diffs = vec![
        ArchitectureDiff {
            version: 1,
            base_graph: base.digest(),
            morphisms: vec![Morphism::InsertResidualBlock {
                anchor: (NodeId(2), 0),
                template: ResidualTemplate::LinearActLinear {
                    hidden: 2,
                    act: baremetal_lgp::apf3::aal_ir::ActKind::Tanh,
                },
                alpha_init: 0.0,
            }],
        },
        ArchitectureDiff {
            version: 1,
            base_graph: base.digest(),
            morphisms: vec![Morphism::WidenLayer {
                layer: NodeId(3),
                add_out: 1,
            }],
        },
        ArchitectureDiff {
            version: 1,
            base_graph: base.digest(),
            morphisms: vec![Morphism::AddMemorySlot {
                len: 8,
                init_closed: true,
            }],
        },
        ArchitectureDiff {
            version: 1,
            base_graph: base.digest(),
            morphisms: vec![Morphism::AddHead {
                anchor: NodeId(1),
                head_dim: 2,
                init_zero: true,
            }],
        },
        ArchitectureDiff {
            version: 1,
            base_graph: base.digest(),
            morphisms: vec![Morphism::SwapActivationIdentityApprox {
                node: NodeId(2),
                new_act: ActParamTemplate {
                    a: 1.0,
                    b: 0.0,
                    c: 1.0,
                },
            }],
        },
    ];

    let mut exec = AALExecutor::default();
    for diff in diffs {
        diff.validate_against_graph(&AllowedMorphisms::default(), &base)
            .expect("diff should validate");
        let after = diff.apply(&base, None).expect("apply diff");
        identity_check(&mut exec, &base, &after, &probe, 1e-6, None)
            .expect("identity gate should pass");
    }
}
