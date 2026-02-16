from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.verify_ccap_v1 import verify
from cdel.v1_7r.canon import load_canon_json, write_canon_json


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _write_repo_fixture(repo_root: Path) -> dict[str, str]:
    (repo_root / "tools" / "omega").mkdir(parents=True, exist_ok=True)
    (repo_root / "authority" / "build_recipes").mkdir(parents=True, exist_ok=True)

    (repo_root / "tools" / "omega" / "score_target_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo_root / "tools" / "omega" / "score_probe_v1.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        "import argparse\n"
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def main() -> None:\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--ticks')\n"
        "    parser.add_argument('--series_prefix', required=True)\n"
        "    parser.add_argument('--runs_root', required=True)\n"
        "    args = parser.parse_args()\n"
        "\n"
        "    module_path = Path(__file__).with_name('score_target_module.py')\n"
        "    compile(module_path.read_text(encoding='utf-8'), str(module_path), 'exec')\n"
        "\n"
        "    run_dir = Path(args.runs_root) / str(args.series_prefix)\n"
        "    run_dir.mkdir(parents=True, exist_ok=True)\n"
        "    scorecard = {\n"
        "        'schema_version': 'omega_run_scorecard_v1',\n"
        "        'median_stps_non_noop_q32': 123,\n"
        "        'non_noop_ticks_per_min': 1.5,\n"
        "        'promotions_u64': 7,\n"
        "        'activation_success_u64': 4,\n"
        "    }\n"
        "    (run_dir / 'OMEGA_RUN_SCORECARD_v1.json').write_text(\n"
        "        json.dumps(scorecard, sort_keys=True, separators=(',', ':')) + '\\n',\n"
        "        encoding='utf-8',\n"
        "    )\n"
        "\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
        encoding="utf-8",
    )

    allowlists = {
        "schema_version": "ccap_patch_allowlists_v1",
        "allow_prefixes": ["tools/omega/"],
        "forbid_prefixes": ["authority/", "meta-core/"],
        "forbid_exact_paths": [],
    }
    write_canon_json(repo_root / "authority" / "ccap_patch_allowlists_v1.json", allowlists)

    recipe_id = "sha256:" + ("4" * 64)
    write_canon_json(
        repo_root / "authority" / "build_recipes" / "build_recipes_v1.json",
        {
            "schema_version": "build_recipes_v1",
            "recipes": [
                {
                    "recipe_id": recipe_id,
                    "recipe_name": "REPO_TESTS_FAST",
                    "commands": [["python3", "-c", "print('realize ok')"]],
                    "env_allowlist": ["PYTHONPATH"],
                    "cwd_policy": "repo_root",
                    "out_capture_policy": {"mode": "none"},
                }
            ],
        },
    )

    pins = {
        "schema_version": "authority_pins_v1",
        "re1_constitution_state_id": "sha256:" + ("1" * 64),
        "re2_verifier_state_id": "sha256:" + ("2" * 64),
        "active_ek_id": "sha256:" + ("3" * 64),
        "active_op_pool_ids": ["sha256:" + ("5" * 64)],
        "active_dsbx_profile_ids": ["sha256:" + ("6" * 64)],
        "env_contract_id": "sha256:" + ("7" * 64),
        "toolchain_root_id": "sha256:" + ("8" * 64),
        "ccap_patch_allowlists_id": canon_hash_obj(allowlists),
        "canon_version_ids": {
            "ccap_can_v": "sha256:" + ("9" * 64),
            "ir_can_v": "sha256:" + ("a" * 64),
            "op_can_v": "sha256:" + ("b" * 64),
            "obs_can_v": "sha256:" + ("c" * 64),
        },
    }
    write_canon_json(repo_root / "authority" / "authority_pins_v1.json", pins)
    return {
        "recipe_id": recipe_id,
        "allowlists_hash": str(pins["ccap_patch_allowlists_id"]),
    }


def test_ccap_score_runs_on_workspace_v1(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], cwd=repo_root)

    ids = _write_repo_fixture(repo_root)
    _run(["git", "add", "-A"], cwd=repo_root)

    pins = load_authority_pins(repo_root)
    base_tree_id = compute_repo_base_tree_id(repo_root)

    subrun_root = tmp_path / "subrun"
    receipt_out_dir = tmp_path / "receipt"
    (subrun_root / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)

    patch_bytes = (
        "diff --git a/tools/omega/score_target_module.py b/tools/omega/score_target_module.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/tools/omega/score_target_module.py\n"
        "+++ b/tools/omega/score_target_module.py\n"
        "@@ -1 +1 @@\n"
        "-VALUE = 1\n"
        "+def broken(\n"
    ).encode("utf-8")
    patch_blob_id = f"sha256:{hashlib.sha256(patch_bytes).hexdigest()}"
    patch_path = subrun_root / "ccap" / "blobs" / f"sha256_{patch_blob_id.split(':', 1)[1]}.patch"
    patch_path.write_bytes(patch_bytes)

    ccap_payload = {
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
        "payload": {
            "kind": "PATCH",
            "patch_blob_id": patch_blob_id,
        },
        "build": {
            "build_recipe_id": ids["recipe_id"],
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "final_suite_id": "sha256:" + ("d" * 64),
        },
        "budgets": {
            "cpu_ms_max": 30000,
            "wall_ms_max": 30000,
            "mem_mb_max": 2048,
            "disk_mb_max": 2048,
            "fds_max": 256,
            "procs_max": 64,
            "threads_max": 64,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap_payload)
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    write_canon_json(subrun_root / ccap_relpath, ccap_payload)

    monkeypatch.setattr(
        "cdel.v18_0.ek.ek_runner_v1._load_active_ek",
        lambda _repo_root, _expected_ek_id: {
            "schema_version": "evaluation_kernel_v1",
            "stages": [
                {"stage_name": "REALIZE"},
                {"stage_name": "SCORE"},
                {"stage_name": "FINAL_AUDIT"},
            ],
            "scoring_impl": {
                "code_ref": {
                    "path": "tools/omega/score_probe_v1.py",
                }
            },
        },
    )

    receipt, code = verify(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=ccap_relpath,
        receipt_out_dir=receipt_out_dir,
    )

    assert code == "EVAL_STAGE_FAIL"
    assert receipt["decision"] == "REJECT"
    assert receipt["eval_status"] == "FAIL"

    cert_paths = sorted((subrun_root / "ccap" / "refutations").glob("sha256_*.ccap_refutation_cert_v1.json"))
    assert cert_paths
    cert = load_canon_json(cert_paths[-1])
    assert cert["refutation_code"] == "EVAL_STAGE_FAIL"
