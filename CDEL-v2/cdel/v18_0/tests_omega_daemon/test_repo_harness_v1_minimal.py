from __future__ import annotations

from pathlib import Path

from cdel.v18_0.realize.repo_harness_v1 import run_repo_harness
from cdel.v1_7r.canon import write_canon_json


def _write_authority_pins(repo_root: Path) -> dict[str, str]:
    pins = {
        "schema_version": "authority_pins_v1",
        "re1_constitution_state_id": "sha256:" + ("1" * 64),
        "re2_verifier_state_id": "sha256:" + ("2" * 64),
        "active_ek_id": "sha256:" + ("3" * 64),
        "active_op_pool_ids": ["sha256:" + ("4" * 64)],
        "active_dsbx_profile_ids": ["sha256:" + ("5" * 64)],
        "env_contract_id": "sha256:" + ("6" * 64),
        "toolchain_root_id": "sha256:" + ("7" * 64),
        "ccap_patch_allowlists_id": "sha256:" + ("c" * 64),
        "canon_version_ids": {
            "ccap_can_v": "sha256:" + ("8" * 64),
            "ir_can_v": "sha256:" + ("9" * 64),
            "op_can_v": "sha256:" + ("a" * 64),
            "obs_can_v": "sha256:" + ("b" * 64),
        },
    }
    write_canon_json(repo_root / "authority" / "authority_pins_v1.json", pins)
    return {
        "env_contract_id": pins["env_contract_id"],
        "toolchain_root_id": pins["toolchain_root_id"],
        "dsbx_profile_id": pins["active_dsbx_profile_ids"][0],
    }


def test_repo_harness_minimal_success(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    applied_tree = tmp_path / "applied"
    sandbox_root = tmp_path / "sandbox"
    repo_root.mkdir(parents=True)
    applied_tree.mkdir(parents=True)
    (applied_tree / "hello.txt").write_text("hello\n", encoding="utf-8")

    ids = _write_authority_pins(repo_root)

    recipe = {
        "recipe_name": "E2E_MINIMAL",
        "commands": [["python3", "-c", "print('ok')"]],
        "env_allowlist": ["PYTHONPATH"],
        "cwd_policy": "repo_root",
        "out_capture_policy": {"mode": "none"},
    }
    recipe_id = "sha256:" + __import__("hashlib").sha256(__import__("json").dumps(
        recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    write_canon_json(
        repo_root / "authority" / "build_recipes" / "build_recipes_v1.json",
        {
            "schema_version": "build_recipes_v1",
            "recipes": [{**recipe, "recipe_id": recipe_id}],
        },
    )

    result = run_repo_harness(
        repo_root=repo_root,
        applied_tree_checkout_dir=applied_tree,
        build_recipe_id=recipe_id,
        budgets={
            "cpu_ms_max": 1000,
            "wall_ms_max": 10000,
            "mem_mb_max": 1024,
            "disk_mb_max": 1024,
            "fds_max": 256,
            "procs_max": 64,
            "threads_max": 64,
            "net": "forbidden",
        },
        env_contract_id=ids["env_contract_id"],
        dsbx_profile_id=ids["dsbx_profile_id"],
        toolchain_root_id=ids["toolchain_root_id"],
        sandbox_root=sandbox_root,
    )

    assert result["ok"] is True
    assert str(result["out_tree_id"]).startswith("sha256:")
    assert str(result["transcript_id"]).startswith("sha256:")
    assert str(result["logs_hash"]).startswith("sha256:")
