#!/usr/bin/env python3
"""Redaction and leak guards for proposer training corpus generation (Step 3A)."""

from __future__ import annotations

import re
from typing import Iterable

Q32_ONE = 1 << 32
Q32_HALF = 1 << 31

FORBIDDEN_PATH_PREFIXES: tuple[str, ...] = (
    "authority/holdouts/",
    "authority/holdout_policies/",
    "authority/holdout_harness/",
    "authority/holdout_harnesses/",
    "authority/holdout_runner/",
    "authority/holdout_policy_harness/",
)

_HOLDOUT_TOKEN_RE = re.compile(r"HOLDOUT_[A-Z0-9_:-]*")
_HOLDOUT_REASON_RE = re.compile(r"holdout", re.IGNORECASE)

_TOXIC_REJECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"allowlist", re.IGNORECASE),
    re.compile(r"public[_:-]?only", re.IGNORECASE),
    re.compile(r"sandbox", re.IGNORECASE),
)

_UTILITY_FAIL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"utility[_:-]?fail", re.IGNORECASE),
    re.compile(r"score[_:-]?below[_:-]?gate", re.IGNORECASE),
    re.compile(r"no[_:-]?utility[_:-]?gain", re.IGNORECASE),
    re.compile(r"bench[_:-]?fail", re.IGNORECASE),
)


def normalize_relpath(path_value: object) -> str:
    text = str(path_value).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/"):
        text = text[1:]
    return text


def forbidden_path_hits(paths: Iterable[object]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        rel = normalize_relpath(path)
        if not rel:
            continue
        lower_rel = rel.lower()
        for prefix in FORBIDDEN_PATH_PREFIXES:
            if lower_rel.startswith(prefix.lower()):
                hits.append(rel)
                break
    return sorted(set(hits))


def redact_reason_code(reason_code: object) -> str:
    text = str(reason_code if reason_code is not None else "").strip()
    if not text:
        return "NONE"
    if _HOLDOUT_REASON_RE.search(text):
        return "HOLDOUT_FAIL"
    return text.upper()


def is_toxic_reject_reason(reason_code: object) -> bool:
    text = str(reason_code if reason_code is not None else "").strip()
    if not text:
        return False
    for pattern in _TOXIC_REJECT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def pair_weight_q32_for_reason(reason_code: object) -> int:
    text = str(reason_code if reason_code is not None else "").strip()
    if not text:
        return Q32_HALF
    for pattern in _UTILITY_FAIL_PATTERNS:
        if pattern.search(text):
            return Q32_ONE
    return Q32_HALF


def utility_class_from_fields(*, declared_class: object, effect_class: object) -> str:
    declared = str(declared_class if declared_class is not None else "").strip().upper()
    effect = str(effect_class if effect_class is not None else "").strip().upper()
    if "FRONTIER_HEAVY" in declared or "HEAVY" in effect:
        return "FRONTIER_HEAVY"
    if declared or effect:
        return "BASELINE"
    return "UNKNOWN"


def text_forbidden_hits(text: object) -> list[str]:
    body = str(text if text is not None else "")
    cleaned = body.replace("HOLDOUT_FAIL", "")
    hits: list[str] = []
    if "holdout" in cleaned.lower():
        hits.append("holdout")
    for match in _HOLDOUT_TOKEN_RE.finditer(body):
        token = match.group(0)
        if token != "HOLDOUT_FAIL":
            hits.append(token)
    return sorted(set(hits))


def redaction_policy_material_v1() -> dict[str, object]:
    return {
        "schema_version": "proposer_redaction_policy_v1",
        "forbidden_path_prefixes": list(FORBIDDEN_PATH_PREFIXES),
        "forbidden_substrings": ["holdout", "HOLDOUT_"],
        "holdout_reason_rewrite": "*holdout* -> HOLDOUT_FAIL",
        "allowed_holdout_token": "HOLDOUT_FAIL",
    }
