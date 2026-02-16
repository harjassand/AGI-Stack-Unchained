"""Ontology v3 evaluation + gating + ledger updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json
from ..constants import meta_identities
from ..demon.trace import load_trace_jsonl
from .dl_metric import compute_dl_metrics, corpus_hash, trace_hash
from .dsl import validate_ontology_def
from .io import ensure_ontology_dirs, write_def_if_missing, write_snapshot_if_missing
from .ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries
from .train import train_snapshot


@dataclass
class EvalOutcome:
    report: dict[str, Any] | None
    admit_receipt: dict[str, Any] | None
    ledger_entries: list[dict[str, Any]]
    active_set: dict[str, Any] | None
    accepted: bool


def _epoch_index(epoch_id: str) -> int | None:
    tail = str(epoch_id).split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _trace_path(state_dir: Path, epoch_idx: int) -> Path:
    return state_dir / "epochs" / f"epoch_{epoch_idx}" / "traces" / "trace_v2.jsonl"


def _load_corpus(state_dir: Path, window_epochs: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    trace_hashes: list[str] = []
    for idx in window_epochs:
        trace_path = _trace_path(state_dir, idx)
        if not trace_path.exists():
            raise CanonError(f"missing trace: {trace_path}")
        trace_hashes.append(trace_hash(trace_path))
        events.extend(load_trace_jsonl(trace_path))
    return events, trace_hashes


def _family_partition(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        fam_id = event.get("family_id")
        if not isinstance(fam_id, str):
            continue
        buckets.setdefault(fam_id, []).append(event)
    return buckets


def _meta_check(payload: dict[str, Any], meta: dict[str, str]) -> None:
    xmeta = payload.get("x-meta")
    if not isinstance(xmeta, dict):
        raise CanonError("x-meta missing")
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash"):
        if xmeta.get(key) != meta.get(key):
            raise CanonError("x-meta mismatch")


def _default_active_set(meta: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "ontology_active_set_v3",
        "schema_version": 3,
        "active_ontology_id": None,
        "active_snapshot_id": None,
        "activation_epoch": None,
        "x-meta": meta,
    }


def _load_active_set(path: Path, meta: dict[str, str]) -> dict[str, Any]:
    if not path.exists():
        return _default_active_set(meta)
    payload = load_canon_json(path)
    if payload.get("schema") != "ontology_active_set_v3":
        raise CanonError("ontology_active_set schema mismatch")
    _meta_check(payload, meta)
    return payload


def _write_active_set(path: Path, payload: dict[str, Any], meta: dict[str, str]) -> None:
    payload["x-meta"] = meta
    write_canon_json(path, payload)


def _select_best(candidates: list[tuple[int, dict[str, Any], dict[str, Any]]]) -> tuple[int, dict[str, Any], dict[str, Any]]:
    def key(item: tuple[int, dict[str, Any], dict[str, Any]]) -> tuple[int, str]:
        gain, report, _snapshot = item
        ontology_id = report.get("ontology_id")
        return (-int(gain), str(ontology_id))

    return sorted(candidates, key=key)[0]


def _state_head_hash(state_dir: Path) -> str:
    state_head = state_dir / "current" / "state_ledger_head_v1.json"
    if not state_head.exists():
        return "sha256:" + "0" * 64
    payload = load_canon_json(state_head)
    return sha256_prefixed(canon_bytes(payload))


def evaluate_epoch(
    *,
    state_dir: Path,
    epoch_id: str,
    constants: dict[str, Any],
    window_epochs: list[int],
    proposals: list[dict[str, Any]],
    strict: bool = True,
) -> EvalOutcome:
    meta = meta_identities()
    ontology_root = state_dir / "current" / "ontology_v3"
    dirs = ensure_ontology_dirs(ontology_root)
    ledger_path = dirs["ledger"] / "ontology_ledger_v3.jsonl"
    active_set_path = dirs["active"] / "ontology_active_set_v3.json"

    active_set = _load_active_set(active_set_path, meta)

    ledger_entries = load_ledger_entries(ledger_path)
    prev_line_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

    events, trace_hashes = _load_corpus(state_dir, window_epochs)
    base_metrics = compute_dl_metrics(events=events, ontology_def=None, snapshot=None)
    family_events = _family_partition(events)

    winners: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for proposal in proposals:
        try:
            validate_ontology_def(proposal, constants=constants)
            _meta_check(proposal, meta)

            snapshot = train_snapshot(
                ontology_def=proposal,
                events=events,
                epoch_id=epoch_id,
                window_epochs=window_epochs,
                corpus_hash=corpus_hash(window_epochs, trace_hashes),
                meta=meta,
            )
            arity = snapshot.get("context_kernel_state", {}).get("arity")
            if not isinstance(arity, int):
                raise CanonError("snapshot arity invalid")
            max_arity = int(constants.get("ONTO_V3_MAX_CTX_ARITY", 0) or 0)
            if max_arity and arity > max_arity:
                raise CanonError("snapshot arity exceeds ONTO_V3_MAX_CTX_ARITY")

            new_metrics = compute_dl_metrics(events=events, ontology_def=proposal, snapshot=snapshot)
            dl_gain_bits = int(base_metrics.dl_bits - new_metrics.dl_bits)

            support_improved = 0
            for family_events_list in family_events.values():
                base_family = compute_dl_metrics(events=family_events_list, ontology_def=None, snapshot=None)
                new_family = compute_dl_metrics(events=family_events_list, ontology_def=proposal, snapshot=snapshot)
                if new_family.dl_bits < base_family.dl_bits:
                    support_improved += 1

            passes = True
            reason = "PASS"
            if dl_gain_bits < int(constants.get("ONTO_V3_DL_GAIN_MIN_BITS", 0) or 0):
                passes = False
                reason = "DL_GAIN_MIN"
            if support_improved < int(constants.get("ONTO_V3_SUPPORT_FAMILIES_MIN", 0) or 0):
                passes = False
                reason = "SUPPORT_FAMILIES_MIN"

            report = {
                "schema": "ontology_eval_report_v3",
                "schema_version": 3,
                "epoch_id": epoch_id,
                "ontology_id": proposal.get("ontology_id"),
                "snapshot_id": snapshot.get("snapshot_id"),
                "corpus": {
                    "window_epochs": window_epochs,
                    "trace_hashes": trace_hashes,
                    "corpus_hash": corpus_hash(window_epochs, trace_hashes),
                },
                "dl": {
                    "dl_bits_base": base_metrics.dl_bits,
                    "dl_bits_new": new_metrics.dl_bits,
                    "dl_gain_bits": dl_gain_bits,
                    "rent_bits_new": new_metrics.rent_bits,
                    "model_bits_new": new_metrics.model_bits,
                    "data_bits_new": new_metrics.data_bits,
                    "support_families_improved": support_improved,
                },
                "decision": {"passes": bool(passes), "reason": reason},
                "x-meta": meta,
            }

            if passes:
                winners.append((dl_gain_bits, report, snapshot))
        except Exception:
            if strict:
                continue
            continue

    if not winners:
        return EvalOutcome(report=None, admit_receipt=None, ledger_entries=[], active_set=None, accepted=False)

    dl_gain, report, snapshot = _select_best(winners)
    epoch_idx = _epoch_index(epoch_id)
    if epoch_idx is None:
        raise CanonError("invalid epoch_id")

    report_path = dirs["reports"] / f"ontology_eval_report_v3_epoch_{epoch_idx}.json"
    write_canon_json(report_path, report)
    report_hash = hash_json(report)

    ontology_def = None
    for proposal in proposals:
        if proposal.get("ontology_id") == report.get("ontology_id"):
            ontology_def = proposal
            break
    if ontology_def is None:
        raise CanonError("selected ontology_def missing")

    def_hash = hash_json(ontology_def)
    snapshot_hash = hash_json(snapshot)

    write_def_if_missing(ontology_def, dirs["defs"])
    write_snapshot_if_missing(snapshot, dirs["snapshots"])

    admit_receipt = {
        "schema": "ontology_admit_receipt_v3",
        "schema_version": 3,
        "epoch_id": epoch_id,
        "ontology_id": ontology_def.get("ontology_id"),
        "snapshot_id": snapshot.get("snapshot_id"),
        "ontology_def_hash": def_hash,
        "ontology_snapshot_hash": snapshot_hash,
        "ontology_eval_report_hash": report_hash,
        "state_ledger_head_hash": _state_head_hash(state_dir),
        "verdict": "VALID",
        "x-meta": meta,
    }
    receipt_path = dirs["receipts"] / f"ontology_admit_receipt_v3_epoch_{epoch_idx}.json"
    write_canon_json(receipt_path, admit_receipt)
    admit_hash = hash_json(admit_receipt)

    entries: list[dict[str, Any]] = []
    admit_entry = build_ledger_entry(
        event="ADMIT",
        epoch_id=epoch_id,
        ontology_id=ontology_def.get("ontology_id"),
        ontology_def_hash=def_hash,
        snapshot_id=snapshot.get("snapshot_id"),
        admit_receipt_hash=admit_hash,
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(admit_entry)
    prev_line_hash = admit_entry.get("line_hash")

    active_set = _default_active_set(meta)
    active_set["active_ontology_id"] = ontology_def.get("ontology_id")
    active_set["active_snapshot_id"] = snapshot.get("snapshot_id")
    active_set["activation_epoch"] = epoch_idx
    _write_active_set(active_set_path, active_set, meta)

    activate_entry = build_ledger_entry(
        event="ACTIVATE",
        epoch_id=epoch_id,
        ontology_id=ontology_def.get("ontology_id"),
        ontology_def_hash=def_hash,
        snapshot_id=snapshot.get("snapshot_id"),
        admit_receipt_hash=admit_hash,
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(activate_entry)

    for entry in entries:
        append_ledger_entry(ledger_path, entry)

    return EvalOutcome(report=report, admit_receipt=admit_receipt, ledger_entries=entries, active_set=active_set, accepted=True)
