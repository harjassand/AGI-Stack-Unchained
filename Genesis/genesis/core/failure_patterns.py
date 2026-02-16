from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple


def operator_signature(operators: List[str]) -> str:
    op_history = ">".join(operators)
    if not op_history:
        return "none"
    return hashlib.sha256(op_history.encode("utf-8")).hexdigest()[:12]


def env_bucket(env_id: str | None) -> str:
    if not env_id:
        return "env_unknown"
    return str(env_id)[:12]


def trace_prefix(trace_hash: str | None) -> str:
    if not trace_hash:
        return "none"
    return str(trace_hash)[:8]


@dataclass
class FailurePattern:
    pattern_id: str
    failure_class: str
    env_bucket: str
    operator_signature: str
    trace_hash_prefix: str
    count: int


class FailurePatternStore:
    def __init__(self) -> None:
        self._patterns: Dict[Tuple[str, str, str, str], FailurePattern] = {}
        self._order: List[Tuple[str, str, str, str]] = []

    def add(
        self,
        failure_class: str,
        env_id: str | None,
        operator_sig: str,
        trace_hash: str | None,
    ) -> str:
        key = (failure_class, env_bucket(env_id), operator_sig, trace_prefix(trace_hash))
        if key not in self._patterns:
            pattern_id = f"fp-{len(self._order) + 1:04d}"
            self._patterns[key] = FailurePattern(
                pattern_id=pattern_id,
                failure_class=failure_class,
                env_bucket=key[1],
                operator_signature=operator_sig,
                trace_hash_prefix=key[3],
                count=0,
            )
            self._order.append(key)
        pattern = self._patterns[key]
        pattern.count += 1
        return pattern.pattern_id

    def penalty_for_signature(self, operator_sig: str) -> int:
        return sum(
            pattern.count
            for pattern in self._patterns.values()
            if pattern.operator_signature == operator_sig
        )

    def choose_operator(self, rng, choices: List[str]) -> str:
        if not choices:
            raise ValueError("no operator choices provided")
        scored = []
        for choice in choices:
            sig = operator_signature([choice])
            scored.append((self.penalty_for_signature(sig), choice))
        min_penalty = min(score for score, _ in scored)
        candidates = sorted(choice for score, choice in scored if score == min_penalty)
        if len(candidates) == 1:
            return candidates[0]
        return rng.choice(candidates)

    def top_k(self, k: int) -> List[dict]:
        if k <= 0:
            return []
        patterns = sorted(
            self._patterns.values(),
            key=lambda item: (-item.count, item.pattern_id),
        )
        return [
            {
                "pattern_id": pattern.pattern_id,
                "failure_class": pattern.failure_class,
                "env_bucket": pattern.env_bucket,
                "operator_signature": pattern.operator_signature,
                "trace_hash_prefix": pattern.trace_hash_prefix,
                "count": pattern.count,
            }
            for pattern in patterns[:k]
        ]
