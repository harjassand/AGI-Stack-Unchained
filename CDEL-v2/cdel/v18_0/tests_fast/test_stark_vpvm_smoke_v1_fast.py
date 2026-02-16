from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.vpvm_stark_verifier_v1 import verify_stark_vm_proof_v1

from .test_pclp_stark_vm_v1_fast import _build_valid_qre_pclp_ctx


def test_stark_vpvm_smoke_v1_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)
    ok, reason = verify_stark_vm_proof_v1(
        vpvm_config_obj=dict(ctx["vpvm_config_obj"]),
        poseidon_params_bin=bytes(ctx["poseidon_params_bytes"]),
        vpvm_public_inputs_obj=dict(ctx["vpvm_public_inputs_obj"]),
        program_bytes=bytes(ctx["program_bytes"]),
        proof_bytes=bytes(ctx["proof_bytes"]),
        lut_bytes=bytes(ctx["lut_bytes"]),
        examples=list(ctx["examples"]),
        weights_before=ctx["weights_before"],
        weights_after=ctx["weights_after"],
    )
    assert ok is True
    assert reason == ""
