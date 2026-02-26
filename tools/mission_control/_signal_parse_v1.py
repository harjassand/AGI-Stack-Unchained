from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ParsedSignalLine:
    signal: str
    tick_u64: int
    raw_line: str
    fields: Dict[str, str]


_VERIFICATION_EXACT = {"CCAP_DECISION", "CCAP_REFUTATION", "REPLAY_VERDICT"}
_VERIFICATION_PREFIX = ("PROOF_",)

_EXECUTION_EXACT = {"REWRITE_ATTEMPT", "RUST_BUILD", "DISPATCH"}
_EXECUTION_PREFIX = ("CAMPAIGN_", "NATIVE_")

_REASONING_EXACT = {"VOID_SCORE", "PATCH_GEN"}
_REASONING_PREFIX = ("POLYMATH_", "LLM_")

_GOVERNANCE_EXACT = {
    "RUNAWAY_ACTIVE",
    "ACTIVATION_COMMIT",
    "REWRITE_COMMIT",
    "TIER_STATUS",
    "HEARTBEAT",
}


def parse_signal_line(raw_line: str) -> Optional[ParsedSignalLine]:
    line = raw_line.rstrip("\n")
    if "SIGNAL=" not in line:
        return None

    fields: Dict[str, str] = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value

    signal = fields.get("SIGNAL", "")
    tick_raw = fields.get("TICK", fields.get("tick_u64", "0"))
    try:
        tick_u64 = int(tick_raw)
    except (TypeError, ValueError):
        tick_u64 = 0

    return ParsedSignalLine(
        signal=signal,
        tick_u64=tick_u64,
        raw_line=line,
        fields=fields,
    )


def map_trace_class(signal: str) -> str:
    if signal in _VERIFICATION_EXACT or signal.startswith(_VERIFICATION_PREFIX):
        return "VERIFICATION"
    if signal in _EXECUTION_EXACT or signal.startswith(_EXECUTION_PREFIX):
        return "EXECUTION"
    if signal in _REASONING_EXACT or signal.startswith(_REASONING_PREFIX):
        return "REASONING"
    if signal in _GOVERNANCE_EXACT:
        return "GOVERNANCE"
    return "GOVERNANCE"
