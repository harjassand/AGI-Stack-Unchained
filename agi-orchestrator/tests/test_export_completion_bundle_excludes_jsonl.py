from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_completion_bundle import collect_bundle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_export_bundle_excludes_jsonl(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "suites").mkdir()
    (repo_root / "configs").mkdir()
    (repo_root / "sealed_suites").mkdir()
    (repo_root / "runs" / "capstone_ae").mkdir(parents=True)

    _write_json(repo_root / "suites" / "env_dev_current.json", {"domain": "env-gridworld-v1", "suite_hash": "abc"})
    (repo_root / "configs" / "sealed_env_dev.toml").write_text(
        "\n".join(
            [
                "[sealed]",
                "eval_harness_id = \"env-harness-v1\"",
                "eval_harness_hash = \"env-harness-v1-hash\"",
                "eval_suite_hash = \"abc\"",
                "episodes = 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "sealed_suites" / "abc.jsonl").write_text("{\"episode\":0}\n", encoding="utf-8")

    _write_json(repo_root / "runs" / "capstone_ae" / "capstone_ae_summary.json", {"run_id": "capstone_ae"})
    _write_json(repo_root / "runs" / "capstone_ae" / "tooluse_heldout_cert.json", {"ok": True})

    bundle_dir = repo_root / "completion_bundle"
    collect_bundle(repo_root=repo_root, bundle_dir=bundle_dir, capstone_dir=repo_root / "runs" / "capstone_ae")

    assert (bundle_dir / "capstone_ae_summary.json").exists()
    assert (bundle_dir / "manifest.json").exists()
    for path in bundle_dir.rglob("*.jsonl"):
        pytest.fail(f"bundle should not include jsonl: {path}")
