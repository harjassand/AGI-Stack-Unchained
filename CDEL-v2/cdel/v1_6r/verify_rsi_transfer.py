"""Replay verifier for RSI transfer artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .canon import CanonError, canon_bytes, load_canon_json, loads
from .constants import meta_identities, require_constants
from .ctime.macro import load_macro_defs, load_macro_ledger
from .ctime.macro_cross_env import build_macro_cross_env_support_report
from .cmeta.translation import load_benchmark_pack, translate_validate
from .mech_patch_eval import compute_mech_patch_eval_cert
from .rsi_integrity_tracker import update_rsi_integrity_tracker
from .rsi_portfolio_tracker import update_rsi_portfolio_tracker
from .rsi_tracker import update_rsi_tracker
from .rsi_transfer_tracker import update_rsi_transfer_tracker
from .verify_rsi_portfolio import verify as verify_portfolio


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


def _load_instance_witnesses(epoch_dirs: list[Path]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for epoch_dir in epoch_dirs:
        diag_dir = epoch_dir / "diagnostics"
        index_path = diag_dir / "instance_witness_index_v1.json"
        if not index_path.exists():
            continue
        index_payload = load_canon_json(index_path)
        by_env = index_payload.get("witnesses_by_env_kind", {})
        if not isinstance(by_env, dict):
            continue
        for env_bucket in by_env.values():
            if not isinstance(env_bucket, dict):
                continue
            for kind_list in env_bucket.values():
                if not isinstance(kind_list, list):
                    continue
                for h in kind_list:
                    if not isinstance(h, str) or h in lookup:
                        continue
                    witness_path = diag_dir / "instance_witnesses_v1" / f"{h.split(':', 1)[1]}.json"
                    if witness_path.exists():
                        lookup[h] = load_canon_json(witness_path)
    return lookup


def verify(state_dir: Path) -> tuple[bool, str]:
    ok, reason = verify_portfolio(state_dir)
    if not ok:
        return False, f"portfolio verify failed: {reason}"

    constants = require_constants()
    epoch_dirs = _list_epoch_dirs(state_dir)
    if not epoch_dirs:
        return False, "no epochs found"

    state_events = _load_state_ledger_events(state_dir)
    prior_state: dict[str, Any] | None = None
    prior_integrity_state: dict[str, Any] | None = None
    prior_portfolio_state: dict[str, Any] | None = None
    prior_transfer_state: dict[str, Any] | None = None
    computed_barrier_entries: list[dict[str, Any]] = []
    last_transfer_report: dict[str, Any] | None = None
    transfer_receipt_seen = False

    eval_budget_reports: dict[str, Any] = {}
    eval_budget_hashes: dict[str, str] = {}
    mining_report_hashes: set[str] = set()
    family_semantics_reports: dict[str, Any] = {}
    family_semantics_hashes: dict[str, str] = {}
    instance_specs_reports: dict[str, Any] = {}
    translation_certs: dict[str, Any] = {}
    translation_cert_hashes: dict[str, str] = {}
    macro_cross_env_reports: dict[str, Any] = {}
    macro_cross_env_hashes: dict[str, str] = {}
    mech_patch_eval_certs: dict[str, Any] = {}
    mech_patch_eval_cert_hashes: dict[str, str] = {}

    trace_hash_map: dict[str, Path] = {}
    for epoch_dir in epoch_dirs:
        trace_path = epoch_dir / "traces" / "trace_heldout_v1.jsonl"
        if trace_path.exists():
            trace_hash_map[_hash_file(trace_path)] = trace_path

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
        sem_path = diag_dir / "family_semantics_report_v1.json"
        if sem_path.exists():
            report = load_canon_json(sem_path)
            report_epoch = report.get("epoch_id")
            if not isinstance(report_epoch, str):
                report_epoch = epoch_dir.name
            family_semantics_reports[report_epoch] = report
            family_semantics_hashes[report_epoch] = _hash_file(sem_path)
        specs_path = diag_dir / "instance_specs_v1.json"
        if specs_path.exists():
            instance_specs_reports[epoch_dir.name] = load_canon_json(specs_path)
        macro_path = diag_dir / "macro_cross_env_support_report_v1.json"
        if macro_path.exists():
            report = load_canon_json(macro_path)
            report_epoch = report.get("epoch_id")
            if not isinstance(report_epoch, str):
                report_epoch = epoch_dir.name
            macro_cross_env_reports[report_epoch] = report
            macro_cross_env_hashes[report_epoch] = _hash_file(macro_path)
        cert_path = diag_dir / "translation_cert_v1.json"
        if cert_path.exists():
            cert = load_canon_json(cert_path)
            patch_id = cert.get("patch_id")
            if isinstance(patch_id, str):
                translation_certs[patch_id] = cert
                translation_cert_hashes[patch_id] = _hash_file(cert_path)
        cert_dir = diag_dir / "meta_patch_certs"
        if cert_dir.exists():
            for path in sorted(cert_dir.glob("*.translation_cert_v1.json")):
                cert = load_canon_json(path)
                patch_id = cert.get("patch_id")
                if isinstance(patch_id, str) and patch_id not in translation_certs:
                    translation_certs[patch_id] = cert
                    translation_cert_hashes[patch_id] = _hash_file(path)
        mech_cert_path = diag_dir / "mech_patch_eval_cert_v1.json"
        if mech_cert_path.exists():
            cert = load_canon_json(mech_cert_path)
            patch_id = cert.get("patch_id")
            if isinstance(patch_id, str):
                mech_patch_eval_certs[patch_id] = cert
                mech_patch_eval_cert_hashes[patch_id] = _hash_file(mech_cert_path)

    benchmark_pack = None
    benchmark_path = state_dir / "current" / "meta_benchmark_pack_v1.json"
    if benchmark_path.exists():
        benchmark_pack = load_benchmark_pack(benchmark_path)
    if translation_certs and benchmark_pack is None:
        return False, "missing meta_benchmark_pack_v1.json"
    for patch_id, cert in translation_certs.items():
        patch_path = state_dir / "current" / "meta_patches" / f"{patch_id.split(':', 1)[1]}.json"
        if not patch_path.exists():
            continue
        patch = load_canon_json(patch_path)
        patch_payload = dict(patch)
        patch_payload["epoch_id"] = cert.get("epoch_id", "")
        recomputed = translate_validate(patch_payload, benchmark_pack)
        if "x-meta" in cert:
            recomputed = dict(recomputed)
            recomputed["x-meta"] = meta_identities()
        if canon_bytes(recomputed) != canon_bytes(cert):
            return False, f"translation cert mismatch for {patch_id}"

    mech_benchmark_pack = None
    mech_benchmark_path = state_dir / "current" / "mech_benchmark_pack_v1.json"
    if mech_benchmark_path.exists():
        mech_benchmark_pack = load_canon_json(mech_benchmark_path)
        if isinstance(mech_benchmark_pack, dict):
            for case in mech_benchmark_pack.get("cases", []) if isinstance(mech_benchmark_pack.get("cases"), list) else []:
                inst_path = case.get("instance_pack_path")
                if isinstance(inst_path, str) and inst_path:
                    path_obj = Path(inst_path)
                    if not path_obj.is_absolute():
                        case["instance_pack_path"] = str(mech_benchmark_path.parent / path_obj)

    macro_ledger_events = load_macro_ledger(state_dir / "current" / "macro_ledger_v1.jsonl")
    macro_def_map = {
        macro.get("macro_id"): macro
        for macro in load_macro_defs(state_dir / "current" / "macros")
        if isinstance(macro.get("macro_id"), str)
    }

    instance_witness_lookup = _load_instance_witnesses(epoch_dirs)
    family_lookup: dict[str, Any] = {}
    families_dir = state_dir / "current" / "families"
    if families_dir.exists():
        for path in sorted(families_dir.glob("*.json")):
            try:
                fam = load_canon_json(path)
            except Exception:
                continue
            fam_id = fam.get("family_id")
            if isinstance(fam_id, str):
                family_lookup[fam_id] = fam

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

        portfolio_epoch_artifacts = {
            "epoch_id": epoch_id,
            "meta": worstcase_report.get("x-meta", {}),
            "rsi_integrity_window_report": integrity_result.window_report,
            "rsi_integrity_receipt": integrity_result.integrity_receipt,
            "rsi_integrity_receipt_hash": _hash_file(integrity_receipt_path) if integrity_receipt_path.exists() else None,
            "rsi_window_report_hash": _hash_file(diagnostics_dir / "rsi_window_report_v1.json"),
            "barrier_ledger_entries": list(computed_barrier_entries),
            "state_ledger_events": state_events,
            "family_semantics_reports": family_semantics_reports,
            "family_semantics_report_hashes": family_semantics_hashes,
            "instance_specs_reports": instance_specs_reports,
            "translation_certs": translation_certs,
            "translation_cert_hashes": translation_cert_hashes,
        }

        try:
            portfolio_result = update_rsi_portfolio_tracker(
                constants=constants,
                epoch_artifacts=portfolio_epoch_artifacts,
                prior_state=prior_portfolio_state,
                strict=True,
            )
        except Exception as exc:
            return False, f"portfolio tracker error at {epoch_id}: {exc}"

        prior_portfolio_state = portfolio_result.state
        portfolio_report_path = diagnostics_dir / "rsi_portfolio_window_report_v1.json"
        if portfolio_report_path.exists():
            on_disk = load_canon_json(portfolio_report_path)
            if canon_bytes(on_disk) != canon_bytes(portfolio_result.window_report):
                reasons = portfolio_result.window_report.get("reason_codes", [])
                reason_str = ",".join([r for r in reasons if isinstance(r, str)])
                return False, f"portfolio window report mismatch at {epoch_id}: {reason_str}"

        portfolio_receipt_path = diagnostics_dir / "rsi_portfolio_receipt_v1.json"
        if portfolio_receipt_path.exists():
            if portfolio_result.portfolio_receipt is None:
                return False, f"missing portfolio receipt computation at {epoch_id}"
            on_disk = load_canon_json(portfolio_receipt_path)
            if canon_bytes(on_disk) != canon_bytes(portfolio_result.portfolio_receipt):
                return False, f"portfolio receipt mismatch at {epoch_id}"

        # Recompute macro cross-env support report if present
        macro_report_path = diagnostics_dir / "macro_cross_env_support_report_v1.json"
        if macro_report_path.exists():
            report = load_canon_json(macro_report_path)
            trace_hashes = report.get("x-trace_hashes") if isinstance(report, dict) else None
            trace_paths: list[Path] = []
            missing_hashes: list[str] = []
            if isinstance(trace_hashes, list) and trace_hashes:
                for h in trace_hashes:
                    if isinstance(h, str) and h in trace_hash_map:
                        trace_paths.append(trace_hash_map[h])
                    elif isinstance(h, str):
                        missing_hashes.append(h)
            if missing_hashes:
                return False, f"macro_cross_env trace hashes missing at {epoch_id}"
            if not trace_paths:
                trace_paths = [epoch_dir / "traces" / "trace_heldout_v1.jsonl"]
            trace_events: list[dict[str, Any]] = []
            instance_specs: dict[str, Any] = {}
            for path in trace_paths:
                if not path.exists():
                    continue
                trace_events.extend(load_canon_json_from_text(path.read_text(encoding="utf-8")))
                specs = instance_specs_reports.get(path.parent.parent.name)
                if isinstance(specs, dict):
                    instances = specs.get("instances")
                    if isinstance(instances, dict):
                        instance_specs.update(instances)
            macro_active_set_path = state_dir / "current" / "macro_active_set_v1.json"
            if not macro_active_set_path.exists():
                macro_active_set_path = diagnostics_dir / "macro_active_set_v1.json"
            if not macro_active_set_path.exists():
                return False, f"missing macro_active_set_v1.json at {epoch_id}"
            macro_active_set = load_canon_json(macro_active_set_path)
            active_ids = list(macro_active_set.get("active_macro_ids", [])) if isinstance(macro_active_set, dict) else []
            macro_defs = load_macro_defs(state_dir / "current" / "macros", allowed=active_ids)
            recomputed = build_macro_cross_env_support_report(
                epoch_id=epoch_id,
                trace_events=trace_events,
                macro_defs=macro_defs,
                macro_active_set_hash=_hash_file(macro_active_set_path),
                instance_specs=instance_specs,
            )
            if "x-trace_hashes" in report:
                recomputed = dict(recomputed)
                recomputed["x-trace_hashes"] = report.get("x-trace_hashes")
            if "x-meta" in report:
                recomputed = dict(recomputed)
                recomputed["x-meta"] = meta_identities()
            if canon_bytes(recomputed) != canon_bytes(report):
                return False, f"macro_cross_env_support_report mismatch at {epoch_id}"

        # Recompute mech patch eval cert if present
        mech_cert_path = diagnostics_dir / "mech_patch_eval_cert_v1.json"
        if mech_cert_path.exists() and mech_benchmark_pack is None:
            return False, f"missing mech_benchmark_pack_v1.json for {epoch_id}"
        if mech_cert_path.exists() and mech_benchmark_pack is not None:
            cert = load_canon_json(mech_cert_path)
            patch_id = cert.get("patch_id")
            patch_path = diagnostics_dir / "candidate_mech_patches_v2" / f"{str(patch_id).split(':', 1)[1]}.json"
            if patch_path.exists():
                patch = load_canon_json(patch_path)
                base_mech_path = diagnostics_dir / "mech_patch_base_mech_v1.json"
                base_mech = load_canon_json(base_mech_path) if base_mech_path.exists() else load_canon_json(state_dir / "current" / "base_mech.json")
                recomputed, _ = compute_mech_patch_eval_cert(
                    epoch_id=epoch_id,
                    patch=patch,
                    base_mech=base_mech,
                    benchmark_pack=mech_benchmark_pack,
                    base_patch_set_hash=cert.get("base_patch_set_hash"),
                    benchmark_pack_hash=cert.get("benchmark_pack_hash"),
                )
                overall = cert.get("overall") if isinstance(cert.get("overall"), dict) else None
                if overall is not None and isinstance(recomputed.get("overall"), dict):
                    selected = overall.get("selected")
                    if isinstance(selected, bool):
                        recomputed = dict(recomputed)
                        recomputed_overall = dict(recomputed.get("overall", {}))
                        recomputed_overall["selected"] = selected
                        recomputed["overall"] = recomputed_overall
                if "x-meta" in cert:
                    recomputed = dict(recomputed)
                    recomputed["x-meta"] = meta_identities()
                if canon_bytes(recomputed) != canon_bytes(cert):
                    return False, f"mech_patch_eval_cert mismatch at {epoch_id}"

        transfer_epoch_artifacts = {
            "epoch_id": epoch_id,
            "meta": worstcase_report.get("x-meta", {}),
            "rsi_portfolio_window_report": portfolio_result.window_report,
            "rsi_portfolio_receipt": portfolio_result.portfolio_receipt,
            "rsi_portfolio_receipt_hash": _hash_file(portfolio_receipt_path) if portfolio_receipt_path.exists() else None,
            "barrier_ledger_entries": list(computed_barrier_entries),
            "state_ledger_events": state_events,
            "family_semantics_reports": family_semantics_reports,
            "family_semantics_report_hashes": family_semantics_hashes,
            "instance_specs_reports": instance_specs_reports,
            "family_lookup": family_lookup,
            "instance_witness_lookup": instance_witness_lookup,
            "macro_cross_env_reports": macro_cross_env_reports,
            "macro_cross_env_report_hashes": macro_cross_env_hashes,
            "mech_patch_eval_certs": mech_patch_eval_certs,
            "mech_patch_eval_cert_hashes": mech_patch_eval_cert_hashes,
        }

        try:
            transfer_result = update_rsi_transfer_tracker(
                constants=constants,
                epoch_artifacts=transfer_epoch_artifacts,
                prior_state=prior_transfer_state,
                strict=True,
            )
        except Exception as exc:
            return False, f"transfer tracker error at {epoch_id}: {exc}"

        prior_transfer_state = transfer_result.state
        last_transfer_report = transfer_result.window_report
        transfer_report_path = diagnostics_dir / "rsi_transfer_window_report_v1.json"
        if transfer_report_path.exists():
            on_disk = load_canon_json(transfer_report_path)
            if canon_bytes(on_disk) != canon_bytes(transfer_result.window_report):
                reasons = transfer_result.window_report.get("reason_codes", [])
                reason_str = ",".join([r for r in reasons if isinstance(r, str)])
                return False, f"transfer window report mismatch at {epoch_id}: {reason_str}"

        transfer_receipt_path = diagnostics_dir / "rsi_transfer_receipt_v1.json"
        if transfer_receipt_path.exists():
            transfer_receipt_seen = True
            if transfer_result.transfer_receipt is None:
                return False, f"missing transfer receipt computation at {epoch_id}"
            on_disk = load_canon_json(transfer_receipt_path)
            if canon_bytes(on_disk) != canon_bytes(transfer_result.transfer_receipt):
                return False, f"transfer receipt mismatch at {epoch_id}"
        if transfer_result.transfer_receipt is not None:
            transfer_receipt_seen = True

    barrier_path = state_dir / "current" / "barrier_ledger_v1.jsonl"
    if barrier_path.exists():
        raw_lines = barrier_path.read_text(encoding="utf-8").splitlines()
        if len(raw_lines) != len(computed_barrier_entries):
            return False, "barrier ledger length mismatch"
        for raw, entry in zip(raw_lines, computed_barrier_entries):
            if canon_bytes(entry).decode("utf-8") != raw:
                return False, "barrier ledger mismatch"

    if not transfer_receipt_seen:
        if isinstance(last_transfer_report, dict):
            reasons = last_transfer_report.get("reason_codes", [])
            reason_str = ",".join([r for r in reasons if isinstance(r, str)])
            return False, f"transfer ignition not met: {reason_str or 'TRANSFER_RECEIPT_MISSING'}"
        return False, "transfer receipt missing"

    return True, "VALID"


def load_canon_json_from_text(text: str) -> list[dict[str, Any]]:
    from .canon import loads, canon_bytes

    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        payload = loads(line)
        if canon_bytes(payload).decode("utf-8") != line:
            raise CanonError("non-canonical JSON line")
        events.append(payload)
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    ok, reason = verify(Path(args.state_dir))
    if ok:
        print("VALID")
    else:
        print(f"INVALID: {reason}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
