use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::candidate::clone_with_mutation;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::judge::{evaluate_phase2_candidate, judge_phase2_candidate};
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{JudgeDecision, PromotionClass};
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
fn phase2_specialist_candidate_is_rejected() {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = phase2_config();

    seed_init(&root, &cfg, None, true).expect("seed init");
    ingest_all_phase2(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("pack hashes");
    let mut constellation =
        build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    // Let coverage/floor gates decide, not margin gates.
    constellation.normalization.public_static_margin_bpb = -1.0;
    constellation.normalization.holdout_static_margin_bpb = -1.0;
    constellation.normalization.min_improved_families = 4;
    constellation
        .normalization
        .min_nonprotected_improved_families = 2;
    constellation.normalization.require_target_subset_hit = false;

    let active_hash =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");
    let active = baremetal_lgp::apfsc::candidate::load_candidate(&root, &active_hash)
        .expect("active candidate");

    // Deliberately over-specialized / brittle head bias.
    let mut heads = active.head_pack.clone();
    for w in &mut heads.native_head.weights {
        *w *= 0.1;
    }
    for b in &mut heads.native_head.bias {
        *b = -8.0;
    }
    if let Some(v) = heads.native_head.bias.get_mut(b'P' as usize) {
        *v = 8.0;
    }

    let specialist = clone_with_mutation(
        &active,
        "truth",
        "specialist_det_only",
        PromotionClass::S,
        active.arch_program.clone(),
        heads,
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
    .expect("specialist clone");
    baremetal_lgp::apfsc::candidate::save_candidate(&root, &specialist).expect("save specialist");

    let evals = evaluate_phase2_candidate(&root, &specialist, &active, &constellation)
        .expect("eval specialist");
    let receipt = judge_phase2_candidate(&root, &specialist, &active, &constellation, &cfg, &evals)
        .expect("judge specialist");

    assert_eq!(receipt.decision, JudgeDecision::Reject);
    assert!(
        receipt.reason.contains("InsufficientCrossFamilyEvidence")
            || receipt.reason.contains("ProtectedFamilyRegress"),
        "unexpected reject reason: {}",
        receipt.reason
    );
}
