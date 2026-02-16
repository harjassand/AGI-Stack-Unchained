"""Activation and rollback wrapper for omega daemon v18.0."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from orchestrator.common.run_invoker_v1 import run_command

from .omega_common_v1 import (
    canon_hash_obj,
    repo_root,
    require_no_absolute_paths,
    validate_schema,
    write_hashed_json,
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _meta_core_root() -> Path:
    override = str(os.environ.get("OMEGA_META_CORE_ROOT", "")).strip()
    if override:
        return Path(override).resolve()
    return repo_root() / "meta-core"


def _active_manifest_hash(meta_core_root: Path) -> str:
    pointer = meta_core_root / "active" / "ACTIVE_BUNDLE"
    if not pointer.exists() or not pointer.is_file():
        return "sha256:" + ("0" * 64)
    raw = pointer.read_text(encoding="utf-8").strip()
    if _HEX64_RE.fullmatch(raw) is None:
        return "sha256:" + ("0" * 64)
    return f"sha256:{raw}"


def _healthcheck(state_root: Path, suitepack: dict[str, Any]) -> tuple[bool, list[str]]:
    checks = suitepack.get("checks")
    if not isinstance(checks, list):
        return False, ["HEALTHCHECK_FAIL"]
    reasons: list[str] = []
    ok = True
    for row in checks:
        if not isinstance(row, dict):
            ok = False
            continue
        target_rel = str(row.get("target_rel", ""))
        required = bool(row.get("required", True))
        kind = str(row.get("kind", ""))
        target = state_root / target_rel

        passed = True
        if kind == "FILE_EXISTS":
            passed = target.exists()
        elif kind == "HASH_MATCH":
            expected = row.get("expected_hash")
            if not isinstance(expected, str):
                passed = False
            else:
                from .omega_common_v1 import hash_file

                passed = bool(target.exists() and hash_file(target) == expected)
        else:
            passed = False

        if required and not passed:
            ok = False
            reasons.append("HEALTHCHECK_FAIL")

    if ok:
        reasons.append("HEALTHCHECK_PASS")
    return ok, sorted(set(reasons))


def _run_meta_core_apply(*, meta_core_root: Path, out_dir: Path, bundle_dir: Path) -> tuple[dict[str, Any], bool]:
    out_json = out_dir / "meta_core_activation_out_v1.json"
    run_result = run_command(
        cmd=[
            sys.executable,
            str(meta_core_root / "cli" / "meta_core_apply.py"),
            "--meta-core-root",
            str(meta_core_root),
            "--bundle-dir",
            str(bundle_dir.resolve()),
            "--out-json",
            str(out_json.resolve()),
        ],
        cwd=repo_root(),
        output_dir=out_dir / "meta_core_apply",
        extra_env={"META_CORE_ROOT": str(meta_core_root)},
    )
    out_payload: dict[str, Any] = {}
    if out_json.exists():
        try:
            raw = json.loads(out_json.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out_payload = raw
        except Exception:  # noqa: BLE001
            out_payload = {}
    verdict = str(out_payload.get("verdict", ""))
    ok = int(run_result["return_code"]) == 0 and verdict in {"APPLIED", "COMMITTED"}
    return out_payload if isinstance(out_payload, dict) else {}, ok


def _run_meta_core_rollback(*, meta_core_root: Path, out_dir: Path, reason: str) -> tuple[dict[str, Any], bool]:
    out_json = out_dir / "meta_core_rollback_out_v1.json"
    run_result = run_command(
        cmd=[
            sys.executable,
            str(meta_core_root / "cli" / "meta_core_rollback.py"),
            "--meta-core-root",
            str(meta_core_root),
            "--out-json",
            str(out_json.resolve()),
            "--reason",
            reason,
        ],
        cwd=repo_root(),
        output_dir=out_dir / "meta_core_rollback",
        extra_env={"META_CORE_ROOT": str(meta_core_root)},
    )
    out_payload: dict[str, Any] = {}
    if out_json.exists():
        try:
            raw = json.loads(out_json.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out_payload = raw
        except Exception:  # noqa: BLE001
            out_payload = {}
    verdict = str(out_payload.get("verdict", ""))
    ok = int(run_result["return_code"]) == 0 and verdict == "ROLLED_BACK"
    return out_payload if isinstance(out_payload, dict) else {}, ok


def _bundle_parent_hash(bundle_dir: Path) -> str | None:
    path = bundle_dir / "constitution.manifest.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    manifest = raw
    parent = manifest.get("parent_bundle_hash")
    if isinstance(parent, str) and _HEX64_RE.fullmatch(parent):
        return parent
    if parent == "":
        return "0" * 64
    return None


def _binding_matches_after_bundle(*, meta_core_root: Path, after_hash: str, expected_binding_id: str) -> bool:
    if not isinstance(expected_binding_id, str) or _HEX64_RE.fullmatch(expected_binding_id.split(":", 1)[-1]) is None:
        return False
    if not after_hash.startswith("sha256:"):
        return False
    after_hex = after_hash.split(":", 1)[1]
    if _HEX64_RE.fullmatch(after_hex) is None:
        return False

    binding_path = meta_core_root / "store" / "bundles" / after_hex / "omega" / "omega_activation_binding_v1.json"
    if not binding_path.exists() or not binding_path.is_file():
        return False
    try:
        raw = json.loads(binding_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(raw, dict):
        return False
    try:
        validate_schema(raw, "omega_activation_binding_v1")
    except Exception:  # noqa: BLE001
        return False

    expected = expected_binding_id
    actual = str(raw.get("binding_id", ""))
    if actual != expected:
        return False
    no_id = dict(raw)
    no_id.pop("binding_id", None)
    return canon_hash_obj(no_id) == expected


def run_activation(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
    promotion_receipt: dict[str, Any] | None,
    healthcheck_suitepack: dict[str, Any],
    healthcheck_suite_hash: str,
    active_manifest_hash_before: str,
) -> tuple[
    dict[str, Any] | None,
    str | None,
    dict[str, Any] | None,
    str | None,
    str,
]:
    if dispatch_ctx is None or promotion_receipt is None:
        return None, None, None, None, active_manifest_hash_before

    if ((promotion_receipt.get("result") or {}).get("status")) != "PROMOTED":
        return None, None, None, None, active_manifest_hash_before

    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "activation"
    state_root = Path(dispatch_ctx["dispatch_dir"]).parents[1]
    meta_core_root = _meta_core_root()
    mode = str(os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE", "live")).lower()
    allow_simulate = str(os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION", "0")).strip() == "1"
    if mode != "live" and not allow_simulate:
        mode = "live"

    before_hash = _active_manifest_hash(meta_core_root)
    health_ok, health_reasons = _healthcheck(state_root, healthcheck_suitepack)

    activation_ok = False
    binding_ok = True
    after_hash = before_hash
    apply_attempted = False

    live_mode = mode == "live"
    live_ready = live_mode and "meta_core_activation_bundle_dir" in dispatch_ctx
    if not live_mode:
        before_hash = active_manifest_hash_before
        after_hash = str(promotion_receipt.get("active_manifest_hash_after") or before_hash)
        activation_ok = True
    else:
        if not live_ready:
            activation_ok = False
            after_hash = before_hash
        else:
            activation_bundle = Path(str(dispatch_ctx.get("meta_core_activation_bundle_dir", "")))
            active_hex = before_hash.split(":", 1)[1]
            parent_hex = _bundle_parent_hash(activation_bundle) if activation_bundle.exists() else None
            if activation_bundle.exists() and parent_hex is not None and active_hex == parent_hex:
                apply_attempted = True
                _, activation_ok = _run_meta_core_apply(
                    meta_core_root=meta_core_root,
                    out_dir=out_dir,
                    bundle_dir=activation_bundle,
                )
            else:
                activation_ok = False
            after_hash = _active_manifest_hash(meta_core_root)

    changed = after_hash != before_hash
    if live_ready and apply_attempted and activation_ok and changed:
        binding_ok = _binding_matches_after_bundle(
            meta_core_root=meta_core_root,
            after_hash=after_hash,
            expected_binding_id=str(dispatch_ctx.get("activation_binding_id", "")),
        )

    activation_success = bool(activation_ok and binding_ok and health_ok and changed)
    reasons: list[str] = []
    if health_reasons:
        reasons.extend(health_reasons)
    if activation_ok and not changed:
        reasons.append("POINTER_SWAP_FAILED")
    if not activation_ok:
        reasons.append("META_CORE_DENIED")
    if not binding_ok:
        reasons.append("BINDING_MISSING_OR_MISMATCH")
    if not health_ok:
        reasons.append("ROLLBACK_REQUIRED")
    reasons = sorted(set(reasons))

    activation_payload = {
        "schema_version": "omega_activation_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "before_active_manifest_hash": before_hash,
        "after_active_manifest_hash": after_hash,
        "healthcheck_suite_hash": healthcheck_suite_hash,
        "healthcheck_result": "PASS" if health_ok else "FAIL",
        "activation_method": "ATOMIC_POINTER_SWAP",
        "activation_success": bool(activation_success),
        "pass": bool(activation_success),
        "reasons": reasons,
    }
    require_no_absolute_paths(activation_payload)
    _, activation_receipt, activation_hash = write_hashed_json(
        out_dir,
        "omega_activation_receipt_v1.json",
        activation_payload,
        id_field="receipt_id",
    )
    validate_schema(activation_receipt, "omega_activation_receipt_v1")

    if health_ok:
        final_hash = _active_manifest_hash(meta_core_root) if live_ready else after_hash
        return activation_receipt, activation_hash, None, None, final_hash

    # Healthcheck failed after a successful live apply: force rollback and emit rollback receipt.
    if live_ready and apply_attempted and activation_ok and changed:
        _run_meta_core_rollback(
            meta_core_root=meta_core_root,
            out_dir=out_dir,
            reason="OMEGA_HEALTHCHECK_FAIL",
        )
        final_hash = _active_manifest_hash(meta_core_root)
    else:
        final_hash = before_hash
    rollback_payload = {
        "schema_version": "omega_rollback_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "rollback_from_manifest_hash": after_hash,
        "rollback_to_manifest_hash": final_hash,
        "cause": "HEALTHCHECK_FAIL",
        "meta_core_verdict_hash": canon_hash_obj(activation_receipt),
    }
    require_no_absolute_paths(rollback_payload)
    _, rollback_receipt, rollback_hash = write_hashed_json(
        out_dir,
        "omega_rollback_receipt_v1.json",
        rollback_payload,
        id_field="receipt_id",
    )
    validate_schema(rollback_receipt, "omega_rollback_receipt_v1")
    return activation_receipt, activation_hash, rollback_receipt, rollback_hash, final_hash


__all__ = ["run_activation"]
