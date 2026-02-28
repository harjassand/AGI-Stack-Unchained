use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::formal_policy::load_active_formal_policy;
use baremetal_lgp::apfsc::ingress::formal::ingest_formal;
use baremetal_lgp::apfsc::scir::ast::{ProgramOutputs, ScirBounds, ScirNode, ScirOp, ScirProgram};
use baremetal_lgp::apfsc::scir::verify::verify_program_with_formal_policy;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures_phase4() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase4")
}

fn phase4_config() -> Phase1Config {
    Phase1Config::from_path(&fixtures_phase4().join("config/phase4.toml")).expect("phase4 cfg")
}

#[test]
fn formal_pack_tightening_applies_and_denies_pattern() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let cfg = phase4_config();
    seed_init(&root, &cfg, None, true).expect("seed");

    let (_ing, receipt) = ingest_formal(
        &root,
        &cfg,
        &fixtures_phase4().join("formal/deny_unbounded_gather/manifest.json"),
    )
    .expect("ingest formal");

    assert!(receipt.applied);

    let policy = load_active_formal_policy(&root).expect("policy");
    let program = ScirProgram {
        input_len: 32,
        nodes: vec![ScirNode {
            id: 1,
            op: ScirOp::ShiftRegister { width: 4 },
            inputs: vec![],
            out_dim: 4,
            mutable: false,
        }],
        outputs: ProgramOutputs {
            feature_node: 1,
            shadow_feature_nodes: vec![],
            probe_nodes: vec![],
        },
        bounds: ScirBounds {
            max_state_bytes: 1024,
            max_param_bits: 1024,
            max_steps: 1024,
        },
    };

    let env = baremetal_lgp::apfsc::candidate::default_resource_envelope();
    let res = verify_program_with_formal_policy(&program, &env, &policy);
    assert!(res.is_err());
}
