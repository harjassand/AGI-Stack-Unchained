"""Untrusted solve loop for stat_cert-gated adoption."""

from __future__ import annotations

from dataclasses import dataclass
import time
from decimal import localcontext

from cdel.adoption.storage import read_head as read_adoption_head
from cdel.adoption.verifier import commit_adoption
from cdel.bench.taxonomy import FAMILY_SPECS
from cdel.config import Config
from cdel.kernel.canon import definition_hash
from cdel.kernel.deps import collect_sym_refs_in_defs, collect_sym_refs_in_specs
from cdel.gen.enum import EnumGenerator, TaskSpec
from cdel.kernel.parse import parse_definition
from cdel.kernel.types import BOOL, INT, FunType, ListType, Type, type_norm, type_to_json
from cdel.ledger import index as idx
from cdel.ledger.closure import compute_closure_with_stats, load_definitions
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.evalue import encoded_evalue_to_decimal, format_decimal, parse_decimal, parse_evalue
from cdel.sealed.worker import issue_stat_cert


@dataclass(frozen=True)
class Domain:
    int_min: int
    int_max: int
    list_max_len: int


@dataclass(frozen=True)
class SolveTask:
    concept: str
    family: str
    k: int
    returns_bool: bool
    fun_symbols: list[str]
    baseline_symbol: str
    oracle_symbol: str
    candidate_symbol: str


@dataclass(frozen=True)
class RetrievalContext:
    working_set: list[str]
    env_symbols: dict[str, Type]
    env_defs: dict[str, object]
    stats: dict[str, int | float]


FAMILY_DOMAINS: dict[str, dict[str, Domain]] = {
    "arith": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=0),
        "sealed": Domain(int_min=-10, int_max=10, list_max_len=0),
    },
    "reuse": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=0),
        "sealed": Domain(int_min=-10, int_max=10, list_max_len=0),
    },
    "predicates": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=0),
        "sealed": Domain(int_min=-10, int_max=10, list_max_len=0),
    },
    "lists": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=3),
        "sealed": Domain(int_min=-5, int_max=5, list_max_len=6),
    },
    "folds": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=3),
        "sealed": Domain(int_min=-5, int_max=5, list_max_len=6),
    },
    "higher": {
        "bounded": Domain(int_min=-2, int_max=2, list_max_len=0),
        "sealed": Domain(int_min=-10, int_max=10, list_max_len=0),
    },
}


def solve_task(
    cfg: Config,
    task_id: str,
    *,
    max_candidates: int,
    episodes: int,
    seed_key: str,
    private_key: str,
    strategy: str = "template_guided",
    max_context_symbols: int = 50,
) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    task = _task_from_id(conn, task_id)
    retrieved_by_concept = idx.list_symbols_for_concept(conn, task.concept, 50)
    retrieved_by_type = _retrieve_by_type(conn, task)
    if strategy not in {"baseline_enum", "retrieval_guided", "template_guided", "hybrid"}:
        raise ValueError("strategy must be baseline_enum, retrieval_guided, template_guided, or hybrid")

    retrieval: RetrievalContext | None = None
    if strategy in {"retrieval_guided", "hybrid"}:
        retrieval = _build_retrieval_context(cfg, conn, task, max_context_symbols)
    if task.family == "reuse":
        ok, rejection = _ensure_reuse_library_symbols(cfg, conn, task.k)
        if not ok:
            return _setup_failure(task, strategy, retrieved_by_concept, retrieved_by_type, rejection, retrieval)
    if task.fun_symbols:
        ok, rejection = _ensure_helper_symbols(cfg, conn)
        if not ok:
            return _setup_failure(task, strategy, retrieved_by_concept, retrieved_by_type, rejection, retrieval)
    ok, rejection = _ensure_base_symbols(cfg, conn, task)
    if not ok:
        return _setup_failure(task, strategy, retrieved_by_concept, retrieved_by_type, rejection, retrieval)

    attempts = []
    candidates, strategy_stats = _candidate_defs(task, max_candidates, strategy, retrieval)
    max_candidates = max(max_candidates, 1)
    for idx_k, candidate in enumerate(candidates[:max_candidates]):
        kind, defn = candidate
        candidate_hash = definition_hash(defn)
        stat_spec, round_before = _stat_cert_for(
            cfg,
            task,
            candidate_symbol=task.candidate_symbol,
            candidate_def=defn,
            episodes=episodes,
            seed_key=seed_key,
            private_key=private_key,
        )
        specs = [_bounded_spec(task, task.candidate_symbol), stat_spec]
        module = _candidate_module(task, defn, specs)
        declared_deps = module["payload"]["declared_deps"]
        module["parent"] = read_head(cfg)
        result = commit_module(cfg, module)
        round_after = _stat_round(cfg)
        adoption_hash = None
        if result.ok:
            adoption_hash = _adopt(cfg, task.concept, task.candidate_symbol, stat_spec)
        attempts.append(
            {
                "candidate_index": idx_k,
                "kind": kind,
                "symbol": task.candidate_symbol,
                "candidate_hash": candidate_hash,
                "accepted": result.ok,
                "rejection": result.rejection.code.value if result.rejection else None,
                "module_hash": result.payload_hash if result.ok else None,
                "adoption_hash": adoption_hash,
                "declared_deps": declared_deps,
                "retrieval": retrieval.stats if retrieval else None,
                "template_stats": strategy_stats.get("templates"),
                "alpha": _alpha_summary(stat_spec, round_before, round_after, result.ok),
            }
        )
        if result.ok:
            break

    return {
        "task_id": task_id,
        "concept": task.concept,
        "family": task.family,
        "strategy": strategy,
        "retrieved_by_concept": retrieved_by_concept,
        "retrieved_by_type": retrieved_by_type,
        "retrieval": retrieval.stats if retrieval else None,
        "strategy_stats": strategy_stats,
        "attempts": attempts,
    }


def _task_from_id(conn, task_id: str) -> SolveTask:
    family, k = _parse_concept(task_id)
    prefix = task_id.replace(".", "_")
    candidate_base = f"{prefix}_candidate"
    candidate_symbol = _fresh_symbol(conn, candidate_base)
    return SolveTask(
        concept=task_id,
        family=family,
        k=k,
        returns_bool=(family == "predicates"),
        fun_symbols=["id_int", "inc_int", "double_int"] if family == "higher" else [],
        baseline_symbol=f"{prefix}_baseline",
        oracle_symbol=f"{prefix}_oracle",
        candidate_symbol=candidate_symbol,
    )


def _parse_concept(concept: str) -> tuple[str, int]:
    for family, spec in FAMILY_SPECS.items():
        prefix = str(spec["prefix"])
        if concept.startswith(prefix + "."):
            tail = concept[len(prefix) + 1 :]
            try:
                return family, int(tail)
            except ValueError as exc:
                raise ValueError(f"invalid concept suffix: {concept}") from exc
    raise ValueError(f"unknown concept: {concept}")


def _fresh_symbol(conn, base: str) -> str:
    if not idx.symbol_exists(conn, base):
        return base
    version = 2
    while idx.symbol_exists(conn, f"{base}_v{version}"):
        version += 1
    return f"{base}_v{version}"


def _ensure_helper_symbols(cfg: Config, conn) -> tuple[bool, str | None]:
    helpers = {
        "id_int": _int_identity_def("id_int"),
        "inc_int": _int_add_def("inc_int", 1),
        "double_int": _int_mul_def("double_int", 2),
    }
    missing = [name for name in helpers if not idx.symbol_exists(conn, name)]
    if not missing:
        return True, None
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": missing,
            "definitions": [helpers[name] for name in missing],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, module)
    if not result.ok:
        rejection = result.rejection.code.value if result.rejection else "UNKNOWN"
        return False, rejection
    return True, None


def _ensure_base_symbols(cfg: Config, conn, task: SolveTask) -> tuple[bool, str | None]:
    missing = []
    definitions = []
    if not idx.symbol_exists(conn, task.oracle_symbol):
        definitions.append(_oracle_def(task, task.oracle_symbol))
        missing.append(task.oracle_symbol)
    if not idx.symbol_exists(conn, task.baseline_symbol):
        definitions.append(_baseline_def(task, task.baseline_symbol))
        missing.append(task.baseline_symbol)
    if not missing:
        return True, None
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": missing,
            "definitions": definitions,
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, module)
    if not result.ok:
        rejection = result.rejection.code.value if result.rejection else "UNKNOWN"
        return False, rejection
    return True, None


def _ensure_reuse_library_symbols(cfg: Config, conn, k: int) -> tuple[bool, str | None]:
    name = _reuse_lib_name(k)
    if idx.symbol_exists(conn, name):
        return True, None
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": [name],
            "definitions": [_int_add_def(name, k)],
            "declared_deps": [],
            "specs": [],
            "concepts": [{"concept": f"lib.add_k.{k}", "symbol": name}],
        },
    }
    result = commit_module(cfg, module)
    if not result.ok:
        rejection = result.rejection.code.value if result.rejection else "UNKNOWN"
        return False, rejection
    return True, None


def _setup_failure(
    task: SolveTask,
    strategy: str,
    retrieved_by_concept: list[str],
    retrieved_by_type: list[str],
    rejection: str | None,
    retrieval: RetrievalContext | None,
) -> dict:
    return {
        "task_id": task.concept,
        "concept": task.concept,
        "family": task.family,
        "strategy": strategy,
        "retrieved_by_concept": retrieved_by_concept,
        "retrieved_by_type": retrieved_by_type,
        "retrieval": retrieval.stats if retrieval else None,
        "attempts": [
            {
                "candidate_index": None,
                "kind": "setup",
                "symbol": None,
                "candidate_hash": None,
                "accepted": False,
                "rejection": rejection,
                "module_hash": None,
                "adoption_hash": None,
                "alpha": None,
            }
        ],
    }


def _build_retrieval_context(
    cfg: Config,
    conn,
    task: SolveTask,
    max_context_symbols: int,
) -> RetrievalContext:
    start = time.perf_counter()
    by_concept = idx.list_symbols_for_concept(conn, task.concept, max_context_symbols)
    by_type = _retrieve_by_type(conn, task)
    working_set: list[str] = []
    for sym in by_concept + by_type:
        if sym not in working_set:
            working_set.append(sym)
        if max_context_symbols and len(working_set) >= max_context_symbols:
            break

    closure_symbols = 0
    closure_lookups = 0
    if working_set:
        closure, lookups = compute_closure_with_stats(conn, working_set)
        closure_symbols = len(closure)
        closure_lookups = lookups

    env_defs: dict[str, object] = {}
    if working_set:
        env_defs = load_definitions(cfg, conn, working_set)

    env_symbols: dict[str, Type] = {}
    for name, defn in env_defs.items():
        if name not in working_set:
            continue
        env_symbols[name] = FunType(tuple(p.typ for p in defn.params), defn.ret_type)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    stats = {
        "retrieved_concept_count": len(by_concept),
        "retrieved_type_count": len(by_type),
        "working_set_count": len(working_set),
        "closure_symbols_count": closure_symbols,
        "closure_lookups": closure_lookups,
        "retrieval_ms": elapsed_ms,
    }
    return RetrievalContext(working_set=working_set, env_symbols=env_symbols, env_defs=env_defs, stats=stats)


def _candidate_defs(
    task: SolveTask,
    max_candidates: int,
    strategy: str,
    retrieval: RetrievalContext | None,
) -> tuple[list[tuple[str, dict]], dict]:
    bounded = FAMILY_DOMAINS[task.family]["bounded"]
    candidates: list[tuple[str, dict]] = []
    stats: dict[str, object] = {}
    if strategy in {"template_guided", "hybrid"}:
        template_candidates, template_stats = _template_candidates(task, bounded, retrieval, max_candidates)
        candidates.extend(template_candidates)
        stats["templates"] = template_stats

    if strategy in {"baseline_enum", "retrieval_guided", "hybrid"}:
        allowed_deps: list[str] = []
        env_symbols: dict[str, Type] = {}
        env_defs: dict[str, object] = {}
        if strategy in {"retrieval_guided", "hybrid"} and retrieval is not None:
            allowed_deps = list(retrieval.working_set)
            env_symbols = retrieval.env_symbols
            env_defs = retrieval.env_defs
        enum_candidates, enum_stats = _enum_candidates(task, max_candidates, allowed_deps, env_symbols, env_defs)
        candidates.extend(enum_candidates)
        stats["enum"] = enum_stats

    return candidates, stats


def _enum_candidates(
    task: SolveTask,
    max_candidates: int,
    allowed_deps: list[str],
    env_symbols: dict[str, Type],
    env_defs: dict[str, object],
) -> tuple[list[tuple[str, dict]], dict]:
    bounded_spec = _bounded_spec(task, task.candidate_symbol)
    task_spec = TaskSpec(
        new_symbol=task.candidate_symbol,
        typ=_task_type(task),
        specs=[bounded_spec],
        allowed_deps=allowed_deps,
    )
    enum_gen = EnumGenerator(max_candidates=max_candidates, max_size=6)
    candidates = enum_gen.generate(task_spec, env_symbols, env_defs)
    return [("enum", cand.definition) for cand in candidates], dict(enum_gen.last_stats)


def _template_candidates(
    task: SolveTask,
    bounded: Domain,
    retrieval: RetrievalContext | None,
    max_candidates: int,
) -> tuple[list[tuple[str, dict]], dict]:
    candidates: list[tuple[str, dict]] = []
    env_symbols = retrieval.env_symbols if retrieval else {}
    stats = {
        "templates_tried": 0,
        "holes_filled": 0,
        "prunes": 0,
        "template_counts": {},
    }

    def record_attempt(kind: str, produced: int) -> None:
        stats["templates_tried"] += 1
        counts = stats["template_counts"].setdefault(kind, {"attempted": 0, "produced": 0, "pruned": 0})
        counts["attempted"] += 1
        if produced == 0:
            counts["pruned"] += 1
            stats["prunes"] += 1
        else:
            counts["produced"] += produced

    def add_candidate(kind: str, defn: dict, holes: int) -> None:
        if len(candidates) >= max_candidates:
            return
        candidates.append((kind, defn))
        stats["holes_filled"] += holes

    if task.family == "arith":
        add_candidate("tmpl_add_k", _int_add_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_add_k", 1)
    elif task.family == "predicates":
        add_candidate("tmpl_lt_k", _pred_lt_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_lt_k", 1)
        add_candidate("tmpl_eq_k", _pred_eq_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_eq_k", 1)
    elif task.family == "lists":
        add_candidate("tmpl_len_plus_k", _len_plus_k_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_len_plus_k", 1)
    elif task.family == "folds":
        add_candidate("tmpl_sum_plus_k", _sum_plus_k_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_sum_plus_k", 1)
    elif task.family == "higher":
        add_candidate("tmpl_apply_add_k", _apply_add_k_def(task.candidate_symbol, task.k), 0)
        record_attempt("tmpl_apply_add_k", 1)
    elif task.family == "reuse":
        add_candidate(
            "tmpl_compose_lib",
            _compose_def(task.candidate_symbol, _reuse_lib_name(task.k), _reuse_lib_name(task.k)),
            2,
        )
        record_attempt("tmpl_compose_lib", 1)

    compose_candidates = _compose_templates(task, env_symbols, max_candidates - len(candidates))
    produced = len(compose_candidates)
    if compose_candidates:
        for defn in compose_candidates:
            add_candidate("tmpl_compose", defn, 2)
        record_attempt("tmpl_compose", produced)
    else:
        record_attempt("tmpl_compose", 0)

    if candidates and len(candidates) >= max_candidates:
        return candidates[:max_candidates], stats

    conditional_candidates = _conditional_templates(task, env_symbols, max_candidates - len(candidates))
    produced = len(conditional_candidates)
    if conditional_candidates:
        for defn in conditional_candidates:
            add_candidate("tmpl_if", defn, 3)
        record_attempt("tmpl_if", produced)
    else:
        record_attempt("tmpl_if", 0)

    return candidates[:max_candidates], stats


def _compose_templates(task: SolveTask, env_symbols: dict[str, Type], limit: int) -> list[dict]:
    if limit <= 0:
        return []
    target = _task_type(task)
    if not isinstance(target, FunType):
        return []
    if len(target.args) != 1 or target.args[0] != target.ret:
        return []
    funcs = [name for name, typ in env_symbols.items() if typ == target]
    funcs = sorted(funcs)
    if not funcs:
        return []
    out: list[dict] = []
    for f in funcs:
        for g in funcs:
            out.append(_compose_def(task.candidate_symbol, f, g))
            if len(out) >= limit:
                return out
    return out


def _conditional_templates(task: SolveTask, env_symbols: dict[str, Type], limit: int) -> list[dict]:
    if limit <= 0:
        return []
    target = _task_type(task)
    if not isinstance(target, FunType) or len(target.args) != 1:
        return []
    arg_type = target.args[0]
    pred_type = FunType((arg_type,), BOOL)
    preds = sorted(name for name, typ in env_symbols.items() if typ == pred_type)
    branches = sorted(name for name, typ in env_symbols.items() if typ == target)
    if not preds or not branches:
        return []
    out: list[dict] = []
    arg = _var("x")
    for pred in preds:
        for left in branches:
            for right in branches:
                cond = _app_sym(pred, [arg])
                then = _app_sym(left, [arg])
                els = _app_sym(right, [arg])
                body = _if(cond, then, els)
                out.append(
                    _definition(
                        task.candidate_symbol,
                        [{"name": "x", "type": type_to_json(arg_type)}],
                        type_to_json(target.ret),
                        body,
                    )
                )
                if len(out) >= limit:
                    return out
    return out


def _candidate_module(task: SolveTask, defn: dict, specs: list[dict]) -> dict:
    actual_refs = collect_sym_refs_in_defs([defn]) | collect_sym_refs_in_specs(specs)
    actual_deps = sorted({ref for ref in actual_refs if ref != task.candidate_symbol})
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": [task.candidate_symbol],
            "definitions": [defn],
            "declared_deps": actual_deps,
            "specs": specs,
            "concepts": [{"concept": task.concept, "symbol": task.candidate_symbol}],
        },
    }


def _bounded_spec(task: SolveTask, symbol: str) -> dict:
    bounded = FAMILY_DOMAINS[task.family]["bounded"]
    vars_list = _vars_for_family(task.family)
    assert_term = _assert_term(task, symbol)
    domain = {
        "int_min": bounded.int_min,
        "int_max": bounded.int_max,
        "list_max_len": bounded.list_max_len,
    }
    if task.fun_symbols:
        domain["fun_symbols"] = list(task.fun_symbols)
    return {
        "kind": "forall",
        "vars": vars_list,
        "domain": domain,
        "assert": assert_term,
    }


def _stat_cert_for(
    cfg: Config,
    task: SolveTask,
    *,
    candidate_symbol: str,
    candidate_def: dict,
    episodes: int,
    seed_key: str,
    private_key: str,
) -> tuple[dict, int]:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    round_idx = 1 if state is None else state[0]
    sealed_domain = FAMILY_DOMAINS[task.family]["sealed"]
    cfg.data["spec"]["int_min"] = sealed_domain.int_min
    cfg.data["spec"]["int_max"] = sealed_domain.int_max
    cfg.data["spec"]["list_max_len"] = sealed_domain.list_max_len
    request = {
        "kind": "stat_cert",
        "concept": task.concept,
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": task.baseline_symbol,
        "candidate_symbol": candidate_symbol,
        "eval": {
            "episodes": episodes,
            "max_steps": 80,
            "paired_seeds": True,
            "oracle_symbol": task.oracle_symbol,
        },
        "risk": {"evalue_threshold": "1"},
    }
    if task.fun_symbols:
        request["eval"]["fun_symbols"] = list(task.fun_symbols)
    extra_defs = {candidate_symbol: parse_definition(candidate_def)}
    spec = issue_stat_cert(cfg, request, private_key, seed_key.encode("utf-8"), extra_defs=extra_defs)
    return spec, round_idx


def _stat_round(cfg: Config) -> int:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    return 1 if state is None else int(state[0])


def _alpha_summary(spec: dict, round_before: int, round_after: int, accepted: bool) -> dict:
    risk = spec.get("risk") or {}
    cert = spec.get("certificate") or {}
    alpha_i_raw = risk.get("alpha_i")
    threshold = None
    decision = "unknown"
    if isinstance(alpha_i_raw, str):
        alpha_i = parse_decimal(alpha_i_raw)
        with localcontext() as ctx:
            ctx.prec = 50
            threshold = format_decimal(parse_decimal("1") / alpha_i)
        try:
            parsed = parse_evalue(cert.get("evalue"), "stat_cert evalue")
            decision = "accept" if encoded_evalue_to_decimal(parsed) * alpha_i >= 1 else "reject"
        except Exception:
            decision = "invalid"
    return {
        "round_before": round_before,
        "round_after": round_after,
        "alpha_i": alpha_i_raw,
        "threshold": threshold,
        "evalue": cert.get("evalue"),
        "decision": "accept" if accepted else decision,
    }


def _adopt(cfg: Config, concept: str, symbol: str, cert: dict) -> str:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    latest = idx.latest_adoption_for_concept(conn, concept)
    baseline_symbol = latest["chosen_symbol"] if latest else None
    record = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": concept,
            "chosen_symbol": symbol,
            "baseline_symbol": baseline_symbol,
            "certificate": cert,
            "constraints": {},
        },
    }
    result = commit_adoption(cfg, record)
    if not result.ok:
        raise ValueError(f"adoption failed: {result.rejection.code}")
    return result.payload_hash


def _retrieve_by_type(conn, task: SolveTask) -> list[str]:
    typ = _task_type(task)
    return idx.search_symbols_by_type(conn, type_norm(typ), 50)


def _task_type(task: SolveTask) -> Type:
    if task.family == "predicates":
        return FunType((INT,), BOOL)
    if task.family in {"arith", "lists", "folds", "reuse"}:
        if task.family == "arith":
            return FunType((INT,), INT)
        if task.family == "reuse":
            return FunType((INT,), INT)
        return FunType((ListType(INT),), INT)
    if task.family == "higher":
        return FunType((FunType((INT,), INT), INT), INT)
    raise ValueError(f"unknown family: {task.family}")


def _vars_for_family(family: str) -> list[dict]:
    if family in {"arith", "predicates", "reuse"}:
        return [{"name": "n", "type": {"tag": "int"}}]
    if family in {"lists", "folds"}:
        return [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}]
    if family == "higher":
        return [
            {"name": "f", "type": {"tag": "fun", "args": [{"tag": "int"}], "ret": {"tag": "int"}}},
            {"name": "n", "type": {"tag": "int"}},
        ]
    raise ValueError(f"unknown family: {family}")


def _assert_term(task: SolveTask, symbol: str) -> dict:
    if task.family == "higher":
        cand = _app_sym(symbol, [_var("f"), _var("n")])
        oracle = _app_sym(task.oracle_symbol, [_var("f"), _var("n")])
    else:
        var_name = "xs" if task.family in {"lists", "folds"} else "n"
        cand = _app_sym(symbol, [_var(var_name)])
        oracle = _app_sym(task.oracle_symbol, [_var(var_name)])
    if task.returns_bool:
        return _bool_eq(cand, oracle)
    return _prim("eq_int", cand, oracle)


def _oracle_def(task: SolveTask, name: str) -> dict:
    if task.family == "arith":
        return _int_add_def(name, task.k)
    if task.family == "predicates":
        return _pred_lt_def(name, task.k)
    if task.family == "lists":
        return _len_plus_k_def(name, task.k)
    if task.family == "folds":
        return _sum_plus_k_def(name, task.k)
    if task.family == "higher":
        return _apply_add_k_def(name, task.k)
    if task.family == "reuse":
        lib = _reuse_lib_name(task.k)
        return _compose_def(name, lib, lib)
    raise ValueError(f"unknown family: {task.family}")


def _baseline_def(task: SolveTask, name: str) -> dict:
    if task.returns_bool:
        body = _bool_lit(False)
        ret_type = {"tag": "bool"}
    else:
        body = _int_lit(0)
        ret_type = {"tag": "int"}
    params = _vars_for_family(task.family)
    return _definition(name, params, ret_type, body)


def _overfit_def(task: SolveTask, domain: Domain, name: str) -> dict:
    if task.family == "arith":
        return _int_add_bounded_def(name, task.k, domain)
    if task.family == "predicates":
        return _pred_lt_bounded_def(name, task.k, domain)
    if task.family == "lists":
        return _len_plus_k_bounded_def(name, task.k, domain.list_max_len)
    if task.family == "folds":
        return _sum_plus_k_bounded_def(name, task.k, domain.list_max_len)
    if task.family == "higher":
        return _apply_add_k_bounded_def(name, task.k, domain)
    if task.family == "reuse":
        return _int_add_bounded_def(name, task.k, domain)
    raise ValueError(f"unknown family: {task.family}")


def _definition(
    name: str,
    params: list[dict],
    ret_type: dict,
    body: dict,
    decreases_param: str | None = None,
) -> dict:
    return {
        "name": name,
        "params": params,
        "ret_type": ret_type,
        "body": body,
        "termination": {"kind": "structural", "decreases_param": decreases_param},
    }


def _int_identity_def(name: str) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "int"},
        _var("n"),
    )


def _int_add_def(name: str, k: int) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "int"},
        _prim("add", _var("n"), _int_lit(k)),
    )


def _int_mul_def(name: str, k: int) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "int"},
        _prim("mul", _var("n"), _int_lit(k)),
    )


def _int_add_bounded_def(name: str, k: int, domain: Domain) -> dict:
    cond = _outside_int(_var("n"), domain.int_min, domain.int_max)
    body = _if(cond, _int_lit(0), _prim("add", _var("n"), _int_lit(k)))
    return _definition(name, [{"name": "n", "type": {"tag": "int"}}], {"tag": "int"}, body)


def _pred_lt_def(name: str, k: int) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "bool"},
        _prim("lt_int", _var("n"), _int_lit(k)),
    )


def _pred_eq_def(name: str, k: int) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "bool"},
        _prim("eq_int", _var("n"), _int_lit(k)),
    )


def _pred_lt_bounded_def(name: str, k: int, domain: Domain) -> dict:
    cond = _outside_int(_var("n"), domain.int_min, domain.int_max)
    body = _if(cond, _bool_lit(False), _prim("lt_int", _var("n"), _int_lit(k)))
    return _definition(name, [{"name": "n", "type": {"tag": "int"}}], {"tag": "bool"}, body)


def _compose_def(name: str, first: str, second: str) -> dict:
    params = [{"name": "n", "type": {"tag": "int"}}]
    body = _app_sym(second, [_app_sym(first, [_var("n")])])
    return _definition(name, params, {"tag": "int"}, body)


def _reuse_lib_name(k: int) -> str:
    return f"lib_add_k_{k}"


def _apply_add_k_def(name: str, k: int) -> dict:
    params = [
        {"name": "f", "type": {"tag": "fun", "args": [{"tag": "int"}], "ret": {"tag": "int"}}},
        {"name": "n", "type": {"tag": "int"}},
    ]
    body = _prim("add", _app(_var("f"), [_var("n")]), _int_lit(k))
    return _definition(name, params, {"tag": "int"}, body)


def _apply_add_k_bounded_def(name: str, k: int, domain: Domain) -> dict:
    params = [
        {"name": "f", "type": {"tag": "fun", "args": [{"tag": "int"}], "ret": {"tag": "int"}}},
        {"name": "n", "type": {"tag": "int"}},
    ]
    cond = _outside_int(_var("n"), domain.int_min, domain.int_max)
    body = _if(cond, _int_lit(0), _prim("add", _app(_var("f"), [_var("n")]), _int_lit(k)))
    return _definition(name, params, {"tag": "int"}, body)


def _len_plus_k_def(name: str, k: int) -> dict:
    xs = _var("xs")
    body = _match_list(xs, _int_lit(k), "h", "t", _prim("add", _int_lit(1), _app_sym(name, [_var("t")])))
    return _definition(
        name,
        [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        {"tag": "int"},
        body,
        decreases_param="xs",
    )


def _len_plus_k_bounded_def(name: str, k: int, max_len: int) -> dict:
    xs = _var("xs")
    body = _bounded_len_case(xs, k, max_len, depth=0)
    return _definition(
        name,
        [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        {"tag": "int"},
        body,
        decreases_param="xs",
    )


def _sum_plus_k_def(name: str, k: int) -> dict:
    xs = _var("xs")
    body = _match_list(xs, _int_lit(k), "h", "t", _prim("add", _var("h"), _app_sym(name, [_var("t")])))
    return _definition(
        name,
        [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        {"tag": "int"},
        body,
        decreases_param="xs",
    )


def _sum_plus_k_bounded_def(name: str, k: int, max_len: int) -> dict:
    xs = _var("xs")
    body = _bounded_sum_case(xs, _int_lit(0), k, max_len, depth=0)
    return _definition(
        name,
        [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        {"tag": "int"},
        body,
        decreases_param="xs",
    )


def _bounded_len_case(list_term: dict, k: int, max_len: int, depth: int) -> dict:
    head = f"h{depth}"
    tail = f"t{depth}"
    if depth >= max_len:
        return _match_list(list_term, _int_lit(k + depth), head, tail, _int_lit(0))
    next_term = _bounded_len_case(_var(tail), k, max_len, depth + 1)
    return _match_list(list_term, _int_lit(k + depth), head, tail, next_term)


def _bounded_sum_case(list_term: dict, acc: dict, k: int, max_len: int, depth: int) -> dict:
    head = f"h{depth}"
    tail = f"t{depth}"
    if depth >= max_len:
        return _match_list(list_term, _prim("add", acc, _int_lit(k)), head, tail, _int_lit(0))
    next_acc = _prim("add", acc, _var(head))
    next_term = _bounded_sum_case(_var(tail), next_acc, k, max_len, depth + 1)
    return _match_list(list_term, _prim("add", acc, _int_lit(k)), head, tail, next_term)


def _outside_int(term: dict, int_min: int, int_max: int) -> dict:
    return _prim(
        "or",
        _prim("lt_int", term, _int_lit(int_min)),
        _prim("lt_int", _int_lit(int_max), term),
    )


def _var(name: str) -> dict:
    return {"tag": "var", "name": name}


def _int_lit(value: int) -> dict:
    return {"tag": "int", "value": int(value)}


def _bool_lit(value: bool) -> dict:
    return {"tag": "bool", "value": bool(value)}


def _prim(op: str, *args: dict) -> dict:
    return {"tag": "prim", "op": op, "args": list(args)}


def _if(cond: dict, then: dict, els: dict) -> dict:
    return {"tag": "if", "cond": cond, "then": then, "else": els}


def _app(fn: dict, args: list[dict]) -> dict:
    return {"tag": "app", "fn": fn, "args": args}


def _app_sym(name: str, args: list[dict]) -> dict:
    return _app({"tag": "sym", "name": name}, args)


def _match_list(scrutinee: dict, nil_case: dict, head_var: str, tail_var: str, body: dict) -> dict:
    return {
        "tag": "match_list",
        "scrutinee": scrutinee,
        "nil_case": nil_case,
        "cons_case": {"head_var": head_var, "tail_var": tail_var, "body": body},
    }


def _bool_eq(a: dict, b: dict) -> dict:
    return _prim("or", _prim("and", a, b), _prim("and", _prim("not", a), _prim("not", b)))
