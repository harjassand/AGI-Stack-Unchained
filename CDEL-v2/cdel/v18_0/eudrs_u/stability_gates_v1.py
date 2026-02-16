"""Ontology stability gates (STAB-G0..G5) (v1).

The normative gate definitions are in the repo-anchored EUDRS-U v1.0 spec
(Section 16). This checkout implements:
  - deterministic structural verification of `cooldown_ledger_v1`
  - a minimal stability gate entry point that is fail-closed when ORoot changes
    (full semantics require additional artifacts not yet integrated)

This module is RE2: deterministic and fail-closed via `omega_common_v1.fail`.
"""

from __future__ import annotations

from typing import Any

from ..omega_common_v1 import fail


def verify_cooldown_ledger_v1(*, ledger_obj: dict[str, Any]) -> None:
    if not isinstance(ledger_obj, dict):
        fail("SCHEMA_FAIL")
    if str(ledger_obj.get("schema_id", "")).strip() != "cooldown_ledger_v1":
        fail("SCHEMA_FAIL")
    epoch_u64 = ledger_obj.get("epoch_u64")
    if not isinstance(epoch_u64, int) or int(epoch_u64) < 0:
        fail("SCHEMA_FAIL")

    locks = ledger_obj.get("locks")
    if not isinstance(locks, list):
        fail("SCHEMA_FAIL")

    prev: str | None = None
    for row in locks:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        lineage_id = row.get("lineage_id")
        if not isinstance(lineage_id, str) or not lineage_id.startswith("sha256:") or len(lineage_id) != len("sha256:") + 64:
            fail("SCHEMA_FAIL")
        if prev is not None and str(lineage_id) <= str(prev):
            fail("SCHEMA_FAIL")
        prev = str(lineage_id)

        lock_kind = str(row.get("lock_kind", "")).strip()
        if not lock_kind:
            fail("SCHEMA_FAIL")

        remaining = row.get("remaining_u64")
        if not isinstance(remaining, int) or int(remaining) < 0:
            fail("SCHEMA_FAIL")


def verify_stability_gates_v1(
    *,
    root_tuple_old: dict[str, Any] | None,
    root_tuple_new: dict[str, Any],
    cooldown_ledger_old: dict[str, Any] | None,
    cooldown_ledger_new: dict[str, Any] | None,
    stability_metrics_obj: dict[str, Any] | None,
    mode: str = "full",
) -> None:
    """Minimal STAB gates entry point.

    v1 semantics require additional manifests and evaluation artifacts. Until
    those are wired, we keep this verifier fail-closed when ORoot changes.
    """

    if str(mode).strip() != "full":
        fail("MODE_UNSUPPORTED")
    if not isinstance(root_tuple_new, dict):
        fail("SCHEMA_FAIL")

    if cooldown_ledger_old is not None:
        verify_cooldown_ledger_v1(ledger_obj=dict(cooldown_ledger_old))
    if cooldown_ledger_new is not None:
        verify_cooldown_ledger_v1(ledger_obj=dict(cooldown_ledger_new))

    # If there is no previous root tuple, we do not have an ORoot_old baseline.
    if root_tuple_old is None:
        return
    if not isinstance(root_tuple_old, dict):
        fail("SCHEMA_FAIL")

    old_oroot = root_tuple_old.get("oroot")
    new_oroot = root_tuple_new.get("oroot")
    if not (isinstance(old_oroot, dict) and isinstance(new_oroot, dict)):
        fail("SCHEMA_FAIL")
    old_id = str(old_oroot.get("artifact_id", "")).strip()
    new_id = str(new_oroot.get("artifact_id", "")).strip()

    # STAB gates are required only when ontology changes.
    if old_id == new_id:
        return

    # Full STAB computation is not yet wired (needs eval suite + probe/fingerprint specs).
    # Fail closed rather than passing an unverifiable promotion.
    _ = stability_metrics_obj  # reserved for future wiring
    fail("MODE_UNSUPPORTED")


__all__ = [
    "verify_cooldown_ledger_v1",
    "verify_stability_gates_v1",
]

