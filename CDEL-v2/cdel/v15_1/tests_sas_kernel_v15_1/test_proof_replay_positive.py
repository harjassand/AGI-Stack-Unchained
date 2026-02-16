from __future__ import annotations

from pathlib import Path

from cdel.v15_1.verify_rsi_sas_kernel_v15_1 import _sealed_lean_replay, _validate_toolchain_manifest

from .utils import repo_root


def test_proof_replay_positive(tmp_path: Path) -> None:
    root = repo_root()
    schema_dir = root / "Genesis" / "schema" / "v15_1"
    lean_manifest = root / "campaigns" / "rsi_sas_kernel_v15_1" / "toolchain_manifest_lean_v1.json"
    lean_tool = _validate_toolchain_manifest(lean_manifest, schema_dir)

    state_dir = tmp_path / "state"
    attempts = state_dir / "attempts"
    attempts.mkdir(parents=True, exist_ok=True)

    preamble = attempts / "SASKernelBrainPreambleV15_1.lean"
    preamble.write_text(
        "def decide (n : Nat) : Nat := n\n"
        "theorem preamble_ok (n : Nat) : decide n = decide n := by\n"
        "  rfl\n",
        encoding="utf-8",
    )

    proof = attempts / "kernel.brain.proof.lean"
    proof.write_text(
        "theorem validate_plan_sound (n : Nat) : n = n := by\n"
        "  rfl\n\n"
        "theorem run_preserves_safety (n : Nat) : n = n := by\n"
        "  rfl\n",
        encoding="utf-8",
    )

    receipt = _sealed_lean_replay(lean_tool=lean_tool, proof_path=proof, state_dir=state_dir)
    assert receipt["schema_version"] == "lean_replay_receipt_v1"
    assert len(receipt["runs"]) == 2
    assert all(run["returncode"] == 0 for run in receipt["runs"])
