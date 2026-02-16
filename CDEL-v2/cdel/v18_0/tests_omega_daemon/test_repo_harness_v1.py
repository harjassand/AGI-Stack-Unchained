from __future__ import annotations

from pathlib import Path

from cdel.v18_0.realize.repo_harness_v1 import run_repo_harness
from cdel.v1_7r.canon import write_canon_json


def _write_authority(repo_root: Path, *, recipe_id: str) -> dict[str, str]:
    ids = {
        "dsbx_profile_id": "sha256:" + ("1" * 64),
        "env_contract_id": "sha256:" + ("2" * 64),
        "toolchain_root_id": "sha256:" + ("3" * 64),
    }
    write_canon_json(
        repo_root / "authority" / "authority_pins_v1.json",
        {
            "schema_version": "authority_pins_v1",
            "re1_constitution_state_id": "sha256:" + ("a" * 64),
            "re2_verifier_state_id": "sha256:" + ("b" * 64),
            "active_ek_id": "sha256:" + ("c" * 64),
            "active_op_pool_ids": ["sha256:" + ("d" * 64)],
            "active_dsbx_profile_ids": [ids["dsbx_profile_id"]],
            "env_contract_id": ids["env_contract_id"],
            "toolchain_root_id": ids["toolchain_root_id"],
            "ccap_patch_allowlists_id": "sha256:" + ("8" * 64),
            "canon_version_ids": {
                "ccap_can_v": "sha256:" + ("e" * 64),
                "ir_can_v": "sha256:" + ("f" * 64),
                "op_can_v": "sha256:" + ("0" * 64),
                "obs_can_v": "sha256:" + ("9" * 64),
            },
        },
    )
    write_canon_json(
        repo_root / "authority" / "build_recipes" / "build_recipes_v1.json",
        {
            "schema_version": "build_recipes_v1",
            "recipes": [
                {
                    "recipe_id": recipe_id,
                    "recipe_name": "UNIT",
                    "commands": [
                        [
                            "python3",
                            "-c",
                            "from pathlib import Path; Path('artifact.txt').write_text('ok\\n',encoding='utf-8')",
                        ]
                    ],
                    "env_allowlist": ["PYTHONPATH"],
                    "cwd_policy": "repo_root",
                    "out_capture_policy": {
                        "mode": "copy_glob",
                        "patterns": ["artifact.txt"],
                    },
                }
            ],
        },
    )
    return ids


def _budgets() -> dict[str, int | str]:
    return {
        "cpu_ms_max": 10_000,
        "wall_ms_max": 10_000,
        "mem_mb_max": 4_096,
        "disk_mb_max": 256,
        "fds_max": 256,
        "procs_max": 64,
        "threads_max": 64,
        "net": "forbidden",
    }


def test_repo_harness_generates_stable_out_and_transcript_hashes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    applied_tree = tmp_path / "applied_tree"
    recipe_id = "sha256:" + ("7" * 64)
    ids = _write_authority(repo_root, recipe_id=recipe_id)
    applied_tree.mkdir(parents=True, exist_ok=True)
    (applied_tree / "README.md").write_text("seed\n", encoding="utf-8")

    run_a = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=applied_tree,
        build_recipe_id=recipe_id,
        budgets=_budgets(),
        env_contract_id=ids["env_contract_id"],
        dsbx_profile_id=ids["dsbx_profile_id"],
        toolchain_root_id=ids["toolchain_root_id"],
        sandbox_root=tmp_path / "sandbox_a",
    )
    run_b = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=applied_tree,
        build_recipe_id=recipe_id,
        budgets=_budgets(),
        env_contract_id=ids["env_contract_id"],
        dsbx_profile_id=ids["dsbx_profile_id"],
        toolchain_root_id=ids["toolchain_root_id"],
        sandbox_root=tmp_path / "sandbox_b",
    )

    assert run_a["ok"] is True
    assert run_b["ok"] is True
    assert str(run_a["out_tree_id"]).startswith("sha256:")
    assert str(run_a["transcript_id"]).startswith("sha256:")
    assert str(run_a["logs_hash"]).startswith("sha256:")
    assert run_a["out_tree_id"] == run_b["out_tree_id"]
    assert run_a["transcript_id"] == run_b["transcript_id"]


def test_repo_harness_rejects_unknown_recipe_id(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    applied_tree = tmp_path / "applied_tree"
    recipe_id = "sha256:" + ("7" * 64)
    ids = _write_authority(repo_root, recipe_id=recipe_id)
    applied_tree.mkdir(parents=True, exist_ok=True)
    (applied_tree / "README.md").write_text("seed\n", encoding="utf-8")

    run = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=applied_tree,
        build_recipe_id="sha256:" + ("8" * 64),
        budgets=_budgets(),
        env_contract_id=ids["env_contract_id"],
        dsbx_profile_id=ids["dsbx_profile_id"],
        toolchain_root_id=ids["toolchain_root_id"],
        sandbox_root=tmp_path / "sandbox",
    )
    assert run["ok"] is False
    assert run["refutation"]["code"] == "EVAL_STAGE_FAIL"
