"""Verifier pipeline for modules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import InvalidOperation
import json
import time
import logging

from cdel.config import Config
from cdel.kernel import canon
from cdel.kernel.ast import App, Cons, Fst, If, MatchList, MatchOption, OptionSome, Pair, Prim, Snd, Sym
from cdel.kernel.cost import count_term_nodes
from cdel.kernel.deps import collect_sym_refs_in_defs, collect_sym_refs_in_specs
from cdel.kernel.parse import parse_definition
from cdel.kernel.spec import SpecError, StatCertContext, check_specs
from cdel.kernel.terminate import TerminationError, check_termination
from cdel.kernel.typecheck import TypeError as KernelTypeError
from cdel.kernel.typecheck import typecheck_definition
from cdel.kernel.types import FunType, Type
from cdel.ledger import index as idx
from cdel.ledger.alias import alias_target
from cdel.ledger.closure import load_definitions
from cdel.ledger.errors import RejectCode, Rejection
from cdel.ledger.storage import append_order_log, object_path, read_head, write_meta, write_object, write_head
from cdel.sealed.config import load_sealed_config
from cdel.sealed.evalue import alpha_for_round, format_decimal, parse_decimal


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    payload_hash: str | None = None
    payload_bytes: bytes | None = None
    payload: dict | None = None
    cost: int | None = None
    spec_work: int | None = None
    symbol_types: dict[str, Type] | None = None
    defs: dict[str, object] | None = None
    actual_deps: set[str] | None = None
    symbol_deps: dict[str, set[str]] | None = None
    stat_cert_count: int | None = None
    stat_round_start: int | None = None
    stat_alpha_spent: str | None = None
    rejection: Rejection | None = None


class MutualRecursionError(Exception):
    pass


def verify_module(cfg: Config, module: dict) -> VerificationResult:
    try:
        _validate_schema(module)
        _precheck_stat_cert_evalue_format(module)
        payload = canon.canonicalize_payload(module.get("payload") or {})
        payload_bytes = canon.canonical_json_bytes(payload)
        payload_hash = canon.payload_hash_hex(payload)
        parent = module.get("parent")

        head = read_head(cfg)
        if parent != head:
            return _reject(RejectCode.PARENT_MISMATCH, "parent does not match head", f"expected {head}")

        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        remaining = idx.get_budget(conn)
        if remaining is None:
            remaining = int(cfg.data["ledger"]["budget"])
            idx.set_budget(conn, remaining)
            conn.commit()

        new_symbols = payload.get("new_symbols") or []
        definitions = payload.get("definitions") or []
        specs = payload.get("specs") or []
        declared_deps = payload.get("declared_deps") or []
        concepts = payload.get("concepts") or []

        if len(set(new_symbols)) != len(new_symbols):
            return _reject(RejectCode.DUPLICATE_SYMBOL, "duplicate new_symbols")
        if len(set(declared_deps)) != len(declared_deps):
            return _reject(RejectCode.SCHEMA_INVALID, "duplicate declared_deps")
        if any(not isinstance(sym, str) for sym in new_symbols):
            return _reject(RejectCode.SCHEMA_INVALID, "new_symbols must be strings")
        if any(not isinstance(sym, str) for sym in declared_deps):
            return _reject(RejectCode.SCHEMA_INVALID, "declared_deps must be strings")
        if not isinstance(concepts, list):
            return _reject(RejectCode.SCHEMA_INVALID, "concepts must be a list")

        concept_pairs: set[tuple[str, str]] = set()
        for entry in concepts:
            if not isinstance(entry, dict):
                return _reject(RejectCode.SCHEMA_INVALID, "concept entry must be an object")
            concept = entry.get("concept")
            symbol = entry.get("symbol")
            if not isinstance(concept, str) or not isinstance(symbol, str):
                return _reject(RejectCode.SCHEMA_INVALID, "concept and symbol must be strings")
            if (concept, symbol) in concept_pairs:
                return _reject(RejectCode.DUPLICATE_SYMBOL, "duplicate concept tag")
            concept_pairs.add((concept, symbol))
            if symbol not in new_symbols:
                return _reject(RejectCode.SCHEMA_INVALID, "concept symbol must be in new_symbols")

        for sym in new_symbols:
            if idx.symbol_exists(conn, sym):
                return _reject(RejectCode.FRESHNESS_VIOLATION, f"symbol already exists: {sym}")
        if object_path(cfg, payload_hash).exists():
            return _reject(RejectCode.HASH_CANON_MISMATCH, "payload already exists", payload_hash)

        def_names = [d.get("name") for d in definitions]
        if any(name is None for name in def_names):
            return _reject(RejectCode.SCHEMA_INVALID, "definition name missing")
        if len(set(def_names)) != len(def_names):
            return _reject(RejectCode.DUPLICATE_SYMBOL, "duplicate definition names")
        if set(def_names) != set(new_symbols):
            return _reject(RejectCode.SCHEMA_INVALID, "new_symbols does not match definitions")
        if any(sym in declared_deps for sym in new_symbols):
            return _reject(RejectCode.DEPS_MISMATCH, "declared_deps includes new symbols")

        actual_refs = collect_sym_refs_in_defs(definitions) | collect_sym_refs_in_specs(specs)
        new_symbol_set = set(new_symbols)
        actual_deps = {s for s in actual_refs if s not in new_symbol_set}
        unknown = [s for s in actual_deps if not idx.symbol_exists(conn, s)]
        if unknown:
            return _reject(RejectCode.DEPS_MISMATCH, "unknown symbol reference", ", ".join(sorted(unknown)))
        if set(declared_deps) != actual_deps:
            return _reject(RejectCode.DEPS_MISMATCH, "declared_deps mismatch", "")

        for spec in specs:
            if spec.get("kind") == "stat_cert":
                candidate = spec.get("candidate_symbol")
                baseline = spec.get("baseline_symbol")
                concept = spec.get("concept")
                eval_cfg = spec.get("eval") or {}
                if not isinstance(candidate, str):
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert candidate_symbol must be string")
                if not isinstance(baseline, str):
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert baseline_symbol must be string")
                if candidate not in new_symbols:
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert candidate_symbol must be new")
                if baseline in new_symbols:
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert baseline_symbol must be existing")
                if not isinstance(concept, str):
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert concept must be string")
                if (concept, candidate) not in concept_pairs:
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert concept must match concept tag")
                oracle_symbol = None
                if isinstance(eval_cfg, dict):
                    oracle_symbol = eval_cfg.get("oracle_symbol")
                if not isinstance(oracle_symbol, str):
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert oracle_symbol must be string")
                if oracle_symbol in new_symbols:
                    return _reject(RejectCode.SCHEMA_INVALID, "stat_cert oracle_symbol must be existing")

        old_defs = load_definitions(cfg, conn, list(actual_deps)) if actual_deps else {}
        sym_types: dict[str, Type] = {}
        for name, defn in old_defs.items():
            sym_types[name] = _definition_type(defn)

        new_defs = {}
        for defn in definitions:
            parsed = parse_definition(defn)
            new_defs[parsed.name] = parsed
            sym_types[parsed.name] = _definition_type(parsed)

        _check_no_mutual_recursion(new_defs)

        for defn in new_defs.values():
            typecheck_definition(defn, sym_types)

        for defn in new_defs.values():
            check_termination(defn)

        step_limit = int(cfg.data["evaluator"]["step_limit"])
        stat_ctx = None
        stat_round_start = None
        stat_alpha_spent = None
        sealed_cfg = None
        if any(spec.get("kind") == "stat_cert" for spec in specs):
            try:
                sealed_cfg = load_sealed_config(cfg.data)
            except (InvalidOperation, ValueError) as exc:
                return _reject(RejectCode.SCHEMA_INVALID, "stat_cert sealed config invalid", str(exc))
            state = idx.get_stat_cert_state(conn)
            if state is None:
                stat_round_start = 1
                stat_alpha_spent = format_decimal(parse_decimal("0"))
            else:
                stat_round_start = state[0]
                stat_alpha_spent = state[1]
            stat_ctx = StatCertContext(
                alpha_total=sealed_cfg.alpha_total,
                alpha_schedule=sealed_cfg.alpha_schedule,
                round_start=stat_round_start,
                allowed_keys=sealed_cfg.allowed_keys,
                eval_harness_id=sealed_cfg.eval_harness_id,
                eval_harness_hash=sealed_cfg.eval_harness_hash,
                eval_suite_hash=sealed_cfg.eval_suite_hash,
            )

        spec_stats = check_specs(specs, {**old_defs, **new_defs}, sym_types, step_limit, stat_ctx=stat_ctx)

        ast_nodes = sum(count_term_nodes(defn.body) for defn in new_defs.values())
        index_impact = len(new_symbols) + len(actual_deps) + len(new_symbols)
        cost_cfg = cfg.data["cost"]
        cost = (
            int(cost_cfg["alpha"]) * ast_nodes
            + int(cost_cfg["beta"]) * spec_stats.spec_work
            + int(cost_cfg["gamma"]) * index_impact
        )
        if cost > remaining:
            return VerificationResult(
                ok=False,
                cost=cost,
                spec_work=spec_stats.spec_work,
                rejection=Rejection(RejectCode.CAPACITY_EXCEEDED, "capacity exceeded", str(cost)),
            )

        per_symbol_deps: dict[str, set[str]] = {}
        for defn in definitions:
            refs = collect_sym_refs_in_defs([defn])
            deps = {s for s in refs if s != defn.get("name")}
            per_symbol_deps[defn.get("name")] = deps

        return VerificationResult(
            ok=True,
            payload_hash=payload_hash,
            payload_bytes=payload_bytes,
            payload=payload,
            cost=cost,
            spec_work=spec_stats.spec_work,
            symbol_types={k: v for k, v in sym_types.items() if k in new_defs},
            defs=new_defs,
            actual_deps=actual_deps,
            symbol_deps=per_symbol_deps,
            stat_cert_count=spec_stats.stat_cert_count,
            stat_round_start=stat_round_start,
            stat_alpha_spent=stat_alpha_spent,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return _reject(RejectCode.SCHEMA_INVALID, "schema validation failed", str(exc))
    except KernelTypeError as exc:
        return _reject(RejectCode.TYPE_ERROR, "type error", str(exc))
    except MutualRecursionError as exc:
        return _reject(RejectCode.MUTUAL_RECURSION_FORBIDDEN, "mutual recursion not allowed", str(exc))
    except TerminationError as exc:
        return _reject(RejectCode.TERMINATION_FAIL, "termination check failed", str(exc))
    except SpecError as exc:
        return _reject(RejectCode.SPEC_FAIL, "spec check failed", str(exc))


def commit_module(cfg: Config, module: dict) -> VerificationResult:
    result = verify_module(cfg, module)
    if not result.ok:
        return result
    assert result.payload_hash is not None
    assert result.payload_bytes is not None
    assert result.payload is not None
    assert result.cost is not None
    assert result.actual_deps is not None
    assert result.defs is not None
    assert result.symbol_types is not None
    assert result.symbol_deps is not None
    if result.stat_cert_count is None:
        stat_cert_count = 0
    else:
        stat_cert_count = result.stat_cert_count

    write_object(cfg, result.payload_hash, result.payload_bytes)
    meta = module.get("meta")
    if isinstance(meta, dict) and meta:
        try:
            write_meta(cfg, result.payload_hash, meta)
        except Exception:
            logging.warning("meta write failed; continuing without metadata")
    appended = append_order_log(cfg, result.payload_hash)
    if not appended:
        logging.warning("order.log already contains payload hash; skipping append")
        return result
    write_head(cfg, result.payload_hash)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    remaining = idx.get_budget(conn)
    if remaining is None:
        remaining = int(cfg.data["ledger"]["budget"])
        idx.set_budget(conn, remaining)
    def_hashes = {defn.get("name"): canon.definition_hash(defn) for defn in result.payload.get("definitions", [])}
    alias_map = {}
    for name, defn in result.defs.items():
        target = alias_target(defn)
        if target:
            alias_map[name] = target
    try:
        with conn:
            idx.insert_module(
                conn,
                result.payload_hash,
                module.get("parent"),
                result.payload_bytes,
                result.cost,
                int(time.time()),
            )
            idx.insert_symbols(conn, result.symbol_types, def_hashes, result.payload_hash)
            idx.insert_def_hashes(conn, def_hashes, result.payload_hash)
            idx.insert_deps(conn, result.payload_hash, result.actual_deps)
            for name, deps in result.symbol_deps.items():
                idx.insert_sym_deps(conn, name, deps)
            idx.insert_type_index(conn, result.symbol_types)
            idx.insert_aliases(conn, alias_map)
            idx.insert_concepts(conn, result.payload.get("concepts") or [], result.payload_hash)
            idx.insert_index_impact(
                conn,
                result.payload_hash,
                len(result.symbol_types),
                len(result.actual_deps),
                sum(len(deps) for deps in result.symbol_deps.values()),
                len(result.symbol_types),
                len(def_hashes),
            )
            idx.update_budget(conn, remaining - result.cost)
            if stat_cert_count > 0:
                sealed_cfg = load_sealed_config(cfg.data)
                round_start = result.stat_round_start or 1
                alpha_spent = parse_decimal(result.stat_alpha_spent or "0")
                for offset in range(stat_cert_count):
                    alpha_spent += alpha_for_round(
                        sealed_cfg.alpha_total,
                        round_start + offset,
                        sealed_cfg.alpha_schedule,
                    )
                idx.set_stat_cert_state(conn, round_start + stat_cert_count, format_decimal(alpha_spent))
    except Exception:
        conn.rollback()
        logging.warning("sqlite update failed; ledger remains append-only, run rebuild-index")
    return result


def _definition_type(defn) -> FunType:
    args = tuple(param.typ for param in defn.params)
    return FunType(args, defn.ret_type)


def _reject(code: RejectCode, reason: str, details: str | None = None) -> VerificationResult:
    return VerificationResult(ok=False, rejection=Rejection(code=code, reason=reason, details=details))


def _validate_schema(module: dict) -> None:
    if not isinstance(module, dict):
        raise ValueError("module must be an object")
    if module.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    if module.get("dsl_version") != 1:
        raise ValueError("unsupported dsl_version")
    if "parent" not in module or not isinstance(module.get("parent"), str):
        raise ValueError("module missing parent")
    if "payload" not in module or not isinstance(module.get("payload"), dict):
        raise ValueError("module missing payload")


def _precheck_stat_cert_evalue_format(module: dict) -> None:
    payload = module.get("payload")
    if not isinstance(payload, dict):
        return
    specs = payload.get("specs")
    if not isinstance(specs, list):
        return
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        if spec.get("kind") != "stat_cert":
            continue
        cert = spec.get("certificate")
        if not isinstance(cert, dict):
            raise SpecError(
                "stat_cert rejected: legacy evalue format detected. "
                "Expected {mantissa, exponent10}. Certificates must be regenerated."
            )
        evalue = cert.get("evalue")
        if not isinstance(evalue, dict):
            raise SpecError(
                "stat_cert rejected: legacy evalue format detected. "
                "Expected {mantissa, exponent10}. Certificates must be regenerated."
            )
        mantissa = evalue.get("mantissa")
        exponent = evalue.get("exponent10")
        if not isinstance(mantissa, str) or isinstance(exponent, bool) or not isinstance(exponent, int):
            raise SpecError(
                "stat_cert rejected: legacy evalue format detected. "
                "Expected {mantissa, exponent10}. Certificates must be regenerated."
            )


def _check_no_mutual_recursion(defs: dict[str, object]) -> None:
    graph: dict[str, set[str]] = {name: set() for name in defs}

    def collect(term, current: str) -> None:
        if isinstance(term, App) and isinstance(term.fn, Sym):
            target = term.fn.name
            if target in defs and target != current:
                graph[current].add(target)
        if isinstance(term, MatchList):
            collect(term.scrutinee, current)
            collect(term.nil_case, current)
            collect(term.cons_body, current)
            return
        if isinstance(term, MatchOption):
            collect(term.scrutinee, current)
            collect(term.none_case, current)
            collect(term.some_body, current)
            return
        if isinstance(term, If):
            collect(term.cond, current)
            collect(term.then, current)
            collect(term.els, current)
            return
        if isinstance(term, Cons):
            collect(term.head, current)
            collect(term.tail, current)
            return
        if isinstance(term, OptionSome):
            collect(term.value, current)
            return
        if isinstance(term, Pair):
            collect(term.left, current)
            collect(term.right, current)
            return
        if isinstance(term, (Fst, Snd)):
            collect(term.pair, current)
            return
        if isinstance(term, Prim):
            for arg in term.args:
                collect(arg, current)
            return
        if isinstance(term, App):
            collect(term.fn, current)
            for arg in term.args:
                collect(arg, current)
            return
        return

    for name, defn in defs.items():
        collect(defn.body, name)

    temp: set[str] = set()
    perm: set[str] = set()

    def visit(node: str) -> None:
        if node in perm:
            return
        if node in temp:
            raise MutualRecursionError("mutual recursion is not allowed")
        temp.add(node)
        for nxt in graph[node]:
            visit(nxt)
        temp.remove(node)
        perm.add(node)

    for node in graph:
        visit(node)
