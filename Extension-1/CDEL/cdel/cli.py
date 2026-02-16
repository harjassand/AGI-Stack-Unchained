"""CDEL CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cdel.config import load_config, write_default_config
from cdel.adoption.storage import (
    init_storage as init_adoption_storage,
    read_head as read_adoption_head,
    read_object as read_adoption_object,
)
from cdel.adoption.verifier import commit_adoption
from cdel.consolidate import consolidate_concept
from cdel.sealed.crypto import generate_keypair, generate_keypair_from_seed, key_id_from_public_key
from cdel.sealed.worker import issue_stat_cert
from cdel.kernel.canon import definition_hash
from cdel.kernel.deps import collect_sym_refs
from cdel.kernel.eval import Evaluator, FunVal, IntVal, BoolVal, ListVal, OptionVal, PairVal
from cdel.kernel.parse import parse_definition, parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.audit import audit_ledger, audit_run
from cdel.ledger.rebuild import rebuild_index
from cdel.ledger.storage import init_storage, iter_order_log, read_object
from cdel.ledger.verifier import commit_module, verify_module


def main() -> None:
    parser = argparse.ArgumentParser(prog="cdel")
    parser.add_argument("--root", default=".", help="project root")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init")
    init_p.add_argument("--budget", type=int, default=1_000_000)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("module_json")

    commit_p = sub.add_parser("commit")
    commit_p.add_argument("module_json")

    adopt_p = sub.add_parser("adopt")
    adopt_p.add_argument("adoption_json", nargs="?")
    adopt_p.add_argument("--concept", default=None)
    adopt_p.add_argument("--to", dest="adopt_to", default=None)
    adopt_p.add_argument("--cert", dest="adopt_cert", default=None)

    eval_p = sub.add_parser("eval")
    eval_p.add_argument("--expr", required=True, help="JSON-encoded term AST")
    eval_p.add_argument("--stats", action="store_true", help="include closure stats")
    eval_p.add_argument("--cache", action="store_true", help="use closure cache")
    eval_p.add_argument("--load-mode", choices=["indexed", "scan"], default="indexed")

    query_p = sub.add_parser("query")
    query_p.add_argument("--symbol", required=True)

    search_p = sub.add_parser("search")
    search_group = search_p.add_mutually_exclusive_group(required=True)
    search_group.add_argument("--type")
    search_group.add_argument("--name-prefix")
    search_group.add_argument("--deps")
    search_p.add_argument("--limit", type=int, default=20)
    search_p.add_argument("--top", type=int, default=None)

    resolve_p = sub.add_parser("resolve")
    resolve_group = resolve_p.add_mutually_exclusive_group(required=True)
    resolve_group.add_argument("--concept")
    resolve_group.add_argument("--family")
    resolve_p.add_argument("--policy", choices=["adopted", "all", "latest"], default="adopted")
    resolve_p.add_argument("--limit", type=int, default=20)
    resolve_p.add_argument("--show-active", action="store_true")
    resolve_p.add_argument("--show-candidates", action="store_true")
    resolve_p.add_argument("--show-cert-summary", action="store_true")

    consolidate_p = sub.add_parser("consolidate")
    consolidate_p.add_argument("--concept", required=True)
    consolidate_p.add_argument("--policy", choices=["best_cert"], default="best_cert")
    consolidate_p.add_argument("--topk", type=int, default=5)
    consolidate_p.add_argument("--outdir", required=True)
    consolidate_p.add_argument("--write-proposal", action="store_true")

    list_p = sub.add_parser("list")
    list_sub = list_p.add_subparsers(dest="list_cmd", required=True)
    list_concepts_p = list_sub.add_parser("concepts")
    list_concepts_p.add_argument("--family", default=None)
    list_concepts_p.add_argument("--limit", type=int, default=None)

    rebuild_p = sub.add_parser("rebuild-index")

    inv_p = sub.add_parser("check-invariants")

    dump_p = sub.add_parser("dump-symbol")
    dump_p.add_argument("--name", required=True)

    stats_p = sub.add_parser("library-stats")
    stats_p.add_argument("--limit", type=int, default=20)
    stats_p.add_argument("--json", dest="stats_json", default=None)

    lint_p = sub.add_parser("lint")
    lint_p.add_argument("--limit", type=int, default=20)

    recommend_p = sub.add_parser("recommend")
    recommend_p.add_argument("--symbol", required=True)
    recommend_p.add_argument("--limit", type=int, default=5)

    run_p = sub.add_parser("run-tasks")
    run_p.add_argument("stream_jsonl")
    run_p.add_argument("--generator", default="enum")
    run_p.add_argument("--report", default=None)
    run_p.add_argument("--out", default=None)
    run_p.add_argument("--no-report", action="store_true")
    run_p.add_argument("--proof-synth", action="store_true")

    gen_p = sub.add_parser("run-generalization-experiment")
    gen_p.add_argument("--out", required=True)
    gen_p.add_argument("--episodes", type=int, default=64)
    gen_p.add_argument("--eval-int-min", type=int, default=-20)
    gen_p.add_argument("--eval-int-max", type=int, default=20)
    gen_p.add_argument("--bounded-int-min", type=int, default=-2)
    gen_p.add_argument("--bounded-int-max", type=int, default=2)
    gen_p.add_argument("--seed-key", default="sealed-seed")
    gen_p.add_argument("--budget", type=int, default=1_000_000)

    solve_p = sub.add_parser("solve")
    solve_p.add_argument("--task", required=True)
    solve_p.add_argument("--max-candidates", type=int, default=2)
    solve_p.add_argument("--episodes", type=int, default=64)
    solve_p.add_argument("--seed-key", default="sealed-seed")
    solve_p.add_argument("--private-key", default=None)
    solve_p.add_argument("--max-context-symbols", type=int, default=50)
    solve_p.add_argument(
        "--strategy",
        choices=["baseline_enum", "retrieval_guided", "template_guided", "hybrid"],
        default="template_guided",
    )

    solve_suite_p = sub.add_parser("solve-suite")
    solve_suite_p.add_argument("--suite", default="trackA")
    solve_suite_p.add_argument("--limit", type=int, default=0)
    solve_suite_p.add_argument("--budget-per-task", type=int, default=100000)
    solve_suite_p.add_argument("--max-candidates", type=int, default=2)
    solve_suite_p.add_argument("--episodes", type=int, default=64)
    solve_suite_p.add_argument("--seed-key", default="sealed-seed")
    solve_suite_p.add_argument("--private-key", default=None)
    solve_suite_p.add_argument(
        "--strategy",
        choices=["baseline_enum", "retrieval_guided", "template_guided", "hybrid"],
        default="template_guided",
    )
    solve_suite_p.add_argument("--max-context-symbols", type=int, default=50)
    solve_suite_p.add_argument("--distractor-modules", type=int, default=0)
    solve_suite_p.add_argument("--distractor-symbols", type=int, default=0)
    solve_suite_p.add_argument("--outdir", required=True)

    solve_abl_p = sub.add_parser("solve-suite-ablations")
    solve_abl_p.add_argument("--suite", default="trackA")
    solve_abl_p.add_argument("--limit", type=int, default=0)
    solve_abl_p.add_argument("--strategies", default="baseline_enum,hybrid")
    solve_abl_p.add_argument("--budget-per-task", type=int, default=100000)
    solve_abl_p.add_argument("--max-candidates", type=int, default=2)
    solve_abl_p.add_argument("--episodes", type=int, default=64)
    solve_abl_p.add_argument("--seed-key", default="sealed-seed")
    solve_abl_p.add_argument("--max-context-symbols", type=int, default=50)
    solve_abl_p.add_argument("--private-key", default=None)
    solve_abl_p.add_argument("--deterministic", action="store_true")
    solve_abl_p.add_argument("--outdir", required=True)

    evidence_p = sub.add_parser("run-evidence-suite")
    evidence_p.add_argument("--out", required=True)
    evidence_p.add_argument("--tasks-per-family", type=int, default=10)
    evidence_p.add_argument("--episodes", type=int, default=64)
    evidence_p.add_argument("--eval-episodes", type=int, default=64)
    evidence_p.add_argument("--seed-key", default="sealed-seed")
    evidence_p.add_argument("--budget", type=int, default=1_000_000)

    scale_p = sub.add_parser("run-scaling-experiment")
    scale_p.add_argument("--out", required=True)
    scale_p.add_argument("--modules", type=int, default=1000)
    scale_p.add_argument("--step", type=int, default=200)
    scale_p.add_argument("--budget", type=int, default=1_000_000)

    solve_score_p = sub.add_parser("run-solve-scoreboard")
    solve_score_p.add_argument("--out", required=True)
    solve_score_p.add_argument("--tasks", type=int, default=10)
    solve_score_p.add_argument("--max-candidates", type=int, default=2)
    solve_score_p.add_argument("--episodes", type=int, default=64)
    solve_score_p.add_argument("--seed-key", default="sealed-seed")
    solve_score_p.add_argument("--budget", type=int, default=1_000_000)

    stress_p = sub.add_parser("run-solve-stress")
    stress_p.add_argument("--out", required=True)
    stress_p.add_argument("--tasks", type=int, default=50)
    stress_p.add_argument("--max-candidates", type=int, default=2)
    stress_p.add_argument("--episodes", type=int, default=32)
    stress_p.add_argument("--seed-key", default="sealed-seed")
    stress_p.add_argument("--budget", type=int, default=1_000_000)
    stress_p.add_argument("--reuse-every", type=int, default=0)
    stress_p.add_argument(
        "--strategy",
        choices=["baseline_enum", "retrieval_guided", "template_guided", "hybrid"],
        default="template_guided",
    )

    exp_p = sub.add_parser("run-experiment")
    exp_p.add_argument("--tasks", required=True)
    exp_p.add_argument("--generator", default="enum")
    exp_p.add_argument("--out", default=None)
    exp_p.add_argument("--seed", type=int, default=None)
    exp_p.add_argument("--budget", type=int, default=None)
    exp_p.add_argument("--cost-alpha", type=int, default=None)
    exp_p.add_argument("--cost-beta", type=int, default=None)
    exp_p.add_argument("--cost-gamma", type=int, default=None)
    exp_p.add_argument("--spec-int-min", type=int, default=None)
    exp_p.add_argument("--spec-int-max", type=int, default=None)
    exp_p.add_argument("--spec-list-max-len", type=int, default=None)
    exp_p.add_argument("--eval-step-limit", type=int, default=None)
    exp_p.add_argument("--closure-cache", action="store_true")
    exp_p.add_argument("--certificate-mode", default=None)
    exp_p.add_argument("--load-mode", choices=["indexed", "scan"], default="indexed")
    exp_p.add_argument("--proof-synth", action="store_true")

    audit_p = sub.add_parser("audit-ledger")
    audit_group = audit_p.add_mutually_exclusive_group()
    audit_group.add_argument("--fast", action="store_true")
    audit_group.add_argument("--full", action="store_true")

    audit_run_p = sub.add_parser("audit-run")

    audit_p = sub.add_parser("audit")
    audit_sub = audit_p.add_subparsers(dest="audit_cmd", required=True)
    audit_stat = audit_sub.add_parser("stat-cert")
    audit_stat.add_argument("module_hash")
    audit_alpha = audit_sub.add_parser("alpha")
    audit_alpha.add_argument("--limit", type=int, default=10)

    report_p = sub.add_parser("report")
    report_sub = report_p.add_subparsers(dest="report_cmd", required=True)
    summarize_p = report_sub.add_parser("summarize")
    summarize_p.add_argument("report_json")

    runs_p = sub.add_parser("runs")
    runs_sub = runs_p.add_subparsers(dest="runs_cmd", required=True)
    runs_gc = runs_sub.add_parser("gc")
    runs_gc.add_argument("--policy", choices=["keep", "archive", "delete"], default="keep")
    runs_gc.add_argument("--days", type=int, default=7)
    runs_gc.add_argument("--runs-root", default=None)

    selfcheck_p = sub.add_parser("selfcheck")

    sealed_p = sub.add_parser("sealed")
    sealed_sub = sealed_p.add_subparsers(dest="sealed_cmd", required=True)
    sealed_keygen_p = sealed_sub.add_parser("keygen")
    sealed_keygen_p.add_argument("--out", default="-")
    sealed_keygen_p.add_argument("--seed", default=None)

    sealed_worker_p = sealed_sub.add_parser("worker")
    sealed_worker_p.add_argument("--request", default="-")
    sealed_worker_p.add_argument("--out", default="-")
    sealed_worker_p.add_argument("--private-key", default=None)
    sealed_worker_p.add_argument("--seed-key", default=None)
    sealed_worker_p.add_argument("--artifact-dir", default=None)
    sealed_worker_p.add_argument("--candidate-module", default=None)

    args = parser.parse_args()
    root = Path(args.root).resolve()
    cfg = load_config(root)

    if args.cmd == "init":
        write_default_config(root, args.budget)
        init_storage(cfg)
        init_adoption_storage(cfg)
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        idx.set_budget(conn, args.budget)
        conn.commit()
        print("initialized")
        return

    if args.cmd == "verify":
        module = _load_json(Path(args.module_json))
        result = verify_module(cfg, module)
        ok = _print_result(result)
        if not ok:
            sys.exit(1)
        return

    if args.cmd == "commit":
        module = _load_json(Path(args.module_json))
        result = commit_module(cfg, module)
        ok = _print_result(result)
        if not ok:
            sys.exit(1)
        return

    if args.cmd == "adopt":
        if args.adoption_json == "revert":
            _run_adopt_revert(cfg, args.concept, args.adopt_to, args.adopt_cert)
            return
        if not args.adoption_json:
            raise SystemExit("adopt requires adoption_json or 'revert'")
        record = _load_json(Path(args.adoption_json))
        result = commit_adoption(cfg, record)
        ok = _print_adoption_result(result)
        if not ok:
            sys.exit(1)
        return

    if args.cmd == "eval":
        term_json = json.loads(args.expr)
        refs = collect_sym_refs(term_json)
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        if refs:
            if args.load_mode == "scan":
                from cdel.ledger.closure import load_definitions_scan_with_stats

                defs, stats = load_definitions_scan_with_stats(cfg, list(refs))
            else:
                defs, stats = load_definitions_with_stats(cfg, conn, list(refs), use_cache=args.cache)
        else:
            defs, stats = ({}, {"closure_symbols_count": 0, "closure_modules_count": 0, "scanned_modules_count": 0})
        term = parse_term(term_json, [])
        evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
        value = evaluator.eval_term(term, [], defs)
        if args.stats:
            print(json.dumps({"value": _value_to_json(value), **stats}, sort_keys=True))
        else:
            print(json.dumps(_value_to_json(value), sort_keys=True))
        return

    if args.cmd == "query":
        conn = idx.connect(str(cfg.sqlite_path))
        info = idx.get_symbol_info(conn, args.symbol)
        if info is None:
            print("symbol not found")
            return
        module_hash, type_norm = info
        deps = idx.list_symbol_deps(conn, args.symbol)
        print(json.dumps({"symbol": args.symbol, "type": type_norm, "module": module_hash, "deps": deps}, sort_keys=True))
        return

    if args.cmd == "search":
        conn = idx.connect(str(cfg.sqlite_path))
        limit = args.limit if args.top is None else args.top
        if args.type:
            symbols = idx.search_symbols_by_type(conn, args.type, limit)
            print(json.dumps({"type": args.type, "symbols": symbols}, sort_keys=True))
            return
        if args.name_prefix:
            symbols = idx.search_symbols_by_prefix(conn, args.name_prefix, limit)
            print(json.dumps({"name_prefix": args.name_prefix, "symbols": symbols}, sort_keys=True))
            return
        if args.deps:
            symbols = idx.list_reverse_deps(conn, args.deps, limit)
            print(json.dumps({"deps": args.deps, "symbols": symbols}, sort_keys=True))
            return
        return

    if args.cmd == "resolve":
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        if args.family:
            result = _resolve_family(cfg, conn, args.family, args)
        else:
            result = _resolve_concept(cfg, conn, args.concept, args)
        print(json.dumps(result, sort_keys=True))
        return

    if args.cmd == "consolidate":
        out_dir = Path(args.outdir).resolve()
        report = consolidate_concept(
            cfg,
            args.concept,
            policy=args.policy,
            topk=args.topk,
            out_dir=out_dir,
            write_proposal=args.write_proposal,
        )
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "list":
        if args.list_cmd == "concepts":
            result = _list_concepts(cfg, args.family, args.limit)
            print(json.dumps(result, sort_keys=True))
            return

    if args.cmd == "rebuild-index":
        rebuild_index(cfg)
        print("rebuilt")
        return

    if args.cmd == "check-invariants":
        _check_invariants(cfg)
        print("ok")
        return

    if args.cmd == "dump-symbol":
        conn = idx.connect(str(cfg.sqlite_path))
        info = idx.get_symbol_info(conn, args.name)
        if info is None:
            print("symbol not found")
            return
        module_hash, type_norm = info
        deps = idx.list_symbol_deps(conn, args.name)
        print(json.dumps({"symbol": args.name, "type": type_norm, "module": module_hash, "deps": deps}, sort_keys=True))
        return

    if args.cmd == "library-stats":
        from cdel.ledger.stats import library_stats

        stats = library_stats(cfg, limit=args.limit)
        if args.stats_json:
            Path(args.stats_json).write_text(json.dumps(stats, sort_keys=True), encoding="utf-8")
        print(json.dumps(stats, sort_keys=True))
        return

    if args.cmd == "lint":
        from cdel.ledger.lint import lint_ledger

        report = lint_ledger(cfg, limit=args.limit)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "recommend":
        from cdel.ledger.lint import load_deprecated_symbols

        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        aliases = idx.list_aliases_for_target(conn, args.symbol, args.limit)
        target = idx.get_alias_target(conn, args.symbol)
        deprecated = load_deprecated_symbols(cfg)
        replaced_by = deprecated.get(args.symbol)
        recommendations = []
        if replaced_by:
            recommendations.append(replaced_by)
        if aliases:
            recommendations.extend(aliases)
        if not recommendations and target:
            recommendations.append(target)
        print(
            json.dumps(
                {"symbol": args.symbol, "recommendations": recommendations[: args.limit]},
                sort_keys=True,
            )
        )
        return

    if args.cmd == "run-tasks":
        from cdel.bench.run import run_tasks

        if args.report and args.out:
            raise SystemExit("use --report or --out, not both")
        if args.no_report and (args.report or args.out):
            raise SystemExit("--no-report cannot be combined with --report/--out")
        out_dir = Path(args.out).resolve() if args.out else None
        report = run_tasks(
            cfg,
            Path(args.stream_jsonl),
            generator=args.generator,
            report_path=args.report,
            out_dir=out_dir,
            proof_synth=args.proof_synth,
            no_report=args.no_report,
        )
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-experiment":
        from cdel.bench.experiment import run_experiment

        out_dir = Path(args.out).resolve() if args.out else None
        report = run_experiment(
            cfg,
            Path(args.tasks).resolve(),
            generator=args.generator,
            out_dir=out_dir,
            seed=args.seed,
            budget_override=args.budget,
            cost_weights=_collect_cost_weights(args),
            spec_domain=_collect_spec_domain(args),
            eval_step_limit=args.eval_step_limit,
            closure_cache=args.closure_cache,
            certificate_mode=args.certificate_mode,
            load_mode=args.load_mode,
            proof_synth=args.proof_synth,
            run_args=sys.argv,
        )
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-generalization-experiment":
        from cdel.experiments.generalization import ExperimentConfig, run_generalization_experiment

        config = ExperimentConfig(
            episodes=args.episodes,
            eval_int_min=args.eval_int_min,
            eval_int_max=args.eval_int_max,
            bounded_int_min=args.bounded_int_min,
            bounded_int_max=args.bounded_int_max,
            seed_key=args.seed_key,
            budget=args.budget,
        )
        report = run_generalization_experiment(Path(args.out).resolve(), config)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "solve":
        from cdel.solve import solve_task

        private_key = args.private_key or os.environ.get("CDEL_SEALED_PRIVKEY")
        if not private_key:
            raise SystemExit("solve requires --private-key or CDEL_SEALED_PRIVKEY")
        report = solve_task(
            cfg,
            args.task,
            max_candidates=args.max_candidates,
            episodes=args.episodes,
            seed_key=args.seed_key,
            private_key=private_key,
            strategy=args.strategy,
            max_context_symbols=args.max_context_symbols,
        )
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "solve-suite":
        from cdel.bench.solve_suite import SolveSuiteConfig, run_solve_suite

        private_key = args.private_key or os.environ.get("CDEL_SEALED_PRIVKEY")
        if not private_key:
            raise SystemExit("solve-suite requires --private-key or CDEL_SEALED_PRIVKEY")
        config = SolveSuiteConfig(
            suite=args.suite,
            limit=args.limit,
            max_candidates=args.max_candidates,
            episodes=args.episodes,
            seed_key=args.seed_key,
            budget_per_task=args.budget_per_task,
            max_context_symbols=args.max_context_symbols,
            strategy=args.strategy,
            distractor_modules=args.distractor_modules,
            distractor_symbols_per_module=args.distractor_symbols,
        )
        report = run_solve_suite(Path(args.outdir).resolve(), cfg, config, private_key)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "solve-suite-ablations":
        from cdel.bench.solve_suite_ablations import AblationConfig, run_solve_suite_ablations

        private_key = args.private_key or os.environ.get("CDEL_SEALED_PRIVKEY")
        strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
        config = AblationConfig(
            suite=args.suite,
            limit=args.limit,
            strategies=strategies,
            max_candidates=args.max_candidates,
            episodes=args.episodes,
            seed_key=args.seed_key,
            budget_per_task=args.budget_per_task,
            max_context_symbols=args.max_context_symbols,
            deterministic=args.deterministic,
        )
        report = run_solve_suite_ablations(Path(args.outdir).resolve(), config, private_key=private_key)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-evidence-suite":
        from cdel.bench.evidence_suite import EvidenceConfig, run_evidence_suite

        config = EvidenceConfig(
            tasks_per_family=args.tasks_per_family,
            episodes=args.episodes,
            eval_episodes=args.eval_episodes,
            seed_key=args.seed_key,
            budget=args.budget,
        )
        report = run_evidence_suite(Path(args.out).resolve(), config)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-scaling-experiment":
        from cdel.experiments.scaling import ScalingConfig, run_scaling_experiment

        config = ScalingConfig(
            modules=args.modules,
            step=args.step,
            budget=args.budget,
        )
        report = run_scaling_experiment(Path(args.out).resolve(), config)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-solve-stress":
        from cdel.experiments.solve_stress import SolveStressConfig, run_solve_stress

        config = SolveStressConfig(
            tasks=args.tasks,
            max_candidates=args.max_candidates,
            episodes=args.episodes,
            seed_key=args.seed_key,
            budget=args.budget,
            strategy=args.strategy,
            reuse_every=args.reuse_every,
        )
        report = run_solve_stress(Path(args.out).resolve(), config)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "run-solve-scoreboard":
        from cdel.bench.solve_scoreboard import ScoreboardConfig, run_solve_scoreboard

        config = ScoreboardConfig(
            tasks=args.tasks,
            max_candidates=args.max_candidates,
            episodes=args.episodes,
            seed_key=args.seed_key,
            budget=args.budget,
        )
        report = run_solve_scoreboard(Path(args.out).resolve(), config)
        print(json.dumps(report, sort_keys=True))
        return

    if args.cmd == "audit-ledger":
        full = args.full
        audit_ledger(cfg, full=full)
        print("ok")
        return

    if args.cmd == "audit-run":
        audit_run(cfg, root)
        print("ok")
        return

    if args.cmd == "audit":
        if args.audit_cmd == "stat-cert":
            _audit_stat_cert(cfg, args.module_hash)
            return
        if args.audit_cmd == "alpha":
            _audit_alpha(cfg, args.limit)
            return

    if args.cmd == "report":
        if args.report_cmd == "summarize":
            from cdel.bench.summarize import summarize_report

            summary = summarize_report(Path(args.report_json))
            print(json.dumps(summary, sort_keys=True))
            return

    if args.cmd == "runs":
        if args.runs_cmd == "gc":
            from cdel.runs import gc_runs

            runs_root = Path(args.runs_root).resolve() if args.runs_root else root
            result = gc_runs(runs_root, policy=args.policy, days=args.days)
            print(json.dumps(result, sort_keys=True))
            return

    if args.cmd == "selfcheck":
        from cdel.selfcheck import run_selfcheck

        run_selfcheck()
        print("ok")
        return

    if args.cmd == "sealed":
        if args.sealed_cmd == "keygen":
            if args.seed:
                priv, pub = generate_keypair_from_seed(args.seed.encode("utf-8"))
            else:
                priv, pub = generate_keypair()
            payload = {"private_key": priv, "public_key": pub, "key_id": key_id_from_public_key(pub)}
            _write_json(Path(args.out), payload)
            return
        if args.sealed_cmd == "worker":
            request = _load_json(Path(args.request)) if args.request != "-" else json.loads(sys.stdin.read())
            private_key = args.private_key or os.environ.get("CDEL_SEALED_PRIVKEY")
            seed_key = args.seed_key or os.environ.get("CDEL_SEALED_SEED")
            if not private_key or not seed_key:
                raise SystemExit("sealed worker requires --private-key/--seed-key or env vars")
            artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else None
            extra_defs = _load_candidate_defs(Path(args.candidate_module)) if args.candidate_module else None
            result = issue_stat_cert(
                cfg,
                request,
                private_key,
                seed_key.encode("utf-8"),
                artifact_dir=artifact_dir,
                extra_defs=extra_defs,
            )
            _write_json(Path(args.out), result)
            return


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _print_result(result) -> bool:
    if result.ok:
        print(json.dumps({"ok": True, "hash": result.payload_hash, "cost": result.cost}, sort_keys=True))
        return True
    else:
        rej = result.rejection
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": rej.code.value if rej else "error",
                    "reason": rej.reason if rej else "unknown",
                    "details": rej.details if rej else None,
                },
                sort_keys=True,
            )
        )
        return False


def _write_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, sort_keys=True)
    if str(path) == "-":
        print(data)
        return
    path.write_text(data + "\n", encoding="utf-8")


def _load_candidate_defs(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    module = payload.get("payload") if isinstance(payload, dict) and "payload" in payload else payload
    if not isinstance(module, dict):
        raise SystemExit("candidate module payload must be an object")
    defs_raw = module.get("definitions") or []
    if not isinstance(defs_raw, list):
        raise SystemExit("candidate module definitions must be a list")
    defs = {}
    for defn in defs_raw:
        parsed = parse_definition(defn)
        defs[parsed.name] = parsed
    return defs


def _print_adoption_result(result) -> bool:
    if result.ok:
        print(json.dumps({"ok": True, "hash": result.payload_hash}, sort_keys=True))
        return True
    rej = result.rejection
    print(
        json.dumps(
            {
                "ok": False,
                "code": rej.code if rej else "error",
                "reason": rej.reason if rej else "unknown",
                "details": rej.details if rej else None,
            },
            sort_keys=True,
        )
    )
    return False


def _run_adopt_revert(cfg, concept: str | None, target: str | None, cert_path: str | None) -> None:
    if not concept or not target or not cert_path:
        raise SystemExit("adopt revert requires --concept, --to, and --cert")
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    current = idx.latest_adoption_for_concept(conn, concept)
    if current is None:
        raise SystemExit("adopt revert requires an existing adoption for the concept")
    current_symbol = current.get("chosen_symbol")
    if target == current_symbol:
        raise SystemExit("adopt revert target already active for concept")
    cert = _load_json(Path(cert_path))
    record = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": concept,
            "chosen_symbol": target,
            "baseline_symbol": current_symbol,
            "certificate": cert,
            "constraints": {},
        },
    }
    result = commit_adoption(cfg, record)
    ok = _print_adoption_result(result)
    if not ok:
        sys.exit(1)


def _resolve_concept(cfg, conn, concept: str, args) -> dict:
    adoption = idx.latest_adoption_for_concept(conn, concept)
    chosen_symbol = adoption["chosen_symbol"] if adoption else None
    has_show = args.show_active or args.show_candidates or args.show_cert_summary
    if not has_show:
        if args.policy == "latest":
            symbol = idx.latest_symbol_for_concept(conn, concept)
            return {"concept": concept, "symbol": symbol}
        candidates = idx.list_symbols_for_concept(conn, concept, args.limit)
        result = {
            "concept": concept,
            "chosen_symbol": chosen_symbol,
            "adoption_hash": adoption["hash"] if adoption else None,
            "candidates": candidates,
            "fallback": None,
        }
        if args.policy == "adopted" and not chosen_symbol:
            result["chosen_symbol"] = idx.latest_symbol_for_concept(conn, concept)
            result["fallback"] = "latest_candidate"
        return result

    result: dict[str, object] = {"concept": concept}
    if args.show_active or args.show_cert_summary:
        result["chosen_symbol"] = chosen_symbol
        result["adoption_hash"] = adoption["hash"] if adoption else None
        if args.show_active and not chosen_symbol:
            result["chosen_symbol"] = idx.latest_symbol_for_concept(conn, concept)
            result["fallback"] = "latest_candidate"
    if args.show_candidates:
        result["candidates"] = idx.list_symbols_for_concept(conn, concept, args.limit)
    if args.show_cert_summary:
        result["cert_summary"] = _cert_summary(cfg, adoption["hash"]) if adoption else None
    return result


def _resolve_family(cfg, conn, family: str, args) -> dict:
    from cdel.bench.taxonomy import concepts_for_family, families

    if family not in families():
        raise SystemExit(f"unknown concept family: {family}")
    concepts = concepts_for_family(family)
    resolved = [_resolve_concept(cfg, conn, concept, args) for concept in concepts]
    return {"family": family, "concepts": resolved}


def _list_concepts(cfg: Config, family: str | None, limit: int | None) -> dict:
    if family:
        from cdel.bench.taxonomy import concepts_for_family, families

        if family not in families():
            raise SystemExit(f"unknown concept family: {family}")
        concepts = concepts_for_family(family)
        if limit is not None:
            concepts = concepts[:limit]
        return {"family": family, "concepts": concepts}

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    concepts = idx.list_concepts(conn, limit)
    return {"concepts": concepts}


def _cert_summary(cfg: Config, adoption_hash: str) -> dict | None:
    from decimal import localcontext

    from cdel.sealed.evalue import encoded_evalue_to_decimal, format_decimal, parse_decimal, parse_evalue

    try:
        payload_bytes = read_adoption_object(cfg, adoption_hash)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None
    cert = payload.get("certificate") if isinstance(payload, dict) else None
    if not isinstance(cert, dict):
        return None
    risk = cert.get("risk") or {}
    eval_cfg = cert.get("eval") or {}
    cert_payload = cert.get("certificate") or {}
    alpha_i_raw = risk.get("alpha_i")
    threshold = None
    decision = None
    if isinstance(alpha_i_raw, str):
        alpha_i = parse_decimal(alpha_i_raw)
        with localcontext() as ctx:
            ctx.prec = 50
            threshold = format_decimal(parse_decimal("1") / alpha_i)
        try:
            parsed = parse_evalue(cert_payload.get("evalue"), "stat_cert evalue")
            decision = "accept" if encoded_evalue_to_decimal(parsed) * alpha_i >= 1 else "reject"
        except Exception:
            decision = "invalid"
    return {
        "concept": cert.get("concept"),
        "baseline_symbol": cert.get("baseline_symbol"),
        "candidate_symbol": cert.get("candidate_symbol"),
        "evalue_schema_version": cert_payload.get("evalue_schema_version"),
        "key_id": cert_payload.get("key_id"),
        "alpha_i": alpha_i_raw,
        "threshold": threshold,
        "evalue": cert_payload.get("evalue"),
        "decision": decision,
        "eval_harness_hash": eval_cfg.get("eval_harness_hash"),
        "eval_suite_hash": eval_cfg.get("eval_suite_hash"),
    }


def _value_to_json(value):
    if isinstance(value, IntVal):
        return value.value
    if isinstance(value, BoolVal):
        return value.value
    if isinstance(value, ListVal):
        return [_value_to_json(v) for v in value.items]
    if isinstance(value, OptionVal):
        if not value.is_some:
            return {"option": "none"}
        return {"option": "some", "value": _value_to_json(value.value)}
    if isinstance(value, PairVal):
        return {"pair": [_value_to_json(value.left), _value_to_json(value.right)]}
    if isinstance(value, FunVal):
        return {"fun": value.name}
    return str(value)


def _check_invariants(cfg):
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    stored = {}
    cur = conn.execute("SELECT symbol, def_hash FROM def_hashes")
    for row in cur.fetchall():
        stored[row[0]] = row[1]
    for module_hash in iter_order_log(cfg):
        payload = json.loads(read_object(cfg, module_hash).decode("utf-8"))
        for defn in payload.get("definitions", []):
            name = defn.get("name")
            if name not in stored:
                raise ValueError(f"missing symbol in index: {name}")
            current = definition_hash(defn)
            if stored[name] != current:
                raise ValueError(f"def_hash mismatch for {name}")


def _collect_cost_weights(args) -> dict | None:
    weights = {}
    if args.cost_alpha is not None:
        weights["alpha"] = args.cost_alpha
    if args.cost_beta is not None:
        weights["beta"] = args.cost_beta
    if args.cost_gamma is not None:
        weights["gamma"] = args.cost_gamma
    return weights or None


def _collect_spec_domain(args) -> dict | None:
    domain = {}
    if args.spec_int_min is not None:
        domain["int_min"] = args.spec_int_min
    if args.spec_int_max is not None:
        domain["int_max"] = args.spec_int_max
    if args.spec_list_max_len is not None:
        domain["list_max_len"] = args.spec_list_max_len
    return domain or None


def _audit_stat_cert(cfg: Config, module_hash: str) -> None:
    from decimal import localcontext
    import json

    from cdel.ledger.storage import read_object
    from cdel.sealed.evalue import encoded_evalue_to_decimal, parse_decimal, parse_evalue

    payload_bytes = read_object(cfg, module_hash)
    payload = json.loads(payload_bytes.decode("utf-8"))
    specs = payload.get("specs") or []
    records = []

    for spec in specs:
        if not isinstance(spec, dict) or spec.get("kind") != "stat_cert":
            continue
        cert = spec.get("certificate") or {}
        risk = spec.get("risk") or {}
        eval_cfg = spec.get("eval") or {}
        alpha_i_raw = risk.get("alpha_i")
        threshold = None
        decision = None
        if isinstance(alpha_i_raw, str):
            alpha_i = parse_decimal(alpha_i_raw)
            with localcontext() as ctx:
                ctx.prec = 50
                threshold = str(parse_decimal("1") / alpha_i)
        evalue_encoded = None
        if isinstance(cert, dict):
            evalue_encoded = cert.get("evalue")
            try:
                parsed_evalue = parse_evalue(evalue_encoded, "audit evalue")
                if isinstance(alpha_i_raw, str):
                    decision = "accept" if encoded_evalue_to_decimal(parsed_evalue) * alpha_i >= 1 else "reject"
            except Exception:
                parsed_evalue = None
        record = {
            "concept": spec.get("concept"),
            "baseline_symbol": spec.get("baseline_symbol"),
            "candidate_symbol": spec.get("candidate_symbol"),
            "evalue_schema_version": cert.get("evalue_schema_version"),
            "key_id": cert.get("key_id"),
            "eval_harness_id": eval_cfg.get("eval_harness_id"),
            "eval_harness_hash": eval_cfg.get("eval_harness_hash"),
            "eval_suite_hash": eval_cfg.get("eval_suite_hash"),
            "alpha_i": alpha_i_raw,
            "threshold": threshold,
            "evalue": evalue_encoded,
            "decision": decision,
            "rule": "evalue * alpha_i >= 1",
        }
        records.append(record)

    out = {"module_hash": module_hash, "stat_certs": records}
    print(json.dumps(out, sort_keys=True))


def _audit_alpha(cfg: Config, limit: int) -> None:
    from decimal import localcontext
    import json

    from cdel.ledger import index as idx
    from cdel.ledger.storage import iter_order_log, read_object
    from cdel.sealed.config import load_sealed_config
    from cdel.sealed.evalue import encoded_evalue_to_decimal, format_decimal, parse_decimal, parse_evalue

    sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    current_round = state[0] if state else 1
    alpha_spent = state[1] if state else format_decimal(parse_decimal("0"))

    decisions = []
    round_idx = 1
    for module_hash in iter_order_log(cfg):
        payload = json.loads(read_object(cfg, module_hash).decode("utf-8"))
        specs = payload.get("specs") or []
        for spec in specs:
            if not isinstance(spec, dict) or spec.get("kind") != "stat_cert":
                continue
            risk = spec.get("risk") or {}
            alpha_i_raw = risk.get("alpha_i")
            threshold = None
            if isinstance(alpha_i_raw, str):
                alpha_i = parse_decimal(alpha_i_raw)
                with localcontext() as ctx:
                    ctx.prec = 50
                    threshold = format_decimal(parse_decimal("1") / alpha_i)
            evalue_encoded = (spec.get("certificate") or {}).get("evalue")
            decision = None
            if isinstance(alpha_i_raw, str):
                try:
                    parsed_evalue = parse_evalue(evalue_encoded, "audit evalue")
                    decision = (
                        "accept" if encoded_evalue_to_decimal(parsed_evalue) * alpha_i >= 1 else "reject"
                    )
                except Exception:
                    decision = "invalid"
            decisions.append(
                {
                    "module_hash": module_hash,
                    "concept": spec.get("concept"),
                    "round": round_idx,
                    "alpha_i": alpha_i_raw,
                    "threshold": threshold,
                    "evalue": evalue_encoded,
                    "decision": decision,
                }
            )
            round_idx += 1

    tail = decisions[-max(limit, 0) :] if limit else decisions
    out = {
        "alpha_total": format_decimal(sealed_cfg.alpha_total),
        "alpha_schedule": {
            "name": sealed_cfg.alpha_schedule.name,
            "exponent": sealed_cfg.alpha_schedule.exponent,
            "coefficient": format_decimal(sealed_cfg.alpha_schedule.coefficient),
        },
        "current_round": current_round,
        "alpha_spent": alpha_spent,
        "decisions": tail,
    }
    print(json.dumps(out, sort_keys=True))
