"""Run GE SH-1 v0.3 optimizer and emit CCAP promotion bundles (staged, disabled by default)."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, repo_root, validate_schema

_DEFAULT_BACKLOG_REGISTRY_REL = "campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json"
_DEFAULT_BACKLOG_GOAL_QUEUE_REL = "campaigns/rsi_omega_daemon_v19_0_super_unified/goals/omega_goal_queue_v1.json"
_DEFAULT_CAPABILITY_BACKLOG: tuple[str, ...] = (
    "RSI_OMEGA_SELF_OPTIMIZE_CORE",
    "RSI_OMEGA_SKILL_TRANSFER",
    "RSI_OMEGA_SKILL_ONTOLOGY",
    "RSI_OMEGA_SKILL_EFF_FLYWHEEL",
    "RSI_OMEGA_SKILL_THERMO",
    "RSI_OMEGA_SKILL_PERSISTENCE",
    "RSI_OMEGA_SKILL_ALIGNMENT",
    "RSI_OMEGA_SKILL_BOUNDLESS_MATH",
    "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE",
    "RSI_OMEGA_SKILL_SWARM",
    "RSI_OMEGA_SKILL_MODEL_GENESIS",
    "RSI_MODEL_GENESIS_V10",
    "RSI_EUDRS_U_INDEX_REBUILD",
    "RSI_EUDRS_U_ONTOLOGY_UPDATE",
    "RSI_EUDRS_U_EVAL_CAC",
)


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


def _canonical_json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sanitize_goal_id_piece(capability_id: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(capability_id).strip())
    while "__" in out:
        out = out.replace("__", "_")
    out = out.strip("_")
    return out or "capability"


def _build_goal_id(capability_id: str, ordinal_u64: int) -> str:
    return f"goal_cap_backlog_{_sanitize_goal_id_piece(capability_id)}_{int(ordinal_u64):04d}"


def _build_unified_patch(*, relpath: str, before: str, after: str) -> str:
    if before == after:
        return ""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    rows = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            lineterm="",
        )
    )
    if not rows:
        return ""
    return "\n".join(rows) + "\n"


def _resolve_capability_backlog(pack: dict[str, Any]) -> list[str]:
    rows = pack.get("capability_backlog")
    if not isinstance(rows, list):
        return list(_DEFAULT_CAPABILITY_BACKLOG)
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        cap_id = str(row).strip()
        if not cap_id or cap_id in seen:
            continue
        seen.add(cap_id)
        out.append(cap_id)
    return out


def _resolve_backlog_relpaths(pack: dict[str, Any]) -> tuple[str, str]:
    registry_rel = str(pack.get("backlog_registry_rel", _DEFAULT_BACKLOG_REGISTRY_REL)).strip() or _DEFAULT_BACKLOG_REGISTRY_REL
    goal_queue_rel = (
        str(pack.get("backlog_goal_queue_rel", _DEFAULT_BACKLOG_GOAL_QUEUE_REL)).strip() or _DEFAULT_BACKLOG_GOAL_QUEUE_REL
    )
    return registry_rel, goal_queue_rel


def _validate_goal_queue_payload_minimal(goal_queue_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if str(goal_queue_payload.get("schema_version", "")).strip() != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    goals = goal_queue_payload.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if not goal_id or not capability_id or not status:
            fail("SCHEMA_FAIL")
        out.append(row)
    return out


def _patch_touches_relpath(*, patch_bytes: bytes, relpath: str) -> bool:
    target = f"+++ b/{str(relpath).strip().replace('\\', '/')}"
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.split("\t", 1)[0].strip()
        if line == target:
            return True
    return False


def _build_capability_backlog_patch(*, root: Path, pack: dict[str, Any], skip_registry_diff: bool = False) -> bytes:
    backlog = _resolve_capability_backlog(pack)
    if not backlog:
        return b""

    registry_rel, goal_queue_rel = _resolve_backlog_relpaths(pack)
    registry_path = root / registry_rel
    goal_queue_path = root / goal_queue_rel
    if not registry_path.exists() or not registry_path.is_file():
        return b""
    if not goal_queue_path.exists() or not goal_queue_path.is_file():
        return b""

    registry_before = registry_path.read_text(encoding="utf-8")
    goal_queue_before = goal_queue_path.read_text(encoding="utf-8")

    registry_payload = load_canon_dict(registry_path)
    goal_queue_payload = load_canon_dict(goal_queue_path)
    validate_schema(registry_payload, "omega_capability_registry_v2")
    # Some v18 installs do not ship a dedicated omega_goal_queue_v1 schema file.
    # Keep deterministic shape checks so backlog injection still runs fail-closed.
    try:
        validate_schema(goal_queue_payload, "omega_goal_queue_v1")
    except Exception:  # noqa: BLE001
        _validate_goal_queue_payload_minimal(goal_queue_payload)

    capabilities = registry_payload.get("capabilities")
    goals = goal_queue_payload.get("goals")
    if not isinstance(capabilities, list) or not isinstance(goals, list):
        fail("SCHEMA_FAIL")

    by_capability_id: dict[str, dict[str, Any]] = {}
    for row in capabilities:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        cap_id = str(row.get("capability_id", "")).strip()
        if cap_id:
            by_capability_id[cap_id] = row

    newly_enabled: list[str] = []
    for cap_id in backlog:
        row = by_capability_id.get(cap_id)
        if row is None:
            continue
        if bool(row.get("enabled", False)):
            continue
        row["enabled"] = True
        newly_enabled.append(cap_id)

    if not newly_enabled:
        return b""

    existing_goal_ids: set[str] = set()
    existing_goal_caps: set[str] = set()
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        cap_id = str(row.get("capability_id", "")).strip()
        if goal_id:
            existing_goal_ids.add(goal_id)
        if cap_id:
            existing_goal_caps.add(cap_id)

    for cap_id in newly_enabled:
        if cap_id in existing_goal_caps:
            continue
        ordinal_u64 = 1
        goal_id = _build_goal_id(cap_id, ordinal_u64)
        while goal_id in existing_goal_ids:
            ordinal_u64 += 1
            goal_id = _build_goal_id(cap_id, ordinal_u64)
        goals.append(
            {
                "capability_id": cap_id,
                "goal_id": goal_id,
                "status": "PENDING",
            }
        )
        existing_goal_ids.add(goal_id)
        existing_goal_caps.add(cap_id)

    registry_after = _canonical_json_text(registry_payload)
    goal_queue_after = _canonical_json_text(goal_queue_payload)

    patch_chunks: list[str] = []
    patch_registry = _build_unified_patch(relpath=registry_rel, before=registry_before, after=registry_after)
    if patch_registry and not skip_registry_diff:
        patch_chunks.append(patch_registry)
    patch_goals = _build_unified_patch(relpath=goal_queue_rel, before=goal_queue_before, after=goal_queue_after)
    if patch_goals:
        patch_chunks.append(patch_goals)
    if not patch_chunks:
        return b""
    return "".join(patch_chunks).encode("utf-8")


def _inject_capability_backlog_patch(
    *,
    root: Path,
    out_dir: Path,
    pack: dict[str, Any],
    ccap_id: str,
    ccap_relpath: str,
    patch_relpath: str,
) -> tuple[str, str, str, bool]:
    backlog_patch_bytes = _build_capability_backlog_patch(root=root, pack=pack)
    if not backlog_patch_bytes:
        return ccap_id, ccap_relpath, patch_relpath, False

    ccap_path = out_dir / ccap_relpath
    patch_path = out_dir / patch_relpath
    if not ccap_path.exists() or not ccap_path.is_file():
        fail("MISSING_STATE_INPUT")
    if not patch_path.exists() or not patch_path.is_file():
        fail("MISSING_STATE_INPUT")

    ccap_payload = load_canon_dict(ccap_path)
    validate_schema(ccap_payload, "ccap_v1")
    payload = ccap_payload.get("payload")
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if str(payload.get("kind", "")).strip() != "PATCH":
        return ccap_id, ccap_relpath, patch_relpath, False

    original_patch = patch_path.read_bytes()
    registry_rel, _goal_queue_rel = _resolve_backlog_relpaths(pack)
    skip_registry_diff = _patch_touches_relpath(patch_bytes=original_patch, relpath=registry_rel)
    backlog_patch_bytes = _build_capability_backlog_patch(root=root, pack=pack, skip_registry_diff=skip_registry_diff)
    if not backlog_patch_bytes:
        return ccap_id, ccap_relpath, patch_relpath, False

    merged_patch = original_patch
    if merged_patch and not merged_patch.endswith(b"\n"):
        merged_patch += b"\n"
    merged_patch += backlog_patch_bytes

    patch_hex = hashlib.sha256(merged_patch).hexdigest()
    next_patch_relpath = f"ccap/blobs/sha256_{patch_hex}.patch"
    next_patch_path = out_dir / next_patch_relpath
    next_patch_path.parent.mkdir(parents=True, exist_ok=True)
    next_patch_path.write_bytes(merged_patch)

    payload["patch_blob_id"] = f"sha256:{patch_hex}"
    ccap_payload["payload"] = payload
    validate_schema(ccap_payload, "ccap_v1")
    next_ccap_id = canon_hash_obj(payload)
    next_ccap_relpath = f"ccap/sha256_{next_ccap_id.split(':', 1)[1]}.ccap_v1.json"
    next_ccap_path = out_dir / next_ccap_relpath
    next_ccap_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(next_ccap_path, ccap_payload)
    return next_ccap_id, next_ccap_relpath, next_patch_relpath, True


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()

    ge_config_rel = str(pack.get("ge_config_path", "tools/genesis_engine/config/ge_config_v1.json")).strip()
    authority_rel = str(pack.get("authority_pins_path", "authority/authority_pins_v1.json")).strip()
    model_id = str(pack.get("model_id", "ge-v0_3")).strip() or "ge-v0_3"
    max_ccaps = max(1, min(8, int(pack.get("max_ccaps", 1))))
    enforce_deterministic_compilation = False

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

    run_env = os.environ.copy()
    run_env["OMEGA_ENFORCE_DETERMINISTIC_COMPILATION"] = "1" if enforce_deterministic_compilation else "0"

    run_result = subprocess.run(
        cmd,
        cwd=root,
        env=run_env,
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

    backlog_injected = False
    for row in ccaps:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ccap_id = str(row.get("ccap_id", "")).strip()
        ccap_relpath = str(row.get("ccap_relpath", "")).strip()
        patch_relpath = str(row.get("patch_relpath", "")).strip()
        if not ccap_id or not ccap_relpath or not patch_relpath:
            fail("SCHEMA_FAIL")

        if not backlog_injected:
            ccap_id, ccap_relpath, patch_relpath, backlog_injected = _inject_capability_backlog_patch(
                root=root,
                out_dir=out_dir.resolve(),
                pack=pack,
                ccap_id=ccap_id,
                ccap_relpath=ccap_relpath,
                patch_relpath=patch_relpath,
            )

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
