use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::transfer::{debug_adapt_candidate_for_family, evaluate_transfer};
use baremetal_lgp::apfsc::types::{EvalMode, JudgeRejectReason};
use tempfile::tempdir;

fn fixtures_phase2() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase2")
}

fn phase2_config() -> Phase1Config {
    Phase1Config::from_path(&fixtures_phase2().join("config/phase2.toml")).expect("phase2 config")
}

fn ingest_all_phase2(root: &std::path::Path, cfg: &Phase1Config) {
    let dirs = [
        "reality_f0_det_base",
        "reality_f0_det_transfer",
        "reality_f0_det_robust",
        "reality_f1_text_base",
        "reality_f1_text_transfer",
        "reality_f1_text_robust",
        "reality_f2_sensor_base",
        "reality_f2_sensor_transfer",
        "reality_f2_sensor_robust",
        "reality_f3_phys_base",
        "reality_f3_phys_transfer",
        "reality_f3_phys_robust",
    ];
    for d in dirs {
        ingest_reality(root, cfg, &fixtures_phase2().join(d).join("manifest.json"))
            .expect("ingest reality");
    }
}

#[test]
fn phase2_transfer_is_bounded_and_replay_stable() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = phase2_config();

    seed_init(&root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("pack hashes");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let active_hash =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let candidate =
        baremetal_lgp::apfsc::candidate::load_candidate(&root, &active_hash).expect("candidate");

    let (adapted, delta_bits) =
        debug_adapt_candidate_for_family(&root, &candidate, "det_micro", &constellation)
            .expect("adapt");

    assert_eq!(adapted.arch_program, candidate.arch_program);
    assert_eq!(
        adapted.state_pack.core_weights,
        candidate.state_pack.core_weights
    );
    assert_eq!(
        adapted.head_pack.native_head,
        candidate.head_pack.native_head
    );
    assert!(
        adapted.head_pack.nuisance_head != candidate.head_pack.nuisance_head
            || adapted.head_pack.residual_head != candidate.head_pack.residual_head
            || adapted.state_pack.resid_weights != candidate.state_pack.resid_weights
    );
    assert!(delta_bits > 0);

    let e1 = evaluate_transfer(
        &root,
        &candidate,
        &candidate,
        &constellation,
        EvalMode::Public,
    )
    .expect("transfer eval");
    let e2 = evaluate_transfer(
        &root,
        &candidate,
        &candidate,
        &constellation,
        EvalMode::Public,
    )
    .expect("transfer eval replay");
    assert_eq!(e1.receipt.replay_hash, e2.receipt.replay_hash);
    assert!((e1.delta_bpb - e2.delta_bpb).abs() < 1e-12);

    let mut tiny = constellation.clone();
    for fam in &mut tiny.family_specs {
        fam.transfer_adapt.max_delta_bits = 8;
    }
    let err = evaluate_transfer(&root, &candidate, &candidate, &tiny, EvalMode::Public)
        .expect_err("must fail tiny budget");
    assert!(err
        .to_string()
        .contains(&JudgeRejectReason::TransferDeltaBudgetExceeded.as_reason()));
}
