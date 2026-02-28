use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{build_bank, load_bank};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

#[test]
fn window_split_counts_are_stable() {
    let payload = fs::read(fixtures().join("reality_f0_det/payload.bin")).expect("read payload");
    let cfg = Phase1Config::default();
    let b1 = build_bank(
        "F0",
        "packhash",
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )
    .expect("build bank");
    let b2 = build_bank(
        "F0",
        "packhash",
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )
    .expect("build bank");

    assert_eq!(b1.manifest.split_counts, b2.manifest.split_counts);
}

#[test]
fn holdout_windows_not_listed_in_public_panel() {
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
    let bank = load_bank(&root, "F0").expect("load bank");

    let public: std::collections::BTreeSet<u64> = bank.public.iter().map(|w| w.start).collect();
    let holdout: std::collections::BTreeSet<u64> = bank.holdout.iter().map(|w| w.start).collect();

    assert!(public.is_disjoint(&holdout));
}

#[test]
fn same_payload_same_bank_manifest() {
    let payload = fs::read(fixtures().join("reality_f1_text/payload.bin")).expect("read payload");
    let cfg = Phase1Config::default();

    let b1 = build_bank(
        "F1",
        "abc",
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )
    .expect("build bank");
    let b2 = build_bank(
        "F1",
        "abc",
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )
    .expect("build bank");

    assert_eq!(b1.manifest.manifest_hash, b2.manifest.manifest_hash);
}
