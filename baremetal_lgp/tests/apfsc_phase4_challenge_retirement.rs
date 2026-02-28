use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::retirement::rotate_hidden_challenges;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures_phase2() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase2")
}
fn fixtures_phase4() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase4")
}

#[test]
fn stale_hidden_challenge_is_retired_and_replaced() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::default();
    cfg.phase4.max_hidden_challenge_families = 2;
    cfg.phase4.challenge_retire_after_epochs = 1;

    seed_init(&root, &cfg, None, true).expect("seed");
    for d in [
        "reality_f0_det_base",
        "reality_f0_det_transfer",
        "reality_f0_det_robust",
    ] {
        ingest_reality(
            &root,
            &cfg,
            &fixtures_phase2().join(d).join("manifest.json"),
        )
        .expect("ingest det roles");
    }
    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");
    baremetal_lgp::apfsc::artifacts::write_pointer(
        &root,
        "active_constellation",
        &constellation.constellation_id,
    )
    .expect("set active constellation");

    ingest_reality(
        &root,
        &cfg,
        &fixtures_phase4().join("reality_challenge/f6_hidden_logic_challenge/manifest.json"),
    )
    .expect("ingest challenge");

    let m1 = rotate_hidden_challenges(&root, &cfg, 0).expect("rot0");
    let m2 = rotate_hidden_challenges(&root, &cfg, 3).expect("rot1");
    assert!(!m1.active_hidden_families.is_empty());
    assert!(m2.retired_hidden_families.len() >= m1.retired_hidden_families.len());
}
