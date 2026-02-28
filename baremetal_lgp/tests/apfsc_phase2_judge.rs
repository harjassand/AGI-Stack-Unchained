use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::candidate::clone_with_mutation;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::judge::{evaluate_phase2_candidate, judge_phase2_candidate};
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{JudgeDecision, PromotionClass, WarmRefinementPack};
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
fn phase2_judge_s_and_a_gates_and_ignores_challenge_stub() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = phase2_config();

    seed_init(&root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("pack hashes");
    let mut constellation =
        build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    constellation.normalization.public_static_margin_bpb = -1.0;
    constellation.normalization.holdout_static_margin_bpb = -1.0;
    constellation.normalization.holdout_transfer_margin_bpb = -1.0;
    constellation.normalization.holdout_robust_margin_bpb = -1.0;
    constellation.normalization.min_improved_families = 0;
    constellation
        .normalization
        .min_nonprotected_improved_families = 0;
    constellation.normalization.require_target_subset_hit = false;

    let active_hash =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let active = baremetal_lgp::apfsc::candidate::load_candidate(&root, &active_hash)
        .expect("active candidate");

    // S candidate can pass static-only gates with relaxed margins.
    let s_eval =
        evaluate_phase2_candidate(&root, &active, &active, &constellation).expect("s eval");
    let s_receipt = judge_phase2_candidate(&root, &active, &active, &constellation, &cfg, &s_eval)
        .expect("s judge");
    assert_eq!(s_receipt.decision, JudgeDecision::Promote);

    // A candidate fails when transfer/robust holdout gate is stricter.
    let bridge = WarmRefinementPack {
        observable_map_hash: None,
        state_map_hash: None,
        tolerance_spec_hash: None,
        protected_head_ids: Vec::new(),
        protected_families: vec!["det_micro".to_string(), "text_code".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "local_splice_v1".to_string(),
    };
    let a_candidate = clone_with_mutation(
        &active,
        "incubator",
        "a_candidate",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        Some(bridge),
        BTreeMap::new(),
    )
    .expect("a clone");

    let mut strict = constellation.clone();
    strict.normalization.holdout_transfer_margin_bpb = 1.0;

    let a_eval = evaluate_phase2_candidate(&root, &a_candidate, &active, &strict).expect("a eval");
    let a_receipt = judge_phase2_candidate(&root, &a_candidate, &active, &strict, &cfg, &a_eval)
        .expect("a judge");
    assert_eq!(a_receipt.decision, JudgeDecision::Reject);

    // Judge should not touch challenge-stub data in phase2.
    let bad_challenge = root
        .join("banks")
        .join("det_micro")
        .join("windows")
        .join("challenge_stub")
        .join("index.jsonl");
    std::fs::create_dir_all(bad_challenge.parent().expect("parent")).expect("mkdir");
    std::fs::write(&bad_challenge, b"not-json\n").expect("write bad challenge");

    let s_eval2 =
        evaluate_phase2_candidate(&root, &active, &active, &constellation).expect("s eval 2");
    let _ = judge_phase2_candidate(&root, &active, &active, &constellation, &cfg, &s_eval2)
        .expect("judge should ignore challenge stub");
}
