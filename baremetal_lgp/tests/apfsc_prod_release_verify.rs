use std::collections::BTreeMap;
use std::io::Read;

use baremetal_lgp::apfsc::prod::release_manifest::{build_release_manifest, verify_release_bundle};
use sha2::{Digest, Sha256};
use tempfile::tempdir;

#[test]
fn release_verify_passes_for_complete_bundle() {
    let tmp = tempdir().expect("tmp");
    let bin = tmp.path().join("apfscd");
    std::fs::write(&bin, b"binary").expect("write");
    let sbom = tmp.path().join("sbom.spdx.json");
    let prov = tmp.path().join("provenance.json");
    let sig = tmp.path().join("signature.bundle.json");
    std::fs::write(&sbom, b"{}").expect("write");
    std::fs::write(&prov, b"{}").expect("write");
    let mut paths = BTreeMap::new();
    paths.insert(bin.display().to_string(), bin.display().to_string());
    let m = build_release_manifest(
        "1.0.0",
        "abc",
        "release",
        "pinned",
        "aarch64-apple-darwin",
        &paths,
        &sbom.display().to_string(),
        &prov.display().to_string(),
        &sig.display().to_string(),
    )
    .expect("manifest");
    let mpath = tmp.path().join("release_manifest.json");
    std::fs::write(&mpath, serde_json::to_vec_pretty(&m).expect("json")).expect("write");
    let mut f = std::fs::File::open(&mpath).expect("open manifest");
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 4096];
    loop {
        let n = f.read(&mut buf).expect("read");
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    let md = format!("sha256:{:x}", hasher.finalize());
    std::fs::write(
        &sig,
        serde_json::to_vec_pretty(&serde_json::json!({
            "signer": "test",
            "manifest_digest": md
        }))
        .expect("json"),
    )
    .expect("write");

    let r = verify_release_bundle(&mpath, &sbom, &prov, &sig).expect("verify");
    assert!(r.passed);
}
