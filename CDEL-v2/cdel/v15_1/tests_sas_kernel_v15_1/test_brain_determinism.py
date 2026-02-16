from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, load_canon_json
from orchestrator.brain_ref_v15_1 import brain_decide_v15_1

from .utils import repo_root


def test_brain_determinism() -> None:
    root = repo_root()
    context_path = (
        root
        / "daemon"
        / "rsi_sas_kernel_v15_1"
        / "config"
        / "brain_corpus"
        / "cases"
        / "sha256:01693967a5e5ed31f400420f6c93d8f3878cd9b68af8fd4a2f46252f9f0afec4"
        / "brain_context_v1.json"
    )
    if not context_path.exists():
        # Fallback to first available case in deterministic lexicographic order.
        context_path = sorted(
            (
                root
                / "daemon"
                / "rsi_sas_kernel_v15_1"
                / "config"
                / "brain_corpus"
                / "cases"
            ).glob("*/brain_context_v1.json")
        )[0]
    ctx = load_canon_json(context_path)
    d1 = brain_decide_v15_1(ctx)
    d2 = brain_decide_v15_1(ctx)
    assert canon_bytes(d1) == canon_bytes(d2)
