use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::load_bank;
use baremetal_lgp::apfsc::canary::drain_queue;
use baremetal_lgp::apfsc::candidate::{clone_with_mutation, load_active_candidate, save_candidate};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::judge::PendingAdmission;
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::ingress::substrate::ingest_substrate;
use baremetal_lgp::apfsc::judge::run_batch;
use baremetal_lgp::apfsc::orchestrator::run_epoch;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{PromotionClass, WarmRefinementPack};
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

fn full_setup(root: &std::path::Path, cfg: &Phase1Config) {
    seed_init(root, cfg, Some(&fixtures()), true).expect("seed init");
    ingest_reality(root, cfg, &fixtures().join("reality_f0_det/manifest.json")).expect("ingest f0");
    ingest_reality(root, cfg, &fixtures().join("reality_f1_text/manifest.json"))
        .expect("ingest f1");
    ingest_prior(root, cfg, &fixtures().join("prior_seed/manifest.json")).expect("ingest prior");
    ingest_substrate(root, cfg, &fixtures().join("substrate_seed/manifest.json"))
        .expect("ingest substrate");
}

#[test]
fn phase1_seed_init_creates_active_candidate() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    let seed_hash = seed_init(&root, &cfg, Some(&fixtures()), true).expect("seed init");

    let active = fs::read_to_string(root.join("pointers/active_candidate")).expect("active ptr");
    assert_eq!(active.trim(), seed_hash);
}

#[test]
fn phase1_epoch_run_emits_receipts() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    full_setup(&root, &cfg);

    let report = run_epoch(&root, &cfg).expect("run epoch");
    assert!(!report.public_receipts.is_empty());
    assert!(!report.judge_report.receipts.is_empty());

    let public_dir = root.join("receipts/public");
    let judge_dir = root.join("receipts/judge");
    assert!(public_dir.exists());
    assert!(judge_dir.exists());
}

#[test]
fn phase1_replay_is_deterministic() {
    let tmp1 = tempdir().expect("tempdir1");
    let tmp2 = tempdir().expect("tempdir2");
    let root1 = tmp1.path().join(".apfsc");
    let root2 = tmp2.path().join(".apfsc");
    let cfg = Phase1Config::default();

    full_setup(&root1, &cfg);
    full_setup(&root2, &cfg);

    let r1 = run_epoch(&root1, &cfg).expect("epoch1");
    let r2 = run_epoch(&root2, &cfg).expect("epoch2");

    let p1: Vec<_> = r1
        .public_receipts
        .iter()
        .map(|r| {
            (
                r.candidate_hash.clone(),
                r.replay_hash.clone(),
                r.total_bits,
            )
        })
        .collect();
    let p2: Vec<_> = r2
        .public_receipts
        .iter()
        .map(|r| {
            (
                r.candidate_hash.clone(),
                r.replay_hash.clone(),
                r.total_bits,
            )
        })
        .collect();

    assert_eq!(p1, p2);

    let j1: Vec<_> = r1
        .judge_report
        .receipts
        .iter()
        .map(|r| (r.candidate_hash.clone(), r.reason.clone(), r.decision))
        .collect();
    let j2: Vec<_> = r2
        .judge_report
        .receipts
        .iter()
        .map(|r| (r.candidate_hash.clone(), r.reason.clone(), r.decision))
        .collect();
    assert_eq!(j1, j2);
}

#[test]
fn phase1_canary_activation_updates_pointers_atomically() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::default();
    full_setup(&root, &cfg);

    let active = load_active_candidate(&root).expect("active");
    let old_active_hash = active.manifest.candidate_hash.clone();

    cfg.judge.public_min_delta_bits = -1_000_000.0;
    cfg.judge.holdout_min_delta_bits = -1_000_000.0;
    cfg.judge.anchor_max_regress_bits = 1_000_000.0;
    cfg.judge.require_canary_for_a = true;

    let bridge = WarmRefinementPack {
        observable_map_hash: None,
        state_map_hash: None,
        tolerance_spec_hash: None,
        protected_head_ids: Vec::new(),
        protected_families: vec!["F0".to_string(), "F1".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "local_splice_v1".to_string(),
    };

    let cand = clone_with_mutation(
        &active,
        "incubator",
        "canary_pointer_case",
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

    let banks = vec![
        load_bank(&root, "F0").expect("bank f0"),
        load_bank(&root, "F1").expect("bank f1"),
    ];

    let _ = run_batch(
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

    let canary = drain_queue(&root, &banks, &cfg).expect("drain canary");
    assert_eq!(
        canary.activated.as_deref(),
        Some(cand.manifest.candidate_hash.as_str())
    );

    let new_active =
        fs::read_to_string(root.join("pointers/active_candidate")).expect("active ptr");
    let rollback =
        fs::read_to_string(root.join("pointers/rollback_candidate")).expect("rollback ptr");

    assert_eq!(new_active.trim(), cand.manifest.candidate_hash);
    assert_eq!(rollback.trim(), old_active_hash);
}
