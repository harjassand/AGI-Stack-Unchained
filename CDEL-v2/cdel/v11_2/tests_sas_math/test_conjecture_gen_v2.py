from __future__ import annotations

import subprocess
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v8_0.math_toolchain import compute_toolchain_id
from cdel.v11_2.sas_conjecture_selection_v2 import select_conjecture


def _write_toolchain(path: Path) -> dict:
    manifest = {
        "schema_version": "math_toolchain_manifest_v1",
        "checker_name": "stub",
        "checker_version": "v1",
        "checker_executable_hash": "sha256:" + "0" * 64,
        "library_name": "stub",
        "library_commit": "v1",
        "os": "macos",
        "arch": "arm64",
        "invocation_template": ["/usr/bin/false", "{entrypoint}"],
        "toolchain_id": "",
    }
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    write_canon_json(path, manifest)
    return manifest


def _write_config(path: Path) -> dict:
    config = {
        "schema_version": "sas_conjecture_gen_config_v2",
        "domain": "NAT_ARITH_EXT",
        "bundle_size": 4,
        "max_vars": 4,
        "max_depth": 6,
        "max_node_count": 40,
        "nat_lits": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        "require_ops": ["Mul", "Pow", "ListRange", "ListSum", "Dvd", "Prime"],
        "require_any_of": [["Mul", "Pow", "ListRange", "ListSum"], ["Dvd", "Prime", "Gcd", "Mod"]],
        "pow_exponent_form": "LIT_ONLY",
        "pow_exponent_lits": [0, 1, 2, 3, 4, 5],
        "mod_denominator_form": "NONZERO_LIT_ONLY",
        "mod_denominator_lits": [1, 2, 3, 4, 5, 6, 7, 8],
        "fn_const_bound": 8,
        "weights": {
            "NatTerm": {"Var": 20, "NatLit": 10, "Add": 20, "Mul": 20, "Pow": 8, "Gcd": 6, "Mod": 6, "Sub": 5, "Succ": 3, "Pred": 2, "ListLen": 5, "ListSum": 7, "ListProd": 3},
            "ListTerm": {"Var": 15, "ListNil": 5, "ListCons": 15, "ListAppend": 15, "ListRange": 25, "ListMap": 25},
            "FnTerm": {"FnSucc": 40, "FnAddConst": 35, "FnMulConst": 25},
            "Prop": {"EqNat": 30, "LeNat": 10, "LtNat": 10, "Dvd": 25, "Prime": 15, "EqListNat": 10},
        },
    }
    write_canon_json(path, config)
    return config


def _run_worker(tmp_path: Path) -> dict:
    state_dir = tmp_path / "state"
    config_path = tmp_path / "sas_conjecture_gen_config_v2.json"
    toolchain_path = tmp_path / "toolchain_manifest.json"
    _write_config(config_path)
    _write_toolchain(toolchain_path)

    seed = "sha256:" + "1" * 64
    cmd = [
        "python3",
        "-m",
        "cdel.v11_2.sealed_sas_conjecture_gen_worker_v2",
        "--state-dir",
        str(state_dir),
        "--config",
        str(config_path),
        "--toolchain-manifest",
        str(toolchain_path),
        "--generator-seed",
        seed,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, proc.stderr

    bundle_path = next((state_dir / "conjectures" / "bundles").glob("sha256_*.sas_conjecture_bundle_v2.json"))
    return load_bundle(bundle_path)


def load_bundle(path: Path) -> dict:
    from cdel.v1_7r.canon import load_canon_json

    return load_canon_json(path)


def test_conjecture_gen_v2_deterministic_bundle_hash(tmp_path):
    bundle_a = _run_worker(tmp_path / "run1")
    bundle_b = _run_worker(tmp_path / "run2")

    assert bundle_a["bundle_id"] == bundle_b["bundle_id"]
    selected_a = select_conjecture(bundle_a.get("conjectures") or [])
    selected_b = select_conjecture(bundle_b.get("conjectures") or [])
    assert selected_a.get("conjecture_id") == selected_b.get("conjecture_id")
    assert selected_a.get("statement_hash") == selected_b.get("statement_hash")


def test_conjecture_gen_v2_contains_unbound_ops(tmp_path):
    bundle = _run_worker(tmp_path)
    found = False
    for conj in bundle.get("conjectures") or []:
        if conj.get("status") != "ACCEPTED":
            continue
        op_counts = (conj.get("metrics") or {}).get("op_counts") or {}
        if int(op_counts.get("Pow", 0)) > 0 or int(op_counts.get("Prime", 0)) > 0 or int(op_counts.get("Dvd", 0)) > 0 or int(op_counts.get("ListSum", 0)) > 0:
            found = True
            break
    assert found
