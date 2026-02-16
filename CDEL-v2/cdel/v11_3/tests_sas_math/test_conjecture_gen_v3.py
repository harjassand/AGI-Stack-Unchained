from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v8_0.math_toolchain import compute_toolchain_id
from cdel.v11_3.sas_conjecture_ir_v3 import collect_used_binders, compute_metrics


def _dummy_toolchain_manifest(path: Path) -> Path:
    manifest = {
        "schema_version": "math_toolchain_manifest_v1",
        "checker_name": "dummy",
        "checker_version": "0",
        "checker_executable_hash": "sha256:" + "0" * 64,
        "library_name": "dummy",
        "library_commit": "0",
        "os": "linux",
        "arch": "x86_64",
        "invocation_template": ["/bin/false", "{entrypoint}"],
        "toolchain_id": "",
    }
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(path, manifest)
    return path


def _run_worker(tmp_path: Path, seed: str) -> str:
    root = Path(__file__).resolve().parents[4]
    state_dir = tmp_path / "state"
    config_path = root / "campaigns" / "rsi_sas_math_v11_3" / "sas_conjecture_gen_config_v3.json"
    toolchain_path = _dummy_toolchain_manifest(tmp_path / "toolchain.json")
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root / 'CDEL-v2'}" + (f":{existing}" if existing else "")
    cmd = [
        "python3",
        "-m",
        "cdel.v11_3.sealed_sas_conjecture_gen_worker_v3",
        "--state-dir",
        str(state_dir),
        "--config",
        str(config_path),
        "--toolchain-manifest",
        str(toolchain_path),
        "--generator-seed",
        seed,
    ]
    subprocess.run(cmd, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    bundle_paths = list((state_dir / "conjectures" / "bundles").glob("sha256_*.sas_conjecture_bundle_v3.json"))
    assert bundle_paths, "bundle missing"
    bundle = load_canon_json(bundle_paths[0])
    return str(bundle.get("bundle_id"))


def _gate_reason(conj_ir: dict) -> str:
    used = collect_used_binders(conj_ir.get("goal") or {})
    declared = {v.get("name") for v in (conj_ir.get("vars") or []) if isinstance(v, dict)}
    if not declared.issubset(used):
        return "UNUSED_BINDER"
    metrics = compute_metrics(conj_ir)
    if not metrics.get("has_lnat") or not metrics.get("has_rec_op"):
        return "NO_RECURSIVE_STRUCTURE"
    return ""


def test_gen_v3_deterministic_bundle_hash(tmp_path: Path) -> None:
    seed = "sha256:" + "1" * 64
    bundle_a = _run_worker(tmp_path / "run_a", seed)
    bundle_b = _run_worker(tmp_path / "run_b", seed)
    assert bundle_a == bundle_b


def test_gen_v3_rejects_unused_binders() -> None:
    conj_ir = {
        "schema_version": "sas_conjecture_ir_v3",
        "domain": "COMB_STRUCT_V1",
        "vars": [
            {"name": "xs", "type": "LNat"},
            {"name": "n", "type": "Nat"},
        ],
        "goal": {
            "op": "EqNat",
            "args": [
                {"op": "Len", "type": "Nat", "args": [{"op": "Var", "type": "LNat", "args": [], "name": "xs"}]},
                {"op": "Len", "type": "Nat", "args": [{"op": "Var", "type": "LNat", "args": [], "name": "xs"}]},
            ],
        },
    }
    assert _gate_reason(conj_ir) == "UNUSED_BINDER"


def test_gen_v3_requires_recursive_structure() -> None:
    conj_ir = {
        "schema_version": "sas_conjecture_ir_v3",
        "domain": "COMB_STRUCT_V1",
        "vars": [{"name": "n", "type": "Nat"}],
        "goal": {
            "op": "EqNat",
            "args": [
                {"op": "Var", "type": "Nat", "args": [], "name": "n"},
                {"op": "Var", "type": "Nat", "args": [], "name": "n"},
            ],
        },
    }
    assert _gate_reason(conj_ir) == "NO_RECURSIVE_STRUCTURE"
