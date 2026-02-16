from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Dict, List

from genesis.core.library import Library, Primitive, primitive_id


def _load_archive(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def update_library(archive_path: Path, library: Library, min_count: int) -> bool:
    records = _load_archive(archive_path)
    groups: Dict[str, List[dict]] = defaultdict(list)
    for rec in records:
        if rec.get("status") != "shadow_pass":
            continue
        if int(rec.get("repair_depth", 0)) <= 0:
            continue
        sig = rec.get("descriptor", {}).get("operator_history_sig")
        if not sig:
            continue
        groups[sig].append(rec)

    updated = False
    for sig in sorted(groups.keys()):
        group = groups[sig]
        if len(group) < min_count:
            continue
        targets = [item.get("metric_target") for item in group if isinstance(item.get("metric_target"), (int, float))]
        if not targets:
            continue
        direction = next(
            (item.get("metric_direction") for item in group if item.get("metric_direction")), "maximize"
        )
        prim_id = primitive_id(sig, direction)
        if library.has(prim_id):
            continue
        prim = Primitive(
            primitive_id=prim_id,
            operator_signature=sig,
            metric_target=float(median(targets)),
            metric_direction=direction,
            provenance=sorted({item.get("capsule_hash", "") for item in group if item.get("capsule_hash")})[:5],
        )
        if library.add(prim):
            updated = True

    return updated
