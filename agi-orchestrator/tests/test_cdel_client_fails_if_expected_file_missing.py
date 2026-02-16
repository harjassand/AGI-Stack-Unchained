from pathlib import Path
import subprocess

import pytest

import orchestrator.cdel_client as cdel_client
from orchestrator.cdel_client import CDELClient


def test_cdel_client_fails_if_expected_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    root.mkdir()
    cfg_path = root / "config.toml"
    cfg_path.write_text("\n", encoding="utf-8")

    out_path = tmp_path / "missing.json"

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cdel_client.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="expected output files"):
        client._run(
            ["sealed", "worker", "--request", "req.json", "--out", str(out_path)],
            root_dir=root,
            config=cfg_path,
            expected_files=[out_path],
        )
