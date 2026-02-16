"""Run coordinator for untrusted orchestration loops."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from cdel.config import load_config_from_path
from cdel.constraints import canonicalize_constraint_spec, constraint_spec_hash
from cdel.sealed.config import load_sealed_config
from cdel.sealed.evalue import format_decimal, parse_decimal

from orchestrator.cdel_client import CDELClient, _redact_text
from orchestrator.ledger_view import LedgerView
from orchestrator.llm_backend import get_backend
from orchestrator.llm_call_log import LLMCallLogger
from orchestrator.llm_limits import LLMBackendLimits
from orchestrator.metrics import compute_scoreboard
from orchestrator.promote import evaluate_candidate_dev, promote_candidate_heldout
from orchestrator.proposer.llm import LLMProposer, ProposerLimits
from orchestrator.proposer.repair import RepairProposer
from orchestrator.proposer.template import TemplateProposer
from orchestrator.ranking import (
    RankedCandidate,
    candidate_payload_hash,
    count_candidate_ast_nodes,
    rank_candidates,
)
from orchestrator.retrieval import retrieve_context
from orchestrator.types import Candidate, ContextBundle
from orchestrator.validation import Limits, validate_candidate


_DEF_RUNS_DIR = "runs"


def run_orchestrator(
    *,
    root_dir: Path,
    concept: str,
    oracle_symbol: str,
    dev_config: Path,
    heldout_config: Path,
    heldout_suites_dir: Path | None,
    safety_config: Path | None,
    safety_suites_dir: Path | None,
    constraint_spec_path: Path | None,
    seed_key: str,
    min_dev_diff_sum: int,
    max_attempts: int,
    max_heldout_attempts: int = 1,
    max_context_symbols: int,
    max_counterexamples: int = 3,
    run_id: str | None,
    runs_dir: Path,
    baseline_symbol: str | None,
    rng_seed: int,
    proposer_names: list[str] | None = None,
    domain_candidates: list[Candidate] | None = None,
    validation_limits: Limits | None = None,
    proposer_limits: ProposerLimits | None = None,
) -> Path:
    client = CDELClient()
    ledger = LedgerView(root_dir)

    if not (root_dir / "ledger" / "head").exists():
        client.init_workspace(root_dir)

    dev_cfg = load_config_from_path(root_dir, dev_config)
    heldout_cfg = load_config_from_path(root_dir, heldout_config)
    dev_sealed = load_sealed_config(dev_cfg.data, require_keys=False)
    heldout_sealed = load_sealed_config(heldout_cfg.data, require_keys=False)
    safety_info = None
    if safety_config is not None:
        safety_cfg = load_config_from_path(root_dir, safety_config)
        safety_sealed = load_sealed_config(safety_cfg.data, require_keys=False)
        spec_hash = None
        if constraint_spec_path is not None:
            spec_payload = json.loads(constraint_spec_path.read_text(encoding="utf-8"))
            spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_payload))
        safety_info = {
            "config": str(safety_config.resolve()),
            "suite_hash": safety_sealed.eval_suite_hash,
            "harness_hash": safety_sealed.eval_harness_hash,
            "spec_hash": spec_hash,
        }

    baseline = baseline_symbol or client.resolve_concept(root_dir, concept, config=dev_config)
    if not baseline:
        raise RuntimeError("missing baseline symbol; set --baseline or adopt a symbol")

    signature = ledger.get_symbol_signature(baseline) or ledger.get_symbol_signature(oracle_symbol)
    if signature is None:
        raise RuntimeError("missing type signature for baseline/oracle")

    bundle = ContextBundle(
        concept=concept,
        baseline_symbol=baseline,
        oracle_symbol=oracle_symbol,
        type_norm=signature.type_norm,
        symbols=[],
    )
    context_symbols = retrieve_context(ledger=ledger, bundle=bundle, limit=max_context_symbols)
    bundle = ContextBundle(
        concept=concept,
        baseline_symbol=baseline,
        oracle_symbol=oracle_symbol,
        type_norm=signature.type_norm,
        symbols=context_symbols,
    )

    proposer_names = proposer_names or ["template", "repair"]
    proposer_set = {name.strip().lower() for name in proposer_names if name.strip()}
    validation_limits = validation_limits or Limits(max_new_symbols=1, max_ast_nodes=50, max_ast_depth=20)
    proposer_limits = proposer_limits or ProposerLimits(max_new_symbols=1, max_ast_nodes=50)

    run_id = run_id or _default_run_id()
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = run_dir / "llm_cache"
    os.environ.setdefault("ORCH_LLM_CACHE_DIR", str(cache_dir))

    candidate_queue: list[Candidate] = []
    if domain_candidates:
        candidate_queue.extend(domain_candidates)

    proposer_idx = 0
    if "template" in proposer_set:
        proposer = TemplateProposer()
        candidate_queue.extend(proposer.propose(context=bundle, budget=1, rng_seed=rng_seed + proposer_idx))
        proposer_idx += 1
    llm_logger = LLMCallLogger()
    llm_limits = LLMBackendLimits.from_env()

    if "llm" in proposer_set:
        llm = LLMProposer(
            get_backend(logger=llm_logger),
            root_dir=root_dir,
            config_path=dev_config,
            limits=proposer_limits,
        )
        candidate_queue.extend(llm.propose(context=bundle, budget=1, rng_seed=rng_seed + proposer_idx))
        proposer_idx += 1

    if "agent" in proposer_set:
        from orchestrator.proposer.agent import AgentProposer

        agent = AgentProposer(root_dir=root_dir, config_path=dev_config, run_dir=run_dir)
        candidate_queue.extend(agent.propose(context=bundle, budget=1, rng_seed=rng_seed + proposer_idx))
        proposer_idx += 1

    attempts_log: list[dict] = []
    ranked_candidates: list[RankedCandidate] = []
    seen_hashes: set[str] = set()
    accepted = False
    reason = "no_candidates"

    try:
        attempt_idx = 0
        while candidate_queue and attempt_idx < max_attempts:
            if _alpha_budget_exhausted(ledger, heldout_sealed.alpha_total):
                reason = "alpha_budget_exhausted"
                break
            candidate = candidate_queue.pop(0)
            try:
                validated = validate_candidate(candidate.payload, limits=validation_limits, allowlist=None)
            except ValueError as exc:
                attempts_log.append(
                    {
                        "attempt_idx": attempt_idx,
                        "candidate": candidate.name,
                        "proposer": candidate.proposer,
                        "dev_diff_sum": None,
                        "dev_passed": False,
                        "counterexamples": 0,
                        "heldout_reason": None,
                        "validation_error": str(exc),
                    }
                )
                attempt_idx += 1
                continue

            candidate = Candidate(
                name=validated.name,
                payload=validated.payload,
                proposer=candidate.proposer,
                notes=candidate.notes,
                meta=candidate.meta,
            )
            payload_hash = candidate_payload_hash(candidate.payload)
            if payload_hash in seen_hashes:
                continue
            seen_hashes.add(payload_hash)

            candidate_dir = run_dir / "candidates" / str(attempt_idx)
            dev_eval, counterexamples, candidate_path = evaluate_candidate_dev(
                root_dir=root_dir,
                baseline=baseline,
                oracle=oracle_symbol,
                candidate=candidate,
                dev_config=dev_config,
                seed_key=seed_key,
                min_dev_diff_sum=min_dev_diff_sum,
                out_dir=candidate_dir,
                max_counterexamples=max_counterexamples,
            )
            attempt_log = {
                "attempt_idx": attempt_idx,
                "candidate": candidate.name,
                "proposer": candidate.proposer,
                "dev_diff_sum": dev_eval.diff_sum,
                "dev_passed": dev_eval.passes_min_dev_diff_sum,
                "counterexamples": len(counterexamples),
                "heldout_reason": None,
            }
            if candidate.meta:
                attempt_log.update(
                    {
                        "llm_parse_success": candidate.meta.get("llm_parse_success"),
                        "llm_validation_success": candidate.meta.get("llm_validation_success"),
                        "llm_retry_count": candidate.meta.get("llm_retry_count"),
                        "llm_last_error": candidate.meta.get("llm_last_error"),
                    }
                )
            attempts_log.append(attempt_log)

            if dev_eval.passes_min_dev_diff_sum:
                ast_nodes = count_candidate_ast_nodes(candidate.payload)
                new_symbols = len(candidate.payload.get("new_symbols") or [])
                ranked_candidates.append(
                    RankedCandidate(
                        candidate=candidate,
                        diff_sum=dev_eval.diff_sum,
                        ast_nodes=ast_nodes,
                        new_symbols=new_symbols,
                        attempt_idx=attempt_idx,
                        candidate_path=candidate_path,
                    )
                )
            else:
                if "repair" in proposer_set and counterexamples:
                    if dev_sealed.eval_harness_id == "pyut-harness-v1":
                        from orchestrator.proposer.pyut_repair import PyUTRepairProposer

                        repair = PyUTRepairProposer(failing_candidate=candidate, counterexample=counterexamples[0])
                    else:
                        repair = RepairProposer(failing_candidate=candidate, counterexample=counterexamples[0])
                    candidate_queue.extend(
                        repair.propose(context=bundle, budget=1, rng_seed=rng_seed + attempt_idx)
                    )
                if "llm" in proposer_set:
                    llm = LLMProposer(
                        get_backend(logger=llm_logger),
                        root_dir=root_dir,
                        config_path=dev_config,
                        limits=proposer_limits,
                        counterexamples=counterexamples,
                    )
                    candidate_queue.extend(
                        llm.propose(context=bundle, budget=1, rng_seed=rng_seed + attempt_idx)
                    )
            attempt_idx += 1

        if max_attempts == 0:
            reason = "max_attempts_zero"

        heldout_attempts = 0
        for ranked in rank_candidates(ranked_candidates):
            if heldout_attempts >= max_heldout_attempts:
                reason = "max_heldout_attempts"
                break
            attempt_log = attempts_log[ranked.attempt_idx]
            result = promote_candidate_heldout(
                client=client,
                root_dir=root_dir,
                concept=concept,
                baseline=baseline,
                oracle=oracle_symbol,
                candidate=ranked.candidate,
                candidate_path=ranked.candidate_path,
                heldout_config=heldout_config,
                heldout_suites_dir=heldout_suites_dir,
                safety_config=safety_config,
                safety_suites_dir=safety_suites_dir,
                constraint_spec_path=constraint_spec_path,
                seed_key=seed_key,
                out_dir=run_dir / "candidates" / str(ranked.attempt_idx),
            )
            attempt_log["heldout_reason"] = result.reason
            heldout_attempts += 1
            if result.accepted:
                accepted = True
                reason = result.reason
                break
        if ranked_candidates and not accepted and reason == "no_candidates":
            reason = "heldout_failed"
    finally:
        manifest_path = run_dir / "manifest.json"
        _write_json(
            manifest_path,
            _build_manifest(
                run_id=run_id,
                root_dir=root_dir,
                dev_config=dev_config,
                heldout_config=heldout_config,
                dev_sealed=dev_sealed,
                heldout_sealed=heldout_sealed,
                seed_key=seed_key,
                min_dev_diff_sum=min_dev_diff_sum,
                max_attempts=max_attempts,
                accepted=accepted,
                reason=reason,
                commands=client.command_log,
                attempts=attempts_log,
                llm_info=_build_llm_manifest(llm_logger, llm_limits),
                safety_info=safety_info,
            ),
        )
        scoreboard_path = run_dir / "scoreboard.json"
        _write_json(
            scoreboard_path,
            compute_scoreboard(run_dir, dev_config=dev_config, heldout_config=heldout_config),
        )

    return run_dir


def _alpha_budget_exhausted(ledger: LedgerView, alpha_total) -> bool:
    state = ledger.get_stat_cert_state()
    if state is None:
        return False
    _, alpha_spent = state
    return parse_decimal(alpha_spent) >= alpha_total


def _build_manifest(
    *,
    run_id: str,
    root_dir: Path,
    dev_config: Path,
    heldout_config: Path,
    dev_sealed,
    heldout_sealed,
    seed_key: str,
    min_dev_diff_sum: int,
    max_attempts: int,
    accepted: bool,
    reason: str,
    commands: list,
    attempts: list[dict],
    llm_info: dict | None = None,
    safety_info: dict | None = None,
) -> dict:
    version_info = _cdel_version_info()
    redacted_attempts: list[dict] = []
    for attempt in attempts:
        entry = dict(attempt)
        last_error = entry.get("llm_last_error")
        if isinstance(last_error, str):
            entry["llm_last_error"] = _redact_text(last_error[:500])
        redacted_attempts.append(entry)

    return {
        "run_id": run_id,
        "root_dir": str(root_dir.resolve()),
        "cdel_version": version_info["version"],
        "cdel_commit": version_info["commit"],
        "dev_config": str(dev_config.resolve()),
        "heldout_config": str(heldout_config.resolve()),
        "dev_suite_hash": dev_sealed.eval_suite_hash,
        "heldout_suite_hash": heldout_sealed.eval_suite_hash,
        "dev_harness_hash": dev_sealed.eval_harness_hash,
        "heldout_harness_hash": heldout_sealed.eval_harness_hash,
        "seed_keys": {"dev": seed_key, "heldout": seed_key},
        "alpha_total": format_decimal(heldout_sealed.alpha_total),
        "alpha_schedule": {
            "name": heldout_sealed.alpha_schedule.name,
            "exponent": heldout_sealed.alpha_schedule.exponent,
            "coefficient": format_decimal(heldout_sealed.alpha_schedule.coefficient),
        },
        "safety": safety_info or {},
        "min_dev_diff_sum": min_dev_diff_sum,
        "max_attempts": max_attempts,
        "accepted": accepted,
        "reason": reason,
        "attempts": redacted_attempts,
        "llm": llm_info or {},
        "commands": [
            {
                "argv": record.argv,
                "env": record.env,
                "env_overrides": record.env_overrides,
                "env_unset": record.env_unset,
                "cwd": record.cwd,
                "returncode": record.returncode,
                "stdout_preview": record.stdout_preview,
                "stderr_preview": record.stderr_preview,
                "expected_files": record.expected_files,
                "expected_files_ok": record.expected_files_ok,
                "expected_files_errors": record.expected_files_errors,
            }
            for record in commands
        ],
    }


def _build_llm_manifest(logger: LLMCallLogger, limits: LLMBackendLimits) -> dict:
    backend = os.environ.get("ORCH_LLM_BACKEND", "mock").lower()
    replay_path = os.environ.get("ORCH_LLM_REPLAY_PATH")
    cache_dir = os.environ.get("ORCH_LLM_CACHE_DIR")
    return {
        "backend": backend,
        "replay_path": replay_path,
        "cache_dir": cache_dir,
        "max_prompt_chars": limits.max_prompt_chars,
        "max_response_chars": limits.max_response_chars,
        "max_calls": limits.max_calls,
        "calls_used": logger.calls_used,
        "calls": logger.records,
    }


def _cdel_version_info() -> dict[str, str]:
    version = "unknown"
    commit = "unknown"
    try:
        version = metadata.version("cdel")
    except metadata.PackageNotFoundError:
        version = "unknown"

    try:
        dist = metadata.distribution("cdel")
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            payload = json.loads(direct_url)
            vcs_info = payload.get("vcs_info") or {}
            commit_id = vcs_info.get("commit_id")
            if isinstance(commit_id, str) and commit_id:
                commit = commit_id
    except Exception:
        pass

    if commit == "unknown":
        commit = _cdel_commit_from_pyproject() or commit

    return {"version": version, "commit": commit}


def _cdel_commit_from_pyproject() -> str | None:
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r"cdel\s*@\s*git\+[^@]+@([0-9a-f]{7,40})", text)
    return match.group(1) if match else None


def _default_run_id() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("run_%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the untrusted orchestrator loop")
    parser.add_argument("--root", required=True, help="CDEL workspace root")
    parser.add_argument("--domain", default=None)
    parser.add_argument("--concept", default=None)
    parser.add_argument("--oracle", dest="oracle_symbol", default=None)
    parser.add_argument("--dev-config", default=None)
    parser.add_argument("--heldout-config", default=None)
    parser.add_argument("--heldout-suites-dir", default=None)
    parser.add_argument("--safety-config", default=None)
    parser.add_argument("--safety-suites-dir", default=None)
    parser.add_argument("--constraints-spec", default=None)
    parser.add_argument("--seed-key", default="sealed-seed")
    parser.add_argument("--min-dev-diff-sum", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--max-heldout-attempts", type=int, default=1)
    parser.add_argument("--max-context-symbols", type=int, default=20)
    parser.add_argument("--max-counterexamples", type=int, default=3)
    parser.add_argument("--proposers", default="template,repair")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--runs-dir", default=_DEF_RUNS_DIR)
    parser.add_argument("--baseline", dest="baseline_symbol", default=None)
    parser.add_argument("--rng-seed", type=int, default=0)

    args = parser.parse_args(argv)

    domain_candidates: list[Candidate] | None = None
    validation_limits: Limits | None = None
    proposer_limits: ProposerLimits | None = None
    if args.domain:
        require_repo = args.dev_config is None or args.heldout_config is None
        domain = _resolve_domain(args.domain, require_repo=require_repo)
        if args.concept is None:
            args.concept = domain.concept
        if args.oracle_symbol is None:
            args.oracle_symbol = domain.oracle_symbol
        if args.baseline_symbol is None:
            args.baseline_symbol = domain.baseline_symbol
        if args.dev_config is None and domain.dev_config is not None:
            args.dev_config = str(domain.dev_config)
        if args.heldout_config is None and domain.heldout_config is not None:
            args.heldout_config = str(domain.heldout_config)
        domain_candidates = _domain_candidates(args.domain, args.concept, args.rng_seed)
        validation_limits = getattr(domain, "validation_limits", None)
        proposer_limits = getattr(domain, "proposer_limits", None)

    if not args.concept or not args.oracle_symbol or not args.dev_config or not args.heldout_config:
        raise SystemExit("missing required concept/oracle/config (set --domain or provide flags)")

    run_dir = run_orchestrator(
        root_dir=Path(args.root).resolve(),
        concept=args.concept,
        oracle_symbol=args.oracle_symbol,
        dev_config=Path(args.dev_config).resolve(),
        heldout_config=Path(args.heldout_config).resolve(),
        heldout_suites_dir=Path(args.heldout_suites_dir).resolve() if args.heldout_suites_dir else None,
        safety_config=Path(args.safety_config).resolve() if args.safety_config else None,
        safety_suites_dir=Path(args.safety_suites_dir).resolve() if args.safety_suites_dir else None,
        constraint_spec_path=Path(args.constraints_spec).resolve() if args.constraints_spec else None,
        seed_key=args.seed_key,
        min_dev_diff_sum=args.min_dev_diff_sum,
        max_attempts=args.max_attempts,
        max_heldout_attempts=args.max_heldout_attempts,
        max_context_symbols=args.max_context_symbols,
        max_counterexamples=args.max_counterexamples,
        run_id=args.run_id,
        runs_dir=Path(args.runs_dir).resolve(),
        baseline_symbol=args.baseline_symbol,
        rng_seed=args.rng_seed,
        proposer_names=_parse_proposers(args.proposers),
        domain_candidates=domain_candidates,
        validation_limits=validation_limits,
        proposer_limits=proposer_limits,
    )
    print(str(run_dir))
    return 0


def _resolve_domain(domain_id: str, *, require_repo: bool = True):
    cdel_root = _default_cdel_repo() if require_repo else None
    if domain_id == "env-gridworld-v1":
        from orchestrator.domains.env_gridworld_v1 import load_domain

        return load_domain(cdel_root)
    if domain_id == "io-algorithms-v1":
        from orchestrator.domains.io_algorithms_v1 import load_domain

        return load_domain(cdel_root)
    if domain_id == "python-ut-v1":
        from orchestrator.domains.python_ut_v1 import load_domain

        return load_domain(cdel_root)
    raise SystemExit(f"unknown domain: {domain_id}")


def _domain_candidates(domain_id: str, concept: str, rng_seed: int) -> list[Candidate]:
    if domain_id == "env-gridworld-v1":
        from orchestrator.domains.env_gridworld_v1 import candidate_templates

        return candidate_templates(concept=concept, rng_seed=rng_seed)
    if domain_id == "io-algorithms-v1":
        from orchestrator.domains.io_algorithms_v1 import candidate_templates

        return candidate_templates(concept=concept, rng_seed=rng_seed)
    if domain_id == "python-ut-v1":
        from orchestrator.domains.python_ut_v1 import candidate_templates

        return candidate_templates(concept=concept, rng_seed=rng_seed)
    return []


def _default_cdel_repo() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root.parent / "CDEL"
    if candidate.exists():
        return candidate
    raise SystemExit("CDEL repo not found; pass explicit --dev-config/--heldout-config")


def _parse_proposers(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
