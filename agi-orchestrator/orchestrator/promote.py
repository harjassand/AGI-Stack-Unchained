"""Promotion pipeline: dev eval then heldout cert then commit/adopt."""

from __future__ import annotations

import json
from pathlib import Path

from cdel.config import load_config_from_path
from cdel.constraints import canonicalize_constraint_spec, constraint_spec_hash
from cdel.sealed.evalue import encoded_evalue_to_decimal, parse_decimal, parse_evalue

from orchestrator.cdel_client import CDELClient
from orchestrator.counterexamples import capture_counterexamples
from orchestrator.eval.dev_eval import evaluate_dev
from orchestrator.types import Candidate, DevEvalResult, PromotionResult


def evaluate_candidate_dev(
    *,
    root_dir: Path,
    baseline: str,
    oracle: str,
    candidate: Candidate,
    dev_config: Path,
    seed_key: str,
    min_dev_diff_sum: int,
    out_dir: Path,
    max_counterexamples: int,
) -> tuple[DevEvalResult, list[dict], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = out_dir / "candidate.json"
    _write_json(candidate_path, candidate.payload)

    dev_artifact_dir = out_dir / "dev_artifacts"
    dev_eval = evaluate_dev(
        root_dir=root_dir,
        config_path=dev_config,
        baseline=baseline,
        candidate=candidate.name,
        oracle=oracle,
        candidate_payload=candidate.payload,
        seed_key=seed_key.encode("utf-8"),
        min_diff_sum=min_dev_diff_sum,
        artifact_dir=dev_artifact_dir,
    )
    dev_eval_path = out_dir / "dev_eval.json"
    _write_json(dev_eval_path, dev_eval.__dict__)

    counter = capture_counterexamples(
        root_dir=root_dir,
        config_path=dev_config,
        baseline=baseline,
        candidate=candidate.name,
        oracle=oracle,
        candidate_payload=candidate.payload,
        artifact_dir=dev_artifact_dir,
        max_examples=max_counterexamples,
    )
    counter_path = out_dir / "counterexamples.json"
    _write_json(counter_path, {"harness_id": counter.harness_id, "examples": counter.examples})

    return dev_eval, counter.examples, candidate_path


def promote_candidate_heldout(
    *,
    client: CDELClient,
    root_dir: Path,
    concept: str,
    baseline: str,
    oracle: str,
    candidate: Candidate,
    candidate_path: Path,
    heldout_config: Path,
    heldout_suites_dir: Path | None,
    safety_config: Path | None,
    safety_suites_dir: Path | None,
    constraint_spec_path: Path | None,
    seed_key: str,
    out_dir: Path,
) -> PromotionResult:
    if heldout_suites_dir is None or not heldout_suites_dir.exists():
        return PromotionResult(accepted=False, reason="heldout_suites_missing")
    if safety_config is not None:
        if not safety_config.exists():
            return PromotionResult(accepted=False, reason="safety_config_missing")
        if safety_suites_dir is None or not safety_suites_dir.exists():
            return PromotionResult(accepted=False, reason="safety_suites_missing")
        if constraint_spec_path is None or not constraint_spec_path.exists():
            return PromotionResult(accepted=False, reason="constraints_spec_missing")

    heldout_cfg = load_config_from_path(root_dir, heldout_config)
    episodes = _require_episodes(heldout_cfg.data)
    max_steps = int((heldout_cfg.data.get("evaluator") or {}).get("step_limit", 100000))

    request = {
        "kind": "stat_cert",
        "concept": concept,
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate.name,
        "eval": {
            "episodes": episodes,
            "max_steps": max_steps,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
        "risk": {"evalue_threshold": "1"},
    }
    request_path = out_dir / "heldout_request.json"
    _write_json(request_path, request)

    cert_path = out_dir / "heldout_cert.json"
    try:
        client.issue_stat_cert(
            root_dir=root_dir,
            request_path=request_path,
            out_path=cert_path,
            config=heldout_config,
            seed_key=seed_key,
            suites_dir=heldout_suites_dir,
            candidate_module=candidate_path,
        )
    except Exception as exc:
        return PromotionResult(accepted=False, reason=f"heldout_issue_failed: {exc}")

    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    if not _passes_threshold(cert):
        return PromotionResult(accepted=False, reason="heldout_below_threshold")

    constraints_payload: dict = {}
    if safety_config is not None:
        try:
            spec_payload = json.loads(constraint_spec_path.read_text(encoding="utf-8"))
            canon_spec = canonicalize_constraint_spec(spec_payload)
            spec_hash = constraint_spec_hash(canon_spec)
        except Exception as exc:
            return PromotionResult(accepted=False, reason=f"constraints_spec_invalid: {exc}")
        safety_cfg = load_config_from_path(root_dir, safety_config)
        safety_episodes = _require_episodes(safety_cfg.data)
        safety_max_steps = int((safety_cfg.data.get("evaluator") or {}).get("step_limit", 100000))
        safety_request = {
            "kind": "stat_cert",
            "concept": concept,
            "metric": "accuracy",
            "null": "no_improvement",
            "baseline_symbol": baseline,
            "candidate_symbol": candidate.name,
            "eval": {
                "episodes": safety_episodes,
                "max_steps": safety_max_steps,
                "paired_seeds": True,
                "oracle_symbol": oracle,
            },
            "risk": {"evalue_threshold": "1"},
        }
        safety_request_path = out_dir / "safety_request.json"
        _write_json(safety_request_path, safety_request)
        safety_cert_path = out_dir / "safety_cert.json"
        try:
            client.issue_stat_cert(
                root_dir=root_dir,
                request_path=safety_request_path,
                out_path=safety_cert_path,
                config=safety_config,
                seed_key=seed_key,
                suites_dir=safety_suites_dir,
                candidate_module=candidate_path,
            )
        except Exception as exc:
            return PromotionResult(accepted=False, reason=f"safety_issue_failed: {exc}")
        safety_cert = json.loads(safety_cert_path.read_text(encoding="utf-8"))
        if not _passes_threshold(safety_cert):
            return PromotionResult(accepted=False, reason="safety_below_threshold")
        constraints_payload = {
            "spec": canon_spec,
            "spec_hash": spec_hash,
            "safety_certificate": safety_cert,
        }

    module = _assemble_module(root_dir, candidate.payload, cert, baseline, oracle)
    module_path = out_dir / "module.json"
    _write_json(module_path, module)

    try:
        module_hash = client.commit_module(root_dir=root_dir, module_path=module_path, config=heldout_config)
    except Exception as exc:
        return PromotionResult(accepted=False, reason=f"commit_failed: {exc}")

    adoption_path = out_dir / "adoption.json"
    adoption = _assemble_adoption(root_dir, concept, candidate.name, baseline, cert, constraints_payload)
    _write_json(adoption_path, adoption)
    try:
        adoption_hash = client.adopt(root_dir=root_dir, adoption_path=adoption_path, config=heldout_config)
    except Exception as exc:
        return PromotionResult(accepted=False, reason=f"adopt_failed: {exc}")

    return PromotionResult(accepted=True, reason="accepted", module_hash=module_hash, adoption_hash=adoption_hash)


def promote_candidate(
    *,
    client: CDELClient,
    root_dir: Path,
    concept: str,
    baseline: str,
    oracle: str,
    candidate: Candidate,
    dev_config: Path,
    heldout_config: Path,
    heldout_suites_dir: Path | None,
    safety_config: Path | None,
    safety_suites_dir: Path | None,
    constraint_spec_path: Path | None,
    seed_key: str,
    min_dev_diff_sum: int,
    out_dir: Path,
) -> PromotionResult:
    if heldout_suites_dir is None or not heldout_suites_dir.exists():
        return PromotionResult(accepted=False, reason="heldout_suites_missing")
    dev_eval, counterexamples, candidate_path = evaluate_candidate_dev(
        root_dir=root_dir,
        baseline=baseline,
        oracle=oracle,
        candidate=candidate,
        dev_config=dev_config,
        seed_key=seed_key,
        min_dev_diff_sum=min_dev_diff_sum,
        out_dir=out_dir,
        max_counterexamples=3,
    )
    if not dev_eval.passes_min_dev_diff_sum:
        return PromotionResult(
            accepted=False,
            reason="dev_gate_failed",
            dev_eval=dev_eval,
            counterexamples=counterexamples,
        )

    result = promote_candidate_heldout(
        client=client,
        root_dir=root_dir,
        concept=concept,
        baseline=baseline,
        oracle=oracle,
        candidate=candidate,
        candidate_path=candidate_path,
        heldout_config=heldout_config,
        heldout_suites_dir=heldout_suites_dir,
        safety_config=safety_config,
        safety_suites_dir=safety_suites_dir,
        constraint_spec_path=constraint_spec_path,
        seed_key=seed_key,
        out_dir=out_dir,
    )
    return PromotionResult(
        accepted=result.accepted,
        reason=result.reason,
        module_hash=result.module_hash,
        adoption_hash=result.adoption_hash,
        dev_eval=dev_eval,
        counterexamples=counterexamples,
    )


def _require_episodes(data: dict) -> int:
    sealed = data.get("sealed") or {}
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError("sealed.episodes must be positive int")
    return episodes


def _passes_threshold(cert: dict) -> bool:
    risk = cert.get("risk") or {}
    alpha_i = parse_decimal(str(risk.get("alpha_i")))
    threshold = parse_decimal(str(risk.get("evalue_threshold")))
    payload = cert.get("certificate") or {}
    evalue = parse_evalue(payload.get("evalue"), "heldout evalue")
    return encoded_evalue_to_decimal(evalue) * alpha_i >= threshold


def _assemble_module(root_dir: Path, payload: dict, cert: dict, baseline: str, oracle: str) -> dict:
    parent = (root_dir / "ledger" / "head").read_text(encoding="utf-8").strip()
    specs = list(payload.get("specs") or [])
    specs.append(cert)
    declared_deps = list(payload.get("declared_deps") or [])
    for name in (baseline, oracle):
        if name not in declared_deps:
            declared_deps.append(name)
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            **payload,
            "declared_deps": declared_deps,
            "specs": specs,
        },
    }


def _assemble_adoption(
    root_dir: Path,
    concept: str,
    candidate: str,
    baseline: str,
    cert: dict,
    constraints: dict,
) -> dict:
    head_path = root_dir / "adoption" / "head"
    parent = head_path.read_text(encoding="utf-8").strip()
    baseline_symbol = None
    if parent and parent != "GENESIS":
        baseline_symbol = baseline
    return {
        "schema_version": 1,
        "parent": parent,
        "payload": {
            "concept": concept,
            "chosen_symbol": candidate,
            "baseline_symbol": baseline_symbol,
            "certificate": cert,
            "constraints": constraints,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
