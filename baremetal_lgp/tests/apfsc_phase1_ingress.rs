use std::fs;
use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::digest_file;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::manifest::{finalize_manifest, load_pack_manifest};
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::ingress::substrate::ingest_substrate;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

#[test]
fn reality_pack_hash_is_stable() {
    let manifest_path = fixtures().join("reality_f0_det/manifest.json");
    let payload_hash =
        digest_file(&fixtures().join("reality_f0_det/payload.bin")).expect("payload hash");
    let m1 = finalize_manifest(
        load_pack_manifest(&manifest_path).expect("load manifest"),
        vec![payload_hash.clone()],
    )
    .expect("finalize manifest");
    let m2 = finalize_manifest(
        load_pack_manifest(&manifest_path).expect("load manifest"),
        vec![payload_hash],
    )
    .expect("finalize manifest");
    assert_eq!(m1.pack_hash, m2.pack_hash);
}

#[test]
fn reality_ingest_builds_deterministic_bank() {
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
    let first =
        fs::read_to_string(root.join("banks/F0/manifest.json")).expect("read bank manifest");

    ingest_reality(
        &root,
        &cfg,
        &fixtures().join("reality_f0_det/manifest.json"),
    )
    .expect("ingest reality again");
    let second =
        fs::read_to_string(root.join("banks/F0/manifest.json")).expect("read bank manifest");

    assert_eq!(first, second);
}

#[test]
fn prior_pack_rejects_illegal_macro() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    seed_init(&root, &cfg, Some(&fixtures()), true).expect("seed init");

    let bad_prior = tmp.path().join("bad_prior");
    fs::create_dir_all(&bad_prior).expect("mkdir");
    fs::write(
        bad_prior.join("manifest.json"),
        r#"{
            "pack_kind": "Prior",
            "pack_hash": "",
            "protocol_version": "apfsc-phase1-mvp-v1",
            "created_unix_s": 1735689600,
            "family_id": null,
            "provenance": {"source_name":"bad","source_type":"test","attestation":null,"notes":null},
            "payload_hashes": [],
            "meta": {}
        }"#,
    )
    .expect("write manifest");
    fs::write(bad_prior.join("ops.json"), r#"{"ops": ["lag_1"]}"#).expect("write ops");
    fs::write(
        bad_prior.join("macros.json"),
        r#"{"macros": ["illegal_macro"]}"#,
    )
    .expect("write macros");

    let err = ingest_prior(&root, &cfg, &bad_prior.join("manifest.json")).expect_err("must reject");
    assert!(err.to_string().contains("unsupported prior macro"));
}

#[test]
fn substrate_pack_updates_oracle_cache() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    seed_init(&root, &cfg, Some(&fixtures()), true).expect("seed init");

    ingest_substrate(
        &root,
        &cfg,
        &fixtures().join("substrate_seed/manifest.json"),
    )
    .expect("ingest substrate");

    let model_path = root.join("archive/hardware_oracle_model.json");
    assert!(model_path.exists());

    let body = fs::read_to_string(model_path).expect("read model");
    assert!(body.contains("traces_count"));
}
