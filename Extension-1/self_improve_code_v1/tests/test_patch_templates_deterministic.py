from __future__ import annotations

from pathlib import Path

from self_improve_code_v1.domains.flagship_code_rsi_v1.patch_templates_v1 import DevHint, get_template
from self_improve_code_v1.domains.flagship_code_rsi_v1.proposer_v1 import PCG32


def test_patch_templates_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "a.py"
    original = "x = 1  \ny = 2  \n"
    target.write_text(original, encoding="utf-8")

    hint = DevHint(implicated_paths=["a.py"], fail_signature="", normalized_error="")
    rng = PCG32(state=1, inc=1)

    template = get_template("trim_trailing_whitespace_v1")
    patch1 = template.apply(str(repo), hint, rng)
    # reset
    target.write_text(original, encoding="utf-8")
    rng = PCG32(state=1, inc=1)
    patch2 = template.apply(str(repo), hint, rng)

    assert patch1 == patch2
    assert "-x = 1  " in patch1
    assert "+x = 1" in patch1
