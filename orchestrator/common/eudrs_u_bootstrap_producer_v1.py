"""Shared EUDRS-U bootstrap producer entrypoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import fail, load_canon_dict

from orchestrator.common.eudrs_u_dmpl_phase4_producer_v1 import emit_dmpl_phase4_promotion_bundle_v1


def _latest_hashed_json(dir_path: Path, glob_pat: str) -> dict[str, Any] | None:
    rows = sorted(dir_path.glob(glob_pat), key=lambda p: p.as_posix())
    if not rows:
        return None
    payload = load_canon_dict(rows[-1])
    if isinstance(payload, dict):
        return payload
    return None


def _template_state_dir(kind: str) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    mapping = {
        "qxrl_train": repo_root / "runs" / "eudrs_u_bootstrap_qxrl_train" / "daemon" / "rsi_eudrs_u_qxrl_train_v1" / "state",
        "dmpl_plan": repo_root / "runs" / "eudrs_u_bootstrap_dmpl_plan" / "daemon" / "rsi_eudrs_u_dmpl_plan_v1" / "state",
    }
    return mapping[str(kind)]


def emit_eudrs_u_bootstrap_promotion_bundle_v1(state_dir: Path, *, producer_kind: str) -> dict[str, Any]:
    kind = str(producer_kind).strip()
    if kind not in {"qxrl_train", "dmpl_plan"}:
        fail("SCHEMA_FAIL")
    state_dir = Path(state_dir).resolve()
    template_dir = _template_state_dir(kind)
    if template_dir.exists() and template_dir.is_dir():
        if state_dir.exists():
            shutil.rmtree(state_dir)
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template_dir, state_dir)
        copied = _latest_hashed_json(state_dir / "promotion", "sha256_*.eudrs_u_promotion_bundle_v1.json")
        if copied is None:
            fail("MISSING_STATE_INPUT")
        return copied

    # Reuse the verifier-clean DMPL phase-4 producer; this emits a full staged tree
    # with QXRL + DMPL artifacts and the expected promotion bundle shape.
    return emit_dmpl_phase4_promotion_bundle_v1(
        state_dir=state_dir,
        producer_kind=f"bootstrap_{kind}",
    )


__all__ = ["emit_eudrs_u_bootstrap_promotion_bundle_v1"]
