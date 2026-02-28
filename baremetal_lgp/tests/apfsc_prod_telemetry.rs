use baremetal_lgp::apfsc::prod::telemetry::Telemetry;

#[test]
fn telemetry_emits_expected_metric_names() {
    let t = Telemetry::default();
    t.inc("apfsc_run_total", 1);
    t.set_gauge("apfsc_rss_bytes", 10.0);
    let text = t.to_prometheus_text();
    assert!(text.contains("apfsc_run_total 1"));
    assert!(text.contains("apfsc_rss_bytes 10"));
}
