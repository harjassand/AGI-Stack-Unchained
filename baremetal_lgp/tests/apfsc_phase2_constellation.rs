use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::read_pointer;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
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
        let manifest = fixtures_phase2().join(d).join("manifest.json");
        ingest_reality(root, cfg, &manifest).expect("ingest reality");
    }
}

#[test]
fn phase2_constellation_builds_and_is_deterministic() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = phase2_config();

    seed_init(&root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(&root, &cfg);

    let snapshot = read_pointer(&root, "active_snapshot").expect("active snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("pack hashes");

    let m1 = build_constellation(&root, &cfg, &snapshot, &packs).expect("build constellation");
    let m2 =
        build_constellation(&root, &cfg, &snapshot, &packs).expect("build constellation again");

    assert_eq!(m1.constellation_id, m2.constellation_id);
    assert_eq!(m1.manifest_hash, m2.manifest_hash);
    assert_eq!(m1.family_specs.len(), 4);

    let mut by_family = BTreeMap::new();
    for f in &m1.family_specs {
        by_family.insert(
            f.family_id.clone(),
            (
                f.base_pack_hash.clone(),
                f.transfer_pack_hashes.len(),
                f.robust_pack_hashes.len(),
            ),
        );
    }

    assert_eq!(by_family.get("det_micro").map(|v| v.1), Some(1));
    assert_eq!(by_family.get("text_code").map(|v| v.1), Some(1));
    assert_eq!(by_family.get("sensor_temporal").map(|v| v.1), Some(1));
    assert_eq!(by_family.get("phys_sim").map(|v| v.1), Some(1));

    let active_constellation =
        read_pointer(&root, "active_constellation").expect("active constellation");
    assert_eq!(active_constellation, m1.constellation_id);
}
