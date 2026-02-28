use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, WindowBank};
use baremetal_lgp::apfsc::candidate::{
    clone_with_mutation, load_active_candidate, rehash_candidate, save_candidate,
};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::judge::PendingAdmission;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::judge::run_batch;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{JudgeDecision, PromotionClass, WarmRefinementPack};
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

fn setup() -> (
    tempfile::TempDir,
    std::path::PathBuf,
    Phase1Config,
    Vec<WindowBank>,
) {
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
    let banks = vec![load_bank(&root, "F0").expect("load bank")];
    (tmp, root, cfg, banks)
}

#[test]
fn judge_rejects_missing_snapshot() {
    let (_tmp, root, cfg, banks) = setup();
    let active = load_active_candidate(&root).expect("active");

    let mut cand = clone_with_mutation(
        &active,
        "truth",
        "missing_snapshot_case",
        PromotionClass::S,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
    .expect("clone");
    cand.manifest.snapshot_hash = "missing_snapshot".to_string();
    rehash_candidate(&mut cand).expect("rehash");
    save_candidate(&root, &cand).expect("save cand");

    let report = run_batch(
        &root,
        &active,
        vec![PendingAdmission {
            candidate_hash: cand.manifest.candidate_hash.clone(),
            snapshot_hash: cand.manifest.snapshot_hash.clone(),
            public_delta_bits: 100.0,
        }],
        &banks,
        &cfg,
    )
    .expect("run judge");

    let r = report.receipts.first().expect("receipt");
    assert_eq!(r.decision, JudgeDecision::Reject);
    assert!(r.reason.contains("MissingSnapshot"));
}

#[test]
fn judge_rejects_anchor_regression() {
    let (_tmp, root, mut cfg, banks) = setup();
    let active = load_active_candidate(&root).expect("active");

    cfg.judge.holdout_min_delta_bits = -1_000_000.0;
    cfg.judge.anchor_max_regress_bits = -0.1;

    let mut bad_heads = active.head_pack.clone();
    for w in &mut bad_heads.native_head.weights {
        *w = 0.0;
    }
    for w in &mut bad_heads.nuisance_head.weights {
        *w = 0.0;
    }
    for w in &mut bad_heads.residual_head.weights {
        *w = 0.0;
    }
    for b in &mut bad_heads.native_head.bias {
        *b = -50.0;
    }
    if let Some(first) = bad_heads.native_head.bias.first_mut() {
        *first = 50.0;
    }

    let cand = clone_with_mutation(
        &active,
        "truth",
        "anchor_regress_case",
        PromotionClass::S,
        active.arch_program.clone(),
        bad_heads,
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
    .expect("clone");
    save_candidate(&root, &cand).expect("save cand");

    let report = run_batch(
        &root,
        &active,
        vec![PendingAdmission {
            candidate_hash: cand.manifest.candidate_hash.clone(),
            snapshot_hash: cand.manifest.snapshot_hash.clone(),
            public_delta_bits: 100.0,
        }],
        &banks,
        &cfg,
    )
    .expect("run judge");

    let r = report.receipts.first().expect("receipt");
    assert_eq!(r.decision, JudgeDecision::Reject);
    assert!(r.reason.contains("AnchorRegress"));
}

#[test]
fn judge_requires_canary_for_a_class() {
    let (_tmp, root, mut cfg, banks) = setup();
    let active = load_active_candidate(&root).expect("active");

    cfg.judge.public_min_delta_bits = -1_000_000.0;
    cfg.judge.holdout_min_delta_bits = -1_000_000.0;
    cfg.judge.anchor_max_regress_bits = 1_000_000.0;

    let bridge = WarmRefinementPack {
        observable_map_hash: None,
        state_map_hash: None,
        tolerance_spec_hash: None,
        protected_head_ids: Vec::new(),
        protected_families: vec!["F0".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "local_splice_v1".to_string(),
    };

    let cand = clone_with_mutation(
        &active,
        "incubator",
        "a_class_case",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        Some(bridge),
        BTreeMap::new(),
    )
    .expect("clone");
    save_candidate(&root, &cand).expect("save cand");

    let report = run_batch(
        &root,
        &active,
        vec![PendingAdmission {
            candidate_hash: cand.manifest.candidate_hash.clone(),
            snapshot_hash: cand.manifest.snapshot_hash.clone(),
            public_delta_bits: 100.0,
        }],
        &banks,
        &cfg,
    )
    .expect("run judge");

    let r = report.receipts.first().expect("receipt");
    assert_eq!(r.decision, JudgeDecision::Promote);
    assert!(r.canary_required);
}

#[test]
fn judge_promotes_valid_candidate() {
    let (_tmp, root, mut cfg, banks) = setup();
    let active = load_active_candidate(&root).expect("active");

    cfg.judge.public_min_delta_bits = -1_000_000.0;
    cfg.judge.holdout_min_delta_bits = -1_000_000.0;
    cfg.judge.anchor_max_regress_bits = 1_000_000.0;
    cfg.judge.require_canary_for_a = true;

    let cand = clone_with_mutation(
        &active,
        "truth",
        "promote_valid_case",
        PromotionClass::S,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
    .expect("clone");
    save_candidate(&root, &cand).expect("save cand");

    let report = run_batch(
        &root,
        &active,
        vec![PendingAdmission {
            candidate_hash: cand.manifest.candidate_hash.clone(),
            snapshot_hash: cand.manifest.snapshot_hash.clone(),
            public_delta_bits: 100.0,
        }],
        &banks,
        &cfg,
    )
    .expect("run judge");

    let r = report.receipts.first().expect("receipt");
    assert_eq!(r.decision, JudgeDecision::Promote);
    assert!(!r.canary_required);
}
