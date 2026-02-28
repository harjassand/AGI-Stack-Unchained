use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::orchestrator::run_phase2_epoch;
use baremetal_lgp::apfsc::seed::seed_init;
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

fn setup_and_run(root: &std::path::Path) -> baremetal_lgp::apfsc::types::EpochReport {
    let cfg = phase2_config();
    seed_init(root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(root, &snapshot).expect("pack hashes");
    let constellation = build_constellation(root, &cfg, &snapshot, &packs).expect("constellation");

    run_phase2_epoch(root, &cfg, Some(&constellation.constellation_id)).expect("phase2 epoch")
}

#[test]
fn phase2_epoch_e2e_is_deterministic() {
    let tmp1 = tempdir().expect("tempdir1");
    let tmp2 = tempdir().expect("tempdir2");
    let root1 = tmp1.path().join(".apfsc");
    let root2 = tmp2.path().join(".apfsc");

    let r1 = setup_and_run(&root1);
    let r2 = setup_and_run(&root2);

    assert!(!r1.judge_report.receipts.is_empty());
    assert!(!r2.judge_report.receipts.is_empty());

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

    assert!(root1.join("receipts/public_static").exists());
    assert!(root1.join("receipts/holdout_static").exists());
    assert!(root1.join("receipts/judge").exists());

    let judge_files = fs::read_dir(root1.join("receipts/judge"))
        .expect("judge dir")
        .count();
    assert!(judge_files > 0);
}
