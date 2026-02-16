"""Benchmark task runner."""

from __future__ import annotations

import json
from pathlib import Path

from cdel.config import Config
from cdel.gen.capacity_filler import CapacityFillerGenerator
from cdel.gen.enum import Candidate, EnumGenerator, TaskSpec
from cdel.kernel import canon
from cdel.kernel.deps import collect_sym_refs_in_defs
from cdel.gen.proof_synth import synthesize_missing_proofs
from cdel.kernel.cost import count_term_nodes
from cdel.kernel.parse import parse_definition
from cdel.kernel.proof import proof_size
from cdel.kernel.types import BOOL, INT, FunType, ListType, OptionType, PairType, Type, type_norm
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_scan_with_stats, load_definitions_with_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module


def run_tasks(
    cfg: Config,
    stream_path: Path,
    generator: str = "enum",
    report_path: str | None = None,
    out_dir: Path | None = None,
    closure_cache: bool = False,
    load_mode: str = "indexed",
    proof_synth: bool = False,
    no_report: bool = False,
    start_index: int = 0,
    on_result=None,
    on_event=None,
) -> dict:
    if generator not in {"enum", "enum-reuse", "capacity-filler"}:
        raise ValueError(f"unsupported generator: {generator}")
    if load_mode not in {"indexed", "scan"}:
        raise ValueError(f"unsupported load_mode: {load_mode}")
    if generator == "capacity-filler":
        gen = CapacityFillerGenerator()
    else:
        gen = EnumGenerator(mode="reuse" if generator == "enum-reuse" else "baseline")
    results = []
    task_index = -1
    recent_symbols: list[str] = []
    with stream_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task_index += 1
            if task_index < start_index:
                continue
            task = json.loads(line)
            task_id = task.get("task_id")
            task_group = task.get("task_group")
            certificate_mode = task.get("certificate_mode")
            if "module" in task:
                module = task.get("module") or {}
                if not module.get("parent"):
                    module["parent"] = read_head(cfg)
                module_payload = module.get("payload") or {}
                module_specs = module_payload.get("specs") or []
                proof_synth_attempted = False
                proof_synth_result = None
                missing_proofs = _count_missing_proofs(module_specs)
                if proof_synth:
                    if missing_proofs > 0:
                        proof_synth_attempted = True
                        deps = module_payload.get("declared_deps") or []
                        if load_mode == "scan":
                            defs_for_proof, _ = load_definitions_scan_with_stats(cfg, deps)
                        else:
                            conn = idx.connect(str(cfg.sqlite_path))
                            defs_for_proof, _ = load_definitions_with_stats(cfg, conn, deps, use_cache=closure_cache)
                        new_defs = {
                            parse_definition(defn).name: parse_definition(defn)
                            for defn in (module_payload.get("definitions") or [])
                        }
                        defs_for_proof.update(new_defs)
                        step_limit = int(cfg.data["evaluator"]["step_limit"])
                        module_specs, synthesized = synthesize_missing_proofs(module_specs, defs_for_proof, step_limit)
                        proof_synth_result = _synth_result(missing_proofs, synthesized)
                        module_payload["specs"] = module_specs
                if missing_proofs > 0 and not proof_synth:
                    proof_synth_result = "disabled"
                if missing_proofs == 0:
                    proof_synth_result = "skipped"
                budget_before = _budget_remaining(cfg)
                env_symbols_pre = _load_env_symbols(cfg)
                delta_hash = _payload_hash_for_module(module)
                result = commit_module(cfg, module)
                accepted = result.ok
                rejection = result.rejection.code.value if result.rejection else None
                cost = result.cost
                spec_work = result.spec_work
                remaining_budget = None
                closure_symbols = 0
                closure_modules = 0
                scanned_modules = 0
                index_lookups = 0
                cache_hits = 0
                cache_misses = 0
                tried = 1
                deps_count = None
                new_symbols_count = None
                reuse_score = None
                definition_size = None
                reuse_ratio = None
                retrieved_candidates_count = 0
                selected_symbols_used_count = 0
                proof_nodes = _proof_nodes(module_specs)
                proof_rejection = _proof_rejection_reason(result)
                if accepted:
                    deps_count = len(module_payload.get("declared_deps") or [])
                    new_symbols_count = len(module_payload.get("new_symbols") or [])
                    defs_raw = module_payload.get("definitions") or []
                    definition_size = _definition_size(defs_raw)
                    reuse_score = deps_count / ((definition_size or 0) + 1)
                    reuse_ratio = _reuse_ratio(defs_raw, env_symbols_pre, set(module_payload.get("new_symbols") or []))
                if result.ok:
                    new_symbols = module_payload.get("new_symbols") or []
                    conn = idx.connect(str(cfg.sqlite_path))
                    remaining_budget = idx.get_budget(conn)
                    if new_symbols:
                        if load_mode == "scan":
                            _, stats = load_definitions_scan_with_stats(cfg, new_symbols)
                        else:
                            _, stats = load_definitions_with_stats(
                                cfg, conn, new_symbols, use_cache=closure_cache
                            )
                        closure_symbols = stats["closure_symbols_count"]
                        closure_modules = stats["closure_modules_count"]
                        scanned_modules = stats.get("scanned_modules_count", 0)
                        index_lookups = stats.get("index_lookups_count", 0)
                        cache_hits = stats.get("closure_cache_hits", 0)
                        cache_misses = stats.get("closure_cache_misses", 0)
                if on_event:
                    on_event(
                        _event_row(
                            step_idx=task_index,
                            task_id=task_id,
                            delta_hash=delta_hash,
                            decision="ACCEPT" if accepted else "REJECT",
                            reject_reason=_reject_reason(result.rejection.code.value if result.rejection else None),
                            remaining_before=budget_before,
                            remaining_after=remaining_budget if accepted else None,
                            cost=cost,
                            error_detail=(result.rejection.details if result.rejection else None),
                        )
                    )
                results.append(
                    {
                        "task_id": task_id,
                        "task_group": task_group,
                        "certificate_mode": certificate_mode,
                        "load_mode": load_mode,
                        "accepted": accepted,
                        "rejection": rejection,
                        "cost": cost,
                        "spec_work": spec_work,
                        "remaining_budget": remaining_budget,
                        "closure_symbols_count": closure_symbols,
                        "closure_modules_count": closure_modules,
                        "scanned_modules_count": scanned_modules if accepted else 0,
                        "index_lookups_count": index_lookups,
                        "closure_cache_hits": cache_hits,
                        "closure_cache_misses": cache_misses,
                        "candidates_tried": tried,
                        "deps_count": deps_count,
                        "new_symbols_count": new_symbols_count,
                        "library_reuse_score": reuse_score,
                        "definition_size": definition_size,
                        "reuse_ratio": reuse_ratio,
                        "retrieved_candidates_count": retrieved_candidates_count,
                        "selected_symbols_used_count": selected_symbols_used_count,
                        "proof_nodes": proof_nodes,
                        "proof_rejection_reason": proof_rejection,
                        "proof_synth_attempted": proof_synth_attempted,
                        "proof_synth_result": proof_synth_result,
                        "gen_bodies_enumerated": None,
                        "gen_deduped": None,
                        "gen_output_fail": None,
                        "gen_min_size": None,
                        "gen_max_size": None,
                        "gen_candidates_returned": None,
                        "reject_type_count": None,
                        "reject_termination_count": None,
                        "reject_spec_count": None,
                    }
                )
                if on_result:
                    on_result(task_index, results[-1])
                if accepted:
                    recent_symbols = _update_recent_symbols(recent_symbols, module_payload.get("new_symbols") or [])
                continue
            new_symbol = task.get("new_symbol")
            type_str = task.get("type")
            allowed_deps = task.get("allowed_deps") or []
            specs = task.get("specs") or []
            typ = parse_type_str(type_str)
            env_symbols = _load_env_symbols(cfg)
            missing = [dep for dep in allowed_deps if dep not in env_symbols]
            if missing:
                if on_event:
                    on_event(
                        _event_row(
                            step_idx=task_index,
                            task_id=task_id,
                            delta_hash=None,
                            decision="REJECT",
                            reject_reason="deps",
                            remaining_before=_budget_remaining(cfg),
                            remaining_after=None,
                            cost=None,
                            error_detail="missing allowed_deps",
                        )
                    )
                results.append(
                    {
                        "task_id": task_id,
                        "certificate_mode": certificate_mode,
                        "load_mode": load_mode,
                        "accepted": False,
                        "rejection": "DEPS_MISMATCH",
                        "cost": None,
                        "spec_work": None,
                        "remaining_budget": None,
                        "closure_symbols_count": 0,
                        "closure_modules_count": 0,
                        "scanned_modules_count": 0,
                        "index_lookups_count": 0,
                        "closure_cache_hits": 0,
                        "closure_cache_misses": 0,
                        "candidates_tried": 0,
                        "deps_count": None,
                        "new_symbols_count": None,
                        "library_reuse_score": None,
                        "proof_nodes": _proof_nodes(specs),
                        "proof_rejection_reason": None,
                    }
                )
                if on_result:
                    on_result(task_index, results[-1])
                continue
            retrieved = _retrieve_context(
                cfg,
                new_symbol,
                typ,
                allowed_deps,
                recent_symbols,
                enabled=(generator == "enum-reuse"),
            )
            gen.symbol_priority = retrieved
            retrieved_count = len(retrieved)
            env_defs = {}
            if allowed_deps:
                if load_mode == "scan":
                    env_defs, _ = load_definitions_scan_with_stats(cfg, allowed_deps)
                else:
                    conn = idx.connect(str(cfg.sqlite_path))
                    env_defs, _ = load_definitions_with_stats(cfg, conn, allowed_deps, use_cache=closure_cache)
            task_spec = TaskSpec(new_symbol=new_symbol, typ=typ, specs=specs, allowed_deps=allowed_deps)
            candidates = gen.generate(task_spec, env_symbols, env_defs=env_defs)
            if generator == "enum-reuse":
                candidates = sorted(candidates, key=lambda c: -len(c.declared_deps))
                if allowed_deps:
                    reuse_candidates = [c for c in candidates if c.declared_deps]
                    if reuse_candidates:
                        candidates = reuse_candidates
            gen_stats = gen.last_stats or {}
            missing_proofs = _count_missing_proofs(specs)
            proof_synth_attempted = False
            proof_synth_result = None
            accepted = False
            rejection = None
            cost = None
            spec_work = None
            remaining_budget = None
            closure_symbols = 0
            closure_modules = 0
            scanned_modules = 0
            index_lookups = 0
            cache_hits = 0
            cache_misses = 0
            tried = 0
            capacity_reject = False
            deps_count = None
            new_symbols_count = None
            reuse_score = None
            definition_size = None
            reuse_ratio = None
            selected_symbols_used_count = 0
            proof_nodes = _proof_nodes(specs)
            proof_rejection = None
            best_synth = None
            reject_type = 0
            reject_termination = 0
            reject_spec = 0
            best_size = None
            for cand in candidates:
                tried += 1
                budget_before = _budget_remaining(cfg)
                cand_size = count_term_nodes(parse_definition(cand.definition).body)
                if best_size is None or cand_size < best_size:
                    best_size = cand_size
                specs_for_candidate = specs
                if proof_synth:
                    if missing_proofs > 0:
                        proof_synth_attempted = True
                        step_limit = int(cfg.data["evaluator"]["step_limit"])
                        defs_for_proof = dict(env_defs)
                        defs_for_proof[new_symbol] = parse_definition(cand.definition)
                        specs_for_candidate, synthesized = synthesize_missing_proofs(specs, defs_for_proof, step_limit)
                        synth_result = _synth_result(missing_proofs, synthesized)
                        best_synth = _best_synth_result(best_synth, synth_result)
                module = {
                    "schema_version": 1,
                    "dsl_version": 1,
                    "parent": read_head(cfg),
                    "payload": {
                        "new_symbols": [new_symbol],
                        "definitions": [cand.definition],
                        "declared_deps": cand.declared_deps,
                        "specs": specs_for_candidate,
                    },
                    "meta": {"generator": "enum_v0", "task_id": task_id},
                }
                delta_hash = _payload_hash_for_module(module)
                result = commit_module(cfg, module)
                if result.ok:
                    accepted = True
                    rejection = None
                    cost = result.cost
                    spec_work = result.spec_work
                    deps_count = len(cand.declared_deps)
                    new_symbols_count = 1
                    definition_size = cand_size
                    reuse_score = deps_count / (cand_size + 1)
                    reuse_ratio = _reuse_ratio([cand.definition], env_symbols, {new_symbol})
                    selected_symbols_used_count = _selected_used_count([cand.definition], retrieved)
                    conn = idx.connect(str(cfg.sqlite_path))
                    remaining_budget = idx.get_budget(conn)
                    if load_mode == "scan":
                        defs, stats = load_definitions_scan_with_stats(cfg, [new_symbol])
                    else:
                        defs, stats = load_definitions_with_stats(cfg, conn, [new_symbol], use_cache=closure_cache)
                    closure_symbols = stats["closure_symbols_count"]
                    closure_modules = stats["closure_modules_count"]
                    scanned_modules = stats.get("scanned_modules_count", 0)
                    index_lookups = stats.get("index_lookups_count", 0)
                    cache_hits = stats.get("closure_cache_hits", 0)
                    cache_misses = stats.get("closure_cache_misses", 0)
                    if proof_synth_attempted and proof_synth_result is None:
                        proof_synth_result = synth_result
                    if on_event:
                        on_event(
                            _event_row(
                                step_idx=task_index,
                                task_id=task_id,
                                delta_hash=delta_hash,
                                decision="ACCEPT",
                                reject_reason=None,
                                remaining_before=budget_before,
                                remaining_after=remaining_budget,
                                cost=cost,
                                error_detail=None,
                            )
                        )
                    break
                if result.rejection and result.rejection.code.value == "CAPACITY_EXCEEDED":
                    capacity_reject = True
                if result.rejection:
                    code = result.rejection.code.value
                    if code == "TYPE_ERROR":
                        reject_type += 1
                    elif code == "TERMINATION_FAIL":
                        reject_termination += 1
                    elif code == "SPEC_FAIL":
                        reject_spec += 1
                rejection = result.rejection.code.value if result.rejection else "error"
                proof_rejection = _proof_rejection_reason(result)
                if on_event:
                    on_event(
                        _event_row(
                            step_idx=task_index,
                            task_id=task_id,
                            delta_hash=delta_hash,
                            decision="REJECT",
                            reject_reason=_reject_reason(result.rejection.code.value if result.rejection else None),
                            remaining_before=budget_before,
                            remaining_after=None,
                            cost=result.cost,
                            error_detail=(result.rejection.details if result.rejection else None),
                        )
                    )
            if missing_proofs > 0 and not proof_synth:
                proof_synth_result = "disabled"
            if missing_proofs == 0:
                proof_synth_result = "skipped"
            if proof_synth_attempted and proof_synth_result is None:
                proof_synth_result = best_synth or "failed"
            if not accepted and capacity_reject:
                rejection = "CAPACITY_EXCEEDED"
            results.append(
                {
                    "task_id": task_id,
                    "task_group": task_group,
                    "certificate_mode": certificate_mode,
                    "load_mode": load_mode,
                    "accepted": accepted,
                    "rejection": rejection,
                    "cost": cost,
                    "spec_work": spec_work,
                    "remaining_budget": remaining_budget,
                    "closure_symbols_count": closure_symbols,
                    "closure_modules_count": closure_modules,
                    "scanned_modules_count": scanned_modules,
                    "index_lookups_count": index_lookups,
                    "closure_cache_hits": cache_hits,
                    "closure_cache_misses": cache_misses,
                    "candidates_tried": tried,
                    "deps_count": deps_count,
                    "new_symbols_count": new_symbols_count,
                    "library_reuse_score": reuse_score,
                    "definition_size": definition_size,
                    "reuse_ratio": reuse_ratio,
                    "retrieved_candidates_count": retrieved_count,
                    "selected_symbols_used_count": selected_symbols_used_count,
                    "proof_nodes": proof_nodes,
                    "proof_rejection_reason": proof_rejection,
                    "proof_synth_attempted": proof_synth_attempted,
                    "proof_synth_result": proof_synth_result,
                    "gen_bodies_enumerated": gen_stats.get("bodies_enumerated"),
                    "gen_deduped": gen_stats.get("deduped"),
                    "gen_output_fail": gen_stats.get("output_fail"),
                    "gen_min_size": gen_stats.get("min_size"),
                    "gen_max_size": gen_stats.get("max_size"),
                    "gen_candidates_returned": gen_stats.get("candidates_returned"),
                    "reject_type_count": reject_type,
                    "reject_termination_count": reject_termination,
                    "reject_spec_count": reject_spec,
                }
            )
            if on_result:
                on_result(task_index, results[-1])
            if accepted:
                recent_symbols = _update_recent_symbols(recent_symbols, [new_symbol])
    report = {"results": results, "ledger_head": read_head(cfg)}
    if not no_report:
        if report_path is None:
            if out_dir is None:
                out_dir = cfg.runs_dir / "_default" / report["ledger_head"]
            report_path = str(Path(out_dir) / "report.json")
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    return report


def _update_recent_symbols(recent: list[str], new_symbols: list[str], limit: int = 50) -> list[str]:
    if not new_symbols:
        return recent
    updated = list(recent) + list(new_symbols)
    return updated[-limit:]


def _definition_size(defs_raw: list[dict]) -> int:
    return sum(count_term_nodes(parse_definition(d).body) for d in defs_raw) if defs_raw else 0


def _reuse_ratio(defs_raw: list[dict], env_symbols: dict[str, Type], new_symbols: set[str]) -> float:
    if not defs_raw:
        return 0.0
    refs = collect_sym_refs_in_defs(defs_raw)
    r_new = {r for r in refs if r in new_symbols}
    r_old = {r for r in refs if r in env_symbols}
    denom = len(r_new) + len(r_old)
    return (len(r_old) / denom) if denom else 0.0


def _selected_used_count(defs_raw: list[dict], retrieved: list[str]) -> int:
    if not defs_raw or not retrieved:
        return 0
    refs = collect_sym_refs_in_defs(defs_raw)
    retrieved_set = set(retrieved)
    return sum(1 for r in refs if r in retrieved_set)


def _retrieve_context(
    cfg: Config,
    new_symbol: str,
    typ: Type,
    allowed_deps: list[str],
    recent_symbols: list[str],
    enabled: bool,
    type_limit: int = 20,
    prefix_limit: int = 20,
    recent_limit: int = 20,
    prefix_len: int = 2,
) -> list[str]:
    if not enabled or not allowed_deps:
        return []
    conn = idx.connect(str(cfg.sqlite_path))
    allowed = set(allowed_deps)
    type_matches = idx.search_symbols_by_type(conn, type_norm(typ), type_limit)
    prefix = new_symbol[:prefix_len] if len(new_symbol) >= prefix_len else new_symbol
    prefix_matches = idx.search_symbols_by_prefix(conn, prefix, prefix_limit) if prefix else []
    recent_matches = [s for s in reversed(recent_symbols) if s in allowed][:recent_limit]
    ordered: list[str] = []
    for group in (type_matches, prefix_matches, recent_matches):
        for sym in group:
            if sym in allowed and sym not in ordered:
                ordered.append(sym)
    return ordered


def _budget_remaining(cfg: Config) -> int | None:
    conn = idx.connect(str(cfg.sqlite_path))
    return idx.get_budget(conn)


def _payload_hash_for_module(module: dict) -> str | None:
    payload = module.get("payload")
    if not isinstance(payload, dict):
        return None
    canon_payload = canon.canonicalize_payload(payload)
    return canon.payload_hash_hex(canon_payload)


def _reject_reason(code: str | None) -> str | None:
    if not code:
        return None
    mapping = {
        "FRESHNESS_VIOLATION": "fresh_symbol",
        "DUPLICATE_SYMBOL": "fresh_symbol",
        "PARENT_MISMATCH": "override",
        "HASH_CANON_MISMATCH": "override",
        "SCHEMA_INVALID": "override",
        "TYPE_ERROR": "typing",
        "TERMINATION_FAIL": "totality",
        "MUTUAL_RECURSION_FORBIDDEN": "totality",
        "SPEC_FAIL": "spec",
        "DEPS_MISMATCH": "deps",
        "CAPACITY_EXCEEDED": "capacity",
    }
    return mapping.get(code, "override")


def _event_row(
    step_idx: int,
    task_id: str | None,
    delta_hash: str | None,
    decision: str,
    reject_reason: str | None,
    remaining_before: int | None,
    remaining_after: int | None,
    cost: int | None,
    error_detail: str | None,
) -> dict:
    return {
        "step_idx": step_idx,
        "task_id": task_id,
        "delta_hash": delta_hash,
        "decision": decision,
        "reject_reason": reject_reason,
        "remaining_budget_before": remaining_before,
        "cost": cost,
        "remaining_budget_after": remaining_after,
        "error_detail": error_detail,
    }


def parse_type_str(text: str) -> Type:
    tokens = _tokenize(text)
    pos = 0

    def parse_atom() -> Type:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("unexpected end of type")
        tok = tokens[pos]
        if tok == "Int":
            pos += 1
            return INT
        if tok == "Bool":
            pos += 1
            return BOOL
        if tok == "List":
            pos += 1
            if tokens[pos] != "[":
                raise ValueError("expected [")
            pos += 1
            inner = parse_type()
            if tokens[pos] != "]":
                raise ValueError("expected ]")
            pos += 1
            return ListType(inner)
        if tok == "Option":
            pos += 1
            if tokens[pos] != "[":
                raise ValueError("expected [")
            pos += 1
            inner = parse_type()
            if tokens[pos] != "]":
                raise ValueError("expected ]")
            pos += 1
            return OptionType(inner)
        if tok == "Pair":
            pos += 1
            if tokens[pos] != "[":
                raise ValueError("expected [")
            pos += 1
            left = parse_type()
            if tokens[pos] != ",":
                raise ValueError("expected ,")
            pos += 1
            right = parse_type()
            if tokens[pos] != "]":
                raise ValueError("expected ]")
            pos += 1
            return PairType(left, right)
        raise ValueError(f"unexpected token: {tok}")

    def parse_type() -> Type:
        nonlocal pos
        left = parse_atom()
        if pos < len(tokens) and tokens[pos] == "->":
            pos += 1
            right = parse_type()
            if isinstance(right, FunType):
                return FunType((left,) + right.args, right.ret)
            return FunType((left,), right)
        return left

    typ = parse_type()
    if pos != len(tokens):
        raise ValueError("unexpected tokens in type")
    return typ


def _tokenize(text: str) -> list[str]:
    tokens = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("->", i):
            tokens.append("->")
            i += 2
            continue
        if ch in "[],":
            tokens.append(ch)
            i += 1
            continue
        if ch.isalpha():
            j = i
            while j < len(text) and (text[j].isalpha() or text[j].isdigit()):
                j += 1
            tokens.append(text[i:j])
            i = j
            continue
        raise ValueError(f"unexpected char in type: {ch}")
    return tokens


def _load_env_symbols(cfg: Config) -> dict[str, Type]:
    from cdel.ledger import index as idx

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    cur = conn.execute("SELECT symbol, type_norm FROM symbols")
    symbols = {}
    for sym, typ in cur.fetchall():
        symbols[sym] = parse_type_str(typ)
    return symbols


def _proof_nodes(specs: list[dict]) -> int:
    total = 0
    for spec in specs:
        if spec.get("kind") not in {"proof", "proof_unbounded"}:
            continue
        try:
            total += proof_size(spec.get("proof") or {})
        except Exception:
            total += 0
    return total


def _proof_rejection_reason(result) -> str | None:
    if not result.rejection or not result.rejection.details:
        return None
    details = result.rejection.details
    if "PROOF_INVALID" in details:
        return details
    return None


def _count_missing_proofs(specs: list[dict]) -> int:
    missing = 0
    for spec in specs:
        if spec.get("kind") not in {"proof", "proof_unbounded"}:
            continue
        proof = spec.get("proof") or {}
        if not isinstance(proof, dict) or proof.get("tag") in {None, "missing"}:
            missing += 1
    return missing


def _synth_result(missing: int, synthesized: int) -> str:
    if missing <= 0:
        return "skipped"
    if synthesized <= 0:
        return "failed"
    if synthesized < missing:
        return "partial"
    return "success"


def _best_synth_result(current: str | None, candidate: str) -> str:
    order = {"failed": 0, "partial": 1, "success": 2}
    if current is None:
        return candidate
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current
