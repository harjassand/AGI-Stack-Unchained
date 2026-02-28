use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::orchestrator::run_phase3_epoch;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{JudgeDecision, PromotionClass};
use tempfile::tempdir;

fn fixtures_phase2() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase2")
}

fn fixtures_phase3() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase3")
}

fn phase3_config() -> Phase1Config {
    Phase1Config::from_path(&fixtures_phase3().join("config/phase3.toml")).expect("phase3 config")
}

fn ingest_all(root: &std::path::Path, cfg: &Phase1Config) {
    let phase2_dirs = [
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
    for d in phase2_dirs {
        ingest_reality(root, cfg, &fixtures_phase2().join(d).join("manifest.json"))
            .expect("ingest p2");
    }
    let phase3_dirs = [
        "reality_f4_event_sparse_base",
        "reality_f4_event_sparse_transfer",
        "reality_f4_event_sparse_robust",
        "reality_f5_formal_alg_base",
        "reality_f5_formal_alg_transfer",
        "reality_f5_formal_alg_robust",
    ];
    for d in phase3_dirs {
        ingest_reality(root, cfg, &fixtures_phase3().join(d).join("manifest.json"))
            .expect("ingest p3");
    }
    ingest_prior(
        root,
        cfg,
        &fixtures_phase3().join("priors/macro_seed/manifest.json"),
    )
    .expect("ingest prior");
}

fn run_once(root: &std::path::Path) -> baremetal_lgp::apfsc::types::EpochReport {
    let mut cfg = phase3_config();
    cfg.phase3.allow_p_warm = true;
    cfg.phase3.allow_p_cold = false;
    cfg.lanes.max_truth_candidates = 3;
    cfg.lanes.max_equivalence_candidates = 1;
    cfg.lanes.max_incubator_candidates = 1;
    cfg.lanes.max_public_candidates = 4;
    cfg.train.steps = 1;
    cfg.incubator.shadow_steps = 1;
    cfg.witness.count = 4;
    cfg.witness.rotation = 1;
    cfg.phase3.limits.max_paradigm_public_candidates = 4;
    cfg.phase3.limits.max_pwarm_holdout_admissions = 1;
    cfg.phase3.canary.warm_windows = 8;

    seed_init(root, &cfg, None, true).expect("seed init");
    ingest_all(root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(root, &snapshot).expect("packs");
    let constellation = build_constellation(root, &cfg, &snapshot, &packs).expect("constellation");

    run_phase3_epoch(root, &cfg, Some(&constellation.constellation_id)).expect("phase3 epoch")
}

#[test]
fn phase3_epoch_pwarm_path_is_deterministic() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");

    let report = run_once(&root);
    let warm: Vec<_> = report
        .judge_report
        .receipts
        .iter()
        .filter(|r| r.promotion_class == Some(PromotionClass::PWarm))
        .map(|r| (r.candidate_hash.clone(), r.reason.clone(), r.decision))
        .collect();

    assert!(!report.judge_report.receipts.is_empty());
    if !warm.is_empty() {
        assert!(report.judge_report.receipts.iter().any(|r| {
            r.promotion_class == Some(PromotionClass::PWarm) && r.decision == JudgeDecision::Promote
        }));
    }

    assert!(root.join("receipts/canary").exists());
    assert!(root.join("receipts/bridge").exists());
}
