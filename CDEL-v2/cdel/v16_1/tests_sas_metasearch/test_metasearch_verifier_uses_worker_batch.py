from __future__ import annotations

import types
from pathlib import Path

import cdel.v16_1.verify_rsi_sas_metasearch_v16_1 as verifier_module


def test_metasearch_verifier_uses_worker_batch(v16_1_run_root: Path, monkeypatch) -> None:
    state_dir = v16_1_run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"

    def _forbid(*_args, **_kwargs) -> None:
        raise AssertionError("unexpected subprocess.run in v16_1 verifier replay")

    monkeypatch.setattr(verifier_module, "subprocess", types.SimpleNamespace(run=_forbid), raising=True)
    assert verifier_module.verify(state_dir, mode="full") == "VALID"
