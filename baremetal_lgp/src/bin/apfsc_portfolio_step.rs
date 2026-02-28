use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::load_active_constellation;
use baremetal_lgp::apfsc::portfolio::{
    allocate_branch_budget, load_or_init_portfolio, persist_portfolio,
};
use baremetal_lgp::apfsc::search_law::{build_search_plan, ensure_active_search_law};
use baremetal_lgp::apfsc::searchlaw_features::build_searchlaw_features;
use baremetal_lgp::apfsc::{law_archive, law_tokens};
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long, default_value = "phase4")]
    profile: String,
    #[arg(long)]
    portfolio: Option<String>,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long, default_value_t = 0)]
    epoch: u64,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path).map_err(|e| e.to_string())?
    } else {
        Phase1Config::default()
    };
    let constellation = load_active_constellation(&args.root).map_err(|e| e.to_string())?;
    let law = ensure_active_search_law(&args.root).map_err(|e| e.to_string())?;
    let summary =
        law_archive::build_summary(&args.root, &law.manifest_hash).map_err(|e| e.to_string())?;
    let records = law_archive::load_records(&args.root).map_err(|e| e.to_string())?;
    let tokens = law_tokens::distill_law_tokens(&records, cfg.phase4.max_qd_cells)
        .map_err(|e| e.to_string())?;
    let features = build_searchlaw_features(&args.root, &constellation, &summary)
        .map_err(|e| e.to_string())?;
    let plan = build_search_plan(
        &law,
        &features,
        &tokens,
        args.epoch,
        cfg.phase4.max_needtokens_per_epoch,
    );

    let (mut manifest, mut branches) = load_or_init_portfolio(
        &args.root,
        &constellation.snapshot_hash,
        &constellation.constellation_id,
        &law.manifest_hash,
        &cfg,
    )
    .map_err(|e| e.to_string())?;
    if let Some(pid) = args.portfolio {
        manifest.portfolio_id = pid;
    }
    allocate_branch_budget(&args.root, &mut manifest, &mut branches, &plan, &cfg)
        .map_err(|e| e.to_string())?;
    persist_portfolio(&args.root, &manifest, &branches).map_err(|e| e.to_string())?;
    println!(
        "portfolio={} branches={} credit={} debt={}",
        manifest.portfolio_id,
        branches.len(),
        manifest.total_credit_supply,
        manifest.total_debt_outstanding
    );
    Ok(())
}
