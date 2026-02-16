"""SCI-RSI v1.7r: deterministic mechanism patch selector (C-MECH-SCI).

Lexicographic score per case (directions):
1) episodes_solved (higher better)
2) env_steps_total (lower better)
3) bytes_hashed_total (lower better)
4) verifier_gas_total (lower better)

A patch cert is admissible iff for every case: new >= base under this lexicographic order.
Strictly improving iff exists case: new > base.
Selection:
1) maximize number of strictly improved cases
2) tie-break by lexicographically smallest patch_id
"""

from __future__ import annotations

from typing import Any


def _require_dict(x: Any, name: str) -> dict:
    if not isinstance(x, dict):
        raise TypeError(f"{name} must be dict")
    return x


def _require_list(x: Any, name: str) -> list:
    if not isinstance(x, list):
        raise TypeError(f"{name} must be list")
    return x


def _require_str(x: Any, name: str) -> str:
    if not isinstance(x, str):
        raise TypeError(f"{name} must be str")
    return x


def _require_int(x: Any, name: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise TypeError(f"{name} must be int")
    return x


def _score_tuple(m: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        _require_int(m.get("episodes_solved"), "episodes_solved"),
        _require_int(m.get("env_steps_total"), "env_steps_total"),
        _require_int(m.get("bytes_hashed_total"), "bytes_hashed_total"),
        _require_int(m.get("verifier_gas_total"), "verifier_gas_total"),
    )


def _cmp_metrics(new_m: dict[str, Any], base_m: dict[str, Any]) -> int:
    """Return 1 if new>base, 0 if equal, -1 if new<base under SCI lexicographic order."""
    n = _score_tuple(new_m)
    b = _score_tuple(base_m)

    # Component 0: higher is better
    if n[0] != b[0]:
        return 1 if n[0] > b[0] else -1
    # Components 1..3: lower is better
    for i in (1, 2, 3):
        if n[i] != b[i]:
            return 1 if n[i] < b[i] else -1
    return 0


def select_best_patch_sci(*, eval_certs: list[dict[str, Any]]) -> str:
    certs = _require_list(eval_certs, "eval_certs")

    best_patch_id: str | None = None
    best_improved_cases = -1

    for cert in certs:
        c = _require_dict(cert, "cert")
        patch_id = _require_str(c.get("patch_id"), "cert.patch_id")
        cases = _require_list(c.get("cases"), "cert.cases")

        admissible = True
        improved = 0

        for case in cases:
            cd = _require_dict(case, "case")
            base_m = _require_dict(cd.get("base"), "case.base")
            new_m = _require_dict(cd.get("new"), "case.new")
            cmpv = _cmp_metrics(new_m, base_m)
            if cmpv < 0:
                admissible = False
                break
            if cmpv > 0:
                improved += 1

        if not admissible:
            continue
        if improved <= 0:
            continue

        if improved > best_improved_cases:
            best_improved_cases = improved
            best_patch_id = patch_id
        elif improved == best_improved_cases:
            if best_patch_id is None or patch_id < best_patch_id:
                best_patch_id = patch_id

    if best_patch_id is None:
        raise ValueError("no admissible improving patch found")
    return best_patch_id
