use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::{candidate_dir, read_json, write_json_atomic};
use baremetal_lgp::apfsc::bank::{load_family_panel_windows, load_payload_index_for_windows, window_bytes};
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::resolve_constellation;
use baremetal_lgp::apfsc::scir::backend_equiv::evaluate_backend_equivalence;
use baremetal_lgp::apfsc::types::{LoweringReceipt, ScirV2Program};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    constellation: Option<String>,
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

    let candidate = load_candidate(&args.root, &args.candidate).map_err(|e| e.to_string())?;
    let constellation =
        resolve_constellation(&args.root, args.constellation.as_deref()).map_err(|e| e.to_string())?;

    let cdir = candidate_dir(&args.root, &candidate.manifest.candidate_hash);
    let lowered: ScirV2Program = read_json(&cdir.join("scir_lowered.json")).map_err(|e| e.to_string())?;
    let compile: LoweringReceipt = read_json(&cdir.join("compile_receipt.json")).map_err(|e| e.to_string())?;

    let mut refs = Vec::new();
    for fam in &constellation.family_specs {
        let mut family_refs =
            load_family_panel_windows(&args.root, &fam.family_id, "static_public").map_err(|e| e.to_string())?;
        family_refs.sort_by(|a, b| a.seq_hash.cmp(&b.seq_hash).then_with(|| a.start.cmp(&b.start)));
        refs.extend(family_refs.into_iter().take(2));
    }
    if refs.is_empty() {
        return Err("no equivalence windows available".to_string());
    }
    let payloads = load_payload_index_for_windows(&args.root, &refs).map_err(|e| e.to_string())?;
    let mut windows = Vec::new();
    for r in &refs {
        let payload = payloads
            .get(&r.seq_hash)
            .ok_or_else(|| format!("missing payload for {}", r.seq_hash))?;
        windows.push(window_bytes(payload, r).map_err(|e| e.to_string())?.to_vec());
    }

    let receipt = evaluate_backend_equivalence(
        &candidate.manifest.candidate_hash,
        &compile.canonical_hash,
        &compile.lowered_hash,
        &lowered,
        &windows,
        &candidate.manifest.snapshot_hash,
        &constellation.constellation_id,
        &cfg.protocol.version,
    )
    .map_err(|e| e.to_string())?;

    write_json_atomic(&cdir.join("backend_equiv_receipt.json"), &receipt).map_err(|e| e.to_string())?;
    baremetal_lgp::apfsc::archive::backend_equiv::append_receipt(&args.root, &receipt)
        .map_err(|e| e.to_string())?;

    println!(
        "candidate={} eligible={} backend={:?}",
        candidate.manifest.candidate_hash, receipt.eligible, receipt.backend_kind
    );
    Ok(())
}
