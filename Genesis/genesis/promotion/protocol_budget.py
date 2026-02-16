from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple


@dataclass(frozen=True)
class ProtocolCaps:
    max_promotions: int
    max_cdel_calls: int
    max_dp_queries: int
    max_stat_queries: int
    max_robust_queries: int

    @classmethod
    def from_config(cls, config: Dict) -> "ProtocolCaps":
        caps = config.get("protocol_caps") or {}
        return cls(
            max_promotions=int(caps.get("max_promotions", 0)),
            max_cdel_calls=int(caps.get("max_cdel_calls", config.get("max_cdel_calls_per_epoch", 0))),
            max_dp_queries=int(caps.get("max_dp_queries", 0)),
            max_stat_queries=int(caps.get("max_stat_queries", 0)),
            max_robust_queries=int(caps.get("max_robust_queries", 0)),
        )


@dataclass(frozen=True)
class ProtocolRequest:
    cdel_calls: int
    dp_queries: int
    stat_queries: int
    robust_queries: int


def load_state(path: Path) -> Dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"epochs": {}}


def save_state(path: Path, state: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _get_epoch(state: Dict, epoch_id: str) -> Dict:
    epochs = state.setdefault("epochs", {})
    return epochs.setdefault(epoch_id, {})


def record_attempt(state: Dict, epoch_id: str) -> int:
    epoch = _get_epoch(state, epoch_id)
    epoch["attempt_index"] = int(epoch.get("attempt_index", 0)) + 1
    return int(epoch["attempt_index"])


def is_descriptor_novel(state: Dict, epoch_id: str, signature: str | None) -> bool:
    if not signature:
        return True
    epoch = _get_epoch(state, epoch_id)
    seen = set(epoch.get("seen_descriptors", []))
    return signature not in seen


def mark_descriptor(state: Dict, epoch_id: str, signature: str | None) -> None:
    if not signature:
        return
    epoch = _get_epoch(state, epoch_id)
    seen = list(epoch.get("seen_descriptors", []))
    if signature not in seen:
        seen.append(signature)
    epoch["seen_descriptors"] = seen


def snapshot(state: Dict, epoch_id: str) -> Dict[str, int]:
    epoch = _get_epoch(state, epoch_id)
    return {
        "promotions": int(epoch.get("promotions", 0)),
        "cdel_calls": int(epoch.get("cdel_calls", 0)),
        "dp_queries": int(epoch.get("dp_queries", 0)),
        "stat_queries": int(epoch.get("stat_queries", 0)),
        "robust_queries": int(epoch.get("robust_queries", 0)),
        "attempt_index": int(epoch.get("attempt_index", 0)),
    }


def check_caps(state: Dict, epoch_id: str, caps: ProtocolCaps, request: ProtocolRequest) -> Tuple[bool, str | None]:
    epoch = _get_epoch(state, epoch_id)
    promotions = int(epoch.get("promotions", 0))
    cdel_calls = int(epoch.get("cdel_calls", 0))
    dp_queries = int(epoch.get("dp_queries", 0))
    stat_queries = int(epoch.get("stat_queries", 0))
    robust_queries = int(epoch.get("robust_queries", 0))

    if caps.max_promotions > 0 and promotions >= caps.max_promotions:
        return False, "protocol_cap:promotions"
    if caps.max_cdel_calls > 0 and cdel_calls + request.cdel_calls > caps.max_cdel_calls:
        return False, "protocol_cap:cdel_calls"
    if caps.max_dp_queries > 0 and dp_queries + request.dp_queries > caps.max_dp_queries:
        return False, "protocol_cap:dp_queries"
    if caps.max_stat_queries > 0 and stat_queries + request.stat_queries > caps.max_stat_queries:
        return False, "protocol_cap:stat_queries"
    if caps.max_robust_queries > 0 and robust_queries + request.robust_queries > caps.max_robust_queries:
        return False, "protocol_cap:robust_queries"
    return True, None


def apply_request(state: Dict, epoch_id: str, request: ProtocolRequest) -> None:
    epoch = _get_epoch(state, epoch_id)
    epoch["cdel_calls"] = int(epoch.get("cdel_calls", 0)) + int(request.cdel_calls)
    epoch["dp_queries"] = int(epoch.get("dp_queries", 0)) + int(request.dp_queries)
    epoch["stat_queries"] = int(epoch.get("stat_queries", 0)) + int(request.stat_queries)
    epoch["robust_queries"] = int(epoch.get("robust_queries", 0)) + int(request.robust_queries)


def apply_promotion(state: Dict, epoch_id: str) -> None:
    epoch = _get_epoch(state, epoch_id)
    epoch["promotions"] = int(epoch.get("promotions", 0)) + 1
