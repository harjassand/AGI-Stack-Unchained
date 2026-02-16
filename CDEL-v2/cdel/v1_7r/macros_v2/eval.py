"""Macro v2 evaluation + gating + ledger updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json
from ..constants import meta_identities
from ..demon.trace import load_trace_jsonl
from .encoder import encode_tokens
from .guards import validate_guard
from .io import compute_rent_bits, ensure_macro_dirs, verify_macro_def_id, verify_macro_rent_bits, write_macro_def_if_missing
from .ledger import append_ledger_entry, build_ledger_entry, load_ledger_entries
from .mdl import compute_ctx_mdl_gain


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


def _trace_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _load_corpus(state_dir: Path, window_epochs: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    trace_hashes: list[str] = []
    for idx in window_epochs:
        trace_path = _trace_path(state_dir, idx)
        if not trace_path.exists():
            raise CanonError(f"missing trace: {trace_path}")
        trace_hashes.append(_trace_hash(trace_path))
        events.extend(load_trace_jsonl(trace_path))
    return events, trace_hashes


def _corpus_hash(window_epochs: list[int], trace_hashes: list[str]) -> str:
    payload = {"window_epochs": window_epochs, "trace_hashes": trace_hashes}
    return sha256_prefixed(canon_bytes(payload))


def _meta_check(payload: dict[str, Any], meta: dict[str, str]) -> None:
    xmeta = payload.get("x-meta")
    if not isinstance(xmeta, dict):
        raise CanonError("x-meta missing")
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash"):
        if xmeta.get(key) != meta.get(key):
            raise CanonError("x-meta mismatch")


def _default_active_set(meta: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "macro_active_set_v2",
        "schema_version": 2,
        "active_macro_ids": [],
        "activation_epoch": None,
        "x-meta": meta,
    }


def _load_active_set(path: Path, meta: dict[str, str]) -> dict[str, Any]:
    if not path.exists():
        return _default_active_set(meta)
    payload = load_canon_json(path)
    if payload.get("schema") != "macro_active_set_v2":
        raise CanonError("macro_active_set schema mismatch")
    _meta_check(payload, meta)
    return payload


def _write_active_set(path: Path, payload: dict[str, Any], meta: dict[str, str]) -> None:
    active_ids = payload.get("active_macro_ids")
    if not isinstance(active_ids, list):
        active_ids = []
    payload["active_macro_ids"] = sorted({str(x) for x in active_ids if isinstance(x, str)})
    payload["x-meta"] = meta
    write_canon_json(path, payload)


def _state_head_hash(state_dir: Path) -> str:
    state_head = state_dir / "current" / "state_ledger_head_v1.json"
    if not state_head.exists():
        return "sha256:" + "0" * 64
    payload = load_canon_json(state_head)
    return sha256_prefixed(canon_bytes(payload))


def _macro_state_path(root: Path) -> Path:
    return root / "macro_state_v2.json"


def _load_macro_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("bad_epochs")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, int):
            out[key] = value
    return out


def _write_macro_state(path: Path, bad_epochs: dict[str, int]) -> None:
    write_canon_json(
        path,
        {
            "schema": "macro_state_v2",
            "schema_version": 2,
            "bad_epochs": bad_epochs,
        },
    )


def _macro_window_gain(events: list[dict[str, Any]], macro_def: dict[str, Any]) -> int:
    base_tokens, _ = encode_tokens(events, [])
    new_tokens, _ = encode_tokens(events, [macro_def])
    delta_tokens = int(base_tokens - new_tokens)
    rent_bits = int(macro_def.get("rent_bits", compute_rent_bits(macro_def)))
    return int(8 * delta_tokens - rent_bits)


def maybe_evict(
    *,
    state_dir: Path,
    epoch_id: str,
    constants: dict[str, Any],
) -> dict[str, Any] | None:
    meta = meta_identities()
    macros_root = state_dir / "current" / "macros_v2"
    dirs = ensure_macro_dirs(macros_root)
    active_set_path = dirs["active"] / "macro_active_set_v2.json"
    ledger_path = dirs["ledger"] / "macro_ledger_v2.jsonl"

    active_set = _load_active_set(active_set_path, meta)
    active_ids = list(active_set.get("active_macro_ids", []))
    if not active_ids:
        return None

    window = int(constants.get("MACRO_V2_WINDOW_EPOCHS", 0) or 0)
    k_drop = int(constants.get("MACRO_V2_EVICT_K_DROP", 0) or 0)
    if window <= 0 or k_drop <= 0:
        return None

    idx = _epoch_index(epoch_id)
    if idx is None:
        return None
    start = max(1, idx - window + 1)
    window_epochs = list(range(start, idx + 1))
    events, _ = _load_corpus(state_dir, window_epochs)

    bad_epochs = _load_macro_state(_macro_state_path(macros_root))

    evicted = None
    ledger_entries = load_ledger_entries(ledger_path)
    prev_line_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

    for macro_id in list(active_ids):
        try:
            macro_def = load_canon_json(dirs["defs"] / f"{macro_id.split(':',1)[1]}.json")
        except Exception:
            continue
        gain_bits = _macro_window_gain(events, macro_def)
        if gain_bits <= 0:
            bad_epochs[macro_id] = int(bad_epochs.get(macro_id, 0)) + 1
        else:
            bad_epochs[macro_id] = 0
        if bad_epochs[macro_id] >= k_drop:
            active_ids = [mid for mid in active_ids if mid != macro_id]
            evicted = build_ledger_entry(
                event="EVICT",
                epoch_id=epoch_id,
                macro_id=macro_id,
                macro_def_hash=None,
                macro_admit_receipt_hash=None,
                prev_line_hash=prev_line_hash,
                meta=meta,
            )
            append_ledger_entry(ledger_path, evicted)
            prev_line_hash = evicted.get("line_hash")
            bad_epochs[macro_id] = 0

    if evicted is not None:
        active_set["active_macro_ids"] = sorted({str(x) for x in active_ids if isinstance(x, str)})
        _write_active_set(active_set_path, active_set, meta)

    _write_macro_state(_macro_state_path(macros_root), bad_epochs)
    return evicted


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
    macros_root = state_dir / "current" / "macros_v2"
    dirs = ensure_macro_dirs(macros_root)
    ledger_path = dirs["ledger"] / "macro_ledger_v2.jsonl"
    active_set_path = dirs["active"] / "macro_active_set_v2.json"

    active_set = _load_active_set(active_set_path, meta)
    active_ids = list(active_set.get("active_macro_ids", []))

    ledger_entries = load_ledger_entries(ledger_path)
    prev_line_hash = ledger_entries[-1].get("line_hash") if ledger_entries else None

    events, trace_hashes = _load_corpus(state_dir, window_epochs)

    active_macros: list[dict[str, Any]] = []
    for mid in active_ids:
        try:
            macro_def = load_canon_json(dirs["defs"] / f"{mid.split(':',1)[1]}.json")
            active_macros.append(macro_def)
        except Exception:
            continue

    best_pass_gain = None
    best_pass_report = None
    best_pass_macro = None
    best_any_gain = None
    best_any_report = None
    best_any_macro = None

    for proposal in proposals:
        try:
            if proposal.get("schema") != "macro_def_v2":
                raise CanonError("macro_def schema mismatch")
            if int(proposal.get("schema_version", 0)) != 2:
                raise CanonError("macro_def schema_version mismatch")

            max_ctx = int(constants.get("MACRO_V2_MAX_GUARD_CTX", 0) or 0)
            validate_guard(proposal.get("guard"), max_ctx=max_ctx)

            body = proposal.get("body")
            if not isinstance(body, list) or not all(isinstance(item, dict) for item in body):
                raise CanonError("macro body invalid")
            verify_macro_def_id(proposal)
            verify_macro_rent_bits(proposal)

            gain = compute_ctx_mdl_gain(events=events, active_macros=active_macros, candidate_macro=proposal)
            ctx_mdl_gain_bits = int(gain.get("ctx_mdl_gain_bits", 0))
            support_families = int(gain.get("support_families_hold", 0))
            support_total = int(gain.get("support_total_hold", 0))

            passes = True
            reason = "PASS"
            if ctx_mdl_gain_bits < int(constants.get("MACRO_V2_CTX_MDL_GAIN_MIN_BITS", 0) or 0):
                passes = False
                reason = "CTX_MDL_GAIN_MIN"
            if support_families < int(constants.get("MACRO_V2_SUPPORT_FAMILIES_MIN", 0) or 0):
                passes = False
                reason = "SUPPORT_FAMILIES_MIN"

            report = {
                "schema": "macro_eval_report_v2",
                "schema_version": 2,
                "epoch_id": epoch_id,
                "corpus": {
                    "window_epochs": window_epochs,
                    "trace_hashes": trace_hashes,
                    "corpus_hash": _corpus_hash(window_epochs, trace_hashes),
                },
                "best_macro": {
                    "macro_id": proposal.get("macro_id"),
                    "ctx_mdl_gain_bits": ctx_mdl_gain_bits,
                    "support_families_hold": support_families,
                    "support_total_hold": support_total,
                },
                "decision": {"passes": bool(passes), "reason": reason},
                "x-meta": meta,
            }

            macro_id = proposal.get("macro_id") if isinstance(proposal.get("macro_id"), str) else ""
            if best_any_gain is None or ctx_mdl_gain_bits > best_any_gain or (
                ctx_mdl_gain_bits == best_any_gain and macro_id < (best_any_macro.get("macro_id") if isinstance(best_any_macro, dict) else "~~~~")
            ):
                best_any_gain = ctx_mdl_gain_bits
                best_any_report = report
                best_any_macro = proposal
            if passes:
                if best_pass_gain is None or ctx_mdl_gain_bits > best_pass_gain or (
                    ctx_mdl_gain_bits == best_pass_gain
                    and macro_id < (best_pass_macro.get("macro_id") if isinstance(best_pass_macro, dict) else "~~~~")
                ):
                    best_pass_gain = ctx_mdl_gain_bits
                    best_pass_report = report
                    best_pass_macro = proposal
        except Exception:
            if strict:
                continue
            continue

    def _active_report() -> dict[str, Any] | None:
        if not active_macros:
            return None
        best_gain = None
        best_macro = None
        best_stats = None
        for macro in active_macros:
            stats = compute_ctx_mdl_gain(events=events, active_macros=[], candidate_macro=macro)
            gain_bits = int(stats.get("ctx_mdl_gain_bits", 0))
            macro_id = macro.get("macro_id") if isinstance(macro.get("macro_id"), str) else ""
            if best_gain is None or gain_bits > best_gain or (
                gain_bits == best_gain and macro_id < (best_macro.get("macro_id") if isinstance(best_macro, dict) else "~~~~")
            ):
                best_gain = gain_bits
                best_macro = macro
                best_stats = stats
        if best_macro is None or best_stats is None:
            return None
        support_families = int(best_stats.get("support_families_hold", 0))
        support_total = int(best_stats.get("support_total_hold", 0))
        passes = True
        reason = "PASS_ACTIVE"
        if best_gain < int(constants.get("MACRO_V2_CTX_MDL_GAIN_MIN_BITS", 0) or 0):
            passes = False
            reason = "CTX_MDL_GAIN_MIN"
        if support_families < int(constants.get("MACRO_V2_SUPPORT_FAMILIES_MIN", 0) or 0):
            passes = False
            reason = "SUPPORT_FAMILIES_MIN"
        return {
            "schema": "macro_eval_report_v2",
            "schema_version": 2,
            "epoch_id": epoch_id,
            "corpus": {
                "window_epochs": window_epochs,
                "trace_hashes": trace_hashes,
                "corpus_hash": _corpus_hash(window_epochs, trace_hashes),
            },
            "best_macro": {
                "macro_id": best_macro.get("macro_id"),
                "ctx_mdl_gain_bits": int(best_gain),
                "support_families_hold": support_families,
                "support_total_hold": support_total,
            },
            "decision": {"passes": bool(passes), "reason": reason},
            "x-meta": meta,
        }

    if best_any_report is None or best_any_macro is None:
        report = _active_report()
        if report is None:
            return EvalOutcome(report=None, admit_receipt=None, ledger_entries=[], active_set=None, accepted=False)
        epoch_idx = _epoch_index(epoch_id)
        if epoch_idx is None:
            raise CanonError("invalid epoch_id")
        report_path = dirs["reports"] / f"macro_eval_report_v2_epoch_{epoch_idx}.json"
        write_canon_json(report_path, report)
        return EvalOutcome(report=report, admit_receipt=None, ledger_entries=[], active_set=active_set, accepted=False)

    epoch_idx = _epoch_index(epoch_id)
    if epoch_idx is None:
        raise CanonError("invalid epoch_id")

    report = best_pass_report if best_pass_report is not None else _active_report() or best_any_report
    report_path = dirs["reports"] / f"macro_eval_report_v2_epoch_{epoch_idx}.json"
    write_canon_json(report_path, report)
    report_hash = hash_json(report)

    passes = bool(report.get("decision", {}).get("passes"))
    if not passes or best_pass_macro is None:
        return EvalOutcome(report=report, admit_receipt=None, ledger_entries=[], active_set=active_set, accepted=False)

    macro_def = best_pass_macro
    macro_def_hash = hash_json(macro_def)
    write_macro_def_if_missing(macro_def, dirs["defs"])

    admit_receipt = {
        "schema": "macro_admit_receipt_v2",
        "schema_version": 2,
        "epoch_id": epoch_id,
        "macro_id": macro_def.get("macro_id"),
        "macro_def_hash": macro_def_hash,
        "macro_eval_report_hash": report_hash,
        "state_ledger_head_hash": _state_head_hash(state_dir),
        "verdict": "VALID",
        "x-meta": meta,
    }
    receipt_path = dirs["receipts"] / f"macro_admit_receipt_v2_epoch_{epoch_idx}.json"
    write_canon_json(receipt_path, admit_receipt)
    admit_hash = hash_json(admit_receipt)

    entries: list[dict[str, Any]] = []
    admit_entry = build_ledger_entry(
        event="ADMIT",
        epoch_id=epoch_id,
        macro_id=macro_def.get("macro_id"),
        macro_def_hash=macro_def_hash,
        macro_admit_receipt_hash=admit_hash,
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(admit_entry)
    prev_line_hash = admit_entry.get("line_hash")

    active_ids = [mid for mid in active_ids if isinstance(mid, str)]
    macro_id = macro_def.get("macro_id")
    if isinstance(macro_id, str) and macro_id not in active_ids:
        active_ids.append(macro_id)
    active_set["active_macro_ids"] = sorted(active_ids)
    active_set["activation_epoch"] = epoch_idx
    _write_active_set(active_set_path, active_set, meta)

    activate_entry = build_ledger_entry(
        event="ACTIVATE",
        epoch_id=epoch_id,
        macro_id=macro_def.get("macro_id"),
        macro_def_hash=macro_def_hash,
        macro_admit_receipt_hash=admit_hash,
        prev_line_hash=prev_line_hash,
        meta=meta,
    )
    entries.append(activate_entry)

    for entry in entries:
        append_ledger_entry(ledger_path, entry)

    _write_macro_state(_macro_state_path(macros_root), _load_macro_state(_macro_state_path(macros_root)))

    return EvalOutcome(report=report, admit_receipt=admit_receipt, ledger_entries=entries, active_set=active_set, accepted=True)
