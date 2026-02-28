use std::collections::BTreeMap;
use std::path::PathBuf;

use baremetal_lgp::apfsc::bank::{load_bank, load_payload_index};
use baremetal_lgp::apfsc::bytecoder::score_panel;
use baremetal_lgp::apfsc::candidate::load_active_candidate;
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::lanes::{equivalence, incubator, truth};
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/apfsc")
}

fn setup() -> (tempfile::TempDir, std::path::PathBuf, Phase1Config) {
    let tmp = tempdir().expect("tempdir");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    seed_init(&root, &cfg, Some(&fixtures()), true).expect("seed init");
    ingest_reality(
        &root,
        &cfg,
        &fixtures().join("reality_f0_det/manifest.json"),
    )
    .expect("ingest f0");
    (tmp, root, cfg)
}

#[test]
fn truth_lane_emits_bounded_candidates() {
    let (_tmp, root, cfg) = setup();
    let active = load_active_candidate(&root).expect("active");
    let cands = truth::generate(&active, &cfg).expect("generate");
    assert!(cands.len() <= cfg.lanes.max_truth_candidates);
}

#[test]
fn equivalence_lane_candidates_pass_witness_equality() {
    let (_tmp, root, cfg) = setup();
    let active = load_active_candidate(&root).expect("active");
    let bank = load_bank(&root, "F0").expect("bank");
    let witnesses: Vec<_> = bank.public.iter().take(16).cloned().collect();
    let payloads = load_payload_index(&root).expect("payloads");

    let raw = equivalence::generate(&active, &cfg).expect("generate");
    let filtered =
        equivalence::filter_witness_equality(&active, raw, &witnesses, &payloads).expect("filter");

    assert!(!filtered.is_empty());
}

#[test]
fn incubator_sidecar_zero_native_coupling_preserves_parent_score() {
    let (_tmp, root, cfg) = setup();
    let active = load_active_candidate(&root).expect("active");
    let bank = load_bank(&root, "F0").expect("bank");
    let payloads: BTreeMap<String, Vec<u8>> = load_payload_index(&root).expect("payloads");

    let train = bank.train.iter().take(16).cloned().collect::<Vec<_>>();
    let public = bank.public.iter().take(16).cloned().collect::<Vec<_>>();

    let artifacts =
        incubator::generate(&active, &cfg, &train, &public, &payloads).expect("generate incubator");
    let first = artifacts.first().expect("at least one artifact");

    let parent_score = score_panel(&active.arch_program, &active.head_pack, &payloads, &public)
        .expect("score parent");
    let sidecar_score = score_panel(
        &first.sidecar_program,
        &active.head_pack,
        &payloads,
        &public,
    )
    .expect("score sidecar");

    assert!((parent_score.total_bits - sidecar_score.total_bits).abs() <= 1e-6);
}

#[test]
fn incubator_materializes_splice_candidate() {
    let (_tmp, root, mut cfg) = setup();
    cfg.incubator.incubator_min_utility_bits = -1_000.0;

    let active = load_active_candidate(&root).expect("active");
    let bank = load_bank(&root, "F0").expect("bank");
    let payloads = load_payload_index(&root).expect("payloads");

    let train = bank.train.iter().take(16).cloned().collect::<Vec<_>>();
    let public = bank.public.iter().take(16).cloned().collect::<Vec<_>>();

    let artifacts =
        incubator::generate(&active, &cfg, &train, &public, &payloads).expect("generate incubator");
    let splice = incubator::materialize_splice_candidates(&active, artifacts, &cfg)
        .expect("materialize splice");

    assert!(!splice.is_empty());
}
