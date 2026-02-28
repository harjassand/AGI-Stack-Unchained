use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::recombination::materialize_recombination_candidate;
use baremetal_lgp::apfsc::seed::seed_init;
use tempfile::tempdir;

#[test]
fn recombination_builds_candidate_and_spec() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let cfg = Phase1Config::default();
    seed_init(&root, &cfg, None, true).expect("seed");
    let active =
        baremetal_lgp::apfsc::artifacts::read_pointer(&root, "active_candidate").expect("active");

    let (cand, spec) =
        materialize_recombination_candidate(&root, &active, &active, "block_swap", &cfg)
            .expect("recombine");
    assert!(!spec.compatibility_hash.is_empty());
    assert!(root
        .join("candidates")
        .join(&cand.manifest.candidate_hash)
        .join("recombination_spec.json")
        .exists());
}
