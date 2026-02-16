#!/usr/bin/env python3
"""Untrusted Genesis Engine symbiotic optimizer (parameterizer-only, v0.2)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "CDEL-v2"):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    p = Path(rel)
    if not rel or p.is_absolute() or ".." in p.parts:
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return rel


def _load_strategy(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "ge_symbiotic_strategy_v0_2":
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return payload


def _load_active_ek(repo_root: Path, ek_id: str) -> dict[str, Any]:
    kernels_dir = repo_root / "authority" / "evaluation_kernels"
    for path in sorted(kernels_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        if not isinstance(payload, dict) or payload.get("schema_version") != "evaluation_kernel_v1":
            continue
        if canon_hash_obj(payload) == ek_id:
            validate_schema(payload, "evaluation_kernel_v1")
            return payload
    raise RuntimeError("INVALID:MISSING_STATE_INPUT")


def _load_build_recipes(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "authority" / "build_recipes" / "build_recipes_v1.json"
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "build_recipes_v1":
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    rows = payload.get("recipes")
    if not isinstance(rows, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    if not out:
        raise RuntimeError("INVALID:MISSING_STATE_INPUT")
    return out


def _resolve_recipe_id(recipes: list[dict[str, Any]], recipe_name: str | None) -> str:
    requested = str(recipe_name or "").strip()
    if requested:
        for row in recipes:
            if str(row.get("recipe_name", "")).strip() == requested:
                value = str(row.get("recipe_id", "")).strip()
                if value.startswith("sha256:"):
                    return value
                raise RuntimeError("INVALID:SCHEMA_FAIL")
        raise RuntimeError("INVALID:MISSING_STATE_INPUT")
    # v0.2 default: fast recipe.
    for row in recipes:
        if str(row.get("recipe_name", "")).strip() == "REPO_TESTS_FAST":
            value = str(row.get("recipe_id", "")).strip()
            if value.startswith("sha256:"):
                return value
            raise RuntimeError("INVALID:SCHEMA_FAIL")
    value = str(recipes[0].get("recipe_id", "")).strip()
    if not value.startswith("sha256:"):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return value


def _load_recent_artifacts(recent_runs_root: Path | None) -> list[dict[str, str]]:
    if recent_runs_root is None:
        return []
    if not recent_runs_root.exists() or not recent_runs_root.is_dir():
        return []
    picks: list[Path] = []
    patterns = ["**/*receipt*.json", "**/OMEGA_RUN_SCORECARD_v1.json", "**/OMEGA_PROMOTION_SUMMARY_v1.json"]
    for pattern in patterns:
        picks.extend(recent_runs_root.glob(pattern))
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in sorted(picks, key=lambda row: row.as_posix()):
        if not path.is_file():
            continue
        rel = path.relative_to(recent_runs_root).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        raw = path.read_bytes()
        rows.append({"path_rel": rel, "hash": _sha256_prefixed(raw)})
        if len(rows) >= 256:
            break
    return rows


def _collect_llm_trace(strategy: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    traces = strategy.get("llm_trace")
    if traces is None:
        return [], []
    if not isinstance(traces, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    out_rows: list[dict[str, str]] = []
    prompt_hashes: list[str] = []
    for row in traces:
        if not isinstance(row, dict):
            raise RuntimeError("INVALID:SCHEMA_FAIL")
        prompt = str(row.get("prompt", ""))
        response = str(row.get("response", ""))
        prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))
        response_hash = _sha256_prefixed(response.encode("utf-8"))
        prompt_hashes.append(prompt_hash)
        out_rows.append(
            {
                "prompt_hash": prompt_hash,
                "response_hash": response_hash,
            }
        )
    return out_rows, prompt_hashes


def _default_budgets() -> dict[str, int | str]:
    return {
        "cpu_ms_max": 600000,
        "wall_ms_max": 600000,
        "mem_mb_max": 4096,
        "disk_mb_max": 2048,
        "fds_max": 256,
        "procs_max": 64,
        "threads_max": 256,
        "net": "forbidden",
    }


def _merged_budgets(strategy: dict[str, Any]) -> dict[str, Any]:
    base = _default_budgets()
    overrides = strategy.get("budgets")
    if overrides is None:
        return base
    if not isinstance(overrides, dict):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    out = dict(base)
    for key, value in overrides.items():
        if key == "net":
            if str(value) != "forbidden":
                raise RuntimeError("INVALID:SCHEMA_FAIL")
            out["net"] = "forbidden"
            continue
        if key not in out:
            continue
        out[key] = int(value)
    return out


def _build_comment_patch(*, target_relpath: str, marker: str, repo_root: Path) -> bytes:
    import difflib

    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    before = target_path.read_text(encoding="utf-8")
    line = f"# ge_symbiotic_optimizer_v0_2:{marker}"
    if before.endswith("\n"):
        after = before + line + "\n"
    else:
        after = before + "\n" + line + "\n"
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    rows = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{target_relpath}",
            tofile=f"b/{target_relpath}",
            lineterm="",
        )
    )
    if not rows:
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _base_tree_id_best_effort(repo_root: Path) -> str:
    try:
        return compute_repo_base_tree_id(repo_root)
    except Exception:  # noqa: BLE001
        pass

    run = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        text=False,
        check=False,
    )
    if run.returncode != 0:
        raise RuntimeError("INVALID:MISSING_STATE_INPUT")

    files: list[dict[str, str]] = []
    for raw_rel in sorted(row for row in run.stdout.split(b"\x00") if row):
        rel = raw_rel.decode("utf-8")
        path = (repo_root / rel).resolve()
        if not path.exists() or not path.is_file():
            continue
        files.append(
            {
                "path": rel,
                "sha256": _sha256_prefixed(path.read_bytes()),
            }
        )
    return canon_hash_obj({"schema_version": "ge_ccap_base_tree_fallback_v1", "files": files})


def _build_eval_stage_list(active_ek: dict[str, Any]) -> list[dict[str, Any]]:
    stages = active_ek.get("stages")
    if not isinstance(stages, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in stages:
        if not isinstance(row, dict):
            raise RuntimeError("INVALID:SCHEMA_FAIL")
        item: dict[str, Any] = {"stage_name": str(row.get("stage_name", "")).strip()}
        if "required_b" in row:
            item["required_b"] = bool(row.get("required_b"))
        if "hard_gate_b" in row:
            item["hard_gate_b"] = bool(row.get("hard_gate_b"))
        if "timeout_ms_max_u64" in row:
            item["timeout_ms_max_u64"] = int(row.get("timeout_ms_max_u64"))
        out.append(item)
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)


def _emit_ccap_bundle(
    *,
    repo_root: Path,
    subrun_out_dir: Path,
    strategy: dict[str, Any],
    pins: dict[str, Any],
    auth_hash_value: str,
    active_ek: dict[str, Any],
    build_recipe_id: str,
    seed: int,
    inputs_hash: str,
    idx: int,
) -> dict[str, Any]:
    target_relpath = _normalize_relpath(
        str(strategy.get("target_relpath", "tools/omega/omega_benchmark_suite_v1.py")).strip()
    )
    marker = f"{inputs_hash.split(':', 1)[1][:16]}_{seed:016x}_{idx:04d}"
    patch_bytes = _build_comment_patch(target_relpath=target_relpath, marker=marker, repo_root=repo_root)
    patch_blob_id = _sha256_prefixed(patch_bytes)

    payload = {
        "kind": "PATCH",
        "patch_blob_id": patch_blob_id,
    }
    ccap_id = ccap_payload_id({"payload": payload})
    ccap_hex = ccap_id.split(":", 1)[1]

    base_tree_id = _base_tree_id_best_effort(repo_root)
    op_pool_ids = pins.get("active_op_pool_ids")
    dsbx_ids = pins.get("active_dsbx_profile_ids")
    if not isinstance(op_pool_ids, list) or not op_pool_ids:
        raise RuntimeError("INVALID:MISSING_STATE_INPUT")
    if not isinstance(dsbx_ids, list) or not dsbx_ids:
        raise RuntimeError("INVALID:MISSING_STATE_INPUT")

    eval_stages = _build_eval_stage_list(active_ek)
    final_suite_id = canon_hash_obj(
        {
            "schema_version": "ge_final_suite_v0_2",
            "build_recipe_id": build_recipe_id,
            "ek_id": pins["active_ek_id"],
        }
    )
    ccap_obj = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash_value,
            "dsbx_profile_id": str(dsbx_ids[0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(op_pool_ids[0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": payload,
        "build": {
            "build_recipe_id": build_recipe_id,
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": eval_stages,
            "final_suite_id": final_suite_id,
        },
        "budgets": _merged_budgets(strategy),
    }
    validate_schema(ccap_obj, "ccap_v1")

    ccap_dir = subrun_out_dir / "ccap"
    blobs_dir = ccap_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    patch_path = blobs_dir / f"sha256_{patch_blob_id.split(':', 1)[1]}.patch"
    patch_path.write_bytes(patch_bytes)
    ccap_path = ccap_dir / f"sha256_{ccap_hex}.ccap_v1.json"
    _write_json(ccap_path, ccap_obj)

    return {
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_path.relative_to(subrun_out_dir).as_posix(),
        "patch_blob_id": patch_blob_id,
        "patch_relpath": patch_path.relative_to(subrun_out_dir).as_posix(),
        "target_relpath": target_relpath,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ge_symbiotic_optimizer_v0_2")
    parser.add_argument("--subrun_out_dir", required=True)
    parser.add_argument("--strategy_config", required=True)
    parser.add_argument("--authority_pins_path", default=str(REPO_ROOT / "authority" / "authority_pins_v1.json"))
    parser.add_argument("--recent_runs_root", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model_id", default="ge_symbiotic_optimizer_v0_2")
    parser.add_argument("--max_ccaps", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = REPO_ROOT.resolve()
    subrun_out_dir = Path(args.subrun_out_dir).resolve()
    strategy_path = Path(args.strategy_config).resolve()
    authority_pins_path = Path(args.authority_pins_path).resolve()
    recent_runs_root = Path(args.recent_runs_root).resolve() if str(args.recent_runs_root).strip() else None
    seed = int(args.seed)
    model_id = str(args.model_id).strip() or "ge_symbiotic_optimizer_v0_2"
    max_ccaps = max(1, min(8, int(args.max_ccaps)))

    if authority_pins_path != (repo_root / "authority" / "authority_pins_v1.json").resolve():
        raise RuntimeError("INVALID:SCHEMA_FAIL")

    strategy = _load_strategy(strategy_path)
    pins = load_authority_pins(repo_root)
    auth_hash_value = auth_hash(pins)
    active_ek = _load_active_ek(repo_root, str(pins["active_ek_id"]))
    recipes = _load_build_recipes(repo_root)
    build_recipe_id = _resolve_recipe_id(recipes, str(strategy.get("build_recipe_name", "")).strip() or None)
    recent_artifacts = _load_recent_artifacts(recent_runs_root)
    llm_trace_rows, prompt_hashes = _collect_llm_trace(strategy)

    fingerprint_inputs = {
        "schema_version": "ge_run_inputs_fingerprint_inputs_v1",
        "authority_pins_hash": _sha256_prefixed(canon_bytes(pins)),
        "strategy_hash": _sha256_prefixed(canon_bytes(strategy)),
        "recent_artifacts": recent_artifacts,
        "seed": seed,
        "model_id": model_id,
        "prompt_hashes": prompt_hashes,
    }
    inputs_hash = _sha256_prefixed(canon_bytes(fingerprint_inputs))
    fingerprint = {
        "schema_version": "ge_run_inputs_fingerprint_v1",
        "inputs_hash": inputs_hash,
        "seed": seed,
        "model_id": model_id,
        "prompt_hashes": prompt_hashes,
    }

    subrun_out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(subrun_out_dir / "ge_run_inputs_fingerprint_v1.json", fingerprint)
    _write_json(
        subrun_out_dir / "ge_prompt_response_hashes_v1.json",
        {
            "schema_version": "ge_prompt_response_hashes_v1",
            "inputs_hash": inputs_hash,
            "rows": llm_trace_rows,
        },
    )

    emits: list[dict[str, Any]] = []
    for idx in range(max_ccaps):
        emits.append(
            _emit_ccap_bundle(
                repo_root=repo_root,
                subrun_out_dir=subrun_out_dir,
                strategy=strategy,
                pins=pins,
                auth_hash_value=auth_hash_value,
                active_ek=active_ek,
                build_recipe_id=build_recipe_id,
                seed=seed,
                inputs_hash=inputs_hash,
                idx=idx,
            )
        )

    _write_json(
        subrun_out_dir / "ge_symbiotic_optimizer_summary_v0_2.json",
        {
            "schema_version": "ge_symbiotic_optimizer_summary_v0_2",
            "inputs_hash": inputs_hash,
            "auth_hash": auth_hash_value,
            "ccaps": emits,
        },
    )
    print(
        json.dumps(
            {
                "status": "OK",
                "inputs_hash": inputs_hash,
                "ccap_count_u64": len(emits),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
