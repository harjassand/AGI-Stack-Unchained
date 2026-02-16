from __future__ import annotations

from pathlib import Path

from cdel.v2_0.autonomy import compute_expected, load_translation_inputs
from cdel.v2_0.constants import require_constants


def _ctx_key(case: dict[str, object]) -> tuple[object, ...]:
    ctx_mode = case.get("ctx_mode")
    if ctx_mode == "null":
        return ("NULL_V1",)
    if ctx_mode == "explicit":
        ontology_id = case.get("active_ontology_id")
        snapshot_id = case.get("active_snapshot_id")
        values = case.get("values")
        values_tuple = tuple(values) if isinstance(values, list) else tuple()
        return ("KEY_V1", ontology_id, snapshot_id, values_tuple)
    raise ValueError("invalid ctx_mode")


def _next_pow2(n: int) -> int:
    if n <= 1:
        return 1
    value = 1
    while value < n:
        value <<= 1
    return value


def _highest_power_of_two_leq(n: int) -> int:
    if n <= 1:
        return 1
    value = 1
    while value << 1 <= n:
        value <<= 1
    return value


def _capacity_formula(*, u: int, max_cap: int, start_shift: int, attempt_index: int) -> int:
    p = _next_pow2(u)
    base_cap = min(p, max_cap)
    e = attempt_index - 1 - start_shift
    if e >= 0:
        cap = base_cap * (2**e)
    else:
        cap = base_cap // (2 ** (-e))
    if cap < 1:
        cap = 1
    if cap > max_cap:
        cap = max_cap
        if max_cap & (max_cap - 1):
            cap = _highest_power_of_two_leq(max_cap)
    return int(cap)


def test_autopatch_enum_v2_capacity_schedule() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    translation_path = repo_root / "campaigns" / "rsi_real_demon_v6_efficiency" / "translation" / "translation_inputs_v1.json"
    translation_inputs = load_translation_inputs(translation_path)

    cases = translation_inputs.get("cases", [])
    keys = {_ctx_key(case) for case in cases}
    u = len(keys)
    assert u >= 1

    constants = require_constants()
    max_cap = int(constants.get("CTX_HASH_CACHE_V1_MAX_CAPACITY", 0) or 0)
    start_shift = int(constants.get("AUTOPATCH_ENUM_V2_START_SHIFT", 0) or 0)

    for attempt_index in range(1, 9):
        manifest, patch_defs = compute_expected(
            translation_inputs,
            attempt_index=attempt_index,
            prior_attempt_index=attempt_index - 1,
            prior_verifier_reason="",
        )
        assert len(patch_defs) == 1
        capacity = patch_defs[0]["params"]["capacity"]
        expected = _capacity_formula(u=u, max_cap=max_cap, start_shift=start_shift, attempt_index=attempt_index)
        assert capacity == expected
        assert manifest["patches"][0]["params"]["capacity"] == expected
