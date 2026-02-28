use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::formal::ingest_formal;
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::ingress::substrate::ingest_substrate;
use baremetal_lgp::apfsc::ingress::tool::ingest_tool;
use baremetal_lgp::apfsc::orchestrator::run_phase4_epoch;
use baremetal_lgp::apfsc::seed::seed_init;
use baremetal_lgp::apfsc::types::{FamilyWeights, ProtectionFloor};
use tempfile::tempdir;

fn root_fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}
fn phase4() -> PathBuf {
    root_fixtures().join("phase4")
}

#[test]
fn phase4_two_epoch_loop_is_replayable_shape_and_updates_ledgers() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::from_path(&phase4().join("config/phase4.toml")).expect("cfg");
    cfg.phase4.searchlaw_required_yield_improvement = 0.10;
    cfg.lanes.max_truth_candidates = 1;
    cfg.lanes.max_equivalence_candidates = 1;
    cfg.lanes.max_incubator_candidates = 1;
    cfg.lanes.max_public_candidates = 2;
    cfg.train.steps = 1;
    cfg.incubator.shadow_steps = 1;
    cfg.witness.count = 2;
    cfg.witness.rotation = 1;
    cfg.phase3.limits.max_paradigm_public_candidates = 2;
    cfg.phase3.canary.warm_windows = 4;
    cfg.phase3.canary.cold_windows = 4;
    cfg.phase2
        .weights
        .entry("event_sparse".to_string())
        .or_insert(FamilyWeights {
            static_weight: 0.2,
            transfer_weight: 0.2,
            robust_weight: 0.2,
        });
    cfg.phase2
        .floors
        .entry("event_sparse".to_string())
        .or_insert(ProtectionFloor {
            protected: false,
            max_static_regress_bpb: 0.01,
            max_transfer_regress_bpb: 0.01,
            max_robust_regress_bpb: 0.01,
            min_family_improve_bpb: 0.0,
        });

    seed_init(&root, &cfg, None, true).expect("seed");
    for d in [
        "reality_f0_det_base",
        "reality_f0_det_transfer",
        "reality_f0_det_robust",
    ] {
        ingest_reality(
            &root,
            &cfg,
            &root_fixtures().join("phase2").join(d).join("manifest.json"),
        )
        .expect("reality");
    }
    for d in [
        "reality_f4_event_sparse_base",
        "reality_f4_event_sparse_transfer",
        "reality_f4_event_sparse_robust",
    ] {
        ingest_reality(
            &root,
            &cfg,
            &root_fixtures().join("phase3").join(d).join("manifest.json"),
        )
        .expect("phase3 event");
    }
    ingest_reality(
        &root,
        &cfg,
        &phase4().join("reality_challenge/f6_hidden_logic_challenge/manifest.json"),
    )
    .expect("challenge");
    ingest_prior(
        &root,
        &cfg,
        &root_fixtures().join("phase3/priors/macro_seed/manifest.json"),
    )
    .expect("prior1");
    ingest_prior(
        &root,
        &cfg,
        &phase4().join("priors/recombination_seed/manifest.json"),
    )
    .expect("prior2");
    ingest_substrate(
        &root,
        &cfg,
        &root_fixtures().join("substrate_seed/manifest.json"),
    )
    .expect("substrate");
    let _ = ingest_formal(
        &root,
        &cfg,
        &phase4().join("formal/deny_unbounded_gather/manifest.json"),
    )
    .expect("formal");
    let _ = ingest_tool(
        &root,
        &cfg,
        &phase4().join("tools/tool_graph_shadow/manifest.json"),
    )
    .expect("tool");

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let r1 = run_phase4_epoch(&root, &cfg, Some(&constellation.constellation_id)).expect("epoch1");
    let r2 = run_phase4_epoch(&root, &cfg, Some(&constellation.constellation_id)).expect("epoch2");

    assert!(root
        .join("snapshots")
        .join(&snapshot)
        .join("hidden_challenge_manifest.json")
        .exists());
    assert!(root.join("archives").exists());
    assert!(root.join("archives/need_tokens.jsonl").exists());
    assert!(root.join("portfolios").exists());
    assert_eq!(r1.public_receipts.len(), r2.public_receipts.len());
}
