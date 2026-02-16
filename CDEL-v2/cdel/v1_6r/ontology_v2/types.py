"""Type helpers for ontology v2 artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OntologyDef = dict[str, Any]
OntologyPatch = dict[str, Any]
OntologyEvalReport = dict[str, Any]
OntologyAdmitReceipt = dict[str, Any]
OntologyLedgerEntry = dict[str, Any]
OntologyActiveSet = dict[str, Any]
OntologySnapshot = dict[str, Any]


@dataclass
class EvalOutcome:
    report: OntologyEvalReport | None
    admit_receipt: OntologyAdmitReceipt | None
    ledger_entries: list[OntologyLedgerEntry]
    active_set: OntologyActiveSet | None
    eviction_entry: OntologyLedgerEntry | None
    accepted: bool
