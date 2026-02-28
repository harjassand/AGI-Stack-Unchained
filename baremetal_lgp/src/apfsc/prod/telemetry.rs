use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Default)]
pub struct Telemetry {
    counters: Arc<Mutex<BTreeMap<String, u64>>>,
    gauges: Arc<Mutex<BTreeMap<String, f64>>>,
}

impl Telemetry {
    pub fn inc(&self, key: &str, by: u64) {
        if let Ok(mut c) = self.counters.lock() {
            *c.entry(key.to_string()).or_insert(0) += by;
        }
    }

    pub fn set_gauge(&self, key: &str, value: f64) {
        if let Ok(mut g) = self.gauges.lock() {
            g.insert(key.to_string(), value);
        }
    }

    pub fn snapshot(&self) -> TelemetrySnapshot {
        let counters = self.counters.lock().map(|m| m.clone()).unwrap_or_default();
        let gauges = self.gauges.lock().map(|m| m.clone()).unwrap_or_default();
        TelemetrySnapshot { counters, gauges }
    }

    pub fn to_prometheus_text(&self) -> String {
        let snap = self.snapshot();
        let mut out = String::new();
        for (k, v) in snap.counters {
            out.push_str(&format!("{} {}\n", sanitize_metric_name(&k), v));
        }
        for (k, v) in snap.gauges {
            out.push_str(&format!("{} {}\n", sanitize_metric_name(&k), v));
        }
        out
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct TelemetrySnapshot {
    pub counters: BTreeMap<String, u64>,
    pub gauges: BTreeMap<String, f64>,
}

pub fn sanitize_metric_name(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == ':' {
                c
            } else {
                '_'
            }
        })
        .collect()
}
