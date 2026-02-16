from pathlib import Path
from types import SimpleNamespace

from cdel.sealed.evalue import parse_decimal

from orchestrator.run import _build_manifest


def test_manifest_records_llm_config_and_usage(tmp_path: Path) -> None:
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

    llm_info = {
        "backend": "mock",
        "replay_path": None,
        "cache_dir": "/tmp/llm_cache",
        "max_prompt_chars": 10,
        "max_response_chars": 20,
        "max_calls": 3,
        "calls_used": 2,
        "calls": [],
    }

    manifest = _build_manifest(
        run_id="test-run",
        root_dir=tmp_path,
        dev_config=tmp_path / "dev.toml",
        heldout_config=tmp_path / "heldout.toml",
        dev_sealed=dev_sealed,
        heldout_sealed=heldout_sealed,
        seed_key="sealed-seed",
        min_dev_diff_sum=1,
        max_attempts=0,
        accepted=False,
        reason="test",
        commands=[],
        attempts=[],
        llm_info=llm_info,
    )

    llm = manifest["llm"]
    assert llm["backend"] == "mock"
    assert llm["cache_dir"] == "/tmp/llm_cache"
    assert llm["max_prompt_chars"] == 10
    assert llm["max_response_chars"] == 20
    assert llm["max_calls"] == 3
    assert llm["calls_used"] == 2
