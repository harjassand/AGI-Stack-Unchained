use baremetal_lgp::apfsc::prod::preflight::run_preflight;
use baremetal_lgp::apfsc::prod::profiles::ProdRuntimeConfig;
use tempfile::tempdir;

#[test]
fn preflight_creates_required_directories() {
    let tmp = tempdir().expect("tmp");
    let cfg = ProdRuntimeConfig::default();
    let r = run_preflight(tmp.path(), &cfg).expect("preflight");
    assert!(r.ok);
    assert!(tmp.path().join("control").exists());
}
