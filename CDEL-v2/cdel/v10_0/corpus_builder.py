"""Build training corpus from v8/v9 runs (v10.0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from ..v8_0 import verify_rsi_boundless_math_v1 as verify_v8_math
from ..v9_0 import verify_rsi_boundless_science_v1 as verify_v9_science

from .corpus_manifest import compute_corpus_id


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _load_allowlist(path: Path) -> set[str]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        return set()
    ids = payload.get("problem_ids") or []
    return {str(item) for item in ids if isinstance(item, str)}


def _load_math_problem_map(problems_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in problems_dir.glob("*.math_problem_spec_v1.json"):
        spec = load_canon_json(path)
        if not isinstance(spec, dict):
            continue
        problem_id = spec.get("problem_id")
        if isinstance(problem_id, str):
            out[problem_id] = spec
    return out


def _read_statement(problems_dir: Path, statement_hash: str) -> str:
    name = f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
    path = problems_dir / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_proof(state_dir: Path, proof_hash: str) -> str:
    path = state_dir / "math" / "attempts" / "proofs" / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
    if not path.exists():
        path = state_dir / "math" / "attempts" / "proofs" / f"sha256_{proof_hash.split(':',1)[1]}.proof"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _compute_example_id(example: dict[str, Any]) -> str:
    payload = dict(example)
    payload.pop("example_id", None)
    data = canon_bytes(payload)
    return sha256_prefixed(data)


def _collect_v8_math_examples(state_dir: Path, allowlist: set[str]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    problems_dir = state_dir.parents[2] / "campaigns" / "rsi_boundless_math_v8_0" / "problems"
    problem_map = _load_math_problem_map(problems_dir)
    receipts_dir = state_dir / "math" / "solved" / "receipts"
    for path in receipts_dir.glob("sha256_*.math_solution_receipt_v1.json"):
        receipt = load_canon_json(path)
        if not isinstance(receipt, dict):
            continue
        problem_id = str(receipt.get("problem_id"))
        if allowlist and problem_id not in allowlist:
            continue
        spec = problem_map.get(problem_id)
        if not spec:
            continue
        statement_hash = str(spec.get("statement_artifact_hash"))
        proof_hash = str(receipt.get("proof_artifact_hash"))
        statement = _read_statement(problems_dir, statement_hash)
        proof = _read_proof(state_dir, proof_hash)
        example = {
            "schema_version": "training_example_v1",
            "example_id": "",
            "example_type": "MATH_PROOF",
            "prompt": statement,
            "completion": proof,
            "source": {
                "source_kind": "V8_MATH",
                "source_run_id": str(state_dir),
                "source_receipt_hash": sha256_prefixed(canon_bytes(receipt)),
                "source_artifact_hashes": [statement_hash, proof_hash],
                "split": "TRAIN",
            },
        }
        example["example_id"] = _compute_example_id(example)
        examples.append(example)
    return examples


def _collect_v9_science_examples(state_dir: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    env_dir = state_dir / "science" / "env"
    dev_suitepack = load_canon_json(env_dir / "science_suitepack_dev_v1.json")
    dev_hash = sha256_prefixed(canon_bytes(dev_suitepack))

    attempts_root = state_dir / "science" / "attempts"
    for record_path in attempts_root.glob("*/*/attempt_record_v1.json"):
        record = load_canon_json(record_path)
        if not isinstance(record, dict):
            continue
        hazard = str(record.get("hazard_class"))
        if hazard not in {"H0_BENIGN", "H1_LOW_RISK"}:
            continue
        attempt_dir = record_path.parent
        sealed_dir = attempt_dir / "sealed"
        dev_receipt = None
        dev_receipt_hash = None
        for sealed_path in sealed_dir.glob("sha256_*.sealed_science_eval_receipt_v1.json"):
            sealed = load_canon_json(sealed_path)
            if not isinstance(sealed, dict):
                continue
            if sealed.get("suitepack_hash") != dev_hash:
                continue
            dev_receipt = sealed
            dev_receipt_hash = "sha256:" + sealed_path.name.split("sha256_", 1)[1].split(".sealed_science_eval_receipt_v1.json", 1)[0]
            break
        if dev_receipt is None or dev_receipt_hash is None:
            continue

        output_manifest = load_canon_json(attempt_dir / "outputs" / "output_manifest_v1.json")
        if not isinstance(output_manifest, dict):
            continue
        artifacts = output_manifest.get("artifacts") or []
        if not artifacts:
            continue
        artifact = artifacts[0]
        artifact_path = Path(str(artifact.get("path")))
        completion = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else ""

        prompt = f"task:{record.get('task_id')}\nvector:{record.get('vector')}\ndomain:{record.get('domain')}"
        example = {
            "schema_version": "training_example_v1",
            "example_id": "",
            "example_type": "SCI_DEV_SUPERVISED",
            "prompt": prompt,
            "completion": completion,
            "source": {
                "source_kind": "V9_SCIENCE",
                "source_run_id": str(state_dir),
                "source_receipt_hash": dev_receipt_hash,
                "source_artifact_hashes": [str(artifact.get("sha256", ""))],
                "split": "DEV",
            },
        }
        example["example_id"] = _compute_example_id(example)
        examples.append(example)
    return examples


def build_corpus(*, smg_root: Path, pack: dict[str, Any]) -> dict[str, Any]:
    state_dir = smg_root / "state"
    corpus_dir = state_dir / "corpus"
    shard_dir = corpus_dir / "shards"
    manifest_dir = corpus_dir / "manifest"
    index_dir = corpus_dir / "indexes"
    for path in [shard_dir, manifest_dir, index_dir]:
        path.mkdir(parents=True, exist_ok=True)

    split_policy = pack.get("split_policy") or {}
    allowlist_path = Path(str(split_policy.get("math_train_allowlist_path", "")))
    allowlist = _load_allowlist(allowlist_path) if allowlist_path.exists() else set()

    source_receipts: list[str] = []
    examples: list[dict[str, Any]] = []

    sources = pack.get("sources") or {}
    for src in sources.get("v8_math_runs", []) or []:
        state_path = Path(str(src.get("state_dir")))
        mode = str(src.get("mode", "full"))
        result = verify_v8_math.verify(state_path, mode=mode)
        ledger_head = result.get("ledger_head_hash")
        if isinstance(ledger_head, str) and ledger_head:
            source_receipts.append(f"sha256:{ledger_head}" if not ledger_head.startswith("sha256:") else ledger_head)
        examples.extend(_collect_v8_math_examples(state_path, allowlist))

    for src in sources.get("v9_science_runs", []) or []:
        state_path = Path(str(src.get("state_dir")))
        mode = str(src.get("mode", "full"))
        result = verify_v9_science.verify(state_path, mode=mode)
        ledger_head = result.get("ledger_head")
        if isinstance(ledger_head, str) and ledger_head:
            source_receipts.append(f"sha256:{ledger_head}" if not ledger_head.startswith("sha256:") else ledger_head)
        examples.extend(_collect_v9_science_examples(state_path))

    examples_sorted = sorted(
        examples,
        key=lambda ex: (
            ex.get("source", {}).get("source_kind", ""),
            ex.get("source", {}).get("source_run_id", ""),
            ex.get("example_id", ""),
        ),
    )

    shard_path = shard_dir / "training_examples_v1.jsonl"
    shard_path.write_text("", encoding="utf-8")
    for ex in examples_sorted:
        write_jsonl_line(shard_path, ex)

    shard_hash = _hash_file(shard_path)

    counts_by_type: dict[str, int] = {}
    for ex in examples_sorted:
        ex_type = str(ex.get("example_type"))
        counts_by_type[ex_type] = counts_by_type.get(ex_type, 0) + 1

    manifest = {
        "schema_version": "training_corpus_manifest_v1",
        "corpus_id": "",
        "shards": [
            {
                "path": str(shard_path),
                "sha256": shard_hash,
                "num_examples": len(examples_sorted),
            }
        ],
        "counts_by_type": counts_by_type,
        "source_run_receipts": list(source_receipts),
        "split_policy": {
            "math_train_allowlist_path": str(allowlist_path),
            "science_use_dev_only": True,
        },
    }
    manifest["corpus_id"] = compute_corpus_id(manifest)

    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_path = manifest_dir / f"sha256_{manifest_hash.split(':',1)[1]}.training_corpus_manifest_v1.json"
    write_canon_json(manifest_path, manifest)

    index = {
        "schema_version": "training_corpus_index_v1",
        "corpus_id": manifest["corpus_id"],
        "example_ids": [ex.get("example_id") for ex in examples_sorted],
    }
    index_hash = sha256_prefixed(canon_bytes(index))
    index_path = index_dir / f"sha256_{index_hash.split(':',1)[1]}.training_corpus_index_v1.json"
    write_canon_json(index_path, index)

    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_hash": manifest_hash,
        "index_path": index_path,
        "shard_path": shard_path,
        "shard_hash": shard_hash,
    }


__all__ = ["build_corpus"]
