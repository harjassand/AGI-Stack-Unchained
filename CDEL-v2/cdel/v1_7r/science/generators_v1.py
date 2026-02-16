"""SCI-RSI v1.7r: deterministic integer-only scientific generators.

Determinism requirement:
- All randomness must derive only from (epoch_key, inst_hash, domain_tag) via a pinned PRNG.
- For each generator, seed bytes are:
    seed = sha256(epoch_key || inst_hash || "<generator_kind>")

This module uses xorshift128+ with 64-bit arithmetic and rejection sampling for unbiased UnifInt.
No floats are used.
"""

from __future__ import annotations

import hashlib
from typing import Any


_U64_MASK = (1 << 64) - 1


def _require_bytes(x: Any, name: str) -> bytes:
    if isinstance(x, bytes):
        return x
    if isinstance(x, bytearray):
        return bytes(x)
    raise TypeError(f"{name} must be bytes")


def _require_dict(x: Any, name: str) -> dict:
    if not isinstance(x, dict):
        raise TypeError(f"{name} must be dict")
    return x


def _get_int(d: dict, key: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(f"{key} must be int")
    return v


def _get_str(d: dict, key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise TypeError(f"{key} must be str")
    return v


def _seed_bytes(epoch_key: bytes, inst_hash: bytes, domain_tag: str) -> bytes:
    # seed = sha256(epoch_key || inst_hash || domain_tag)
    return hashlib.sha256(epoch_key + inst_hash + domain_tag.encode("utf-8")).digest()


def _xorshift128plus_seed_from_sha256(seed32: bytes) -> tuple[int, int]:
    if not isinstance(seed32, (bytes, bytearray)) or len(seed32) != 32:
        raise ValueError("seed must be 32 bytes (sha256 digest)")
    s0 = int.from_bytes(seed32[0:8], "little") & _U64_MASK
    s1 = int.from_bytes(seed32[8:16], "little") & _U64_MASK
    if s0 == 0 and s1 == 0:
        # Avoid forbidden all-zero state.
        s1 = 0x9E3779B97F4A7C15
    return s0, s1


def _xorshift128plus_next(state: tuple[int, int]) -> tuple[int, tuple[int, int]]:
    s0, s1 = state
    x = s0
    y = s1
    s0 = y
    x ^= (x << 23) & _U64_MASK
    x ^= (x >> 17) & _U64_MASK
    x ^= y
    x ^= (y >> 26) & _U64_MASK
    s1 = x & _U64_MASK
    out = (s0 + s1) & _U64_MASK
    return out, (s0, s1)


def _rand_u64(state: tuple[int, int]) -> tuple[int, tuple[int, int]]:
    return _xorshift128plus_next(state)


def _rand_int_inclusive(state: tuple[int, int], min_val: int, max_val: int) -> tuple[int, tuple[int, int]]:
    if isinstance(min_val, bool) or isinstance(max_val, bool):
        raise TypeError("min_val/max_val must be int")
    if not isinstance(min_val, int) or not isinstance(max_val, int):
        raise TypeError("min_val/max_val must be int")
    if min_val > max_val:
        raise ValueError("min_val must be <= max_val")
    span = max_val - min_val + 1
    # Rejection sampling for unbiased range.
    limit = (1 << 64) - ((1 << 64) % span)
    while True:
        v, state = _rand_u64(state)
        if v < limit:
            return min_val + (v % span), state


def _rand_ppm(state: tuple[int, int]) -> tuple[int, tuple[int, int]]:
    # Return uniform integer in [0, 999_999].
    return _rand_int_inclusive(state, 0, 999_999)


def gen_wm_linear_sep_int_v1(*, epoch_key: bytes, inst_hash: bytes, gen_cfg: dict) -> list[dict]:
    """Generate linear separable integer dataset rows: {"x":[int...], "y":0|1}."""
    epoch_key_b = _require_bytes(epoch_key, "epoch_key")
    inst_hash_b = _require_bytes(inst_hash, "inst_hash")
    cfg = _require_dict(gen_cfg, "gen_cfg")

    kind = _get_str(cfg, "kind")
    if kind != "wm_linear_sep_int_v1":
        raise ValueError("gen_cfg.kind must be wm_linear_sep_int_v1")

    n = _get_int(cfg, "n")
    d = _get_int(cfg, "d")
    x_min = _get_int(cfg, "x_min")
    x_max = _get_int(cfg, "x_max")
    w_true_min = _get_int(cfg, "w_true_min")
    w_true_max = _get_int(cfg, "w_true_max")
    b_true_min = _get_int(cfg, "b_true_min")
    b_true_max = _get_int(cfg, "b_true_max")
    noise_ppm = _get_int(cfg, "noise_ppm")

    if n < 0:
        raise ValueError("n must be >= 0")
    if d < 0:
        raise ValueError("d must be >= 0")
    if x_min > x_max:
        raise ValueError("x_min must be <= x_max")
    if w_true_min > w_true_max:
        raise ValueError("w_true_min must be <= w_true_max")
    if b_true_min > b_true_max:
        raise ValueError("b_true_min must be <= b_true_max")
    if noise_ppm < 0 or noise_ppm > 1_000_000:
        raise ValueError("noise_ppm out of bounds")

    seed = _seed_bytes(epoch_key_b, inst_hash_b, "wm_linear_sep_int_v1")
    state = _xorshift128plus_seed_from_sha256(seed)

    # Sample true separator (not revealed to agent).
    w_true: list[int] = []
    for _ in range(d):
        w_i, state = _rand_int_inclusive(state, w_true_min, w_true_max)
        w_true.append(w_i)
    b_true, state = _rand_int_inclusive(state, b_true_min, b_true_max)

    rows: list[dict] = []
    for _ in range(n):
        x: list[int] = []
        for _j in range(d):
            xj, state = _rand_int_inclusive(state, x_min, x_max)
            x.append(xj)

        score = 0
        for wi, xi in zip(w_true, x):
            score += wi * xi
        score += b_true
        y = 1 if score >= 0 else 0

        if noise_ppm != 0:
            r, state = _rand_ppm(state)
            if r < noise_ppm:
                y = 1 - y

        rows.append({"x": x, "y": int(y)})

    return rows


def gen_scm_backdoor_int_v1(*, epoch_key: bytes, inst_hash: bytes, gen_cfg: dict) -> tuple[list[dict], dict]:
    """Generate SCM backdoor dataset rows: {"Z":int,"W":int,"T":0|1,"Y":int}. Meta includes true_ate:int."""
    epoch_key_b = _require_bytes(epoch_key, "epoch_key")
    inst_hash_b = _require_bytes(inst_hash, "inst_hash")
    cfg = _require_dict(gen_cfg, "gen_cfg")

    kind = _get_str(cfg, "kind")
    if kind != "scm_backdoor_int_v1":
        raise ValueError("gen_cfg.kind must be scm_backdoor_int_v1")

    n = _get_int(cfg, "n")

    z_min = _get_int(cfg, "z_min")
    z_max = _get_int(cfg, "z_max")
    w_min = _get_int(cfg, "w_min")
    w_max = _get_int(cfg, "w_max")

    a_z = _get_int(cfg, "a_z")
    a_w = _get_int(cfg, "a_w")
    a0 = _get_int(cfg, "a0")

    c_t = _get_int(cfg, "c_t")
    c_z = _get_int(cfg, "c_z")
    c_w = _get_int(cfg, "c_w")
    c0 = _get_int(cfg, "c0")

    eps_t_min = _get_int(cfg, "eps_t_min")
    eps_t_max = _get_int(cfg, "eps_t_max")
    eps_y_min = _get_int(cfg, "eps_y_min")
    eps_y_max = _get_int(cfg, "eps_y_max")

    if n < 0:
        raise ValueError("n must be >= 0")
    if z_min > z_max:
        raise ValueError("z_min must be <= z_max")
    if w_min > w_max:
        raise ValueError("w_min must be <= w_max")
    if eps_t_min > eps_t_max:
        raise ValueError("eps_t_min must be <= eps_t_max")
    if eps_y_min > eps_y_max:
        raise ValueError("eps_y_min must be <= eps_y_max")

    seed = _seed_bytes(epoch_key_b, inst_hash_b, "scm_backdoor_int_v1")
    state = _xorshift128plus_seed_from_sha256(seed)

    rows: list[dict] = []
    for _ in range(n):
        Z, state = _rand_int_inclusive(state, z_min, z_max)
        W, state = _rand_int_inclusive(state, w_min, w_max)

        eps_t, state = _rand_int_inclusive(state, eps_t_min, eps_t_max)
        t_score = a_z * Z + a_w * W + a0 + eps_t
        T = 1 if t_score >= 0 else 0

        eps_y, state = _rand_int_inclusive(state, eps_y_min, eps_y_max)
        Y = c_t * T + c_z * Z + c_w * W + c0 + eps_y

        rows.append({"Z": int(Z), "W": int(W), "T": int(T), "Y": int(Y)})

    meta = {"true_ate": int(c_t)}
    return rows, meta
