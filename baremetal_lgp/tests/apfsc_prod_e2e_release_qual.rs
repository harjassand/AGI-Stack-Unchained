use baremetal_lgp::apfsc::prod::service::run_qualification;
use tempfile::tempdir;

#[test]
fn release_qualification_emits_report() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let r = run_qualification(&root, "release").expect("qual");
    assert!(r.passed);
    assert!(root.join("evals/reports/qual-release.json").exists());
}
