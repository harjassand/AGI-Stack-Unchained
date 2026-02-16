"""Replay verifier for RSI integrity artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .canon import CanonError, canon_bytes, load_canon_json, loads
from .constants import require_constants
from .ctime.macro import load_macro_defs, load_macro_ledger
from .rsi_integrity_tracker import update_rsi_integrity_tracker
from .rsi_tracker import update_rsi_tracker


def _hash_file(path: Path) -> str:
    from .canon import sha256_prefixed

    if path.suffix == ".json":
        payload = load_canon_json(path)
        return sha256_prefixed(canon_bytes(payload))
    return sha256_prefixed(path.read_bytes())


def _list_epoch_dirs(state_dir: Path) -> list[Path]:
    epochs_dir = state_dir / "epochs"
    if not epochs_dir.exists():
        return []

    def _sort_key(path: Path) -> tuple[int, Any]:
        name = path.name
        tail = name.split("_")[-1]
        if tail.isdigit():
            return (0, int(tail))
        return (1, name)

    return sorted([p for p in epochs_dir.iterdir() if p.is_dir()], key=_sort_key)


def _load_state_ledger_events(state_dir: Path) -> dict[str, dict[str, Any]]:
    ledger_path = state_dir / "current" / "state_ledger_v1.jsonl"
    events: dict[str, dict[str, Any]] = {}
    if not ledger_path.exists():
        return events
    prev_hash = "sha256:" + "0" * 64
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            raise CanonError("non-canonical state ledger line")
        if payload.get("prev_ledger_hash") != prev_hash:
            raise CanonError("state ledger chain mismatch")
        prev_hash = payload.get("line_hash")
        epoch_id = payload.get("epoch_id")
        if isinstance(epoch_id, str):
            events[epoch_id] = payload
    return events


def verify(state_dir: Path) -> tuple[bool, str]:
    constants = require_constants()
    epoch_dirs = _list_epoch_dirs(state_dir)
    if not epoch_dirs:
        return False, "no epochs found"

    state_events = _load_state_ledger_events(state_dir)
    prior_state: dict[str, Any] | None = None
    prior_integrity_state: dict[str, Any] | None = None
    computed_barrier_entries: list[dict[str, Any]] = []

    eval_budget_reports: dict[str, Any] = {}
    eval_budget_hashes: dict[str, str] = {}
    mining_report_hashes: set[str] = set()
    for epoch_dir in epoch_dirs:
        diag_dir = epoch_dir / "diagnostics"
        eval_path = diag_dir / "eval_budget_report_v1.json"
        if eval_path.exists():
            report = load_canon_json(eval_path)
            report_epoch = report.get("epoch_id")
            if not isinstance(report_epoch, str):
                report_epoch = epoch_dir.name
            eval_budget_reports[report_epoch] = report
            eval_budget_hashes[report_epoch] = _hash_file(eval_path)
        mining_path = diag_dir / "macro_mining_report_v1.json"
        if mining_path.exists():
            mining_report_hashes.add(_hash_file(mining_path))

    macro_ledger_events = load_macro_ledger(state_dir / "current" / "macro_ledger_v1.jsonl")
    macro_def_map = {
        macro.get("macro_id"): macro
        for macro in load_macro_defs(state_dir / "current" / "macros")
        if isinstance(macro.get("macro_id"), str)
    }

    for epoch_dir in epoch_dirs:
        diagnostics_dir = epoch_dir / "diagnostics"
        epoch_id = epoch_dir.name
        if epoch_id not in state_events:
            return False, f"missing state ledger event for {epoch_id}"
        try:
            worstcase_report = load_canon_json(diagnostics_dir / "worstcase_report_v1.json")
            selection = load_canon_json(epoch_dir / "selection.json")
            work_meter = load_canon_json(epoch_dir / "work_meter_v1.json")
            rho_report = load_canon_json(diagnostics_dir / "rho_report_v1.json")
            anchor_pack = load_canon_json(diagnostics_dir / "anchor_pack_v1.json")
            state_head = load_canon_json(diagnostics_dir / "state_ledger_head_v1.json")
        except Exception as exc:
            return False, f"missing artifact for {epoch_id}: {exc}"

        epoch_artifacts = {
            "epoch_id": epoch_id,
            "meta": worstcase_report.get("x-meta", {}),
            "anchor_pack_hash": _hash_file(diagnostics_dir / "anchor_pack_v1.json"),
            "worstcase_report": worstcase_report,
            "worstcase_report_hash": _hash_file(diagnostics_dir / "worstcase_report_v1.json"),
            "selection": selection,
            "selection_hash": _hash_file(epoch_dir / "selection.json"),
            "work_meter": work_meter,
            "work_meter_hash": _hash_file(epoch_dir / "work_meter_v1.json"),
            "rho_report": rho_report,
            "rho_report_hash": _hash_file(diagnostics_dir / "rho_report_v1.json"),
            "state_ledger_head": state_head,
            "state_ledger_head_hash": _hash_file(diagnostics_dir / "state_ledger_head_v1.json"),
            "state_ledger_event": state_events[epoch_id],
        }

        try:
            result = update_rsi_tracker(
                constants=constants,
                epoch_artifacts=epoch_artifacts,
                prior_state=prior_state,
                strict=True,
            )
        except Exception as exc:
            return False, f"tracker error at {epoch_id}: {exc}"

        prior_state = result.state
        if result.barrier_entry is not None:
            computed_barrier_entries.append(result.barrier_entry)

        existing_report = diagnostics_dir / "rsi_window_report_v1.json"
        if existing_report.exists():
            on_disk = load_canon_json(existing_report)
            if canon_bytes(on_disk) != canon_bytes(result.window_report):
                return False, f"rsi window report mismatch at {epoch_id}"

        receipt_path = diagnostics_dir / "rsi_ignition_receipt_v1.json"
        if receipt_path.exists():
            if result.ignition_receipt is None:
                return False, f"missing ignition receipt computation at {epoch_id}"
            on_disk = load_canon_json(receipt_path)
            if canon_bytes(on_disk) != canon_bytes(result.ignition_receipt):
                return False, f"ignition receipt mismatch at {epoch_id}"

        integrity_epoch_artifacts = {
            "epoch_id": epoch_id,
            "meta": worstcase_report.get("x-meta", {}),
            "rsi_window_report": result.window_report,
            "rsi_window_report_hash": _hash_file(diagnostics_dir / "rsi_window_report_v1.json"),
            "rsi_ignition_receipt": result.ignition_receipt,
            "rsi_ignition_receipt_hash": _hash_file(receipt_path) if receipt_path.exists() else None,
            "barrier_ledger_entries": list(computed_barrier_entries),
            "eval_budget_reports": eval_budget_reports,
            "eval_budget_report_hashes": eval_budget_hashes,
            "macro_ledger_events": macro_ledger_events,
            "macro_defs": macro_def_map,
            "mining_report_hashes": mining_report_hashes,
        }

        try:
            integrity_result = update_rsi_integrity_tracker(
                constants=constants,
                epoch_artifacts=integrity_epoch_artifacts,
                prior_state=prior_integrity_state,
                strict=True,
            )
        except Exception as exc:
            return False, f"integrity tracker error at {epoch_id}: {exc}"

        prior_integrity_state = integrity_result.state
        integrity_report_path = diagnostics_dir / "rsi_integrity_window_report_v1.json"
        if integrity_report_path.exists():
            on_disk = load_canon_json(integrity_report_path)
            if canon_bytes(on_disk) != canon_bytes(integrity_result.window_report):
                reasons = integrity_result.window_report.get("reason_codes", [])
                reason_str = ",".join([r for r in reasons if isinstance(r, str)])
                return False, f"integrity window report mismatch at {epoch_id}: {reason_str}"

        integrity_receipt_path = diagnostics_dir / "rsi_integrity_receipt_v1.json"
        if integrity_receipt_path.exists():
            if integrity_result.integrity_receipt is None:
                return False, f"missing integrity receipt computation at {epoch_id}"
            on_disk = load_canon_json(integrity_receipt_path)
            if canon_bytes(on_disk) != canon_bytes(integrity_result.integrity_receipt):
                return False, f"integrity receipt mismatch at {epoch_id}"

    # Validate barrier ledger against computed entries
    barrier_path = state_dir / "current" / "barrier_ledger_v1.jsonl"
    if barrier_path.exists():
        raw_lines = [line for line in barrier_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(raw_lines) != len(computed_barrier_entries):
            return False, "barrier ledger entry count mismatch"
        for raw, expected in zip(raw_lines, computed_barrier_entries):
            if canon_bytes(expected).decode("utf-8") != raw:
                return False, "barrier ledger mismatch"

    return True, "VALID"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    ok, reason = verify(Path(args.state_dir))
    if ok:
        print("VALID")
    else:
        print(f"INVALID: {reason}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
