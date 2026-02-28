use std::path::PathBuf;

use baremetal_lgp::apfsc::artifacts::{candidate_dir, receipt_path, write_json_atomic};
use baremetal_lgp::apfsc::candidate::load_candidate;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::resolve_constellation;
use baremetal_lgp::apfsc::types::{ColdBoundaryPack, PromotionClass};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    candidate: String,
    #[arg(long)]
    incumbent: Option<String>,
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
    let incumbent_hash = if let Some(v) = args.incumbent {
        v
    } else {
        baremetal_lgp::apfsc::artifacts::read_pointer(&args.root, "active_candidate")
            .map_err(|e| e.to_string())?
    };
    let incumbent = load_candidate(&args.root, &incumbent_hash).map_err(|e| e.to_string())?;
    let constellation = resolve_constellation(&args.root, args.constellation.as_deref())
        .map_err(|e| e.to_string())?;

    let (bridge_receipt, recent) = match candidate.manifest.promotion_class {
        PromotionClass::A | PromotionClass::PWarm => {
            let pack = candidate
                .bridge_pack
                .as_ref()
                .ok_or_else(|| "candidate missing warm bridge pack".to_string())?;
            let bridge = baremetal_lgp::apfsc::bridge::evaluate_warm_bridge(
                &args.root,
                &candidate,
                &incumbent,
                &constellation,
                pack,
            )
            .map_err(|e| e.to_string())?;
            (bridge, None)
        }
        PromotionClass::PCold => {
            let cold_pack = ColdBoundaryPack {
                protected_panels: vec!["anchor".to_string()],
                max_anchor_regret_bpb: cfg.phase3.promotion.p_cold_max_anchor_regret_bpb,
                max_error_streak: cfg.phase3.promotion.p_cold_max_error_streak,
                required_transfer_gain_bpb: cfg.phase3.promotion.p_cold_min_transfer_delta_bpb,
                required_recent_family_gain_bpb: cfg
                    .phase3
                    .promotion
                    .p_cold_min_recent_family_gain_bpb,
                mandatory_canary_windows: cfg.phase3.canary.cold_windows,
                rollback_target_hash: incumbent.manifest.candidate_hash.clone(),
            };
            let (bridge, recent) = baremetal_lgp::apfsc::bridge::evaluate_cold_boundary(
                &args.root,
                &candidate,
                &incumbent,
                &constellation,
                &cold_pack,
                &constellation.fresh_families,
                0,
            )
            .map_err(|e| e.to_string())?;
            (bridge, Some(recent))
        }
        _ => return Err("bridge eval is only required for A/PWarm/PCold".to_string()),
    };

    let cdir = candidate_dir(&args.root, &candidate.manifest.candidate_hash);
    write_json_atomic(&cdir.join("bridge_receipt.json"), &bridge_receipt)
        .map_err(|e| e.to_string())?;
    write_json_atomic(
        &receipt_path(
            &args.root,
            "bridge",
            &format!("{}.json", candidate.manifest.candidate_hash),
        ),
        &bridge_receipt,
    )
    .map_err(|e| e.to_string())?;

    if let Some(r) = recent {
        write_json_atomic(&cdir.join("fresh_public_receipt.json"), &r)
            .map_err(|e| e.to_string())?;
    }

    println!(
        "candidate={} bridge={} pass={}",
        candidate.manifest.candidate_hash, bridge_receipt.bridge_kind, bridge_receipt.pass
    );
    Ok(())
}
