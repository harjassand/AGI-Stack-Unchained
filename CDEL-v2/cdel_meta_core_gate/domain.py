from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetaCoreAudit:
    active_bundle_hash: str
    prev_active_bundle_hash: str
    kernel_hash: str
    meta_hash: str
    ruleset_hash: str
    toolchain_merkle_root: str
    ledger_head_hash: str
