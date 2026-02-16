from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins


def test_authority_hash_is_deterministic_and_sensitive() -> None:
    repo = Path(__file__).resolve().parents[4]
    pins = load_authority_pins(repo)

    h1 = auth_hash(pins)
    h2 = auth_hash(deepcopy(pins))
    assert h1 == h2

    mutated = deepcopy(pins)
    mutated["toolchain_root_id"] = "sha256:" + ("f" * 64)
    assert auth_hash(mutated) != h1
