use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::apfsc::artifacts::write_json_atomic;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::prod::versioning::RELEASE_MANIFEST_VERSION;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReleaseManifest {
    pub release_manifest_version: u32,
    pub version: String,
    pub git_commit: String,
    pub build_profile: String,
    pub rust_toolchain: String,
    pub target_triple: String,
    pub artifact_digests: BTreeMap<String, String>,
    pub sbom_path: String,
    pub provenance_path: String,
    pub signature_bundle_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReleaseVerificationReport {
    pub manifest_path: String,
    pub passed: bool,
    pub failures: Vec<String>,
}

pub fn build_release_manifest(
    version: &str,
    git_commit: &str,
    build_profile: &str,
    rust_toolchain: &str,
    target_triple: &str,
    artifact_paths: &BTreeMap<String, String>,
    sbom_path: &str,
    provenance_path: &str,
    signature_bundle_path: &str,
) -> Result<ReleaseManifest> {
    let mut digests = BTreeMap::new();
    for (k, p) in artifact_paths {
        let digest = sha256_file(Path::new(p))?;
        digests.insert(k.clone(), format!("sha256:{}", digest));
    }
    Ok(ReleaseManifest {
        release_manifest_version: RELEASE_MANIFEST_VERSION,
        version: version.to_string(),
        git_commit: git_commit.to_string(),
        build_profile: build_profile.to_string(),
        rust_toolchain: rust_toolchain.to_string(),
        target_triple: target_triple.to_string(),
        artifact_digests: digests,
        sbom_path: sbom_path.to_string(),
        provenance_path: provenance_path.to_string(),
        signature_bundle_path: signature_bundle_path.to_string(),
    })
}

pub fn write_release_manifest(path: &Path, manifest: &ReleaseManifest) -> Result<()> {
    write_json_atomic(path, manifest)
}

pub fn verify_release_bundle(
    manifest_path: &Path,
    sbom_path: &Path,
    provenance_path: &Path,
    signature_path: &Path,
) -> Result<ReleaseVerificationReport> {
    let body = fs::read(manifest_path).map_err(|e| io_err(manifest_path, e))?;
    let manifest: ReleaseManifest = serde_json::from_slice(&body)?;
    let manifest_digest = format!("sha256:{}", sha256_file(manifest_path)?);

    let mut failures = Vec::new();
    if manifest.release_manifest_version != RELEASE_MANIFEST_VERSION {
        failures.push("release_manifest_version mismatch".to_string());
    }
    for (name, digest) in &manifest.artifact_digests {
        let p = Path::new(name);
        if !p.exists() {
            failures.push(format!("missing artifact: {}", p.display()));
            continue;
        }
        let got = format!("sha256:{}", sha256_file(p)?);
        if &got != digest {
            failures.push(format!("artifact digest mismatch for {}", name));
        }
    }

    for (label, p) in [
        ("sbom", sbom_path),
        ("provenance", provenance_path),
        ("signature", signature_path),
    ] {
        if !p.exists() {
            failures.push(format!("missing {} artifact: {}", label, p.display()));
        }
    }

    if sbom_path.exists() {
        let sbom_body = fs::read(sbom_path).map_err(|e| io_err(sbom_path, e))?;
        if serde_json::from_slice::<serde_json::Value>(&sbom_body).is_err() {
            failures.push(format!("sbom is not valid json: {}", sbom_path.display()));
        }
    }

    if provenance_path.exists() {
        let prov_body = fs::read(provenance_path).map_err(|e| io_err(provenance_path, e))?;
        if serde_json::from_slice::<serde_json::Value>(&prov_body).is_err() {
            failures.push(format!(
                "provenance is not valid json: {}",
                provenance_path.display()
            ));
        }
    }

    if signature_path.exists() {
        let sig_body = fs::read(signature_path).map_err(|e| io_err(signature_path, e))?;
        let sig: serde_json::Value = serde_json::from_slice(&sig_body)?;
        let manifest_ref = sig
            .get("manifest_digest")
            .and_then(|v| v.as_str())
            .unwrap_or_default();
        if manifest_ref != manifest_digest {
            failures.push(format!(
                "signature manifest digest mismatch: expected {}, got {}",
                manifest_digest, manifest_ref
            ));
        }
    }

    Ok(ReleaseVerificationReport {
        manifest_path: manifest_path.display().to_string(),
        passed: failures.is_empty(),
        failures,
    })
}

pub fn verify_release_bundle_from_manifest(
    manifest_path: &Path,
) -> Result<ReleaseVerificationReport> {
    let manifest: ReleaseManifest =
        serde_json::from_slice(&fs::read(manifest_path).map_err(|e| io_err(manifest_path, e))?)?;
    verify_release_bundle(
        manifest_path,
        Path::new(&manifest.sbom_path),
        Path::new(&manifest.provenance_path),
        Path::new(&manifest.signature_bundle_path),
    )
}

pub fn ensure_release_verified(report: &ReleaseVerificationReport) -> Result<()> {
    if report.passed {
        return Ok(());
    }
    Err(ApfscError::Validation(format!(
        "release verification failed: {}",
        report.failures.join("; ")
    )))
}

fn sha256_file(path: &Path) -> Result<String> {
    let mut file = fs::File::open(path).map_err(|e| io_err(path, e))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = file.read(&mut buf).map_err(|e| io_err(path, e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}
