use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ControlCommand {
    Status,
    Health,
    IngestReality {
        manifest_path: String,
    },
    IngestPrior {
        manifest_path: String,
    },
    IngestSubstrate {
        manifest_path: String,
    },
    IngestFormal {
        manifest_path: String,
    },
    IngestTool {
        manifest_path: String,
    },
    StartRun {
        profile: String,
        epochs: u32,
    },
    Pause,
    Resume,
    CancelRun {
        run_id: String,
    },
    BackupCreate,
    BackupVerify {
        backup_id: String,
    },
    RestoreDryRun {
        backup_id: String,
    },
    RestoreApply {
        backup_id: String,
    },
    GcDryRun,
    GcApply,
    Compact,
    Qualify {
        mode: String,
    },
    DiagDump,
    ReleaseVerify {
        manifest_path: String,
    },
    ActiveShow,
    Rollback,
    ForceClearRecovery,
    ForceThermalSpike {
        temp: f64,
        epochs: u32,
        cooldown_temp: f64,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ControlRequest {
    pub request_id: String,
    pub actor: String,
    pub token: Option<String>,
    pub command: ControlCommand,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ControlResponse {
    pub request_id: String,
    pub ok: bool,
    pub message: String,
    pub payload: Option<serde_json::Value>,
}
