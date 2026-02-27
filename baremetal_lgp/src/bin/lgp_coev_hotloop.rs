use std::fs;
use std::path::{Path, PathBuf};
use std::time::Instant;

use baremetal_lgp::agent_b::{default_regime_spec, AgentBState, B_LEAGUE_K};
use baremetal_lgp::jit2::raw_runner::SNIPER_USEC;
use baremetal_lgp::jit2::templates::default_templates;
use baremetal_lgp::oracle::SplitMix64;
use baremetal_lgp::oracle3::spec::{InputDistSpec, PiecewiseScheduleSpec, RegimeSpec};
use baremetal_lgp::oracle3::RawJitExecEngine;
use baremetal_lgp::outer_loop::coev::{run_epoch, AState};
use baremetal_lgp::search::digest::{bytes32_to_hex, run_digest_v3_text, RunDigestV3};
use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "lgp_coev_hotloop")]
#[command(about = "Phase-3 coevolution hotloop")]
struct Args {
    #[arg(long)]
    seed: u64,
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long)]
    epochs: u32,
    #[arg(long, default_value_t = 1)]
    workers: u32,
    #[arg(long)]
    a_evals_per_epoch: Option<u32>,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("lgp_coev_hotloop failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    fs::create_dir_all(&args.run_dir).map_err(|e| e.to_string())?;

    if args.workers != 1 {
        eprintln!(
            "workers={} requested; phase3 deterministic mode currently runs single-worker",
            args.workers
        );
    }

    let templates = default_templates();
    let champion_words = templates
        .iter()
        .find(|template| template.name == "ret_only")
        .map(|template| template.words.clone())
        .unwrap_or_else(|| vec![0xD65F03C0]);

    let mut a_state = AState {
        champion: champion_words,
        league: Vec::new(),
    };
    let mut b_state = AgentBState::new(args.seed ^ 0xB3A7_1EED_u64);
    let anchors = build_anchor_specs();

    let mut engine = RawJitExecEngine::new(SNIPER_USEC);
    let mut rng = SplitMix64::new(args.seed ^ 0xA076_1D64_78BD_642F);

    let run_started = Instant::now();
    let mut last_schedule_hash = [0_u8; 32];
    let mut last_epoch = 0_u32;
    let mut last_a_score = 0.0_f32;
    let mut last_b_fitness = 0.0_f32;
    let mut last_b_hash = [0_u8; 32];
    let mut total_sigalrm = 0_u64;
    let mut total_fault = 0_u64;

    for epoch in 0..args.epochs {
        let t0 = Instant::now();
        let report = run_epoch(
            epoch,
            args.seed,
            &mut a_state,
            &mut b_state,
            &anchors,
            &mut engine,
            &mut rng,
        );

        let elapsed = t0.elapsed().as_secs_f64().max(1e-9);
        let evals = u64::from(args.a_evals_per_epoch.unwrap_or(report.evals as u32));
        let throughput = evals as f64 / elapsed;

        total_sigalrm = total_sigalrm.saturating_add(u64::from(report.sigalrm_count));
        total_fault = total_fault.saturating_add(u64::from(report.fault_count));

        write_summary_snapshot(
            &args.run_dir,
            report.epoch,
            report.a_champion_score,
            report.b_current_fitness,
            report.b_current_spec_hash,
            total_sigalrm,
            total_fault,
            throughput,
            report.compiled_chunks,
        )
        .map_err(|e| e.to_string())?;

        dump_b_specs(&args.run_dir, &b_state).map_err(|e| e.to_string())?;

        last_schedule_hash = report.schedule_hash;
        last_epoch = report.epoch;
        last_a_score = report.a_champion_score;
        last_b_fitness = report.b_current_fitness;
        last_b_hash = report.b_current_spec_hash;
    }

    if args.epochs == 0 {
        write_summary_snapshot(
            &args.run_dir,
            0,
            0.0,
            0.0,
            baremetal_lgp::oracle3::spec::spec_hash_32(&b_state.current),
            0,
            0,
            0.0,
            0,
        )
        .map_err(|e| e.to_string())?;
        dump_b_specs(&args.run_dir, &b_state).map_err(|e| e.to_string())?;
        last_b_hash = baremetal_lgp::oracle3::spec::spec_hash_32(&b_state.current);
    }

    let mut league_hashes = Vec::with_capacity(B_LEAGUE_K);
    for i in 0..B_LEAGUE_K {
        let spec = b_state.league_specs().get(i).cloned();
        if let Some(spec) = spec {
            league_hashes.push(baremetal_lgp::oracle3::spec::spec_hash_32(&spec));
        } else {
            league_hashes.push([0_u8; 32]);
        }
    }

    let digest = RunDigestV3 {
        version: 3,
        seed: args.seed,
        epochs: args.epochs,
        a_champion_hash: program_hash(&a_state.champion),
        b_current_spec_hash: last_b_hash,
        b_league_topk_hashes: league_hashes,
        chunk_schedule_hash: last_schedule_hash,
    };
    fs::write(
        args.run_dir.join("run_digest.txt"),
        run_digest_v3_text(&digest),
    )
    .map_err(|e| e.to_string())?;

    // Keep currently surfaced values alive for debugging parity with summary outputs.
    let _ = (last_epoch, last_a_score, last_b_fitness, run_started);

    Ok(())
}

fn write_summary_snapshot(
    run_dir: &Path,
    epoch: u32,
    a_champion_score: f32,
    b_current_fitness: f32,
    b_current_spec_hash: [u8; 32],
    sigalrm_count: u64,
    fault_count: u64,
    eval_throughput: f64,
    compiled_chunks: u32,
) -> Result<(), std::io::Error> {
    let b_hash_hex = bytes32_to_hex(&b_current_spec_hash);
    let summary_line = format!(
        "epoch={epoch} a_champion_score={a_champion_score:.6} b_current_fitness={b_current_fitness:.6} b_current_spec_hash={b_hash_hex} sigalrm_count={sigalrm_count} fault_count={fault_count} eval_throughput={eval_throughput:.2}/s compiled_chunks={compiled_chunks}"
    );

    let summary_json = serde_json::json!({
        "epoch": epoch,
        "a_champion_score": a_champion_score,
        "b_current_fitness": b_current_fitness,
        "b_current_spec_hash": b_hash_hex,
        "sigalrm_count": sigalrm_count,
        "fault_count": fault_count,
        "eval_throughput": eval_throughput,
        "compiled_chunks": compiled_chunks,
    });

    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
    fs::write(
        run_dir.join("snapshot_latest.json"),
        serde_json::to_string_pretty(&summary_json).unwrap_or_else(|_| "{}".to_string()),
    )?;
    Ok(())
}

fn dump_b_specs(run_dir: &Path, b_state: &AgentBState) -> Result<(), std::io::Error> {
    let b_current_json =
        serde_json::to_string_pretty(&b_state.current).unwrap_or_else(|_| "{}".to_string());
    fs::write(run_dir.join("b_current.json"), b_current_json)?;

    let league = b_state.league_specs();
    for i in 0..B_LEAGUE_K {
        let path = run_dir.join(format!("b_league_{i}.json"));
        if let Some(spec) = league.get(i) {
            let body = serde_json::to_string_pretty(spec).unwrap_or_else(|_| "{}".to_string());
            fs::write(path, body)?;
        } else {
            fs::write(path, "null")?;
        }
    }

    Ok(())
}

fn program_hash(words: &[u32]) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&(words.len() as u64).to_le_bytes());
    for &word in words {
        hasher.update(&word.to_le_bytes());
    }
    *hasher.finalize().as_bytes()
}

fn build_anchor_specs() -> Vec<RegimeSpec> {
    let mut anchors = Vec::new();
    anchors.push(default_regime_spec());

    let mut a1 = default_regime_spec();
    a1.input_dist = InputDistSpec::Rademacher { scale: 1.0 };
    anchors.push(a1);

    let mut a2 = default_regime_spec();
    a2.input_dist = InputDistSpec::Normal {
        mean: 0.0,
        std: 1.0,
    };
    anchors.push(a2);

    let mut a3 = default_regime_spec();
    a3.schedule = PiecewiseScheduleSpec {
        segments: vec![baremetal_lgp::oracle3::spec::ScheduleSegment {
            start_episode: 0,
            end_episode: 128,
            param_scale: 1.25,
            input_scale: 0.75,
        }],
    };
    anchors.push(a3);

    anchors
}
