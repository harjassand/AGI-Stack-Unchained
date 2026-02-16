from pathlib import Path
import subprocess

import pytest

import orchestrator.cdel_client as cdel_client

from orchestrator.cdel_client import CDELClient


def test_cdel_client_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    client.init_workspace(root)

    cfg_path = root / "config.toml"
    result = client._run(["--help"], root_dir=root, config=cfg_path)
    assert result.stdout.strip() or result.stderr.strip()

    assert client.command_log
    for record in client.command_log:
        assert "--config" in record.argv

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cdel_client.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="empty output"):
        client._run(["init"], root_dir=root, config=cfg_path)
