use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::prod::auth::resolve_role;
use crate::apfsc::prod::control_api::{ControlRequest, ControlResponse};
use crate::apfsc::prod::service::{handle_request, ServiceContext};

pub fn serve(
    root: &Path,
    socket_path: &Path,
    token_file: &Path,
    ctx: &mut ServiceContext,
) -> Result<()> {
    if socket_path.exists() {
        std::fs::remove_file(socket_path).map_err(|e| io_err(socket_path, e))?;
    }
    if let Some(parent) = socket_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    let listener = UnixListener::bind(socket_path).map_err(|e| io_err(socket_path, e))?;
    for stream in listener.incoming() {
        match stream {
            Ok(mut s) => {
                let _ = handle_client(root, token_file, &mut s, ctx);
            }
            Err(e) => return Err(io_err(socket_path, e)),
        }
    }
    Ok(())
}

pub fn serve_once(
    _root: &Path,
    token_file: &Path,
    stream: &mut UnixStream,
    ctx: &mut ServiceContext,
) -> Result<()> {
    let mut body = Vec::new();
    stream
        .read_to_end(&mut body)
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let req: ControlRequest = serde_json::from_slice(&body)?;
    let role = resolve_role(token_file, &req.actor, req.token.as_deref())?;
    let resp = handle_request(ctx, &req, role).unwrap_or_else(|e| ControlResponse {
        request_id: req.request_id.clone(),
        ok: false,
        message: e.to_string(),
        payload: None,
    });
    let out = serde_json::to_vec(&resp).map_err(|e| ApfscError::Protocol(e.to_string()))?;
    stream
        .write_all(&out)
        .map_err(|e| ApfscError::Protocol(e.to_string()))?;
    let _ = stream.shutdown(std::net::Shutdown::Write);
    Ok(())
}

fn handle_client(
    root: &Path,
    token_file: &Path,
    stream: &mut UnixStream,
    ctx: &mut ServiceContext,
) -> Result<()> {
    serve_once(root, token_file, stream, ctx)
}
