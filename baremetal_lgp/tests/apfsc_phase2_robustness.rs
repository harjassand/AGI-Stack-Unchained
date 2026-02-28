use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::candidate::clone_with_mutation;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::robustness::evaluate_robustness;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{EvalMode, PromotionClass};
use tempfile::tempdir;

fn fixtures_phase2() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase2")
}

fn phase2_config() -> Phase1Config {
    Phase1Config::from_path(&fixtures_phase2().join("config/phase2.toml")).expect("phase2 config")
}

fn ingest_all_phase2(root: &std::path::Path, cfg: &Phase1Config) {
    let dirs = [
        "reality_f0_det_base",
        "reality_f0_det_transfer",
        "reality_f0_det_robust",
        "reality_f1_text_base",
        "reality_f1_text_transfer",
        "reality_f1_text_robust",
        "reality_f2_sensor_base",
        "reality_f2_sensor_transfer",
        "reality_f2_sensor_robust",
        "reality_f3_phys_base",
        "reality_f3_phys_transfer",
        "reality_f3_phys_robust",
    ];
    for d in dirs {
        ingest_reality(root, cfg, &fixtures_phase2().join(d).join("manifest.json"))
            .expect("ingest reality");
    }
}

#[test]
fn phase2_robustness_has_no_adaptation_and_checks_protected_floors() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = phase2_config();

    seed_init(&root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("pack hashes");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");
    let mut strict_constellation = constellation.clone();
    for fam in &mut strict_constellation.family_specs {
        if fam.floors.protected {
            fam.floors.max_robust_regress_bpb = -1.0;
        }
    }

    let active_hash =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let active = baremetal_lgp::apfsc::candidate::load_candidate(&root, &active_hash)
        .expect("active candidate");

    let mut bad_heads = active.head_pack.clone();
    for w in &mut bad_heads.native_head.weights {
        *w = 0.0;
    }
    for b in &mut bad_heads.native_head.bias {
        *b = -25.0;
    }
    if let Some(v) = bad_heads.native_head.bias.first_mut() {
        *v = 25.0;
    }

    let bad = clone_with_mutation(
        &active,
        "truth",
        "robust_bad",
        PromotionClass::S,
        active.arch_program.clone(),
        bad_heads,
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
    .expect("bad clone");

    let before = bad.clone();
    let public = evaluate_robustness(
        &root,
        &bad,
        &active,
        &strict_constellation,
        EvalMode::Public,
    )
    .expect("public robust");
    let holdout = evaluate_robustness(
        &root,
        &bad,
        &active,
        &strict_constellation,
        EvalMode::Holdout,
    )
    .expect("holdout robust");

    assert_eq!(bad.arch_program, before.arch_program);
    assert_eq!(bad.state_pack, before.state_pack);
    assert_eq!(bad.head_pack, before.head_pack);

    assert!(public.receipt.weighted_robust_public_bpb.is_some());
    assert!(holdout.receipt.weighted_robust_holdout_bpb.is_some());
    assert_ne!(public.receipt.replay_hash, holdout.receipt.replay_hash);

    assert!(!holdout.protected_floor_failures.is_empty());
}
