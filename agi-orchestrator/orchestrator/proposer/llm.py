"""LLM-based proposer with strict schema validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from orchestrator.llm_backend import LLMBackend
from orchestrator.context_pack import ContextPackLimits, build_context_pack_v1
from orchestrator.proposer.base import Proposer
from orchestrator.types import Candidate, ContextBundle
from orchestrator.validation import Limits, validate_candidate


@dataclass(frozen=True)
class ProposerLimits:
    max_new_symbols: int
    max_ast_nodes: int
    max_ast_depth: int = 20
    allow_primitives: list[str] | None = None


class LLMProposer(Proposer):
    def __init__(
        self,
        backend: LLMBackend,
        *,
        root_dir: Path,
        config_path: Path,
        limits: ProposerLimits | None = None,
        counterexamples: list[dict] | None = None,
    ) -> None:
        self.backend = backend
        self.root_dir = root_dir
        self.config_path = config_path
        self.limits = limits or ProposerLimits(max_new_symbols=1, max_ast_nodes=50)
        self.counterexamples = counterexamples or []

    def propose(self, *, context: ContextBundle, budget: int, rng_seed: int) -> list[Candidate]:
        if budget <= 0:
            return []
        prompt = _build_prompt(
            root_dir=self.root_dir,
            config_path=self.config_path,
            context=context,
            limits=self.limits,
            counterexamples=self.counterexamples,
            rng_seed=rng_seed,
        )
        result = _parse_with_retry(
            backend=self.backend,
            prompt=prompt,
            concept=context.concept,
            limits=self.limits,
            retries=2,
        )
        if result is None:
            return []
        candidate, meta = result
        return [Candidate(
            name=candidate.name,
            payload=candidate.payload,
            proposer=candidate.proposer,
            notes=candidate.notes,
            meta=meta,
        )]


def _build_prompt(
    *,
    root_dir: Path,
    config_path: Path,
    context: ContextBundle,
    limits: ProposerLimits,
    counterexamples: list[dict],
    rng_seed: int,
) -> str:
    pack = build_context_pack_v1(
        root_dir=root_dir,
        config_path=config_path,
        concept=context.concept,
        baseline_symbol=context.baseline_symbol,
        oracle_symbol=context.oracle_symbol,
        context_symbols=context.symbols,
        counterexamples=counterexamples,
        rng_seed=rng_seed,
        limits=ContextPackLimits(
            max_new_symbols=limits.max_new_symbols,
            max_ast_nodes=limits.max_ast_nodes,
            max_ast_depth=limits.max_ast_depth,
            allow_primitives=limits.allow_primitives,
        ),
    )
    return json.dumps(pack, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _parse_payload(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("payload"), dict):
        data = data["payload"]
    if not isinstance(data, dict):
        return None
    return data


def _parse_with_retry(
    *,
    backend: LLMBackend,
    prompt: str,
    concept: str,
    limits: ProposerLimits,
    retries: int,
) -> tuple[Candidate, dict] | None:
    last_error = ""
    for attempt in range(retries + 1):
        raw = backend.generate(prompt if attempt == 0 else _repair_prompt(prompt, last_error))
        payload = _parse_payload(raw)
        if payload is None:
            last_error = "invalid_json"
            continue
        try:
            validated = validate_candidate(
                payload,
                limits=Limits(
                    max_new_symbols=limits.max_new_symbols,
                    max_ast_nodes=limits.max_ast_nodes,
                    max_ast_depth=limits.max_ast_depth,
                ),
                allowlist=None,
            )
        except ValueError as exc:
            last_error = str(exc)
            continue
        meta = {
            "llm_parse_success": True,
            "llm_validation_success": True,
            "llm_retry_count": attempt,
            "llm_last_error": last_error[:500],
        }
        return Candidate(
            name=validated.name,
            payload=validated.payload,
            proposer="llm",
        ), meta
    meta = {
        "llm_parse_success": False,
        "llm_validation_success": False,
        "llm_retry_count": retries,
        "llm_last_error": last_error[:500],
    }
    return None if retries < 0 else None


def _repair_prompt(original: str, error: str) -> str:
    payload = {
        "prompt": original,
        "error": error[:500],
        "schema": _schema_summary(),
    }
    return json.dumps(payload, sort_keys=True)


def _schema_summary() -> dict:
    return {
        "required": ["new_symbols", "definitions", "concepts"],
        "definition_keys": ["name", "params", "ret_type", "body", "termination"],
    }
