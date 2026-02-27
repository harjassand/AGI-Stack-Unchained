use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use baremetal_lgp::library::bank::LibraryBank;
use baremetal_lgp::library::LibraryImage;
use baremetal_lgp::oracle::{
    ExecConfig as OracleExecConfig, Oracle as RealOracle, OracleConfig as RealOracleConfig,
};
use baremetal_lgp::search::archive::Archive;
use baremetal_lgp::search::champion::{maybe_update_champion, Champion, StabilityOracle};
use baremetal_lgp::search::descriptors::{
    bin_id, build_descriptor, output_entropy_sketch, DescriptorInputs,
};
use baremetal_lgp::search::evaluate::{
    scan_instruction_profile, EvalReport, EvaluatedCandidate, ExecConfig as SearchExecConfig,
    Linker,
};
use baremetal_lgp::search::ir::{CandidateCfg, Terminator};
use baremetal_lgp::search::mutate::{
    mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT,
};
use baremetal_lgp::search::rng::Rng;
use baremetal_lgp::search::select::{select_parent, CHAMPION_INJECTION_P};
use baremetal_lgp::search::topk_trace::{TopKTraceManager, TraceOracle, TraceSummary};
use baremetal_lgp::types::CandidateId;
use baremetal_lgp::vm::{VmProgram, VmWorker};
use clap::Parser;
use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender};

const CHUNK_EVALS: u64 = 256;

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
    #[arg(long, default_value_t = 0)]
    profile_stride: u32,
    #[arg(long)]
    seed: Option<u64>,
}

#[repr(align(128))]
#[derive(Default)]
struct WorkerAtomics {
    evals: AtomicU64,
    proxy_wins: AtomicU64,
    filled_bins: AtomicU64,
    champion_bits: AtomicU64,
    mutate_ns: AtomicU64,
    link_ns: AtomicU64,
    oracle_ns: AtomicU64,
    archive_ns: AtomicU64,
}

impl WorkerAtomics {
    fn new() -> Self {
        Self {
            evals: AtomicU64::new(0),
            proxy_wins: AtomicU64::new(0),
            filled_bins: AtomicU64::new(0),
            champion_bits: AtomicU64::new(f64::NEG_INFINITY.to_bits()),
            mutate_ns: AtomicU64::new(0),
            link_ns: AtomicU64::new(0),
            oracle_ns: AtomicU64::new(0),
            archive_ns: AtomicU64::new(0),
        }
    }
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

struct ChampionEvent {
    worker_id: u32,
    champion_mean: f32,
    champ_hash_hex: String,
    champ_cfg: CandidateCfg,
}

#[derive(Clone)]
struct GlobalChampionMsg {
    champ_hash_hex: String,
    champ_mean: f32,
    champ_cfg: CandidateCfg,
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

    if args.workers.max(1) == 1 {
        return run_single_worker(&args);
    }

    run_island_multi_worker(&args)
}

fn run_single_worker(args: &Args) -> Result<(), String> {
    let library_bank = LibraryBank::new_seeded();
    let library = Arc::new(LibraryImage::from(&library_bank));
    let fallback_parent = CandidateCfg::default();
    let exec_cfg = SearchExecConfig {
        fuel_max: args.fuel_max,
        stability_runs: 3,
        stability_threshold: 0.0,
    };
    let oracle_cfg = RealOracleConfig {
        fuel_max: args.fuel_max,
        proxy_eps: 2,
        full_eps_per_family: 4,
        stability_runs: 3,
        topk_trace: args.topk_trace,
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
        let oracle_cfg = oracle_cfg;
        let seed_base = args.seed;
        worker_handles.push(thread::spawn(move || {
            worker_loop(worker_idx, rx, tx, shared_lib, cfg, oracle_cfg, seed_base)
        }));
    }
    drop(result_tx);

    let mut rng = if let Some(seed) = args.seed {
        Rng::new(mix64(seed ^ 0xA076_1D64_78BD_642F))
    } else {
        Rng::from_entropy()
    };
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
    let mut child_buf = CandidateCfg::default();
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
            mutate_candidate(
                parent,
                &archive,
                &mut rng,
                &mutation_weights,
                &mut child_buf,
            );
            let job = EvalJob {
                id: CandidateId(next_id),
                cfg: child_buf.clone(),
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
                    topk.write_champion_trace(result.id, &summary)
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

fn run_island_multi_worker(args: &Args) -> Result<(), String> {
    let worker_count = args.workers.max(1);
    let max_evals = if args.max_evals == 0 {
        u64::MAX
    } else {
        args.max_evals
    };
    let seed_base = args.seed.unwrap_or_else(|| os_seed(0xA5A5_A5A5_A5A5_A5A5));

    let library_bank = LibraryBank::new_seeded();
    let library = Arc::new(LibraryImage::from(&library_bank));
    let exec_cfg = SearchExecConfig {
        fuel_max: args.fuel_max,
        stability_runs: 3,
        stability_threshold: 0.0,
    };
    let oracle_cfg = RealOracleConfig {
        fuel_max: args.fuel_max,
        proxy_eps: 2,
        full_eps_per_family: 4,
        stability_runs: 3,
        topk_trace: args.topk_trace,
    };

    let total_claimed = Arc::new(AtomicU64::new(0));
    let atomics = Arc::new(
        (0..worker_count)
            .map(|_| WorkerAtomics::new())
            .collect::<Vec<_>>(),
    );

    let (champ_tx, champ_rx) = bounded::<ChampionEvent>(1024);
    let mut bcast_txs = Vec::with_capacity(worker_count);
    let mut bcast_rxs = Vec::with_capacity(worker_count);
    for _ in 0..worker_count {
        let (tx, rx) = bounded::<GlobalChampionMsg>(1);
        bcast_txs.push(tx);
        bcast_rxs.push(rx);
    }

    let mut worker_handles = Vec::with_capacity(worker_count);
    for (worker_id, bcast_rx) in bcast_rxs.into_iter().enumerate() {
        let lib = Arc::clone(&library);
        let cfg = exec_cfg.clone();
        let oracle_cfg = oracle_cfg;
        let total_claimed = Arc::clone(&total_claimed);
        let atomics = Arc::clone(&atomics);
        let champ_tx = champ_tx.clone();
        let run_dir = args.run_dir.clone();
        let profile_stride = args.profile_stride;

        worker_handles.push(thread::spawn(move || {
            worker_thread_main(
                worker_id,
                seed_base,
                max_evals,
                cfg,
                oracle_cfg,
                profile_stride,
                total_claimed,
                atomics,
                champ_tx,
                bcast_rx,
                lib,
                run_dir,
            )
        }));
    }
    drop(champ_tx);

    let started = Instant::now();
    let mut last_t = Instant::now();
    let mut last_sum_evals = 0_u64;
    let mut global_best_mean = f32::NEG_INFINITY;
    let mut global_best_hash = String::new();

    loop {
        thread::sleep(Duration::from_secs(1));

        let mut sum_evals = 0_u64;
        let mut sum_proxy_wins = 0_u64;
        let mut filled_bins_sum = 0_u64;
        let mut best_mean = f32::NEG_INFINITY;

        let mut profile_mutate_ns = 0_u64;
        let mut profile_link_ns = 0_u64;
        let mut profile_oracle_ns = 0_u64;
        let mut profile_archive_ns = 0_u64;

        for wa in atomics.iter() {
            sum_evals = sum_evals.saturating_add(wa.evals.load(Relaxed));
            sum_proxy_wins = sum_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
            filled_bins_sum = filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));

            let mean = f64::from_bits(wa.champion_bits.load(Relaxed)) as f32;
            if mean > best_mean {
                best_mean = mean;
            }

            if args.profile_stride > 0 {
                profile_mutate_ns = profile_mutate_ns.saturating_add(wa.mutate_ns.load(Relaxed));
                profile_link_ns = profile_link_ns.saturating_add(wa.link_ns.load(Relaxed));
                profile_oracle_ns = profile_oracle_ns.saturating_add(wa.oracle_ns.load(Relaxed));
                profile_archive_ns = profile_archive_ns.saturating_add(wa.archive_ns.load(Relaxed));
            }
        }

        while let Ok(evt) = champ_rx.try_recv() {
            let _source_worker = evt.worker_id;
            if evt.champion_mean > global_best_mean + 0.001 {
                global_best_mean = evt.champion_mean;
                global_best_hash = evt.champ_hash_hex.clone();

                let msg = GlobalChampionMsg {
                    champ_hash_hex: evt.champ_hash_hex,
                    champ_mean: evt.champion_mean,
                    champ_cfg: evt.champ_cfg,
                };
                for tx in &bcast_txs {
                    let _ = tx.try_send(msg.clone());
                }
            }
        }

        if best_mean > global_best_mean {
            global_best_mean = best_mean;
        }

        let dt = last_t.elapsed().as_secs_f64().max(1e-9);
        let d_evals = sum_evals.saturating_sub(last_sum_evals);
        let evals_per_sec = d_evals as f64 / dt;
        let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
        let wins_per_hour = sum_proxy_wins as f64 / (elapsed_secs / 3600.0);

        write_island_snapshot(
            &args.run_dir,
            sum_evals,
            evals_per_sec,
            wins_per_hour,
            global_best_mean,
            filled_bins_sum,
            &global_best_hash,
        )
        .map_err(|e| e.to_string())?;

        if args.profile_stride > 0 {
            write_profile_snapshot(
                &args.run_dir,
                args.profile_stride,
                sum_evals,
                profile_mutate_ns,
                profile_link_ns,
                profile_oracle_ns,
                profile_archive_ns,
            )
            .map_err(|e| e.to_string())?;
        }

        last_sum_evals = sum_evals;
        last_t = Instant::now();

        if args.max_evals != 0 && sum_evals >= args.max_evals {
            break;
        }
    }

    for handle in worker_handles {
        if handle.join().is_err() {
            return Err("worker thread panicked".to_string());
        }
    }

    let mut final_sum_evals = 0_u64;
    let mut final_proxy_wins = 0_u64;
    let mut final_filled_bins_sum = 0_u64;
    for wa in atomics.iter() {
        final_sum_evals = final_sum_evals.saturating_add(wa.evals.load(Relaxed));
        final_proxy_wins = final_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
        final_filled_bins_sum = final_filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));
    }

    let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
    let final_throughput = final_sum_evals as f64 / elapsed_secs;
    let final_wins_per_hour = final_proxy_wins as f64 / (elapsed_secs / 3600.0);

    write_island_snapshot(
        &args.run_dir,
        final_sum_evals,
        final_throughput,
        final_wins_per_hour,
        global_best_mean,
        final_filled_bins_sum,
        &global_best_hash,
    )
    .map_err(|e| e.to_string())?;

    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn worker_thread_main(
    worker_id: usize,
    seed_base: u64,
    max_evals: u64,
    exec_cfg: SearchExecConfig,
    oracle_cfg: RealOracleConfig,
    profile_stride: u32,
    total_claimed: Arc<AtomicU64>,
    atomics: Arc<Vec<WorkerAtomics>>,
    champ_tx: Sender<ChampionEvent>,
    bcast_rx: Receiver<GlobalChampionMsg>,
    library: Arc<LibraryImage>,
    run_dir: PathBuf,
) {
    let seed_worker = mix64(seed_base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_id as u64);

    let mut rng = Rng::new(seed_worker ^ 0xA076_1D64_78BD_642F);
    let mut archive = Archive::new();
    let mut champion: Option<Champion> = None;
    let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
    let mut next_weight_refresh = 4096_u64;

    let mut linker = NoopLinker::default();
    let mut oracle = RealOracle::new(oracle_cfg, seed_worker ^ 0xD6E8_FDDA_AE9D_3A57);
    let oracle_exec_cfg = OracleExecConfig {
        run_full_eval: true,
    };
    let mut vm_worker = VmWorker::default();
    let mut stability = DeterministicStabilityOracle;
    let mut child_buf = CandidateCfg::default();

    let fallback_parent = CandidateCfg::default();

    let mut global_champ_mean = f32::NEG_INFINITY;
    let mut global_champ_cfg: Option<CandidateCfg> = None;

    let mut local_evals = 0_u64;
    let mut local_proxy_wins = 0_u64;

    let mut prof_mutate_ns = 0_u64;
    let mut prof_link_ns = 0_u64;
    let mut prof_oracle_ns = 0_u64;
    let mut prof_archive_ns = 0_u64;

    loop {
        let start = total_claimed.fetch_add(CHUNK_EVALS, Relaxed);
        if start >= max_evals {
            break;
        }
        let end = start.saturating_add(CHUNK_EVALS).min(max_evals);
        let n = end.saturating_sub(start);

        if local_evals >= next_weight_refresh {
            if let Some(next) = read_mutation_weights(&run_dir) {
                mutation_weights = next;
            }
            next_weight_refresh = next_weight_refresh.saturating_add(4096);
        }

        let mut pending_champion_event: Option<ChampionEvent> = None;

        for j in 0..n {
            let eidx = start + j;
            let do_prof = profile_stride > 0 && (eidx % u64::from(profile_stride) == 0);

            let parent = if global_champ_cfg.is_some()
                && global_champ_mean.is_finite()
                && rng.gen_bool(CHAMPION_INJECTION_P)
            {
                global_champ_cfg.as_ref().unwrap_or(&fallback_parent)
            } else {
                select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
                    .map_or(&fallback_parent, |elite| &elite.candidate)
            };

            if do_prof {
                let t = Instant::now();
                mutate_candidate(
                    parent,
                    &archive,
                    &mut rng,
                    &mutation_weights,
                    &mut child_buf,
                );
                prof_mutate_ns = prof_mutate_ns.saturating_add(elapsed_nanos_u64(t));
            } else {
                mutate_candidate(
                    parent,
                    &archive,
                    &mut rng,
                    &mutation_weights,
                    &mut child_buf,
                );
            }

            let program = if do_prof {
                let t = Instant::now();
                let linked = linker.link(&child_buf);
                prof_link_ns = prof_link_ns.saturating_add(elapsed_nanos_u64(t));
                linked
            } else {
                linker.link(&child_buf)
            };

            let report = if do_prof {
                let t = Instant::now();
                let eval = evaluate_with_real_oracle(
                    &mut oracle,
                    &oracle_exec_cfg,
                    &mut vm_worker,
                    &program,
                    &library,
                    &exec_cfg,
                );
                prof_oracle_ns = prof_oracle_ns.saturating_add(elapsed_nanos_u64(t));
                eval
            } else {
                evaluate_with_real_oracle(
                    &mut oracle,
                    &oracle_exec_cfg,
                    &mut vm_worker,
                    &program,
                    &library,
                    &exec_cfg,
                )
            };

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

            let evaluated = EvaluatedCandidate {
                child_cfg: child_buf.clone(),
                program,
                report: report.clone(),
                profile,
                desc,
                bin: bin_id(&desc),
                score: report.full_mean.unwrap_or(report.proxy_mean),
                fuel_used,
                code_size_words,
            };

            let champion_updated = if do_prof {
                let t = Instant::now();
                archive.insert(evaluated.bin, evaluated.to_elite());
                let updated =
                    maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability);
                prof_archive_ns = prof_archive_ns.saturating_add(elapsed_nanos_u64(t));
                updated
            } else {
                archive.insert(evaluated.bin, evaluated.to_elite());
                maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability)
            };

            if evaluated.score > 0.0 {
                local_proxy_wins = local_proxy_wins.saturating_add(1);
            }
            local_evals = local_evals.saturating_add(1);

            if champion_updated {
                if let Some(current) = champion.as_ref() {
                    let evt = ChampionEvent {
                        worker_id: worker_id as u32,
                        champion_mean: current.full_mean,
                        champ_hash_hex: program_hash_hex(&evaluated.program),
                        champ_cfg: current.elite.candidate.clone(),
                    };
                    let replace = pending_champion_event
                        .as_ref()
                        .map_or(true, |prev| evt.champion_mean > prev.champion_mean);
                    if replace {
                        pending_champion_event = Some(evt);
                    }
                }
            }
        }

        let wa = &atomics[worker_id];
        wa.evals.store(local_evals, Relaxed);
        wa.proxy_wins.store(local_proxy_wins, Relaxed);
        wa.filled_bins.store(u64::from(archive.filled), Relaxed);
        let champion_mean = champion
            .as_ref()
            .map_or(f64::NEG_INFINITY, |c| c.full_mean as f64);
        wa.champion_bits.store(champion_mean.to_bits(), Relaxed);

        if profile_stride > 0 {
            wa.mutate_ns.store(prof_mutate_ns, Relaxed);
            wa.link_ns.store(prof_link_ns, Relaxed);
            wa.oracle_ns.store(prof_oracle_ns, Relaxed);
            wa.archive_ns.store(prof_archive_ns, Relaxed);
        }

        if let Some(evt) = pending_champion_event {
            let _ = champ_tx.try_send(evt);
        }

        while let Ok(msg) = bcast_rx.try_recv() {
            global_champ_mean = msg.champ_mean;
            global_champ_cfg = Some(msg.champ_cfg);
            let _ = msg.champ_hash_hex;
        }
    }
}

fn worker_loop(
    worker_idx: usize,
    rx: Receiver<Option<EvalJob>>,
    tx: Sender<EvalResult>,
    library: Arc<LibraryImage>,
    exec_cfg: SearchExecConfig,
    oracle_cfg: RealOracleConfig,
    seed_base: Option<u64>,
) {
    let mut worker = VmWorker::default();
    let mut linker = NoopLinker::default();
    let oracle_seed = seed_base
        .map(|base| mix64(base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_idx as u64))
        .unwrap_or_else(|| os_seed(worker_idx as u64 + 1));
    let mut oracle = RealOracle::new(oracle_cfg, oracle_seed);
    let oracle_exec_cfg = OracleExecConfig {
        run_full_eval: true,
    };

    while let Ok(job) = rx.recv() {
        let Some(job) = job else {
            break;
        };
        let evaluated = evaluate_cfg(
            job.cfg,
            &mut linker,
            &mut oracle,
            &oracle_exec_cfg,
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

fn mix64(mut z: u64) -> u64 {
    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

fn elapsed_nanos_u64(start: Instant) -> u64 {
    let nanos = start.elapsed().as_nanos();
    if nanos > u128::from(u64::MAX) {
        u64::MAX
    } else {
        nanos as u64
    }
}

fn program_hash_hex(program: &VmProgram) -> String {
    let mut hasher = blake3::Hasher::new();
    hasher.update(&(program.words.len() as u64).to_le_bytes());
    for &word in &program.words {
        hasher.update(&word.to_le_bytes());
    }
    hasher.finalize().to_hex().to_string()
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

fn evaluate_cfg<L>(
    cfg: CandidateCfg,
    linker: &mut L,
    oracle: &mut RealOracle,
    oracle_exec_cfg: &OracleExecConfig,
    worker: &mut VmWorker,
    library: &LibraryImage,
    exec_cfg: &SearchExecConfig,
) -> EvaluatedCandidate
where
    L: Linker,
{
    let program = linker.link(&cfg);
    let report =
        evaluate_with_real_oracle(oracle, oracle_exec_cfg, worker, &program, library, exec_cfg);
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
            const_pool: [0.0; baremetal_lgp::abi::CONST_POOL_WORDS],
            #[cfg(feature = "trace")]
            pc_to_block: Vec::new(),
        }
    }
}

fn evaluate_with_real_oracle(
    oracle: &mut RealOracle,
    oracle_exec_cfg: &OracleExecConfig,
    worker: &mut VmWorker,
    program: &VmProgram,
    library: &LibraryImage,
    exec_cfg: &SearchExecConfig,
) -> EvalReport {
    let report = oracle.eval_candidate(worker, program, library, oracle_exec_cfg);
    let fuel_used = (program.words.len() as u32 + 1).min(exec_cfg.fuel_max.max(1));
    let output_len = worker.scratch.len().min(64);
    let output_snapshot = worker.scratch[..output_len].to_vec();
    EvalReport {
        proxy_mean: report.proxy_mean,
        proxy_fuel_used: fuel_used,
        full_mean: report.full_mean,
        full_var: report.full_var,
        full_fuel_used: report.full_mean.map(|_| fuel_used),
        regime_profile_bits: report.regime_profile_bits,
        output_snapshot,
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

fn write_island_snapshot(
    run_dir: &Path,
    completed: u64,
    throughput: f64,
    wins_per_hour: f64,
    champ_mu: f32,
    filled_bins_sum_islands: u64,
    champ_hash_hex: &str,
) -> Result<(), std::io::Error> {
    let champ_var = f32::INFINITY;
    let summary_line = format!(
        "wins/hour={wins_per_hour:.3} champion_mu={champ_mu:.6} champion_var={champ_var:.6} filled_bins={filled_bins_sum_islands} filled_bins_sum_islands={filled_bins_sum_islands} eval_throughput={throughput:.2}/s completed={completed} champion_hash={champ_hash_hex}",
    );
    println!("{summary_line}");

    let summary_json = format!(
        "{{\"wins_per_hour\":{wins_per_hour:.6},\"champion_mean\":{champ_mu:.6},\"champion_var\":{champ_var:.6},\"filled_bins\":{filled_bins_sum_islands},\"filled_bins_sum_islands\":{filled_bins_sum_islands},\"eval_throughput\":{throughput:.6},\"completed\":{completed}}}"
    );
    fs::write(run_dir.join("snapshot_latest.json"), summary_json)?;
    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
    Ok(())
}

fn write_profile_snapshot(
    run_dir: &Path,
    profile_stride: u32,
    completed: u64,
    mutate_ns: u64,
    link_ns: u64,
    oracle_ns: u64,
    archive_ns: u64,
) -> Result<(), std::io::Error> {
    if profile_stride == 0 {
        return Ok(());
    }

    let sampled = completed / u64::from(profile_stride.max(1));
    let profile_line = format!(
        "profile_stride={profile_stride} sampled={sampled} mutate_ns={mutate_ns} link_ns={link_ns} oracle_ns={oracle_ns} archive_ns={archive_ns}"
    );
    fs::write(run_dir.join("profile_latest.txt"), profile_line)
}
