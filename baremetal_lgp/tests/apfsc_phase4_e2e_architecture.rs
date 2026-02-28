use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::orchestrator::run_phase4_epoch;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{FamilyWeights, ProtectionFloor};
use tempfile::tempdir;

fn fixtures_phase2() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase2")
}
fn fixtures_phase3() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase3")
}
fn fixtures_phase4() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc/phase4")
}

fn cfg() -> Phase1Config {
    Phase1Config::from_path(&fixtures_phase4().join("config/phase4.toml")).expect("cfg")
}

fn ingest_all(root: &std::path::Path, cfg: &Phase1Config) {
    for d in [
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
    ] {
        ingest_reality(root, cfg, &fixtures_phase2().join(d).join("manifest.json"))
            .expect("ingest p2");
    }
    for d in [
        "reality_f4_event_sparse_base",
        "reality_f4_event_sparse_transfer",
        "reality_f4_event_sparse_robust",
        "reality_f5_formal_alg_base",
        "reality_f5_formal_alg_transfer",
        "reality_f5_formal_alg_robust",
    ] {
        ingest_reality(root, cfg, &fixtures_phase3().join(d).join("manifest.json"))
            .expect("ingest p3");
    }
    for d in [
        "reality_challenge/f6_hidden_logic_challenge",
        "reality_challenge/f7_hidden_sparse_challenge",
    ] {
        ingest_reality(root, cfg, &fixtures_phase4().join(d).join("manifest.json"))
            .expect("ingest p4 challenge");
    }
    ingest_prior(
        root,
        cfg,
        &fixtures_phase3().join("priors/macro_seed/manifest.json"),
    )
    .expect("prior");
}

#[test]
fn phase4_architecture_epoch_writes_challenge_and_atomic_receipts() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = cfg();
    cfg.phase4.searchlaw_required_yield_improvement = 0.10;
    cfg.lanes.max_truth_candidates = 2;
    cfg.lanes.max_equivalence_candidates = 1;
    cfg.lanes.max_incubator_candidates = 1;
    cfg.lanes.max_public_candidates = 3;
    cfg.train.steps = 1;
    cfg.incubator.shadow_steps = 1;
    cfg.witness.count = 2;
    cfg.witness.rotation = 1;
    cfg.phase3.limits.max_paradigm_public_candidates = 2;
    cfg.phase3.canary.warm_windows = 4;
    cfg.phase3.canary.cold_windows = 4;
    for fam in [
        "event_sparse",
        "formal_alg",
        "hidden_logic",
        "hidden_sparse",
    ] {
        cfg.phase2
            .weights
            .entry(fam.to_string())
            .or_insert(FamilyWeights {
                static_weight: 1.0 / 8.0,
                transfer_weight: 1.0 / 8.0,
                robust_weight: 1.0 / 8.0,
            });
        cfg.phase2
            .floors
            .entry(fam.to_string())
            .or_insert(ProtectionFloor {
                protected: false,
                max_static_regress_bpb: 0.01,
                max_transfer_regress_bpb: 0.01,
                max_robust_regress_bpb: 0.01,
                min_family_improve_bpb: 0.0,
            });
    }

    seed_init(&root, &cfg, None, true).expect("seed");
    ingest_all(&root, &cfg);

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let report =
        run_phase4_epoch(&root, &cfg, Some(&constellation.constellation_id)).expect("phase4");
    if report
        .judge_report
        .receipts
        .iter()
        .any(|r| r.decision == baremetal_lgp::apfsc::types::JudgeDecision::Promote)
    {
        assert!(root.join("receipts/challenge").exists());
    }
    assert!(root.join("pointers/active_candidate").exists());
}
