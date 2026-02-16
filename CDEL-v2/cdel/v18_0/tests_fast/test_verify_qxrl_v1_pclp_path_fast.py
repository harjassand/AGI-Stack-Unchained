from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.verify_qxrl_v1 import verify_qxrl_v1

from .test_pclp_stark_vm_v1_fast import _build_valid_qre_pclp_ctx


def test_verify_qxrl_v1_uses_pclp_and_skips_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _build_valid_qre_pclp_ctx(tmp_path=tmp_path, monkeypatch=monkeypatch)

    # If legacy replay is called, fail loudly.
    import cdel.v18_0.eudrs_u.verify_qxrl_v1 as vmod

    monkeypatch.setattr(vmod, "replay_qxrl_training_v1", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("legacy replay called")))
    monkeypatch.setattr(
        vmod,
        "compute_qxrl_eval_scorecard_v1",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("legacy eval called")),
    )

    def _loader(ref: dict[str, str]) -> bytes:
        return ctx["bytes_by_id"][ref["artifact_id"]]

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(ctx["root_tuple_obj"]),
        system_manifest_obj=dict(ctx["system_manifest_obj"]),
        determinism_cert_obj=dict(ctx["determinism_cert_obj"]),
        registry_loader=_loader,
        mode="full",
    )
    assert ok is True
    assert reason == "EUDRSU_OK"
