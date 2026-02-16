from __future__ import annotations

import subprocess
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from cdel.v17_0.runtime.sas_val_run_v1 import _run_v16_1_smoke_downstream


def test_v16_1_smoke_fallback_generates_fresh_fixture(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    fixture_dir = config_dir / "workload" / "v16_1_fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_state = tmp_path / "fixture_state"
    fixture_state.mkdir(parents=True, exist_ok=True)

    locator = {
        "schema_version": "v16_1_fixture_locator_v1",
        "state_dir_rel": str(fixture_state),
    }
    write_canon_json(fixture_dir / "fixture_locator_v1.json", locator)

    repo_root = tmp_path / "repo"
    pack_path = repo_root / "campaigns" / "rsi_sas_metasearch_v16_1" / "rsi_sas_metasearch_pack_v16_1.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append([str(part) for part in cmd])
        cmd_parts = [str(part) for part in cmd]

        if cmd_parts[:3] == ["python3", "-m", "cdel.v16_1.verify_rsi_sas_metasearch_v16_1"]:
            if len([row for row in calls if row[:3] == cmd_parts[:3]]) == 1:
                return subprocess.CompletedProcess(cmd, 1, stdout="INVALID:BIN_HASH_MISMATCH\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="VALID\n", stderr="")

        if cmd_parts[:3] == ["python3", "-m", "orchestrator.rsi_sas_metasearch_v16_1"]:
            out_dir = Path(cmd_parts[cmd_parts.index("--out_dir") + 1])
            (out_dir / "daemon" / "rsi_sas_metasearch_v16_1" / "state").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="OK\n", stderr="")

        raise AssertionError(f"unexpected command: {cmd_parts}")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    receipt = _run_v16_1_smoke_downstream(
        state_dir=tmp_path / "state",
        config_dir=config_dir,
        repo_root=repo_root,
    )

    assert receipt["schema_version"] == "v16_1_smoke_receipt_v1"
    assert receipt["pass"] is True
    assert receipt["result"] == "VALID"
    assert str(receipt["fixture_state_dir"]).startswith("GENERATED:")
    assert len(calls) == 3
