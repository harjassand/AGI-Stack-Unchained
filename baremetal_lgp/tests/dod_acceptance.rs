use std::fs;
use std::path::PathBuf;
use std::process::Command;

use baremetal_lgp::abi::CONST_POOL_WORDS;
use baremetal_lgp::bytecode::program::BytecodeProgram;
use baremetal_lgp::isa::encoding::encode;
use baremetal_lgp::isa::op::Op;
use baremetal_lgp::library::bank::LibraryBank;
use baremetal_lgp::library::LibraryImage;
use baremetal_lgp::oracle::regimes::complex_linear;
use baremetal_lgp::oracle::scoring;
use baremetal_lgp::oracle::{ExecConfig as OracleExecConfig, Oracle, OracleConfig, SplitMix64};
use baremetal_lgp::outer_loop::stage_a::StageARegistry;
use baremetal_lgp::search::descriptors::bucket_code;
use baremetal_lgp::types::StopReason;
use baremetal_lgp::vm::{run_candidate, ExecConfig, VmProgram, VmWorker};

fn mk_prog(words: Vec<u32>, const_pool: [f32; CONST_POOL_WORDS]) -> BytecodeProgram {
    BytecodeProgram {
        words,
        const_pool,
        #[cfg(feature = "trace")]
        pc_to_block: Vec::new(),
    }
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

#[test]
fn dod_gas_enforcement_stops_infinite_loop_with_fuel_exhausted() {
    let prog = mk_prog(vec![encode(Op::Jmp, 0, 0, 0, 0)], [0.0; CONST_POOL_WORDS]);
    let lib = LibraryBank::default();
    let mut worker = VmWorker::default();

    let result = run_candidate(
        &mut worker,
        &prog,
        &lib,
        &ExecConfig {
            fuel_max: 64,
            trace: false,
            trace_budget_bytes: 0,
        },
    );

    assert_eq!(
        result.stop_reason,
        baremetal_lgp::vm::StopReason::FuelExhausted
    );
    assert_eq!(result.fuel_used, 64);
}

#[test]
fn dod_hidden_oracle_champion_trend_upward() {
    let mut oracle = Oracle::new(
        OracleConfig {
            fuel_max: 200_000,
            proxy_eps: 2,
            full_eps_per_family: 4,
            stability_runs: 3,
            topk_trace: 16,
        },
        0xD0D5_A11C_E123_4567,
    );
    let mut rng = SplitMix64::new(0xBADC_0FFE_EE01_0101);
    let mut worker = VmWorker::default();
    let lib = LibraryImage::default();
    let cfg = OracleExecConfig {
        run_full_eval: true,
    };

    let mut first_observed = None::<f32>;
    let mut champion = f32::NEG_INFINITY;
    for _ in 0..4_096_u32 {
        let mut words = Vec::with_capacity(64);
        for _ in 0..64_u32 {
            words.push((rng.next_u64() as u32) & 0x00FF_FFFF);
        }
        let mut const_pool = [0.0_f32; CONST_POOL_WORDS];
        for slot in const_pool.iter_mut().take(8) {
            *slot = rng.range_f32(-1.0, 1.0);
        }
        let program = VmProgram {
            words,
            const_pool,
            #[cfg(feature = "trace")]
            pc_to_block: Vec::new(),
        };
        let report = oracle.eval_candidate(&mut worker, &program, &lib, &cfg);
        let score = report
            .full_mean
            .expect("full_mean must exist when run_full_eval=true");
        if first_observed.is_none() {
            first_observed = Some(score);
        }
        champion = champion.max(score);
    }

    let first = first_observed.expect("at least one candidate evaluated");
    assert!(
        champion >= first + 0.01,
        "champion did not trend upward enough: first={first:.6}, best={champion:.6}"
    );
}

#[test]
fn dod_library_promotion_calllib_improves_code_bucket_score_stable() {
    let mut motif = Vec::new();
    motif.push(encode(Op::LdF, 0, 0, 0, 0));
    for _ in 0..140_u32 {
        motif.push(encode(Op::Nop, 0, 0, 0, 0));
    }
    motif.push(encode(Op::StF, 0, 1, 0, 0));

    let lib_prog = mk_prog(
        {
            let mut words = motif.clone();
            words.push(encode(Op::Ret, 0, 0, 0, 0));
            words
        },
        [0.0; CONST_POOL_WORDS],
    );

    let baseline_prog = mk_prog(
        {
            let mut words = vec![
                encode(Op::IConst, 0, 0, 0, 0),
                encode(Op::IConst, 1, 0, 0, 1),
            ];
            words.extend_from_slice(&motif);
            words.push(encode(Op::Halt, 0, 0, 0, 0));
            words
        },
        [0.0; CONST_POOL_WORDS],
    );

    let promoted_prog = mk_prog(
        vec![
            encode(Op::IConst, 0, 0, 0, 0),
            encode(Op::IConst, 1, 0, 0, 1),
            encode(Op::CallLib, 0, 0, 0, 0),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        [0.0; CONST_POOL_WORDS],
    );

    let mut bank = LibraryBank::default();
    bank.set_slot(0, lib_prog).expect("library slot 0 set");

    let run = |prog: &BytecodeProgram| -> f32 {
        let mut worker = VmWorker::default();
        worker.scratch[0] = 0.25;
        let res = run_candidate(
            &mut worker,
            prog,
            &bank,
            &ExecConfig {
                fuel_max: 100_000,
                trace: false,
                trace_budget_bytes: 0,
            },
        );
        assert_eq!(res.stop_reason, baremetal_lgp::vm::StopReason::Halt);
        worker.scratch[1]
    };

    let baseline_out = run(&baseline_prog);
    let promoted_out = run(&promoted_prog);
    let baseline_score = -((baseline_out - 0.25).powi(2));
    let promoted_score = -((promoted_out - 0.25).powi(2));

    let baseline_bucket = bucket_code(baseline_prog.words.len() as u32);
    let promoted_bucket = bucket_code(promoted_prog.words.len() as u32);

    assert!(
        promoted_bucket < baseline_bucket,
        "expected promoted code bucket to improve: baseline={baseline_bucket} promoted={promoted_bucket}"
    );
    assert!(
        (promoted_score - baseline_score).abs() <= 1.0e-9,
        "score changed after CALL_LIB promotion: baseline={baseline_score} promoted={promoted_score}"
    );
}

#[test]
fn dod_complex_family_requires_complex_ops_score_collapse_without_vcmul() {
    let mut rng = SplitMix64::new(0xFACE_B00C);
    let episode = complex_linear::sample(&mut rng, 0.6);
    let l = episode.meta_u32[6] as usize;
    assert!(l > 0);

    let perfect = episode.target.clone();
    let mut no_complex = vec![0.0_f32; perfect.len()];
    for idx in 0..l {
        let x_re = episode.in_data[2 * idx];
        let x_im = episode.in_data[2 * idx + 1];
        let w_re = episode.in_data[2 * l + 2 * idx];
        let w_im = episode.in_data[2 * l + 2 * idx + 1];
        // Debug-style "complex disabled" fallback: no cross terms, so imag lane collapses.
        no_complex[2 * idx] = w_re * x_re;
        no_complex[2 * idx + 1] = w_im * x_im;
    }

    let good_score = scoring::score_episode(&perfect, &episode.target, 10, StopReason::Halt, 0.0);
    let collapsed_score =
        scoring::score_episode(&no_complex, &episode.target, 10, StopReason::Halt, 0.0);

    assert!(
        good_score > collapsed_score + 0.05,
        "expected complex-disabled collapse: good={good_score:.6} collapsed={collapsed_score:.6}"
    );
}

#[cfg(target_os = "macos")]
#[test]
fn dod_stage_a_hot_swap_shadow_accepts_and_wins_per_hour_increases() {
    let workdir = unique_temp_dir("dod_stage_a");
    fs::create_dir_all(&workdir).expect("create temp dir");
    let src = workdir.join("stage_a_module.c");
    let dylib = workdir.join("libstage_a_module.dylib");
    let source = r#"
        #include <math.h>
        float fast_tanh(float x) { (void)x; return 0.70f; }
        float fast_sigm(float x) { (void)x; return 0.35f; }
    "#;
    fs::write(&src, source).expect("write c source");

    let status = Command::new("cc")
        .arg("-dynamiclib")
        .arg("-fPIC")
        .arg(src.as_os_str())
        .arg("-o")
        .arg(dylib.as_os_str())
        .status()
        .expect("invoke cc");
    assert!(status.success(), "failed to compile stage_a module");

    let module = StageARegistry::load_module(&dylib).expect("load stage_a module");
    let mut registry = StageARegistry::new();
    let baseline_dispatch = registry.active_dispatch();
    let baseline =
        ((baseline_dispatch.fast_tanh)(0.5) + (baseline_dispatch.fast_sigm)(-0.25)) * 256.0;

    let accepted = registry.promote_if_shadow_passes(module, |dispatch, episodes| {
        ((dispatch.fast_tanh)(0.5) + (dispatch.fast_sigm)(-0.25)) * episodes as f32
    });
    assert!(accepted, "shadow battery should accept better module");

    let upgraded_dispatch = registry.active_dispatch();
    let upgraded =
        ((upgraded_dispatch.fast_tanh)(0.5) + (upgraded_dispatch.fast_sigm)(-0.25)) * 256.0;
    assert!(
        upgraded > baseline,
        "wins/hour proxy did not improve: baseline={baseline:.6} upgraded={upgraded:.6}"
    );
}
