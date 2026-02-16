from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import orchestrator.cdel_client as cdel_client
from orchestrator.cdel_client import CDELClient
from orchestrator.run import _build_manifest
from cdel.sealed.evalue import parse_decimal


def test_manifest_redacts_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = CDELClient()
    root = tmp_path / "workspace"
    root.mkdir()
    cfg_path = root / "config.toml"
    cfg_path.write_text("\n", encoding="utf-8")

    monkeypatch.setenv("API_TOKEN", "secret-token")
    monkeypatch.setenv("NORMAL_ENV", "ok")

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="token=ghp_ABC1234567890\n",
            stderr="auth=github_pat_ABC_def_123456\n",
        )

    monkeypatch.setattr(cdel_client.subprocess, "run", fake_run)
    client._run(
        ["--help"],
        root_dir=root,
        config=cfg_path,
        env_overrides={"PASSWORD": "supersecret"},
    )

    schedule = SimpleNamespace(
        name="p_series",
        exponent=2,
        coefficient=parse_decimal("0.5"),
    )
    dev_sealed = SimpleNamespace(
        eval_suite_hash="dev-suite",
        eval_harness_hash="dev-harness",
        alpha_total=parse_decimal("1e-4"),
        alpha_schedule=schedule,
    )
    heldout_sealed = SimpleNamespace(
        eval_suite_hash="heldout-suite",
        eval_harness_hash="heldout-harness",
        alpha_total=parse_decimal("1e-4"),
        alpha_schedule=schedule,
    )

    manifest = _build_manifest(
        run_id="test-run",
        root_dir=root,
        dev_config=cfg_path,
        heldout_config=cfg_path,
        dev_sealed=dev_sealed,
        heldout_sealed=heldout_sealed,
        seed_key="sealed-seed",
        min_dev_diff_sum=1,
        max_attempts=0,
        accepted=False,
        reason="test",
        commands=client.command_log,
        attempts=[],
        llm_info={},
    )

    record = manifest["commands"][0]
    assert record["env"]["API_TOKEN"] == "**REDACTED**"
    assert record["env"]["PASSWORD"] == "**REDACTED**"
    assert record["env"]["NORMAL_ENV"] == "ok"
    assert record["env_overrides"]["PASSWORD"] == "**REDACTED**"
    assert "ghp_" not in record["stdout_preview"]
    assert "github_pat_" not in record["stderr_preview"]
    assert "**REDACTED**" in record["stdout_preview"]
