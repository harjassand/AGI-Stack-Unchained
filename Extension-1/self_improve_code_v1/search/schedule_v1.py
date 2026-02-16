"""Deterministic search schedule (v1)."""

from __future__ import annotations

import itertools
from typing import Dict, List, Tuple

from ..canon.hash_v1 import sha256_hex
from .learner_v1 import score_edit_set


def _fingerprint(baseline_commit: str, eval_plan_id: str, arm_ids: List[str], value_choices: List[str]) -> str:
    parts = [baseline_commit, "\x00", eval_plan_id, "\x00", "\x00".join(arm_ids), "\x00", "\x00".join(value_choices)]
    data = "".join(parts).encode("utf-8")
    return sha256_hex(data)


def schedule_candidates(
    arms: List[Dict],
    state: Dict,
    baseline_commit: str,
    eval_plan_id: str,
    cfg: Dict,
) -> List[Dict]:
    bonus0 = int(cfg.get("bonus0", 0))
    beta = int(cfg.get("beta", 0))
    max_k = int(cfg.get("max_edit_set_size", 1))
    budget = int(cfg.get("budget_candidates", 0))

    arms_sorted = sorted(arms, key=lambda a: a["arm_id"])
    candidates: List[Dict] = []

    for k in range(1, max_k + 1):
        for combo in itertools.combinations(arms_sorted, k):
            arm_ids = [a["arm_id"] for a in combo]
            base_score = score_edit_set(arm_ids, state, bonus0, beta)
            value_sets = [sorted(a["value_set"]) for a in combo]
            for value_choice in itertools.product(*value_sets):
                value_choices = list(value_choice)
                fp = _fingerprint(baseline_commit, eval_plan_id, arm_ids, value_choices)
                candidates.append(
                    {
                        "arm_ids": arm_ids,
                        "value_choices": value_choices,
                        "score": base_score,
                        "fingerprint": fp,
                    }
                )

    # Dedup by fingerprint deterministically.
    seen = set()
    deduped: List[Dict] = []
    for c in candidates:
        if c["fingerprint"] in seen:
            continue
        seen.add(c["fingerprint"])
        deduped.append(c)

    deduped.sort(key=lambda c: (-int(c["score"]), c["fingerprint"]))
    if budget > 0:
        deduped = deduped[:budget]
    return deduped


__all__ = ["schedule_candidates"]
