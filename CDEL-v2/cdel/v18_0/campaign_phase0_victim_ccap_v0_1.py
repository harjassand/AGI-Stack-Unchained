"""Phase0 victim CCAP campaign v0.1.

Emits exactly 2 CCAP candidates + 2 CCAP promotion bundles whose deterministic ordering mismatches:
- lexicographically-first CCAP id != CCAP id referenced by lexicographically-first promotion bundle hash

This guarantees `CCAP_RECEIPT_MISSING_OR_MISMATCH` when the subverifier is forced into legacy CCAP discovery.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .authority.authority_hash_v1 import auth_hash, load_authority_pins
from .ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id
from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_relpath, validate_schema


_PACK_SCHEMA = "rsi_omega_phase0_victim_ccap_pack_v0_1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _first_build_recipe_id(repo_root: Path) -> str:
    payload = load_canon_dict(repo_root / "authority" / "build_recipes" / "build_recipes_v1.json", reason="MISSING_STATE_INPUT")
    if payload.get("schema_version") != "build_recipes_v1":
        fail("SCHEMA_FAIL")
    recipes = payload.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        fail("SCHEMA_FAIL")
    ids = sorted(str(row.get("recipe_id", "")).strip() for row in recipes if isinstance(row, dict))
    ids = [row for row in ids if row.startswith("sha256:")]
    if not ids:
        fail("SCHEMA_FAIL")
    return ids[0]


def _patch_append_nonce(*, relpath: str, base_text: str, nonce: int) -> bytes:
    # Use newline-free line sequences; `difflib` outputs hunk lines directly, so embedded newlines
    # would corrupt the patch stream (git apply is strict).
    if base_text and base_text.endswith("\n"):
        base_text = base_text[:-1]
    old_lines = base_text.splitlines()
    new_lines = list(old_lines) + [f"nonce={int(nonce)}"]
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            lineterm="",
        )
    )
    patch_text = "\n".join([f"diff --git a/{relpath} b/{relpath}", *diff_lines]) + "\n"
    return patch_text.encode("utf-8")


@dataclass(frozen=True)
class _Candidate:
    nonce: int
    patch_bytes: bytes
    patch_hex: str
    ccap: dict[str, Any]
    ccap_id: str
    ccap_relpath: str
    patch_relpath: str
    bundle: dict[str, Any]
    bundle_hash: str


def _candidate(
    *,
    repo_root: Path,
    pins: dict[str, Any],
    base_tree_id: str,
    build_recipe_id: str,
    anchor_relpath: str,
    anchor_text: str,
    nonce: int,
) -> _Candidate:
    patch_bytes = _patch_append_nonce(relpath=anchor_relpath, base_text=anchor_text, nonce=nonce)
    patch_hex = hashlib.sha256(patch_bytes).hexdigest()
    patch_blob_id = f"sha256:{patch_hex}"

    ccap: dict[str, Any] = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": str(pins["active_dsbx_profile_ids"][0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(pins["active_op_pool_ids"][0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {"build_recipe_id": build_recipe_id, "build_targets": [], "artifact_bindings": {}},
        "eval": {
            "stages": [{"stage_name": "REALIZE"}, {"stage_name": "SCORE"}, {"stage_name": "FINAL_AUDIT"}],
            "final_suite_id": "sha256:" + ("1" * 64),
        },
        "budgets": {
            "cpu_ms_max": 60_000,
            "wall_ms_max": 60_000,
            "mem_mb_max": 4096,
            # CCAP EK runner measures on-disk footprint of the ek_run workspace.
            # Phase0 subruns can exceed 512MB due to repo snapshot size.
            "disk_mb_max": 8192,
            "fds_max": 256,
            "procs_max": 128,
            "threads_max": 256,
            "net": "forbidden",
        },
    }
    validate_schema(ccap, "ccap_v1")

    ccap_id = ccap_payload_id(ccap)
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    patch_relpath = f"ccap/blobs/sha256_{patch_hex}.patch"

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_relpath,
        "patch_relpath": patch_relpath,
        "touched_paths": [ccap_relpath, patch_relpath],
        "activation_key": ccap_id,
    }
    validate_schema(bundle, "omega_promotion_bundle_ccap_v1")
    bundle_hash = canon_hash_obj(bundle)

    return _Candidate(
        nonce=int(nonce),
        patch_bytes=patch_bytes,
        patch_hex=patch_hex,
        ccap=ccap,
        ccap_id=ccap_id,
        ccap_relpath=ccap_relpath,
        patch_relpath=patch_relpath,
        bundle=bundle,
        bundle_hash=bundle_hash,
    )


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    repo_root = _repo_root()
    pack = load_canon_dict(campaign_pack)
    if str(pack.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")

    anchor_relpath = require_relpath(pack.get("anchor_relpath"))
    anchor_path = (repo_root / anchor_relpath).resolve()
    if not anchor_path.exists() or not anchor_path.is_file():
        fail("MISSING_STATE_INPUT")
    anchor_text = anchor_path.read_text(encoding="utf-8")

    pins = load_authority_pins(repo_root)
    base_tree_id = compute_repo_base_tree_id(repo_root)
    build_recipe_id = _first_build_recipe_id(repo_root)

    min_ccap: _Candidate | None = None
    min_bundle: _Candidate | None = None
    max_attempts = 50_000
    for nonce in range(max_attempts):
        cand = _candidate(
            repo_root=repo_root,
            pins=pins,
            base_tree_id=base_tree_id,
            build_recipe_id=build_recipe_id,
            anchor_relpath=anchor_relpath,
            anchor_text=anchor_text,
            nonce=nonce,
        )
        if min_ccap is None or cand.ccap_id < min_ccap.ccap_id:
            min_ccap = cand
        if min_bundle is None or cand.bundle_hash < min_bundle.bundle_hash:
            min_bundle = cand
        if min_ccap is not None and min_bundle is not None and min_ccap.ccap_id != min_bundle.ccap_id:
            break

    if min_ccap is None or min_bundle is None or min_ccap.ccap_id == min_bundle.ccap_id:
        fail("NONDETERMINISTIC")

    selected = [min_ccap, min_bundle]
    out_dir = out_dir.resolve()
    (out_dir / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)
    (out_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (out_dir / "ccap").mkdir(parents=True, exist_ok=True)

    for cand in selected:
        (out_dir / cand.patch_relpath).parent.mkdir(parents=True, exist_ok=True)
        (out_dir / cand.patch_relpath).write_bytes(cand.patch_bytes)
        write_canon_json(out_dir / cand.ccap_relpath, cand.ccap)

        bundle_hash = cand.bundle_hash
        bundle_path = out_dir / "promotion" / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json"
        write_canon_json(bundle_path, cand.bundle)

    # Emit a small deterministic summary (useful when debugging locally).
    summary = {
        "schema_version": "phase0_victim_ccap_summary_v0_1",
        "selected": [
            {"nonce": selected[0].nonce, "ccap_id": selected[0].ccap_id, "bundle_hash": selected[0].bundle_hash},
            {"nonce": selected[1].nonce, "ccap_id": selected[1].ccap_id, "bundle_hash": selected[1].bundle_hash},
        ],
        "min_ccap_id": min_ccap.ccap_id,
        "min_bundle_hash": min_bundle.bundle_hash,
        "base_tree_id": base_tree_id,
        "anchor_relpath": anchor_relpath,
    }
    write_canon_json(out_dir / "phase0_victim_ccap_summary_v0_1.json", summary)

    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="campaign_phase0_victim_ccap_v0_1")
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

