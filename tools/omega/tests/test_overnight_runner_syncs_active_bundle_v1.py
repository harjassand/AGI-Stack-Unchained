from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def test_sync_campaign_fixtures_copies_active_bundle_payload(tmp_path: Path) -> None:
    source_repo = tmp_path / "source_repo"
    worktree_repo = tmp_path / "worktree_repo"
    (source_repo / "campaigns").mkdir(parents=True, exist_ok=True)
    (worktree_repo / "campaigns").mkdir(parents=True, exist_ok=True)

    active_hex = "a" * 64
    (source_repo / "meta-core" / "active").mkdir(parents=True, exist_ok=True)
    (source_repo / "meta-core" / "active" / "ACTIVE_BUNDLE").write_text(active_hex + "\n", encoding="utf-8")
    (source_repo / "meta-core" / "active" / "PREV_ACTIVE_BUNDLE").write_text(active_hex + "\n", encoding="utf-8")
    bundle_src = source_repo / "meta-core" / "store" / "bundles" / active_hex / "omega"
    bundle_src.mkdir(parents=True, exist_ok=True)
    (bundle_src / "omega_activation_binding_v1.json").write_text("{}", encoding="utf-8")

    runner._sync_campaign_fixtures_into_worktree(source_repo_root=source_repo, repo_root=worktree_repo)

    assert (worktree_repo / "meta-core" / "active" / "ACTIVE_BUNDLE").read_text(encoding="utf-8").strip() == active_hex
    assert (worktree_repo / "meta-core" / "active" / "PREV_ACTIVE_BUNDLE").read_text(encoding="utf-8").strip() == active_hex
    assert (worktree_repo / "meta-core" / "store" / "bundles" / active_hex / "omega" / "omega_activation_binding_v1.json").exists()


def test_sync_campaign_fixtures_materializes_missing_val_fixture_tar(tmp_path: Path, monkeypatch) -> None:
    source_repo = tmp_path / "source_repo"
    worktree_repo = tmp_path / "worktree_repo"
    locator_dir = source_repo / "campaigns" / "rsi_sas_val_v17_0" / "workload" / "v16_1_fixture"
    locator_dir.mkdir(parents=True, exist_ok=True)
    (worktree_repo / "campaigns").mkdir(parents=True, exist_ok=True)

    locator_payload = {
        "schema_version": "v16_1_fixture_locator_v1",
        "fixture_tar_rel": "workload/v16_1_fixture/v16_1_state_fixture.tar.gz",
        "state_dir_in_tar": "rsi_sas_metasearch_v16_1/state",
    }
    (locator_dir / "fixture_locator_v1.json").write_text(
        json.dumps(locator_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    calls: list[tuple[str, str]] = []

    def _fake_materialize(*, repo_root: Path, campaign_id: str, fixture_rel: Path, state_dir_in_tar: str) -> bool:
        calls.append((campaign_id, state_dir_in_tar))
        target = (repo_root / "campaigns" / campaign_id / fixture_rel).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fixture-bytes")
        return True

    monkeypatch.setattr(runner, "_materialize_missing_fixture_tarball", _fake_materialize)
    runner._sync_campaign_fixtures_into_worktree(source_repo_root=source_repo, repo_root=worktree_repo)

    copied = (
        worktree_repo
        / "campaigns"
        / "rsi_sas_val_v17_0"
        / "workload"
        / "v16_1_fixture"
        / "v16_1_state_fixture.tar.gz"
    )
    assert copied.exists()
    assert copied.read_bytes() == b"fixture-bytes"
    assert calls == [("rsi_sas_val_v17_0", "rsi_sas_metasearch_v16_1/state")]
