"""Ledger audit utilities."""

from __future__ import annotations

import json

from pathlib import Path

from cdel.config import Config
from cdel.kernel import canon
from cdel.kernel.deps import collect_sym_refs_in_defs, collect_sym_refs_in_specs
from cdel.kernel.parse import parse_definition
from cdel.kernel.spec import SpecError, StatCertContext, check_specs
from cdel.kernel.terminate import TerminationError, check_termination
from cdel.kernel.typecheck import TypeError as KernelTypeError
from cdel.kernel.typecheck import typecheck_definition
from cdel.kernel.types import FunType, Type
from cdel.ledger import index as idx
from cdel.ledger.storage import iter_order_log, read_object, read_head
from cdel.ledger.verifier import MutualRecursionError, _check_no_mutual_recursion
from cdel.sealed.config import load_sealed_config
from cdel.sealed.evalue import alpha_for_round, parse_decimal, format_decimal


class AuditError(Exception):
    pass


def audit_run(cfg: Config, out_dir: Path | None = None) -> dict:
    """Run fast + full audits and emit .ok/.json artifacts."""
    out_dir = out_dir or cfg.root
    out_dir = Path(out_dir)
    results = {}
    failures = []

    for label, full in (("fast", False), ("full", True)):
        ok = True
        error = None
        payload = None
        try:
            payload = audit_ledger(cfg, full=full)
        except Exception as exc:  # noqa: BLE001 - surface audit failure details
            ok = False
            error = str(exc)
            failures.append(f"{label}: {error}")
        record = {"ok": ok, "result": payload, "error": error}
        results[label] = record
        (out_dir / f"audit_{label}.json").write_text(
            json.dumps(record, sort_keys=True, indent=2), encoding="utf-8"
        )
        ok_path = out_dir / f"audit_{label}.ok"
        if ok:
            ok_path.write_text("ok\n", encoding="utf-8")
        elif ok_path.exists():
            ok_path.unlink()

    if failures:
        raise AuditError("audit failed: " + "; ".join(failures))
    return results


def audit_ledger(cfg: Config, full: bool = False) -> dict:
    seen: dict[str, str] = {}
    defs: dict[str, object] = {}
    sym_types: dict[str, Type] = {}
    module_count = 0
    stat_round = 1
    sealed_cfg = None
    alpha_spent = None
    if full:
        alpha_spent = parse_decimal("0")

    for module_hash in iter_order_log(cfg):
        module_count += 1
        payload_bytes = read_object(cfg, module_hash)
        payload = json.loads(payload_bytes.decode("utf-8"))
        canon_payload = canon.canonicalize_payload(payload)
        canon_bytes = canon.canonical_json_bytes(canon_payload)
        if canon_bytes != payload_bytes:
            raise AuditError(f"module {module_count} non-canonical payload")
        if canon.payload_hash_hex(canon_payload) != module_hash:
            raise AuditError(f"module {module_count} hash mismatch")

        definitions = canon_payload.get("definitions") or []
        for defn in definitions:
            name = defn.get("name")
            if name in seen:
                raise AuditError(f"module {module_count} symbol redefinition: {name}")
            seen[name] = canon.definition_hash(defn)

        if full:
            if sealed_cfg is None and any(spec.get("kind") == "stat_cert" for spec in canon_payload.get("specs") or []):
                sealed_cfg = load_sealed_config(cfg.data)
            stats = _audit_full_module(
                cfg,
                canon_payload,
                definitions,
                defs,
                sym_types,
                module_count,
                stat_round,
                sealed_cfg,
            )
            stat_round += stats.stat_cert_count
            if sealed_cfg is not None and stats.stat_cert_count:
                for offset in range(stats.stat_cert_count):
                    alpha_spent += alpha_for_round(
                        sealed_cfg.alpha_total,
                        stat_round - stats.stat_cert_count + offset,
                        sealed_cfg.alpha_schedule,
                    )

    # Check def_hash index once at the end to avoid O(n^2) work on large ledgers.
    _check_def_hash_index(cfg, seen)

    result = {
        "modules": module_count,
        "symbols": len(seen),
        "head": read_head(cfg),
    }
    if sealed_cfg is not None:
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        state = idx.get_stat_cert_state(conn)
        if state is not None and alpha_spent is not None:
            expected_round = stat_round
            if state[0] != expected_round:
                raise AuditError("stat_cert round mismatch in index")
            if format_decimal(alpha_spent) != str(state[1]):
                raise AuditError("stat_cert alpha_spent mismatch in index")
        result["stat_cert_round"] = stat_round
    return result


def _audit_full_module(
    cfg: Config,
    payload: dict,
    definitions: list[dict],
    defs: dict[str, object],
    sym_types: dict[str, Type],
    module_count: int,
    stat_round: int,
    sealed_cfg,
) -> SpecStats:
    new_symbols = payload.get("new_symbols") or []
    declared_deps = payload.get("declared_deps") or []
    specs = payload.get("specs") or []
    concepts = payload.get("concepts") or []

    if not isinstance(concepts, list):
        raise AuditError(f"module {module_count} concepts must be a list")
    concept_pairs: set[tuple[str, str]] = set()
    for entry in concepts:
        if not isinstance(entry, dict):
            raise AuditError(f"module {module_count} concept entry must be an object")
        concept = entry.get("concept")
        symbol = entry.get("symbol")
        if not isinstance(concept, str) or not isinstance(symbol, str):
            raise AuditError(f"module {module_count} concept fields must be strings")
        if (concept, symbol) in concept_pairs:
            raise AuditError(f"module {module_count} duplicate concept tag")
        concept_pairs.add((concept, symbol))
        if symbol not in new_symbols:
            raise AuditError(f"module {module_count} concept symbol not in new_symbols")

    actual_refs = collect_sym_refs_in_defs(definitions) | collect_sym_refs_in_specs(specs)
    new_symbol_set = set(new_symbols)
    actual_deps = {s for s in actual_refs if s not in new_symbol_set}
    unknown = [s for s in actual_deps if s not in defs]
    if unknown:
        raise AuditError(f"module {module_count} unknown deps: {', '.join(sorted(unknown))}")
    if set(declared_deps) != actual_deps:
        raise AuditError(f"module {module_count} declared_deps mismatch")

    new_defs = {}
    new_types: dict[str, Type] = {}
    for defn_json in definitions:
        parsed = parse_definition(defn_json)
        new_defs[parsed.name] = parsed
        new_types[parsed.name] = FunType(tuple(p.typ for p in parsed.params), parsed.ret_type)

    try:
        _check_no_mutual_recursion(new_defs)
        combined_types = dict(sym_types)
        combined_types.update(new_types)
        for defn in new_defs.values():
            typecheck_definition(defn, combined_types)
        for defn in new_defs.values():
            check_termination(defn)
        defs_with_new = dict(defs)
        defs_with_new.update(new_defs)
        combined_types = dict(sym_types)
        combined_types.update(new_types)
        step_limit = int(cfg.data["evaluator"]["step_limit"])
        stat_ctx = None
        if any(spec.get("kind") == "stat_cert" for spec in specs):
            if sealed_cfg is None:
                raise AuditError(f"module {module_count} stat_cert config missing")
            stat_ctx = StatCertContext(
                alpha_total=sealed_cfg.alpha_total,
                alpha_schedule=sealed_cfg.alpha_schedule,
                round_start=stat_round,
                allowed_keys=sealed_cfg.allowed_keys,
                eval_harness_id=sealed_cfg.eval_harness_id,
                eval_harness_hash=sealed_cfg.eval_harness_hash,
                eval_suite_hash=sealed_cfg.eval_suite_hash,
            )
        stats = check_specs(specs, defs_with_new, combined_types, step_limit, stat_ctx=stat_ctx)
    except (KernelTypeError, MutualRecursionError, TerminationError, SpecError) as exc:
        raise AuditError(f"module {module_count} kernel check failed: {exc}") from exc

    defs.update(new_defs)
    sym_types.update(new_types)
    return stats


def _check_def_hash_index(cfg: Config, seen: dict[str, str]) -> None:
    if not cfg.sqlite_path.exists():
        return
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    cur = conn.execute("SELECT COUNT(1) FROM def_hashes")
    row = cur.fetchone()
    if row is None or row[0] == 0:
        return
    for symbol, def_hash in seen.items():
        stored = idx.get_def_hash(conn, symbol)
        if stored is None:
            raise AuditError(f"def_hash missing in index: {symbol}")
        if stored != def_hash:
            raise AuditError(f"def_hash mismatch for {symbol}")
