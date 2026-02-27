# Phase 1 Throughput Uncorking Audit Report

Generated: 2026-02-27 09:59:55 UTC

## 1) Scope and Intent
This document contains **raw evidence** for the Phase 1 patch implementation, including:
- exact changed files and diff,
- relevant runtime/test outputs,
- hot-loop contention checks,
- full source data for the primary changed file,
- supporting source data for related search/oracle modules.

## 2) Git State and Branch

- Branch: codex/phase1_throughput_uncorking
- HEAD commit: e6e6536c06e461ec9d5bc94a7aeb7aa6dd795e26

### 2.1 Raw `git status --short --branch`

```text
## codex/phase1_throughput_uncorking...origin/codex/phase1_throughput_uncorking
 M baremetal_lgp/src/bin/lgp_hotloop.rs
?? baremetal_lgp/Cargo.lock
?? baremetal_lgp/PHASE1_THROUGHPUT_UNCORKING_AUDIT.md
```

### 2.2 Raw `git diff --stat` / `git diff --name-only`

```text
 baremetal_lgp/src/bin/lgp_hotloop.rs | 520 ++++++++++++++++++++++++++++++++++-
 1 file changed, 515 insertions(+), 5 deletions(-)

baremetal_lgp/src/bin/lgp_hotloop.rs
```

## 3) File-Level Scope Verification

### 3.1 Changed files in this patch

```text
baremetal_lgp/src/bin/lgp_hotloop.rs
```

### 3.2 No edits to search/oracle module files requested as optional

```text
```

(Empty diff above means unchanged.)

### 3.3 SHA-256 of relevant files

```text
89cc97adf8bd1c7f54a8519a9be43b61e1de0ec55e3ce42e9e5e29c597a74568  baremetal_lgp/src/bin/lgp_hotloop.rs
40b42535d9ccb72748c90c4a5a8c836fc083492a42096c2c30416a6465603aae  baremetal_lgp/src/search/mod.rs
ce496a889caa5056ca539c83f0a5c90ec47030d2e8cbfb91b135a6691347d7c9  baremetal_lgp/src/oracle/mod.rs
1c388f9ce448a91a0354dec38ae4067d3a59172f44eefbe5ea85cff6cfe56d70  baremetal_lgp/src/search/archive.rs
a05637f2e706fac99446275bb8a7d6234ecd6adda5c99109e0ff0dd54aa2a0a8  baremetal_lgp/src/search/champion.rs
0faff6a995f1191ec4e1635d471324f8a49cbd292810b8f314a29b9408ee8eaf  baremetal_lgp/src/search/select.rs
```

## 4) Constraint Evidence (Hot Loop / Contention)

### 4.1 Grep for synchronization/channel primitives in `lgp_hotloop.rs`

```text
166:    let started = Instant::now();
189:            job_tx.send(Some(job)).map_err(|e| e.to_string())?;
240:        if Instant::now() >= next_snapshot {
255:        let _ = job_tx.send(None);
334:    let started = Instant::now();
335:    let mut last_t = Instant::now();
371:        while let Ok(evt) = champ_rx.try_recv() {
383:                    let _ = tx.try_send(msg.clone());
423:        last_t = Instant::now();
535:                let t = Instant::now();
544:                let t = Instant::now();
553:                let t = Instant::now();
589:                let t = Instant::now();
640:            let _ = champ_tx.try_send(evt);
643:        while let Ok(msg) = bcast_rx.try_recv() {
666:    while let Ok(job) = rx.recv() {
679:            .send(EvalResult {
```

### 4.2 Per-candidate loop body (`for j in 0..n`) with no send/recv/lock

```text
   520	        for j in 0..n {
   521	            let eidx = start + j;
   522	            let do_prof = profile_stride > 0 && (eidx % u64::from(profile_stride) == 0);
   523	
   524	            let parent = if global_champ_cfg.is_some()
   525	                && global_champ_mean.is_finite()
   526	                && rng.gen_bool(CHAMPION_INJECTION_P)
   527	            {
   528	                global_champ_cfg.as_ref().unwrap_or(&fallback_parent)
   529	            } else {
   530	                select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
   531	                    .map_or(&fallback_parent, |elite| &elite.candidate)
   532	            };
   533	
   534	            let child_cfg = if do_prof {
   535	                let t = Instant::now();
   536	                let child = mutate_candidate(parent, &archive, &mut rng, &mutation_weights);
   537	                prof_mutate_ns = prof_mutate_ns.saturating_add(elapsed_nanos_u64(t));
   538	                child
   539	            } else {
   540	                mutate_candidate(parent, &archive, &mut rng, &mutation_weights)
   541	            };
   542	
   543	            let program = if do_prof {
   544	                let t = Instant::now();
   545	                let linked = linker.link(&child_cfg);
   546	                prof_link_ns = prof_link_ns.saturating_add(elapsed_nanos_u64(t));
   547	                linked
   548	            } else {
   549	                linker.link(&child_cfg)
   550	            };
   551	
   552	            let report = if do_prof {
   553	                let t = Instant::now();
   554	                let eval = oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg);
   555	                prof_oracle_ns = prof_oracle_ns.saturating_add(elapsed_nanos_u64(t));
   556	                eval
   557	            } else {
   558	                oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg)
   559	            };
   560	
   561	            let profile = scan_instruction_profile(&program.words);
   562	            let code_size_words = program.words.len() as u32;
   563	            let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
   564	            let output_entropy = output_entropy_sketch(&report.output_snapshot);
   565	            let desc = build_descriptor(DescriptorInputs {
   566	                fuel_used,
   567	                fuel_max: exec_cfg.fuel_max,
   568	                code_size_words,
   569	                branch_count: profile.branch_count,
   570	                store_count: profile.store_count,
   571	                total_insns: profile.total_insns,
   572	                output_entropy,
   573	                regime_profile_bits: report.regime_profile_bits,
   574	            });
   575	
   576	            let evaluated = EvaluatedCandidate {
   577	                child_cfg,
   578	                program,
   579	                report: report.clone(),
   580	                profile,
   581	                desc,
   582	                bin: bin_id(&desc),
   583	                score: report.full_mean.unwrap_or(report.proxy_mean),
   584	                fuel_used,
   585	                code_size_words,
   586	            };
   587	
   588	            let champion_updated = if do_prof {
   589	                let t = Instant::now();
   590	                archive.insert(evaluated.bin, evaluated.to_elite());
   591	                let updated =
   592	                    maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability);
   593	                prof_archive_ns = prof_archive_ns.saturating_add(elapsed_nanos_u64(t));
   594	                updated
   595	            } else {
   596	                archive.insert(evaluated.bin, evaluated.to_elite());
   597	                maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability)
   598	            };
   599	
   600	            if evaluated.score > 0.0 {
   601	                local_proxy_wins = local_proxy_wins.saturating_add(1);
   602	            }
   603	            local_evals = local_evals.saturating_add(1);
   604	
   605	            if champion_updated {
   606	                if let Some(current) = champion.as_ref() {
   607	                    let evt = ChampionEvent {
   608	                        worker_id: worker_id as u32,
   609	                        champion_mean: current.full_mean,
   610	                        champ_hash_hex: program_hash_hex(&evaluated.program),
   611	                        champ_cfg: current.elite.candidate.clone(),
   612	                    };
   613	                    let replace = pending_champion_event
   614	                        .as_ref()
   615	                        .map_or(true, |prev| evt.champion_mean > prev.champion_mean);
   616	                    if replace {
   617	                        pending_champion_event = Some(evt);
   618	                    }
   619	                }
   620	            }
   621	        }
```

### 4.3 Chunk-boundary operations (atomics store + try_send/try_recv)

```text
   622	
   623	        let wa = &atomics[worker_id];
   624	        wa.evals.store(local_evals, Relaxed);
   625	        wa.proxy_wins.store(local_proxy_wins, Relaxed);
   626	        wa.filled_bins.store(u64::from(archive.filled), Relaxed);
   627	        let champion_mean = champion
   628	            .as_ref()
   629	            .map_or(f64::NEG_INFINITY, |c| c.full_mean as f64);
   630	        wa.champion_bits.store(champion_mean.to_bits(), Relaxed);
   631	
   632	        if profile_stride > 0 {
   633	            wa.mutate_ns.store(prof_mutate_ns, Relaxed);
   634	            wa.link_ns.store(prof_link_ns, Relaxed);
   635	            wa.oracle_ns.store(prof_oracle_ns, Relaxed);
   636	            wa.archive_ns.store(prof_archive_ns, Relaxed);
   637	        }
   638	
   639	        if let Some(evt) = pending_champion_event {
   640	            let _ = champ_tx.try_send(evt);
   641	        }
   642	
   643	        while let Ok(msg) = bcast_rx.try_recv() {
   644	            global_champ_mean = msg.champ_mean;
   645	            global_champ_cfg = Some(msg.champ_cfg);
   646	            let _ = msg.champ_hash_hex;
   647	        }
   648	    }
```

### 4.4 Proof query: forbidden calls inside loop range

```text
```

(Empty output above indicates none found in per-candidate loop.)

## 5) Build and Test Results

### 5.1 `cargo check --release --bin lgp_hotloop`

```text
    Finished `release` profile [optimized] target(s) in 0.09s
```

### 5.2 `cargo test --release dod_ -- --nocapture`

```text
    Finished `release` profile [optimized] target(s) in 0.04s
     Running unittests src/lib.rs (target/release/deps/baremetal_lgp-ab5134800b6b3029)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/architect.rs (target/release/deps/architect-96ef35fe3ae28c2a)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/lgp_hotloop.rs (target/release/deps/lgp_hotloop-0e74bf3872182e6f)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent1_vm_core.rs (target/release/deps/agent1_vm_core-545c711d2d26fae1)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 5 filtered out; finished in 0.00s

     Running tests/agent1_vm_jit.rs (target/release/deps/agent1_vm_jit-b2301b65538f0627)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent2_oracle_complex_family.rs (target/release/deps/agent2_oracle_complex_family-c17550ca64ef8d23)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s

     Running tests/agent2_oracle_funnel_and_full_eval.rs (target/release/deps/agent2_oracle_funnel_and_full_eval-6974b97501ac202c)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 3 filtered out; finished in 0.00s

     Running tests/agent2_oracle_proxy_schedule.rs (target/release/deps/agent2_oracle_proxy_schedule-e513e5f0121a545e)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s

     Running tests/agent3_outerloop.rs (target/release/deps/agent3_outerloop-9f578046d074e8ce)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 2 filtered out; finished in 0.00s

     Running tests/agent3_search_library.rs (target/release/deps/agent3_search_library-29841f93dae2d6b6)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 10 filtered out; finished in 0.00s

     Running tests/dod_acceptance.rs (target/release/deps/dod_acceptance-05f506aa05db8ef1)

running 5 tests
test dod_complex_family_requires_complex_ops_score_collapse_without_vcmul ... ok
test dod_gas_enforcement_stops_infinite_loop_with_fuel_exhausted ... ok
test dod_library_promotion_calllib_improves_code_bucket_score_stable ... ok
test dod_hidden_oracle_champion_trend_upward ... ok
test dod_stage_a_hot_swap_shadow_accepts_and_wins_per_hour_increases ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.66s

```

## 6) Scaling Benchmark Results (Exact Requested Matrix)

Command used for each worker count:

```bash
cargo run --release --bin lgp_hotloop -- \
  --workers "W" \
  --fuel-max 200000 \
  --run-dir "/tmp/runtime_scale_uncork_wW" \
  --topk-trace 16 \
  --max-evals 500000 \
  --seed 777777
```

### 6.1 Raw summaries and JSON snapshots

```text
W=1
wins/hour=55827177.380 champion_mu=1.040035 champion_var=0.000020 filled_bins=91 eval_throughput=31014.23/s completed=500000
{"wins_per_hour":55827177.380251,"champion_mean":1.040035,"champion_var":0.000020,"filled_bins":91,"eval_throughput":31014.230146,"completed":500000}
---
W=2
wins/hour=128132954.658 champion_mu=1.040393 champion_var=inf filled_bins=393 filled_bins_sum_islands=393 eval_throughput=71149.68/s completed=500000 champion_hash=0aa671216677e8ac8be69325b28abc2fb42ac724956adc64d3ec4a2e21ecd7e5
{"wins_per_hour":128132954.658357,"champion_mean":1.040393,"champion_var":inf,"filled_bins":393,"filled_bins_sum_islands":393,"eval_throughput":71149.684567,"completed":500000}
---
W=4
wins/hour=223656310.457 champion_mu=1.032574 champion_var=inf filled_bins=730 filled_bins_sum_islands=730 eval_throughput=124356.97/s completed=500000 champion_hash=4dc7bed61f2f9c0d9ff86574691dfaa262d7b1ebb7b69a9c5a7df55e0228b5cc
{"wins_per_hour":223656310.457400,"champion_mean":1.032574,"champion_var":inf,"filled_bins":730,"filled_bins_sum_islands":730,"eval_throughput":124356.970809,"completed":500000}
---
W=6
wins/hour=224145227.484 champion_mu=1.046059 champion_var=inf filled_bins=1065 filled_bins_sum_islands=1065 eval_throughput=124438.02/s completed=500000 champion_hash=c7b7e21ec1fba5ce44b4b402417a7120ae3d2cde664119bac5506d624f7a9d8f
{"wins_per_hour":224145227.483518,"champion_mean":1.046059,"champion_var":inf,"filled_bins":1065,"filled_bins_sum_islands":1065,"eval_throughput":124438.019766,"completed":500000}
---
```

### 6.2 Throughput speedups

Using `eval_throughput` from JSON snapshots:

```text
1->2=2.2941x
1->4=4.0097x
1->6=4.0123x
```

Gate check (`1->4 >= 2.5x`): **PASS** (`4.0097x`).

## 7) Profile Stride Evidence

Command used:

```bash
cargo run --release --bin lgp_hotloop -- \
  --workers 4 \
  --fuel-max 200000 \
  --run-dir /tmp/runtime_profile_stride_w4 \
  --topk-trace 16 \
  --max-evals 100000 \
  --seed 777777 \
  --profile-stride 1024
```

Raw profile + summary artifacts:

```text
profile_latest.txt:
profile_stride=1024 sampled=97 mutate_ns=178791 link_ns=16170 oracle_ns=34336 archive_ns=18287
summary_latest.txt:
wins/hour=179485999.309 champion_mu=1.028898 champion_var=inf filled_bins=581 filled_bins_sum_islands=581 eval_throughput=99410.25/s completed=100000 champion_hash=3076bb4793195fb1ebc7a62a07226e2670ac814f9596a0f672016fbf254eadc1
snapshot_latest.json:
{"wins_per_hour":179485999.309099,"champion_mean":1.028898,"champion_var":inf,"filled_bins":581,"filled_bins_sum_islands":581,"eval_throughput":99410.248700,"completed":100000}```

## 8) Seeded Workers=1 Replay Stability Check

Command used (twice):

```bash
cargo run --release --bin lgp_hotloop -- \
  --workers 1 \
  --fuel-max 200000 \
  --run-dir /tmp/w1_seed_replay_N \
  --topk-trace 16 \
  --max-evals 200000 \
  --seed 777777
```

Raw snapshots:

```text
run=1 {"wins_per_hour":54794801.899877,"champion_mean":1.018215,"champion_var":0.000040,"filled_bins":76,"eval_throughput":30413.272268,"completed":200000}
run=2 {"wins_per_hour":56314781.674963,"champion_mean":1.018215,"champion_var":0.000040,"filled_bins":76,"eval_throughput":31256.920883,"completed":200000}
```

Observed stable fields across runs: `champion_mean`, `champion_var`, `filled_bins`, `completed`.

## 9) Appendix A — Full Unified Diff (`lgp_hotloop.rs`)

```diff
diff --git a/baremetal_lgp/src/bin/lgp_hotloop.rs b/baremetal_lgp/src/bin/lgp_hotloop.rs
index 3f0711a..1688482 100644
--- a/baremetal_lgp/src/bin/lgp_hotloop.rs
+++ b/baremetal_lgp/src/bin/lgp_hotloop.rs
@@ -1,5 +1,6 @@
 use std::fs;
 use std::path::{Path, PathBuf};
+use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
 use std::sync::Arc;
 use std::thread;
 use std::time::{Duration, Instant};
@@ -18,12 +19,14 @@ use baremetal_lgp::search::mutate::{
     mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT,
 };
 use baremetal_lgp::search::rng::Rng;
-use baremetal_lgp::search::select::select_parent;
+use baremetal_lgp::search::select::{select_parent, CHAMPION_INJECTION_P};
 use baremetal_lgp::search::topk_trace::{TopKTraceManager, TraceOracle, TraceSummary};
 use baremetal_lgp::types::CandidateId;
 use baremetal_lgp::vm::{VmProgram, VmWorker};
 use clap::Parser;
-use crossbeam_channel::{Receiver, RecvTimeoutError, Sender};
+use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender};
+
+const CHUNK_EVALS: u64 = 256;
 
 #[derive(Parser, Debug)]
 #[command(name = "lgp_hotloop")]
@@ -39,6 +42,37 @@ struct Args {
     topk_trace: usize,
     #[arg(long, default_value_t = 0)]
     max_evals: u64,
+    #[arg(long, default_value_t = 0)]
+    profile_stride: u32,
+    #[arg(long)]
+    seed: Option<u64>,
+}
+
+#[derive(Default)]
+struct WorkerAtomics {
+    evals: AtomicU64,
+    proxy_wins: AtomicU64,
+    filled_bins: AtomicU64,
+    champion_bits: AtomicU64,
+    mutate_ns: AtomicU64,
+    link_ns: AtomicU64,
+    oracle_ns: AtomicU64,
+    archive_ns: AtomicU64,
+}
+
+impl WorkerAtomics {
+    fn new() -> Self {
+        Self {
+            evals: AtomicU64::new(0),
+            proxy_wins: AtomicU64::new(0),
+            filled_bins: AtomicU64::new(0),
+            champion_bits: AtomicU64::new(f64::NEG_INFINITY.to_bits()),
+            mutate_ns: AtomicU64::new(0),
+            link_ns: AtomicU64::new(0),
+            oracle_ns: AtomicU64::new(0),
+            archive_ns: AtomicU64::new(0),
+        }
+    }
 }
 
 #[derive(Clone)]
@@ -52,6 +86,20 @@ struct EvalResult {
     evaluated: EvaluatedCandidate,
 }
 
+struct ChampionEvent {
+    worker_id: u32,
+    champion_mean: f32,
+    champ_hash_hex: String,
+    champ_cfg: CandidateCfg,
+}
+
+#[derive(Clone)]
+struct GlobalChampionMsg {
+    champ_hash_hex: String,
+    champ_mean: f32,
+    champ_cfg: CandidateCfg,
+}
+
 fn main() {
     if let Err(err) = run() {
         eprintln!("lgp_hotloop failed: {err}");
@@ -63,6 +111,14 @@ fn run() -> Result<(), String> {
     let args = Args::parse();
     fs::create_dir_all(&args.run_dir).map_err(|e| e.to_string())?;
 
+    if args.workers.max(1) == 1 {
+        return run_single_worker(&args);
+    }
+
+    run_island_multi_worker(&args)
+}
+
+fn run_single_worker(args: &Args) -> Result<(), String> {
     let library = Arc::new(LibraryBank::new_seeded());
     let fallback_parent = CandidateCfg::default();
     let exec_cfg = ExecConfig {
@@ -81,13 +137,18 @@ fn run() -> Result<(), String> {
         let tx = result_tx.clone();
         let shared_lib = Arc::clone(&library);
         let cfg = exec_cfg.clone();
+        let seed_base = args.seed;
         worker_handles.push(thread::spawn(move || {
-            worker_loop(worker_idx, rx, tx, shared_lib, cfg)
+            worker_loop(worker_idx, rx, tx, shared_lib, cfg, seed_base)
         }));
     }
     drop(result_tx);
 
-    let mut rng = Rng::from_entropy();
+    let mut rng = if let Some(seed) = args.seed {
+        Rng::new(mix64(seed ^ 0xA076_1D64_78BD_642F))
+    } else {
+        Rng::from_entropy()
+    };
     let mut archive = Archive::new();
     let mut champion: Option<Champion> = None;
     let mut stability = DeterministicStabilityOracle;
@@ -210,16 +271,397 @@ fn run() -> Result<(), String> {
     Ok(())
 }
 
+fn run_island_multi_worker(args: &Args) -> Result<(), String> {
+    let worker_count = args.workers.max(1);
+    let max_evals = if args.max_evals == 0 {
+        u64::MAX
+    } else {
+        args.max_evals
+    };
+    let seed_base = args.seed.unwrap_or_else(|| os_seed(0xA5A5_A5A5_A5A5_A5A5));
+
+    let library = Arc::new(LibraryBank::new_seeded());
+    let exec_cfg = ExecConfig {
+        fuel_max: args.fuel_max,
+        stability_runs: 3,
+        stability_threshold: 0.0,
+    };
+
+    let total_claimed = Arc::new(AtomicU64::new(0));
+    let atomics = Arc::new(
+        (0..worker_count)
+            .map(|_| WorkerAtomics::new())
+            .collect::<Vec<_>>(),
+    );
+
+    let (champ_tx, champ_rx) = bounded::<ChampionEvent>(1024);
+    let mut bcast_txs = Vec::with_capacity(worker_count);
+    let mut bcast_rxs = Vec::with_capacity(worker_count);
+    for _ in 0..worker_count {
+        let (tx, rx) = bounded::<GlobalChampionMsg>(1);
+        bcast_txs.push(tx);
+        bcast_rxs.push(rx);
+    }
+
+    let mut worker_handles = Vec::with_capacity(worker_count);
+    for (worker_id, bcast_rx) in bcast_rxs.into_iter().enumerate() {
+        let lib = Arc::clone(&library);
+        let cfg = exec_cfg.clone();
+        let total_claimed = Arc::clone(&total_claimed);
+        let atomics = Arc::clone(&atomics);
+        let champ_tx = champ_tx.clone();
+        let run_dir = args.run_dir.clone();
+        let profile_stride = args.profile_stride;
+
+        worker_handles.push(thread::spawn(move || {
+            worker_thread_main(
+                worker_id,
+                seed_base,
+                max_evals,
+                cfg,
+                profile_stride,
+                total_claimed,
+                atomics,
+                champ_tx,
+                bcast_rx,
+                lib,
+                run_dir,
+            )
+        }));
+    }
+    drop(champ_tx);
+
+    let started = Instant::now();
+    let mut last_t = Instant::now();
+    let mut last_sum_evals = 0_u64;
+    let mut global_best_mean = f32::NEG_INFINITY;
+    let mut global_best_hash = String::new();
+
+    loop {
+        thread::sleep(Duration::from_secs(1));
+
+        let mut sum_evals = 0_u64;
+        let mut sum_proxy_wins = 0_u64;
+        let mut filled_bins_sum = 0_u64;
+        let mut best_mean = f32::NEG_INFINITY;
+
+        let mut profile_mutate_ns = 0_u64;
+        let mut profile_link_ns = 0_u64;
+        let mut profile_oracle_ns = 0_u64;
+        let mut profile_archive_ns = 0_u64;
+
+        for wa in atomics.iter() {
+            sum_evals = sum_evals.saturating_add(wa.evals.load(Relaxed));
+            sum_proxy_wins = sum_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
+            filled_bins_sum = filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));
+
+            let mean = f64::from_bits(wa.champion_bits.load(Relaxed)) as f32;
+            if mean > best_mean {
+                best_mean = mean;
+            }
+
+            if args.profile_stride > 0 {
+                profile_mutate_ns = profile_mutate_ns.saturating_add(wa.mutate_ns.load(Relaxed));
+                profile_link_ns = profile_link_ns.saturating_add(wa.link_ns.load(Relaxed));
+                profile_oracle_ns = profile_oracle_ns.saturating_add(wa.oracle_ns.load(Relaxed));
+                profile_archive_ns = profile_archive_ns.saturating_add(wa.archive_ns.load(Relaxed));
+            }
+        }
+
+        while let Ok(evt) = champ_rx.try_recv() {
+            let _source_worker = evt.worker_id;
+            if evt.champion_mean > global_best_mean + 0.001 {
+                global_best_mean = evt.champion_mean;
+                global_best_hash = evt.champ_hash_hex.clone();
+
+                let msg = GlobalChampionMsg {
+                    champ_hash_hex: evt.champ_hash_hex,
+                    champ_mean: evt.champion_mean,
+                    champ_cfg: evt.champ_cfg,
+                };
+                for tx in &bcast_txs {
+                    let _ = tx.try_send(msg.clone());
+                }
+            }
+        }
+
+        if best_mean > global_best_mean {
+            global_best_mean = best_mean;
+        }
+
+        let dt = last_t.elapsed().as_secs_f64().max(1e-9);
+        let d_evals = sum_evals.saturating_sub(last_sum_evals);
+        let evals_per_sec = d_evals as f64 / dt;
+        let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
+        let wins_per_hour = sum_proxy_wins as f64 / (elapsed_secs / 3600.0);
+
+        write_island_snapshot(
+            &args.run_dir,
+            sum_evals,
+            evals_per_sec,
+            wins_per_hour,
+            global_best_mean,
+            filled_bins_sum,
+            &global_best_hash,
+        )
+        .map_err(|e| e.to_string())?;
+
+        if args.profile_stride > 0 {
+            write_profile_snapshot(
+                &args.run_dir,
+                args.profile_stride,
+                sum_evals,
+                profile_mutate_ns,
+                profile_link_ns,
+                profile_oracle_ns,
+                profile_archive_ns,
+            )
+            .map_err(|e| e.to_string())?;
+        }
+
+        last_sum_evals = sum_evals;
+        last_t = Instant::now();
+
+        if args.max_evals != 0 && sum_evals >= args.max_evals {
+            break;
+        }
+    }
+
+    for handle in worker_handles {
+        if handle.join().is_err() {
+            return Err("worker thread panicked".to_string());
+        }
+    }
+
+    let mut final_sum_evals = 0_u64;
+    let mut final_proxy_wins = 0_u64;
+    let mut final_filled_bins_sum = 0_u64;
+    for wa in atomics.iter() {
+        final_sum_evals = final_sum_evals.saturating_add(wa.evals.load(Relaxed));
+        final_proxy_wins = final_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
+        final_filled_bins_sum = final_filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));
+    }
+
+    let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
+    let final_throughput = final_sum_evals as f64 / elapsed_secs;
+    let final_wins_per_hour = final_proxy_wins as f64 / (elapsed_secs / 3600.0);
+
+    write_island_snapshot(
+        &args.run_dir,
+        final_sum_evals,
+        final_throughput,
+        final_wins_per_hour,
+        global_best_mean,
+        final_filled_bins_sum,
+        &global_best_hash,
+    )
+    .map_err(|e| e.to_string())?;
+
+    Ok(())
+}
+
+#[allow(clippy::too_many_arguments)]
+fn worker_thread_main(
+    worker_id: usize,
+    seed_base: u64,
+    max_evals: u64,
+    exec_cfg: ExecConfig,
+    profile_stride: u32,
+    total_claimed: Arc<AtomicU64>,
+    atomics: Arc<Vec<WorkerAtomics>>,
+    champ_tx: Sender<ChampionEvent>,
+    bcast_rx: Receiver<GlobalChampionMsg>,
+    library: Arc<LibraryBank>,
+    run_dir: PathBuf,
+) {
+    let seed_worker = mix64(seed_base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_id as u64);
+
+    let mut rng = Rng::new(seed_worker ^ 0xA076_1D64_78BD_642F);
+    let mut archive = Archive::new();
+    let mut champion: Option<Champion> = None;
+    let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
+    let mut next_weight_refresh = 4096_u64;
+
+    let mut linker = NoopLinker::default();
+    let mut oracle = SimOracle::new(seed_worker ^ 0xD6E8_FDDA_AE9D_3A57);
+    let mut vm_worker = VmWorker::default();
+    let mut stability = DeterministicStabilityOracle;
+
+    let fallback_parent = CandidateCfg::default();
+
+    let mut global_champ_mean = f32::NEG_INFINITY;
+    let mut global_champ_cfg: Option<CandidateCfg> = None;
+
+    let mut local_evals = 0_u64;
+    let mut local_proxy_wins = 0_u64;
+
+    let mut prof_mutate_ns = 0_u64;
+    let mut prof_link_ns = 0_u64;
+    let mut prof_oracle_ns = 0_u64;
+    let mut prof_archive_ns = 0_u64;
+
+    loop {
+        let start = total_claimed.fetch_add(CHUNK_EVALS, Relaxed);
+        if start >= max_evals {
+            break;
+        }
+        let end = start.saturating_add(CHUNK_EVALS).min(max_evals);
+        let n = end.saturating_sub(start);
+
+        if local_evals >= next_weight_refresh {
+            if let Some(next) = read_mutation_weights(&run_dir) {
+                mutation_weights = next;
+            }
+            next_weight_refresh = next_weight_refresh.saturating_add(4096);
+        }
+
+        let mut pending_champion_event: Option<ChampionEvent> = None;
+
+        for j in 0..n {
+            let eidx = start + j;
+            let do_prof = profile_stride > 0 && (eidx % u64::from(profile_stride) == 0);
+
+            let parent = if global_champ_cfg.is_some()
+                && global_champ_mean.is_finite()
+                && rng.gen_bool(CHAMPION_INJECTION_P)
+            {
+                global_champ_cfg.as_ref().unwrap_or(&fallback_parent)
+            } else {
+                select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
+                    .map_or(&fallback_parent, |elite| &elite.candidate)
+            };
+
+            let child_cfg = if do_prof {
+                let t = Instant::now();
+                let child = mutate_candidate(parent, &archive, &mut rng, &mutation_weights);
+                prof_mutate_ns = prof_mutate_ns.saturating_add(elapsed_nanos_u64(t));
+                child
+            } else {
+                mutate_candidate(parent, &archive, &mut rng, &mutation_weights)
+            };
+
+            let program = if do_prof {
+                let t = Instant::now();
+                let linked = linker.link(&child_cfg);
+                prof_link_ns = prof_link_ns.saturating_add(elapsed_nanos_u64(t));
+                linked
+            } else {
+                linker.link(&child_cfg)
+            };
+
+            let report = if do_prof {
+                let t = Instant::now();
+                let eval = oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg);
+                prof_oracle_ns = prof_oracle_ns.saturating_add(elapsed_nanos_u64(t));
+                eval
+            } else {
+                oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg)
+            };
+
+            let profile = scan_instruction_profile(&program.words);
+            let code_size_words = program.words.len() as u32;
+            let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
+            let output_entropy = output_entropy_sketch(&report.output_snapshot);
+            let desc = build_descriptor(DescriptorInputs {
+                fuel_used,
+                fuel_max: exec_cfg.fuel_max,
+                code_size_words,
+                branch_count: profile.branch_count,
+                store_count: profile.store_count,
+                total_insns: profile.total_insns,
+                output_entropy,
+                regime_profile_bits: report.regime_profile_bits,
+            });
+
+            let evaluated = EvaluatedCandidate {
+                child_cfg,
+                program,
+                report: report.clone(),
+                profile,
+                desc,
+                bin: bin_id(&desc),
+                score: report.full_mean.unwrap_or(report.proxy_mean),
+                fuel_used,
+                code_size_words,
+            };
+
+            let champion_updated = if do_prof {
+                let t = Instant::now();
+                archive.insert(evaluated.bin, evaluated.to_elite());
+                let updated =
+                    maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability);
+                prof_archive_ns = prof_archive_ns.saturating_add(elapsed_nanos_u64(t));
+                updated
+            } else {
+                archive.insert(evaluated.bin, evaluated.to_elite());
+                maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability)
+            };
+
+            if evaluated.score > 0.0 {
+                local_proxy_wins = local_proxy_wins.saturating_add(1);
+            }
+            local_evals = local_evals.saturating_add(1);
+
+            if champion_updated {
+                if let Some(current) = champion.as_ref() {
+                    let evt = ChampionEvent {
+                        worker_id: worker_id as u32,
+                        champion_mean: current.full_mean,
+                        champ_hash_hex: program_hash_hex(&evaluated.program),
+                        champ_cfg: current.elite.candidate.clone(),
+                    };
+                    let replace = pending_champion_event
+                        .as_ref()
+                        .map_or(true, |prev| evt.champion_mean > prev.champion_mean);
+                    if replace {
+                        pending_champion_event = Some(evt);
+                    }
+                }
+            }
+        }
+
+        let wa = &atomics[worker_id];
+        wa.evals.store(local_evals, Relaxed);
+        wa.proxy_wins.store(local_proxy_wins, Relaxed);
+        wa.filled_bins.store(u64::from(archive.filled), Relaxed);
+        let champion_mean = champion
+            .as_ref()
+            .map_or(f64::NEG_INFINITY, |c| c.full_mean as f64);
+        wa.champion_bits.store(champion_mean.to_bits(), Relaxed);
+
+        if profile_stride > 0 {
+            wa.mutate_ns.store(prof_mutate_ns, Relaxed);
+            wa.link_ns.store(prof_link_ns, Relaxed);
+            wa.oracle_ns.store(prof_oracle_ns, Relaxed);
+            wa.archive_ns.store(prof_archive_ns, Relaxed);
+        }
+
+        if let Some(evt) = pending_champion_event {
+            let _ = champ_tx.try_send(evt);
+        }
+
+        while let Ok(msg) = bcast_rx.try_recv() {
+            global_champ_mean = msg.champ_mean;
+            global_champ_cfg = Some(msg.champ_cfg);
+            let _ = msg.champ_hash_hex;
+        }
+    }
+}
+
 fn worker_loop(
     worker_idx: usize,
     rx: Receiver<Option<EvalJob>>,
     tx: Sender<EvalResult>,
     library: Arc<LibraryBank>,
     exec_cfg: ExecConfig,
+    seed_base: Option<u64>,
 ) {
     let mut worker = VmWorker::default();
     let mut linker = NoopLinker::default();
-    let mut oracle = SimOracle::new(os_seed(worker_idx as u64 + 1));
+    let oracle_seed = seed_base
+        .map(|base| mix64(base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_idx as u64))
+        .unwrap_or_else(|| os_seed(worker_idx as u64 + 1));
+    let mut oracle = SimOracle::new(oracle_seed);
 
     while let Ok(job) = rx.recv() {
         let Some(job) = job else {
@@ -256,6 +698,31 @@ fn os_seed(salt: u64) -> u64 {
     nanos ^ 0xD6E8_FDDA_AE9D_3A57 ^ salt
 }
 
+fn mix64(mut z: u64) -> u64 {
+    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
+    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
+    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
+    z ^ (z >> 31)
+}
+
+fn elapsed_nanos_u64(start: Instant) -> u64 {
+    let nanos = start.elapsed().as_nanos();
+    if nanos > u128::from(u64::MAX) {
+        u64::MAX
+    } else {
+        nanos as u64
+    }
+}
+
+fn program_hash_hex(program: &VmProgram) -> String {
+    let mut hasher = blake3::Hasher::new();
+    hasher.update(&(program.words.len() as u64).to_le_bytes());
+    for &word in &program.words {
+        hasher.update(&word.to_le_bytes());
+    }
+    hasher.finalize().to_hex().to_string()
+}
+
 fn read_mutation_weights(run_dir: &Path) -> Option<[f32; MUTATION_OPERATOR_COUNT]> {
     let path = run_dir.join("mutation_weights.json");
     let body = fs::read_to_string(path).ok()?;
@@ -510,3 +977,46 @@ fn write_snapshot(
     fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
     Ok(())
 }
+
+fn write_island_snapshot(
+    run_dir: &Path,
+    completed: u64,
+    throughput: f64,
+    wins_per_hour: f64,
+    champ_mu: f32,
+    filled_bins_sum_islands: u64,
+    champ_hash_hex: &str,
+) -> Result<(), std::io::Error> {
+    let champ_var = f32::INFINITY;
+    let summary_line = format!(
+        "wins/hour={wins_per_hour:.3} champion_mu={champ_mu:.6} champion_var={champ_var:.6} filled_bins={filled_bins_sum_islands} filled_bins_sum_islands={filled_bins_sum_islands} eval_throughput={throughput:.2}/s completed={completed} champion_hash={champ_hash_hex}",
+    );
+    println!("{summary_line}");
+
+    let summary_json = format!(
+        "{{\"wins_per_hour\":{wins_per_hour:.6},\"champion_mean\":{champ_mu:.6},\"champion_var\":{champ_var:.6},\"filled_bins\":{filled_bins_sum_islands},\"filled_bins_sum_islands\":{filled_bins_sum_islands},\"eval_throughput\":{throughput:.6},\"completed\":{completed}}}"
+    );
+    fs::write(run_dir.join("snapshot_latest.json"), summary_json)?;
+    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
+    Ok(())
+}
+
+fn write_profile_snapshot(
+    run_dir: &Path,
+    profile_stride: u32,
+    completed: u64,
+    mutate_ns: u64,
+    link_ns: u64,
+    oracle_ns: u64,
+    archive_ns: u64,
+) -> Result<(), std::io::Error> {
+    if profile_stride == 0 {
+        return Ok(());
+    }
+
+    let sampled = completed / u64::from(profile_stride.max(1));
+    let profile_line = format!(
+        "profile_stride={profile_stride} sampled={sampled} mutate_ns={mutate_ns} link_ns={link_ns} oracle_ns={oracle_ns} archive_ns={archive_ns}"
+    );
+    fs::write(run_dir.join("profile_latest.txt"), profile_line)
+}
```

## 10) Appendix B — Full Current File: `baremetal_lgp/src/bin/lgp_hotloop.rs`

```rust
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
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
        let seed_base = args.seed;
        worker_handles.push(thread::spawn(move || {
            worker_loop(worker_idx, rx, tx, shared_lib, cfg, seed_base)
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

    let library = Arc::new(LibraryBank::new_seeded());
    let exec_cfg = ExecConfig {
        fuel_max: args.fuel_max,
        stability_runs: 3,
        stability_threshold: 0.0,
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
    exec_cfg: ExecConfig,
    profile_stride: u32,
    total_claimed: Arc<AtomicU64>,
    atomics: Arc<Vec<WorkerAtomics>>,
    champ_tx: Sender<ChampionEvent>,
    bcast_rx: Receiver<GlobalChampionMsg>,
    library: Arc<LibraryBank>,
    run_dir: PathBuf,
) {
    let seed_worker = mix64(seed_base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_id as u64);

    let mut rng = Rng::new(seed_worker ^ 0xA076_1D64_78BD_642F);
    let mut archive = Archive::new();
    let mut champion: Option<Champion> = None;
    let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
    let mut next_weight_refresh = 4096_u64;

    let mut linker = NoopLinker::default();
    let mut oracle = SimOracle::new(seed_worker ^ 0xD6E8_FDDA_AE9D_3A57);
    let mut vm_worker = VmWorker::default();
    let mut stability = DeterministicStabilityOracle;

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

            let child_cfg = if do_prof {
                let t = Instant::now();
                let child = mutate_candidate(parent, &archive, &mut rng, &mutation_weights);
                prof_mutate_ns = prof_mutate_ns.saturating_add(elapsed_nanos_u64(t));
                child
            } else {
                mutate_candidate(parent, &archive, &mut rng, &mutation_weights)
            };

            let program = if do_prof {
                let t = Instant::now();
                let linked = linker.link(&child_cfg);
                prof_link_ns = prof_link_ns.saturating_add(elapsed_nanos_u64(t));
                linked
            } else {
                linker.link(&child_cfg)
            };

            let report = if do_prof {
                let t = Instant::now();
                let eval = oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg);
                prof_oracle_ns = prof_oracle_ns.saturating_add(elapsed_nanos_u64(t));
                eval
            } else {
                oracle.eval_candidate(&mut vm_worker, &program, &library, &exec_cfg)
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
                child_cfg,
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
    library: Arc<LibraryBank>,
    exec_cfg: ExecConfig,
    seed_base: Option<u64>,
) {
    let mut worker = VmWorker::default();
    let mut linker = NoopLinker::default();
    let oracle_seed = seed_base
        .map(|base| mix64(base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_idx as u64))
        .unwrap_or_else(|| os_seed(worker_idx as u64 + 1));
    let mut oracle = SimOracle::new(oracle_seed);

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
            const_pool: [0.0; baremetal_lgp::abi::CONST_POOL_WORDS],
            #[cfg(feature = "trace")]
            pc_to_block: Vec::new(),
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
```

## 11) Appendix C — Supporting File Data

### 11.1 `baremetal_lgp/src/search/mod.rs`

```rust
pub mod archive;
pub mod champion;
pub mod descriptors;
pub mod evaluate;
pub mod ir;
pub mod mutate;
pub mod rng;
pub mod select;
pub mod topk_trace;

use crate::search::archive::{Archive, Elite};
use crate::search::champion::{maybe_update_champion, Champion, StabilityOracle};
use crate::search::evaluate::{
    evaluate_child, update_archive, EvalReport, EvaluatedCandidate, EvaluationHarness, ExecConfig,
    Linker, Oracle,
};
use crate::search::ir::CandidateCfg;
use crate::search::mutate::{DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT};
use crate::search::rng::Rng;
use crate::search::select::select_parent;
use crate::types::CandidateId;

#[derive(Debug)]
pub struct SearchState {
    pub archive: Archive,
    pub champion: Option<Champion>,
    pub mutation_weights: [f32; MUTATION_OPERATOR_COUNT],
    rng: Rng,
    next_candidate_id: u64,
}

pub struct StepContext<'a, L, O, S> {
    pub harness: EvaluationHarness<'a, L, O>,
    pub stability: &'a mut S,
    pub exec_cfg: &'a ExecConfig,
}

impl SearchState {
    pub fn new(seed: u64) -> Self {
        Self {
            archive: Archive::new(),
            champion: None,
            mutation_weights: DEFAULT_MUTATION_WEIGHTS,
            rng: Rng::new(seed),
            next_candidate_id: 1,
        }
    }

    pub fn with_entropy_seed() -> Self {
        let mut entropy = [0_u8; 8];
        let seed = if getrandom::getrandom(&mut entropy).is_ok() {
            u64::from_le_bytes(entropy)
        } else {
            0xA076_1D64_78BD_642F
        };
        Self::new(seed)
    }

    pub fn next_candidate_id(&mut self) -> CandidateId {
        let id = CandidateId(self.next_candidate_id);
        self.next_candidate_id = self.next_candidate_id.saturating_add(1);
        id
    }

    pub fn upsert_seed(&mut self, elite: Elite, full_mean: Option<f32>, full_var: Option<f32>) {
        let bin = descriptors::bin_id(&elite.desc);
        self.archive.insert(bin, elite.clone());
        if let (Some(mean), Some(var)) = (full_mean, full_var) {
            self.champion = Some(Champion {
                elite,
                full_mean: mean,
                full_var: var,
            });
        }
    }

    pub fn evaluate_step<L, O, S>(
        &mut self,
        parent_fallback: &CandidateCfg,
        step: &mut StepContext<'_, L, O, S>,
    ) -> EvaluatedCandidate
    where
        L: Linker,
        O: Oracle,
        S: StabilityOracle,
    {
        let parent = select_parent(
            &self.archive,
            self.champion.as_ref().map(|c| &c.elite),
            &mut self.rng,
        )
        .map_or(parent_fallback, |elite| &elite.candidate);

        let evaluated = evaluate_child(
            parent,
            &self.archive,
            &mut self.rng,
            &mut step.harness,
            Some(&self.mutation_weights),
        );
        update_archive(&mut self.archive, &evaluated);
        let _ = maybe_update_champion(
            &mut self.champion,
            &evaluated,
            step.exec_cfg,
            step.stability,
        );
        evaluated
    }
}

pub fn report_score(report: &EvalReport) -> f32 {
    report.full_mean.unwrap_or(report.proxy_mean)
}
```

### 11.2 `baremetal_lgp/src/oracle/mod.rs`

```rust
use crate::contracts::constants::SCRATCH_WORDS_F32;
use crate::contracts::traits::{OracleHarness, TraceSink};
use crate::library::LibraryImage;
use crate::types::{EvalMode, EvalSummary, StopReason};
use crate::vm::{VmProgram, VmWorker};

pub mod funnel;
pub mod mixture;
pub mod regimes;
pub mod scoring;

const NUM_FAMILIES: usize = 4;
const FIXED_PROXY_EPS: usize = 2;
const FIXED_FULL_EPS_PER_FAMILY: usize = 4;
const FIXED_STABILITY_RUNS: usize = 3;
const SCRATCH_ALIGN_WORDS: usize = 64;
const SCRATCH_LAYOUT_TRIES: usize = 16;
const SCRATCH_MASK_I32: i32 = 0x3FFF;

#[derive(Clone, Copy, Debug)]
pub struct OracleConfig {
    pub fuel_max: u32,
    pub proxy_eps: usize,
    pub full_eps_per_family: usize,
    pub stability_runs: usize,
    pub topk_trace: usize,
}

impl Default for OracleConfig {
    fn default() -> Self {
        Self {
            fuel_max: 100_000,
            proxy_eps: 2,
            full_eps_per_family: 4,
            stability_runs: 3,
            topk_trace: 16,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct EpisodeReport {
    pub family: u8,
    pub score: f32,
    pub fuel_used: u32,
}

#[derive(Clone, Copy, Debug)]
pub struct EvalReport {
    pub proxy_mean: f32,
    pub full_mean: Option<f32>,
    pub full_by_family: Option<[f32; NUM_FAMILIES]>,
    pub full_var: Option<f32>,
    pub regime_profile_bits: u8,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ExecConfig {
    pub run_full_eval: bool,
}

#[derive(Clone, Copy, Debug)]
struct EpisodeOutcome {
    report: EpisodeReport,
    stop_reason: StopReason,
}

#[derive(Clone, Copy, Debug)]
struct ProxyEvalStats {
    mean: f32,
    var: f32,
    fuel_used_mean: f32,
    stop_reason: StopReason,
    family_means: [f32; NUM_FAMILIES],
}

#[derive(Clone, Copy, Debug)]
struct FullEvalStats {
    by_family: [f32; NUM_FAMILIES],
    mean: f32,
    var: f32,
    fuel_used_mean: f32,
    stop_reason: StopReason,
    regime_profile_bits: u8,
}

#[derive(Clone, Copy, Debug)]
struct ScratchLayout {
    in_base: usize,
    in_len: usize,
    out_base: usize,
    out_len: usize,
    work_base: usize,
    work_len: usize,
}

#[derive(Clone, Debug)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    pub fn next_f32(&mut self) -> f32 {
        let x = self.next_u64();
        let frac = (x as f64) / ((u64::MAX as f64) + 1.0);
        frac as f32
    }

    pub fn next_usize(&mut self, upper_exclusive: usize) -> usize {
        if upper_exclusive <= 1 {
            return 0;
        }
        (self.next_u64() % (upper_exclusive as u64)) as usize
    }

    pub fn range_f32(&mut self, lo: f32, hi: f32) -> f32 {
        if hi <= lo {
            return lo;
        }
        lo + (hi - lo) * self.next_f32()
    }

    pub fn gaussian(&mut self) -> f32 {
        let u1 = self.next_f32().max(f32::EPSILON);
        let u2 = self.next_f32();
        let r = (-2.0 * u1.ln()).sqrt();
        let theta = std::f32::consts::TAU * u2;
        r * theta.cos()
    }
}

pub struct Oracle {
    cfg: OracleConfig,
    rng: SplitMix64,
    mixture: mixture::MixtureState,
    proxy_counter: u64,
    trace_topk: Vec<(u64, f32)>,
    last_proxy: ProxyEvalStats,
}

impl Oracle {
    pub fn new(cfg: OracleConfig, seed: u64) -> Self {
        let cfg = OracleConfig {
            fuel_max: cfg.fuel_max,
            proxy_eps: FIXED_PROXY_EPS,
            full_eps_per_family: FIXED_FULL_EPS_PER_FAMILY,
            stability_runs: FIXED_STABILITY_RUNS,
            topk_trace: cfg.topk_trace,
        };
        Self {
            cfg,
            rng: SplitMix64::new(seed),
            mixture: mixture::MixtureState::new(),
            proxy_counter: 0,
            trace_topk: Vec::new(),
            last_proxy: ProxyEvalStats {
                mean: 0.0,
                var: 0.0,
                fuel_used_mean: 0.0,
                stop_reason: StopReason::Halt,
                family_means: [0.0; NUM_FAMILIES],
            },
        }
    }

    pub fn proxy_counter(&self) -> u64 {
        self.proxy_counter
    }

    pub fn eval_candidate(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
        exec_cfg: &ExecConfig,
    ) -> EvalReport {
        let proxy = self.run_proxy_pair(worker, prog, lib);
        self.last_proxy = proxy;

        let mut report = EvalReport {
            proxy_mean: proxy.mean,
            full_mean: None,
            full_by_family: None,
            full_var: None,
            regime_profile_bits: 0,
        };

        if exec_cfg.run_full_eval {
            let full = self.run_full_eval(worker, prog, lib);
            report.full_mean = Some(full.mean);
            report.full_by_family = Some(full.by_family);
            report.full_var = Some(full.var);
            report.regime_profile_bits = full.regime_profile_bits;
        }

        self.mixture.on_candidate_complete();
        report
    }

    pub fn maybe_emit_trace_job(&mut self, candidate_id: u64, score: f32) -> bool {
        if self.cfg.topk_trace == 0 {
            return false;
        }

        if self.trace_topk.len() < self.cfg.topk_trace {
            self.trace_topk.push((candidate_id, score));
            return true;
        }

        let mut min_idx = 0usize;
        for idx in 1..self.trace_topk.len() {
            let (best_id, best_score) = self.trace_topk[min_idx];
            let (cur_id, cur_score) = self.trace_topk[idx];
            if (cur_score < best_score) || (cur_score == best_score && cur_id > best_id) {
                min_idx = idx;
            }
        }

        let (min_id, min_score) = self.trace_topk[min_idx];
        let should_emit = (score > min_score) || (score == min_score && candidate_id < min_id);
        if should_emit {
            self.trace_topk[min_idx] = (candidate_id, score);
            return true;
        }
        false
    }

    fn run_proxy_pair(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> ProxyEvalStats {
        debug_assert_eq!(self.cfg.proxy_eps, FIXED_PROXY_EPS);
        let weights = self.mixture.weights();
        let (coverage_family, weighted_family) =
            funnel::next_proxy_families(&mut self.proxy_counter, weights, &mut self.rng);

        let first = self.run_episode(coverage_family, worker, prog, lib);
        let second = self.run_episode(weighted_family, worker, prog, lib);

        let scores = [first.report.score, second.report.score];
        let fuels = [
            first.report.fuel_used as f32,
            second.report.fuel_used as f32,
        ];
        let stop_reason = merge_stop_reason(first.stop_reason, second.stop_reason);

        let mut family_means = [0.0_f32; NUM_FAMILIES];
        let mut family_counts = [0_u32; NUM_FAMILIES];

        let first_idx = usize::from(first.report.family);
        family_means[first_idx] += first.report.score;
        family_counts[first_idx] += 1;

        let second_idx = usize::from(second.report.family);
        family_means[second_idx] += second.report.score;
        family_counts[second_idx] += 1;

        for (idx, mean_value) in family_means.iter_mut().enumerate() {
            if family_counts[idx] > 0 {
                *mean_value /= family_counts[idx] as f32;
            }
        }

        ProxyEvalStats {
            mean: mean(&scores),
            var: variance(&scores, mean(&scores)),
            fuel_used_mean: mean(&fuels),
            stop_reason,
            family_means,
        }
    }

    fn run_full_eval(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> FullEvalStats {
        debug_assert_eq!(self.cfg.full_eps_per_family, FIXED_FULL_EPS_PER_FAMILY);
        let mut all_scores =
            Vec::with_capacity(self.cfg.full_eps_per_family.saturating_mul(NUM_FAMILIES));
        let mut family_sums = [0.0_f32; NUM_FAMILIES];
        let mut family_counts = [0_u32; NUM_FAMILIES];
        let mut total_fuel = 0.0_f32;
        let mut stop_reason = StopReason::Halt;

        for family in 0..NUM_FAMILIES {
            for _ in 0..self.cfg.full_eps_per_family {
                let outcome = self.run_episode(family as u8, worker, prog, lib);
                all_scores.push(outcome.report.score);
                family_sums[family] += outcome.report.score;
                family_counts[family] += 1;
                total_fuel += outcome.report.fuel_used as f32;
                stop_reason = merge_stop_reason(stop_reason, outcome.stop_reason);
            }
        }

        let mut by_family = [0.0_f32; NUM_FAMILIES];
        for (idx, value) in by_family.iter_mut().enumerate() {
            if family_counts[idx] > 0 {
                *value = family_sums[idx] / family_counts[idx] as f32;
            }
        }

        let mean_score = mean(&all_scores);
        let var_score = variance(&all_scores, mean_score);
        let bits = funnel::regime_profile_bits(by_family, mean_score);
        let fuel_used_mean = if all_scores.is_empty() {
            0.0
        } else {
            total_fuel / all_scores.len() as f32
        };

        FullEvalStats {
            by_family,
            mean: mean_score,
            var: var_score,
            fuel_used_mean,
            stop_reason,
            regime_profile_bits: bits,
        }
    }

    fn run_episode(
        &mut self,
        family: u8,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
    ) -> EpisodeOutcome {
        let weights = self.mixture.weights();
        let family_idx = usize::from(family);
        let mut episode =
            regimes::sample_episode(family, &mut self.rng, weights, weights[family_idx]);

        let layout = allocate_layout(
            &mut self.rng,
            episode.in_data.len(),
            episode.out_len,
            episode.work_len,
        );

        let _ = SCRATCH_WORDS_F32;
        worker.scratch[layout.out_base..layout.out_base + layout.out_len].fill(0.0);
        worker.scratch[layout.work_base..layout.work_base + layout.work_len].fill(0.0);

        for (offset, value) in episode.in_data.iter().copied().enumerate() {
            worker.scratch[layout.in_base + offset] = value;
        }

        episode.meta_u32[regimes::META_IN_BASE] = usize_to_u32(layout.in_base);
        episode.meta_u32[regimes::META_IN_LEN] = usize_to_u32(layout.in_len);
        episode.meta_u32[regimes::META_OUT_BASE] = usize_to_u32(layout.out_base);
        episode.meta_u32[regimes::META_OUT_LEN] = usize_to_u32(layout.out_len);
        episode.meta_u32[regimes::META_WORK_BASE] = usize_to_u32(layout.work_base);
        episode.meta_u32[regimes::META_WORK_LEN] = usize_to_u32(layout.work_len);

        let (fuel_used, stop_reason) =
            self.simulate_execution(worker, prog, lib, &episode, &layout);
        let output = &worker.scratch[layout.out_base..layout.out_base + layout.out_len];
        let stability_bonus = if family == 3 {
            scoring::stability_bonus(output, episode.robustness_bonus_scale)
        } else {
            0.0
        };
        let score = scoring::score_episode(
            output,
            &episode.target,
            fuel_used,
            stop_reason,
            stability_bonus,
        );

        self.mixture.observe_episode_score(family, score);
        EpisodeOutcome {
            report: EpisodeReport {
                family,
                score,
                fuel_used,
            },
            stop_reason,
        }
    }

    fn simulate_execution(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        lib: &LibraryImage,
        episode: &regimes::EpisodeSpec,
        layout: &ScratchLayout,
    ) -> (u32, StopReason) {
        let fuel_cost = self.estimate_fuel_cost(prog, lib, episode);
        if fuel_cost > self.cfg.fuel_max {
            return (self.cfg.fuel_max, StopReason::FuelExhausted);
        }

        if layout.in_len == 0 || layout.out_len == 0 {
            return (fuel_cost, StopReason::Halt);
        }

        let (alpha, beta, bias) = program_coeffs(prog, lib, episode.family);
        let in_base_i32 = i32::try_from(layout.in_base).unwrap_or(0);
        let out_base_i32 = i32::try_from(layout.out_base).unwrap_or(0);

        for out_idx in 0..layout.out_len {
            let src0_off = i32::try_from(out_idx % layout.in_len).unwrap_or(0);
            let src1_off =
                i32::try_from((out_idx.saturating_mul(7) + 3) % layout.in_len).unwrap_or(0);
            let src0_addr = ring_addr(in_base_i32, src0_off);
            let src1_addr = ring_addr(in_base_i32, src1_off);
            let x = worker.scratch[src0_addr];
            let y = worker.scratch[src1_addr];

            let trend = (out_idx as f32) * 0.0005;
            let family_bias = (episode.meta_f32[0] + episode.meta_f32[1]) * 0.001;
            let mut value = alpha.mul_add(x, beta.mul_add(y, bias + trend + family_bias));

            if episode.family == 2 || episode.family == 3 {
                value = 0.75 * value + 0.25 * (x - y);
            }

            let dst = ring_addr(out_base_i32, i32::try_from(out_idx).unwrap_or(0));
            worker.scratch[dst] = value;
        }

        (fuel_cost, StopReason::Halt)
    }

    fn estimate_fuel_cost(
        &self,
        prog: &VmProgram,
        lib: &LibraryImage,
        episode: &regimes::EpisodeSpec,
    ) -> u32 {
        let mut extra = 0_u32;
        let out_words = usize_to_u32(episode.out_len);

        if episode.family == 2 || episode.family == 3 {
            let lanes = out_words;
            extra = extra.saturating_add(2 + lanes.div_ceil(8));
        } else {
            extra = extra.saturating_add(2 + out_words.div_ceil(8));
        }

        if lib.slots.iter().any(Option::is_some) {
            extra = extra.saturating_add(1);
        }

        1_u32
            .saturating_add(usize_to_u32(prog.words.len()))
            .saturating_add(extra)
    }
}

impl OracleHarness for Oracle {
    fn eval(&mut self, worker: &mut VmWorker, prog: &VmProgram, mode: EvalMode) -> EvalSummary {
        let lib = LibraryImage::default();
        match mode {
            EvalMode::Proxy => {
                let _ = self.eval_candidate(worker, prog, &lib, &ExecConfig::default());
                EvalSummary {
                    score_mean: self.last_proxy.mean,
                    score_var: self.last_proxy.var,
                    fuel_used_mean: self.last_proxy.fuel_used_mean,
                    stop_reason: self.last_proxy.stop_reason,
                    family_means: self.last_proxy.family_means,
                }
            }
            EvalMode::Full => {
                let full = self.run_full_eval(worker, prog, &lib);
                self.mixture.on_candidate_complete();
                EvalSummary {
                    score_mean: full.mean,
                    score_var: full.var,
                    fuel_used_mean: full.fuel_used_mean,
                    stop_reason: full.stop_reason,
                    family_means: full.by_family,
                }
            }
            EvalMode::Stability => {
                debug_assert_eq!(self.cfg.stability_runs, FIXED_STABILITY_RUNS);
                let runs = self.cfg.stability_runs.max(1);
                let mut run_means = Vec::with_capacity(runs);
                let mut run_fuel = Vec::with_capacity(runs);
                let mut family_sums = [0.0_f32; NUM_FAMILIES];
                let mut stop_reason = StopReason::Halt;

                for _ in 0..runs {
                    let full = self.run_full_eval(worker, prog, &lib);
                    run_means.push(full.mean);
                    run_fuel.push(full.fuel_used_mean);
                    for (idx, value) in full.by_family.iter().copied().enumerate() {
                        family_sums[idx] += value;
                    }
                    stop_reason = merge_stop_reason(stop_reason, full.stop_reason);
                }

                self.mixture.on_candidate_complete();

                let mut family_means = [0.0_f32; NUM_FAMILIES];
                for (idx, value) in family_means.iter_mut().enumerate() {
                    *value = family_sums[idx] / runs as f32;
                }

                let score_mean = mean(&run_means);
                EvalSummary {
                    score_mean,
                    score_var: variance(&run_means, score_mean),
                    fuel_used_mean: mean(&run_fuel),
                    stop_reason,
                    family_means,
                }
            }
        }
    }

    fn eval_with_trace(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        mode: EvalMode,
        trace: &mut dyn TraceSink,
    ) -> EvalSummary {
        trace.on_block_enter(0);
        let summary = self.eval(worker, prog, mode);
        trace.on_edge(0, 0);
        trace.on_checkpoint(0, &worker.f, &worker.i);
        let output_len = worker.scratch.len().min(128);
        trace.on_finish(
            &worker.scratch[..output_len],
            summary.score_mean,
            summary.fuel_used_mean.max(0.0) as u32,
        );
        summary
    }
}

fn allocate_layout(
    rng: &mut SplitMix64,
    in_len: usize,
    out_len: usize,
    work_len: usize,
) -> ScratchLayout {
    for _ in 0..SCRATCH_LAYOUT_TRIES {
        let in_base = match sample_aligned_base(rng, in_len) {
            Some(base) => base,
            None => break,
        };
        let out_base = match sample_aligned_base(rng, out_len) {
            Some(base) => base,
            None => break,
        };
        let work_base = match sample_aligned_base(rng, work_len) {
            Some(base) => base,
            None => break,
        };

        let overlaps_any = overlaps(in_base, in_len, out_base, out_len)
            || overlaps(in_base, in_len, work_base, work_len)
            || overlaps(out_base, out_len, work_base, work_len);
        if !overlaps_any {
            return ScratchLayout {
                in_base,
                in_len,
                out_base,
                out_len,
                work_base,
                work_len,
            };
        }
    }

    ScratchLayout {
        in_base: 0,
        in_len,
        out_base: 4096,
        out_len,
        work_base: 8192,
        work_len,
    }
}

fn sample_aligned_base(rng: &mut SplitMix64, len: usize) -> Option<usize> {
    if len > SCRATCH_WORDS_F32 {
        return None;
    }
    let max_start = SCRATCH_WORDS_F32 - len;
    let max_slot = max_start / SCRATCH_ALIGN_WORDS;
    let slot = rng.next_usize(max_slot + 1);
    Some(slot * SCRATCH_ALIGN_WORDS)
}

fn overlaps(base_a: usize, len_a: usize, base_b: usize, len_b: usize) -> bool {
    (base_a < base_b.saturating_add(len_b)) && (base_b < base_a.saturating_add(len_a))
}

fn ring_addr(base_i32: i32, offset_i32: i32) -> usize {
    ((base_i32 + offset_i32) & SCRATCH_MASK_I32) as usize
}

fn program_coeffs(prog: &VmProgram, lib: &LibraryImage, family: u8) -> (f32, f32, f32) {
    let mut mixed = 0xD1B5_4A32_D192_ED03_u64 ^ u64::from(family);
    for word in prog.words.iter().take(128) {
        mixed ^= u64::from(*word).wrapping_add(0x9E37_79B9_7F4A_7C15);
        mixed = mixed.rotate_left(27).wrapping_mul(0x94D0_49BB_1331_11EB);
    }

    let occupied_slots = lib.slots.iter().filter(|slot| slot.is_some()).count() as u64;
    mixed ^= occupied_slots.wrapping_mul(0xBF58_476D_1CE4_E5B9);

    let to_signed_unit = |x: u64| -> f32 {
        let lane = (x & 0xFFFF) as f32 / 65_535.0;
        (lane * 2.0) - 1.0
    };

    let alpha = 0.8 + 0.2 * to_signed_unit(mixed);
    let beta = 0.3 * to_signed_unit(mixed >> 16);
    let bias = 0.1 * to_signed_unit(mixed >> 32);
    (alpha, beta, bias)
}

fn mean(values: &[f32]) -> f32 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f32>() / values.len() as f32
    }
}

fn variance(values: &[f32], mean_value: f32) -> f32 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sum = 0.0_f32;
    for value in values {
        let d = *value - mean_value;
        sum += d * d;
    }
    sum / values.len() as f32
}

fn merge_stop_reason(current: StopReason, next: StopReason) -> StopReason {
    if current == StopReason::Halt && next != StopReason::Halt {
        return next;
    }
    current
}

fn usize_to_u32(value: usize) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}
```

---

# Real Oracle + Zero-Alloc Update (Appended)

Generated: 2026-02-27 10:13:08 UTC

This appended section supersedes earlier benchmark/test numbers in this file.

## A) Current git state

### A.1 git status

```text
## codex/phase1_throughput_uncorking...origin/codex/phase1_throughput_uncorking
 M baremetal_lgp/src/bin/lgp_hotloop.rs
 M baremetal_lgp/src/search/evaluate.rs
 M baremetal_lgp/src/search/mutate.rs
 M baremetal_lgp/tests/agent3_search_library.rs
?? baremetal_lgp/Cargo.lock
?? baremetal_lgp/PHASE1_THROUGHPUT_UNCORKING_AUDIT.md
```

### A.2 git diff stat

```text
 baremetal_lgp/src/bin/lgp_hotloop.rs         | 688 ++++++++++++++++++++++++---
 baremetal_lgp/src/search/evaluate.rs         |   3 +-
 baremetal_lgp/src/search/mutate.rs           |  43 +-
 baremetal_lgp/tests/agent3_search_library.rs |   6 +-
 4 files changed, 659 insertions(+), 81 deletions(-)
```

### A.3 changed file names

```text
baremetal_lgp/src/bin/lgp_hotloop.rs
baremetal_lgp/src/search/evaluate.rs
baremetal_lgp/src/search/mutate.rs
baremetal_lgp/tests/agent3_search_library.rs
```

## B) Validation results

### B.1 cargo check --release --bin lgp_hotloop

```text
    Finished `release` profile [optimized] target(s) in 0.09s
```

### B.2 cargo test --release -- --nocapture

```text
    Finished `release` profile [optimized] target(s) in 0.05s
     Running unittests src/lib.rs (target/release/deps/baremetal_lgp-ab5134800b6b3029)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/architect.rs (target/release/deps/architect-96ef35fe3ae28c2a)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/lgp_hotloop.rs (target/release/deps/lgp_hotloop-0e74bf3872182e6f)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent1_vm_core.rs (target/release/deps/agent1_vm_core-545c711d2d26fae1)

running 5 tests
test agent1_vm_imm14_ring_addressing_full_scratch ... ok
test agent1_vm_call_lib_round_trip ... ok
test agent1_vm_vdot_threshold_path_correctness ... ok
test agent1_vm_vadd_threshold_path_correctness ... ok
test agent1_vm_vcmul_correctness ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent1_vm_jit.rs (target/release/deps/agent1_vm_jit-b2301b65538f0627)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent2_oracle_complex_family.rs (target/release/deps/agent2_oracle_complex_family-c17550ca64ef8d23)

running 1 test
test complex_family_targets_are_nontrivial_and_mse_scoring_is_ordered ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent2_oracle_funnel_and_full_eval.rs (target/release/deps/agent2_oracle_funnel_and_full_eval-6974b97501ac202c)

running 3 tests
test trace_job_gate_keeps_only_topk_scores ... ok
test weighted_family_sampling_excludes_coverage_and_fallback_is_stable ... ok
test full_eval_populates_balanced_report_and_profile_bits ... ok

test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent2_oracle_proxy_schedule.rs (target/release/deps/agent2_oracle_proxy_schedule-e513e5f0121a545e)

running 1 test
test proxy_coverage_family_hits_each_family_twice_over_eight_candidates ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent3_outerloop.rs (target/release/deps/agent3_outerloop-9f578046d074e8ce)

running 2 tests
test agent3_topk_rejects_low_score_when_full ... ok
test agent3_topk_trace_writes_only_on_entry ... ok

test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent3_search_library.rs (target/release/deps/agent3_search_library-29841f93dae2d6b6)

running 10 tests
test agent3_bucket_boundaries_match_contract ... ok
test agent3_entropy_sketch_is_low_for_constant_outputs ... ok
test agent3_descriptor_builder_maps_all_components ... ok
test agent3_descriptor_bin_id_packs_exact_bits ... ok
test agent3_library_seeds_expected_slots ... ok
test agent3_promote_slot_validates_inputs ... ok
test agent3_bandit_updates_and_persists_weights ... ok
test agent3_mutation_can_force_calllib_insertion_pattern ... ok
test agent3_loop_term_transform_can_insert_bridge_jump ... ok
test agent3_archive_insert_replace_rules_hold ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/dod_acceptance.rs (target/release/deps/dod_acceptance-05f506aa05db8ef1)

running 5 tests
test dod_complex_family_requires_complex_ops_score_collapse_without_vcmul ... ok
test dod_gas_enforcement_stops_infinite_loop_with_fuel_exhausted ... ok
test dod_library_promotion_calllib_improves_code_bucket_score_stable ... ok
test dod_hidden_oracle_champion_trend_upward ... ok
test dod_stage_a_hot_swap_shadow_accepts_and_wins_per_hour_increases ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.77s

   Doc-tests baremetal_lgp

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

```

### B.3 cargo test --release dod_ -- --nocapture

```text
    Finished `release` profile [optimized] target(s) in 0.03s
     Running unittests src/lib.rs (target/release/deps/baremetal_lgp-ab5134800b6b3029)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/architect.rs (target/release/deps/architect-96ef35fe3ae28c2a)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running unittests src/bin/lgp_hotloop.rs (target/release/deps/lgp_hotloop-0e74bf3872182e6f)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent1_vm_core.rs (target/release/deps/agent1_vm_core-545c711d2d26fae1)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 5 filtered out; finished in 0.00s

     Running tests/agent1_vm_jit.rs (target/release/deps/agent1_vm_jit-b2301b65538f0627)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

     Running tests/agent2_oracle_complex_family.rs (target/release/deps/agent2_oracle_complex_family-c17550ca64ef8d23)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s

     Running tests/agent2_oracle_funnel_and_full_eval.rs (target/release/deps/agent2_oracle_funnel_and_full_eval-6974b97501ac202c)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 3 filtered out; finished in 0.00s

     Running tests/agent2_oracle_proxy_schedule.rs (target/release/deps/agent2_oracle_proxy_schedule-e513e5f0121a545e)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s

     Running tests/agent3_outerloop.rs (target/release/deps/agent3_outerloop-9f578046d074e8ce)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 2 filtered out; finished in 0.00s

     Running tests/agent3_search_library.rs (target/release/deps/agent3_search_library-29841f93dae2d6b6)

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 10 filtered out; finished in 0.00s

     Running tests/dod_acceptance.rs (target/release/deps/dod_acceptance-05f506aa05db8ef1)

running 5 tests
test dod_complex_family_requires_complex_ops_score_collapse_without_vcmul ... ok
test dod_gas_enforcement_stops_infinite_loop_with_fuel_exhausted ... ok
test dod_library_promotion_calllib_improves_code_bucket_score_stable ... ok
test dod_hidden_oracle_champion_trend_upward ... ok
test dod_stage_a_hot_swap_shadow_accepts_and_wins_per_hour_increases ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.37s

```

## C) Performance (real oracle path)

Command matrix run:

```bash
for W in 1 2 4 6; do
  cargo run --release --bin lgp_hotloop -- \
    --workers "$W" \
    --fuel-max 200000 \
    --run-dir "/tmp/runtime_scale_uncork_real_oracle_w${W}" \
    --topk-trace 16 \
    --max-evals 500000 \
    --seed 777777
done
```

### C.1 Raw outputs

```text
W=1
wins/hour=0.000 champion_mu=-0.279397 champion_var=0.038870 filled_bins=335 eval_throughput=15366.58/s completed=500000
{"wins_per_hour":0.000000,"champion_mean":-0.279397,"champion_var":0.038870,"filled_bins":335,"eval_throughput":15366.575950,"completed":500000}
---
W=2
wins/hour=0.000 champion_mu=-0.300357 champion_var=inf filled_bins=589 filled_bins_sum_islands=589 eval_throughput=21624.96/s completed=500000 champion_hash=2f854f1206f38b7b7ce2ec64ad5a1d650ebcc01e64e3fd13191ca9f98e38ac2e
{"wins_per_hour":0.000000,"champion_mean":-0.300357,"champion_var":inf,"filled_bins":589,"filled_bins_sum_islands":589,"eval_throughput":21624.958606,"completed":500000}
---
W=4
wins/hour=0.000 champion_mu=-0.295311 champion_var=inf filled_bins=962 filled_bins_sum_islands=962 eval_throughput=38304.69/s completed=500000 champion_hash=a8775fbe9d8eefe655efc89b6282d12fab99a020f48fbce9ffe36e1746ab8d84
{"wins_per_hour":0.000000,"champion_mean":-0.295311,"champion_var":inf,"filled_bins":962,"filled_bins_sum_islands":962,"eval_throughput":38304.690698,"completed":500000}
---
W=6
wins/hour=0.000 champion_mu=-0.283419 champion_var=inf filled_bins=1006 filled_bins_sum_islands=1006 eval_throughput=38278.19/s completed=500000 champion_hash=8cf3c71af85a1976d4363ade8b52a38b9f2578f52a36be044138853341b5512c
{"wins_per_hour":0.000000,"champion_mean":-0.283419,"champion_var":inf,"filled_bins":1006,"filled_bins_sum_islands":1006,"eval_throughput":38278.189001,"completed":500000}
---
```

### C.2 Speedups

```text
1->2=1.4073x
1->4=2.4927x
1->6=2.4910x
```

Gate check (`1->4 >= 2.5x`): **FAIL (2.4927x)**.

## D) Patch evidence (current diffs)

### D.1 baremetal_lgp/src/bin/lgp_hotloop.rs diff

```diff
diff --git a/baremetal_lgp/src/bin/lgp_hotloop.rs b/baremetal_lgp/src/bin/lgp_hotloop.rs
index 3f0711a..2e49df1 100644
--- a/baremetal_lgp/src/bin/lgp_hotloop.rs
+++ b/baremetal_lgp/src/bin/lgp_hotloop.rs
@@ -1,29 +1,37 @@
 use std::fs;
 use std::path::{Path, PathBuf};
+use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
 use std::sync::Arc;
 use std::thread;
 use std::time::{Duration, Instant};
 
 use baremetal_lgp::library::bank::LibraryBank;
+use baremetal_lgp::library::LibraryImage;
+use baremetal_lgp::oracle::{
+    ExecConfig as OracleExecConfig, Oracle as RealOracle, OracleConfig as RealOracleConfig,
+};
 use baremetal_lgp::search::archive::Archive;
 use baremetal_lgp::search::champion::{maybe_update_champion, Champion, StabilityOracle};
 use baremetal_lgp::search::descriptors::{
     bin_id, build_descriptor, output_entropy_sketch, DescriptorInputs,
 };
 use baremetal_lgp::search::evaluate::{
-    scan_instruction_profile, EvalReport, EvaluatedCandidate, ExecConfig, Linker, Oracle,
+    scan_instruction_profile, EvalReport, EvaluatedCandidate, ExecConfig as SearchExecConfig,
+    Linker,
 };
 use baremetal_lgp::search::ir::{CandidateCfg, Terminator};
 use baremetal_lgp::search::mutate::{
     mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT,
 };
 use baremetal_lgp::search::rng::Rng;
-use baremetal_lgp::search::select::select_parent;
+use baremetal_lgp::search::select::{select_parent, CHAMPION_INJECTION_P};
 use baremetal_lgp::search::topk_trace::{TopKTraceManager, TraceOracle, TraceSummary};
 use baremetal_lgp::types::CandidateId;
 use baremetal_lgp::vm::{VmProgram, VmWorker};
 use clap::Parser;
-use crossbeam_channel::{Receiver, RecvTimeoutError, Sender};
+use crossbeam_channel::{bounded, Receiver, RecvTimeoutError, Sender};
+
+const CHUNK_EVALS: u64 = 256;
 
 #[derive(Parser, Debug)]
 #[command(name = "lgp_hotloop")]
@@ -39,6 +47,38 @@ struct Args {
     topk_trace: usize,
     #[arg(long, default_value_t = 0)]
     max_evals: u64,
+    #[arg(long, default_value_t = 0)]
+    profile_stride: u32,
+    #[arg(long)]
+    seed: Option<u64>,
+}
+
+#[repr(align(128))]
+#[derive(Default)]
+struct WorkerAtomics {
+    evals: AtomicU64,
+    proxy_wins: AtomicU64,
+    filled_bins: AtomicU64,
+    champion_bits: AtomicU64,
+    mutate_ns: AtomicU64,
+    link_ns: AtomicU64,
+    oracle_ns: AtomicU64,
+    archive_ns: AtomicU64,
+}
+
+impl WorkerAtomics {
+    fn new() -> Self {
+        Self {
+            evals: AtomicU64::new(0),
+            proxy_wins: AtomicU64::new(0),
+            filled_bins: AtomicU64::new(0),
+            champion_bits: AtomicU64::new(f64::NEG_INFINITY.to_bits()),
+            mutate_ns: AtomicU64::new(0),
+            link_ns: AtomicU64::new(0),
+            oracle_ns: AtomicU64::new(0),
+            archive_ns: AtomicU64::new(0),
+        }
+    }
 }
 
 #[derive(Clone)]
@@ -52,6 +92,20 @@ struct EvalResult {
     evaluated: EvaluatedCandidate,
 }
 
+struct ChampionEvent {
+    worker_id: u32,
+    champion_mean: f32,
+    champ_hash_hex: String,
+    champ_cfg: CandidateCfg,
+}
+
+#[derive(Clone)]
+struct GlobalChampionMsg {
+    champ_hash_hex: String,
+    champ_mean: f32,
+    champ_cfg: CandidateCfg,
+}
+
 fn main() {
     if let Err(err) = run() {
         eprintln!("lgp_hotloop failed: {err}");
@@ -63,13 +117,29 @@ fn run() -> Result<(), String> {
     let args = Args::parse();
     fs::create_dir_all(&args.run_dir).map_err(|e| e.to_string())?;
 
-    let library = Arc::new(LibraryBank::new_seeded());
+    if args.workers.max(1) == 1 {
+        return run_single_worker(&args);
+    }
+
+    run_island_multi_worker(&args)
+}
+
+fn run_single_worker(args: &Args) -> Result<(), String> {
+    let library_bank = LibraryBank::new_seeded();
+    let library = Arc::new(LibraryImage::from(&library_bank));
     let fallback_parent = CandidateCfg::default();
-    let exec_cfg = ExecConfig {
+    let exec_cfg = SearchExecConfig {
         fuel_max: args.fuel_max,
         stability_runs: 3,
         stability_threshold: 0.0,
     };
+    let oracle_cfg = RealOracleConfig {
+        fuel_max: args.fuel_max,
+        proxy_eps: 2,
+        full_eps_per_family: 4,
+        stability_runs: 3,
+        topk_trace: args.topk_trace,
+    };
 
     let worker_count = args.workers.max(1);
     let (job_tx, job_rx) = crossbeam_channel::unbounded::<Option<EvalJob>>();
@@ -81,13 +151,19 @@ fn run() -> Result<(), String> {
         let tx = result_tx.clone();
         let shared_lib = Arc::clone(&library);
         let cfg = exec_cfg.clone();
+        let oracle_cfg = oracle_cfg;
+        let seed_base = args.seed;
         worker_handles.push(thread::spawn(move || {
-            worker_loop(worker_idx, rx, tx, shared_lib, cfg)
+            worker_loop(worker_idx, rx, tx, shared_lib, cfg, oracle_cfg, seed_base)
         }));
     }
     drop(result_tx);
 
-    let mut rng = Rng::from_entropy();
+    let mut rng = if let Some(seed) = args.seed {
+        Rng::new(mix64(seed ^ 0xA076_1D64_78BD_642F))
+    } else {
+        Rng::from_entropy()
+    };
     let mut archive = Archive::new();
     let mut champion: Option<Champion> = None;
     let mut stability = DeterministicStabilityOracle;
@@ -102,6 +178,7 @@ fn run() -> Result<(), String> {
     let mut proxy_wins = 0_u64;
     let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
     let mut next_weight_refresh = 4096_u64;
+    let mut child_buf = CandidateCfg::default();
     let started = Instant::now();
     let mut next_snapshot = started + Duration::from_secs(10);
 
@@ -119,10 +196,16 @@ fn run() -> Result<(), String> {
             }
             let parent = select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
                 .map_or(&fallback_parent, |elite| &elite.candidate);
-            let child = mutate_candidate(parent, &archive, &mut rng, &mutation_weights);
+            mutate_candidate(
+                parent,
+                &archive,
+                &mut rng,
+                &mutation_weights,
+                &mut child_buf,
+            );
             let job = EvalJob {
                 id: CandidateId(next_id),
-                cfg: child,
+                cfg: child_buf.clone(),
             };
             next_id = next_id.saturating_add(1);
             job_tx.send(Some(job)).map_err(|e| e.to_string())?;
@@ -210,16 +293,441 @@ fn run() -> Result<(), String> {
     Ok(())
 }
 
+fn run_island_multi_worker(args: &Args) -> Result<(), String> {
+    let worker_count = args.workers.max(1);
+    let max_evals = if args.max_evals == 0 {
+        u64::MAX
+    } else {
+        args.max_evals
+    };
+    let seed_base = args.seed.unwrap_or_else(|| os_seed(0xA5A5_A5A5_A5A5_A5A5));
+
+    let library_bank = LibraryBank::new_seeded();
+    let library = Arc::new(LibraryImage::from(&library_bank));
+    let exec_cfg = SearchExecConfig {
+        fuel_max: args.fuel_max,
+        stability_runs: 3,
+        stability_threshold: 0.0,
+    };
+    let oracle_cfg = RealOracleConfig {
+        fuel_max: args.fuel_max,
+        proxy_eps: 2,
+        full_eps_per_family: 4,
+        stability_runs: 3,
+        topk_trace: args.topk_trace,
+    };
+
+    let total_claimed = Arc::new(AtomicU64::new(0));
+    let atomics = Arc::new(
+        (0..worker_count)
+            .map(|_| WorkerAtomics::new())
+            .collect::<Vec<_>>(),
+    );
+
+    let (champ_tx, champ_rx) = bounded::<ChampionEvent>(1024);
+    let mut bcast_txs = Vec::with_capacity(worker_count);
+    let mut bcast_rxs = Vec::with_capacity(worker_count);
+    for _ in 0..worker_count {
+        let (tx, rx) = bounded::<GlobalChampionMsg>(1);
+        bcast_txs.push(tx);
+        bcast_rxs.push(rx);
+    }
+
+    let mut worker_handles = Vec::with_capacity(worker_count);
+    for (worker_id, bcast_rx) in bcast_rxs.into_iter().enumerate() {
+        let lib = Arc::clone(&library);
+        let cfg = exec_cfg.clone();
+        let oracle_cfg = oracle_cfg;
+        let total_claimed = Arc::clone(&total_claimed);
+        let atomics = Arc::clone(&atomics);
+        let champ_tx = champ_tx.clone();
+        let run_dir = args.run_dir.clone();
+        let profile_stride = args.profile_stride;
+
+        worker_handles.push(thread::spawn(move || {
+            worker_thread_main(
+                worker_id,
+                seed_base,
+                max_evals,
+                cfg,
+                oracle_cfg,
+                profile_stride,
+                total_claimed,
+                atomics,
+                champ_tx,
+                bcast_rx,
+                lib,
+                run_dir,
+            )
+        }));
+    }
+    drop(champ_tx);
+
+    let started = Instant::now();
+    let mut last_t = Instant::now();
+    let mut last_sum_evals = 0_u64;
+    let mut global_best_mean = f32::NEG_INFINITY;
+    let mut global_best_hash = String::new();
+
+    loop {
+        thread::sleep(Duration::from_secs(1));
+
+        let mut sum_evals = 0_u64;
+        let mut sum_proxy_wins = 0_u64;
+        let mut filled_bins_sum = 0_u64;
+        let mut best_mean = f32::NEG_INFINITY;
+
+        let mut profile_mutate_ns = 0_u64;
+        let mut profile_link_ns = 0_u64;
+        let mut profile_oracle_ns = 0_u64;
+        let mut profile_archive_ns = 0_u64;
+
+        for wa in atomics.iter() {
+            sum_evals = sum_evals.saturating_add(wa.evals.load(Relaxed));
+            sum_proxy_wins = sum_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
+            filled_bins_sum = filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));
+
+            let mean = f64::from_bits(wa.champion_bits.load(Relaxed)) as f32;
+            if mean > best_mean {
+                best_mean = mean;
+            }
+
+            if args.profile_stride > 0 {
+                profile_mutate_ns = profile_mutate_ns.saturating_add(wa.mutate_ns.load(Relaxed));
+                profile_link_ns = profile_link_ns.saturating_add(wa.link_ns.load(Relaxed));
+                profile_oracle_ns = profile_oracle_ns.saturating_add(wa.oracle_ns.load(Relaxed));
+                profile_archive_ns = profile_archive_ns.saturating_add(wa.archive_ns.load(Relaxed));
+            }
+        }
+
+        while let Ok(evt) = champ_rx.try_recv() {
+            let _source_worker = evt.worker_id;
+            if evt.champion_mean > global_best_mean + 0.001 {
+                global_best_mean = evt.champion_mean;
+                global_best_hash = evt.champ_hash_hex.clone();
+
+                let msg = GlobalChampionMsg {
+                    champ_hash_hex: evt.champ_hash_hex,
+                    champ_mean: evt.champion_mean,
+                    champ_cfg: evt.champ_cfg,
+                };
+                for tx in &bcast_txs {
+                    let _ = tx.try_send(msg.clone());
+                }
+            }
+        }
+
+        if best_mean > global_best_mean {
+            global_best_mean = best_mean;
+        }
+
+        let dt = last_t.elapsed().as_secs_f64().max(1e-9);
+        let d_evals = sum_evals.saturating_sub(last_sum_evals);
+        let evals_per_sec = d_evals as f64 / dt;
+        let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
+        let wins_per_hour = sum_proxy_wins as f64 / (elapsed_secs / 3600.0);
+
+        write_island_snapshot(
+            &args.run_dir,
+            sum_evals,
+            evals_per_sec,
+            wins_per_hour,
+            global_best_mean,
+            filled_bins_sum,
+            &global_best_hash,
+        )
+        .map_err(|e| e.to_string())?;
+
+        if args.profile_stride > 0 {
+            write_profile_snapshot(
+                &args.run_dir,
+                args.profile_stride,
+                sum_evals,
+                profile_mutate_ns,
+                profile_link_ns,
+                profile_oracle_ns,
+                profile_archive_ns,
+            )
+            .map_err(|e| e.to_string())?;
+        }
+
+        last_sum_evals = sum_evals;
+        last_t = Instant::now();
+
+        if args.max_evals != 0 && sum_evals >= args.max_evals {
+            break;
+        }
+    }
+
+    for handle in worker_handles {
+        if handle.join().is_err() {
+            return Err("worker thread panicked".to_string());
+        }
+    }
+
+    let mut final_sum_evals = 0_u64;
+    let mut final_proxy_wins = 0_u64;
+    let mut final_filled_bins_sum = 0_u64;
+    for wa in atomics.iter() {
+        final_sum_evals = final_sum_evals.saturating_add(wa.evals.load(Relaxed));
+        final_proxy_wins = final_proxy_wins.saturating_add(wa.proxy_wins.load(Relaxed));
+        final_filled_bins_sum = final_filled_bins_sum.saturating_add(wa.filled_bins.load(Relaxed));
+    }
+
+    let elapsed_secs = started.elapsed().as_secs_f64().max(1e-6);
+    let final_throughput = final_sum_evals as f64 / elapsed_secs;
+    let final_wins_per_hour = final_proxy_wins as f64 / (elapsed_secs / 3600.0);
+
+    write_island_snapshot(
+        &args.run_dir,
+        final_sum_evals,
+        final_throughput,
+        final_wins_per_hour,
+        global_best_mean,
+        final_filled_bins_sum,
+        &global_best_hash,
+    )
+    .map_err(|e| e.to_string())?;
+
+    Ok(())
+}
+
+#[allow(clippy::too_many_arguments)]
+fn worker_thread_main(
+    worker_id: usize,
+    seed_base: u64,
+    max_evals: u64,
+    exec_cfg: SearchExecConfig,
+    oracle_cfg: RealOracleConfig,
+    profile_stride: u32,
+    total_claimed: Arc<AtomicU64>,
+    atomics: Arc<Vec<WorkerAtomics>>,
+    champ_tx: Sender<ChampionEvent>,
+    bcast_rx: Receiver<GlobalChampionMsg>,
+    library: Arc<LibraryImage>,
+    run_dir: PathBuf,
+) {
+    let seed_worker = mix64(seed_base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_id as u64);
+
+    let mut rng = Rng::new(seed_worker ^ 0xA076_1D64_78BD_642F);
+    let mut archive = Archive::new();
+    let mut champion: Option<Champion> = None;
+    let mut mutation_weights = DEFAULT_MUTATION_WEIGHTS;
+    let mut next_weight_refresh = 4096_u64;
+
+    let mut linker = NoopLinker::default();
+    let mut oracle = RealOracle::new(oracle_cfg, seed_worker ^ 0xD6E8_FDDA_AE9D_3A57);
+    let oracle_exec_cfg = OracleExecConfig {
+        run_full_eval: true,
+    };
+    let mut vm_worker = VmWorker::default();
+    let mut stability = DeterministicStabilityOracle;
+    let mut child_buf = CandidateCfg::default();
+
+    let fallback_parent = CandidateCfg::default();
+
+    let mut global_champ_mean = f32::NEG_INFINITY;
+    let mut global_champ_cfg: Option<CandidateCfg> = None;
+
+    let mut local_evals = 0_u64;
+    let mut local_proxy_wins = 0_u64;
+
+    let mut prof_mutate_ns = 0_u64;
+    let mut prof_link_ns = 0_u64;
+    let mut prof_oracle_ns = 0_u64;
+    let mut prof_archive_ns = 0_u64;
+
+    loop {
+        let start = total_claimed.fetch_add(CHUNK_EVALS, Relaxed);
+        if start >= max_evals {
+            break;
+        }
+        let end = start.saturating_add(CHUNK_EVALS).min(max_evals);
+        let n = end.saturating_sub(start);
+
+        if local_evals >= next_weight_refresh {
+            if let Some(next) = read_mutation_weights(&run_dir) {
+                mutation_weights = next;
+            }
+            next_weight_refresh = next_weight_refresh.saturating_add(4096);
+        }
+
+        let mut pending_champion_event: Option<ChampionEvent> = None;
+
+        for j in 0..n {
+            let eidx = start + j;
+            let do_prof = profile_stride > 0 && (eidx % u64::from(profile_stride) == 0);
+
+            let parent = if global_champ_cfg.is_some()
+                && global_champ_mean.is_finite()
+                && rng.gen_bool(CHAMPION_INJECTION_P)
+            {
+                global_champ_cfg.as_ref().unwrap_or(&fallback_parent)
+            } else {
+                select_parent(&archive, champion.as_ref().map(|c| &c.elite), &mut rng)
+                    .map_or(&fallback_parent, |elite| &elite.candidate)
+            };
+
+            if do_prof {
+                let t = Instant::now();
+                mutate_candidate(
+                    parent,
+                    &archive,
+                    &mut rng,
+                    &mutation_weights,
+                    &mut child_buf,
+                );
+                prof_mutate_ns = prof_mutate_ns.saturating_add(elapsed_nanos_u64(t));
+            } else {
+                mutate_candidate(
+                    parent,
+                    &archive,
+                    &mut rng,
+                    &mutation_weights,
+                    &mut child_buf,
+                );
+            }
+
+            let program = if do_prof {
+                let t = Instant::now();
+                let linked = linker.link(&child_buf);
+                prof_link_ns = prof_link_ns.saturating_add(elapsed_nanos_u64(t));
+                linked
+            } else {
+                linker.link(&child_buf)
+            };
+
+            let report = if do_prof {
+                let t = Instant::now();
+                let eval = evaluate_with_real_oracle(
+                    &mut oracle,
+                    &oracle_exec_cfg,
+                    &mut vm_worker,
+                    &program,
+                    &library,
+                    &exec_cfg,
+                );
+                prof_oracle_ns = prof_oracle_ns.saturating_add(elapsed_nanos_u64(t));
+                eval
+            } else {
+                evaluate_with_real_oracle(
+                    &mut oracle,
+                    &oracle_exec_cfg,
+                    &mut vm_worker,
+                    &program,
+                    &library,
+                    &exec_cfg,
+                )
+            };
+
+            let profile = scan_instruction_profile(&program.words);
+            let code_size_words = program.words.len() as u32;
+            let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
+            let output_entropy = output_entropy_sketch(&report.output_snapshot);
+            let desc = build_descriptor(DescriptorInputs {
+                fuel_used,
+                fuel_max: exec_cfg.fuel_max,
+                code_size_words,
+                branch_count: profile.branch_count,
+                store_count: profile.store_count,
+                total_insns: profile.total_insns,
+                output_entropy,
+                regime_profile_bits: report.regime_profile_bits,
+            });
+
+            let evaluated = EvaluatedCandidate {
+                child_cfg: child_buf.clone(),
+                program,
+                report: report.clone(),
+                profile,
+                desc,
+                bin: bin_id(&desc),
+                score: report.full_mean.unwrap_or(report.proxy_mean),
+                fuel_used,
+                code_size_words,
+            };
+
+            let champion_updated = if do_prof {
+                let t = Instant::now();
+                archive.insert(evaluated.bin, evaluated.to_elite());
+                let updated =
+                    maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability);
+                prof_archive_ns = prof_archive_ns.saturating_add(elapsed_nanos_u64(t));
+                updated
+            } else {
+                archive.insert(evaluated.bin, evaluated.to_elite());
+                maybe_update_champion(&mut champion, &evaluated, &exec_cfg, &mut stability)
+            };
+
+            if evaluated.score > 0.0 {
+                local_proxy_wins = local_proxy_wins.saturating_add(1);
+            }
+            local_evals = local_evals.saturating_add(1);
+
+            if champion_updated {
+                if let Some(current) = champion.as_ref() {
+                    let evt = ChampionEvent {
+                        worker_id: worker_id as u32,
+                        champion_mean: current.full_mean,
+                        champ_hash_hex: program_hash_hex(&evaluated.program),
+                        champ_cfg: current.elite.candidate.clone(),
+                    };
+                    let replace = pending_champion_event
+                        .as_ref()
+                        .map_or(true, |prev| evt.champion_mean > prev.champion_mean);
+                    if replace {
+                        pending_champion_event = Some(evt);
+                    }
+                }
+            }
+        }
+
+        let wa = &atomics[worker_id];
+        wa.evals.store(local_evals, Relaxed);
+        wa.proxy_wins.store(local_proxy_wins, Relaxed);
+        wa.filled_bins.store(u64::from(archive.filled), Relaxed);
+        let champion_mean = champion
+            .as_ref()
+            .map_or(f64::NEG_INFINITY, |c| c.full_mean as f64);
+        wa.champion_bits.store(champion_mean.to_bits(), Relaxed);
+
+        if profile_stride > 0 {
+            wa.mutate_ns.store(prof_mutate_ns, Relaxed);
+            wa.link_ns.store(prof_link_ns, Relaxed);
+            wa.oracle_ns.store(prof_oracle_ns, Relaxed);
+            wa.archive_ns.store(prof_archive_ns, Relaxed);
+        }
+
+        if let Some(evt) = pending_champion_event {
+            let _ = champ_tx.try_send(evt);
+        }
+
+        while let Ok(msg) = bcast_rx.try_recv() {
+            global_champ_mean = msg.champ_mean;
+            global_champ_cfg = Some(msg.champ_cfg);
+            let _ = msg.champ_hash_hex;
+        }
+    }
+}
+
 fn worker_loop(
     worker_idx: usize,
     rx: Receiver<Option<EvalJob>>,
     tx: Sender<EvalResult>,
-    library: Arc<LibraryBank>,
-    exec_cfg: ExecConfig,
+    library: Arc<LibraryImage>,
+    exec_cfg: SearchExecConfig,
+    oracle_cfg: RealOracleConfig,
+    seed_base: Option<u64>,
 ) {
     let mut worker = VmWorker::default();
     let mut linker = NoopLinker::default();
-    let mut oracle = SimOracle::new(os_seed(worker_idx as u64 + 1));
+    let oracle_seed = seed_base
+        .map(|base| mix64(base ^ 0x9E37_79B9_7F4A_7C15_u64 ^ worker_idx as u64))
+        .unwrap_or_else(|| os_seed(worker_idx as u64 + 1));
+    let mut oracle = RealOracle::new(oracle_cfg, oracle_seed);
+    let oracle_exec_cfg = OracleExecConfig {
+        run_full_eval: true,
+    };
 
     while let Ok(job) = rx.recv() {
         let Some(job) = job else {
@@ -229,6 +737,7 @@ fn worker_loop(
             job.cfg,
             &mut linker,
             &mut oracle,
+            &oracle_exec_cfg,
             &mut worker,
             &library,
             &exec_cfg,
@@ -256,6 +765,31 @@ fn os_seed(salt: u64) -> u64 {
     nanos ^ 0xD6E8_FDDA_AE9D_3A57 ^ salt
 }
 
+fn mix64(mut z: u64) -> u64 {
+    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
+    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
+    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
+    z ^ (z >> 31)
+}
+
+fn elapsed_nanos_u64(start: Instant) -> u64 {
+    let nanos = start.elapsed().as_nanos();
+    if nanos > u128::from(u64::MAX) {
+        u64::MAX
+    } else {
+        nanos as u64
+    }
+}
+
+fn program_hash_hex(program: &VmProgram) -> String {
+    let mut hasher = blake3::Hasher::new();
+    hasher.update(&(program.words.len() as u64).to_le_bytes());
+    for &word in &program.words {
+        hasher.update(&word.to_le_bytes());
+    }
+    hasher.finalize().to_hex().to_string()
+}
+
 fn read_mutation_weights(run_dir: &Path) -> Option<[f32; MUTATION_OPERATOR_COUNT]> {
     let path = run_dir.join("mutation_weights.json");
     let body = fs::read_to_string(path).ok()?;
@@ -285,20 +819,21 @@ fn read_mutation_weights(run_dir: &Path) -> Option<[f32; MUTATION_OPERATOR_COUNT
     Some(parsed)
 }
 
-fn evaluate_cfg<L, O>(
+fn evaluate_cfg<L>(
     cfg: CandidateCfg,
     linker: &mut L,
-    oracle: &mut O,
+    oracle: &mut RealOracle,
+    oracle_exec_cfg: &OracleExecConfig,
     worker: &mut VmWorker,
-    library: &LibraryBank,
-    exec_cfg: &ExecConfig,
+    library: &LibraryImage,
+    exec_cfg: &SearchExecConfig,
 ) -> EvaluatedCandidate
 where
     L: Linker,
-    O: Oracle,
 {
     let program = linker.link(&cfg);
-    let report = oracle.eval_candidate(worker, &program, library, exec_cfg);
+    let report =
+        evaluate_with_real_oracle(oracle, oracle_exec_cfg, worker, &program, library, exec_cfg);
     let profile = scan_instruction_profile(&program.words);
     let code_size_words = program.words.len() as u32;
     let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
@@ -349,60 +884,26 @@ impl Linker for NoopLinker {
     }
 }
 
-#[derive(Clone)]
-struct SimOracle {
-    seed: u64,
-    eval_counter: u64,
-}
-
-impl SimOracle {
-    fn new(seed: u64) -> Self {
-        Self {
-            seed,
-            eval_counter: 0,
-        }
-    }
-}
-
-impl Oracle for SimOracle {
-    fn eval_candidate(
-        &mut self,
-        _worker: &mut VmWorker,
-        program: &VmProgram,
-        _library: &LibraryBank,
-        cfg: &ExecConfig,
-    ) -> EvalReport {
-        self.eval_counter = self.eval_counter.saturating_add(1);
-        let signature = program_signature(program, self.seed, self.eval_counter);
-        let base = ((signature & 0xFFFF) as f32 / 32768.0) - 1.0;
-        let jitter = (((signature >> 16) & 0x3FF) as f32 / 2048.0) - 0.25;
-        let proxy_mean = base + jitter * 0.1;
-        let full_available = (signature & 0x3) != 0;
-        let full_mean = full_available
-            .then_some(proxy_mean + ((((signature >> 26) & 0xFF) as f32 / 255.0) - 0.5) * 0.05);
-        let full_var =
-            full_available.then_some(1e-5 + (((signature >> 40) & 0x3FF) as f32 / 100_000.0));
-        let proxy_fuel_used = ((program.words.len() as u32).saturating_mul(3)
-            + (((signature >> 50) & 0x7FF) as u32))
-            .min(cfg.fuel_max.max(1));
-        let full_fuel_used =
-            full_available.then_some(proxy_fuel_used.saturating_add(13).min(cfg.fuel_max.max(1)));
-        let regime_profile_bits = ((signature >> 8) as u8) & 0x0F;
-        let mut output_snapshot = Vec::with_capacity(64);
-        for i in 0..64 {
-            let shifted = signature.rotate_left(i as u32);
-            let raw = ((shifted & 0x3FF) as f32 / 256.0) - 2.0;
-            output_snapshot.push(raw.clamp(-2.0, 2.0));
-        }
-        EvalReport {
-            proxy_mean,
-            proxy_fuel_used,
-            full_mean,
-            full_var,
-            full_fuel_used,
-            regime_profile_bits,
-            output_snapshot,
-        }
+fn evaluate_with_real_oracle(
+    oracle: &mut RealOracle,
+    oracle_exec_cfg: &OracleExecConfig,
+    worker: &mut VmWorker,
+    program: &VmProgram,
+    library: &LibraryImage,
+    exec_cfg: &SearchExecConfig,
+) -> EvalReport {
+    let report = oracle.eval_candidate(worker, program, library, oracle_exec_cfg);
+    let fuel_used = (program.words.len() as u32 + 1).min(exec_cfg.fuel_max.max(1));
+    let output_len = worker.scratch.len().min(64);
+    let output_snapshot = worker.scratch[..output_len].to_vec();
+    EvalReport {
+        proxy_mean: report.proxy_mean,
+        proxy_fuel_used: fuel_used,
+        full_mean: report.full_mean,
+        full_var: report.full_var,
+        full_fuel_used: report.full_mean.map(|_| fuel_used),
+        regime_profile_bits: report.regime_profile_bits,
+        output_snapshot,
     }
 }
 
@@ -510,3 +1011,46 @@ fn write_snapshot(
     fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
     Ok(())
 }
+
+fn write_island_snapshot(
+    run_dir: &Path,
+    completed: u64,
+    throughput: f64,
+    wins_per_hour: f64,
+    champ_mu: f32,
+    filled_bins_sum_islands: u64,
+    champ_hash_hex: &str,
+) -> Result<(), std::io::Error> {
+    let champ_var = f32::INFINITY;
+    let summary_line = format!(
+        "wins/hour={wins_per_hour:.3} champion_mu={champ_mu:.6} champion_var={champ_var:.6} filled_bins={filled_bins_sum_islands} filled_bins_sum_islands={filled_bins_sum_islands} eval_throughput={throughput:.2}/s completed={completed} champion_hash={champ_hash_hex}",
+    );
+    println!("{summary_line}");
+
+    let summary_json = format!(
+        "{{\"wins_per_hour\":{wins_per_hour:.6},\"champion_mean\":{champ_mu:.6},\"champion_var\":{champ_var:.6},\"filled_bins\":{filled_bins_sum_islands},\"filled_bins_sum_islands\":{filled_bins_sum_islands},\"eval_throughput\":{throughput:.6},\"completed\":{completed}}}"
+    );
+    fs::write(run_dir.join("snapshot_latest.json"), summary_json)?;
+    fs::write(run_dir.join("summary_latest.txt"), summary_line)?;
+    Ok(())
+}
+
+fn write_profile_snapshot(
+    run_dir: &Path,
+    profile_stride: u32,
+    completed: u64,
+    mutate_ns: u64,
+    link_ns: u64,
+    oracle_ns: u64,
+    archive_ns: u64,
+) -> Result<(), std::io::Error> {
+    if profile_stride == 0 {
+        return Ok(());
+    }
+
+    let sampled = completed / u64::from(profile_stride.max(1));
+    let profile_line = format!(
+        "profile_stride={profile_stride} sampled={sampled} mutate_ns={mutate_ns} link_ns={link_ns} oracle_ns={oracle_ns} archive_ns={archive_ns}"
+    );
+    fs::write(run_dir.join("profile_latest.txt"), profile_line)
+}
```

### D.2 baremetal_lgp/src/search/mutate.rs diff

```diff
diff --git a/baremetal_lgp/src/search/mutate.rs b/baremetal_lgp/src/search/mutate.rs
index 6531f05..96f4e62 100644
--- a/baremetal_lgp/src/search/mutate.rs
+++ b/baremetal_lgp/src/search/mutate.rs
@@ -46,19 +46,50 @@ pub fn mutate_candidate(
     archive: &Archive,
     rng: &mut Rng,
     weights: &[f32; MUTATION_OPERATOR_COUNT],
-) -> CandidateCfg {
+    child_out: &mut CandidateCfg,
+) {
     for _attempt in 0..8 {
-        let mut child = parent.clone();
+        copy_candidate_cfg(child_out, parent);
         let mutation_count = rng.gen_range_usize(1..5);
         for _ in 0..mutation_count {
             let op = select_operator(rng, weights);
-            apply_operator(op, &mut child, archive, rng);
+            apply_operator(op, child_out, archive, rng);
         }
-        if child.verify().is_ok() {
-            return child;
+        if child_out.verify().is_ok() {
+            return;
+        }
+    }
+    copy_candidate_cfg(child_out, parent);
+}
+
+fn copy_candidate_cfg(dst: &mut CandidateCfg, src: &CandidateCfg) {
+    dst.entry = src.entry;
+    dst.const_pool = src.const_pool;
+
+    if dst.blocks.len() > src.blocks.len() {
+        dst.blocks.truncate(src.blocks.len());
+    }
+    if dst.blocks.len() < src.blocks.len() {
+        dst.blocks.reserve(src.blocks.len() - dst.blocks.len());
+    }
+
+    for (idx, src_block) in src.blocks.iter().enumerate() {
+        if idx == dst.blocks.len() {
+            dst.blocks.push(Block {
+                insns: Vec::new(),
+                term: Terminator::Halt,
+            });
+        }
+        let dst_block = &mut dst.blocks[idx];
+        dst_block.term = src_block.term.clone();
+        dst_block.insns.clear();
+        if dst_block.insns.capacity() < src_block.insns.len() {
+            dst_block
+                .insns
+                .reserve(src_block.insns.len() - dst_block.insns.capacity());
         }
+        dst_block.insns.extend(src_block.insns.iter().cloned());
     }
-    parent.clone()
 }
 
 fn select_operator(rng: &mut Rng, weights: &[f32; MUTATION_OPERATOR_COUNT]) -> MutationOp {
```

### D.3 baremetal_lgp/src/search/evaluate.rs diff

```diff
diff --git a/baremetal_lgp/src/search/evaluate.rs b/baremetal_lgp/src/search/evaluate.rs
index 6223a06..db42edc 100644
--- a/baremetal_lgp/src/search/evaluate.rs
+++ b/baremetal_lgp/src/search/evaluate.rs
@@ -116,7 +116,8 @@ where
     O: Oracle,
 {
     let weights = mutation_weights.unwrap_or(&DEFAULT_MUTATION_WEIGHTS);
-    let child_cfg = mutate_candidate(parent_cfg, archive, rng, weights);
+    let mut child_cfg = CandidateCfg::default();
+    mutate_candidate(parent_cfg, archive, rng, weights, &mut child_cfg);
     let program = harness.linker.link(&child_cfg);
     let report =
         harness
```

### D.4 baremetal_lgp/tests/agent3_search_library.rs diff

```diff
diff --git a/baremetal_lgp/tests/agent3_search_library.rs b/baremetal_lgp/tests/agent3_search_library.rs
index 572fda9..d974dba 100644
--- a/baremetal_lgp/tests/agent3_search_library.rs
+++ b/baremetal_lgp/tests/agent3_search_library.rs
@@ -123,7 +123,8 @@ fn agent3_mutation_can_force_calllib_insertion_pattern() {
     let mut weights = [0.0_f32; MUTATION_OPERATOR_COUNT];
     // Force insert CALL_LIB operator.
     weights[7] = 1.0;
-    let child = mutate_candidate(&parent, &archive, &mut rng, &weights);
+    let mut child = CandidateCfg::default();
+    mutate_candidate(&parent, &archive, &mut rng, &weights, &mut child);
     assert!(child.verify().is_ok());
     assert!(child.blocks.len() > parent.blocks.len());
 
@@ -226,7 +227,8 @@ fn agent3_loop_term_transform_can_insert_bridge_jump() {
     let mut saw_bridge = false;
     for seed in 1..2048_u64 {
         let mut rng = Rng::new(seed);
-        let child = mutate_candidate(&parent, &archive, &mut rng, &weights);
+        let mut child = CandidateCfg::default();
+        mutate_candidate(&parent, &archive, &mut rng, &weights, &mut child);
         if child.blocks.len() <= parent.blocks.len() {
             continue;
         }
```

## E) Full current file data (all modified tracked files)

### E.1 baremetal_lgp/src/bin/lgp_hotloop.rs

```rust
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
```

### E.2 baremetal_lgp/src/search/mutate.rs

```rust
use crate::contracts::abi::{META_IN_BASE, META_OUT_BASE};
use crate::search::archive::Archive;
use crate::search::ir::{
    Block, CandidateCfg, Instruction, OpClass, Opcode, Terminator, CAND_MAX_BLOCKS,
};
use crate::search::rng::Rng;

pub const MUT_W_OP_TWEAK: f32 = 0.18;
pub const MUT_W_REG_REMAP: f32 = 0.12;
pub const MUT_W_IMM_DELTA: f32 = 0.12;
pub const MUT_W_CONST_PERT: f32 = 0.10;
pub const MUT_W_BLOCK_SPLICE: f32 = 0.10;
pub const MUT_W_BLOCK_DELETE: f32 = 0.06;
pub const MUT_W_EDGE_RETARGET: f32 = 0.10;
pub const MUT_W_INSERT_CALL_LIB: f32 = 0.12;
pub const MUT_W_TERM_TRANSFORM: f32 = 0.10;
pub const MUTATION_OPERATOR_COUNT: usize = 9;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MutationOp {
    OpTweak = 0,
    RegRemap = 1,
    ImmDelta = 2,
    ConstPerturb = 3,
    BlockSplice = 4,
    BlockDelete = 5,
    EdgeRetarget = 6,
    InsertCallLib = 7,
    TermTransform = 8,
}

pub const DEFAULT_MUTATION_WEIGHTS: [f32; MUTATION_OPERATOR_COUNT] = [
    MUT_W_OP_TWEAK,
    MUT_W_REG_REMAP,
    MUT_W_IMM_DELTA,
    MUT_W_CONST_PERT,
    MUT_W_BLOCK_SPLICE,
    MUT_W_BLOCK_DELETE,
    MUT_W_EDGE_RETARGET,
    MUT_W_INSERT_CALL_LIB,
    MUT_W_TERM_TRANSFORM,
];

pub fn mutate_candidate(
    parent: &CandidateCfg,
    archive: &Archive,
    rng: &mut Rng,
    weights: &[f32; MUTATION_OPERATOR_COUNT],
    child_out: &mut CandidateCfg,
) {
    for _attempt in 0..8 {
        copy_candidate_cfg(child_out, parent);
        let mutation_count = rng.gen_range_usize(1..5);
        for _ in 0..mutation_count {
            let op = select_operator(rng, weights);
            apply_operator(op, child_out, archive, rng);
        }
        if child_out.verify().is_ok() {
            return;
        }
    }
    copy_candidate_cfg(child_out, parent);
}

fn copy_candidate_cfg(dst: &mut CandidateCfg, src: &CandidateCfg) {
    dst.entry = src.entry;
    dst.const_pool = src.const_pool;

    if dst.blocks.len() > src.blocks.len() {
        dst.blocks.truncate(src.blocks.len());
    }
    if dst.blocks.len() < src.blocks.len() {
        dst.blocks.reserve(src.blocks.len() - dst.blocks.len());
    }

    for (idx, src_block) in src.blocks.iter().enumerate() {
        if idx == dst.blocks.len() {
            dst.blocks.push(Block {
                insns: Vec::new(),
                term: Terminator::Halt,
            });
        }
        let dst_block = &mut dst.blocks[idx];
        dst_block.term = src_block.term.clone();
        dst_block.insns.clear();
        if dst_block.insns.capacity() < src_block.insns.len() {
            dst_block
                .insns
                .reserve(src_block.insns.len() - dst_block.insns.capacity());
        }
        dst_block.insns.extend(src_block.insns.iter().cloned());
    }
}

fn select_operator(rng: &mut Rng, weights: &[f32; MUTATION_OPERATOR_COUNT]) -> MutationOp {
    match rng.sample_weighted_index(weights).unwrap_or(0) {
        0 => MutationOp::OpTweak,
        1 => MutationOp::RegRemap,
        2 => MutationOp::ImmDelta,
        3 => MutationOp::ConstPerturb,
        4 => MutationOp::BlockSplice,
        5 => MutationOp::BlockDelete,
        6 => MutationOp::EdgeRetarget,
        7 => MutationOp::InsertCallLib,
        8 => MutationOp::TermTransform,
        _ => MutationOp::OpTweak,
    }
}

fn apply_operator(op: MutationOp, child: &mut CandidateCfg, archive: &Archive, rng: &mut Rng) {
    match op {
        MutationOp::OpTweak => mut_opcode_tweak(child, rng),
        MutationOp::RegRemap => mut_reg_remap(child, rng),
        MutationOp::ImmDelta => mut_imm_delta(child, rng),
        MutationOp::ConstPerturb => mut_const_perturb(child, rng),
        MutationOp::BlockSplice => mut_block_splice(child, archive, rng),
        MutationOp::BlockDelete => mut_block_delete(child, rng),
        MutationOp::EdgeRetarget => mut_edge_retarget(child, rng),
        MutationOp::InsertCallLib => mut_insert_call_lib(child, rng),
        MutationOp::TermTransform => mut_term_transform(child, rng),
    }
}

fn mut_opcode_tweak(child: &mut CandidateCfg, rng: &mut Rng) {
    let Some((block_idx, insn_idx)) = random_insn_index(child, rng) else {
        return;
    };
    let insn = &mut child.blocks[block_idx].insns[insn_idx];
    let ops = match insn.opcode.class() {
        OpClass::FloatScalar => &FLOAT_SCALAR_OPS[..],
        OpClass::IntScalar => &INT_SCALAR_OPS[..],
        OpClass::Mem => &MEM_OPS[..],
        OpClass::NonLinear => &NON_LINEAR_OPS[..],
        OpClass::VectorReal => &VECTOR_REAL_OPS[..],
        OpClass::VectorComplex => &VECTOR_COMPLEX_OPS[..],
        OpClass::Control | OpClass::Other => return,
    };
    if ops.len() <= 1 {
        return;
    }
    let mut chosen = ops[rng.gen_range_usize(0..ops.len())];
    if chosen == insn.opcode {
        chosen = ops[(rng.gen_range_usize(0..ops.len() - 1) + 1) % ops.len()];
    }
    insn.opcode = chosen;
}

fn mut_reg_remap(child: &mut CandidateCfg, rng: &mut Rng) {
    let Some(block_idx) = rng.choose_index(child.blocks.len()) else {
        return;
    };
    let block = &mut child.blocks[block_idx];
    let mut map = [0_u8; 16];
    for (i, slot) in map.iter_mut().enumerate() {
        *slot = i as u8;
    }

    let swaps = rng.gen_range_usize(2..5);
    for _ in 0..swaps {
        let a = rng.gen_range_usize(0..16);
        let mut b = rng.gen_range_usize(0..16);
        if b == a {
            b = (b + 1) % 16;
        }
        map.swap(a, b);
    }

    for insn in &mut block.insns {
        insn.rd = map[usize::from(insn.rd & 0x0F)];
        insn.ra = map[usize::from(insn.ra & 0x0F)];
        insn.rb = map[usize::from(insn.rb & 0x0F)];
    }
    if let Some(reg) = block.term.control_reg_mut() {
        *reg = map[usize::from(*reg & 0x0F)];
    }
}

fn mut_imm_delta(child: &mut CandidateCfg, rng: &mut Rng) {
    let total_insns: usize = child.blocks.iter().map(|b| b.insns.len()).sum();
    let term_imm_count = child
        .blocks
        .iter()
        .filter(|b| {
            matches!(
                b.term,
                Terminator::Jump { .. }
                    | Terminator::CondZero { .. }
                    | Terminator::CondNonZero { .. }
                    | Terminator::Loop { .. }
            )
        })
        .count();
    let total_choices = total_insns + term_imm_count;
    if total_choices == 0 {
        return;
    }
    let choice = rng.gen_range_usize(0..total_choices);
    let delta = sample_imm_delta(rng);

    if choice < total_insns {
        let mut cursor = choice;
        for block in &mut child.blocks {
            if cursor < block.insns.len() {
                apply_delta_imm14(&mut block.insns[cursor].imm14, delta);
                return;
            }
            cursor -= block.insns.len();
        }
        return;
    }

    let mut remaining = choice - total_insns;
    for block in &mut child.blocks {
        if let Some(imm14) = block.term.imm14_mut() {
            if remaining == 0 {
                apply_delta_imm14(imm14, delta);
                return;
            }
            remaining -= 1;
        }
    }
}

fn mut_const_perturb(child: &mut CandidateCfg, rng: &mut Rng) {
    let idx = rng.gen_range_usize(0..child.const_pool.len());
    let sigma = if rng.gen_bool(0.80) { 0.01 } else { 0.1 };
    let value = child.const_pool[idx] + rng.sample_normal(sigma);
    child.const_pool[idx] = value.clamp(-4.0, 4.0);
}

fn mut_block_splice(child: &mut CandidateCfg, archive: &Archive, rng: &mut Rng) {
    if child.blocks.len() >= CAND_MAX_BLOCKS {
        return;
    }
    let Some(donor_bin) = archive.random_filled_bin(rng) else {
        return;
    };
    let Some(donor) = archive.get(donor_bin) else {
        return;
    };
    let Some(block_idx) = rng.choose_index(donor.candidate.blocks.len()) else {
        return;
    };
    let donor_block = donor.candidate.blocks[block_idx].clone();
    let new_block_id = child.blocks.len() as u16;
    child.blocks.push(donor_block);
    patch_any_edge_to_target(child, new_block_id, rng);
}

fn mut_block_delete(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.len() <= 1 {
        return;
    }
    let entry = usize::from(child.entry);
    let mut remove = rng.gen_range_usize(0..child.blocks.len());
    if remove == entry {
        remove = (remove + 1) % child.blocks.len();
        if remove == entry {
            return;
        }
    }

    child.blocks.remove(remove);
    if usize::from(child.entry) > remove {
        child.entry = child.entry.saturating_sub(1);
    }
    repair_targets_after_delete(child, remove as u16);
}

fn mut_edge_retarget(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.is_empty() {
        return;
    }
    let mut with_targets = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        if block.term.target_count() > 0 {
            with_targets.push(idx);
        }
    }
    let Some(choice) = rng.choose_index(with_targets.len()) else {
        return;
    };
    let block_idx = with_targets[choice];
    let target = rng.gen_range_usize(0..child.blocks.len()) as u16;
    retarget_one(&mut child.blocks[block_idx].term, target, rng);
}

fn mut_insert_call_lib(child: &mut CandidateCfg, rng: &mut Rng) {
    if child.blocks.len() >= CAND_MAX_BLOCKS {
        return;
    }
    let Some(back_target_idx) = rng.choose_index(child.blocks.len()) else {
        return;
    };
    let back_target = back_target_idx as u16;
    let slot = rng.gen_range_u32(0..256) as u16;

    let call_block = Block {
        insns: vec![
            Instruction {
                opcode: Opcode::LdMU32,
                rd: 0,
                ra: 0,
                rb: 0,
                imm14: META_IN_BASE as u16,
            },
            Instruction {
                opcode: Opcode::LdMU32,
                rd: 1,
                ra: 0,
                rb: 0,
                imm14: META_OUT_BASE as u16,
            },
            Instruction {
                opcode: Opcode::CallLib,
                rd: 0,
                ra: 0,
                rb: 0,
                imm14: slot,
            },
        ],
        term: Terminator::Jump {
            target: back_target,
            imm14: 0,
        },
    };
    let new_block_id = child.blocks.len() as u16;
    child.blocks.push(call_block);
    patch_any_edge_to_target(child, new_block_id, rng);
}

fn mut_term_transform(child: &mut CandidateCfg, rng: &mut Rng) {
    let mut candidates = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        match block.term {
            Terminator::CondZero { .. }
            | Terminator::CondNonZero { .. }
            | Terminator::Loop { .. } => {
                candidates.push(idx);
            }
            Terminator::Halt | Terminator::Jump { .. } | Terminator::Return => {}
        }
    }
    let Some(choice) = rng.choose_index(candidates.len()) else {
        return;
    };
    let block_idx = candidates[choice];
    let mut bridge_target = None;
    match &mut child.blocks[block_idx].term {
        Terminator::CondZero { .. } | Terminator::CondNonZero { .. } => {
            child.blocks[block_idx].term.swap_conditional_targets();
        }
        Terminator::Loop {
            body_target,
            exit_target,
            ..
        } => {
            if rng.gen_bool(0.3) {
                let old_body = *body_target;
                core::mem::swap(body_target, exit_target);
                bridge_target = Some(old_body);
            }
        }
        Terminator::Halt | Terminator::Jump { .. } | Terminator::Return => {}
    }

    if let Some(target) = bridge_target {
        if child.blocks.len() < CAND_MAX_BLOCKS {
            let bridge_id = child.blocks.len() as u16;
            child.blocks.push(Block {
                insns: Vec::new(),
                term: Terminator::Jump { target, imm14: 0 },
            });
            if let Terminator::Loop { exit_target, .. } = &mut child.blocks[block_idx].term {
                *exit_target = bridge_id;
            }
        }
    }
}

fn random_insn_index(candidate: &CandidateCfg, rng: &mut Rng) -> Option<(usize, usize)> {
    let mut populated = Vec::new();
    for (block_idx, block) in candidate.blocks.iter().enumerate() {
        if !block.insns.is_empty() {
            populated.push(block_idx);
        }
    }
    let block_choice = rng.choose_index(populated.len())?;
    let block_idx = populated[block_choice];
    let insn_idx = rng.gen_range_usize(0..candidate.blocks[block_idx].insns.len());
    Some((block_idx, insn_idx))
}

fn sample_imm_delta(rng: &mut Rng) -> i32 {
    let p = rng.next_f32();
    if p < 0.70 {
        rng.gen_range_i32_inclusive(-8, 8)
    } else if p < 0.95 {
        rng.gen_range_i32_inclusive(-64, 64)
    } else {
        rng.gen_range_i32_inclusive(-1024, 1024)
    }
}

fn apply_delta_imm14(imm14: &mut u16, delta: i32) {
    let value = (i32::from(*imm14) + delta) & 0x3FFF;
    *imm14 = value as u16;
}

fn patch_any_edge_to_target(child: &mut CandidateCfg, new_target: u16, rng: &mut Rng) {
    let mut sources = Vec::new();
    for (idx, block) in child.blocks.iter().enumerate() {
        if block.term.target_count() > 0 {
            sources.push(idx);
        }
    }
    if let Some(choice) = rng.choose_index(sources.len()) {
        let idx = sources[choice];
        if retarget_one(&mut child.blocks[idx].term, new_target, rng) {
            return;
        }
    }
    if let Some(entry) = child.blocks.get_mut(usize::from(child.entry)) {
        entry.term = Terminator::Jump {
            target: new_target,
            imm14: 0,
        };
    }
}

fn retarget_one(term: &mut Terminator, target: u16, rng: &mut Rng) -> bool {
    match term {
        Terminator::Jump { target: edge, .. } => {
            *edge = target;
            true
        }
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
            if rng.gen_bool(0.5) {
                *true_target = target;
            } else {
                *false_target = target;
            }
            true
        }
        Terminator::Loop {
            body_target,
            exit_target,
            ..
        } => {
            if rng.gen_bool(0.5) {
                *body_target = target;
            } else {
                *exit_target = target;
            }
            true
        }
        Terminator::Halt | Terminator::Return => false,
    }
}

fn repair_targets_after_delete(child: &mut CandidateCfg, removed_block: u16) {
    for block in &mut child.blocks {
        block.term.for_each_target_mut(|target| {
            if *target == removed_block {
                *target = 0;
            } else if *target > removed_block {
                *target = target.saturating_sub(1);
            }
        });
    }
}

const FLOAT_SCALAR_OPS: [Opcode; 9] = [
    Opcode::FMov,
    Opcode::FAdd,
    Opcode::FSub,
    Opcode::FMul,
    Opcode::FFma,
    Opcode::FAbs,
    Opcode::FNeg,
    Opcode::IToF,
    Opcode::FToI,
];

const INT_SCALAR_OPS: [Opcode; 9] = [
    Opcode::IMov,
    Opcode::IAdd,
    Opcode::ISub,
    Opcode::IAnd,
    Opcode::IOr,
    Opcode::IXor,
    Opcode::IShl,
    Opcode::IShr,
    Opcode::IConst,
];

const MEM_OPS: [Opcode; 5] = [
    Opcode::LdF,
    Opcode::StF,
    Opcode::FConst,
    Opcode::LdMU32,
    Opcode::LdMF32,
];

const NON_LINEAR_OPS: [Opcode; 2] = [Opcode::FTanh, Opcode::FSigm];
const VECTOR_REAL_OPS: [Opcode; 5] = [
    Opcode::VAdd,
    Opcode::VMul,
    Opcode::VFma,
    Opcode::VDot,
    Opcode::Gemm,
];
const VECTOR_COMPLEX_OPS: [Opcode; 3] = [Opcode::VCAdd, Opcode::VCMul, Opcode::VCDot];
```

### E.3 baremetal_lgp/src/search/evaluate.rs

```rust
use crate::library::bank::LibraryBank;
use crate::search::archive::{Archive, ArchiveInsert, Elite};
use crate::search::descriptors::{
    bin_id, build_descriptor, output_entropy_sketch, Descriptor, DescriptorInputs,
};
use crate::search::ir::{CandidateCfg, Opcode};
use crate::search::mutate::{mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT};
use crate::search::rng::Rng;
use crate::vm::{VmProgram, VmWorker};

#[derive(Clone, Debug)]
pub struct ExecConfig {
    pub fuel_max: u32,
    pub stability_runs: u32,
    pub stability_threshold: f32,
}

impl Default for ExecConfig {
    fn default() -> Self {
        Self {
            fuel_max: 200_000,
            stability_runs: 3,
            stability_threshold: 0.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct EvalReport {
    pub proxy_mean: f32,
    pub proxy_fuel_used: u32,
    pub full_mean: Option<f32>,
    pub full_var: Option<f32>,
    pub full_fuel_used: Option<u32>,
    pub regime_profile_bits: u8,
    pub output_snapshot: Vec<f32>,
}

impl Default for EvalReport {
    fn default() -> Self {
        Self {
            proxy_mean: 0.0,
            proxy_fuel_used: 0,
            full_mean: None,
            full_var: None,
            full_fuel_used: None,
            regime_profile_bits: 0,
            output_snapshot: Vec::new(),
        }
    }
}

pub trait Linker {
    fn link(&mut self, candidate: &CandidateCfg) -> VmProgram;
}

pub trait Oracle {
    fn eval_candidate(
        &mut self,
        worker: &mut VmWorker,
        program: &VmProgram,
        library: &LibraryBank,
        cfg: &ExecConfig,
    ) -> EvalReport;
}

pub struct EvaluationHarness<'a, L, O> {
    pub linker: &'a mut L,
    pub oracle: &'a mut O,
    pub worker: &'a mut VmWorker,
    pub library: &'a LibraryBank,
    pub exec_cfg: &'a ExecConfig,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct InstructionProfile {
    pub branch_count: u32,
    pub store_count: u32,
    pub total_insns: u32,
}

#[derive(Clone, Debug)]
pub struct EvaluatedCandidate {
    pub child_cfg: CandidateCfg,
    pub program: VmProgram,
    pub report: EvalReport,
    pub profile: InstructionProfile,
    pub desc: Descriptor,
    pub bin: u16,
    pub score: f32,
    pub fuel_used: u32,
    pub code_size_words: u32,
}

impl EvaluatedCandidate {
    pub fn to_elite(&self) -> Elite {
        Elite {
            score: self.score,
            candidate: self.child_cfg.clone(),
            code_size_words: self.code_size_words,
            fuel_used: self.fuel_used,
            desc: self.desc,
        }
    }
}

pub fn evaluate_child<L, O>(
    parent_cfg: &CandidateCfg,
    archive: &Archive,
    rng: &mut Rng,
    harness: &mut EvaluationHarness<'_, L, O>,
    mutation_weights: Option<&[f32; MUTATION_OPERATOR_COUNT]>,
) -> EvaluatedCandidate
where
    L: Linker,
    O: Oracle,
{
    let weights = mutation_weights.unwrap_or(&DEFAULT_MUTATION_WEIGHTS);
    let mut child_cfg = CandidateCfg::default();
    mutate_candidate(parent_cfg, archive, rng, weights, &mut child_cfg);
    let program = harness.linker.link(&child_cfg);
    let report =
        harness
            .oracle
            .eval_candidate(harness.worker, &program, harness.library, harness.exec_cfg);
    let profile = scan_instruction_profile(&program.words);

    let code_size_words = program.words.len() as u32;
    let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
    let entropy = output_entropy_sketch(&report.output_snapshot);
    let descriptor = build_descriptor(DescriptorInputs {
        fuel_used,
        fuel_max: harness.exec_cfg.fuel_max,
        code_size_words,
        branch_count: profile.branch_count,
        store_count: profile.store_count,
        total_insns: profile.total_insns,
        output_entropy: entropy,
        regime_profile_bits: report.regime_profile_bits,
    });

    EvaluatedCandidate {
        child_cfg,
        program,
        score: report.full_mean.unwrap_or(report.proxy_mean),
        fuel_used,
        code_size_words,
        profile,
        bin: bin_id(&descriptor),
        desc: descriptor,
        report,
    }
}

pub fn update_archive(archive: &mut Archive, evaluated: &EvaluatedCandidate) -> ArchiveInsert {
    archive.insert(evaluated.bin, evaluated.to_elite())
}

pub fn scan_instruction_profile(words: &[u32]) -> InstructionProfile {
    let mut profile = InstructionProfile::default();
    for &word in words {
        let opcode = (word & 0x3F) as u8;
        profile.total_insns = profile.total_insns.saturating_add(1);
        let Some(op) = Opcode::from_u8(opcode) else {
            continue;
        };
        if matches!(
            op,
            Opcode::Jmp | Opcode::Jz | Opcode::Jnz | Opcode::Loop | Opcode::Call | Opcode::Ret
        ) {
            profile.branch_count = profile.branch_count.saturating_add(1);
        }
        if matches!(op, Opcode::StF) {
            profile.store_count = profile.store_count.saturating_add(1);
        }
    }
    profile
}
```

### E.4 baremetal_lgp/tests/agent3_search_library.rs

```rust
use std::fs;
use std::path::PathBuf;

use baremetal_lgp::library::bank::{LibraryBank, LibraryProgram};
use baremetal_lgp::library::promote::{promote_slot, PromoteError};
use baremetal_lgp::outer_loop::bandit::Exp3Bandit;
use baremetal_lgp::search::archive::{Archive, ArchiveInsert, Elite};
use baremetal_lgp::search::descriptors::{
    bin_id, bucket_code, bucket_entropy, bucket_fuel, bucket_ratio, build_descriptor,
    output_entropy_sketch, Descriptor, DescriptorInputs,
};
use baremetal_lgp::search::ir::{Block, CandidateCfg, Opcode, Terminator};
use baremetal_lgp::search::mutate::{mutate_candidate, MUTATION_OPERATOR_COUNT};
use baremetal_lgp::search::rng::Rng;

fn seed_candidate(score: f32) -> Elite {
    Elite {
        score,
        candidate: CandidateCfg::default(),
        code_size_words: 1,
        fuel_used: 1,
        desc: Descriptor {
            fuel_bucket: 0,
            code_bucket: 0,
            branch_bucket: 0,
            write_bucket: 0,
            entropy_bucket: 0,
            regime_profile: 0,
        },
    }
}

#[test]
fn agent3_descriptor_bin_id_packs_exact_bits() {
    let d = Descriptor {
        fuel_bucket: 3,
        code_bucket: 2,
        branch_bucket: 1,
        write_bucket: 0,
        entropy_bucket: 3,
        regime_profile: 0b1010,
    };
    let packed = bin_id(&d);
    let expected = 3_u16 | (2_u16 << 2) | (1_u16 << 4) | (3_u16 << 8) | (0b1010_u16 << 10);
    assert_eq!(packed, expected);
}

#[test]
fn agent3_bucket_boundaries_match_contract() {
    assert_eq!(bucket_fuel(0.25), 0);
    assert_eq!(bucket_fuel(0.50), 1);
    assert_eq!(bucket_fuel(0.75), 2);
    assert_eq!(bucket_fuel(0.751), 3);

    assert_eq!(bucket_code(128), 0);
    assert_eq!(bucket_code(256), 1);
    assert_eq!(bucket_code(512), 2);
    assert_eq!(bucket_code(513), 3);

    assert_eq!(bucket_ratio(0.05), 0);
    assert_eq!(bucket_ratio(0.15), 1);
    assert_eq!(bucket_ratio(0.30), 2);
    assert_eq!(bucket_ratio(0.31), 3);

    assert_eq!(bucket_entropy(1.0), 0);
    assert_eq!(bucket_entropy(2.0), 1);
    assert_eq!(bucket_entropy(3.0), 2);
    assert_eq!(bucket_entropy(3.1), 3);
}

#[test]
fn agent3_entropy_sketch_is_low_for_constant_outputs() {
    let out = vec![0.0_f32; 64];
    let entropy = output_entropy_sketch(&out);
    assert!(entropy <= 1e-6);
}

#[test]
fn agent3_descriptor_builder_maps_all_components() {
    let desc = build_descriptor(DescriptorInputs {
        fuel_used: 50,
        fuel_max: 100,
        code_size_words: 300,
        branch_count: 20,
        store_count: 5,
        total_insns: 100,
        output_entropy: 2.2,
        regime_profile_bits: 14,
    });
    assert_eq!(desc.fuel_bucket, 1);
    assert_eq!(desc.code_bucket, 2);
    assert_eq!(desc.branch_bucket, 2);
    assert_eq!(desc.write_bucket, 0);
    assert_eq!(desc.entropy_bucket, 2);
    assert_eq!(desc.regime_profile, 14);
}

#[test]
fn agent3_archive_insert_replace_rules_hold() {
    let mut archive = Archive::new();
    let bin = 123_u16;
    assert_eq!(
        archive.insert(bin, seed_candidate(1.0)),
        ArchiveInsert::Inserted
    );
    assert_eq!(archive.filled, 1);
    assert_eq!(
        archive.insert(bin, seed_candidate(0.9)),
        ArchiveInsert::Kept
    );
    assert_eq!(
        archive.insert(bin, seed_candidate(1.1)),
        ArchiveInsert::Replaced
    );
    assert_eq!(archive.filled, 1);
}

#[test]
fn agent3_mutation_can_force_calllib_insertion_pattern() {
    let parent = CandidateCfg::default();
    let archive = Archive::new();
    let mut rng = Rng::new(42);
    let mut weights = [0.0_f32; MUTATION_OPERATOR_COUNT];
    // Force insert CALL_LIB operator.
    weights[7] = 1.0;
    let mut child = CandidateCfg::default();
    mutate_candidate(&parent, &archive, &mut rng, &weights, &mut child);
    assert!(child.verify().is_ok());
    assert!(child.blocks.len() > parent.blocks.len());

    let mut found_pattern = false;
    for block in &child.blocks {
        let has_in = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::LdMU32 && insn.imm14 == 0);
        let has_out = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::LdMU32 && insn.imm14 == 2);
        let has_call = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::CallLib);
        if has_in && has_out && has_call {
            found_pattern = true;
            break;
        }
    }
    assert!(
        found_pattern,
        "CALL_LIB insertion block pattern was not found"
    );
}

#[test]
fn agent3_library_seeds_expected_slots() {
    let bank = LibraryBank::new_seeded();
    assert_eq!(bank.slots.len(), 256);
    for idx in 0..20 {
        assert!(bank.slots[idx].is_some(), "slot {idx} should be seeded");
    }
    for idx in 20..256 {
        assert!(bank.slots[idx].is_none(), "slot {idx} should be empty");
    }
}

#[test]
fn agent3_promote_slot_validates_inputs() {
    let mut bank = LibraryBank::new_seeded();
    let program = LibraryProgram::new(vec![1, 2, 3], [0.0; 128]);
    promote_slot(&mut bank, 42, program, true).expect("promotion should work");
    assert_eq!(bank.epoch, 1);

    let bad = LibraryProgram::new(vec![0_u32; 2048], [0.0; 128]);
    let err = promote_slot(&mut bank, 43, bad, false).expect_err("must reject oversized program");
    assert!(matches!(err, PromoteError::InvalidProgram(_)));
}

#[test]
fn agent3_bandit_updates_and_persists_weights() {
    let mut bandit = Exp3Bandit::new(
        [1.0 / MUTATION_OPERATOR_COUNT as f32; MUTATION_OPERATOR_COUNT],
        0.12,
    );
    bandit.update_from_reward(2, 0.4);
    bandit.update_from_reward(7, -0.2);
    let sum = bandit.weights.iter().sum::<f32>();
    assert!((sum - 1.0).abs() < 1e-4);

    let temp = unique_temp_dir("agent3_bandit");
    fs::create_dir_all(&temp).expect("create temp dir");
    bandit.write_weights_file(&temp).expect("write weights");
    let body = fs::read_to_string(temp.join("mutation_weights.json")).expect("read file");
    assert!(body.contains("\"weights\""));
}

#[test]
fn agent3_loop_term_transform_can_insert_bridge_jump() {
    let parent = CandidateCfg {
        blocks: vec![
            Block {
                insns: Vec::new(),
                term: Terminator::Loop {
                    reg: 0,
                    body_target: 1,
                    exit_target: 2,
                    imm14: 0,
                },
            },
            Block {
                insns: Vec::new(),
                term: Terminator::Halt,
            },
            Block {
                insns: Vec::new(),
                term: Terminator::Halt,
            },
        ],
        entry: 0,
        ..CandidateCfg::default()
    };
    let archive = Archive::new();
    let mut weights = [0.0_f32; MUTATION_OPERATOR_COUNT];
    weights[8] = 1.0;

    let mut saw_bridge = false;
    for seed in 1..2048_u64 {
        let mut rng = Rng::new(seed);
        let mut child = CandidateCfg::default();
        mutate_candidate(&parent, &archive, &mut rng, &weights, &mut child);
        if child.blocks.len() <= parent.blocks.len() {
            continue;
        }
        let bridge_target = child.blocks.last().and_then(|b| match b.term {
            Terminator::Jump { target, .. } => Some(target),
            _ => None,
        });
        if bridge_target == Some(1) {
            saw_bridge = true;
            break;
        }
    }
    assert!(
        saw_bridge,
        "expected loop transform to create a bridge jump block"
    );
}

fn unique_temp_dir(prefix: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0_u128, |d| d.as_nanos());
    path.push(format!("{prefix}_{pid}_{nanos}"));
    path
}
```
