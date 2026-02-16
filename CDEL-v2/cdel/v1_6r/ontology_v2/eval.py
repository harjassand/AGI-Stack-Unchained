"""Ontology v2 evaluation + gating + ledger updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json
from ..ctime.trace import load_trace_jsonl
from ..proposals.inbox import load_ontology_proposals
from .dl_metric import compute_dl_metrics, corpus_hash
from .dsl import validate_ontology_def
from .io import ensure_ontology_dirs, load_def_by_hash, write_def_if_missing
from .ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries
from .types import EvalOutcome


@dataclass
class CandidateScore:
    ontology_def: dict[str, Any]
    dl_gain_bits: int
    rent_bits: int
    support_families_improved: int
    model_bits_new: int
    data_bits_new: int


def _epoch_index(epoch_id: str) -> int | None:
    tail = str(epoch_id).split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _trace_path(state_dir: Path, epoch_idx: int) -> Path:
    epoch_dir = state_dir / "epochs" / f"epoch_{epoch_idx}" / "traces"
    trace_v1 = epoch_dir / "trace_v1.jsonl"
    if trace_v1.exists():
        return trace_v1
    trace_hold = epoch_dir / "trace_heldout_v1.jsonl"
    return trace_hold


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _load_corpus(state_dir: Path, window_epochs: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    trace_hashes: list[str] = []
    for idx in window_epochs:
        trace_path = _trace_path(state_dir, idx)
        if not trace_path.exists():
            raise CanonError(f"missing trace: {trace_path}")
        trace_hashes.append(_hash_file(trace_path))
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
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash", "toolchain_root"):
        if xmeta.get(key) != meta.get(key):
            raise CanonError("x-meta mismatch")


def _default_active_set(meta: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "ontology_active_set_v2",
        "schema_version": 2,
        "active_ontology_id": None,
        "active_snapshot_hash": None,
        "activation_epoch": None,
        "x-meta": meta,
    }


def _load_active_set(path: Path, meta: dict[str, str]) -> dict[str, Any]:
    if not path.exists():
        return _default_active_set(meta)
    payload = load_canon_json(path)
    if payload.get("schema") != "ontology_active_set_v2":
        raise CanonError("ontology_active_set schema mismatch")
    _meta_check(payload, meta)
    return payload


def _write_active_set(path: Path, payload: dict[str, Any], meta: dict[str, str]) -> None:
    payload["x-meta"] = meta
    write_canon_json(path, payload)


def _snapshot_active_set(active_set: dict[str, Any], snapshots_dir: Path) -> str:
    snap_payload = dict(active_set)
    snap_payload["schema"] = "ontology_active_set_v2"
    snap_payload["schema_version"] = 2
    snap_hash = hash_json(snap_payload)
    hex_part = snap_hash.split(":", 1)[1]
    snap_path = snapshots_dir / f"{hex_part}.json"
    if not snap_path.exists():
        write_canon_json(snap_path, snap_payload)
    return snap_hash


def _load_bad_epochs(state_path: Path) -> int:
    if not state_path.exists():
        return 0
    payload = load_canon_json(state_path)
    if not isinstance(payload, dict):
        return 0
    val = payload.get("bad_epochs")
    return int(val) if isinstance(val, int) else 0


def _write_bad_epochs(state_path: Path, bad_epochs: int) -> None:
    write_canon_json(
        state_path,
        {
            "schema": "ontology_state_v2",
            "schema_version": 2,
            "bad_epochs": int(bad_epochs),
        },
    )


def _select_best(candidates: list[tuple[CandidateScore, dict[str, Any]]]) -> tuple[CandidateScore, dict[str, Any]]:
    def key(item: tuple[CandidateScore, dict[str, Any]]) -> tuple[int, int, int, str]:
        score, _report = item
        concept_count = len(score.ontology_def.get("concepts", []))
        return (-int(score.dl_gain_bits), int(score.rent_bits), int(concept_count), str(score.ontology_def.get("ontology_id")))

    return sorted(candidates, key=key)[0]


def evaluate_epoch(
    *,
    state_dir: Path,
    epoch_id: str,
    meta: dict[str, str],
    constants: dict[str, Any],
    window_epochs: list[int],
    strict: bool = True,
) -> EvalOutcome:
    ontology_root = state_dir / "current" / "ontology"
    dirs = ensure_ontology_dirs(ontology_root)
    ledger_path = ontology_root / "ontology_ledger_v2.jsonl"
    active_set_path = ontology_root / "ontology_active_set_v2.json"
    bad_state_path = ontology_root / "ontology_state_v2.json"

    active_set = _load_active_set(active_set_path, meta)
    active_ontology_id = active_set.get("active_ontology_id")
    if not isinstance(active_ontology_id, str):
        active_ontology_id = None

    ledger_entries = load_ledger_entries(ledger_path)
    prev_line_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

    proposals = load_ontology_proposals(state_dir)
    events, trace_hashes = _load_corpus(state_dir, window_epochs)
    base_def = None
    if active_ontology_id:
        base_def = load_def_by_hash(active_ontology_id, inbox_root=state_dir / "current" / "inbox" / "ontology_v2", defs_root=dirs["defs"])

    base_metrics = compute_dl_metrics(events=events, ontology_def=base_def)
    family_events = _family_partition(events)

    winners: list[tuple[CandidateScore, dict[str, Any]]] = []
    for patch in proposals:
        try:
            if patch.get("schema") != "ontology_patch_v2" or int(patch.get("schema_version", 0)) != 2:
                raise CanonError("ontology_patch schema mismatch")
            patch_id = patch.get("patch_id")
            if not isinstance(patch_id, str):
                raise CanonError("ontology_patch missing patch_id")
            base_id = patch.get("base_ontology_id")
            if base_id != active_ontology_id:
                continue
            proposed_hash = patch.get("proposed_ontology_def_hash")
            if not isinstance(proposed_hash, str):
                raise CanonError("ontology_patch missing proposed_ontology_def_hash")
            ontology_def = load_def_by_hash(
                proposed_hash,
                inbox_root=state_dir / "current" / "inbox" / "ontology_v2",
                defs_root=dirs["defs"],
            )
            _meta_check(ontology_def, meta)
            validate_ontology_def(ontology_def, constants=constants)

            new_metrics = compute_dl_metrics(events=events, ontology_def=ontology_def)
            dl_gain_bits = int(base_metrics.dl_bits - new_metrics.dl_bits)

            support_improved = 0
            for family_events_list in family_events.values():
                base_family = compute_dl_metrics(events=family_events_list, ontology_def=base_def, include_rent=False)
                new_family = compute_dl_metrics(events=family_events_list, ontology_def=ontology_def, include_rent=False)
                if new_family.dl_bits < base_family.dl_bits:
                    support_improved += 1

            score = CandidateScore(
                ontology_def=ontology_def,
                dl_gain_bits=dl_gain_bits,
                rent_bits=new_metrics.rent_bits,
                support_families_improved=support_improved,
                model_bits_new=new_metrics.model_bits,
                data_bits_new=new_metrics.data_bits,
            )
            reason = "PASS"
            passes = True
            if dl_gain_bits < int(constants.get("ontology", {}).get("ONTO_DL_GAIN_MIN_BITS", 0) or 0):
                passes = False
                reason = "DL_GAIN_MIN"
            if support_improved < int(constants.get("ontology", {}).get("ONTO_SUPPORT_FAMILIES_MIN", 0) or 0):
                passes = False
                reason = "SUPPORT_FAMILIES_MIN"
            worstcase_path = state_dir / "epochs" / epoch_id / "diagnostics" / "worstcase_report_v1.json"
            if worstcase_path.exists():
                worstcase = load_canon_json(worstcase_path)
                if int(worstcase.get("worst_anchor", 0)) != 1 or int(worstcase.get("worst_heldout", 0)) != 1:
                    passes = False
                    reason = "CONTRACT_REGRESSION"
            report = {
                "schema": "ontology_eval_report_v2",
                "schema_version": 2,
                "epoch_id": epoch_id,
                "base_ontology_id": active_ontology_id,
                "new_ontology_id": ontology_def.get("ontology_id"),
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
                winners.append((score, report))
        except Exception:
            if strict:
                continue
            continue

    if not winners:
        return EvalOutcome(report=None, admit_receipt=None, ledger_entries=[], active_set=None, eviction_entry=None, accepted=False)

    score, report = _select_best(winners)
    report_path = dirs["reports"] / f"ontology_eval_report_v2_{epoch_id}.json"
    write_canon_json(report_path, report)
    report_hash = hash_json(report)

    ontology_def = score.ontology_def
    def_hash = hash_json(ontology_def)
    write_def_if_missing(ontology_def, dirs["defs"])

    state_head_path = state_dir / "current" / "state_ledger_head_v1.json"
    if not state_head_path.exists():
        raise CanonError("missing state_ledger_head_v1.json")
    state_head_hash = hash_json(load_canon_json(state_head_path))

    admit_receipt = {
        "schema": "ontology_admit_receipt_v2",
        "schema_version": 2,
        "epoch_id": epoch_id,
        "ontology_id": ontology_def.get("ontology_id"),
        "ontology_def_hash": def_hash,
        "ontology_eval_report_hash": report_hash,
        "state_ledger_head_hash": state_head_hash,
        "verdict": "VALID",
        "x-meta": meta,
    }
    receipt_path = dirs["receipts"] / f"ontology_admit_receipt_v2_{epoch_id}.json"
    write_canon_json(receipt_path, admit_receipt)
    admit_hash = hash_json(admit_receipt)

    entries: list[dict[str, Any]] = []
    admit_entry = build_ledger_entry(
        event="ADMIT",
        epoch_id=epoch_id,
        ontology_id=ontology_def.get("ontology_id"),
        ontology_def_hash=def_hash,
        admit_receipt_hash=admit_hash,
        active_snapshot_hash=None,
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(admit_entry)
    prev_line_hash = admit_entry.get("line_hash")

    active_set = _default_active_set(meta)
    active_set["active_ontology_id"] = ontology_def.get("ontology_id")
    active_set["activation_epoch"] = _epoch_index(epoch_id)
    active_set["active_snapshot_hash"] = _snapshot_active_set(active_set, dirs["snapshots"])
    _write_active_set(active_set_path, active_set, meta)

    activate_entry = build_ledger_entry(
        event="ACTIVATE",
        epoch_id=epoch_id,
        ontology_id=ontology_def.get("ontology_id"),
        ontology_def_hash=def_hash,
        admit_receipt_hash=admit_hash,
        active_snapshot_hash=active_set.get("active_snapshot_hash"),
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(activate_entry)

    for entry in entries:
        append_ledger_entry(ledger_path, entry)

    _write_bad_epochs(bad_state_path, 0)

    return EvalOutcome(report=report, admit_receipt=admit_receipt, ledger_entries=entries, active_set=active_set, eviction_entry=None, accepted=True)


def maybe_evict(
    *,
    state_dir: Path,
    epoch_id: str,
    meta: dict[str, str],
    constants: dict[str, Any],
) -> dict[str, Any] | None:
    ontology_root = state_dir / "current" / "ontology"
    dirs = ensure_ontology_dirs(ontology_root)
    ledger_path = ontology_root / "ontology_ledger_v2.jsonl"
    active_set_path = ontology_root / "ontology_active_set_v2.json"
    bad_state_path = ontology_root / "ontology_state_v2.json"

    active_set = _load_active_set(active_set_path, meta)
    active_ontology_id = active_set.get("active_ontology_id")
    if not isinstance(active_ontology_id, str):
        return None

    limits = constants.get("ontology", {})
    window = int(limits.get("ONTO_EVICT_WINDOW_EPOCHS", 0) or 0)
    min_gain = int(limits.get("ONTO_EVICT_MIN_GAIN_BITS", 0) or 0)
    k_drop = int(limits.get("ONTO_EVICT_K_DROP", 0) or 0)
    if window <= 0 or k_drop <= 0:
        return None

    idx = _epoch_index(epoch_id)
    if idx is None:
        return None
    start = max(1, idx - window + 1)
    window_epochs = list(range(start, idx + 1))

    events, _ = _load_corpus(state_dir, window_epochs)
    base_metrics = compute_dl_metrics(events=events, ontology_def=None)
    ontology_def = load_def_by_hash(active_ontology_id, inbox_root=state_dir / "current" / "inbox" / "ontology_v2", defs_root=dirs["defs"])
    active_metrics = compute_dl_metrics(events=events, ontology_def=ontology_def)
    dl_gain_bits = int(base_metrics.dl_bits - active_metrics.dl_bits)

    bad_epochs = _load_bad_epochs(bad_state_path)
    if dl_gain_bits < min_gain:
        bad_epochs += 1
    else:
        bad_epochs = 0

    if bad_epochs < k_drop:
        _write_bad_epochs(bad_state_path, bad_epochs)
        return None

    ledger_entries = load_ledger_entries(ledger_path)
    prev_line_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None
    active_set = _default_active_set(meta)
    active_set["active_snapshot_hash"] = _snapshot_active_set(active_set, dirs["snapshots"])
    _write_active_set(active_set_path, active_set, meta)

    evict_entry = build_ledger_entry(
        event="EVICT",
        epoch_id=epoch_id,
        ontology_id=active_ontology_id,
        ontology_def_hash=None,
        admit_receipt_hash=None,
        active_snapshot_hash=active_set.get("active_snapshot_hash"),
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    append_ledger_entry(ledger_path, evict_entry)
    _write_bad_epochs(bad_state_path, 0)
    return evict_entry
