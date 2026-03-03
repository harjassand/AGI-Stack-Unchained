use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::daemon::serve_with_on_ready;
use baremetal_lgp::apfsc::prod::preflight::ensure_preflight;
use baremetal_lgp::apfsc::prod::profiles::{load_layered_config, resolve_paths};
use baremetal_lgp::apfsc::prod::service::{
    spawn_background_recovery, spawn_resonance_distiller, spawn_symbolic_extraction_daemon,
    ServiceContext,
};
use baremetal_lgp::apfsc::prod::telemetry::Telemetry;
use clap::Parser;

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = "config/base.toml")]
    base_config: PathBuf,
    #[arg(long, default_value = "config/profiles/prod_single_node.toml")]
    profile_config: PathBuf,
    #[arg(long)]
    local_override: Option<PathBuf>,
    #[arg(long, default_value_t = false)]
    omega_mode: bool,
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    if args.omega_mode {
        std::env::set_var("APFSC_OMEGA_MODE", "1");
        std::env::set_var("APFSC_SILENT_RUN", "1");
        std::env::set_var("APFSC_DEMON_LANE_STRICT", "1");
    }
    let cfg = load_layered_config(
        &args.base_config,
        &args.profile_config,
        args.local_override.as_deref(),
    )
    .map_err(|e| e.to_string())?;
    let (mut root, mut control_db_path, mut socket_path) = resolve_paths(&cfg);
    if args.omega_mode {
        if std::env::var_os("APFSC_ROOT").is_none() {
            if let Ok(home) = std::env::var("HOME") {
                root = PathBuf::from(home).join(".apfsc");
            } else {
                root = PathBuf::from(".apfsc");
            }
        }
        control_db_path = PathBuf::from("file:apfscd_omega_memdb?mode=memory&cache=shared");
        socket_path = root.join("discoveries").join("omega_apfscd.sock");
    }
    ensure_preflight(&root, &cfg).map_err(|e| e.to_string())?;

    let conn = open_control_db(&control_db_path).map_err(|e| e.to_string())?;
    let telemetry = Telemetry::default();
    let mut ctx = ServiceContext::new(root.clone(), root.join("backups"), conn, telemetry);
    ctx.set_control_db_path(control_db_path.clone());
    let token_file = root.join(&cfg.auth.token_file);
    let recovery_root = root.clone();
    let recovery_db = control_db_path.clone();
    let recovery_state = ctx.runtime_state_handle();
    let distiller_root = root.clone();
    let distiller_db = control_db_path.clone();
    let rosetta_root = root.clone();
    let rosetta_db = control_db_path.clone();

    let distiller_interval = std::env::var("APFSC_DISTILLER_INTERVAL_EPOCHS")
        .ok()
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(50)
        .max(1);
    let rosetta_interval = std::env::var("APFSC_ROSETTA_INTERVAL_EPOCHS")
        .ok()
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(25)
        .max(1);

    let omega_mode = args.omega_mode;
    serve_with_on_ready(&root, &socket_path, &token_file, &mut ctx, move || {
        if omega_mode {
            return;
        }
        let _ = spawn_background_recovery(
            recovery_root.clone(),
            recovery_db.clone(),
            recovery_state.clone(),
        );
        let _ = spawn_resonance_distiller(
            distiller_root.clone(),
            distiller_db.clone(),
            distiller_interval,
            true,
        );
        let _ = spawn_symbolic_extraction_daemon(
            rosetta_root.clone(),
            rosetta_db.clone(),
            rosetta_interval,
            true,
        );
    })
    .map_err(|e| e.to_string())
}
