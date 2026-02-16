"""Deterministic proposer state and template selection (v1)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ...canon.hash_v1 import sha256_bytes
from ...canon.json_canon_v1 import canon_bytes
from .patch_templates_v1 import template_ids


@dataclass
class PCG32:
    state: int
    inc: int

    def next_uint32(self) -> int:
        oldstate = self.state
        self.state = (oldstate * 6364136223846793005 + self.inc) & 0xFFFFFFFFFFFFFFFF
        xorshifted = ((oldstate >> 18) ^ oldstate) >> 27
        rot = oldstate >> 59
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & 0xFFFFFFFF

    def randbelow(self, n: int) -> int:
        if n <= 0:
            return 0
        threshold = (-n) % n
        while True:
            r = self.next_uint32()
            if r >= threshold:
                return r % n

    def choice(self, items: List[str]) -> str:
        if not items:
            raise ValueError("empty choice list")
        idx = self.randbelow(len(items))
        return items[idx]


def derive_rng(seed: int, epoch: int, index: int) -> PCG32:
    payload = f"flagship_rng_v1\0{seed}\0{epoch}\0{index}".encode("utf-8")
    digest = sha256_bytes(payload)
    state = int.from_bytes(digest[:8], "big")
    inc = int.from_bytes(digest[8:16], "big") | 1
    return PCG32(state=state, inc=inc)


def init_state() -> Dict:
    stats = {}
    for tid in template_ids():
        stats[tid] = {
            "attempts": 0,
            "devscreen_passes": 0,
            "sealed_dev_passes": 0,
            "last_success_epoch": -1,
        }
    return {
        "version": "1",
        "template_stats": stats,
        "signature_to_templates": {},
        "improvement_events": [],
    }


def load_state(path: str) -> Dict:
    if not os.path.exists(path):
        return init_state()
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def save_state(path: str, state: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(canon_bytes(state))


def _ensure_template_stats(state: Dict) -> None:
    stats = state.setdefault("template_stats", {})
    for tid in template_ids():
        stats.setdefault(
            tid,
            {
                "attempts": 0,
                "devscreen_passes": 0,
                "sealed_dev_passes": 0,
                "last_success_epoch": -1,
            },
        )


def select_template(
    state: Dict,
    fail_signature: str,
    rng: PCG32,
    explore_fraction: Tuple[int, int],
) -> Tuple[str, str]:
    _ensure_template_stats(state)
    sig_map = state.get("signature_to_templates", {}) or {}
    pref = list(sig_map.get(fail_signature, []))
    templates = template_ids()
    explore_num, explore_den = explore_fraction
    explore_pick = rng.randbelow(explore_den) < explore_num if explore_den > 0 else False
    if not explore_pick:
        for tid in pref:
            if tid in templates:
                return tid, "exploit"
    return rng.choice(templates), "explore"


def update_state(
    state: Dict,
    epoch: int,
    candidates: List[Dict],
    *,
    baseline_failed: bool,
    tier_name: str,
) -> None:
    _ensure_template_stats(state)
    sig_map = state.setdefault("signature_to_templates", {})
    improvement_events = state.setdefault("improvement_events", [])
    for cand in candidates:
        tid = cand.get("template_id", "")
        if tid not in state["template_stats"]:
            continue
        stats = state["template_stats"][tid]
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if cand.get("devscreen_ok"):
            stats["devscreen_passes"] = int(stats.get("devscreen_passes", 0)) + 1
        real_credit = bool(
            cand.get("sealed_dev_pass")
            and baseline_failed
            and not cand.get("semantic_noop")
        )
        if real_credit:
            stats["sealed_dev_passes"] = int(stats.get("sealed_dev_passes", 0)) + 1
            stats["last_success_epoch"] = int(epoch)
            failsig = cand.get("fail_signature", "")
            if failsig:
                ordered = list(sig_map.get(failsig, []))
                if tid in ordered:
                    ordered.remove(tid)
                ordered.insert(0, tid)
                sig_map[failsig] = ordered
            improvement_events.append(
                {
                    "epoch": int(epoch),
                    "failsig": str(failsig),
                    "template_id": str(tid),
                    "tier": str(tier_name),
                    "candidate_id": str(cand.get("candidate_id", "")),
                }
            )


__all__ = [
    "PCG32",
    "derive_rng",
    "init_state",
    "load_state",
    "save_state",
    "select_template",
    "update_state",
]
