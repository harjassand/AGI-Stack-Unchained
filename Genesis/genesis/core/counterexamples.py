from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple


def _stable_hash(value: Any) -> str:
    try:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        payload = json.dumps(str(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Counterexample:
    counterexample_id: str
    test_name: str
    input_hash: str
    failure_class: str
    capsule_hash: str
    input_value: Any


class CounterexampleDB:
    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, str, str], Counterexample] = {}
        self._order: list[Tuple[str, str, str]] = []

    def add(
        self,
        test_name: str,
        input_value: Any,
        failure_class: str,
        capsule_hash: str,
    ) -> Counterexample:
        input_hash = _stable_hash(input_value)
        key = (test_name, input_hash, failure_class)
        if key not in self._entries:
            counterexample_id = _stable_hash({"test": test_name, "input": input_hash, "class": failure_class})
            entry = Counterexample(
                counterexample_id=counterexample_id,
                test_name=test_name,
                input_hash=input_hash,
                failure_class=failure_class,
                capsule_hash=capsule_hash,
                input_value=input_value,
            )
            self._entries[key] = entry
            self._order.append(key)
        return self._entries[key]

    def latest(self) -> Counterexample | None:
        if not self._order:
            return None
        return self._entries[self._order[-1]]

    def size(self) -> int:
        return len(self._entries)

    def entries(self) -> list[Counterexample]:
        return [self._entries[key] for key in self._order]
