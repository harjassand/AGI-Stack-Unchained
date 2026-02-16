"""Evidence suite runner for concept families and OOD evaluation."""

from __future__ import annotations

import json
import random
import subprocess
from dataclasses import dataclass
from decimal import localcontext
from pathlib import Path

from blake3 import blake3

from cdel.adoption.storage import init_storage as init_adoption_storage, read_head as read_adoption_head
from cdel.adoption.verifier import commit_adoption
from cdel.bench.taxonomy import FAMILY_SPECS, families
from cdel.config import Config, write_config
from cdel.kernel.deps import collect_sym_refs_in_defs, collect_sym_refs_in_specs
from cdel.kernel.eval import Evaluator, FunVal, IntVal, ListVal
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.storage import init_storage, read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.evalue import encoded_evalue_to_decimal, format_decimal, parse_decimal, parse_evalue
from cdel.sealed.worker import issue_stat_cert


@dataclass(frozen=True)
class Domain:
    int_min: int
    int_max: int
    list_max_len: int


@dataclass(frozen=True)
class EvidenceConfig:
    tasks_per_family: int
    episodes: int
    eval_episodes: int
    seed_key: str
    budget: int


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


def run_evidence_suite(out_dir: Path, cfg: EvidenceConfig) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "meta": {},
        "config": {
            "tasks_per_family": cfg.tasks_per_family,
            "episodes": cfg.episodes,
            "eval_episodes": cfg.eval_episodes,
            "seed_key": cfg.seed_key,
            "budget": cfg.budget,
        },
        "families": {},
        "regimes": {},
    }
    meta_set = False

    for regime in ("bounded_only", "stat_cert"):
        root = out_dir / regime
        root.mkdir(parents=True, exist_ok=True)
        exp_cfg = _init_regime(root, cfg)
        if not meta_set:
            results["meta"] = _meta_info(exp_cfg)
            meta_set = True
        _commit_helper_symbols(exp_cfg)
        family_records = {}
        tasks = []

        for family in families():
            spec = FAMILY_SPECS[family]
            count = min(cfg.tasks_per_family, int(spec["count"]))
            family_records[family] = {
                "tasks": count,
                "accepted": 0,
                "rejected": 0,
                "avg_sealed_score": 0.0,
                "alpha_round_start": None,
                "alpha_round_end": None,
                "alpha_spent": None,
                "invariants_ok": True,
            }
            if regime == "stat_cert":
                family_records[family]["alpha_round_start"] = _stat_round(exp_cfg)
            sealed_scores = []
            for idx_k in range(count):
                concept = f"{spec['prefix']}.{idx_k}"
                task = _task_for_family(family, concept, idx_k)
                base = _base_module(task)
                base["parent"] = read_head(exp_cfg)
                base_result = commit_module(exp_cfg, base)
                hashes_before = _def_hashes(exp_cfg)
                invariants_ok = True
                if base_result.ok:
                    invariants_ok = _hashes_unchanged(exp_cfg, hashes_before)
                tasks.append(_task_row(regime, family, concept, "base", base_result, None, None, None, invariants_ok))

                if regime == "bounded_only":
                    candidate_module = _candidate_module(
                        task,
                        kind="overfit",
                        specs=[_bounded_spec(task, task.overfit_symbol)],
                    )
                    candidate_module["parent"] = read_head(exp_cfg)
                    result = commit_module(exp_cfg, candidate_module)
                    sealed_score = _accuracy_on_domain(
                        task,
                        task.overfit_symbol,
                        task.oracle_symbol,
                        FAMILY_DOMAINS[family]["sealed"],
                        cfg.eval_episodes,
                        cfg.seed_key,
                    )
                    invariants_ok = _hashes_unchanged(exp_cfg, hashes_before) if result.ok else invariants_ok
                    tasks.append(_task_row(regime, family, concept, "overfit", result, sealed_score, None, None, invariants_ok))
                    if result.ok:
                        family_records[family]["accepted"] += 1
                    else:
                        family_records[family]["rejected"] += 1
                    sealed_scores.append(sealed_score)
                    continue

                # stat_cert regime: overfit attempt
                overfit_spec, round_before = _stat_cert_for(
                    exp_cfg, task, task.overfit_symbol, cfg.episodes, cfg.seed_key
                )
                candidate_module = _candidate_module(
                    task,
                    kind="overfit",
                    specs=[_bounded_spec(task, task.overfit_symbol), overfit_spec],
                )
                candidate_module["parent"] = read_head(exp_cfg)
                result = commit_module(exp_cfg, candidate_module)
                round_after = _stat_round(exp_cfg)
                alpha_row = _alpha_row(overfit_spec, round_before, round_after, result.ok)
                sealed_score = _accuracy_on_domain(
                    task,
                    task.overfit_symbol,
                    task.oracle_symbol,
                    FAMILY_DOMAINS[family]["sealed"],
                    cfg.eval_episodes,
                    cfg.seed_key,
                )
                invariants_ok = _hashes_unchanged(exp_cfg, hashes_before) if result.ok else invariants_ok
                tasks.append(
                    _task_row(regime, family, concept, "overfit", result, sealed_score, alpha_row, round_before, invariants_ok)
                )
                if not result.ok:
                    family_records[family]["rejected"] += 1

                # correct attempt
                correct_spec, round_before = _stat_cert_for(
                    exp_cfg, task, task.correct_symbol, cfg.episodes, cfg.seed_key
                )
                candidate_module = _candidate_module(
                    task,
                    kind="correct",
                    specs=[_bounded_spec(task, task.correct_symbol), correct_spec],
                )
                candidate_module["parent"] = read_head(exp_cfg)
                result = commit_module(exp_cfg, candidate_module)
                if result.ok:
                    _adopt_symbol(exp_cfg, task.concept, task.correct_symbol, None, correct_spec)
                round_after = _stat_round(exp_cfg)
                alpha_row = _alpha_row(correct_spec, round_before, round_after, result.ok)
                sealed_score = _accuracy_on_domain(
                    task,
                    task.correct_symbol,
                    task.oracle_symbol,
                    FAMILY_DOMAINS[family]["sealed"],
                    cfg.eval_episodes,
                    cfg.seed_key,
                )
                invariants_ok = _hashes_unchanged(exp_cfg, hashes_before) if result.ok else invariants_ok
                tasks.append(
                    _task_row(regime, family, concept, "correct", result, sealed_score, alpha_row, round_before, invariants_ok)
                )
                if result.ok:
                    family_records[family]["accepted"] += 1
                else:
                    family_records[family]["rejected"] += 1
                sealed_scores.append(sealed_score)

            if sealed_scores:
                family_records[family]["avg_sealed_score"] = sum(sealed_scores) / len(sealed_scores)
            if regime == "stat_cert":
                state = idx.get_stat_cert_state(idx.connect(str(exp_cfg.sqlite_path)))
                if state is not None:
                    family_records[family]["alpha_round_end"] = state[0]
                    family_records[family]["alpha_spent"] = state[1]

        results["regimes"][regime] = {"tasks": tasks, "families": family_records}

    results["checks"] = _evaluate_checks(results)
    results["summary"] = _summarize_regimes(results)
    _write_outputs(out_dir, results)
    return results


@dataclass(frozen=True)
class TaskInfo:
    family: str
    concept: str
    prefix: str
    baseline_symbol: str
    overfit_symbol: str
    correct_symbol: str
    oracle_symbol: str
    returns_bool: bool
    fun_symbols: list[str]


def _task_for_family(family: str, concept: str, idx_k: int) -> TaskInfo:
    prefix = concept.replace(".", "_")
    return TaskInfo(
        family=family,
        concept=concept,
        prefix=prefix,
        baseline_symbol=f"{prefix}_base",
        overfit_symbol=f"{prefix}_overfit",
        correct_symbol=f"{prefix}_correct",
        oracle_symbol=f"{prefix}_oracle",
        returns_bool=(family == "predicates"),
        fun_symbols=["id_int", "inc_int", "double_int"] if family == "higher" else [],
    )


def _init_regime(root: Path, cfg: EvidenceConfig) -> Config:
    priv, pub = generate_keypair()
    key_id = key_id_from_public_key(pub)
    data = {
        "ledger": {"budget": cfg.budget},
        "runs": {"base_dir": "runs"},
        "evaluator": {"step_limit": 100_000},
        "spec": {
            "int_min": -10,
            "int_max": 10,
            "list_max_len": 6,
        },
        "cost": {"alpha": 1, "beta": 1, "gamma": 1},
        "sealed": {
            "public_key": pub,
            "key_id": key_id,
            "public_keys": [],
            "prev_public_keys": [],
            "alpha_total": "1e-4",
            "alpha_schedule": {
                "name": "p_series",
                "exponent": 2,
                "coefficient": "0.60792710185402662866",
            },
            "eval_harness_id": "toy-harness-v1",
            "eval_harness_hash": "harness-hash",
            "eval_suite_hash": "suite-hash",
        },
    }
    write_config(root, data)
    exp_cfg = Config(root=root, data=data)
    init_storage(exp_cfg)
    init_adoption_storage(exp_cfg)
    conn = idx.connect(str(exp_cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, cfg.budget)
    conn.commit()
    exp_cfg.data["sealed"]["private_key"] = priv
    return exp_cfg


def _commit_helper_symbols(cfg: Config) -> None:
    reuse_count = int((FAMILY_SPECS.get("reuse") or {}).get("count", 0))
    reuse_symbols = [_reuse_lib_name(idx_k) for idx_k in range(reuse_count)]
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["id_int", "inc_int", "double_int"] + reuse_symbols,
            "definitions": [
                _int_identity_def("id_int"),
                _int_add_def("inc_int", 1),
                _int_mul_def("double_int", 2),
            ]
            + [_int_add_def(name, idx_k) for idx_k, name in enumerate(reuse_symbols)],
            "declared_deps": [],
            "specs": [],
            "concepts": [{"concept": f"lib.add_k.{idx_k}", "symbol": name} for idx_k, name in enumerate(reuse_symbols)],
        },
    }
    result = commit_module(cfg, module)
    if not result.ok:
        raise ValueError("helper symbol commit failed")


def _base_module(task: TaskInfo) -> dict:
    bounded = FAMILY_DOMAINS[task.family]["bounded"]
    defs = [_oracle_def(task, task.oracle_symbol), _baseline_def(task, bounded, task.baseline_symbol)]
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": [task.oracle_symbol, task.baseline_symbol],
            "definitions": defs,
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }


def _candidate_module(task: TaskInfo, *, kind: str, specs: list[dict]) -> dict:
    if kind == "overfit":
        defn = _overfit_def(task, FAMILY_DOMAINS[task.family]["bounded"], task.overfit_symbol)
        symbol = task.overfit_symbol
    else:
        defn = _oracle_def(task, task.correct_symbol)
        symbol = task.correct_symbol
    actual_refs = collect_sym_refs_in_defs([defn]) | collect_sym_refs_in_specs(specs)
    actual_deps = sorted({ref for ref in actual_refs if ref not in {symbol}})
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": [symbol],
            "definitions": [defn],
            "declared_deps": actual_deps,
            "specs": specs,
            "concepts": [{"concept": task.concept, "symbol": symbol}],
        },
    }


def _bounded_spec(task: TaskInfo, symbol: str) -> dict:
    bounded = FAMILY_DOMAINS[task.family]["bounded"]
    vars_list = _vars_for_family(task.family)
    assert_term = _assert_term(task, symbol)
    return {
        "kind": "forall",
        "vars": vars_list,
        "domain": {
            "int_min": bounded.int_min,
            "int_max": bounded.int_max,
            "list_max_len": bounded.list_max_len,
            "fun_symbols": task.fun_symbols,
        },
        "assert": assert_term,
    }


def _stat_cert_for(
    cfg: Config,
    task: TaskInfo,
    candidate_symbol: str,
    episodes: int,
    seed_key: str,
) -> tuple[dict, int]:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    round_idx = 1 if state is None else state[0]
    sealed = cfg.data.get("sealed") or {}
    priv_key = sealed.get("private_key")
    if not isinstance(priv_key, str):
        raise ValueError("missing sealed private key")
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
    extra_defs = _extra_defs_for_candidate(task, candidate_symbol)
    spec = issue_stat_cert(cfg, request, priv_key, seed_key.encode("utf-8"), extra_defs=extra_defs)
    return spec, round_idx


def _adopt_symbol(cfg: Config, concept: str, symbol: str, baseline: str | None, cert: dict) -> None:
    record = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": concept,
            "chosen_symbol": symbol,
            "baseline_symbol": baseline,
            "certificate": cert,
            "constraints": {},
        },
    }
    result = commit_adoption(cfg, record)
    if not result.ok:
        raise ValueError(f"adoption failed: {result.rejection.code}")


def _accuracy_on_domain(
    task: TaskInfo,
    symbol: str,
    oracle: str,
    domain: Domain,
    episodes: int,
    seed_key: str,
) -> float:
    defs = _defs_for_eval(task, symbol, oracle)
    correct = 0
    for episode in range(episodes):
        evaluator = Evaluator(200_000)
        rng = random.Random(_episode_seed(seed_key, task.concept, symbol, episode))
        args = _random_args(task.family, rng, domain)
        try:
            oracle_val = evaluator._apply(FunVal(oracle), args, defs)
            value = evaluator._apply(FunVal(symbol), args, defs)
        except Exception:
            continue
        if value == oracle_val:
            correct += 1
    return correct / episodes if episodes else 0.0


def _defs_for_eval(task: TaskInfo, symbol: str, oracle: str) -> dict:
    bounded = FAMILY_DOMAINS[task.family]["bounded"]
    defs = {
        task.oracle_symbol: parse_definition(_oracle_def(task, task.oracle_symbol)),
        task.baseline_symbol: parse_definition(_baseline_def(task, bounded, task.baseline_symbol)),
    }
    if symbol == task.overfit_symbol:
        defs[symbol] = parse_definition(_overfit_def(task, bounded, symbol))
    elif symbol == task.correct_symbol:
        defs[symbol] = parse_definition(_oracle_def(task, symbol))
    else:
        defs[symbol] = parse_definition(_oracle_def(task, symbol))
    for helper in ("id_int", "inc_int", "double_int"):
        defs[helper] = parse_definition(_helper_defs()[helper])
    return defs


def _extra_defs_for_candidate(task: TaskInfo, symbol: str) -> dict:
    defs = {
        task.oracle_symbol: parse_definition(_oracle_def(task, task.oracle_symbol)),
        task.baseline_symbol: parse_definition(
            _baseline_def(task, FAMILY_DOMAINS[task.family]["bounded"], task.baseline_symbol)
        ),
    }
    if symbol == task.overfit_symbol:
        defs[symbol] = parse_definition(_overfit_def(task, FAMILY_DOMAINS[task.family]["bounded"], symbol))
    else:
        defs[symbol] = parse_definition(_oracle_def(task, symbol))
    for helper in ("id_int", "inc_int", "double_int"):
        defs[helper] = parse_definition(_helper_defs()[helper])
    return defs


def _task_row(
    regime: str,
    family: str,
    concept: str,
    variant: str,
    result,
    sealed_score: float | None,
    alpha: dict | None,
    round_before: int | None,
    invariants_ok: bool,
) -> dict:
    return {
        "regime": regime,
        "family": family,
        "concept": concept,
        "variant": variant,
        "accepted": result.ok,
        "rejection": result.rejection.code.value if result.rejection else None,
        "sealed_score": sealed_score,
        "alpha": alpha,
        "round_before": round_before,
        "invariants_ok": invariants_ok,
    }


def _evaluate_checks(results: dict) -> dict[str, bool]:
    regimes = results.get("regimes") or {}
    bounded = regimes.get("bounded_only") or {}
    stat = regimes.get("stat_cert") or {}
    bounded_tasks = bounded.get("tasks") or []
    stat_tasks = stat.get("tasks") or []

    checks = {
        "non_interference_ok": all(task.get("invariants_ok") for task in bounded_tasks + stat_tasks),
    }
    overfit_accepts = [t for t in bounded_tasks if t.get("variant") == "overfit" and t.get("accepted")]
    stat_overfit_rejects = [t for t in stat_tasks if t.get("variant") == "overfit" and not t.get("accepted")]
    stat_correct_accepts = [t for t in stat_tasks if t.get("variant") == "correct" and t.get("accepted")]
    checks["bounded_overfit_accepts"] = len(overfit_accepts) > 0
    checks["stat_overfit_rejects"] = len(stat_overfit_rejects) > 0
    checks["stat_correct_accepts"] = len(stat_correct_accepts) > 0
    return checks


def _summarize_regimes(results: dict) -> dict:
    regimes = results.get("regimes") or {}
    out: dict[str, dict] = {}
    for regime, payload in regimes.items():
        tasks = payload.get("tasks") or []
        out[regime] = _summarize_regime(tasks)
    return out


def _summarize_regime(tasks: list[dict]) -> dict:
    summary = {"overall": _summarize_tasks([t for t in tasks if t.get("variant") != "base"]), "variants": {}}
    variants = sorted({t.get("variant") for t in tasks if t.get("variant")})
    for variant in variants:
        subset = [t for t in tasks if t.get("variant") == variant]
        summary["variants"][variant] = _summarize_tasks(subset)

    alpha_rows = [t for t in tasks if t.get("alpha")]
    if alpha_rows:
        rounds_before = [t.get("round_before") for t in alpha_rows if t.get("round_before") is not None]
        rounds_after = [t["alpha"].get("round_after") for t in alpha_rows if t.get("alpha")]
        summary["alpha_audit"] = {
            "attempts": len(alpha_rows),
            "accepts": sum(1 for t in alpha_rows if t.get("accepted")),
            "round_start": min(rounds_before) if rounds_before else None,
            "round_end": max(r for r in rounds_after if r is not None) if rounds_after else None,
        }
    return summary


def _summarize_tasks(tasks: list[dict]) -> dict:
    attempts = len(tasks)
    accepted = sum(1 for t in tasks if t.get("accepted"))
    sealed_scores = [t.get("sealed_score") for t in tasks if t.get("sealed_score") is not None]
    avg_sealed_score = sum(sealed_scores) / len(sealed_scores) if sealed_scores else None
    return {
        "attempts": attempts,
        "accepted": accepted,
        "rejected": attempts - accepted,
        "accept_rate": (accepted / attempts) if attempts else 0.0,
        "avg_sealed_score": avg_sealed_score,
    }


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "results.json"
    summary_path = out_dir / "summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")

    lines = ["# Evidence Suite Summary", ""]
    checks = results.get("checks") or {}
    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    summary = results.get("summary") or {}
    if summary:
        lines.append("## Summary")
        for regime, info in summary.items():
            overall = info.get("overall") or {}
            lines.append(
                f"- {regime}: attempts={overall.get('attempts')} accepted={overall.get('accepted')} "
                f"accept_rate={overall.get('accept_rate')} avg_sealed_score={overall.get('avg_sealed_score')}"
            )
        lines.append("")
    for regime, payload in (results.get("regimes") or {}).items():
        lines.append(f"## {regime}")
        families_payload = payload.get("families") or {}
        for family, info in families_payload.items():
            lines.append(
                f"- {family}: tasks={info.get('tasks')} accepted={info.get('accepted')} "
                f"rejected={info.get('rejected')} avg_sealed_score={info.get('avg_sealed_score')}"
            )
        lines.append("")
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _meta_info(cfg: Config) -> dict:
    sealed = cfg.data.get("sealed") or {}
    return {
        "git_commit": _git_commit(_repo_root()),
        "config_hash": _config_hash(cfg.data),
        "eval_harness_id": sealed.get("eval_harness_id"),
        "eval_harness_hash": sealed.get("eval_harness_hash"),
        "eval_suite_hash": sealed.get("eval_suite_hash"),
        "alpha_total": sealed.get("alpha_total"),
        "alpha_schedule": sealed.get("alpha_schedule"),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _config_hash(data: dict) -> str:
    payload = json.loads(json.dumps(data))
    sealed = payload.get("sealed")
    if isinstance(sealed, dict):
        sealed.pop("private_key", None)
    return blake3(canon_bytes(payload)).hexdigest()


def _stat_round(cfg: Config) -> int:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    return 1 if state is None else int(state[0])


def _alpha_row(spec: dict, round_before: int, round_after: int, accepted: bool) -> dict:
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


def _def_hashes(cfg: Config) -> dict[str, str]:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    cur = conn.execute("SELECT symbol, def_hash FROM def_hashes")
    return {row[0]: row[1] for row in cur.fetchall()}


def _hashes_unchanged(cfg: Config, before: dict[str, str]) -> bool:
    after = _def_hashes(cfg)
    for symbol, def_hash in before.items():
        if after.get(symbol) != def_hash:
            return False
    return True


def _episode_seed(seed_key: str, concept: str, symbol: str, episode: int) -> int:
    data = f"{seed_key}:{concept}:{symbol}:{episode}".encode("utf-8")
    return int.from_bytes(blake3(data).digest()[:8], "big", signed=False)


def _random_args(family: str, rng: random.Random, domain: Domain) -> list:
    if family in {"arith", "predicates", "reuse"}:
        return [IntVal(rng.randint(domain.int_min, domain.int_max))]
    if family in {"lists", "folds"}:
        length = rng.randint(0, max(0, domain.list_max_len))
        items = tuple(IntVal(rng.randint(domain.int_min, domain.int_max)) for _ in range(length))
        return [ListVal(items)]
    if family == "higher":
        fun = rng.choice(["id_int", "inc_int", "double_int"])
        return [FunVal(fun), IntVal(rng.randint(domain.int_min, domain.int_max))]
    raise ValueError(f"unknown family: {family}")


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


def _assert_term(task: TaskInfo, symbol: str) -> dict:
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


def _oracle_def(task: TaskInfo, name: str) -> dict:
    if task.family == "arith":
        return _int_add_def(name, _task_k(task))
    if task.family == "predicates":
        return _pred_lt_def(name, _task_k(task))
    if task.family == "lists":
        return _len_plus_k_def(name, _task_k(task))
    if task.family == "folds":
        return _sum_plus_k_def(name, _task_k(task))
    if task.family == "higher":
        return _apply_add_k_def(name, _task_k(task))
    if task.family == "reuse":
        lib = _reuse_lib_name(_task_k(task))
        return _compose_def(name, lib, lib)
    raise ValueError(f"unknown family: {task.family}")


def _baseline_def(task: TaskInfo, domain: Domain, name: str) -> dict:
    if task.family == "arith":
        return _int_add_bounded_def(name, _task_k(task), domain)
    if task.family == "predicates":
        return _pred_lt_bounded_def(name, _task_k(task), domain)
    if task.family == "lists":
        return _len_plus_k_bounded_def(name, _task_k(task), domain.list_max_len)
    if task.family == "folds":
        return _sum_plus_k_bounded_def(name, _task_k(task), domain.list_max_len)
    if task.family == "higher":
        return _apply_add_k_bounded_def(name, _task_k(task), domain)
    if task.family == "reuse":
        return _int_add_bounded_def(name, _task_k(task), domain)
    raise ValueError(f"unknown family: {task.family}")


def _overfit_def(task: TaskInfo, domain: Domain, name: str) -> dict:
    return _baseline_def(task, domain, name)


def _task_k(task: TaskInfo) -> int:
    return int(task.concept.split(".")[-1])


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
    return _definition(name, [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}], {"tag": "int"}, body)


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
    return _definition(name, [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}], {"tag": "int"}, body)


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


def _helper_defs() -> dict[str, dict]:
    return {
        "id_int": _int_identity_def("id_int"),
        "inc_int": _int_add_def("inc_int", 1),
        "double_int": _int_mul_def("double_int", 2),
    }


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
