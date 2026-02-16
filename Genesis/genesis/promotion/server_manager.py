from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ServerHandle:
    process: subprocess.Popen
    base_url: str
    info_path: Path


def _wait_for_info(path: Path, timeout_s: float = 5.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise RuntimeError("server info file not created")


def _wait_for_health(base_url: str, timeout_s: float = 20.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("healthz not ready")


def start_server(
    cdel_root: Path,
    ledger_dir: Path,
    fixture_dir: Path,
    epoch_id: str,
    component_store_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    info_path: Path | None = None,
    env_overrides: dict | None = None,
) -> ServerHandle:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    info_path = info_path or (ledger_dir / "server_info.json")
    if info_path.exists():
        info_path.unlink()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cdel_root)
    if env_overrides:
        env.update({str(k): str(v) for k, v in env_overrides.items()})
    cmd = [
        "python3",
        "-m",
        "cdel.cdel_server",
        "--host",
        host,
        "--port",
        str(port),
        "--ledger-dir",
        str(ledger_dir),
        "--fixture-dir",
        str(fixture_dir),
        "--server-info-file",
        str(info_path),
        "--epoch-id",
        epoch_id,
    ]
    if component_store_dir is not None:
        cmd.extend(["--component-store-dir", str(component_store_dir)])
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    info = _wait_for_info(info_path)
    base_url = info.get("base_url", "")
    if not base_url:
        raise RuntimeError("missing base_url in server info")
    _wait_for_health(base_url)
    return ServerHandle(process=proc, base_url=base_url, info_path=info_path)


def stop_server(handle: ServerHandle) -> None:
    handle.process.terminate()
    try:
        handle.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        handle.process.kill()
        handle.process.wait(timeout=5)
