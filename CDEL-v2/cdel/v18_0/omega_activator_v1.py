"""Activation and rollback wrapper for omega daemon v18.0."""

from __future__ import annotations

import json
import os
import re
import sys
import hashlib
import platform
from pathlib import Path
from typing import Any

from orchestrator.common.run_invoker_v1 import run_command

from .omega_common_v1 import (
    canon_hash_obj,
    load_canon_dict,
    repo_root,
    require_no_absolute_paths,
    validate_schema,
    write_hashed_json,
)
from ..v19_0.common_v1 import validate_schema as validate_schema_v19

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


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file_bytes(path: Path) -> str:
    return _sha256_prefixed(path.read_bytes())


def _native_ext() -> str:
    return ".dylib" if sys.platform == "darwin" else ".so"


def _omega_cache_root() -> Path:
    return repo_root() / ".omega_cache"


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(src.read_bytes())
    os.replace(tmp, dst)


def _is_sha256_prefixed(value: str) -> bool:
    if not value.startswith("sha256:"):
        return False
    return _HEX64_RE.fullmatch(value.split(":", 1)[1]) is not None


def _require_sha256_prefixed(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if not _is_sha256_prefixed(text):
        raise RuntimeError(f"SCHEMA_FAIL:{field}")
    return text


def _verify_hashed_json(path: Path, *, expected_hash: str, schema_name: str) -> dict[str, Any]:
    payload = load_canon_dict(path)
    validate_schema(payload, schema_name)
    if canon_hash_obj(payload) != expected_hash:
        raise RuntimeError("NONDETERMINISTIC")
    return payload


def _resolve_hashed_artifact_path(*, root: Path, suffix: str, digest: str) -> Path:
    hex64 = digest.split(":", 1)[1]
    target = f"sha256_{hex64}.{suffix}"
    candidate = root / target
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()
    matches = sorted(root.rglob(target), key=lambda p: p.as_posix())
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT")
    return matches[0].resolve()


def _resolve_wasm_blob_path(*, root: Path, binary_sha256: str) -> Path:
    hex64 = binary_sha256.split(":", 1)[1]
    target = f"sha256_{hex64}.wasm"
    direct = root / "daemon" / "rsi_knowledge_transpiler_v1" / "state" / "native" / "bin" / target
    if direct.exists() and direct.is_file():
        return direct.resolve()
    matches = sorted(root.rglob(target), key=lambda p: p.as_posix())
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT")
    return matches[0].resolve()


def _shadow_state_root(dispatch_ctx: dict[str, Any]) -> Path:
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        raise RuntimeError("MISSING_STATE_INPUT")
    state_root = Path(state_root_raw).resolve()
    return state_root / "native" / "shadow"


def _normalize_shadow_module_row(row: dict[str, Any]) -> dict[str, Any]:
    op_id = str(row.get("op_id", "")).strip()
    binary_sha256 = str(row.get("binary_sha256", "")).strip()
    runtime_contract_hash = str(row.get("runtime_contract_hash", "")).strip()
    campaign_id = str(row.get("campaign_id", "")).strip() or "rsi_knowledge_transpiler_v1"
    status = "STATUS_SHADOW"
    disabled_key = str(row.get("disabled_key", "")).strip()
    if not disabled_key:
        disabled_key = f"{op_id}|{binary_sha256}"
    portability_status = str(row.get("portability_status", "")).strip()
    if portability_status not in {"RUNNABLE", "PORTABILITY_SKIP_RUN"}:
        portability_status = "PORTABILITY_SKIP_RUN"
    shadow_route_disabled_b = bool(row.get("shadow_route_disabled_b", False))
    shadow_route_disable_reason = row.get("shadow_route_disable_reason")
    if not isinstance(shadow_route_disable_reason, str) or not shadow_route_disable_reason.strip():
        shadow_route_disable_reason = None
    shadow_route_disable_tick_u64 = row.get("shadow_route_disable_tick_u64")
    if isinstance(shadow_route_disable_tick_u64, bool):
        shadow_route_disable_tick_u64 = None
    if not isinstance(shadow_route_disable_tick_u64, int) or shadow_route_disable_tick_u64 < 0:
        shadow_route_disable_tick_u64 = None

    if not shadow_route_disabled_b:
        shadow_route_disable_reason = None
        shadow_route_disable_tick_u64 = None

    return {
        "op_id": op_id,
        "binary_sha256": binary_sha256,
        "runtime_contract_hash": runtime_contract_hash,
        "status": status,
        "campaign_id": campaign_id,
        "portability_status": portability_status,
        "shadow_route_disabled_b": bool(shadow_route_disabled_b),
        "shadow_route_disable_reason": shadow_route_disable_reason,
        "shadow_route_disable_tick_u64": shadow_route_disable_tick_u64,
        "disabled_key": disabled_key,
    }


def _current_host_triple() -> str:
    machine_raw = platform.machine().strip().lower()
    system_raw = platform.system().strip().lower()
    if system_raw == "darwin":
        if machine_raw in {"arm64", "aarch64"}:
            arch = "arm64"
        elif machine_raw in {"x86_64", "amd64"}:
            arch = "x86_64"
        else:
            arch = machine_raw
        return f"{arch}-apple-darwin"
    if system_raw == "linux":
        if machine_raw in {"arm64", "aarch64"}:
            arch = "aarch64"
        elif machine_raw in {"x86_64", "amd64"}:
            arch = "x86_64"
        else:
            arch = machine_raw
        return f"{arch}-unknown-linux-gnu"
    if system_raw == "windows":
        if machine_raw in {"x86_64", "amd64"}:
            arch = "x86_64"
        elif machine_raw in {"arm64", "aarch64"}:
            arch = "aarch64"
        else:
            arch = machine_raw
        return f"{arch}-pc-windows-msvc"
    return f"{machine_raw}-{system_raw}"


def _compute_portability_status(runtime_contract_payload: dict[str, Any]) -> str:
    contract_host = str(runtime_contract_payload.get("host_triple", "")).strip().lower()
    if not contract_host:
        return "PORTABILITY_SKIP_RUN"
    if contract_host == _current_host_triple().lower():
        return "RUNNABLE"
    return "PORTABILITY_SKIP_RUN"


def _read_active_shadow_registry_modules(shadow_dir: Path) -> list[dict[str, Any]]:
    pointer = shadow_dir / "ACTIVE_SHADOW_REGISTRY"
    if not pointer.exists() or not pointer.is_file():
        return []
    digest = pointer.read_text(encoding="utf-8").strip()
    if not _is_sha256_prefixed(digest):
        raise RuntimeError("NONDETERMINISTIC")
    artifact = shadow_dir / f"sha256_{digest.split(':', 1)[1]}.native_shadow_registry_v1.json"
    if not artifact.exists() or not artifact.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    try:
        payload = _verify_hashed_json(
            artifact,
            expected_hash=digest,
            schema_name="native_shadow_registry_v1",
        )
    except RuntimeError:
        payload = load_canon_dict(artifact)
        if canon_hash_obj(payload) != digest:
            raise RuntimeError("NONDETERMINISTIC")
    modules = payload.get("modules")
    if not isinstance(modules, list):
        raise RuntimeError("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in modules:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_shadow_module_row(row)
        if not normalized["op_id"]:
            continue
        if not _is_sha256_prefixed(str(normalized["binary_sha256"])):
            continue
        if not _is_sha256_prefixed(str(normalized["runtime_contract_hash"])):
            continue
        out.append(normalized)
    return out


def _write_shadow_pointer(pointer: Path, digest: str) -> None:
    pointer.parent.mkdir(parents=True, exist_ok=True)
    tmp = pointer.with_name(pointer.name + ".tmp")
    tmp.write_text(f"{digest}\n", encoding="utf-8")
    os.replace(tmp, pointer)


def _install_native_shadow_registry(
    *,
    dispatch_ctx: dict[str, Any],
    tick_u64: int,
    binding_payload: dict[str, Any],
) -> str:
    campaign_id = str(binding_payload.get("campaign_id", "")).strip()
    if campaign_id != "rsi_knowledge_transpiler_v1":
        raise RuntimeError("SCHEMA_FAIL")

    native_module = binding_payload.get("native_module")
    if not isinstance(native_module, dict):
        raise RuntimeError("SCHEMA_FAIL")
    op_id = str(native_module.get("op_id", "")).strip()
    if not op_id:
        raise RuntimeError("SCHEMA_FAIL")
    binary_sha256 = _require_sha256_prefixed(native_module.get("binary_sha256"), field="native_module.binary_sha256")
    runtime_contract_hash = _require_sha256_prefixed(
        binding_payload.get("native_runtime_contract_hash"),
        field="native_runtime_contract_hash",
    )
    _require_sha256_prefixed(
        binding_payload.get("native_healthcheck_vectors_hash"),
        field="native_healthcheck_vectors_hash",
    )
    _require_sha256_prefixed(
        binding_payload.get("native_restricted_ir_hash"),
        field="native_restricted_ir_hash",
    )
    _require_sha256_prefixed(
        binding_payload.get("native_src_merkle_hash"),
        field="native_src_merkle_hash",
    )
    _require_sha256_prefixed(
        binding_payload.get("native_build_proof_hash"),
        field="native_build_proof_hash",
    )

    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)) or not str(subrun_root_raw):
        raise RuntimeError("MISSING_STATE_INPUT")
    subrun_root = Path(subrun_root_raw).resolve()
    if not subrun_root.exists() or not subrun_root.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")

    wasm_path = _resolve_wasm_blob_path(root=subrun_root, binary_sha256=binary_sha256)
    if _hash_file_bytes(wasm_path) != binary_sha256:
        raise RuntimeError("NONDETERMINISTIC")
    runtime_contract_payload = _verify_hashed_json(
        _resolve_hashed_artifact_path(
            root=subrun_root,
            suffix="native_wasm_runtime_contract_v1.json",
            digest=runtime_contract_hash,
        ),
        expected_hash=runtime_contract_hash,
        schema_name="native_wasm_runtime_contract_v1",
    )
    vectors_hash = _require_sha256_prefixed(
        binding_payload.get("native_healthcheck_vectors_hash"),
        field="native_healthcheck_vectors_hash",
    )
    _verify_hashed_json(
        _resolve_hashed_artifact_path(
            root=subrun_root,
            suffix="native_wasm_healthcheck_vectors_v1.json",
            digest=vectors_hash,
        ),
        expected_hash=vectors_hash,
        schema_name="native_wasm_healthcheck_vectors_v1",
    )

    # Optional cache mirror (never source-of-truth).
    cache_blob = _omega_cache_root() / "native_blobs" / f"sha256_{binary_sha256.split(':', 1)[1]}.wasm"
    _atomic_copy(wasm_path, cache_blob)
    if _hash_file_bytes(cache_blob) != binary_sha256:
        raise RuntimeError("NONDETERMINISTIC")

    shadow_dir = _shadow_state_root(dispatch_ctx)
    existing_modules = _read_active_shadow_registry_modules(shadow_dir)
    merged: dict[str, dict[str, Any]] = {}
    for row in existing_modules:
        if isinstance(row, dict):
            row_op_id = str(row.get("op_id", "")).strip()
            if row_op_id:
                merged[row_op_id] = _normalize_shadow_module_row(row)
    disabled_key = f"{op_id}|{binary_sha256}"
    prior_same_key = None
    for row in merged.values():
        if str(row.get("disabled_key", "")).strip() == disabled_key:
            prior_same_key = row
            break
    preserved_disabled = bool((prior_same_key or {}).get("shadow_route_disabled_b", False))
    preserved_reason: str | None
    preserved_tick: int | None
    if preserved_disabled:
        reason_raw = (prior_same_key or {}).get("shadow_route_disable_reason")
        preserved_reason = str(reason_raw).strip() if isinstance(reason_raw, str) and str(reason_raw).strip() else "SHADOW_ROUTE_DISABLED"
        tick_raw = (prior_same_key or {}).get("shadow_route_disable_tick_u64")
        preserved_tick = int(tick_raw) if isinstance(tick_raw, int) and tick_raw >= 0 else int(tick_u64)
    else:
        preserved_reason = None
        preserved_tick = None
    merged[op_id] = {
        "op_id": op_id,
        "binary_sha256": binary_sha256,
        "runtime_contract_hash": runtime_contract_hash,
        "status": "STATUS_SHADOW",
        "campaign_id": campaign_id,
        "portability_status": _compute_portability_status(runtime_contract_payload),
        "shadow_route_disabled_b": bool(preserved_disabled),
        "shadow_route_disable_reason": preserved_reason,
        "shadow_route_disable_tick_u64": preserved_tick,
        "disabled_key": disabled_key,
    }

    state_root = Path(dispatch_ctx["state_root"]).resolve()
    daemon_id = state_root.parent.name if state_root.parent.name else "rsi_omega_daemon_v19_0"
    registry_payload = {
        "schema_version": "native_shadow_registry_v1",
        "registry_id": "sha256:" + ("0" * 64),
        "daemon_id": daemon_id,
        "tick_u64": int(tick_u64),
        "modules": [merged[key] for key in sorted(merged.keys())],
    }
    validate_schema(registry_payload, "native_shadow_registry_v1")
    _, registry_obj, registry_hash = write_hashed_json(
        shadow_dir,
        "native_shadow_registry_v1.json",
        registry_payload,
        id_field="registry_id",
    )
    validate_schema(registry_obj, "native_shadow_registry_v1")
    if canon_hash_obj(registry_obj) != registry_hash:
        raise RuntimeError("NONDETERMINISTIC")
    _write_shadow_pointer(shadow_dir / "ACTIVE_SHADOW_REGISTRY", registry_hash)
    return registry_hash


def _update_active_native_registry(*, op_id: str, native_module: dict[str, Any]) -> None:
    path = _omega_cache_root() / "native_runtime" / "active_registry_v1.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    payload = raw if isinstance(raw, dict) else {}
    ops = payload.get("ops")
    if not isinstance(ops, dict):
        ops = {}
    ops[str(op_id)] = {
        "binary_sha256": str(native_module.get("binary_sha256", "")),
        "platform": str(native_module.get("platform", "")),
        "abi_version_u32": int(native_module.get("abi_version_u32", 1)),
        "abi_kind": str(native_module.get("abi_kind", "BLOBLIST_V1")),
    }
    payload["schema_version"] = "omega_native_active_registry_v1"
    payload["ops"] = ops
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _native_activation_gate(
    *,
    dispatch_ctx: dict[str, Any],
    native_module: dict[str, Any],
    out_dir: Path,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return (gate_result, gate_reason, healthcheck_receipt_or_none)."""

    op_id = str(native_module.get("op_id", "")).strip()
    binary_sha256 = str(native_module.get("binary_sha256", "")).strip()
    if not op_id or not binary_sha256.startswith("sha256:"):
        return "FAIL", "NATIVE_GATE_ABI_MISMATCH", None

    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)) or not str(subrun_root_raw):
        return "FAIL", "NATIVE_GATE_BINARY_MISSING", None
    subrun_root = Path(subrun_root_raw).resolve()
    if not subrun_root.exists() or not subrun_root.is_dir():
        return "FAIL", "NATIVE_GATE_BINARY_MISSING", None

    hex64 = binary_sha256.split(":", 1)[1]
    expected_name = f"sha256_{hex64}{_native_ext()}"
    expected_rel = Path("daemon") / "rsi_omega_native_module_v0_1" / "state" / "native" / "blobs" / expected_name
    candidate = (subrun_root / expected_rel).resolve()
    src_blob: Path | None = None
    if candidate.exists() and candidate.is_file():
        src_blob = candidate
    else:
        matches = sorted(subrun_root.rglob(expected_name), key=lambda p: p.as_posix())
        if len(matches) == 1 and matches[0].is_file():
            src_blob = matches[0].resolve()
    if src_blob is None:
        return "FAIL", "NATIVE_GATE_BINARY_MISSING", None
    if _hash_file_bytes(src_blob) != binary_sha256:
        return "FAIL", "NATIVE_GATE_BINARY_HASH_MISMATCH", None

    cache_blob = _omega_cache_root() / "native_blobs" / expected_name
    _atomic_copy(src_blob, cache_blob)
    if _hash_file_bytes(cache_blob) != binary_sha256:
        return "FAIL", "NATIVE_GATE_BINARY_HASH_MISMATCH", None

    # Healthcheck the installed binary deterministically.
    try:
        from orchestrator.native.native_router_v1 import healthcheck_vectors
    except Exception:
        return "FAIL", "NATIVE_GATE_DLOPEN_FAIL", None
    try:
        receipt = healthcheck_vectors(op_id, cache_blob)
    except OSError:
        return "FAIL", "NATIVE_GATE_DLOPEN_FAIL", None
    except RuntimeError as exc:
        msg = str(exc)
        if "abi" in msg:
            return "FAIL", "NATIVE_GATE_ABI_MISMATCH", None
        if "op_id" in msg:
            return "FAIL", "NATIVE_GATE_OP_ID_MISMATCH", None
        return "FAIL", "NATIVE_GATE_HEALTHCHECK_FAIL", None
    except Exception:
        return "FAIL", "NATIVE_GATE_HEALTHCHECK_FAIL", None

    if str(receipt.get("result", "")) != "PASS":
        # Persist the gate receipt for debugging (activation output only).
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "omega_native_activation_gate_healthcheck_v1.json").write_text(
                json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return "FAIL", "NATIVE_GATE_HEALTHCHECK_FAIL", receipt

    # Gate pass: record active mapping for runtime router.
    _update_active_native_registry(op_id=op_id, native_module=native_module)
    return "PASS", "NATIVE_GATE_PASS", receipt


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


def _run_root_from_state_root(state_root: Path) -> Path:
    try:
        return state_root.parents[2]
    except Exception:  # noqa: BLE001
        return state_root.parent


def _required_extension_source_files(promotion_dir: Path) -> list[Path]:
    suffixes = (
        "kernel_extension_spec_v1.json",
        "benchmark_suite_manifest_v1.json",
        "benchmark_suite_set_v1.json",
    )
    files: list[Path] = []
    seen: set[str] = set()
    for suffix in suffixes:
        plain = (promotion_dir / suffix).resolve()
        if not plain.exists() or not plain.is_file():
            raise RuntimeError("WRITE_FAIL")
        key = plain.as_posix()
        if key not in seen:
            files.append(plain)
            seen.add(key)
        hashed_rows = sorted(
            promotion_dir.glob(f"sha256_*.{suffix}"),
            key=lambda row: row.as_posix(),
        )
        if not hashed_rows:
            raise RuntimeError("WRITE_FAIL")
        for row in hashed_rows:
            resolved = row.resolve()
            rkey = resolved.as_posix()
            if rkey in seen:
                continue
            files.append(resolved)
            seen.add(rkey)
    return files


def _queue_extension_artifacts(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    promotion_receipt: dict[str, Any],
    out_dir: Path,
    state_root: Path,
) -> tuple[dict[str, Any], str]:
    extension_id = _require_sha256_prefixed(
        promotion_receipt.get("promotion_bundle_hash"),
        field="promotion_bundle_hash",
    )
    promotion_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    source_files = _required_extension_source_files(promotion_dir)
    run_root = _run_root_from_state_root(state_root)
    approved_root = (run_root / "approved_extensions" / extension_id).resolve()
    copied_rows: list[dict[str, str]] = []
    for src in source_files:
        dst = (approved_root / src.name).resolve()
        _atomic_copy(src, dst)
        src_hash = _hash_file_bytes(src)
        dst_hash = _hash_file_bytes(dst)
        if src_hash != dst_hash:
            raise RuntimeError("HASH_MISMATCH")
        copied_rows.append(
            {
                "relpath": str(dst.relative_to(approved_root).as_posix()),
                "sha256": str(dst_hash),
            }
        )
    source_run_id = str(run_root.name).strip() or f"tick_{int(tick_u64)}"
    queued_payload = {
        "schema_version": "extension_queued_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "extension_id": extension_id,
        "source_run_id": source_run_id,
        "copied_files": copied_rows,
        "operator_next_step": "RUN append_kernel_extension_v1.py WITH THESE FILES",
        "activation_kind": "ACTIVATION_KIND_EXT_QUEUED",
        "status_code": "ACT_EXT_QUEUED:OK",
    }
    validate_schema_v19(queued_payload, "extension_queued_receipt_v1")
    _, queued_receipt, queued_hash = write_hashed_json(
        out_dir,
        "extension_queued_receipt_v1.json",
        queued_payload,
        id_field="receipt_id",
    )
    validate_schema_v19(queued_receipt, "extension_queued_receipt_v1")
    return queued_receipt, queued_hash


def _run_activation_ext_queued(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    promotion_receipt: dict[str, Any],
    healthcheck_suite_hash: str,
    active_manifest_hash_before: str,
) -> tuple[
    dict[str, Any] | None,
    str | None,
    dict[str, Any] | None,
    str | None,
    str,
]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "activation"
    state_root = Path(dispatch_ctx["dispatch_dir"]).parents[1]
    before_hash = (
        str(active_manifest_hash_before)
        if _is_sha256_prefixed(str(active_manifest_hash_before))
        else _active_manifest_hash(_meta_core_root())
    )
    after_hash = before_hash
    ext_status_code = "ACT_EXT_QUEUED:OK"
    extension_queued_receipt_hash: str | None = None
    try:
        _queued_receipt, extension_queued_receipt_hash = _queue_extension_artifacts(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=promotion_receipt,
            out_dir=out_dir,
            state_root=state_root,
        )
    except Exception as exc:  # noqa: BLE001
        reason_text = str(exc).strip().upper()
        if reason_text == "HASH_MISMATCH":
            ext_status_code = "ACT_EXT_QUEUED:HASH_MISMATCH"
        else:
            ext_status_code = "ACT_EXT_QUEUED:WRITE_FAIL"
        extension_queued_receipt_hash = None
    activation_success = ext_status_code == "ACT_EXT_QUEUED:OK" and _is_sha256_prefixed(
        str(extension_queued_receipt_hash or "")
    )
    reasons = ["EXTENSION_QUEUED", ext_status_code, ("HEALTHCHECK_PASS" if activation_success else "HEALTHCHECK_FAIL")]
    activation_payload = {
        "schema_version": "omega_activation_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "before_active_manifest_hash": before_hash,
        "after_active_manifest_hash": after_hash,
        "healthcheck_suite_hash": healthcheck_suite_hash,
        "healthcheck_result": ("PASS" if activation_success else "FAIL"),
        "activation_method": "ACTIVATION_KIND_EXT_QUEUED",
        "activation_kind": "ACTIVATION_KIND_EXT_QUEUED",
        "activation_success": bool(activation_success),
        "pass": bool(activation_success),
        "native_module": None,
        "native_activation_gate_result": None,
        "native_gate_reason": None,
        "extension_queued_receipt_hash": (
            extension_queued_receipt_hash if _is_sha256_prefixed(str(extension_queued_receipt_hash or "")) else None
        ),
        "extension_queued_status_code": ext_status_code,
        "reasons": sorted(set(str(row) for row in reasons)),
    }
    require_no_absolute_paths(activation_payload)
    _, activation_receipt, activation_hash = write_hashed_json(
        out_dir,
        "omega_activation_receipt_v1.json",
        activation_payload,
        id_field="receipt_id",
    )
    validate_schema(activation_receipt, "omega_activation_receipt_v1")
    return activation_receipt, activation_hash, None, None, after_hash


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

    result_kind = str(promotion_receipt.get("result_kind", "")).strip().upper()
    if result_kind == "PROMOTED_EXT_QUEUED":
        return _run_activation_ext_queued(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=promotion_receipt,
            healthcheck_suite_hash=healthcheck_suite_hash,
            active_manifest_hash_before=active_manifest_hash_before,
        )

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
    native_module: dict[str, Any] | None = None
    native_gate_result: str | None = None
    native_gate_reason: str | None = None
    native_runtime_contract_hash: str | None = None
    native_healthcheck_vectors_hash: str | None = None
    native_restricted_ir_hash: str | None = None
    native_src_merkle_hash: str | None = None
    native_build_proof_hash: str | None = None
    native_shadow_registry_hash: str | None = None

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

    # Optional native activation gate (fail closed).
    binding_path = Path(dispatch_ctx["dispatch_dir"]) / "promotion" / "omega_activation_binding_v1.json"
    if activation_ok and binding_ok and changed and health_ok and binding_path.exists() and binding_path.is_file():
        try:
            binding_payload = json.loads(binding_path.read_text(encoding="utf-8"))
        except Exception:
            binding_payload = None
        if isinstance(binding_payload, dict):
            try:
                validate_schema(binding_payload, "omega_activation_binding_v1")
            except Exception:
                binding_payload = None
        if isinstance(binding_payload, dict):
            candidate = binding_payload.get("native_module")
            if isinstance(candidate, dict):
                native_module = candidate
            campaign_id = str(binding_payload.get("campaign_id", "")).strip()
            if not campaign_id:
                campaign_id = str((dispatch_ctx.get("campaign_entry") or {}).get("campaign_id", "")).strip()
            if campaign_id == "rsi_knowledge_transpiler_v1":
                try:
                    native_runtime_contract_hash = _require_sha256_prefixed(
                        binding_payload.get("native_runtime_contract_hash"),
                        field="native_runtime_contract_hash",
                    )
                    native_healthcheck_vectors_hash = _require_sha256_prefixed(
                        binding_payload.get("native_healthcheck_vectors_hash"),
                        field="native_healthcheck_vectors_hash",
                    )
                    native_restricted_ir_hash = _require_sha256_prefixed(
                        binding_payload.get("native_restricted_ir_hash"),
                        field="native_restricted_ir_hash",
                    )
                    native_src_merkle_hash = _require_sha256_prefixed(
                        binding_payload.get("native_src_merkle_hash"),
                        field="native_src_merkle_hash",
                    )
                    native_build_proof_hash = _require_sha256_prefixed(
                        binding_payload.get("native_build_proof_hash"),
                        field="native_build_proof_hash",
                    )
                    native_shadow_registry_hash = _install_native_shadow_registry(
                        dispatch_ctx=dispatch_ctx,
                        tick_u64=int(tick_u64),
                        binding_payload=binding_payload,
                    )
                    native_gate_result = "SKIP"
                    native_gate_reason = None
                except Exception:
                    health_ok = False
                    health_reasons.append("NATIVE_GATE_FAILED")
                    health_reasons.append("NATIVE_GATE_REQUIRED")
                    native_gate_result = "FAIL"
                    native_gate_reason = "NATIVE_GATE_HEALTHCHECK_FAIL"
            elif isinstance(candidate, dict):
                native_gate_result, native_gate_reason, _ = _native_activation_gate(
                    dispatch_ctx=dispatch_ctx,
                    native_module=native_module,
                    out_dir=out_dir,
                )
                if native_gate_result != "PASS":
                    # Reuse rollback path by forcing health failure.
                    health_ok = False
                    health_reasons.append("NATIVE_GATE_FAILED")
                    health_reasons.append("NATIVE_GATE_REQUIRED")

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
        "activation_kind": "ATOMIC_POINTER_SWAP",
        "activation_success": bool(activation_success),
        "pass": bool(activation_success),
        "native_module": native_module,
        "native_activation_gate_result": native_gate_result,
        "native_gate_reason": native_gate_reason,
        "reasons": reasons,
    }
    if native_runtime_contract_hash is not None:
        activation_payload["native_runtime_contract_hash"] = native_runtime_contract_hash
    if native_healthcheck_vectors_hash is not None:
        activation_payload["native_healthcheck_vectors_hash"] = native_healthcheck_vectors_hash
    if native_restricted_ir_hash is not None:
        activation_payload["native_restricted_ir_hash"] = native_restricted_ir_hash
    if native_src_merkle_hash is not None:
        activation_payload["native_src_merkle_hash"] = native_src_merkle_hash
    if native_build_proof_hash is not None:
        activation_payload["native_build_proof_hash"] = native_build_proof_hash
    if native_shadow_registry_hash is not None:
        activation_payload["native_shadow_registry_hash"] = native_shadow_registry_hash
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
