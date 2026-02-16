"""Overfit vs stat_cert generalization experiment runner."""

from __future__ import annotations

import json
import subprocess
from decimal import localcontext
from dataclasses import dataclass
from pathlib import Path

from cdel.adoption.storage import init_storage as init_adoption_storage, read_head as read_adoption_head
from cdel.adoption.verifier import commit_adoption
from cdel.config import Config, write_config
from cdel.kernel.eval import Evaluator, FunVal, IntVal
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.storage import init_storage, read_head
from cdel.ledger.verifier import commit_module
from blake3 import blake3

from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.evalue import format_decimal, parse_decimal
from cdel.sealed.worker import issue_stat_cert


@dataclass(frozen=True)
class ExperimentConfig:
    episodes: int
    eval_int_min: int
    eval_int_max: int
    bounded_int_min: int
    bounded_int_max: int
    seed_key: str
    budget: int


def run_generalization_experiment(out_dir: Path, cfg: ExperimentConfig) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "meta": {},
        "config": {
            "episodes": cfg.episodes,
            "eval_int_min": cfg.eval_int_min,
            "eval_int_max": cfg.eval_int_max,
            "bounded_int_min": cfg.bounded_int_min,
            "bounded_int_max": cfg.bounded_int_max,
            "seed_key": cfg.seed_key,
            "budget": cfg.budget,
        },
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
        steps = []

        base_defs = _base_module(cfg.bounded_int_min, cfg.bounded_int_max)
        base_result = commit_module(exp_cfg, base_defs)
        steps.append(_step_result("base", base_result, None, None, None, None, True))

        conn = idx.connect(str(exp_cfg.sqlite_path))
        idx.init_schema(conn)
        base_hashes = _def_hashes(conn, ["is_even_base", "is_even_oracle"])

        if regime == "bounded_only":
            overfit_module = _candidate_module(
                "is_even_overfit",
                include_stat_cert=False,
                bounded_int_min=cfg.bounded_int_min,
                bounded_int_max=cfg.bounded_int_max,
            )
            overfit_module["parent"] = read_head(exp_cfg)
            overfit_result = commit_module(exp_cfg, overfit_module)
            chosen_symbol = _latest_candidate(conn, "is_even") if overfit_result.ok else None
            bounded_score, sealed_score = _scores_for_symbol(
                exp_cfg,
                "is_even_overfit",
                cfg.bounded_int_min,
                cfg.bounded_int_max,
                cfg.eval_int_min,
                cfg.eval_int_max,
                defs_override=_defs_for_candidate("is_even_overfit", cfg.bounded_int_min, cfg.bounded_int_max),
            )
            invariant_ok = _hashes_unchanged(conn, base_hashes)
            steps.append(
                _step_result(
                    "overfit",
                    overfit_result,
                    chosen_symbol,
                    bounded_score,
                    sealed_score,
                    None,
                    invariant_ok,
                )
            )
        else:
            overfit_spec, overfit_round = _stat_cert_for(
                exp_cfg,
                "is_even_base",
                "is_even_overfit",
                "is_even_oracle",
                cfg.episodes,
                cfg.seed_key,
                cfg.bounded_int_min,
                cfg.bounded_int_max,
            )
            overfit_module = _candidate_module(
                "is_even_overfit",
                include_stat_cert=True,
                bounded_int_min=cfg.bounded_int_min,
                bounded_int_max=cfg.bounded_int_max,
                stat_cert=overfit_spec,
            )
            overfit_module["parent"] = read_head(exp_cfg)
            overfit_result = commit_module(exp_cfg, overfit_module)
            overfit_chosen = _adopted_symbol(conn, "is_even")
            overfit_scores = _scores_for_symbol(
                exp_cfg,
                "is_even_overfit",
                cfg.bounded_int_min,
                cfg.bounded_int_max,
                cfg.eval_int_min,
                cfg.eval_int_max,
                defs_override=_defs_for_candidate("is_even_overfit", cfg.bounded_int_min, cfg.bounded_int_max),
            )
            invariant_ok = _hashes_unchanged(conn, base_hashes)
            overfit_round_after = _stat_round(exp_cfg, overfit_round)
            steps.append(
                _step_result(
                    "overfit",
                    overfit_result,
                    overfit_chosen,
                    overfit_scores[0],
                    overfit_scores[1],
                    _alpha_row(overfit_spec, overfit_round, overfit_round_after, overfit_result.ok),
                    invariant_ok,
                )
            )

            correct_spec, correct_round = _stat_cert_for(
                exp_cfg,
                "is_even_base",
                "is_even_correct",
                "is_even_oracle",
                cfg.episodes,
                cfg.seed_key,
                cfg.bounded_int_min,
                cfg.bounded_int_max,
            )
            correct_module = _candidate_module(
                "is_even_correct",
                include_stat_cert=True,
                bounded_int_min=cfg.bounded_int_min,
                bounded_int_max=cfg.bounded_int_max,
                stat_cert=correct_spec,
            )
            correct_module["parent"] = read_head(exp_cfg)
            correct_result = commit_module(exp_cfg, correct_module)
            if correct_result.ok:
                _adopt_symbol(exp_cfg, "is_even", "is_even_correct", None, correct_spec)
            adopted = _adopted_symbol(conn, "is_even")
            correct_scores = _scores_for_symbol(
                exp_cfg,
                adopted or "is_even_correct",
                cfg.bounded_int_min,
                cfg.bounded_int_max,
                cfg.eval_int_min,
                cfg.eval_int_max,
                defs_override=_defs_for_candidate(adopted or "is_even_correct", cfg.bounded_int_min, cfg.bounded_int_max),
            )
            invariant_ok = _hashes_unchanged(conn, base_hashes)
            correct_round_after = _stat_round(exp_cfg, correct_round)
            steps.append(
                _step_result(
                    "correct",
                    correct_result,
                    adopted,
                    correct_scores[0],
                    correct_scores[1],
                    _alpha_row(correct_spec, correct_round, correct_round_after, correct_result.ok),
                    invariant_ok,
                )
            )

        results["regimes"][regime] = {
            "steps": steps,
            "chosen_symbol": steps[-1]["chosen_symbol"] if steps else None,
        }

    results["checks"] = _evaluate_checks(results)
    _write_outputs(out_dir, results)
    return results


def _init_regime(root: Path, cfg: ExperimentConfig) -> Config:
    priv, pub = generate_keypair()
    key_id = key_id_from_public_key(pub)
    data = {
        "ledger": {"budget": cfg.budget},
        "runs": {"base_dir": "runs"},
        "evaluator": {"step_limit": 100_000},
        "spec": {
            "int_min": cfg.eval_int_min,
            "int_max": cfg.eval_int_max,
            "list_max_len": 0,
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


def _base_module(int_min: int, int_max: int) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["is_even_base", "is_even_oracle"],
            "definitions": [
                _is_even_base_def("is_even_base", int_min, int_max),
                _is_even_def("is_even_oracle"),
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }


def _candidate_module(
    symbol: str,
    *,
    include_stat_cert: bool,
    bounded_int_min: int,
    bounded_int_max: int,
    stat_cert: dict | None = None,
) -> dict:
    specs = [_bounded_spec(symbol, bounded_int_min, bounded_int_max)]
    if include_stat_cert:
        if stat_cert is None:
            raise ValueError("stat_cert required when include_stat_cert is True")
        specs.append(stat_cert)
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": [symbol],
            "definitions": [
                _overfit_def(symbol, bounded_int_min, bounded_int_max)
                if symbol == "is_even_overfit"
                else _is_even_def(symbol)
            ],
            "declared_deps": _candidate_deps(include_stat_cert),
            "specs": specs,
            "concepts": [{"concept": "is_even", "symbol": symbol}],
        },
    }


def _stat_cert_for(
    cfg: Config,
    baseline: str,
    candidate: str,
    oracle: str,
    episodes: int,
    seed_key: str,
    bounded_int_min: int,
    bounded_int_max: int,
) -> tuple[dict, int]:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    round_idx = 1 if state is None else state[0]
    request = {
        "kind": "stat_cert",
        "concept": "is_even",
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": episodes,
            "max_steps": 50,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
        "risk": {"evalue_threshold": "1"},
    }
    sealed = cfg.data.get("sealed") or {}
    priv_key = sealed.get("private_key")
    if not isinstance(priv_key, str):
        raise ValueError("missing sealed private key in experiment config")
    extra_defs = _defs_for_candidate(candidate, bounded_int_min, bounded_int_max)
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


def _adopted_symbol(conn, concept: str) -> str | None:
    adoption = idx.latest_adoption_for_concept(conn, concept)
    return adoption.get("chosen_symbol") if adoption else None


def _latest_candidate(conn, concept: str) -> str | None:
    return idx.latest_symbol_for_concept(conn, concept)


def _scores_for_symbol(
    cfg: Config,
    symbol: str,
    bounded_int_min: int,
    bounded_int_max: int,
    eval_int_min: int,
    eval_int_max: int,
    defs_override: dict | None = None,
) -> tuple[float, float]:
    bounded = _accuracy_on_range(
        cfg,
        symbol,
        "is_even_oracle",
        bounded_int_min,
        bounded_int_max,
        defs_override=defs_override,
    )
    sealed = _accuracy_on_range(
        cfg,
        symbol,
        "is_even_oracle",
        eval_int_min,
        eval_int_max,
        defs_override=defs_override,
    )
    return bounded, sealed


def _accuracy_on_range(
    cfg: Config,
    symbol: str,
    oracle: str,
    int_min: int,
    int_max: int,
    defs_override: dict | None = None,
) -> float:
    if defs_override is None:
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        defs = _load_defs(cfg, conn, [symbol, oracle])
    else:
        defs = defs_override
    evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
    correct = 0
    total = 0
    for n in range(int_min, int_max + 1):
        total += 1
        try:
            oracle_val = evaluator._apply(FunVal(oracle), [IntVal(n)], defs)
            value = evaluator._apply(FunVal(symbol), [IntVal(n)], defs)
        except Exception:
            continue
        if value == oracle_val:
            correct += 1
    return correct / total if total else 0.0


def _load_defs(cfg: Config, conn, symbols: list[str]) -> dict:
    from cdel.ledger.closure import load_definitions

    return load_definitions(cfg, conn, symbols)


def _def_hashes(conn, symbols: list[str]) -> dict[str, str]:
    out = {}
    for symbol in symbols:
        cur = conn.execute("SELECT def_hash FROM def_hashes WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        if row:
            out[symbol] = row[0]
    return out


def _hashes_unchanged(conn, base_hashes: dict[str, str]) -> bool:
    current = _def_hashes(conn, list(base_hashes.keys()))
    return current == base_hashes


def _stat_round(cfg: Config, round_before: int) -> int:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    return round_before if state is None else int(state[0])


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


def _meta_info(cfg: Config) -> dict:
    sealed = cfg.data.get("sealed") or {}
    commit = _git_commit(_repo_root()) or "unknown"
    return {
        "git_commit": commit,
        "config_hash": _config_hash(cfg.data),
        "eval_harness_id": sealed.get("eval_harness_id"),
        "eval_harness_hash": sealed.get("eval_harness_hash"),
        "eval_suite_hash": sealed.get("eval_suite_hash"),
        "alpha_total": sealed.get("alpha_total"),
        "alpha_schedule": sealed.get("alpha_schedule"),
    }


def _format_evalue_for_summary(raw: object) -> str:
    if isinstance(raw, dict):
        mantissa = raw.get("mantissa")
        exponent = raw.get("exponent10")
        if isinstance(mantissa, str) and isinstance(exponent, int):
            return f"{mantissa}e{exponent}"
    return str(raw)


def _alpha_row(spec: dict, round_before: int, round_after: int, accepted: bool) -> dict:
    risk = spec.get("risk") or {}
    cert = spec.get("certificate") or {}
    alpha_i_raw = risk.get("alpha_i")
    threshold = None
    if isinstance(alpha_i_raw, str):
        alpha_i = parse_decimal(alpha_i_raw)
        with localcontext() as ctx:
            ctx.prec = 50
            threshold = format_decimal(parse_decimal("1") / alpha_i)
    decision = "accept" if accepted else "reject"
    return {
        "round_before": round_before,
        "round_after": round_after,
        "alpha_i": alpha_i_raw,
        "threshold": threshold,
        "evalue": cert.get("evalue"),
        "decision": decision,
    }


def _step_result(
    label: str,
    result,
    chosen_symbol: str | None,
    bounded_score: float | None,
    sealed_score: float | None,
    alpha: dict | None,
    invariant_ok: bool,
) -> dict:
    return {
        "label": label,
        "accepted": result.ok,
        "rejection": result.rejection.code.value if result.rejection else None,
        "chosen_symbol": chosen_symbol,
        "bounded_score": bounded_score,
        "sealed_score": sealed_score,
        "alpha": alpha,
        "invariants_ok": invariant_ok,
    }


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "results.json"
    summary_path = out_dir / "summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")

    lines = ["# Generalization Experiment Summary", ""]
    checks = results.get("checks") or {}
    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    for regime, payload in (results.get("regimes") or {}).items():
        steps = payload.get("steps") or []
        chosen = payload.get("chosen_symbol")
        lines.append(f"## {regime}")
        lines.append(f"- chosen_symbol: {chosen}")
        if steps:
            last = steps[-1]
            lines.append(f"- bounded_score: {last.get('bounded_score')}")
            lines.append(f"- sealed_score: {last.get('sealed_score')}")
            lines.append(f"- invariants_ok: {last.get('invariants_ok')}")
            alpha_steps = [step for step in steps if step.get("alpha")]
            if alpha_steps:
                lines.append("alpha_audit:")
                for step in alpha_steps:
                    alpha = step.get("alpha") or {}
                    lines.append(
                        f"{step.get('label')}: round_before={alpha.get('round_before')} "
                        f"round_after={alpha.get('round_after')} "
                        f"alpha_i={alpha.get('alpha_i')} "
                        f"threshold={alpha.get('threshold')} "
                        f"evalue={_format_evalue_for_summary(alpha.get('evalue'))} "
                        f"decision={alpha.get('decision')}"
                    )
        lines.append("")
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _const_false_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {"tag": "bool", "value": False},
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _is_even_base_def(name: str, int_min: int, int_max: int) -> dict:
    outside = {
        "tag": "prim",
        "op": "or",
        "args": [
            {
                "tag": "prim",
                "op": "lt_int",
                "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": int_min}],
            },
            {
                "tag": "prim",
                "op": "lt_int",
                "args": [{"tag": "int", "value": int_max}, {"tag": "var", "name": "n"}],
            },
        ],
    }
    body = {
        "tag": "if",
        "cond": outside,
        "then": {"tag": "bool", "value": False},
        "else": _is_even_body("n"),
    }
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": body,
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _is_even_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": _is_even_body("n"),
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _overfit_def(name: str, int_min: int, int_max: int) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": _overfit_body("n", int_min, int_max),
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _is_even_body(var: str) -> dict:
    return {
        "tag": "prim",
        "op": "eq_int",
        "args": [
            {
                "tag": "prim",
                "op": "mod",
                "args": [{"tag": "var", "name": var}, {"tag": "int", "value": 2}],
            },
            {"tag": "int", "value": 0},
        ],
    }


def _overfit_body(var: str, int_min: int, int_max: int) -> dict:
    outside = {
        "tag": "prim",
        "op": "or",
        "args": [
            {
                "tag": "prim",
                "op": "lt_int",
                "args": [{"tag": "var", "name": var}, {"tag": "int", "value": int_min}],
            },
            {
                "tag": "prim",
                "op": "lt_int",
                "args": [{"tag": "int", "value": int_max}, {"tag": "var", "name": var}],
            },
        ],
    }
    return {
        "tag": "if",
        "cond": outside,
        "then": {"tag": "bool", "value": False},
        "else": _is_even_body(var),
    }


def _bounded_spec(symbol: str, int_min: int, int_max: int) -> dict:
    lhs = {"tag": "app", "fn": {"tag": "sym", "name": symbol}, "args": [{"tag": "var", "name": "n"}]}
    rhs = {"tag": "app", "fn": {"tag": "sym", "name": "is_even_oracle"}, "args": [{"tag": "var", "name": "n"}]}
    return {
        "kind": "forall",
        "vars": [{"name": "n", "type": {"tag": "int"}}],
        "domain": {"int_min": int_min, "int_max": int_max, "list_max_len": 0, "fun_symbols": []},
        "assert": _bool_eq(lhs, rhs),
    }


def _bool_eq(left: dict, right: dict) -> dict:
    return {
        "tag": "prim",
        "op": "or",
        "args": [
            {"tag": "prim", "op": "and", "args": [left, right]},
            {
                "tag": "prim",
                "op": "and",
                "args": [
                    {"tag": "prim", "op": "not", "args": [left]},
                    {"tag": "prim", "op": "not", "args": [right]},
                ],
            },
        ],
    }


def _evaluate_checks(results: dict) -> dict[str, bool]:
    regimes = results.get("regimes") or {}
    bounded = regimes.get("bounded_only") or {}
    stat = regimes.get("stat_cert") or {}
    bounded_steps = bounded.get("steps") or []
    stat_steps = stat.get("steps") or []

    overfit_bounded = next((s for s in bounded_steps if s.get("label") == "overfit"), None)
    overfit_stat = next((s for s in stat_steps if s.get("label") == "overfit"), None)
    correct_stat = next((s for s in stat_steps if s.get("label") == "correct"), None)

    checks = {}
    if overfit_bounded:
        checks["regime_a_ood_failure"] = (overfit_bounded.get("sealed_score") or 0) < (
            overfit_bounded.get("bounded_score") or 0
        )
    if overfit_stat:
        checks["regime_b_overfit_rejected"] = not bool(overfit_stat.get("accepted"))
    if correct_stat:
        checks["regime_b_ood_improved"] = (correct_stat.get("sealed_score") or 0) >= 0.9
    checks["non_interference_ok"] = all(
        bool(step.get("invariants_ok")) for step in (bounded_steps + stat_steps)
    )
    return checks


def _candidate_deps(include_stat_cert: bool) -> list[str]:
    deps = ["is_even_oracle"]
    if include_stat_cert:
        deps.append("is_even_base")
    return deps


def _defs_for_candidate(symbol: str, int_min: int, int_max: int) -> dict[str, object]:
    defs = {
        "is_even_oracle": parse_definition(_is_even_def("is_even_oracle")),
        "is_even_base": parse_definition(_is_even_base_def("is_even_base", int_min, int_max)),
    }
    if symbol == "is_even_overfit":
        defs[symbol] = parse_definition(_overfit_def(symbol, int_min, int_max))
    elif symbol == "is_even_correct":
        defs[symbol] = parse_definition(_is_even_def(symbol))
    else:
        defs[symbol] = parse_definition(_is_even_def(symbol))
    return defs
