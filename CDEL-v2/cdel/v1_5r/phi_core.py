"""phi_core feature extraction for v1.5r."""

from __future__ import annotations

from typing import Iterable


def _last_nibble(hash_str: str) -> int:
    if not isinstance(hash_str, str):
        return 0
    if ":" in hash_str:
        _, hex_part = hash_str.split(":", 1)
    else:
        hex_part = hash_str
    hex_part = hex_part.strip()
    if not hex_part:
        return 0
    try:
        return int(hex_part[-1], 16)
    except ValueError:
        return 0


def phi_core(observation_hashes: Iterable[str]) -> dict[str, int]:
    hashes = list(observation_hashes)
    obs_count = len(hashes)
    if obs_count == 0:
        return {
            "obs_count": 0,
            "first_obs_mod_16": 0,
            "last_obs_mod_16": 0,
            "xor_obs_mod_16": 0,
        }
    first_mod = _last_nibble(hashes[0])
    last_mod = _last_nibble(hashes[-1])
    xor_mod = 0
    for h in hashes:
        xor_mod ^= _last_nibble(h)
    return {
        "obs_count": obs_count,
        "first_obs_mod_16": first_mod,
        "last_obs_mod_16": last_mod,
        "xor_obs_mod_16": xor_mod,
    }
