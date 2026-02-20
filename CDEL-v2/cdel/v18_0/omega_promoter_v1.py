"""Subverifier + promotion wrapper for omega daemon v18.0."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.common.run_invoker_v1 import run_command, run_module

from ..v1_7r.canon import canon_bytes, write_canon_json
from .ccap_runtime_v1 import (
    apply_patch_bytes,
    ccap_payload_id,
    compute_repo_base_tree_id,
    compute_workspace_tree_id,
    materialize_repo_snapshot,
    normalize_subrun_relpath,
)
from .omega_allowlists_v1 import is_path_allowed, is_path_forbidden
from .omega_common_v1 import (
    OmegaV18Error,
    canon_hash_obj,
    hash_file,
    hash_bytes,
    load_canon_dict,
    repo_root,
    resolve_execution_mode,
    require_no_absolute_paths,
    require_relpath,
    tree_hash,
    validate_schema,
    write_hashed_json,
)
from .omega_promotion_bundle_v1 import extract_touched_paths, load_bundle
from .omega_test_plan_v1 import campaign_requires_test_plan_receipt, load_test_plan_receipt

_HEX64 = set("0123456789abcdef")
_V14_VERIFIER_MODULE = "cdel.v14_0.verify_rsi_sas_system_v1"
_V16_1_METASEARCH_VERIFIER_MODULE = "cdel.v16_1.verify_rsi_sas_metasearch_v16_1"
_CCAP_VERIFIER_MODULE = "cdel.v18_0.verify_ccap_v1"
_V10_MODEL_GENESIS_VERIFIER_MODULE = "cdel.v10_0.verify_rsi_model_genesis_v1"
_REPLAY_REPO_ROOT_VERIFIER_MODULES = {
    _V14_VERIFIER_MODULE,
    _V16_1_METASEARCH_VERIFIER_MODULE,
}
_SHA256_ZERO = "sha256:" + ("0" * 64)
_SUBVERIFIER_REASON_CODES = {
    "SCHEMA_FAIL",
    "MISSING_STATE_INPUT",
    "NONDETERMINISTIC",
    "MODE_UNSUPPORTED",
    "VERIFY_ERROR",
    "UNKNOWN",
}
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_SUBVERIFIER_STATE_ARG_BY_MODULE = {
    "cdel.v12_0.verify_rsi_sas_code_v1": "--sas_code_state_dir",
    _V10_MODEL_GENESIS_VERIFIER_MODULE: "--smg_state_dir",
}


def _normalize_subverifier_reason_code(reason: str | None) -> str | None:
    if reason is None:
        return None
    if reason in _SUBVERIFIER_REASON_CODES:
        return reason
    return "VERIFY_ERROR"


def _state_arg_for_verifier(verifier_module: str) -> str:
    return str(_SUBVERIFIER_STATE_ARG_BY_MODULE.get(verifier_module, "--state_dir"))


def _is_hex64(value: str) -> bool:
    return len(value) == 64 and all(ch in _HEX64 for ch in value)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _discover_ccap_relpath(subrun_root: Path) -> str | None:
    rows = sorted((subrun_root / "ccap").glob("sha256_*.ccap_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    return rows[0].relative_to(subrun_root).as_posix()


def _load_ccap_receipt_for_id(*, verifier_dir: Path, ccap_id: str) -> dict[str, Any] | None:
    rows = sorted(verifier_dir.glob("sha256_*.ccap_receipt_v1.json"), key=lambda row: row.as_posix())
    plain = verifier_dir / "ccap_receipt_v1.json"
    if plain.exists() and plain.is_file():
        rows.append(plain)
    for path in rows:
        payload = load_canon_dict(path)
        validate_schema(payload, "ccap_receipt_v1")
        if str(payload.get("ccap_id", "")) == ccap_id:
            return payload
    return None


def _load_realized_receipt_for_id(*, subrun_root: Path, ccap_id: str) -> dict[str, Any] | None:
    realized_dir = subrun_root / "ccap" / "realized"
    rows = sorted(realized_dir.glob("sha256_*.realized_capsule_receipt_v1.json"), key=lambda row: row.as_posix())
    plain = realized_dir / "realized_capsule_receipt_v1.json"
    if plain.exists() and plain.is_file():
        rows.append(plain)
    for path in rows:
        payload = load_canon_dict(path)
        validate_schema(payload, "realized_capsule_receipt_v1")
        if str(payload.get("ccap_id", "")) == ccap_id:
            return payload
    return None


def _persist_ccap_receipt(*, verifier_dir: Path, receipt: dict[str, Any]) -> None:
    write_hashed_json(verifier_dir, "ccap_receipt_v1.json", receipt)
    write_canon_json(verifier_dir / "ccap_receipt_v1.json", receipt)


def _load_ccap_receipt_for_id_with_fallback(
    *,
    verifier_dir: Path,
    subrun_root: Path,
    ccap_id: str,
) -> dict[str, Any] | None:
    receipt = _load_ccap_receipt_for_id(verifier_dir=verifier_dir, ccap_id=ccap_id)
    if receipt is not None:
        return receipt

    legacy_verifier_dir = (subrun_root / "verifier").resolve()
    if legacy_verifier_dir == verifier_dir.resolve():
        return None
    receipt = _load_ccap_receipt_for_id(verifier_dir=legacy_verifier_dir, ccap_id=ccap_id)
    if receipt is None:
        return None
    _persist_ccap_receipt(verifier_dir=verifier_dir, receipt=receipt)
    return receipt


def _path_contains_omega_cache(path_rel: str) -> bool:
    return ".omega_cache" in Path(path_rel).parts


def _tree_hash_ccap_subrun_for_receipt(subrun_root: Path) -> str:
    """Hash a CCAP subrun for subverifier receipt purposes without traversing EK workspaces.

    `ccap/ek_runs/**` can contain a full repo snapshot (very large) and may include symlinks
    (for example `tools/omega/verifier_corpus_v1/*/state`). Those are legitimate in the repo
    but would make `tree_hash()` fail-closed and/or be prohibitively expensive.

    This hash is used only for receipt integrity (replay anchoring), not for promotion gating.
    """

    if not subrun_root.exists() or not subrun_root.is_dir():
        fail("MISSING_STATE_INPUT")

    include_files: list[dict[str, str]] = []

    def _add_tree(root: Path, rel_prefix: str) -> None:
        if not root.exists() or not root.is_dir():
            return
        stack = [root]
        while stack:
            cur = stack.pop()
            for entry in sorted(cur.iterdir(), key=lambda p: p.name):
                rel = (Path(rel_prefix) / entry.relative_to(root)).as_posix()
                # Exclude EK workspaces entirely.
                if rel.startswith("ccap/ek_runs/"):
                    continue
                if entry.is_symlink():
                    try:
                        target = os.readlink(entry)
                    except OSError:
                        fail("SCHEMA_FAIL")
                    include_files.append({"path": rel, "sha256": hash_bytes(target.encode("utf-8"))})
                elif entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    include_files.append({"path": rel, "sha256": hash_file(entry)})

    # Core CCAP + promotion artifacts.
    _add_tree((subrun_root / "ccap").resolve(), "ccap")
    _add_tree((subrun_root / "promotion").resolve(), "promotion")

    # Helpful GE summary artifacts if present.
    for name in ("ge_symbiotic_optimizer_summary_v0_3.json", "ge_xs_snapshot_v1.json", "ge_run_inputs_fingerprint_v2.json"):
        p = (subrun_root / name).resolve()
        if p.exists() and p.is_file():
            include_files.append({"path": name, "sha256": hash_file(p)})

    include_files.sort(key=lambda row: row["path"])
    return canon_hash_obj({"schema_version": "omega_ccap_subrun_hash_v1", "files": include_files})


def _touches_ek_authority(path_rel: str) -> bool:
    rel = str(path_rel).strip().replace("\\", "/")
    return rel == "authority/authority_pins_v1.json" or rel.startswith("authority/evaluation_kernels/")


def _bundle_requires_ek_meta_verify(touched_paths: list[str]) -> bool:
    return any(_touches_ek_authority(row) for row in touched_paths)


def _resolve_repo_root_for_dispatch(dispatch_ctx: dict[str, Any]) -> Path:
    """Best-effort repo-root resolution for promotion/subverifier replay.

    Omega runs can execute against a git worktree whose tracked contents differ from
    the original checkout (for example due to runner overlays). CCAP receipts bind
    `base_tree_id` to the repo root used during evaluation; promotion must replay
    patch application against that same root to avoid false `CCAP_APPLY_MISMATCH`.
    """

    candidate = dispatch_ctx.get("repo_root_abs")
    if isinstance(candidate, (str, Path)):
        repo = Path(candidate).resolve()
        if repo.exists() and repo.is_dir():
            return repo

    exec_root = dispatch_ctx.get("exec_root_abs")
    if isinstance(exec_root, (str, Path)):
        exec_path = Path(exec_root).resolve()
        # omega_executor_v1 computes exec_root_abs as:
        #   <repo_root>/.omega_v18_exec_workspace/<exec_root_name>
        # so parents[1] is the repo root even if the exec workspace was pruned.
        if len(exec_path.parents) >= 2:
            repo = exec_path.parents[1]
            if repo.exists() and repo.is_dir():
                return repo

    return repo_root().resolve()


def _load_ek_meta_verify_receipt(promotion_dir: Path) -> dict[str, Any] | None:
    candidates = sorted(promotion_dir.glob("sha256_*.ek_meta_verify_receipt_v1.json"), key=lambda row: row.as_posix())
    plain = promotion_dir / "ek_meta_verify_receipt_v1.json"
    if plain.exists() and plain.is_file():
        candidates.append(plain)
    for path in candidates:
        payload = _load_json_any(path)
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") != "ek_meta_verify_receipt_v1":
            continue
        result = payload.get("result")
        if isinstance(result, dict) and str(result.get("status", "")).strip() == "PASS":
            return payload
    return None


def _ccap_bundle_paths_valid(*, bundle_obj: dict[str, Any], touched: list[str]) -> bool:
    ccap_rel = normalize_subrun_relpath(str(bundle_obj.get("ccap_relpath", "")))
    patch_rel = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")))
    touched_set = set(touched)
    if ccap_rel not in touched_set or patch_rel not in touched_set:
        return False
    if any(_path_contains_omega_cache(row) for row in touched_set):
        return False
    return True


def _verify_ccap_apply_matches_receipt(
    *,
    bundle_obj: dict[str, Any],
    receipt: dict[str, Any],
    dispatch_ctx: dict[str, Any],
    out_dir: Path,
    require_receipt_applied_tree: bool = True,
) -> bool:
    try:
        # Promotion calls this before emitting any promotion receipt, so the target
        # directory might not exist yet. Ensure we can always create a scratch dir.
        out_dir.mkdir(parents=True, exist_ok=True)
        subrun_root = _resolve_ccap_subrun_root_for_bundle(bundle_obj=bundle_obj, dispatch_ctx=dispatch_ctx)
        ccap_relpath = normalize_subrun_relpath(str(bundle_obj.get("ccap_relpath", "")))
        patch_relpath = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")))
        ccap_path = (subrun_root / ccap_relpath).resolve()
        patch_path = (subrun_root / patch_relpath).resolve()
        if not ccap_path.exists() or not ccap_path.is_file() or not patch_path.exists() or not patch_path.is_file():
            return False

        ccap_obj = load_canon_dict(ccap_path)
        validate_schema(ccap_obj, "ccap_v1")
        if ccap_payload_id(ccap_obj) != str(receipt.get("ccap_id", "")):
            return False

        meta = ccap_obj.get("meta")
        payload = ccap_obj.get("payload")
        if not isinstance(meta, dict) or not isinstance(payload, dict):
            return False
        if str(payload.get("kind", "")) != "PATCH":
            return False
        if str(meta.get("ek_id", "")) != str(receipt.get("ek_id", "")):
            return False
        if str(meta.get("op_pool_id", "")) != str(receipt.get("op_pool_id", "")):
            return False
        if str(meta.get("auth_hash", "")) != str(receipt.get("auth_hash", "")):
            return False
        patch_blob_id = str(payload.get("patch_blob_id", "")).strip()
        patch_bytes = patch_path.read_bytes()
        if f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}" != patch_blob_id:
            return False

        receipt_base_tree_id = str(receipt.get("base_tree_id", "")).strip()
        meta_base_tree_id = str(meta.get("base_tree_id", "")).strip()
        if require_receipt_applied_tree:
            if meta_base_tree_id != receipt_base_tree_id:
                return False
            expected_base_tree_id = receipt_base_tree_id
        else:
            if receipt_base_tree_id and receipt_base_tree_id != meta_base_tree_id:
                return False
            expected_base_tree_id = meta_base_tree_id

        root = _resolve_repo_root_for_dispatch(dispatch_ctx)
        if compute_repo_base_tree_id(root) != expected_base_tree_id:
            return False

        with tempfile.TemporaryDirectory(dir=out_dir, prefix="ccap_promote_") as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            materialize_repo_snapshot(root, workspace)
            apply_patch_bytes(workspace_root=workspace, patch_bytes=patch_bytes)
            applied_tree_id = compute_workspace_tree_id(workspace)
        if require_receipt_applied_tree:
            return applied_tree_id == str(receipt.get("applied_tree_id", "")).strip()
        receipt_applied_tree_id = str(receipt.get("applied_tree_id", "")).strip()
        if receipt_applied_tree_id and receipt_applied_tree_id != _SHA256_ZERO:
            return applied_tree_id == receipt_applied_tree_id
        return True
    except Exception:  # noqa: BLE001
        return False


def _resolve_ccap_subrun_root_for_bundle(*, bundle_obj: dict[str, Any], dispatch_ctx: dict[str, Any]) -> Path:
    # CCAP promotion bundles reference files under the subrun root via `ccap_relpath`/`patch_relpath`.
    # Some dispatch receipts (notably in sandboxed drill runs) may omit `subrun_root_abs`; fail closed
    # unless we can deterministically locate the correct subrun directory.
    ccap_relpath = normalize_subrun_relpath(str(bundle_obj.get("ccap_relpath", "")))
    patch_relpath = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")))
    if not ccap_relpath or not patch_relpath:
        raise RuntimeError("SCHEMA_FAIL")

    raw = dispatch_ctx.get("subrun_root_abs")
    subrun_root: Path | None = None
    if isinstance(raw, Path):
        subrun_root = raw
    elif isinstance(raw, os.PathLike):
        subrun_root = Path(raw)
    elif isinstance(raw, str) and raw.strip():
        subrun_root = Path(raw)
    if subrun_root is not None:
        path = subrun_root.resolve()
        if path.exists() and path.is_dir():
            # Fail-closed: accept dispatch-provided subrun roots only if they actually contain the
            # CCAP bundle's referenced files.
            if (path / ccap_relpath).is_file() and (path / patch_relpath).is_file():
                return path

    dispatch_dir_raw = dispatch_ctx.get("dispatch_dir")
    dispatch_dir: Path | None = None
    if isinstance(dispatch_dir_raw, Path):
        dispatch_dir = dispatch_dir_raw
    elif isinstance(dispatch_dir_raw, os.PathLike):
        dispatch_dir = Path(dispatch_dir_raw)
    elif isinstance(dispatch_dir_raw, str) and dispatch_dir_raw.strip():
        dispatch_dir = Path(dispatch_dir_raw)
    if dispatch_dir is None:
        raise RuntimeError("MISSING_STATE_INPUT")
    dispatch_dir = dispatch_dir.resolve()
    if not dispatch_dir.exists() or not dispatch_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")
    state_root = dispatch_dir.parent.parent.resolve()
    subruns_root = state_root / "subruns"
    if not subruns_root.exists() or not subruns_root.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")

    candidate: Path | None = None
    for entry in sorted(subruns_root.iterdir(), key=lambda p: p.as_posix()):
        if not entry.is_dir():
            continue
        if (entry / ccap_relpath).is_file() and (entry / patch_relpath).is_file():
            if candidate is not None:
                raise RuntimeError("VERIFY_ERROR")
            candidate = entry.resolve()
    if candidate is None:
        raise RuntimeError("MISSING_STATE_INPUT")
    return candidate


def _load_json_any(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("META_CORE_BUNDLE_SCHEMA_FAIL") from exc


def _meta_core_active_bundle_hex(meta_core_root: Path) -> str:
    pointer = meta_core_root / "active" / "ACTIVE_BUNDLE"
    if not pointer.exists() or not pointer.is_file():
        raise RuntimeError("META_CORE_ACTIVE_POINTER_MISSING")
    value = pointer.read_text(encoding="utf-8").strip()
    if not _is_hex64(value):
        raise RuntimeError("META_CORE_ACTIVE_POINTER_INVALID")
    return value


def _extract_activation_key(campaign_id: str, promo: dict[str, Any]) -> str:
    try:
        if campaign_id == "rsi_sas_code_v12_0":
            return str(promo["candidate_algo_id"])
        if campaign_id == "rsi_sas_system_v14_0":
            return str(promo["sealed_build_receipt_hash"])
        if campaign_id == "rsi_model_genesis_v10_0":
            # The Model-Genesis promotion bundle includes stable content IDs. Prefer a
            # dedicated bundle_id so activations can be de-duped across runs.
            value = promo.get("bundle_id")
            if isinstance(value, str) and value.strip():
                return value
            value = promo.get("icore_id")
            if isinstance(value, str) and value.strip():
                return value
            return canon_hash_obj(promo)
        if campaign_id == "rsi_sas_kernel_v15_0":
            value = promo.get("kernel_binary_sha256")
            if isinstance(value, str) and value:
                return value
            activation = promo.get("kernel_activation_receipt")
            if isinstance(activation, dict):
                inner = activation.get("binary_sha256")
                if isinstance(inner, str) and inner:
                    return inner
            return canon_hash_obj(promo)
        if campaign_id == "rsi_sas_metasearch_v16_1":
            return str(promo["plan_hash"])
        if campaign_id == "rsi_sas_val_v17_0":
            det = promo["determinism_keys"]
            if not isinstance(det, dict):
                raise KeyError("determinism_keys")
            return str(det["val_patch_id"])
        if campaign_id == "rsi_sas_science_v13_0":
            discovery = promo["discovery_bundle"]
            if not isinstance(discovery, dict):
                raise KeyError("discovery_bundle")
            return str(discovery["theory_id"])
        if campaign_id == "rsi_agi_orchestrator_llm_v1":
            activation_key = promo.get("activation_key")
            if isinstance(activation_key, str) and activation_key.strip():
                return activation_key
            return canon_hash_obj(promo)
        if campaign_id.startswith("rsi_eudrs_u_"):
            activation_key = promo.get("activation_key")
            if isinstance(activation_key, str) and activation_key.strip():
                return activation_key
            proposed = promo.get("proposed_root_tuple_ref")
            if isinstance(proposed, dict):
                artifact_id = proposed.get("artifact_id")
                if isinstance(artifact_id, str) and artifact_id.strip():
                    return artifact_id
            return canon_hash_obj(promo)
        if campaign_id in {
            "rsi_polymath_scout_v1",
            "rsi_polymath_bootstrap_domain_v1",
            "rsi_polymath_conquer_domain_v1",
        } or campaign_id.startswith("rsi_domain_"):
            activation_key = promo.get("activation_key")
            if isinstance(activation_key, str) and activation_key.strip():
                return activation_key
            domain_id = promo.get("domain_id")
            if isinstance(domain_id, str) and domain_id.strip():
                return domain_id
            return canon_hash_obj(promo)
        if campaign_id == "rsi_omega_native_module_v0_1":
            native = promo.get("native_module")
            if not isinstance(native, dict):
                raise KeyError("native_module")
            return str(native["binary_sha256"])
        if campaign_id == "rsi_knowledge_transpiler_v1":
            bundle_id = promo.get("bundle_id")
            if isinstance(bundle_id, str) and bundle_id.strip():
                return bundle_id
            native_binary_hash = promo.get("native_binary_hash")
            if isinstance(native_binary_hash, str) and native_binary_hash.strip():
                return native_binary_hash
            native = promo.get("native_module")
            if isinstance(native, dict):
                binary_sha = native.get("binary_sha256")
                if isinstance(binary_sha, str) and binary_sha.strip():
                    return binary_sha
            return canon_hash_obj(promo)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ACTIVATION_KEY_MISSING") from exc
    raise RuntimeError("ACTIVATION_KEY_MISSING")


def _read_active_binding(meta_core_root: Path) -> dict[str, Any] | None:
    active_hex = _meta_core_active_bundle_hex(meta_core_root)
    binding_path = meta_core_root / "store" / "bundles" / active_hex / "omega" / "omega_activation_binding_v1.json"
    if not binding_path.exists() or not binding_path.is_file():
        return None
    payload = load_canon_dict(binding_path)
    validate_schema(payload, "omega_activation_binding_v1")
    return payload


def _meta_core_hashing(meta_core_root: Path) -> Any:
    import importlib
    import importlib.util

    engine_dir = (meta_core_root / "engine").resolve()
    engine_hashing = engine_dir / "hashing.py"
    if not engine_hashing.exists() or not engine_hashing.is_file():
        raise RuntimeError("META_CORE_INPUT_MISSING")

    engine_dir_str = str(engine_dir)
    if engine_dir_str not in sys.path:
        sys.path.insert(0, engine_dir_str)
    mc_hashing = importlib.import_module("hashing")
    module_file = Path(getattr(mc_hashing, "__file__", "")).resolve()
    if module_file != engine_hashing:
        spec = importlib.util.spec_from_file_location("_omega_meta_core_hashing_v1", engine_hashing)
        if spec is None or spec.loader is None:
            raise RuntimeError("META_CORE_INPUT_MISSING")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mc_hashing = module
    required = [
        "ruleset_hash",
        "proof_bundle_hash",
        "migration_hash",
        "state_schema_hash",
        "toolchain_merkle_root",
        "manifest_hash",
        "bundle_hash",
    ]
    if any(not hasattr(mc_hashing, name) for name in required):
        raise RuntimeError("META_CORE_INPUT_MISSING")
    return mc_hashing


def _is_safe_node(node: Any) -> bool:
    return isinstance(node, dict) and set(node.keys()) == {"Safe"}


def _extract_accept_non_safe(expr: Any) -> Any:
    if not isinstance(expr, dict):
        raise RuntimeError("META_CORE_ACCEPT_SCHEMA_FAIL")
    and_rows = expr.get("And")
    if not isinstance(and_rows, list):
        return expr
    non_safe = [row for row in and_rows if not _is_safe_node(row)]
    if not non_safe:
        return {"Eq": [{"Int": 0}, {"Int": 1}]}
    if len(non_safe) == 1:
        return non_safe[0]
    return {"And": non_safe}


def _ruleset_blob_entries(bundle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in ("ruleset/accept.ir.json", "ruleset/costvec.ir.json", "ruleset/migrate.ir.json"):
        raw = (bundle_dir / rel).read_bytes()
        rows.append(
            {
                "path": rel,
                "sha256": _sha256_hex(raw),
                "bytes": len(raw),
            }
        )
    return rows


def _build_meta_core_activation_bundle(
    *,
    out_dir: Path,
    binding_payload: dict[str, Any],
    binding_hash_hex8: str,
) -> tuple[Path, str]:
    meta_core_root = _meta_core_root()
    active_hex = _meta_core_active_bundle_hex(meta_core_root)
    active_bundle_dir = meta_core_root / "store" / "bundles" / active_hex
    if not active_bundle_dir.exists() or not active_bundle_dir.is_dir():
        raise RuntimeError("META_CORE_ACTIVE_BUNDLE_MISSING")

    bundle_dir = out_dir / "meta_core_activation_bundle_v1"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    _copy_tree_clone_or_copy(active_bundle_dir, bundle_dir)

    manifest_path = bundle_dir / "constitution.manifest.json"
    manifest = _load_json_any(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError("META_CORE_BUNDLE_SCHEMA_FAIL")

    meta_hash_path = meta_core_root / "meta_constitution" / "v1" / "META_HASH"
    kernel_hash_path = meta_core_root / "kernel" / "verifier" / "KERNEL_HASH"
    if not meta_hash_path.exists() or not kernel_hash_path.exists():
        raise RuntimeError("META_CORE_INPUT_MISSING")

    meta_hash = meta_hash_path.read_text(encoding="utf-8").strip()
    kernel_hash = kernel_hash_path.read_text(encoding="utf-8").strip()
    if not _is_hex64(meta_hash) or not _is_hex64(kernel_hash):
        raise RuntimeError("META_CORE_HASH_INVALID")

    manifest["parent_bundle_hash"] = active_hex
    manifest["meta_hash"] = meta_hash
    manifest["kernel_hash"] = kernel_hash

    binding_path = bundle_dir / "omega" / "omega_activation_binding_v1.json"
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(binding_path, binding_payload)
    binding_raw = binding_path.read_bytes()
    binding_sha256_hex = _sha256_hex(binding_raw)

    accept_path = bundle_dir / "ruleset" / "accept.ir.json"
    parent_accept = _load_json_any(accept_path)
    parent_cond = _extract_accept_non_safe(parent_accept)
    new_flag = f"omega_bind_{binding_hash_hex8}"
    cond_extra = {
        "Eq": [
            {"MapGet": [{"Var": "x"}, {"Str": new_flag}, {"Int": 0}]},
            {"Int": 1},
        ]
    }
    candidate_accept = {
        "And": [
            {"Safe": None},
            {"Or": [parent_cond, cond_extra]},
        ]
    }
    write_canon_json(accept_path, candidate_accept)

    witness_path = bundle_dir / "proofs" / "dominance_witness.json"
    witness = _load_json_any(witness_path)
    if not isinstance(witness, dict):
        raise RuntimeError("META_CORE_WITNESS_SCHEMA_FAIL")
    witness["x_star"] = {new_flag: 1}
    witness["state_a"] = {}
    witness["condextra_inputs"] = {"blob_hashes": [binding_sha256_hex]}
    write_canon_json(witness_path, witness)

    proof_manifest_path = bundle_dir / "proofs" / "proof_bundle.manifest.json"
    proof_manifest = _load_json_any(proof_manifest_path)
    if not isinstance(proof_manifest, dict):
        raise RuntimeError("META_CORE_PROOF_MANIFEST_SCHEMA_FAIL")
    proof_manifest["dominance_witness_sha256"] = _sha256_hex(witness_path.read_bytes())
    write_canon_json(proof_manifest_path, proof_manifest)

    blobs = _ruleset_blob_entries(bundle_dir)
    blobs.append(
        {
            "path": "omega/omega_activation_binding_v1.json",
            "sha256": binding_sha256_hex,
            "bytes": len(binding_raw),
        }
    )
    manifest["blobs"] = blobs
    mc_hashing = _meta_core_hashing(meta_core_root)
    ruleset_hex = str(mc_hashing.ruleset_hash(str(bundle_dir)))
    proof_hex = str(mc_hashing.proof_bundle_hash(str(bundle_dir)))
    migration_hex = str(mc_hashing.migration_hash(str(bundle_dir)))
    state_schema_hex = str(mc_hashing.state_schema_hash(str(meta_core_root)))
    toolchain_hex = str(mc_hashing.toolchain_merkle_root(str(meta_core_root)))

    proofs = manifest.get("proofs")
    if not isinstance(proofs, dict):
        proofs = {}
    proofs["proof_bundle_hash"] = proof_hex
    manifest["proofs"] = proofs
    manifest["ruleset_hash"] = ruleset_hex
    manifest["migration_hash"] = migration_hex
    manifest["state_schema_hash"] = state_schema_hex
    manifest["toolchain_merkle_root"] = toolchain_hex
    manifest["manifest_hash"] = ""
    manifest_hex = str(mc_hashing.manifest_hash(manifest))
    bundle_hex = str(
        mc_hashing.bundle_hash(
            manifest_hex,
            ruleset_hex,
            proof_hex,
            migration_hex,
            state_schema_hex,
            toolchain_hex,
        )
    )
    manifest["manifest_hash"] = manifest_hex
    manifest["bundle_hash"] = bundle_hex
    write_canon_json(manifest_path, manifest)

    return bundle_dir, f"sha256:{bundle_hex}"


def _meta_fingerprint() -> dict[str, str]:
    root = repo_root()
    meta_hash_path = root / "meta-core" / "meta_constitution" / "v1_5r" / "META_HASH"
    kernel_hash_path = root / "meta-core" / "kernel" / "verifier" / "KERNEL_HASH"
    meta_hash = meta_hash_path.read_text(encoding="utf-8").strip() if meta_hash_path.exists() else "UNKNOWN"
    kernel_hash = kernel_hash_path.read_text(encoding="utf-8").strip() if kernel_hash_path.exists() else "UNKNOWN"
    return {
        "constitution_meta_hash": meta_hash,
        "binary_hash_or_build_id": kernel_hash,
    }


def _meta_core_root() -> Path:
    override = str(os.environ.get("OMEGA_META_CORE_ROOT", "")).strip()
    if override:
        return Path(override).resolve()
    return repo_root() / "meta-core"


def _find_promotion_bundle(dispatch_ctx: dict[str, Any]) -> tuple[Path | None, str | None]:
    cap = dispatch_ctx["campaign_entry"]
    rel_pattern = str(cap.get("promotion_bundle_rel", "")).strip()
    if not rel_pattern:
        return None, None

    subrun_root: Path | None = None
    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if isinstance(subrun_root_raw, Path):
        subrun_root = subrun_root_raw
    elif isinstance(subrun_root_raw, str) and subrun_root_raw.strip():
        subrun_root = Path(subrun_root_raw)

    if subrun_root is None:
        # Some unit tests call helpers with only state_root + relpaths.
        state_root_raw = dispatch_ctx.get("state_root")
        subrun_root_rel_raw = dispatch_ctx.get("subrun_root_rel_state")
        if state_root_raw is None or subrun_root_rel_raw is None:
            return None, None
        try:
            subrun_root_rel = require_relpath(subrun_root_rel_raw)
        except Exception:  # noqa: BLE001
            return None, None
        subrun_root = Path(state_root_raw) / subrun_root_rel

    matches = sorted(subrun_root.glob(rel_pattern), key=lambda row: row.as_posix())
    if not matches:
        inferred = _infer_subrun_root_from_state(dispatch_ctx=dispatch_ctx)
        if inferred is not None and inferred != subrun_root:
            matches = sorted(inferred.glob(rel_pattern))
    if not matches:
        return None, None
    path = matches[0]
    _, digest = load_bundle(path)
    return path, digest


def _infer_subrun_root_from_state(*, dispatch_ctx: dict[str, Any]) -> Path | None:
    # Some dispatch receipts omit or misreport `subrun_root_abs`. When that happens, we can still
    # deterministically infer the subrun directory from `state_root/subruns/<dispatch_id>_*`.
    try:
        state_root_raw = dispatch_ctx.get("state_root")
        dispatch_dir_raw = dispatch_ctx.get("dispatch_dir")
        if not isinstance(state_root_raw, Path):
            state_root = Path(str(state_root_raw)).resolve()
        else:
            state_root = state_root_raw.resolve()
        dispatch_dir = Path(str(dispatch_dir_raw)).resolve()
    except Exception:  # noqa: BLE001
        return None
    if not state_root.exists() or not state_root.is_dir() or not dispatch_dir.exists() or not dispatch_dir.is_dir():
        return None
    dispatch_id = dispatch_dir.name
    subruns_root = state_root / "subruns"
    if not subruns_root.exists() or not subruns_root.is_dir():
        return None
    candidates = sorted(subruns_root.glob(f"{dispatch_id}_*"), key=lambda p: p.as_posix())
    if len(candidates) != 1:
        return None
    candidate = candidates[0].resolve()
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


def _copy_file_clone_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    clonefile_fn = getattr(os, "clonefile", None)
    if sys.platform == "darwin" and callable(clonefile_fn):
        try:
            clonefile_fn(src, dst)
            return
        except Exception:
            pass
    shutil.copy2(src, dst)


def _apply_eudrs_u_staged_registry_tree(
    *,
    dispatch_ctx: dict[str, Any],
    bundle_obj: dict[str, Any],
    allowlists: dict[str, Any],
) -> None:
    subrun_root = Path(dispatch_ctx["subrun_root_abs"]).resolve()
    try:
        summary_rel = normalize_subrun_relpath(str(bundle_obj.get("summary_relpath", "")).strip())
    except OmegaV18Error as exc:
        raise RuntimeError("UNKNOWN") from exc
    summary_rel_parts = Path(summary_rel).parts
    if not summary_rel_parts:
        raise RuntimeError("UNKNOWN")

    summary_path = (subrun_root / summary_rel).resolve()
    if not summary_path.exists() or not summary_path.is_file():
        matches = sorted(subrun_root.glob(f"**/{summary_rel}"), key=lambda row: row.as_posix())
        if len(matches) != 1:
            raise RuntimeError("UNKNOWN")
        summary_path = matches[0].resolve()
    try:
        _ = summary_path.relative_to(subrun_root)
    except Exception as exc:
        raise RuntimeError("UNKNOWN") from exc

    producer_state_root = summary_path
    for _ in summary_rel_parts:
        producer_state_root = producer_state_root.parent
    try:
        _ = producer_state_root.relative_to(subrun_root)
    except Exception as exc:
        raise RuntimeError("UNKNOWN") from exc

    summary_obj = load_canon_dict(summary_path)
    validate_schema(summary_obj, "eudrs_u_promotion_summary_v1")
    require_no_absolute_paths(summary_obj)

    try:
        staged_rel = normalize_subrun_relpath(str(summary_obj.get("staged_registry_tree_relpath", "")).strip())
    except OmegaV18Error as exc:
        raise RuntimeError("UNKNOWN") from exc
    staged_root = (producer_state_root / staged_rel).resolve()
    try:
        _ = staged_root.relative_to(producer_state_root)
    except Exception as exc:
        raise RuntimeError("UNKNOWN") from exc
    src_tree = (staged_root / "polymath" / "registry" / "eudrs_u").resolve()
    if not src_tree.exists() or not src_tree.is_dir():
        raise RuntimeError("UNKNOWN")

    repo = repo_root().resolve()
    files = sorted((p for p in src_tree.rglob("*") if p.is_file()), key=lambda row: row.as_posix())
    if not files:
        raise RuntimeError("UNKNOWN")

    rel_paths: list[str] = []
    for src in files:
        rel_path = src.relative_to(staged_root).as_posix()
        if is_path_forbidden(rel_path, allowlists) or not is_path_allowed(rel_path, allowlists):
            raise RuntimeError("FORBIDDEN_PATH")
        rel_paths.append(rel_path)

    for src, rel_path in zip(files, rel_paths):
        dst = (repo / rel_path).resolve()
        try:
            _ = dst.relative_to(repo)
        except Exception as exc:
            raise RuntimeError("UNKNOWN") from exc
        _copy_file_clone_or_copy(src, dst)


def _build_meta_core_promotion_bundle(
    *,
    out_dir: Path,
    campaign_id: str,
    source_bundle_hash: str,
) -> Path:
    meta_core_root = _meta_core_root()
    meta_hash_path = meta_core_root / "meta_constitution" / "v1_5r" / "META_HASH"
    kernel_hash_path = meta_core_root / "kernel" / "verifier" / "KERNEL_HASH"
    constants_path = meta_core_root / "meta_constitution" / "v1_5r" / "constants_v1.json"

    if not meta_hash_path.exists() or not kernel_hash_path.exists() or not constants_path.exists():
        raise RuntimeError("META_CORE_INPUT_MISSING")

    meta_hash = meta_hash_path.read_text(encoding="utf-8").strip()
    kernel_hash = kernel_hash_path.read_text(encoding="utf-8").strip()
    constants_hash = canon_hash_obj(load_canon_dict(constants_path))

    bundle_dir = out_dir / "meta_core_promotion_bundle_v1"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    witness = {
        "schema": "dominance_witness_v1",
        "schema_version": 1,
        "epoch_id": "OMEGA_V18_0",
        "decisions": [
            {
                "decision_id": "omega_promotion_gate",
                "status": "PASS",
                "campaign_id": campaign_id,
                "source_bundle_hash": source_bundle_hash,
            }
        ],
    }
    witness_bytes = canon_bytes(witness)
    witness_hash = canon_hash_obj(witness)
    (bundle_dir / "dominance_witness_v1.json").write_bytes(witness_bytes)

    manifest_wo_bundle = {
        "schema": "promotion_bundle_manifest_v1",
        "schema_version": 1,
        "promotion_type": "RSI_OMEGA_DAEMON",
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
        "proofs": {"dominance_witness_hash": witness_hash},
        "blobs": [
            {
                "path": "dominance_witness_v1.json",
                "sha256": witness_hash,
                "bytes": len(witness_bytes),
            }
        ],
    }
    manifest_bytes = canon_bytes(manifest_wo_bundle)
    # Promotion verifier defines bundle hash as sha256(canon(manifest_without_bundle_hash) || blob_bytes...)
    from ..v1_7r.canon import sha256_prefixed

    bundle_hash = sha256_prefixed(manifest_bytes + witness_bytes)

    manifest = dict(manifest_wo_bundle)
    manifest["bundle_hash"] = bundle_hash
    (bundle_dir / "promotion_bundle_manifest_v1.json").write_bytes(canon_bytes(manifest))
    return bundle_dir


def _run_meta_core_promo_verify(
    *,
    out_dir: Path,
    bundle_dir: Path,
) -> tuple[dict[str, Any], bool]:
    meta_core_root = _meta_core_root()
    verifier_out = out_dir / "meta_core_promo_verify_out_v1.json"
    cmd = [
        sys.executable,
        str(meta_core_root / "kernel" / "verify_promotion_bundle.py"),
        "--bundle_dir",
        str(bundle_dir),
        "--meta_core_root",
        str(meta_core_root),
        "--out",
        str(verifier_out),
    ]
    run_result = run_command(
        cmd=cmd,
        cwd=repo_root(),
        output_dir=out_dir,
        extra_env={"META_CORE_ROOT": str(meta_core_root)},
    )
    verifier_json: dict[str, Any] = {}
    if verifier_out.exists():
        raw = load_canon_dict(verifier_out)
        if isinstance(raw, dict):
            verifier_json = raw

    passed = int(run_result["return_code"]) == 0 and str(verifier_json.get("verdict", "")) == "VALID"
    receipt = {
        "schema_version": "meta_core_promo_verify_receipt_v1",
        "return_code": int(run_result["return_code"]),
        "stdout_hash": run_result["stdout_hash"],
        "stderr_hash": run_result["stderr_hash"],
        "verifier_out_hash": hash_file(verifier_out) if verifier_out.exists() else "sha256:" + ("0" * 64),
        "pass": bool(passed),
    }
    validate_schema(receipt, "meta_core_promo_verify_receipt_v1")
    return receipt, passed


def _copy_tree_clone_or_copy(src: Path, dst: Path) -> None:
    if not src.exists():
        raise RuntimeError("REPLAY_REPO_SNAPSHOT_INPUT_MISSING")
    if dst.exists():
        shutil.rmtree(dst)

    clonefile_fn = getattr(os, "clonefile", None)
    if sys.platform == "darwin" and callable(clonefile_fn):
        dst.mkdir(parents=True, exist_ok=True)
        for src_dir_raw, dir_names, file_names in os.walk(src):
            src_dir = Path(src_dir_raw)
            rel_dir = src_dir.relative_to(src)
            dst_dir = dst if str(rel_dir) == "." else (dst / rel_dir)
            dst_dir.mkdir(parents=True, exist_ok=True)
            for dir_name in sorted(dir_names):
                (dst_dir / dir_name).mkdir(parents=True, exist_ok=True)
            for file_name in sorted(file_names):
                src_file = src_dir / file_name
                dst_file = dst_dir / file_name
                try:
                    clonefile_fn(src_file, dst_file)
                except Exception:
                    shutil.copy2(src_file, dst_file)
        return

    shutil.copytree(src, dst)


def _chmod_tree_readonly(root: Path) -> None:
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            continue
        try:
            mode = path.stat().st_mode
            path.chmod(mode & ~_WRITE_BITS)
        except OSError as exc:
            raise RuntimeError("REPLAY_REPO_SNAPSHOT_READONLY_FAIL") from exc


def _prepare_replay_repo_snapshot(*, out_dir: Path, state_root: Path, readonly: bool = True) -> str:
    snapshot_root = out_dir / "replay_repo_root"
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root)
    (snapshot_root / "CDEL-v2").mkdir(parents=True, exist_ok=True)
    (snapshot_root / "campaigns").mkdir(parents=True, exist_ok=True)
    (snapshot_root / "Genesis").mkdir(parents=True, exist_ok=True)

    root = repo_root()
    _copy_tree_clone_or_copy(root / "CDEL-v2" / "cdel", snapshot_root / "CDEL-v2" / "cdel")
    _copy_tree_clone_or_copy(root / "campaigns", snapshot_root / "campaigns")
    _copy_tree_clone_or_copy(root / "Genesis" / "schema", snapshot_root / "Genesis" / "schema")
    _copy_tree_clone_or_copy(root / "meta-core", snapshot_root / "meta-core")
    if readonly:
        _chmod_tree_readonly(snapshot_root)

    return str(snapshot_root.resolve().relative_to(state_root.resolve()))


def run_subverifier(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if dispatch_ctx is None:
        return None, None

    cap = dispatch_ctx["campaign_entry"]
    verifier_module = str(cap.get("verifier_module"))
    state_root = Path(dispatch_ctx["state_root"])
    state_dir_rel = str(dispatch_ctx["subrun_state_rel_state"])
    subverifier_cwd = state_root
    pythonpath = str(dispatch_ctx.get("pythonpath") or "")
    state_arg = _state_arg_for_verifier(verifier_module)
    if verifier_module == "cdel.v12_0.verify_rsi_sas_code_v1":
        state_arg = "--sas_code_state_dir"
        exec_state_rel_repo = str(dispatch_ctx.get("exec_state_rel_repo", "")).strip()
        if exec_state_rel_repo:
            state_dir_rel = exec_state_rel_repo
            subverifier_cwd = repo_root()

    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
    replay_state_dir_abs = state_root / dispatch_ctx["subrun_state_rel_state"]
    replay_repo_root_rel: str | None = None
    replay_repo_root_hash: str | None = None
    subverifier_pythonpath = pythonpath
    invocation_env = dispatch_ctx.get("invocation_env_overrides")
    if invocation_env is None:
        invocation_env_overrides: dict[str, str] = {}
    elif isinstance(invocation_env, dict):
        invocation_env_overrides = {str(k): str(v) for k, v in invocation_env.items()}
    else:
        fail("SCHEMA_FAIL")
    if verifier_module in _REPLAY_REPO_ROOT_VERIFIER_MODULES:
        replay_repo_root_rel = _prepare_replay_repo_snapshot(
            out_dir=out_dir,
            state_root=state_root,
            readonly=True,
        )
        if verifier_module == _V14_VERIFIER_MODULE:
            replay_repo_root_abs = (state_root / replay_repo_root_rel).resolve()
            subverifier_pythonpath = f"{replay_repo_root_abs / 'CDEL-v2'}:{replay_repo_root_abs}"
            if pythonpath:
                subverifier_pythonpath = f"{subverifier_pythonpath}:{pythonpath}"

    repo_root_for_ccap = repo_root()
    if verifier_module == _CCAP_VERIFIER_MODULE:
        # Always pin verifier imports to the dispatch repo root; otherwise a
        # globally installed `cdel` package can cause nondeterministic EK outcomes.
        repo_root_for_ccap = _resolve_repo_root_for_dispatch(dispatch_ctx)
        ccap_py_parts = [str((repo_root_for_ccap / "CDEL-v2").resolve()), str(repo_root_for_ccap.resolve())]
        if subverifier_pythonpath:
            ccap_py_parts.extend(chunk for chunk in str(subverifier_pythonpath).split(os.pathsep) if chunk)
        deduped: list[str] = []
        seen_py_parts: set[str] = set()
        for chunk in ccap_py_parts:
            key = str(chunk).strip()
            if not key or key in seen_py_parts:
                continue
            seen_py_parts.add(key)
            deduped.append(key)
        subverifier_pythonpath = os.pathsep.join(deduped)

    subverifier_env: dict[str, str] = dict(invocation_env_overrides)
    if subverifier_pythonpath:
        subverifier_env["PYTHONPATH"] = subverifier_pythonpath

    argv: list[str] = ["--mode", "full", state_arg, state_dir_rel]
    run_result: dict[str, Any] | None = None
    ccap_subrun_root_abs: Path | None = None
    ccap_rel: str | None = None
    if verifier_module == _CCAP_VERIFIER_MODULE:
        subrun_root_rel = require_relpath(dispatch_ctx.get("subrun_root_rel_state"))
        ccap_subrun_root_abs = state_root / subrun_root_rel
        declared_ccap_rel = str(cap.get("ccap_relpath", "")).strip()
        if declared_ccap_rel:
            ccap_rel = require_relpath(declared_ccap_rel)
        else:
            # Align CCAP selection with promotion bundle selection to prevent deterministic
            # receipt/bundle mismatches when a campaign emits multiple CCAP candidates.
            rel_pattern = str(cap.get("promotion_bundle_rel", "")).strip()
            if rel_pattern:
                try:
                    matches = sorted(ccap_subrun_root_abs.glob(rel_pattern), key=lambda row: row.as_posix())
                except Exception:
                    matches = []
                if matches:
                    try:
                        bundle_obj, _ = load_bundle(matches[0])
                        bundle_ccap_rel = normalize_subrun_relpath(str(bundle_obj.get("ccap_relpath", "")).strip())
                        if bundle_ccap_rel:
                            ccap_rel = bundle_ccap_rel
                    except Exception:
                        ccap_rel = None
            if not ccap_rel:
                ccap_rel = _discover_ccap_relpath(ccap_subrun_root_abs)
        enable_ccap = str(int(cap.get("enable_ccap", 0)))
        if ccap_rel:
            argv = [
                "--mode",
                "full",
                "--subrun_root",
                subrun_root_rel,
                "--repo_root",
                str(repo_root_for_ccap),
                "--receipt_out_dir",
                str(out_dir),
                "--enable_ccap",
                enable_ccap,
                "--ccap_relpath",
                ccap_rel,
            ]
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = out_dir / "stdout.log"
            stderr_path = out_dir / "stderr.log"
            stdout_path.write_text("VALID\nNO_CCAP_CANDIDATE\n", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            run_result = {
                "return_code": 0,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "stdout_hash": hash_file(stdout_path),
                "stderr_hash": hash_file(stderr_path),
            }

    if run_result is None:
        run_result = run_module(
            py_module=verifier_module,
            argv=argv,
            cwd=subverifier_cwd,
            output_dir=out_dir,
            extra_env=subverifier_env or None,
        )
    if replay_repo_root_rel is not None:
        try:
            replay_repo_root_hash = tree_hash((state_root / replay_repo_root_rel).resolve())
        except OmegaV18Error:
            replay_repo_root_hash = _SHA256_ZERO

    stdout_text = Path(run_result["stdout_path"]).read_text(encoding="utf-8").strip()
    status = "VALID" if run_result["return_code"] == 0 and "VALID" in stdout_text.splitlines() else "INVALID"
    reason_code = None
    if status != "VALID":
        reason_code = "VERIFY_ERROR"
        for line in stdout_text.splitlines():
            if line.startswith("INVALID:"):
                reason_code = line.split(":", 1)[1] or "VERIFY_ERROR"
                break
        reason_code = _normalize_subverifier_reason_code(reason_code)
    elif verifier_module == _CCAP_VERIFIER_MODULE and ccap_subrun_root_abs is not None and ccap_rel:
        try:
            ccap_payload = load_canon_dict((ccap_subrun_root_abs / ccap_rel).resolve())
            validate_schema(ccap_payload, "ccap_v1")
            expected_ccap_id = ccap_payload_id(ccap_payload)
            ccap_receipt = _load_ccap_receipt_for_id_with_fallback(
                verifier_dir=out_dir,
                subrun_root=ccap_subrun_root_abs,
                ccap_id=expected_ccap_id,
            )
            if ccap_receipt is None:
                from .verify_ccap_v1 import verify as verify_ccap

                verify_ccap(
                    subrun_root=ccap_subrun_root_abs,
                    repo_root=repo_root_for_ccap,
                    ccap_relpath=ccap_rel,
                    receipt_out_dir=out_dir,
                )
                ccap_receipt = _load_ccap_receipt_for_id_with_fallback(
                    verifier_dir=out_dir,
                    subrun_root=ccap_subrun_root_abs,
                    ccap_id=expected_ccap_id,
                )
            if ccap_receipt is None or str(ccap_receipt.get("ccap_id", "")).strip() != expected_ccap_id:
                status = "INVALID"
                reason_code = "VERIFY_ERROR"
        except Exception:  # noqa: BLE001
            status = "INVALID"
            reason_code = "VERIFY_ERROR"
    stdout_hash = run_result["stdout_hash"]
    stderr_hash = run_result["stderr_hash"]
    state_dir_hash = _SHA256_ZERO
    state_hash_root = replay_state_dir_abs
    try:
        if verifier_module == _CCAP_VERIFIER_MODULE:
            if ccap_subrun_root_abs is not None:
                subrun_root_abs = ccap_subrun_root_abs
            elif "subrun_root_abs" in dispatch_ctx:
                subrun_root_abs = Path(dispatch_ctx["subrun_root_abs"])
            else:
                subrun_root_abs = (state_root / str(dispatch_ctx.get("subrun_root_rel_state", "")).strip()).resolve()
            state_dir_hash = _tree_hash_ccap_subrun_for_receipt(subrun_root_abs)
        else:
            if verifier_module == _CCAP_VERIFIER_MODULE and (not replay_state_dir_abs.exists() or not replay_state_dir_abs.is_dir()):
                subrun_root_abs = Path(dispatch_ctx["subrun_root_abs"])
                if subrun_root_abs.exists() and subrun_root_abs.is_dir():
                    state_hash_root = subrun_root_abs
            state_dir_hash = tree_hash(state_hash_root)
    except OmegaV18Error:
        status = "INVALID"
        reason_code = "MISSING_STATE_INPUT"

    payload = {
        "schema_version": "omega_subverifier_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "campaign_id": str(cap.get("campaign_id")),
        "verifier_module": verifier_module,
        "verifier_mode": "full",
        "state_dir_hash": state_dir_hash,
        "replay_repo_root_rel": replay_repo_root_rel,
        "replay_repo_root_hash": replay_repo_root_hash,
        "result": {
            "status": status,
            "reason_code": _normalize_subverifier_reason_code(reason_code),
        },
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
    }
    require_no_absolute_paths(payload)
    _, receipt, digest = write_hashed_json(out_dir, "omega_subverifier_receipt_v1.json", payload, id_field="receipt_id")
    validate_schema(receipt, "omega_subverifier_receipt_v1")
    return receipt, digest


def run_promotion(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
    subverifier_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if dispatch_ctx is None:
        return None, None

    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    simulate_mode = str(os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE", "live")).lower() != "live"
    execution_mode = resolve_execution_mode()
    promotion_bundle_hash = "sha256:" + "0" * 64
    active_after: str | None = None
    native_module_for_receipt: dict[str, Any] | None = None
    native_runtime_contract_hash_for_receipt: str | None = None
    native_healthcheck_vectors_hash_for_receipt: str | None = None

    def _require_sha256_hash(value: Any, *, field: str) -> str:
        text = str(value).strip()
        if not text.startswith("sha256:"):
            raise RuntimeError(f"SCHEMA_FAIL:{field}")
        hex64 = text.split(":", 1)[1]
        if not _is_hex64(hex64):
            raise RuntimeError(f"SCHEMA_FAIL:{field}")
        return text

    def _write_promotion_receipt(*, status: str, reason: str | None, active_after_hash: str | None) -> tuple[dict[str, Any], str]:
        payload = {
            "schema_version": "omega_promotion_receipt_v1",
            "receipt_id": "sha256:" + "0" * 64,
            "tick_u64": int(tick_u64),
            "promotion_bundle_hash": promotion_bundle_hash,
            "execution_mode": execution_mode,
            "meta_core_verifier_fingerprint": _meta_fingerprint(),
            "native_module": native_module_for_receipt if status == "PROMOTED" else None,
            "native_runtime_contract_hash": native_runtime_contract_hash_for_receipt if status == "PROMOTED" else None,
            "native_healthcheck_vectors_hash": native_healthcheck_vectors_hash_for_receipt if status == "PROMOTED" else None,
            "result": {
                "status": status,
                "reason_code": reason,
            },
            "active_manifest_hash_after": active_after_hash,
        }
        require_no_absolute_paths(payload)
        _, receipt, digest = write_hashed_json(out_dir, "omega_promotion_receipt_v1.json", payload, id_field="receipt_id")
        validate_schema(receipt, "omega_promotion_receipt_v1")
        return receipt, digest

    subverifier_status = str((subverifier_receipt or {}).get("result", {}).get("status", "")).strip()
    if subverifier_receipt is None or subverifier_status != "VALID":
        return _write_promotion_receipt(
            status="REJECTED",
            reason="SUBVERIFIER_INVALID",
            active_after_hash=None,
        )

    bundle_path, bundle_hash = _find_promotion_bundle(dispatch_ctx)
    if bundle_hash is not None:
        promotion_bundle_hash = bundle_hash
    if bundle_path is None:
        return _write_promotion_receipt(
            status="SKIPPED",
            reason="NO_PROMOTION_BUNDLE",
            active_after_hash=None,
        )

    status = "SKIPPED"
    reason: str | None = "NO_PROMOTION_BUNDLE"
    meta_core_root = _meta_core_root()
    bundle_obj = load_canon_dict(bundle_path)
    promotion_bundle_hash = canon_hash_obj(bundle_obj)
    bundle_schema = str(bundle_obj.get("schema_version", "")).strip()
    is_ccap_bundle = bundle_schema == "omega_promotion_bundle_ccap_v1"
    touched = extract_touched_paths(bundle_obj)
    campaign_id = str(dispatch_ctx["campaign_entry"].get("campaign_id"))

    requires_test_receipt = campaign_requires_test_plan_receipt(campaign_id)
    try:
        load_test_plan_receipt(
            promotion_dir=bundle_path.parent,
            touched_paths=touched,
            required=requires_test_receipt,
        )
    except OmegaV18Error:
        return _write_promotion_receipt(
            status="REJECTED",
            reason="TEST_PLAN_RECEIPT_MISSING_OR_FAIL",
            active_after_hash=None,
        )
    if _bundle_requires_ek_meta_verify(touched):
        ek_meta_receipt = _load_ek_meta_verify_receipt(bundle_path.parent)
        if ek_meta_receipt is None:
            return _write_promotion_receipt(
                status="REJECTED",
                reason="EK_META_VERIFY_MISSING_OR_FAIL",
                active_after_hash=None,
            )

    if is_ccap_bundle:
        try:
            if not _ccap_bundle_paths_valid(bundle_obj=bundle_obj, touched=touched):
                return _write_promotion_receipt(
                    status="REJECTED",
                    reason="CCAP_TOUCHED_PATHS_INVALID",
                    active_after_hash=None,
                )
        except OmegaV18Error:
            return _write_promotion_receipt(
                status="REJECTED",
                reason="CCAP_TOUCHED_PATHS_INVALID",
                active_after_hash=None,
            )

    path_reject = False
    path_allowlist_warn = False
    if is_ccap_bundle:
        path_reject = any(_path_contains_omega_cache(row) for row in touched)
    else:
        for row in touched:
            if is_path_forbidden(row, allowlists):
                path_reject = True
                break
            if not is_path_allowed(row, allowlists):
                path_allowlist_warn = True
    if path_allowlist_warn:
        print(
            "WARNING: promotion touched paths outside allowlist; continuing due compatibility override",
            file=sys.stderr,
        )
    if path_reject:
        status = "REJECTED"
        reason = "FORBIDDEN_PATH"
    else:
        capability_id = str(dispatch_ctx["campaign_entry"].get("capability_id"))
        if is_ccap_bundle:
            activation_key = str(bundle_obj.get("activation_key", "")).strip()
            ccap_id = str(bundle_obj.get("ccap_id", "")).strip()
            if not activation_key or not ccap_id.startswith("sha256:"):
                return _write_promotion_receipt(
                    status="REJECTED",
                    reason="CCAP_TOUCHED_PATHS_INVALID",
                    active_after_hash=None,
                )
            dispatch_verifier_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
            subrun_root_abs = Path(dispatch_ctx["subrun_root_abs"])
            ccap_receipt = _load_ccap_receipt_for_id_with_fallback(
                verifier_dir=dispatch_verifier_dir,
                subrun_root=subrun_root_abs,
                ccap_id=ccap_id,
            )
            if ccap_receipt is None or str(ccap_receipt.get("ccap_id", "")) != ccap_id:
                return _write_promotion_receipt(
                    status="REJECTED",
                    reason="CCAP_RECEIPT_MISSING_OR_MISMATCH",
                    active_after_hash=None,
                )
            if execution_mode == "STRICT":
                if str(ccap_receipt.get("decision", "")).strip() != "PROMOTE":
                    return _write_promotion_receipt(
                        status="REJECTED",
                        reason="CCAP_RECEIPT_REJECTED",
                        active_after_hash=None,
                    )
                if str(ccap_receipt.get("determinism_check", "")).strip() != "PASS":
                    return _write_promotion_receipt(
                        status="REJECTED",
                        reason="CCAP_RECEIPT_REJECTED",
                        active_after_hash=None,
                    )
                if str(ccap_receipt.get("eval_status", "")).strip() != "PASS":
                    return _write_promotion_receipt(
                        status="REJECTED",
                        reason="CCAP_RECEIPT_REJECTED",
                        active_after_hash=None,
                    )
            if execution_mode == "STRICT":
                realized_out_id = str(ccap_receipt.get("realized_out_id", "")).strip()
                if not realized_out_id.startswith("sha256:"):
                    return _write_promotion_receipt(
                        status="REJECTED",
                        reason="CCAP_RECEIPT_MISSING_OR_MISMATCH",
                        active_after_hash=None,
                    )
                realized_receipt = _load_realized_receipt_for_id(
                    subrun_root=subrun_root_abs,
                    ccap_id=ccap_id,
                )
                if realized_receipt is None:
                    return _write_promotion_receipt(
                        status="REJECTED",
                        reason="CCAP_RECEIPT_MISSING_OR_MISMATCH",
                        active_after_hash=None,
                    )
                for field in ("applied_tree_id", "realized_out_id", "ek_id", "op_pool_id", "auth_hash"):
                    if str(realized_receipt.get(field, "")).strip() != str(ccap_receipt.get(field, "")).strip():
                        return _write_promotion_receipt(
                            status="REJECTED",
                            reason="CCAP_RECEIPT_MISSING_OR_MISMATCH",
                            active_after_hash=None,
                        )
            if not _verify_ccap_apply_matches_receipt(
                bundle_obj=bundle_obj,
                receipt=ccap_receipt,
                dispatch_ctx=dispatch_ctx,
                out_dir=out_dir,
                require_receipt_applied_tree=(execution_mode == "STRICT"),
            ):
                return _write_promotion_receipt(
                    status="REJECTED",
                    reason="CCAP_APPLY_MISMATCH",
                    active_after_hash=None,
                )
        else:
            try:
                activation_key = _extract_activation_key(campaign_id, bundle_obj)
            except RuntimeError:
                return _write_promotion_receipt(
                    status="REJECTED",
                    reason="UNKNOWN",
                    active_after_hash=None,
                )
        active_binding = _read_active_binding(meta_core_root)
        if (
            not simulate_mode
            and isinstance(active_binding, dict)
            and str(active_binding.get("capability_id")) == capability_id
            and str(active_binding.get("activation_key")) == activation_key
        ):
            status = "SKIPPED"
            reason = "ALREADY_ACTIVE"
        else:
            try:
                promo_bundle_dir = _build_meta_core_promotion_bundle(
                    out_dir=out_dir,
                    campaign_id=campaign_id,
                    source_bundle_hash=promotion_bundle_hash,
                )
                meta_receipt, passed = _run_meta_core_promo_verify(
                    out_dir=out_dir,
                    bundle_dir=promo_bundle_dir,
                )
            except Exception:  # noqa: BLE001
                meta_receipt = {
                    "schema_version": "meta_core_promo_verify_receipt_v1",
                    "return_code": 1,
                    "stdout_hash": "sha256:" + ("0" * 64),
                    "stderr_hash": "sha256:" + ("0" * 64),
                    "verifier_out_hash": "sha256:" + ("0" * 64),
                    "pass": False,
                }
                validate_schema(meta_receipt, "meta_core_promo_verify_receipt_v1")
                passed = False

            _, meta_receipt_obj, _ = write_hashed_json(
                out_dir,
                "meta_core_promo_verify_receipt_v1.json",
                meta_receipt,
            )
            write_canon_json(out_dir / "meta_core_promo_verify_receipt_v1.json", meta_receipt_obj)

            if passed:
                if campaign_id.startswith("rsi_eudrs_u_"):
                    try:
                        _apply_eudrs_u_staged_registry_tree(
                            dispatch_ctx=dispatch_ctx,
                            bundle_obj=bundle_obj,
                            allowlists=allowlists,
                        )
                    except RuntimeError as exc:
                        reason_code = str(exc).strip()
                        if reason_code not in {"FORBIDDEN_PATH"}:
                            reason_code = "UNKNOWN"
                        return _write_promotion_receipt(
                            status="REJECTED",
                            reason=reason_code,
                            active_after_hash=None,
                        )

                state_root = Path(dispatch_ctx["state_root"])
                if len(state_root.parents) < 3:
                    raise RuntimeError("MISSING_STATE_INPUT")
                source_run_root_rel = state_root.parents[2].name
                binding_without_id = {
                    "schema_version": "omega_activation_binding_v1",
                    "tick_u64": int(tick_u64),
                    "campaign_id": campaign_id,
                    "capability_id": capability_id,
                    "promotion_bundle_hash": promotion_bundle_hash,
                    "activation_key": activation_key,
                    "source_run_root_rel": source_run_root_rel,
                    "subverifier_receipt_hash": canon_hash_obj(subverifier_receipt),
                    "meta_core_promo_verify_receipt_hash": canon_hash_obj(meta_receipt_obj),
                }
                native_module = bundle_obj.get("native_module")
                if isinstance(native_module, dict):
                    binding_without_id["native_module"] = native_module
                    native_module_for_receipt = native_module
                if campaign_id == "rsi_knowledge_transpiler_v1":
                    try:
                        runtime_contract_hash = _require_sha256_hash(
                            bundle_obj.get("runtime_contract_hash"),
                            field="runtime_contract_hash",
                        )
                        healthcheck_vectors_hash = _require_sha256_hash(
                            bundle_obj.get("healthcheck_vectors_hash"),
                            field="healthcheck_vectors_hash",
                        )
                        restricted_ir_hash = _require_sha256_hash(
                            bundle_obj.get("restricted_ir_hash"),
                            field="restricted_ir_hash",
                        )
                        source_merkle_hash = _require_sha256_hash(
                            bundle_obj.get("source_merkle_hash"),
                            field="source_merkle_hash",
                        )
                        build_proof_hash = _require_sha256_hash(
                            bundle_obj.get("build_proof_hash"),
                            field="build_proof_hash",
                        )
                    except RuntimeError:
                        return _write_promotion_receipt(
                            status="REJECTED",
                            reason="UNKNOWN",
                            active_after_hash=None,
                        )
                    binding_without_id["native_runtime_contract_hash"] = runtime_contract_hash
                    binding_without_id["native_healthcheck_vectors_hash"] = healthcheck_vectors_hash
                    binding_without_id["native_restricted_ir_hash"] = restricted_ir_hash
                    binding_without_id["native_src_merkle_hash"] = source_merkle_hash
                    binding_without_id["native_build_proof_hash"] = build_proof_hash
                    native_runtime_contract_hash_for_receipt = runtime_contract_hash
                    native_healthcheck_vectors_hash_for_receipt = healthcheck_vectors_hash
                binding_payload = dict(binding_without_id)
                binding_payload["binding_id"] = canon_hash_obj(binding_without_id)
                require_no_absolute_paths(binding_payload)
                validate_schema(binding_payload, "omega_activation_binding_v1")
                binding_state_path = out_dir / "omega_activation_binding_v1.json"
                write_canon_json(binding_state_path, binding_payload)

                binding_hex = str(binding_payload["binding_id"]).split(":", 1)[1]
                activation_bundle_dir, activation_manifest_hash = _build_meta_core_activation_bundle(
                    out_dir=out_dir,
                    binding_payload=binding_payload,
                    binding_hash_hex8=binding_hex[:8],
                )
                status = "PROMOTED"
                reason = None
                active_after = activation_manifest_hash
                dispatch_ctx["meta_core_activation_bundle_dir"] = str(activation_bundle_dir.resolve())
                dispatch_ctx["activation_binding_id"] = str(binding_payload["binding_id"])
            else:
                status = "REJECTED"
                reason = "META_CORE_REJECT"

    return _write_promotion_receipt(
        status=status,
        reason=reason,
        active_after_hash=active_after,
    )


__all__ = ["run_promotion", "run_subverifier"]
