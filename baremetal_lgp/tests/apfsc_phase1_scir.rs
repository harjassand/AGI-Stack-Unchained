use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, load_payload_index};
use baremetal_lgp::apfsc::bytecoder::score_panel;
use baremetal_lgp::apfsc::candidate::{default_resource_envelope, load_active_candidate};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::lanes::equivalence;
use baremetal_lgp::apfsc::scir::ast::{ProgramOutputs, ScirBounds, ScirNode, ScirOp, ScirProgram};
use baremetal_lgp::apfsc::scir::interp::run_program;
use baremetal_lgp::apfsc::scir::rewrite::widen_with_zero_channels;
use baremetal_lgp::apfsc::scir::verify::verify_program;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

#[test]
fn scir_verify_rejects_dynamic_allocation() {
    let mut env = default_resource_envelope();
    env.max_steps = 100;
    let p = ScirProgram {
        input_len: 4,
        nodes: vec![ScirNode {
            id: 1,
            op: ScirOp::ByteEmbedding { vocab: 256, dim: 4 },
            inputs: Vec::new(),
            out_dim: 0,
            mutable: false,
        }],
        outputs: ProgramOutputs {
            feature_node: 1,
            shadow_feature_nodes: Vec::new(),
            probe_nodes: Vec::new(),
        },
        bounds: ScirBounds {
            max_state_bytes: 1024,
            max_param_bits: 1024,
            max_steps: 100,
        },
    };

    let err = verify_program(&p, &env).expect_err("must reject");
    assert!(err.to_string().contains("dynamic/zero out_dim"));
}

#[test]
fn scir_verify_rejects_noncausal_edges() {
    let env = default_resource_envelope();
    let p = ScirProgram {
        input_len: 4,
        nodes: vec![
            ScirNode {
                id: 1,
                op: ScirOp::ByteEmbedding { vocab: 256, dim: 4 },
                inputs: Vec::new(),
                out_dim: 4,
                mutable: false,
            },
            ScirNode {
                id: 2,
                op: ScirOp::Linear {
                    in_dim: 4,
                    out_dim: 4,
                    bias: false,
                },
                inputs: vec![3],
                out_dim: 4,
                mutable: false,
            },
            ScirNode {
                id: 3,
                op: ScirOp::Linear {
                    in_dim: 4,
                    out_dim: 4,
                    bias: false,
                },
                inputs: vec![2],
                out_dim: 4,
                mutable: false,
            },
        ],
        outputs: ProgramOutputs {
            feature_node: 3,
            shadow_feature_nodes: Vec::new(),
            probe_nodes: Vec::new(),
        },
        bounds: ScirBounds {
            max_state_bytes: 1024,
            max_param_bits: 1024,
            max_steps: 100,
        },
    };

    let err = verify_program(&p, &env).expect_err("must reject");
    assert!(err.to_string().contains("noncausal") || err.to_string().contains("topological"));
}

#[test]
fn equivalence_widen_zero_channels_preserves_output() {
    let program = ScirProgram {
        input_len: 8,
        nodes: vec![
            ScirNode {
                id: 1,
                op: ScirOp::ByteEmbedding { vocab: 256, dim: 4 },
                inputs: Vec::new(),
                out_dim: 4,
                mutable: false,
            },
            ScirNode {
                id: 2,
                op: ScirOp::Linear {
                    in_dim: 4,
                    out_dim: 4,
                    bias: false,
                },
                inputs: vec![1],
                out_dim: 4,
                mutable: false,
            },
        ],
        outputs: ProgramOutputs {
            feature_node: 2,
            shadow_feature_nodes: Vec::new(),
            probe_nodes: Vec::new(),
        },
        bounds: ScirBounds {
            max_state_bytes: 1024,
            max_param_bits: 1024,
            max_steps: 100,
        },
    };

    let rew = widen_with_zero_channels(&program, 4).expect("rewrite");
    let input = b"abcdefgh";
    let a = run_program(&program, input).expect("run a");
    let b = run_program(&rew, input).expect("run b");
    assert_eq!(a.feature, b.feature);
}

#[test]
fn split_readout_zero_init_preserves_output() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();

    seed_init(&root, &cfg, Some(&fixtures()), true).expect("seed init");
    ingest_reality(
        &root,
        &cfg,
        &fixtures().join("reality_f0_det/manifest.json"),
    )
    .expect("ingest reality");

    let active = load_active_candidate(&root).expect("load active");
    let candidates = equivalence::generate(&active, &cfg).expect("generate equiv");
    let split = candidates
        .into_iter()
        .find(|c| c.build_meta.mutation_type == "split_readout_zero_init")
        .expect("split candidate");

    let bank = load_bank(&root, "F0").expect("bank");
    let windows: Vec<_> = bank.public.iter().take(8).cloned().collect();
    let payloads: BTreeMap<String, Vec<u8>> = load_payload_index(&root).expect("payload index");

    let parent_score = score_panel(&active.arch_program, &active.head_pack, &payloads, &windows)
        .expect("score parent");
    let split_score = score_panel(&split.arch_program, &split.head_pack, &payloads, &windows)
        .expect("score split");

    assert!((parent_score.total_bits - split_score.total_bits).abs() <= 1e-6);
}
