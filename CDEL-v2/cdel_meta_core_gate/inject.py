from __future__ import annotations

from .domain import MetaCoreAudit
from .errors import MetaCoreGateInternal


def inject_meta_core_fields(receipt: dict, audit: MetaCoreAudit) -> dict:
    """
    Returns a NEW dict (do not mutate input) with a new 'meta_core' object injected.
    Must be deterministic: no timestamps, no randomness.
    """
    if "meta_core" in receipt:
        raise MetaCoreGateInternal("meta_core already present")
    out = dict(receipt)
    out["meta_core"] = {
        "active_bundle_hash": audit.active_bundle_hash,
        "prev_active_bundle_hash": audit.prev_active_bundle_hash,
        "kernel_hash": audit.kernel_hash,
        "meta_hash": audit.meta_hash,
        "ruleset_hash": audit.ruleset_hash,
        "toolchain_merkle_root": audit.toolchain_merkle_root,
        "ledger_head_hash": audit.ledger_head_hash,
    }
    return out
