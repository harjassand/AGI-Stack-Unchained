use std::path::PathBuf;

use baremetal_lgp::apfsc::bridge::evaluate_cold_boundary;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::ColdBoundaryPack;
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
}

#[test]
fn cold_boundary_pass_and_failure_modes() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let cfg = phase3_config();

    seed_init(&root, &cfg, None, true).expect("seed");
    ingest_all(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let active_hash =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let incumbent =
        baremetal_lgp::apfsc::candidate::load_candidate(&root, &active_hash).expect("incumbent");

    let pass_pack = ColdBoundaryPack {
        protected_panels: vec!["anchor".to_string()],
        max_anchor_regret_bpb: 10.0,
        max_error_streak: 3,
        required_transfer_gain_bpb: -1_000_000.0,
        required_recent_family_gain_bpb: -1_000_000.0,
        mandatory_canary_windows: 16,
        rollback_target_hash: incumbent.manifest.candidate_hash.clone(),
    };
    let (pass_bridge, _recent) = evaluate_cold_boundary(
        &root,
        &incumbent,
        &incumbent,
        &constellation,
        &pass_pack,
        &constellation.fresh_families,
        0,
    )
    .expect("pass eval");
    assert!(pass_bridge.pass);

    let fail_anchor_pack = ColdBoundaryPack {
        max_anchor_regret_bpb: -1.0,
        ..pass_pack.clone()
    };
    let (fail_anchor_bridge, _) = evaluate_cold_boundary(
        &root,
        &incumbent,
        &incumbent,
        &constellation,
        &fail_anchor_pack,
        &constellation.fresh_families,
        0,
    )
    .expect("fail anchor eval");
    assert!(!fail_anchor_bridge.pass);

    let fail_recent_pack = ColdBoundaryPack {
        max_anchor_regret_bpb: 10.0,
        required_recent_family_gain_bpb: 1.0,
        ..pass_pack
    };
    let (fail_recent_bridge, recent_receipt) = evaluate_cold_boundary(
        &root,
        &incumbent,
        &incumbent,
        &constellation,
        &fail_recent_pack,
        &constellation.fresh_families,
        0,
    )
    .expect("fail recent eval");
    assert!(!recent_receipt.pass);
    assert!(!fail_recent_bridge.pass);
}
