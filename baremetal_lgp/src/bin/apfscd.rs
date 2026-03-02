use std::path::PathBuf;

use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::daemon::serve_with_on_ready;
use baremetal_lgp::apfsc::prod::preflight::ensure_preflight;
use baremetal_lgp::apfsc::prod::profiles::{load_layered_config, resolve_paths};
use baremetal_lgp::apfsc::prod::service::{spawn_background_recovery, ServiceContext};
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
}

fn main() -> Result<(), String> {
    let args = Args::parse();
    let cfg = load_layered_config(
        &args.base_config,
        &args.profile_config,
        args.local_override.as_deref(),
    )
    .map_err(|e| e.to_string())?;
    let (root, control_db_path, socket_path) = resolve_paths(&cfg);
    ensure_preflight(&root, &cfg).map_err(|e| e.to_string())?;

    let conn = open_control_db(&control_db_path).map_err(|e| e.to_string())?;
    let telemetry = Telemetry::default();
    let mut ctx = ServiceContext::new(root.clone(), root.join("backups"), conn, telemetry);
    ctx.set_control_db_path(control_db_path.clone());
    let token_file = root.join(&cfg.auth.token_file);
    let recovery_root = root.clone();
    let recovery_db = control_db_path.clone();
    let recovery_state = ctx.runtime_state_handle();

    serve_with_on_ready(&root, &socket_path, &token_file, &mut ctx, move || {
        let _ = spawn_background_recovery(
            recovery_root.clone(),
            recovery_db.clone(),
            recovery_state.clone(),
        );
    })
    .map_err(|e| e.to_string())
}
