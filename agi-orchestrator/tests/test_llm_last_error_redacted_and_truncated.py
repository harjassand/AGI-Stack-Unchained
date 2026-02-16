from pathlib import Path
from types import SimpleNamespace

from cdel.sealed.evalue import parse_decimal

from orchestrator.run import _build_manifest


def test_llm_last_error_redacted_and_truncated(tmp_path: Path) -> None:
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

    token = "ghp_ABC1234567890"
    long_error = token + ("x" * 600)
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
        attempts=[{"llm_last_error": long_error}],
    )

    attempt = manifest["attempts"][0]
    redacted = attempt["llm_last_error"]
    assert "ghp_" not in redacted
    assert "**REDACTED**" in redacted
    assert len(redacted) <= 500
