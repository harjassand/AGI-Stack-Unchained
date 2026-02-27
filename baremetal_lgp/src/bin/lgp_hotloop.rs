use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use baremetal_lgp::library::bank::LibraryBank;
use baremetal_lgp::search::archive::Archive;
use baremetal_lgp::search::champion::{maybe_update_champion, Champion, StabilityOracle};
use baremetal_lgp::search::descriptors::{
    bin_id, build_descriptor, output_entropy_sketch, DescriptorInputs,
};
use baremetal_lgp::search::evaluate::{
    scan_instruction_profile, EvalReport, EvaluatedCandidate, ExecConfig, Linker, Oracle,
};
use baremetal_lgp::search::ir::{CandidateCfg, Terminator};
use baremetal_lgp::search::mutate::{
    mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT,
};
use baremetal_lgp::search::rng::Rng;
use baremetal_lgp::search::select::select_parent;
use baremetal_lgp::search::topk_trace::{TopKTraceManager, TraceOracle, TraceSummary};
use baremetal_lgp::types::CandidateId;
use baremetal_lgp::vm::{VmProgram, VmWorker};
use clap::Parser;
use crossbeam_channel::{Receiver, RecvTimeoutError, Sender};

#[derive(Parser, Debug)]
#[command(name = "lgp_hotloop")]
#[command(about = "MAP-Elites hot loop for baremetal_lgp")]
struct Args {
    #[arg(long, default_value_t = 6)]
    workers: usize,
    #[arg(long, default_value_t = 200_000)]
    fuel_max: u32,
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long, default_value_t = 16)]
    topk_trace: usize,
    #[arg(long, default_value_t = 0)]
    max_evals: u64,
}

#[derive(Clone)]
struct EvalJob {
    id: CandidateId,
    cfg: CandidateCfg,
}

struct EvalResult {
    id: CandidateId,
    evaluated: EvaluatedCandidate,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("lgp_hotloop failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    fs::create_dir_all(&args.run_dir).map_err(|e| e.to_string())?;

    let library = Arc::new(LibraryBank::new_seeded());
    let fallback_parent = CandidateCfg::default();
    let exec_cfg = ExecConfig {
        fuel_max: args.fuel_max,
        stability_runs: 3,
        stability_threshold: 0.0,
    };

    let worker_count = args.workers.max(1);
    let (job_tx, job_rx) = crossbeam_channel::unbounded::<Option<EvalJob>>();
    let (result_tx, result_rx) = crossbeam_channel::unbounded::<EvalResult>();

    let mut worker_handles = Vec::with_capacity(worker_count);
    for worker_idx in 0..worker_count {
        let rx = job_rx.clone();
        let tx = result_tx.clone();
        let shared_lib = Arc::clone(&library);
        let cfg = exec_cfg.clone();
        worker_handles.push(thread::spawn(move || {
            worker_loop(worker_idx, rx, tx, shared_lib, cfg)
        }));
    }
    drop(result_tx);

    let mut rng = Rng::from_entropy();
    let mut archive = Archive::new();
    let mut champion: Option<Champion> = None;
    let mut stability = DeterministicStabilityOracle;
    let mut tracer = DeterministicTraceOracle;
    let mut topk =
        TopKTraceManager::new(&args.run_dir, args.topk_trace).map_err(|e| e.to_string())?;

    let mut in_flight = 0usize;
    let mut sent = 0_u64;
    let mut completed = 0_u64;
    let mut next_id = 1_u64;
    let mut proxy_wins = 0_u64;
    let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
    let mut next_weight_refresh = 4096_u64;
    let started = Instant::now();
    let mut next_snapshot = started + Duration::from_secs(10);

    loop {
        if sent >= next_weight_refresh {
            if let Some(next) = read_mutation_weights(&args.run_dir) {
                mutation_weights = next;
            }
            next_weight_refresh = next_weight_refresh.saturating_add(4096);
        }

        while in_flight < worker_count.saturating_mul(2) {
            if args.max_evals != 0 && sent >= args.max_evals {
                break;
            }
            let parent = select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
                .map_or(&fallback_parent, |elite| &elite.candidate);
            let child = mutate_candidate(parent, &archive, &mut rng, &mutation_weights);
            let job = EvalJob {
                id: CandidateId(next_id),
                cfg: child,
            };
            next_id = next_id.saturating_add(1);
            job_tx.send(Some(job)).map_err(|e| e.to_string())?;
            in_flight += 1;
            sent = sent.saturating_add(1);
        }

        if in_flight == 0 && args.max_evals != 0 && sent >= args.max_evals {
            break;
        }

        match result_rx.recv_timeout(Duration::from_millis(500)) {
            Ok(result) => {
                in_flight = in_flight.saturating_sub(1);
                completed = completed.saturating_add(1);
                let score = result.evaluated.score;
                if score > 0.0 {
                    proxy_wins = proxy_wins.saturating_add(1);
                }

                let elite = result.evaluated.to_elite();
                archive.insert(result.evaluated.bin, elite);

                let champion_updated = maybe_update_champion(
                    &mut champion,
                    &result.evaluated,
                    &exec_cfg,
                    &mut stability,
                );
                let rank_score = result
                    .evaluated
                    .report
                    .full_mean
                    .unwrap_or(result.evaluated.report.proxy_mean);
                let _ = topk
                    .consider(
                        result.id,
                        rank_score,
                        &result.evaluated.child_cfg,
                        &mut tracer,
                    )
                    .map_err(|e| e.to_string())?;

                if champion_updated {
                    let summary = tracer.run_trace(&result.evaluated.child_cfg);
                    let _ = topk
                        .write_champion_trace(result.id, &summary)
                        .map_err(|e| e.to_string())?;
                }
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => break,
        }

        if Instant::now() >= next_snapshot {
            write_snapshot(
                &args.run_dir,
                &archive,
                champion.as_ref(),
                completed,
                proxy_wins,
                started.elapsed(),
            )
            .map_err(|e| e.to_string())?;
            next_snapshot += Duration::from_secs(10);
        }
    }

    for _ in 0..worker_count {
        let _ = job_tx.send(None);
    }
    for handle in worker_handles {
        let _ = handle.join();
    }

    write_snapshot(
        &args.run_dir,
        &archive,
        champion.as_ref(),
        completed,
        proxy_wins,
        started.elapsed(),
    )
    .map_err(|e| e.to_string())?;

    Ok(())
}

fn worker_loop(
    worker_idx: usize,
    rx: Receiver<Option<EvalJob>>,
    tx: Sender<EvalResult>,
    library: Arc<LibraryBank>,
    exec_cfg: ExecConfig,
) {
    let mut worker = VmWorker::default();
    let mut linker = NoopLinker::default();
    let mut oracle = SimOracle::new(os_seed(worker_idx as u64 + 1));

    while let Ok(job) = rx.recv() {
        let Some(job) = job else {
            break;
        };
        let evaluated = evaluate_cfg(
            job.cfg,
            &mut linker,
            &mut oracle,
            &mut worker,
            &library,
            &exec_cfg,
        );
        if tx
            .send(EvalResult {
                id: job.id,
                evaluated,
            })
            .is_err()
        {
            break;
        }
    }
}

fn os_seed(salt: u64) -> u64 {
    let mut bytes = [0_u8; 8];
    if getrandom::getrandom(&mut bytes).is_ok() {
        return u64::from_le_bytes(bytes) ^ salt;
    }
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0_u64, |d| d.as_nanos() as u64);
    nanos ^ 0xD6E8_FDDA_AE9D_3A57 ^ salt
}

fn read_mutation_weights(run_dir: &Path) -> Option<[f32; MUTATION_OPERATOR_COUNT]> {
    let path = run_dir.join("mutation_weights.json");
    let body = fs::read_to_string(path).ok()?;
    let start = body.find('[')?;
    let end = body[start..].find(']')?;
    let payload = &body[start + 1..start + end];
    let mut parsed = [0.0_f32; MUTATION_OPERATOR_COUNT];
    let mut count = 0usize;
    for item in payload.split(',') {
        if count >= MUTATION_OPERATOR_COUNT {
            break;
        }
        let value = item.trim().parse::<f32>().ok()?;
        parsed[count] = value;
        count += 1;
    }
    if count != MUTATION_OPERATOR_COUNT {
        return None;
    }
    let sum = parsed.iter().sum::<f32>();
    if sum <= f32::EPSILON {
        return None;
    }
    for weight in &mut parsed {
        *weight = (*weight / sum).max(0.0);
    }
    Some(parsed)
}

fn evaluate_cfg<L, O>(
    cfg: CandidateCfg,
    linker: &mut L,
    oracle: &mut O,
    worker: &mut VmWorker,
    library: &LibraryBank,
    exec_cfg: &ExecConfig,
) -> EvaluatedCandidate
where
    L: Linker,
    O: Oracle,
{
    let program = linker.link(&cfg);
    let report = oracle.eval_candidate(worker, &program, library, exec_cfg);
    let profile = scan_instruction_profile(&program.words);
    let code_size_words = program.words.len() as u32;
    let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
    let output_entropy = output_entropy_sketch(&report.output_snapshot);
    let desc = build_descriptor(DescriptorInputs {
        fuel_used,
        fuel_max: exec_cfg.fuel_max,
        code_size_words,
        branch_count: profile.branch_count,
        store_count: profile.store_count,
        total_insns: profile.total_insns,
        output_entropy,
        regime_profile_bits: report.regime_profile_bits,
    });
    EvaluatedCandidate {
        child_cfg: cfg,
        program,
        report: report.clone(),
        profile,
        desc,
        bin: bin_id(&desc),
        score: report.full_mean.unwrap_or(report.proxy_mean),
        fuel_used,
        code_size_words,
    }
}

#[derive(Default)]
struct NoopLinker {
    arena: LinkerArena,
}

#[derive(Default)]
struct LinkerArena {
    scratch: Vec<u32>,
}

impl Linker for NoopLinker {
    fn link(&mut self, candidate: &CandidateCfg) -> VmProgram {
        self.arena.scratch.clear();
        self.arena.scratch.extend(candidate.to_program_words());
        VmProgram {
            words: self.arena.scratch.clone(),
        }
    }
}

#[derive(Clone)]
struct SimOracle {
    seed: u64,
    eval_counter: u64,
}

impl SimOracle {
    fn new(seed: u64) -> Self {
        Self {
            seed,
            eval_counter: 0,
        }
    }
}

impl Oracle for SimOracle {
    fn eval_candidate(
        &mut self,
        _worker: &mut VmWorker,
        program: &VmProgram,
        _library: &LibraryBank,
        cfg: &ExecConfig,
    ) -> EvalReport {
        self.eval_counter = self.eval_counter.saturating_add(1);
        let signature = program_signature(program, self.seed, self.eval_counter);
        let base = ((signature & 0xFFFF) as f32 / 32768.0) - 1.0;
        let jitter = (((signature >> 16) & 0x3FF) as f32 / 2048.0) - 0.25;
        let proxy_mean = base + jitter * 0.1;
        let full_available = (signature & 0x3) != 0;
        let full_mean = full_available
            .then_some(proxy_mean + ((((signature >> 26) & 0xFF) as f32 / 255.0) - 0.5) * 0.05);
        let full_var =
            full_available.then_some(1e-5 + (((signature >> 40) & 0x3FF) as f32 / 100_000.0));
        let proxy_fuel_used = ((program.words.len() as u32).saturating_mul(3)
            + (((signature >> 50) & 0x7FF) as u32))
            .min(cfg.fuel_max.max(1));
        let full_fuel_used =
            full_available.then_some(proxy_fuel_used.saturating_add(13).min(cfg.fuel_max.max(1)));
        let regime_profile_bits = ((signature >> 8) as u8) & 0x0F;
        let mut output_snapshot = Vec::with_capacity(64);
        for i in 0..64 {
            let shifted = signature.rotate_left(i as u32);
            let raw = ((shifted & 0x3FF) as f32 / 256.0) - 2.0;
            output_snapshot.push(raw.clamp(-2.0, 2.0));
        }
        EvalReport {
            proxy_mean,
            proxy_fuel_used,
            full_mean,
            full_var,
            full_fuel_used,
            regime_profile_bits,
            output_snapshot,
        }
    }
}

struct DeterministicStabilityOracle;

impl StabilityOracle for DeterministicStabilityOracle {
    fn run_stability(
        &mut self,
        _candidate: &CandidateCfg,
        program: &VmProgram,
        stability_runs: u32,
    ) -> Option<(f32, f32)> {
        if stability_runs == 0 {
            return None;
        }
        let signature = program_signature(program, 0xA3C5_9F41, stability_runs as u64);
        let mean = (((signature >> 12) & 0xFFFF) as f32 / 32768.0) - 1.0;
        let var = 1e-4 + (((signature >> 32) & 0x7FF) as f32 / 500_000.0);
        Some((mean, var))
    }
}

struct DeterministicTraceOracle;

impl TraceOracle for DeterministicTraceOracle {
    fn run_trace(&mut self, candidate: &CandidateCfg) -> TraceSummary {
        let mut blocks = Vec::with_capacity(candidate.blocks.len());
        let mut edges = Vec::new();
        for (idx, block) in candidate.blocks.iter().enumerate() {
            blocks.push(idx as u16);
            match block.term {
                Terminator::Jump { target, .. } => edges.push((idx as u16, target)),
                Terminator::CondZero {
                    true_target,
                    false_target,
                    ..
                }
                | Terminator::CondNonZero {
                    true_target,
                    false_target,
                    ..
                } => {
                    edges.push((idx as u16, true_target));
                    edges.push((idx as u16, false_target));
                }
                Terminator::Loop {
                    body_target,
                    exit_target,
                    ..
                } => {
                    edges.push((idx as u16, body_target));
                    edges.push((idx as u16, exit_target));
                }
                Terminator::Halt | Terminator::Return => {}
            }
        }
        TraceSummary {
            blocks,
            edges,
            checkpoints: candidate.total_words() as u32,
            score: candidate.total_words() as f32,
            fuel_used: (candidate.total_words() as u32).saturating_mul(2),
        }
    }
}

fn program_signature(program: &VmProgram, seed: u64, counter: u64) -> u64 {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&seed.to_le_bytes());
    hasher.update(&counter.to_le_bytes());
    for &word in &program.words {
        hasher.update(&word.to_le_bytes());
    }
    let digest = hasher.finalize();
    let bytes = digest.as_bytes();
    u64::from_le_bytes(bytes[0..8].try_into().unwrap_or([0_u8; 8]))
}

fn write_snapshot(
    run_dir: &Path,
    archive: &Archive,
    champion: Option<&Champion>,
    completed: u64,
    proxy_wins: u64,
    elapsed: Duration,
) -> Result<(), std::io::Error> {
    let elapsed_secs = elapsed.as_secs_f64().max(1e-6);
    let throughput = completed as f64 / elapsed_secs;
    let wins_per_hour = proxy_wins as f64 / (elapsed_secs / 3600.0);
    let (champ_mu, champ_var) = champion
        .map(|c| (c.full_mean, c.full_var))
        .unwrap_or((f32::NEG_INFINITY, f32::INFINITY));

    let summary_line = format!(
        "wins/hour={wins_per_hour:.3} champion_mu={champ_mu:.6} champion_var={champ_var:.6} filled_bins={} eval_throughput={throughput:.2}/s completed={completed}",
        archive.filled
    );
    println!("{summary_line}");

    let summary_json = format!(
        "{{\"wins_per_hour\":{wins_per_hour:.6},\"champion_mean\":{champ_mu:.6},\"champion_var\":{champ_var:.6},\"filled_bins\":{},\"eval_throughput\":{throughput:.6},\"completed\":{completed}}}",
        archive.filled
    );
    fs::write(run_dir.join("snapshot_latest.json"), summary_json)?;
    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
    Ok(())
}
