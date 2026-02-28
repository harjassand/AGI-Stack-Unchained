use std::path::PathBuf;

use baremetal_lgp::apf3::judge::{run_judge, JudgeConfig};
use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "apf3_judge_daemon")]
#[command(about = "APF-v3 silent judge")]
struct Args {
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long)]
    heldout_salt_file: PathBuf,
    #[arg(long)]
    heldout_pack_dir: PathBuf,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("apf3_judge_daemon failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    let cfg = JudgeConfig {
        seed: args.seed,
        run_dir: args.run_dir,
        heldout_salt_file: args.heldout_salt_file,
        heldout_pack_dir: args.heldout_pack_dir,
    };
    run_judge(&cfg)
}
