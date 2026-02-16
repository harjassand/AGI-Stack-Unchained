from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, List

from genesis.core.counterexamples import Counterexample


@dataclass
class ForagerTest:
    test_id: str
    input_value: Any


def _hash_input(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_tests(
    capsule: dict,
    counterexamples: list[Counterexample],
    seed: str,
    max_tests: int,
) -> list[ForagerTest]:
    if max_tests <= 0:
        return []
    resource_spec = capsule.get("contract", {}).get("resource_spec", {})
    max_sample = int(resource_spec.get("max_sample_count", 0))

    tests: list[ForagerTest] = []
    for i in range(min(max_tests, max(1, min(max_sample, 3)))):
        tests.append(ForagerTest(test_id=f"base-{i}", input_value=i))

    if counterexamples:
        for idx, ce in enumerate(counterexamples):
            if len(tests) >= max_tests:
                break
            value = max_sample + 1
            if isinstance(ce.input_value, (int, float)):
                value = int(ce.input_value) + 1
            elif isinstance(ce.input_value, dict) and "input" in ce.input_value:
                raw = ce.input_value.get("input")
                if isinstance(raw, (int, float)):
                    value = int(raw) + 1
            tests.append(ForagerTest(test_id=f"ce-{idx}", input_value=value))

    seen = set()
    deduped: list[ForagerTest] = []
    for test in tests:
        key = _hash_input(test.input_value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(test)
        if len(deduped) >= max_tests:
            break
    return deduped


def evaluate_tests(capsule: dict, tests: list[ForagerTest]) -> tuple[bool, ForagerTest | None]:
    resource_spec = capsule.get("contract", {}).get("resource_spec", {})
    max_sample = int(resource_spec.get("max_sample_count", 0))

    for test in tests:
        if isinstance(test.input_value, (int, float)) and test.input_value > max_sample:
            return False, test
    return True, None
