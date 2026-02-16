"""Deterministic governance/falsifier flags for CAOE v1 proposer."""

from __future__ import annotations

from typing import Any


def _last_n(history: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    if n <= 0:
        return []
    return history[-n:]


def compute_flags(state: dict[str, Any]) -> dict[str, bool]:
    history = list(state.get("history", []))

    # Ontology bloat proxy: check last 5 PASS entries.
    pass_entries = [entry for entry in history if entry.get("decision") == "PASS"]
    last5 = pass_entries[-5:]
    ontology_bloat_proxy = False
    if len(last5) >= 2:
        for prev, cur in zip(last5, last5[1:]):
            try:
                prev_wcs = float(prev.get("worst_case_success", 0.0))
                cur_wcs = float(cur.get("worst_case_success", 0.0))
                prev_mdl = float(prev.get("mdl_bits", 0.0))
                cur_mdl = float(cur.get("mdl_bits", 0.0))
            except (TypeError, ValueError):
                continue
            if cur_wcs < prev_wcs:
                ontology_bloat_proxy = True
                break
            if cur_mdl >= prev_mdl:
                ontology_bloat_proxy = True
                break

    # Promotion without invariance proxy: requires avg_success if present.
    promotion_without_invariance_proxy = False
    for prev, cur in zip(history, history[1:]):
        if prev.get("decision") != "PASS" or cur.get("decision") != "PASS":
            continue
        if "avg_success" in prev and "avg_success" in cur:
            try:
                prev_avg = float(prev.get("avg_success"))
                cur_avg = float(cur.get("avg_success"))
                prev_wcs = float(prev.get("worst_case_success", 0.0))
                cur_wcs = float(cur.get("worst_case_success", 0.0))
            except (TypeError, ValueError):
                continue
            if cur_avg > prev_avg and cur_wcs < prev_wcs:
                promotion_without_invariance_proxy = True
                break

    # Macro magic proxy.
    macro_magic_proxy = False
    if state.get("macro_stage_enabled", False):
        for entry in _last_n(history, 3):
            if entry.get("do_pass") is False:
                macro_magic_proxy = True
                break

    # Degenerate proxy: any C-ANTI fail in last 3 selected attempts.
    degenerate_proxy = False
    for entry in _last_n(history, 3):
        if entry.get("any_c_anti_fail") is True:
            degenerate_proxy = True
            break

    # Stagnation proxy: no improvement in worst-case success across last 10 epochs.
    stagnation_proxy = False
    if len(history) >= 10:
        window = history[-10:]
        values = []
        for entry in window:
            try:
                values.append(float(entry.get("worst_case_success", 0.0)))
            except (TypeError, ValueError):
                values.append(0.0)
        if values:
            if max(values) - min(values) < 1e-6:
                stagnation_proxy = True

    return {
        "ontology_bloat_proxy": ontology_bloat_proxy,
        "promotion_without_invariance_proxy": promotion_without_invariance_proxy,
        "macro_magic_proxy": macro_magic_proxy,
        "degenerate_proxy": degenerate_proxy,
        "stagnation_proxy": stagnation_proxy,
    }
