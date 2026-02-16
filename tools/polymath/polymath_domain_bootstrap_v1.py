#!/usr/bin/env python3
"""Domain bootstrap helpers for polymath v1."""

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
from cdel.v18_0.omega_common_v1 import canon_hash_obj, validate_schema
from tools.polymath.polymath_dataset_fetch_v1 import record_domain_artifact, seal_bytes_with_receipt


def normalize_domain_id(topic_name: str) -> str:
    out = []
    prev_sep = False
    for ch in str(topic_name).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    slug = "".join(out).strip("_")
    return slug or "domain_unknown"


def _synthetic_rows(domain_name: str, size: int = 24) -> list[dict[str, Any]]:
    seed = hashlib.sha256(str(domain_name).encode("utf-8")).hexdigest()[:8]
    rows: list[dict[str, Any]] = []
    for idx in range(max(8, int(size))):
        positive = idx % 3 == 0
        marker = "alpha" if positive else "beta"
        rows.append(
            {
                "id": f"{seed}_{idx:04d}",
                "input": {
                    "feature_x": int((idx * 7) % 11),
                    "text": f"{marker} sample {idx} {seed}",
                },
                "target": 1 if positive else 0,
            }
        )
    return rows


def _split_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = max(1, (len(rows) * 7) // 10)
    train = rows[:cutoff]
    test = rows[cutoff:]
    if not test:
        test = rows[-1:]
    return train, test


def _baseline_solver_source() -> str:
    return """#!/usr/bin/env python3
\"\"\"Deterministic baseline solver for polymath domain classification.\"\"\"

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def predict(rows: list[dict[str, Any]]) -> list[int]:
    labels = [int(row.get(\"target\", 0)) for row in rows]
    positives = sum(1 for value in labels if value == 1)
    negatives = len(labels) - positives
    majority = 1 if positives >= negatives else 0
    return [majority for _ in rows]


def main() -> None:
    parser = argparse.ArgumentParser(prog=\"baseline_solver_v1\")
    parser.add_argument(\"--dataset_path\", required=True)
    parser.add_argument(\"--out_path\", required=True)
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset_path).read_text(encoding=\"utf-8\"))
    if not isinstance(dataset, list):
        raise RuntimeError(\"dataset must be a list\")
    predictions = predict(dataset)
    Path(args.out_path).write_text(json.dumps({\"predictions\": predictions}, sort_keys=True, separators=(\",\",\":\")) + \"\\n\", encoding=\"utf-8\")


if __name__ == \"__main__\":
    main()
"""


def _write_domain_readme(domain_root: Path, domain_id: str, domain_name: str) -> None:
    text = "\n".join(
        [
            f"# {domain_name}",
            "",
            f"- Domain ID: `{domain_id}`",
            "- This domain pack was bootstrapped by polymath_domain_bootstrap_v1.",
            "- Datasets are sealed under `polymath/store/blobs/sha256/` and referenced by hash in `domain_pack_v1.json`.",
            "",
        ]
    )
    (domain_root / "README.md").write_text(text, encoding="utf-8")


def bootstrap_domain(
    *,
    domain_id: str,
    domain_name: str,
    topic_ids: list[str],
    domains_root: Path,
    store_root: Path,
    license_name: str = "CC0-1.0",
    license_url: str = "https://creativecommons.org/publicdomain/zero/1.0/",
    starter_size: int = 24,
) -> dict[str, Any]:
    domain_id = normalize_domain_id(domain_id)
    rows = _synthetic_rows(domain_name=domain_name, size=max(8, int(starter_size)))
    train_rows, test_rows = _split_rows(rows)

    full_sealed = seal_bytes_with_receipt(
        data=json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        source_url=f"synthetic://{domain_id}/dataset/full",
        store_root=store_root,
        content_type="application/json",
    )
    train_sealed = seal_bytes_with_receipt(
        data=json.dumps(train_rows, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        source_url=f"synthetic://{domain_id}/dataset/train",
        store_root=store_root,
        content_type="application/json",
    )
    test_sealed = seal_bytes_with_receipt(
        data=json.dumps(test_rows, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        source_url=f"synthetic://{domain_id}/dataset/test",
        store_root=store_root,
        content_type="application/json",
    )

    for kind, sealed in (
        ("dataset_full", full_sealed),
        ("dataset_train", train_sealed),
        ("dataset_test", test_sealed),
    ):
        record_domain_artifact(domain_id=domain_id, artifact_kind=kind, sha256=str(sealed["sha256"]), store_root=store_root)

    domain_root = (domains_root / domain_id).resolve()
    schemas_dir = domain_root / "schemas"
    tasks_dir = domain_root / "tasks"
    corpus_dir = domain_root / "corpus"
    solver_dir = domain_root / "solver"
    plugins_dir = domain_root / "plugins"
    for path in (schemas_dir, tasks_dir, corpus_dir, solver_dir, plugins_dir):
        path.mkdir(parents=True, exist_ok=True)

    input_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "feature_x": {"type": "integer"},
            "text": {"type": "string"},
        },
        "required": ["feature_x", "text"],
        "title": "Polymath domain input v1",
        "type": "object",
    }
    target_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Polymath domain target v1",
        "type": "integer",
    }
    write_canon_json(schemas_dir / "input_v1.jsonschema", input_schema)
    write_canon_json(schemas_dir / "target_v1.jsonschema", target_schema)

    task_spec = {
        "metric": "accuracy",
        "task_id": "task_classify_v1",
        "task_type": "classification",
    }
    write_canon_json(tasks_dir / "task_classify_v1.json", task_spec)

    domain_pack = {
        "dataset_artifacts": [
            {
                "kind": "starter_dataset",
                "license": license_name,
                "license_url": license_url,
                "provenance": [
                    {
                        "receipt_sha256": str(full_sealed["sha256"]),
                        "url": f"synthetic://{domain_id}/dataset/full",
                    }
                ],
                "sha256": str(full_sealed["sha256"]),
            }
        ],
        "domain_id": domain_id,
        "domain_name": str(domain_name),
        "metamorphic_tests": [
            {
                "task_id": "task_classify_v1",
                "template": "schema_round_trip",
                "test_id": "schema_round_trip_v1",
            },
            {
                "task_id": "task_classify_v1",
                "template": "permutation_invariance",
                "test_id": "permutation_invariance_v1",
            },
        ],
        "oracles": [
            {
                "adapter_version": "polymath_sources_v1",
                "oracle_name": "huggingface_load_dataset",
                "response_sha256": [str(full_sealed["sha256"])],
            }
        ],
        "schema_version": "polymath_domain_pack_v1",
        "tasks": [
            {
                "input_schema_ref": "schemas/input_v1.jsonschema",
                "metric": "accuracy",
                "split": {
                    "test_sha256": str(test_sealed["sha256"]),
                    "train_sha256": str(train_sealed["sha256"]),
                },
                "target_schema_ref": "schemas/target_v1.jsonschema",
                "task_id": "task_classify_v1",
                "task_type": "classification",
            }
        ],
        "topic_ids": [str(x) for x in topic_ids],
    }
    validate_schema(domain_pack, "polymath_domain_pack_v1")
    write_canon_json(domain_root / "domain_pack_v1.json", domain_pack)

    corpus_payload = {
        "corpus_id": "sha256:" + ("0" * 64),
        "dataset_sha256": str(test_sealed["sha256"]),
        "domain_id": domain_id,
        "examples": [
            {
                "example_id": str(row["id"]),
                "input": row["input"],
                "target": row["target"],
            }
            for row in test_rows[: min(12, len(test_rows))]
        ],
        "schema_version": "polymath_domain_corpus_v1",
    }
    no_id = dict(corpus_payload)
    no_id.pop("corpus_id", None)
    corpus_payload["corpus_id"] = canon_hash_obj(no_id)
    validate_schema(corpus_payload, "polymath_domain_corpus_v1")
    write_canon_json(corpus_dir / "corpus_v1.json", corpus_payload)

    (solver_dir / "baseline_solver_v1.py").write_text(_baseline_solver_source(), encoding="utf-8")
    _write_domain_readme(domain_root, domain_id, domain_name)

    return {
        "corpus_path": (corpus_dir / "corpus_v1.json").as_posix(),
        "domain_id": domain_id,
        "domain_pack_path": (domain_root / "domain_pack_v1.json").as_posix(),
        "domain_root": domain_root.as_posix(),
        "test_sha256": str(test_sealed["sha256"]),
        "train_sha256": str(train_sealed["sha256"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_domain_bootstrap_v1")
    parser.add_argument("--domain_id", default="")
    parser.add_argument("--domain_name", required=True)
    parser.add_argument("--topic_id", action="append", default=[])
    parser.add_argument("--domains_root", default="domains")
    parser.add_argument("--store_root", default="polymath/store")
    parser.add_argument("--starter_size", type=int, default=24)
    args = parser.parse_args()

    domain_name = str(args.domain_name).strip()
    domain_id = str(args.domain_id).strip() or normalize_domain_id(domain_name)
    result = bootstrap_domain(
        domain_id=domain_id,
        domain_name=domain_name,
        topic_ids=[str(x) for x in args.topic_id] or [f"topic:{domain_id}"],
        domains_root=Path(args.domains_root).resolve(),
        store_root=Path(args.store_root).resolve(),
        starter_size=max(8, int(args.starter_size)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
