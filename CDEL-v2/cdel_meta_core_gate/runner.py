from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .domain import MetaCoreAudit
from .errors import MetaCoreGateInvalid, MetaCoreGateInternal

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_KEYS = {
    "verdict",
    "active_bundle_hash",
    "prev_active_bundle_hash",
    "kernel_hash",
    "meta_hash",
    "ruleset_hash",
    "toolchain_merkle_root",
    "ledger_head_hash",
}


def _require_hash(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise MetaCoreGateInvalid(f"{name} invalid")
    return value


def _require_hash_or_empty(name: str, value: Any) -> str:
    if value == "":
        return ""
    return _require_hash(name, value)


def audit_meta_core_active(meta_core_root: str, *, timeout_s: int = 60) -> MetaCoreAudit:
    """
    Calls meta-core audit CLI. Fail-closed:
    - returns MetaCoreAudit on success
    - raises MetaCoreGateInvalid on invalid
    - raises MetaCoreGateInternal on tool/internal errors
    """
    root = Path(meta_core_root)
    if not root.is_absolute():
        raise MetaCoreGateInternal("meta_core_root must be absolute")
    cli_path = root / "cli" / "meta_core_audit_active.py"
    if not cli_path.is_file():
        raise MetaCoreGateInternal("meta-core audit cli missing")

    cdel_root = Path(__file__).resolve().parents[1]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONUTF8": "1",
    }

    with tempfile.TemporaryDirectory(dir=str(cdel_root)) as tmp_dir:
        out_path = Path(tmp_dir) / "meta_core_audit.json"
        try:
            result = subprocess.run(
                [
                    "python3",
                    str(cli_path),
                    "--meta-core-root",
                    str(root),
                    "--out-json",
                    str(out_path),
                ],
                cwd=str(root),
                env=env,
                timeout=timeout_s,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise MetaCoreGateInternal("meta-core audit timed out") from exc
        except OSError as exc:
            raise MetaCoreGateInternal("meta-core audit failed to start") from exc

        if result.returncode == 2:
            raise MetaCoreGateInvalid("meta-core audit invalid")
        if result.returncode != 0:
            raise MetaCoreGateInternal(f"meta-core audit failed (exit {result.returncode})")

        if not out_path.is_file():
            raise MetaCoreGateInternal("meta-core audit json missing")
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise MetaCoreGateInternal("meta-core audit json parse error") from exc

        if not isinstance(payload, dict):
            raise MetaCoreGateInvalid("meta-core audit json invalid")
        if set(payload.keys()) != _REQUIRED_KEYS:
            raise MetaCoreGateInvalid("meta-core audit json schema mismatch")
        if payload.get("verdict") != "OK":
            raise MetaCoreGateInvalid("meta-core audit verdict not ok")

        active_bundle_hash = _require_hash("active_bundle_hash", payload.get("active_bundle_hash"))
        prev_active_bundle_hash = _require_hash_or_empty(
            "prev_active_bundle_hash", payload.get("prev_active_bundle_hash")
        )
        kernel_hash = _require_hash("kernel_hash", payload.get("kernel_hash"))
        meta_hash = _require_hash("meta_hash", payload.get("meta_hash"))
        ruleset_hash = _require_hash("ruleset_hash", payload.get("ruleset_hash"))
        toolchain_merkle_root = _require_hash(
            "toolchain_merkle_root", payload.get("toolchain_merkle_root")
        )
        ledger_head_hash = _require_hash("ledger_head_hash", payload.get("ledger_head_hash"))

        return MetaCoreAudit(
            active_bundle_hash=active_bundle_hash,
            prev_active_bundle_hash=prev_active_bundle_hash,
            kernel_hash=kernel_hash,
            meta_hash=meta_hash,
            ruleset_hash=ruleset_hash,
            toolchain_merkle_root=toolchain_merkle_root,
            ledger_head_hash=ledger_head_hash,
        )
