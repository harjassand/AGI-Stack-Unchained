#!/usr/bin/env python3
"""Emit V19_GE_DISPATCH_EVIDENCE_v1.json from v19 loop run artifacts.

This mirrors the GE SH1 evidence counting logic used by
tools/omega/omega_overnight_runner_v1._count_ge_sh1_artifacts, but scans
the per-tick directories produced by tools/v19_runs/run_omega_v19_full_loop.py.

Fail-closed: exit non-zero if no GE dispatches are found.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_TICK_DIR_RE = re.compile(r"^tick_(\d+)$")
_DAEMON_ID = "rsi_omega_daemon_v19_0"
_GE_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_load_dict(path: Path, *, errors: list[str], context: str) -> dict[str, Any] | None:
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"INVALID_JSON:{context}:{path.as_posix()}:{type(exc).__name__}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"NOT_OBJECT:{context}:{path.as_posix()}")
        return None
    return payload


def _state_dir(run_dir: Path) -> Path:
    return run_dir / "daemon" / _DAEMON_ID / "state"


def _tick_run_dirs(runs_root: Path) -> list[tuple[int, Path]]:
    runs_root = runs_root.resolve()
    out: list[tuple[int, Path]] = []
    for child in sorted(runs_root.iterdir(), key=lambda row: row.as_posix()):
        if not child.is_dir():
            continue
        match = _TICK_DIR_RE.match(child.name)
        if not match:
            continue
        out.append((int(match.group(1)), child))
    if out:
        out.sort(key=lambda row: int(row[0]))
        return out
    return [(0, runs_root)]


def count_ge_evidence(*, runs_root: Path) -> dict[str, Any]:
    runs_root = runs_root.resolve()
    errors: list[str] = []

    ge_dispatch_dirs: list[Path] = []
    ge_dispatch_receipt_paths: list[str] = []

    for _tick_id, run_dir in _tick_run_dirs(runs_root):
        state_dir = _state_dir(run_dir)
        dispatch_root = state_dir / "dispatch"
        if not dispatch_root.exists() or not dispatch_root.is_dir():
            continue
        for dispatch_dir in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
            if not dispatch_dir.is_dir():
                continue
            matched_ge = False
            for dispatch_path in sorted(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json"), key=lambda row: row.as_posix()):
                dispatch_payload = _safe_load_dict(dispatch_path, errors=errors, context="omega_dispatch_receipt_v1")
                if dispatch_payload is None:
                    continue
                if str(dispatch_payload.get("campaign_id", "")).strip() == _GE_CAMPAIGN_ID:
                    matched_ge = True
                    ge_dispatch_receipt_paths.append(dispatch_path.as_posix())
                    break
            if matched_ge:
                ge_dispatch_dirs.append(dispatch_dir)

    ccap_ids: set[str] = set()
    ccap_receipt_paths: list[str] = []
    fallback_count = 0
    for dispatch_dir in ge_dispatch_dirs:
        verifier_dir = dispatch_dir / "verifier"
        if not verifier_dir.exists() or not verifier_dir.is_dir():
            continue
        for path in sorted(verifier_dir.glob("*ccap_receipt_v1.json"), key=lambda row: row.as_posix()):
            receipt_payload = _safe_load_dict(path, errors=errors, context="ccap_receipt_v1")
            if receipt_payload is None:
                fallback_count += 1
                continue
            ccap_id = str(receipt_payload.get("ccap_id", "")).strip()
            if ccap_id.startswith("sha256:"):
                if ccap_id not in ccap_ids:
                    ccap_receipt_paths.append(path.as_posix())
                ccap_ids.add(ccap_id)
            else:
                fallback_count += 1
                ccap_receipt_paths.append(path.as_posix())

    ccap_receipts_u64 = len(ccap_ids) if ccap_ids else fallback_count

    return {
        "schema_version": "V19_GE_DISPATCH_EVIDENCE_v1",
        "runs_root": runs_root.as_posix(),
        "ge_dispatch_u64": int(len(ge_dispatch_dirs)),
        "ccap_receipts_u64": int(ccap_receipts_u64),
        "ge_dispatch_receipt_paths": sorted(set(ge_dispatch_receipt_paths)),
        "ccap_ids": sorted(ccap_ids),
        "ccap_receipt_paths": sorted(set(ccap_receipt_paths)),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Count GE SH1 dispatch + CCAP evidence from v19 run artifacts")
    parser.add_argument("--runs_root", default="runs/v19_full_loop", help="Root directory containing per-tick run dirs")
    args = parser.parse_args()

    runs_root = Path(str(args.runs_root)).expanduser().resolve()
    payload = count_ge_evidence(runs_root=runs_root)

    out_path = runs_root / "V19_GE_DISPATCH_EVIDENCE_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))

    if int(payload.get("ge_dispatch_u64", 0)) <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
