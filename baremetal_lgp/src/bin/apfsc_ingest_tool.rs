use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::tool::ingest_tool;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(value_name = "MANIFEST_OR_DIR")]
    input: Option<PathBuf>,
    #[arg(long)]
    manifest: Option<PathBuf>,
    #[arg(long)]
    config: Option<PathBuf>,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };
    let manifest = resolve_manifest(args.input, args.manifest)?;
    let (ingress, shadow) = ingest_tool(&args.root, &cfg, &manifest).map_err(|e| e.to_string())?;
    println!(
        "ingested tool pack {} status={:?}",
        ingress.pack_hash, shadow.status
    );
    Ok(())
}

fn resolve_manifest(input: Option<PathBuf>, manifest: Option<PathBuf>) -> Result<PathBuf, String> {
    if let Some(path) = manifest {
        return Ok(path);
    }
    let path = input.ok_or_else(|| "missing manifest path".to_string())?;
    if path.is_dir() {
        let m = path.join("manifest.json");
        if m.exists() {
            Ok(m)
        } else {
            Err(format!(
                "manifest not found in directory: {}",
                path.display()
            ))
        }
    } else {
        Ok(path)
    }
}
