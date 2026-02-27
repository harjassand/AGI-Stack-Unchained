use baremetal_lgp::library::LibraryImage;
use baremetal_lgp::oracle::{funnel, ExecConfig, Oracle, OracleConfig};
use baremetal_lgp::vm::{VmProgram, VmWorker};

#[test]
fn proxy_coverage_family_hits_each_family_twice_over_eight_candidates() {
    let cfg = OracleConfig {
        fuel_max: 100_000,
        proxy_eps: 2,
        full_eps_per_family: 4,
        stability_runs: 3,
        topk_trace: 16,
    };

    let mut oracle = Oracle::new(cfg, 0xA11CE);
    let mut worker = VmWorker::default();
    let prog = VmProgram {
        words: vec![0x13, 0x24, 0x35, 0x46],
        const_pool: [0.0; baremetal_lgp::abi::CONST_POOL_WORDS],
        #[cfg(feature = "trace")]
        pc_to_block: Vec::new(),
    };
    let lib = LibraryImage::default();
    let exec_cfg = ExecConfig::default();

    let mut coverage_counts = [0_u32; 4];
    for _ in 0..8 {
        let coverage = funnel::coverage_family(oracle.proxy_counter()) as usize;
        let _ = oracle.eval_candidate(&mut worker, &prog, &lib, &exec_cfg);
        coverage_counts[coverage] = coverage_counts[coverage].saturating_add(1);
    }

    assert!(
        coverage_counts.iter().all(|count| *count >= 2),
        "coverage counts were {coverage_counts:?}"
    );
}
