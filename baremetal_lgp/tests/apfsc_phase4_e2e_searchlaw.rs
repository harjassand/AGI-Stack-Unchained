use std::path::PathBuf;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::constellation::{build_constellation, pack_hashes_from_snapshot};
use baremetal_lgp::apfsc::ingress::formal::ingest_formal;
use baremetal_lgp::apfsc::ingress::prior::ingest_prior;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::ingress::tool::ingest_tool;
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

#[test]
fn phase4_searchlaw_receipts_exist_and_pointer_is_separate() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg =
        Phase1Config::from_path(&fixtures_phase4().join("config/phase4.toml")).expect("cfg");
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
    for fam in ["event_sparse", "hidden_logic"] {
        cfg.phase2
            .weights
            .entry(fam.to_string())
            .or_insert(FamilyWeights {
                static_weight: 0.2,
                transfer_weight: 0.2,
                robust_weight: 0.2,
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
    for d in [
        "reality_f0_det_base",
        "reality_f0_det_transfer",
        "reality_f0_det_robust",
    ] {
        ingest_reality(
            &root,
            &cfg,
            &fixtures_phase2().join(d).join("manifest.json"),
        )
        .expect("ingest det");
    }
    for d in [
        "reality_f4_event_sparse_base",
        "reality_f4_event_sparse_transfer",
        "reality_f4_event_sparse_robust",
    ] {
        ingest_reality(
            &root,
            &cfg,
            &fixtures_phase3().join(d).join("manifest.json"),
        )
        .expect("ingest event");
    }
    ingest_reality(
        &root,
        &cfg,
        &fixtures_phase4().join("reality_challenge/f6_hidden_logic_challenge/manifest.json"),
    )
    .expect("ingest");
    ingest_prior(
        &root,
        &cfg,
        &fixtures_phase3().join("priors/macro_seed/manifest.json"),
    )
    .expect("prior");
    ingest_prior(
        &root,
        &cfg,
        &fixtures_phase4().join("priors/searchlaw_seed/manifest.json"),
    )
    .expect("prior2");
    let _ = ingest_formal(
        &root,
        &cfg,
        &fixtures_phase4().join("formal/deny_unbounded_gather/manifest.json"),
    )
    .expect("formal");
    let _ = ingest_tool(
        &root,
        &cfg,
        &fixtures_phase4().join("tools/tool_graph_shadow/manifest.json"),
    )
    .expect("tool");

    let snapshot =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_snapshot").expect("snapshot");
    let packs = pack_hashes_from_snapshot(&root, &snapshot).expect("packs");
    let constellation = build_constellation(&root, &cfg, &snapshot, &packs).expect("constellation");

    let active_candidate_before =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("cand ptr");
    let _ = run_phase4_epoch(&root, &cfg, Some(&constellation.constellation_id)).expect("phase4");

    let active_search_law =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_search_law").expect("law ptr");
    assert!(!active_search_law.is_empty());
    assert!(root.join("search_laws").exists());
    assert_eq!(
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate")
            .expect("cand ptr after")
            .is_empty(),
        false
    );
    let _ = active_candidate_before;
}
