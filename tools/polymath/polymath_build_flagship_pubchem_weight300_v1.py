#!/usr/bin/env python3
"""Build deterministic L0/L1/L2 pubchem_weight300 domain packs and sealed corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema
from tools.polymath.polymath_dataset_fetch_v1 import polymath_store_root, record_domain_artifact, seal_bytes_with_receipt

_DOMAIN_ID = "pubchem_weight300"
_DOMAIN_NAME = "PubChem Weight >= 300"
_TASK_ID = "task_mw_ge_300_binary_v1"
_LEVEL_SIZES: dict[str, int] = {
    "l0": 64,
    "l1": 160,
    "l2": 240,
}


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("fixture must be a list")
    out: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        cid = int(row.get("cid", 0))
        smiles = str(row.get("smiles", "")).strip()
        mw = float(row.get("mw", 0.0))
        if cid <= 0 or not smiles:
            continue
        target = 1 if float(mw) >= 300.0 else 0
        out.append(
            {
                "cid": cid,
                "id": f"cid:{cid}",
                "input": {"smiles": smiles},
                "mw": float(mw),
                "target": int(target),
            }
        )
    if not out:
        raise RuntimeError("fixture is empty")
    return out


def _deterministic_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(row: dict[str, Any]) -> tuple[str, int]:
        token = f"{int(row['cid'])}|{row['input']['smiles']}|{float(row['mw']):.6f}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest(), int(row["cid"])

    return sorted(rows, key=_key)


def _split_train_test(rows: list[dict[str, Any]], *, train_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_class: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    for row in rows:
        label = 1 if int(row.get("target", 0)) > 0 else 0
        by_class[label].append(row)

    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for label in (0, 1):
        class_rows = sorted(by_class[label], key=lambda row: int(row["cid"]))
        if not class_rows:
            raise RuntimeError(f"missing class label={label}")
        split = int(len(class_rows) * train_ratio)
        split = max(1, min(len(class_rows) - 1, split))
        train.extend(class_rows[:split])
        test.extend(class_rows[split:])

    train.sort(key=lambda row: int(row["cid"]))
    test.sort(key=lambda row: int(row["cid"]))
    return train, test


def _encode_rows(rows: list[dict[str, Any]]) -> bytes:
    compact = [
        {
            "id": str(row["id"]),
            "input": {"smiles": str((row.get("input") or {}).get("smiles", ""))},
            "target": int(row["target"]),
        }
        for row in rows
    ]
    return json.dumps(compact, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal_rows(*, rows: list[dict[str, Any]], store_root: Path, source_url: str) -> dict[str, str]:
    sealed = seal_bytes_with_receipt(
        data=_encode_rows(rows),
        source_url=source_url,
        store_root=store_root,
        content_type="application/json",
    )
    receipt_payload = load_canon_dict(Path(str(sealed["receipt_path"])))
    return {
        "sha256": str(sealed["sha256"]),
        "receipt_sha256": canon_hash_obj(receipt_payload),
    }


def _domain_pack_payload(
    *,
    level: str,
    full_sealed: dict[str, str],
    train_sealed: dict[str, str],
    test_sealed: dict[str, str],
) -> dict[str, Any]:
    payload = {
        "schema_version": "polymath_domain_pack_v1",
        "domain_id": _DOMAIN_ID,
        "domain_name": _DOMAIN_NAME,
        "topic_ids": ["topic:chemistry", "topic:pubchem"],
        "dataset_artifacts": [
            {
                "sha256": str(full_sealed["sha256"]),
                "kind": f"pubchem_weight300_{level}_snapshot",
                "license": "CC0-1.0",
                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "provenance": [
                    {
                        "url": f"fixture://tools/polymath/fixtures/pubchem_weight300_snapshot_v1.json#{level}",
                        "receipt_sha256": str(full_sealed["receipt_sha256"]),
                    }
                ],
            }
        ],
        "tasks": [
            {
                "task_id": _TASK_ID,
                "task_type": "classification",
                "input_schema_ref": "schemas/input_v1.jsonschema",
                "target_schema_ref": "schemas/target_v1.jsonschema",
                "metric": "accuracy",
                "split": {
                    "train_sha256": str(train_sealed["sha256"]),
                    "test_sha256": str(test_sealed["sha256"]),
                },
            }
        ],
        "metamorphic_tests": [
            {
                "test_id": "schema_round_trip_v1",
                "task_id": _TASK_ID,
                "template": "schema_round_trip",
            },
            {
                "test_id": "permutation_invariance_v1",
                "task_id": _TASK_ID,
                "template": "permutation_invariance",
            },
        ],
        "oracles": [
            {
                "oracle_name": "fixture_pubchem_weight300_snapshot_v1",
                "adapter_version": "polymath_build_flagship_pubchem_weight300_v1",
                "response_sha256": [str(full_sealed["sha256"])],
            }
        ],
    }
    validate_schema(payload, "polymath_domain_pack_v1")
    return payload


def build_flagship(*, fixture_path: Path, domain_root: Path, store_root: Path) -> dict[str, Any]:
    all_rows = _deterministic_order(_load_fixture(fixture_path))
    if len(all_rows) < max(_LEVEL_SIZES.values()):
        raise RuntimeError("fixture too small for L2 corpus")

    summary: dict[str, Any] = {
        "domain_id": _DOMAIN_ID,
        "store_root": store_root.as_posix(),
        "levels": {},
    }

    for level in ("l0", "l1", "l2"):
        size = int(_LEVEL_SIZES[level])
        selected = all_rows[:size]
        train_rows, test_rows = _split_train_test(selected, train_ratio=0.8)

        full_sealed = _seal_rows(
            rows=selected,
            store_root=store_root,
            source_url=f"fixture://pubchem_weight300/{level}/full",
        )
        train_sealed = _seal_rows(
            rows=train_rows,
            store_root=store_root,
            source_url=f"fixture://pubchem_weight300/{level}/train",
        )
        test_sealed = _seal_rows(
            rows=test_rows,
            store_root=store_root,
            source_url=f"fixture://pubchem_weight300/{level}/test",
        )

        for kind, sealed in (
            (f"{level}_dataset_full", full_sealed),
            (f"{level}_dataset_train", train_sealed),
            (f"{level}_dataset_test", test_sealed),
        ):
            record_domain_artifact(
                domain_id=_DOMAIN_ID,
                artifact_kind=kind,
                sha256=str(sealed["sha256"]),
                store_root=store_root,
            )

        pack_payload = _domain_pack_payload(
            level=level,
            full_sealed=full_sealed,
            train_sealed=train_sealed,
            test_sealed=test_sealed,
        )
        pack_path = domain_root / f"domain_pack_{level}_v1.json"
        write_canon_json(pack_path, pack_payload)
        summary["levels"][level] = {
            "rows_u64": int(len(selected)),
            "train_rows_u64": int(len(train_rows)),
            "test_rows_u64": int(len(test_rows)),
            "domain_pack_path": pack_path.as_posix(),
            "dataset_sha256": str(full_sealed["sha256"]),
            "train_sha256": str(train_sealed["sha256"]),
            "test_sha256": str(test_sealed["sha256"]),
        }

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_build_flagship_pubchem_weight300_v1")
    parser.add_argument(
        "--fixture_path",
        default=str(_REPO_ROOT / "tools" / "polymath" / "fixtures" / "pubchem_weight300_snapshot_v1.json"),
    )
    parser.add_argument(
        "--domain_root",
        default=str(_REPO_ROOT / "domains" / _DOMAIN_ID),
    )
    parser.add_argument("--store_root", default="")
    args = parser.parse_args()

    fixture_path = Path(args.fixture_path).resolve()
    domain_root = Path(args.domain_root).resolve()
    store_arg = Path(args.store_root).expanduser().resolve() if str(args.store_root).strip() else None
    store_root = polymath_store_root(store_arg)

    if not fixture_path.exists() or not fixture_path.is_file():
        raise FileNotFoundError(f"missing fixture: {fixture_path}")
    domain_root.mkdir(parents=True, exist_ok=True)

    summary = build_flagship(
        fixture_path=fixture_path,
        domain_root=domain_root,
        store_root=store_root,
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
