from pathlib import Path
import subprocess

import pytest

import orchestrator.cdel_client as cdel_client
from orchestrator.cdel_client import CDELClient


def test_cdel_client_allows_empty_output_when_file_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    root.mkdir()
    cfg_path = root / "config.toml"
    cfg_path.write_text("\n", encoding="utf-8")

    out_path = tmp_path / "cert.json"
    out_path.write_text("{\"certificate\": {}}", encoding="utf-8")

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cdel_client.subprocess, "run", fake_run)
    result = client._run(
        ["sealed", "worker", "--request", "req.json", "--out", str(out_path)],
        root_dir=root,
        config=cfg_path,
        expected_files=[out_path],
    )

    assert result.returncode == 0
    assert client.command_log
