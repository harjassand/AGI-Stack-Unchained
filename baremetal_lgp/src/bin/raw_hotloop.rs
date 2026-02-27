use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use baremetal_lgp::jit2::mutate::mutate_words;
use baremetal_lgp::jit2::sniper::WorkerWatch;
use baremetal_lgp::jit2::swap::{EpochHealth, KernelSwapState};
use baremetal_lgp::jit2::templates::default_templates;
use baremetal_lgp::oracle::raw::RawOracle;
use baremetal_lgp::oracle::{ExecConfig as OracleExecConfig, OracleConfig, SplitMix64};
use clap::Parser;

const CHUNK_EVALS: u64 = 128;

#[derive(Parser, Debug)]
#[command(name = "raw_hotloop")]
#[command(about = "Phase-2 Raw AArch64 substrate hot loop")]
struct Args {
    #[arg(long)]
    run_dir: PathBuf,
    #[arg(long, default_value_t = 6)]
    workers: usize,
    #[arg(long, default_value_t = 0)]
    max_evals: u64,
    #[arg(long)]
    seed: Option<u64>,
}

#[repr(align(128))]
#[derive(Default)]
struct WorkerAtomics {
    evals: AtomicU64,
    proxy_wins: AtomicU64,
    traps: AtomicU64,
    timeouts: AtomicU64,
    best_bits: AtomicU64,
}

impl WorkerAtomics {
    fn new() -> Self {
        Self {
            evals: AtomicU64::new(0),
            proxy_wins: AtomicU64::new(0),
            traps: AtomicU64::new(0),
            timeouts: AtomicU64::new(0),
            best_bits: AtomicU64::new(f64::NEG_INFINITY.to_bits()),
        }
    }
}

fn main() {
    if let Err(err) = run() {
        eprintln!("raw_hotloop failed: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let args = Args::parse();
    fs::create_dir_all(&args.run_dir).map_err(|e| e.to_string())?;

    let workers = args.workers.max(1);
    let max_evals = if args.max_evals == 0 {
        u64::MAX
    } else {
        args.max_evals
    };
    let seed_base = args
        .seed
        .unwrap_or_else(|| os_seed(0xC0DE_CAFE_1BAD_B002_u64));

    let templates = default_templates();
    let initial_words = templates
        .first()
        .map(|t| t.words.clone())
        .unwrap_or_else(|| vec![0xD65F03C0]);
    let swap_state = Arc::new(KernelSwapState::new(initial_words));

    let total_claimed = Arc::new(AtomicU64::new(0));
    let atomics = Arc::new(
        (0..workers)
            .map(|_| WorkerAtomics::new())
            .collect::<Vec<_>>(),
    );
    let global_best = Arc::new(Mutex::new(f32::NEG_INFINITY));

    let mut handles = Vec::with_capacity(workers);
    for worker_id in 0..workers {
        let run_dir = args.run_dir.clone();
        let total_claimed = Arc::clone(&total_claimed);
        let atomics = Arc::clone(&atomics);
        let swap_state = Arc::clone(&swap_state);
        let global_best = Arc::clone(&global_best);
        let templates_local: Vec<Vec<u32>> = templates.iter().map(|t| t.words.clone()).collect();

        handles.push(thread::spawn(move || {
            worker_loop(
                worker_id,
                seed_base,
                max_evals,
                total_claimed,
                atomics,
                swap_state,
                global_best,
                templates_local,
                run_dir,
            )
        }));
    }

    let started = Instant::now();
    let mut last_t = Instant::now();
    let mut last_sum_evals = 0_u64;

    loop {
        thread::sleep(Duration::from_secs(1));

        let mut sum_evals = 0_u64;
        let mut sum_proxy_wins = 0_u64;
        let mut sum_traps = 0_u64;
        let mut sum_timeouts = 0_u64;
        let mut best_mean = f32::NEG_INFINITY;

        for wa in atomics.iter() {
            sum_evals = sum_evals.saturating_add(wa.evals.load(Relaxed));
            sum_proxy_wins = sum_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
            sum_traps = sum_traps.saturating_add(wa.traps.load(Relaxed));
            sum_timeouts = sum_timeouts.saturating_add(wa.timeouts.load(Relaxed));

            let local_best = f64::from_bits(wa.best_bits.load(Relaxed)) as f32;
            if local_best > best_mean {
                best_mean = local_best;
            }
        }

        let dt = last_t.elapsed().as_secs_f64().max(1e-9);
        let d_evals = sum_evals.saturating_sub(last_sum_evals);
        let evals_per_sec = d_evals as f64 / dt;
        let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
        let wins_per_hour = sum_proxy_wins as f64 / (elapsed_secs / 3600.0);

        let active = swap_state.active_kernel();
        write_snapshot(
            &args.run_dir,
            sum_evals,
            evals_per_sec,
            wins_per_hour,
            best_mean,
            sum_traps,
            sum_timeouts,
            active.epoch,
        )
        .map_err(|e| e.to_string())?;

        last_sum_evals = sum_evals;
        last_t = Instant::now();

        if sum_evals >= max_evals {
            break;
        }
    }

    for handle in handles {
        if handle.join().is_err() {
            return Err("worker thread panicked".to_string());
        }
    }

    let mut final_evals = 0_u64;
    let mut final_proxy_wins = 0_u64;
    let mut final_traps = 0_u64;
    let mut final_timeouts = 0_u64;
    let mut final_best = f32::NEG_INFINITY;

    for wa in atomics.iter() {
        final_evals = final_evals.saturating_add(wa.evals.load(Relaxed));
        final_proxy_wins = final_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
        final_traps = final_traps.saturating_add(wa.traps.load(Relaxed));
        final_timeouts = final_timeouts.saturating_add(wa.timeouts.load(Relaxed));
        let local_best = f64::from_bits(wa.best_bits.load(Relaxed)) as f32;
        if local_best > final_best {
            final_best = local_best;
        }
    }

    let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
    let throughput = final_evals as f64 / elapsed_secs;
    let wins_per_hour = final_proxy_wins as f64 / (elapsed_secs / 3600.0);
    let active = swap_state.active_kernel();
    write_snapshot(
        &args.run_dir,
        final_evals,
        throughput,
        wins_per_hour,
        final_best,
        final_traps,
        final_timeouts,
        active.epoch,
    )
    .map_err(|e| e.to_string())?;

    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn worker_loop(
    worker_id: usize,
    seed_base: u64,
    max_evals: u64,
    total_claimed: Arc<AtomicU64>,
    atomics: Arc<Vec<WorkerAtomics>>,
    swap_state: Arc<KernelSwapState>,
    global_best: Arc<Mutex<f32>>,
    templates: Vec<Vec<u32>>,
    _run_dir: PathBuf,
) {
    let worker_seed = mix64(seed_base ^ worker_id as u64 ^ 0x9E37_79B9_7F4A_7C15);
    let mut rng = SplitMix64::new(worker_seed);

    let watch = Box::leak(Box::new(WorkerWatch::new()));
    let mut raw_ctx = baremetal_lgp::jit2::raw_runner::raw_thread_init(watch);

    let oracle_cfg = OracleConfig {
        fuel_max: 200_000,
        proxy_eps: 2,
        full_eps_per_family: 4,
        stability_runs: 3,
        topk_trace: 0,
    };
    let mut oracle = RawOracle::new(oracle_cfg, worker_seed ^ 0xD6E8_FDDA_AE9D_3A57);
    let oracle_exec_cfg = OracleExecConfig {
        run_full_eval: true,
    };

    let mut local_evals = 0_u64;
    let mut local_proxy_wins = 0_u64;
    let mut local_traps = 0_u64;
    let mut local_timeouts = 0_u64;
    let mut local_best = f32::NEG_INFINITY;

    let mut epoch_score_sum = 0.0_f32;
    let mut epoch_traps = 0_u64;
    let mut epoch_timeouts = 0_u64;
    let mut epoch_evals = 0_u64;

    let mut pending_candidate: Option<(Vec<u32>, f32)> = None;

    loop {
        let start = total_claimed.fetch_add(CHUNK_EVALS, Relaxed);
        if start >= max_evals {
            break;
        }
        let end = start.saturating_add(CHUNK_EVALS).min(max_evals);
        let n = end.saturating_sub(start);

        for _ in 0..n {
            let active = swap_state.active_kernel();
            if raw_ctx.installed_epoch != active.epoch || raw_ctx.installed_hash != active.hash {
                let _ = raw_ctx.arena.install_active(active.words.as_slice());
                raw_ctx.installed_epoch = active.epoch;
                raw_ctx.installed_hash = active.hash;
            }

            let template = &templates[rng.next_usize(templates.len())];
            let parent = if rng.next_f32() < 0.75 {
                active.words.as_slice()
            } else {
                template.as_slice()
            };
            let donor = if rng.next_f32() < 0.5 {
                Some(active.words.as_slice())
            } else {
                None
            };

            let candidate = mutate_words(&mut rng, parent, donor);
            let report = oracle.eval_raw_candidate(&mut raw_ctx, &candidate, &oracle_exec_cfg);
            let score = report.full_mean.unwrap_or(report.proxy_mean);

            local_evals = local_evals.saturating_add(1);
            epoch_evals = epoch_evals.saturating_add(1);
            epoch_score_sum += score;

            if report.proxy_mean > 0.0 {
                local_proxy_wins = local_proxy_wins.saturating_add(1);
            }

            let trapped = report.trap_rate > 0.0;
            let timed_out = report.timeout_rate > 0.0;
            if trapped {
                local_traps = local_traps.saturating_add(1);
                epoch_traps = epoch_traps.saturating_add(1);
            }
            if timed_out {
                local_timeouts = local_timeouts.saturating_add(1);
                epoch_timeouts = epoch_timeouts.saturating_add(1);
            }

            if score > local_best {
                local_best = score;
            }

            if report.trap_rate <= 0.10 {
                let replace = pending_candidate
                    .as_ref()
                    .map_or(true, |(_, prev)| score > *prev);
                if replace {
                    pending_candidate = Some((candidate.clone(), score));
                }
            }

            if swap_state.on_eval_batch(1) {
                if let Some((words, cand_score)) = pending_candidate.take() {
                    let stability = oracle.run_stability(&mut raw_ctx, &words);
                    if RawOracle::stability_passes_promotion(&stability) {
                        let mut gate = global_best.lock().expect("global_best lock poisoned");
                        if cand_score > *gate {
                            *gate = cand_score;
                            let _ = swap_state.publish_new_kernel(words);
                        }
                    }
                }

                if epoch_evals > 0 {
                    let health = EpochHealth {
                        mean_score: epoch_score_sum / epoch_evals as f32,
                        trap_rate: epoch_traps as f32 / epoch_evals as f32,
                        timeout_rate: epoch_timeouts as f32 / epoch_evals as f32,
                    };
                    let _ = swap_state.maybe_rollback(health, 0.05, 0.02);
                }

                epoch_score_sum = 0.0;
                epoch_traps = 0;
                epoch_timeouts = 0;
                epoch_evals = 0;
            }
        }

        let wa = &atomics[worker_id];
        wa.evals.store(local_evals, Relaxed);
        wa.proxy_wins.store(local_proxy_wins, Relaxed);
        wa.traps.store(local_traps, Relaxed);
        wa.timeouts.store(local_timeouts, Relaxed);
        wa.best_bits.store((local_best as f64).to_bits(), Relaxed);
    }
}

fn write_snapshot(
    run_dir: &Path,
    completed: u64,
    throughput: f64,
    wins_per_hour: f64,
    champ_mu: f32,
    traps: u64,
    timeouts: u64,
    active_epoch: u64,
) -> Result<(), std::io::Error> {
    let champ_var = f32::INFINITY;
    let trap_rate = if completed == 0 {
        0.0
    } else {
        traps as f64 / completed as f64
    };
    let timeout_rate = if completed == 0 {
        0.0
    } else {
        timeouts as f64 / completed as f64
    };

    let summary_line = format!(
        "wins/hour={wins_per_hour:.3} champion_mu={champ_mu:.6} champion_var={champ_var:.6} filled_bins=0 eval_throughput={throughput:.2}/s completed={completed} traps={traps} timeouts={timeouts} trap_rate={trap_rate:.6} timeout_rate={timeout_rate:.6} active_epoch={active_epoch}"
    );
    println!("{summary_line}");

    let summary_json = format!(
        "{{\"wins_per_hour\":{wins_per_hour:.6},\"champion_mean\":{champ_mu:.6},\"champion_var\":{champ_var:.6},\"filled_bins\":0,\"eval_throughput\":{throughput:.6},\"completed\":{completed},\"traps\":{traps},\"timeouts\":{timeouts},\"trap_rate\":{trap_rate:.6},\"timeout_rate\":{timeout_rate:.6},\"active_epoch\":{active_epoch}}}"
    );
    fs::write(run_dir.join("snapshot_latest.json"), summary_json)?;
    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
    Ok(())
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
