"""Heldout rotation helpers for pyut suites."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3


@dataclass(frozen=True)
class HeldoutRotationResult:
    suite_hash: str
    suite_path: Path
    manifest_path: Path


def generate_heldout_candidate(
    *,
    pool_paths: list[Path],
    out_dir: Path,
    seed: int,
    target_size: int,
    stratify: bool = False,
) -> HeldoutRotationResult:
    rows = _load_pool(pool_paths)
    if not rows:
        raise ValueError("pool is empty")

    selection = _select_rows(rows, seed=seed, target_size=target_size, stratify=stratify)
    out_dir.mkdir(parents=True, exist_ok=True)
    suite_path = out_dir / "heldout_candidate.jsonl"
    suite_path.write_text(_encode_jsonl(selection), encoding="utf-8")
    suite_hash = blake3(suite_path.read_bytes()).hexdigest()
    final_path = out_dir / f"heldout_candidate_{suite_hash}.jsonl"
    suite_path.replace(final_path)

    manifest = {
        "seed": seed,
        "target_size": target_size,
        "stratify": stratify,
        "input_pool_hashes": _pool_hashes(pool_paths),
        "counts": _count_tags(selection),
    }
    manifest_path = out_dir / "heldout_rotation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    return HeldoutRotationResult(
        suite_hash=suite_hash,
        suite_path=final_path,
        manifest_path=manifest_path,
    )


def update_heldout_config_hash(*, config_path: Path, suite_hash: str) -> None:
    if not config_path.exists():
        raise ValueError(f"heldout config not found: {config_path}")
    lines = config_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    updated = False
    for line in lines:
        if line.strip().startswith("eval_suite_hash"):
            out.append(f'eval_suite_hash = "{suite_hash}"')
            updated = True
        else:
            out.append(line)
    if not updated:
        raise ValueError("eval_suite_hash not found in heldout config")
    config_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _load_pool(pool_paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in pool_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _select_rows(rows: list[dict], *, seed: int, target_size: int, stratify: bool) -> list[dict]:
    rng = _rng(seed)
    if not stratify:
        rng.shuffle(rows)
        return rows[:target_size]

    by_tag: dict[str, list[dict]] = {}
    for row in rows:
        tags = row.get("tags")
        if isinstance(tags, list) and tags:
            tag = str(tags[0])
        else:
            tag = "untagged"
        by_tag.setdefault(tag, []).append(row)

    for bucket in by_tag.values():
        rng.shuffle(bucket)

    buckets = list(by_tag.values())
    selection: list[dict] = []
    while buckets and len(selection) < target_size:
        next_buckets: list[list[dict]] = []
        for bucket in buckets:
            if len(selection) >= target_size:
                break
            if bucket:
                selection.append(bucket.pop())
            if bucket:
                next_buckets.append(bucket)
        buckets = next_buckets
    return selection


def _encode_jsonl(rows: list[dict]) -> str:
    return "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"


def _pool_hashes(paths: list[Path]) -> list[str]:
    hashes = []
    for path in paths:
        hashes.append(blake3(path.read_bytes()).hexdigest())
    return hashes


def _count_tags(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        tags = row.get("tags")
        if isinstance(tags, list) and tags:
            for tag in tags:
                counts[str(tag)] = counts.get(str(tag), 0) + 1
        else:
            counts["untagged"] = counts.get("untagged", 0) + 1
    return counts


def _rng(seed: int):
    import random

    return random.Random(seed)
