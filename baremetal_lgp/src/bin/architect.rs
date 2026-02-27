use std::fs;
use std::path::PathBuf;

use baremetal_lgp::library::bank::LibraryBank;
use baremetal_lgp::outer_loop::architect::{
    Architect, ArchiveSnapshotSummary, ChampionHistoryPoint, TraceDiffSummary,
};
use baremetal_lgp::outer_loop::stage_c::{KernelBuilder, KernelRequest, ShadowSuite};
use baremetal_lgp::types::CandidateId;
use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "architect")]
#[command(
    about = "Outer-loop architect for mutation weights, library promotions, and native swaps"
)]
struct Args {
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long)]
    stage_a_module: Option<PathBuf>,
    #[arg(long, default_value_t = false)]
    enable_stage_c: bool,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("architect failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    let mut architect = Architect::new();
    let mut library = LibraryBank::new_seeded();

    let snapshot = read_snapshot(&args.run_dir);
    let trace_diffs = collect_trace_diffs(&args.run_dir);
    let champion_history = Vec::<ChampionHistoryPoint>::new();

    let decision = architect.decide(snapshot, &champion_history, &trace_diffs);
    architect
        .write_mutation_weights(&args.run_dir)
        .map_err(|e| e.to_string())?;

    let promotions_applied = architect.apply_promotions(&mut library, &decision.promotions);

    if let Some(path) = args.stage_a_module.as_ref() {
        let swapped = architect.try_stage_a_swap(path, |dispatch, episodes| {
            let sample = (dispatch.fast_tanh)(0.5) + (dispatch.fast_sigm)(-0.25);
            sample * episodes as f32
        });
        println!("stage_a_swap={swapped} module={}", path.display());
    }

    if args.enable_stage_c {
        let mut builder = MockKernelBuilder;
        let mut shadow = MockShadowSuite;
        for request in &decision.stage_c_requests {
            let enabled = architect
                .stage_c
                .propose_kernel(*request, &mut builder, &mut shadow, 1.0)
                .map_err(|e| format!("{e:?}"))?;
            println!("stage_c_request={request:?} enabled={enabled}");
        }
    }

    println!(
        "mutation_weights_written=true promotions_applied={} stage_c_requests={} filled_bins={}",
        promotions_applied,
        decision.stage_c_requests.len(),
        snapshot.filled_bins
    );
    Ok(())
}

fn read_snapshot(run_dir: &PathBuf) -> ArchiveSnapshotSummary {
    let path = run_dir.join("snapshot_latest.json");
    let Ok(body) = fs::read_to_string(path) else {
        return ArchiveSnapshotSummary::default();
    };
    let filled_bins = parse_u32(&body, "\"filled_bins\":").unwrap_or(0);
    let wins_per_hour = parse_f32(&body, "\"wins_per_hour\":").unwrap_or(0.0);
    let eval_throughput = parse_f32(&body, "\"eval_throughput\":").unwrap_or(0.0);
    ArchiveSnapshotSummary {
        filled_bins,
        wins_per_hour,
        eval_throughput,
    }
}

fn collect_trace_diffs(run_dir: &PathBuf) -> Vec<TraceDiffSummary> {
    let traces_dir = run_dir.join("traces");
    let Ok(entries) = fs::read_dir(traces_dir) else {
        return Vec::new();
    };
    let mut diffs = Vec::new();
    for entry in entries.flatten() {
        let file_name = entry.file_name();
        let name = file_name.to_string_lossy();
        if !name.ends_with(".bin") || !name.chars().next().is_some_and(|c| c.is_ascii_digit()) {
            continue;
        }
        let id_str = name.trim_end_matches(".bin");
        let Ok(id_num) = id_str.parse::<u64>() else {
            continue;
        };
        let divergence = (id_num % 17) as f32 / 16.0;
        diffs.push(TraceDiffSummary {
            candidate_id: CandidateId(id_num),
            divergence_score: divergence,
        });
    }
    diffs
}

fn parse_u32(body: &str, key: &str) -> Option<u32> {
    let idx = body.find(key)?;
    let tail = &body[idx + key.len()..];
    let end = tail
        .find(|c: char| !c.is_ascii_digit())
        .unwrap_or(tail.len());
    tail[..end].parse().ok()
}

fn parse_f32(body: &str, key: &str) -> Option<f32> {
    let idx = body.find(key)?;
    let tail = &body[idx + key.len()..];
    let end = tail
        .find(|c: char| !(c.is_ascii_digit() || c == '.' || c == '-'))
        .unwrap_or(tail.len());
    tail[..end].parse().ok()
}

struct MockKernelBuilder;

impl KernelBuilder for MockKernelBuilder {
    fn build_kernel(&mut self, request: KernelRequest) -> Option<Vec<u8>> {
        let len = request.len as usize;
        Some(vec![0x00_u8; len.max(16)])
    }
}

struct MockShadowSuite;

impl ShadowSuite for MockShadowSuite {
    fn run_shadow_suite(
        &mut self,
        _request: KernelRequest,
        _entry_ptr: *const std::ffi::c_void,
    ) -> bool {
        true
    }
}
