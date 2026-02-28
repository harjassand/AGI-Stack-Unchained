use std::path::PathBuf;

use baremetal_lgp::apfsc::canary::run_phase3_canary;
use baremetal_lgp::apfsc::candidate::{clone_with_mutation, save_candidate};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::rollback::stage_rollback_target;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::PromotionClass;
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
        ingest_reality(root, cfg, &fixtures_phase2().join(d).join("manifest.json")).expect("ingest p2");
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
        ingest_reality(root, cfg, &fixtures_phase3().join(d).join("manifest.json")).expect("ingest p3");
    }
}

#[test]
fn pcold_canary_fail_keeps_active_and_rollback_pointer() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let cfg = phase3_config();

    seed_init(&root, &cfg, None, true).expect("seed");
    ingest_all(&root, &cfg);
    let snapshot = baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let incumbent_hash = baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let incumbent = baremetal_lgp::apfsc::candidate::load_candidate(&root, &incumbent_hash).expect("incumbent");

    let mut bad_env = incumbent.manifest.resource_envelope.clone();
    bad_env.max_state_bytes = cfg.limits.state_tile_bytes_max.saturating_mul(10);
    let mut cand = clone_with_mutation(
        &incumbent,
        "cold_frontier",
        "pcold_canary_fail",
        PromotionClass::PCold,
        incumbent.arch_program.clone(),
        incumbent.head_pack.clone(),
        incumbent.state_pack.clone(),
        incumbent.schedule_pack.clone(),
        incumbent.bridge_pack.clone(),
        std::collections::BTreeMap::new(),
    )
    .expect("clone");
    cand.manifest.resource_envelope = bad_env;
    baremetal_lgp::apfsc::candidate::rehash_candidate(&mut cand).expect("rehash");
    save_candidate(&root, &cand).expect("save candidate");

    stage_rollback_target(&root, &incumbent_hash).expect("stage rollback");
    let receipt = run_phase3_canary(
        &root,
        &cand.manifest.candidate_hash,
        &incumbent_hash,
        &constellation.constellation_id,
        1,
        &cfg,
    )
    .expect("canary");

    assert!(!receipt.pass);
    let active_after = baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active after");
    let rollback_after = baremetal_lgp::apfsc::artifacts::read_pointer(&root, "rollback_candidate").expect("rollback after");
    assert_eq!(active_after, incumbent_hash);
    assert_eq!(rollback_after, incumbent_hash);
}
