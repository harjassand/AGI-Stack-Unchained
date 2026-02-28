use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::release_manifest::{
    ensure_release_verified, verify_release_bundle,
};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long)]
    manifest: PathBuf,
    #[arg(long)]
    sbom: PathBuf,
    #[arg(long)]
    provenance: PathBuf,
    #[arg(long)]
    signature: PathBuf,
}

fn main() -> Result<(), String> {
    let a = Args::parse();
    let report = verify_release_bundle(&a.manifest, &a.sbom, &a.provenance, &a.signature)
        .map_err(|e| e.to_string())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?
    );
    ensure_release_verified(&report).map_err(|e| e.to_string())
}
