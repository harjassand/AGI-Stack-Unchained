#!/usr/bin/env python3
"""Materialize promoted micdrop solver patches into the workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SOLVER_RELPATH = "tools/omega/agi_micdrop_solver_v1.py"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _tick_from_path(path: Path) -> int:
    match = re.search(r"/tick_(\d+)/", path.as_posix())
    if match is None:
        return 0
    return int(match.group(1))


def _iter_promoted_solver_patches(ticks_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    glob = "tick_*/daemon/rsi_omega_daemon_v19_0/state/dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json"
    for receipt_path in sorted(ticks_root.glob(glob), key=lambda p: p.as_posix()):
        receipt = _load_json(receipt_path)
        result = receipt.get("result")
        status = str((result or {}).get("status", "")).strip().upper() if isinstance(result, dict) else ""
        if status != "PROMOTED":
            continue

        dispatch_dir = receipt_path.parents[1]
        activation_paths = sorted((dispatch_dir / "activation").glob("sha256_*.omega_activation_receipt_v1.json"), key=lambda p: p.as_posix())
        if not activation_paths:
            continue
        activation_payload = _load_json(activation_paths[-1])
        if not bool(activation_payload.get("activation_success", False)):
            continue

        replay_binding = receipt.get("replay_binding_v1")
        if not isinstance(replay_binding, dict):
            continue
        replay_rel = str(replay_binding.get("replay_state_dir_relpath", "")).strip()
        bundle_id = str(receipt.get("promotion_bundle_hash", "")).strip()
        if not replay_rel or not bundle_id.startswith("sha256:"):
            continue

        state_root = dispatch_dir.parents[1]
        bundle_path = state_root / replay_rel / "promotion" / f"sha256_{bundle_id.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
        if not bundle_path.exists() or not bundle_path.is_file():
            continue
        bundle_payload = _load_json(bundle_path)

        touched = bundle_payload.get("touched_paths")
        touched_paths = [str(item).strip() for item in touched if str(item).strip()] if isinstance(touched, list) else []
        if SOLVER_RELPATH not in touched_paths:
            continue

        patch_rel = str(bundle_payload.get("patch_relpath", "")).strip()
        if not patch_rel:
            continue
        patch_path = (state_root / replay_rel / patch_rel).resolve()
        if not patch_path.exists() or not patch_path.is_file():
            continue

        patch_sha = _sha256_file(patch_path)
        patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
        feature_match = re.search(r"# MICDROP_FEATURE:([A-Z0-9_]+)", patch_text)
        rows.append(
            {
                "tick_u64": _tick_from_path(receipt_path),
                "receipt_relpath": receipt_path.relative_to(REPO_ROOT).as_posix(),
                "ccap_id": str(bundle_payload.get("ccap_id", "")).strip(),
                "patch_relpath": patch_path.relative_to(REPO_ROOT).as_posix(),
                "patch_sha256": patch_sha,
                "feature_id": feature_match.group(1) if feature_match else "",
                "touched_paths": touched_paths,
            }
        )

    rows.sort(key=lambda row: (int(row["tick_u64"]), str(row["patch_sha256"]), str(row["receipt_relpath"])))
    return rows


def _run_git_apply(path: Path) -> bool:
    check = subprocess.run(["git", "apply", "--check", path.as_posix()], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if check.returncode != 0:
        return False
    apply_run = subprocess.run(["git", "apply", path.as_posix()], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if apply_run.returncode != 0:
        raise RuntimeError(f"git apply failed for {path.as_posix()}: {apply_run.stderr.strip()}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(prog="micdrop_materialize_promotions_v1")
    parser.add_argument("--ticks_root", default="runs/micdrop_ticks")
    args = parser.parse_args()

    ticks_root = (REPO_ROOT / str(args.ticks_root)).resolve()
    if not ticks_root.exists() or not ticks_root.is_dir():
        raise RuntimeError(f"ticks root missing: {ticks_root.as_posix()}")

    solver_path = (REPO_ROOT / SOLVER_RELPATH).resolve()
    before_sha = _sha256_file(solver_path)
    solver_text = solver_path.read_text(encoding="utf-8")

    promoted = _iter_promoted_solver_patches(ticks_root=ticks_root)
    seen_patch_ids: set[str] = set()
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in promoted:
        patch_sha = str(row["patch_sha256"])
        if patch_sha in seen_patch_ids:
            continue
        seen_patch_ids.add(patch_sha)

        marker = f"# MICDROP_FEATURE:{row['feature_id']}" if str(row["feature_id"]).strip() else ""
        if marker and marker in solver_text:
            skipped.append(dict(row))
            continue

        patch_path = (REPO_ROOT / str(row["patch_relpath"])).resolve()
        if not _run_git_apply(path=patch_path):
            skipped.append(dict(row))
            continue

        solver_text = solver_path.read_text(encoding="utf-8")
        applied.append(dict(row))

    after_sha = _sha256_file(solver_path)
    summary = {
        "schema_version": "MICDROP_MATERIALIZE_PROMOTIONS_SUMMARY_v1",
        "ticks_root": ticks_root.relative_to(REPO_ROOT).as_posix(),
        "promoted_solver_patches_u64": len(promoted),
        "applied_solver_patches_u64": len(applied),
        "skipped_solver_patches_u64": len(skipped),
        "solver_sha256_before": before_sha,
        "solver_sha256_after": after_sha,
        "applied": applied,
        "skipped": skipped,
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
