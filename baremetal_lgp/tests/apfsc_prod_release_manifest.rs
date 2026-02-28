use std::collections::BTreeMap;

use baremetal_lgp::apfsc::prod::release_manifest::{
    build_release_manifest, write_release_manifest,
};
use tempfile::tempdir;

#[test]
fn release_manifest_writes_with_expected_fields() {
    let tmp = tempdir().expect("tmp");
    let bin = tmp.path().join("apfscd");
    std::fs::write(&bin, b"binary").expect("write");
    let mut paths = BTreeMap::new();
    paths.insert("apfscd".to_string(), bin.display().to_string());
    let m = build_release_manifest(
        "1.0.0-rc1",
        "abc123",
        "release",
        "pinned",
        "aarch64-apple-darwin",
        &paths,
        "release/sbom.spdx.json",
        "release/provenance.json",
        "release/signature.bundle.json",
    )
    .expect("manifest");
    write_release_manifest(&tmp.path().join("release_manifest.json"), &m).expect("write");
    assert_eq!(m.release_manifest_version, 1);
}
