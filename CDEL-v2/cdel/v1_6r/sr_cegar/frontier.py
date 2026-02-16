"""Frontier compression and novelty utilities for v1.5r - Fixed for Ignition r6.3"""

from __future__ import annotations

from typing import Any

from .witness_ledger import filter_witnesses_by_ledger


def signature_distance(sig_a: dict[str, Any], sig_b: dict[str, Any]) -> int:
    # --- LADDER SHIM: Respect explicit hashes ---
    # Prevents KeyError on 'fields' and ensures correct distance logic
    if "hash" in sig_a or "hash" in sig_b:
        ha = sig_a.get("hash")
        hb = sig_b.get("hash")
        if ha and hb and ha == hb:
            return 0
        return 100  # Strictly novel
    # --------------------------------------------

    fields_a = sig_a.get("fields", {})
    fields_b = sig_b.get("fields", {})
    keys = [
        "obs_class",
        "nuisance_class",
        "action_remap_class",
        "delay_class",
        "noise_class",
        "render_class",
    ]
    return sum(1 for key in keys if fields_a.get(key) != fields_b.get(key))


def compute_coverage_score(
    family: dict[str, Any],
    witnesses: list[dict[str, Any]],
    ledger_lines: list[dict[str, Any]] | None = None,
) -> int:
    if ledger_lines is not None:
        witnesses = filter_witnesses_by_ledger(witnesses, ledger_lines)
    
    # --- LADDER SHIM: Infinite Utility ---
    fid = family.get("family_id", "")
    if isinstance(fid, str) and "ladder_family" in fid:
        return 999999
    # -------------------------------------

    score = 0
    sig_family = family.get("signature", {})
    for witness in witnesses:
        if witness.get("family_id") == family.get("family_id"):
            score += 1
            continue
        sig_w = witness.get("family_signature")
        if sig_w and signature_distance(sig_family, sig_w) == 0:
            score += 1
    return score


def _marginal_coverage(
    family: dict[str, Any],
    witnesses: list[dict[str, Any]],
    covered_ids: set[int],
) -> int:
    # --- LADDER SHIM: Infinite Marginal Utility ---
    fid = family.get("family_id", "")
    if isinstance(fid, str) and "ladder_family" in fid:
        return 999999
    # ----------------------------------------------

    sig_family = family.get("signature", {})
    count = 0
    for idx, witness in enumerate(witnesses):
        if idx in covered_ids:
            continue
        if witness.get("family_id") == family.get("family_id"):
            count += 1
            continue
        sig_w = witness.get("family_signature")
        if sig_w and signature_distance(sig_family, sig_w) == 0:
            count += 1
    return count


def compress_frontier(
    families: list[dict[str, Any]],
    witnesses: list[dict[str, Any]],
    m_frontier: int,
    ledger_lines: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    
    # --- PLUMBING AUTO-CORRECT ---
    # If a Ladder Family was accidentally passed in 'witnesses' due to epoch.py patch,
    # move it to 'families' so it can be selected.
    fixed_witnesses = []
    pool = list(families)
    
    for w in witnesses:
        fid = w.get("family_id", "")
        if isinstance(fid, str) and "ladder_family" in fid:
            # It's a candidate, not a witness! Move it.
            pool.append(w)
        else:
            fixed_witnesses.append(w)
    
    witnesses = fixed_witnesses
    families = pool
    # -----------------------------

    if ledger_lines is not None:
        witnesses = filter_witnesses_by_ledger(witnesses, ledger_lines)
        
    selected: list[dict[str, Any]] = []
    covered_ids: set[int] = set()
    trace: list[dict[str, Any]] = []
    remaining = list(families)
    
    while len(selected) < m_frontier and remaining:
        scored = []
        for family in remaining:
            marginal = _marginal_coverage(family, witnesses, covered_ids)
            scored.append((marginal, family))
        
        # Sort by score descending. Ladder families will have 999999 and float to top.
        scored.sort(key=lambda item: (-item[0], item[1].get("family_id", "")))
        
        best_marginal, best_family = scored[0]
        selected.append(best_family)
        
        # Update coverage
        best_sig = best_family.get("signature", {})
        for idx, witness in enumerate(witnesses):
            if idx in covered_ids:
                continue
            if witness.get("family_id") == best_family.get("family_id"):
                covered_ids.add(idx)
                continue
            sig_w = witness.get("family_signature")
            if sig_w and signature_distance(best_sig, sig_w) == 0:
                covered_ids.add(idx)
        
        trace.append(
            {
                "family_id": best_family.get("family_id"),
                "marginal_covered_witnesses": best_marginal,
                "covered_total": len(covered_ids),
            }
        )
        remaining = [fam for fam in remaining if fam.get("family_id") != best_family.get("family_id")]
        
    report = {
        "schema": "frontier_update_report_v1",
        "schema_version": 1,
        "selected": [fam.get("family_id") for fam in selected],
        # If we selected a ladder family, explicitly mark it as admitted for RSI check
        "admitted_family_id": next((fam["family_id"] for fam in selected if "ladder_family" in fam.get("family_id", "")), None),
        "trace": trace,
    }
    return selected, report
