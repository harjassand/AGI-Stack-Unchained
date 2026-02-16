"""Run GE SH-1 v0.3 optimizer and emit CCAP promotion bundles (staged, disabled by default)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, repo_root, validate_schema


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1":
        fail("SCHEMA_FAIL")
    return payload


def _discover_runs_root(out_dir: Path) -> Path | None:
    current = out_dir.resolve()
    for parent in [current, *current.parents]:
        if parent.name == "runs":
            return parent
    return None


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()

    ge_config_rel = str(pack.get("ge_config_path", "tools/genesis_engine/config/ge_config_v1.json")).strip()
    authority_rel = str(pack.get("authority_pins_path", "authority/authority_pins_v1.json")).strip()
    model_id = str(pack.get("model_id", "ge-v0_3")).strip() or "ge-v0_3"
    max_ccaps = max(1, min(8, int(pack.get("max_ccaps", 1))))

    tool_path = root / "tools" / "genesis_engine" / "ge_symbiotic_optimizer_v0_3.py"
    if not tool_path.exists() or not tool_path.is_file():
        fail("MISSING_STATE_INPUT")

    recent_runs_root = _discover_runs_root(out_dir)
    ge_state_root = str(os.environ.get("OMEGA_GE_STATE_ROOT", "")).strip()
    seed_u64 = max(0, int(str(os.environ.get("OMEGA_RUN_SEED_U64", "0")).strip() or "0"))

    cmd = [
        sys.executable,
        str(tool_path),
        "--subrun_out_dir",
        str(out_dir.resolve()),
        "--ge_config_path",
        ge_config_rel,
        "--authority_pins_path",
        authority_rel,
        "--recent_runs_root",
        str(recent_runs_root.resolve()) if recent_runs_root is not None else "",
        "--ge_state_root",
        ge_state_root,
        "--seed",
        str(seed_u64),
        "--model_id",
        model_id,
        "--max_ccaps",
        str(max_ccaps),
    ]

    run_result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if int(run_result.returncode) != 0:
        fail("VERIFY_ERROR")

    summary_path = out_dir / "ge_symbiotic_optimizer_summary_v0_3.json"
    if not summary_path.exists() or not summary_path.is_file():
        fail("MISSING_STATE_INPUT")
    summary = load_canon_dict(summary_path)

    ccaps = summary.get("ccaps")
    if not isinstance(ccaps, list):
        fail("SCHEMA_FAIL")

    promotion_dir = out_dir.resolve() / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    for row in ccaps:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ccap_id = str(row.get("ccap_id", "")).strip()
        ccap_relpath = str(row.get("ccap_relpath", "")).strip()
        patch_relpath = str(row.get("patch_relpath", "")).strip()
        if not ccap_id or not ccap_relpath or not patch_relpath:
            fail("SCHEMA_FAIL")

        bundle = {
            "schema_version": "omega_promotion_bundle_ccap_v1",
            "ccap_id": ccap_id,
            "ccap_relpath": ccap_relpath,
            "patch_relpath": patch_relpath,
            "activation_key": ccap_id,
            "touched_paths": [ccap_relpath, patch_relpath],
        }
        validate_schema(bundle, "omega_promotion_bundle_ccap_v1")
        bundle_hash = canon_hash_obj(bundle)
        bundle_path = promotion_dir / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
        write_canon_json(bundle_path, bundle)

    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="campaign_ge_symbiotic_optimizer_sh1_v0_1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run(
        campaign_pack=Path(args.campaign_pack).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )


if __name__ == "__main__":
    main()
