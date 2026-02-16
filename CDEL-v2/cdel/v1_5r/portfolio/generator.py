"""Deterministic portfolio generator for v1.5r."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canon import canon_bytes, hash_json, sha256_prefixed, write_canon_json, write_jsonl_line
from ..ctime.macro import compute_rent_bits
from ..family_dsl.runtime import compute_family_id, compute_signature


@dataclass(frozen=True)
class PortfolioSpec:
    portfolio_id: str
    seed_label: str
    families: int
    repeats_per_family: int
    motif_action_names: list[str]


def _suite_row_from_seed(seed: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(seed).digest()
    x = digest[0] % 4
    y = digest[1] % 4
    gx = (x + 1) % 4
    gy = (y + 1) % 4
    return {
        "env": "gridworld-v1",
        "start": {"x": x, "y": y},
        "goal": {"x": gx, "y": gy},
        "walls": [],
        "max_steps": 6,
    }


def _family_for_row(row: dict[str, Any], motif: list[str]) -> dict[str, Any]:
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "family_id": "",
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 16,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {
            "op": "CONST",
            "value": {
                "suite_row": row,
                "motif_action_names": motif,
            },
        },
        "signature": {},
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _write_suitepack_manifest(path: Path, suite_hashes: list[str], families: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = {
        "schema": "suitepack_v1_5r",
        "schema_version": 1,
        "suitepack_id": "",
        "suite_hashes": suite_hashes,
        "families": [
            {"family_id": fam["family_id"], "family_hash": hash_json(fam)} for fam in families
        ],
    }
    manifest["suitepack_id"] = hash_json(manifest)
    write_canon_json(path, manifest)
    return manifest


def _emit_suite_rows(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    hashes: list[str] = []
    for row in rows:
        line_path = path / f"{sha256_prefixed(canon_bytes(row))}.jsonl"
        if not line_path.exists():
            write_jsonl_line(line_path, row)
        hashes.append(sha256_prefixed(line_path.read_bytes()))
    return hashes


def _macro_preflight(motif: list[str], repeats_total: int) -> dict[str, Any]:
    required_by_length: dict[str, int] = {}
    rent_bits_by_length: dict[str, int] = {}
    for length in range(6, 13):
        body = [{"name": motif[i % len(motif)], "args": {}} for i in range(length)]
        macro_def = {
            "schema": "macro_def_v1",
            "schema_version": 1,
            "macro_id": "",
            "body": body,
            "guard": None,
            "admission_epoch": 0,
            "rent_bits": 0,
        }
        rent_bits = compute_rent_bits(macro_def)
        gain_per_occ = 8 * (length - 1)
        required = (rent_bits + 32 + gain_per_occ - 1) // gain_per_occ
        required = max(required, 10)
        required_by_length[str(length)] = required
        rent_bits_by_length[str(length)] = rent_bits
    required_max = max(required_by_length.values()) if required_by_length else 0
    return {
        "schema": "portfolio_economics_preflight_v1",
        "schema_version": 1,
        "motif_length": len(motif),
        "required_occurrences_by_length": required_by_length,
        "rent_bits_by_length": rent_bits_by_length,
        "required_occurrences_max": required_max,
        "planned_occurrences": repeats_total,
        "meets_requirement": repeats_total >= required_max,
    }


def build_portfolio(spec: PortfolioSpec, out_root: Path) -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    suite_rows: list[dict[str, Any]] = []
    for idx in range(spec.families):
        seed = f"{spec.seed_label}:{spec.portfolio_id}:{idx}".encode("utf-8")
        row = _suite_row_from_seed(seed)
        family = _family_for_row(row, spec.motif_action_names)
        families.append(family)
        for _ in range(spec.repeats_per_family):
            suite_rows.append(row)

    families_dir = out_root / "families"
    families_dir.mkdir(parents=True, exist_ok=True)
    for idx, family in enumerate(families):
        write_canon_json(families_dir / f"family_{idx}.json", family)

    dev_dir = out_root / "suitepacks" / "dev"
    heldout_dir = out_root / "suitepacks" / "heldout"
    dev_dir.mkdir(parents=True, exist_ok=True)
    heldout_dir.mkdir(parents=True, exist_ok=True)

    dev_hashes = _emit_suite_rows(dev_dir, suite_rows)
    heldout_hashes = _emit_suite_rows(heldout_dir, suite_rows)

    dev_manifest = _write_suitepack_manifest(dev_dir / "suitepack.json", dev_hashes, families)
    heldout_manifest = _write_suitepack_manifest(heldout_dir / "suitepack.json", heldout_hashes, families)

    preflight = _macro_preflight(spec.motif_action_names, len(suite_rows))
    write_canon_json(out_root / "portfolio_economics_preflight_v1.json", preflight)

    manifest = {
        "schema": "portfolio_manifest_v1",
        "schema_version": 1,
        "portfolio_id": hash_json({"portfolio_id": spec.portfolio_id, "seed": spec.seed_label}),
        "generator_id": spec.seed_label,
        "suitepacks": {
            "dev_hash": hash_json(dev_manifest),
            "heldout_hash": hash_json(heldout_manifest),
        },
        "families": [
            {"family_id": fam["family_id"], "family_hash": hash_json(fam)} for fam in families
        ],
        "parameter_domains": {},
        "counts": {
            "dev_instances": len(dev_hashes),
            "heldout_instances": len(heldout_hashes),
        },
    }
    write_canon_json(out_root / "portfolio_manifest_v1.json", manifest)
    return manifest


def load_generator(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw


def build_from_generator(generator: dict[str, Any], out_root: Path) -> list[dict[str, Any]]:
    motif = generator.get("motif_action_names")
    if not isinstance(motif, list) or any(not isinstance(item, str) for item in motif):
        raise ValueError("generator motif_action_names must be list of strings")
    portfolios: list[dict[str, Any]] = []
    for entry in generator.get("portfolios", []):
        portfolio_id = entry.get("portfolio_id")
        seed_label = entry.get("seed_label")
        families = int(entry.get("families", 5))
        repeats = int(entry.get("repeats_per_family", 10))
        if not isinstance(portfolio_id, str) or not isinstance(seed_label, str):
            raise ValueError("portfolio_id/seed_label required")
        spec = PortfolioSpec(
            portfolio_id=portfolio_id,
            seed_label=seed_label,
            families=families,
            repeats_per_family=repeats,
            motif_action_names=motif,
        )
        portfolio_root = out_root / portfolio_id
        portfolio_root.mkdir(parents=True, exist_ok=True)
        manifest = build_portfolio(spec, portfolio_root)
        portfolios.append(manifest)
    return portfolios
