use std::path::PathBuf;

use baremetal_lgp::apf3::wake::{run_wake, WakeConfig};
use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "apf3_wake_hotloop")]
#[command(about = "APF-v3 wake hot loop")]
struct Args {
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long, default_value_t = 1)]
    workers: usize,
    #[arg(long, default_value_t = 1000)]
    max_candidates: u64,
    #[arg(long)]
    train_pack_dir: PathBuf,
    #[arg(long)]
    proposal_dir: PathBuf,
    #[arg(long)]
    graph: Option<PathBuf>,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("apf3_wake_hotloop failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    let cfg = WakeConfig {
        seed: args.seed,
        run_dir: args.run_dir,
        workers: args.workers,
        max_candidates: args.max_candidates,
        train_pack_dir: args.train_pack_dir,
        proposal_dir: args.proposal_dir,
        base_graph: args.graph,
    };
    run_wake(&cfg)
}
