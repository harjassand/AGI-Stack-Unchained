use baremetal_lgp::library::LibraryImage;
use baremetal_lgp::oracle::{funnel, ExecConfig, Oracle, OracleConfig, SplitMix64};
use baremetal_lgp::vm::{VmProgram, VmWorker};

#[test]
fn weighted_family_sampling_excludes_coverage_and_fallback_is_stable() {
    let mut rng = SplitMix64::new(0x1234_5678_ABCD_EF00);
    let weights = [0.1, 0.2, 0.3, 0.4];
    for coverage in 0_u8..4_u8 {
        for _ in 0..128 {
            let sampled = funnel::sample_weighted_excluding(weights, coverage, &mut rng);
            assert_ne!(sampled, coverage);
        }
    }

    let mut fallback_rng = SplitMix64::new(7);
    let fallback = funnel::sample_weighted_excluding([0.0, 1.0, 0.0, 0.0], 1, &mut fallback_rng);
    assert_eq!(fallback, 2);

    let bits = funnel::regime_profile_bits([0.05, -0.01, -0.20, 0.25], 0.10);
    assert_eq!(bits, 0b1001);
}

#[test]
fn full_eval_populates_balanced_report_and_profile_bits() {
    let mut oracle = Oracle::new(
        OracleConfig {
            fuel_max: 150_000,
            proxy_eps: 99,
            full_eps_per_family: 1,
            stability_runs: 1,
            topk_trace: 4,
        },
        0xCAFE_F00D,
    );
    let mut worker = VmWorker::default();
    let prog = VmProgram {
        words: vec![0x1, 0x2, 0x3, 0x4, 0x5],
    };
    let lib = LibraryImage::default();
    let report = oracle.eval_candidate(
        &mut worker,
        &prog,
        &lib,
        &ExecConfig {
            run_full_eval: true,
        },
    );

    assert!(report.full_mean.is_some());
    assert!(report.full_var.is_some());
    let by_family = report
        .full_by_family
        .expect("full_by_family should be populated when full eval is enabled");
    assert_eq!(by_family.len(), 4);
    assert!(report.regime_profile_bits <= 0b1111);
}

#[test]
fn trace_job_gate_keeps_only_topk_scores() {
    let mut oracle = Oracle::new(
        OracleConfig {
            fuel_max: 100_000,
            proxy_eps: 2,
            full_eps_per_family: 4,
            stability_runs: 3,
            topk_trace: 2,
        },
        0xA55A,
    );

    assert!(oracle.maybe_emit_trace_job(1, 0.10));
    assert!(oracle.maybe_emit_trace_job(2, 0.20));
    assert!(!oracle.maybe_emit_trace_job(3, 0.05));
    assert!(oracle.maybe_emit_trace_job(4, 0.30));
}
