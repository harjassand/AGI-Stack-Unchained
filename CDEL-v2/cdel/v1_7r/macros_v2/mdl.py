"""MDL computations for context-guarded macros v2."""

from __future__ import annotations

from typing import Any

from ..canon import CanonError
from .encoder import encode_tokens
from .io import compute_rent_bits


def _macro_id(macro_def: dict[str, Any]) -> str:
    macro_id = macro_def.get("macro_id")
    return macro_id if isinstance(macro_id, str) else ""


def _filter_occurrences(occurrences: list[tuple[str, int, int]], macro_id: str) -> list[tuple[int, int]]:
    return [(start, length) for mid, start, length in occurrences if mid == macro_id]


def _verify_replay(events: list[dict[str, Any]], occurrence: tuple[int, int]) -> None:
    start, length = occurrence
    if start + length > len(events):
        raise CanonError("macro occurrence out of bounds")
    for idx in range(start, start + length):
        if "post_obs_hash" not in events[idx]:
            raise CanonError("macro replay missing post_obs_hash")


def compute_ctx_mdl_gain(
    *,
    events: list[dict[str, Any]],
    active_macros: list[dict[str, Any]],
    candidate_macro: dict[str, Any],
) -> dict[str, int]:
    base_tokens, _ = encode_tokens(events, active_macros)
    combined_macros = list(active_macros) + [candidate_macro]
    new_tokens, occurrences = encode_tokens(events, combined_macros)

    delta_tokens = int(base_tokens - new_tokens)
    rent_bits = int(candidate_macro.get("rent_bits", compute_rent_bits(candidate_macro)))
    ctx_mdl_gain_bits = int(8 * delta_tokens - rent_bits)

    macro_id = _macro_id(candidate_macro)
    macro_occ = _filter_occurrences(occurrences, macro_id)
    support_families: set[str] = set()
    for start, length in macro_occ:
        _verify_replay(events, (start, length))
        fam_id = events[start].get("family_id")
        if isinstance(fam_id, str):
            support_families.add(fam_id)

    return {
        "ctx_mdl_gain_bits": ctx_mdl_gain_bits,
        "support_families_hold": len(support_families),
        "support_total_hold": len(macro_occ),
        "delta_tokens": delta_tokens,
    }
