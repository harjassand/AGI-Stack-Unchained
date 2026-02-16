"""Bootstrap a new polymath domain from top void candidate (v1)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json, write_jsonl_line
from .omega_common_v1 import Q32_ONE, canon_hash_obj, fail, load_canon_dict, repo_root, validate_schema, write_hashed_json
from .omega_test_plan_v1 import emit_test_plan_receipt
from .polymath_portfolio_v1 import bootstrap_entry, load_or_init_portfolio
from .polymath_verifier_kernel_v1 import verify_domain

_DEFAULT_MAX_DATASET_BYTES_U64 = 20 * 1024 * 1024


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_polymath_bootstrap_domain_pack_v1":
        fail("SCHEMA_FAIL")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        payload = json.loads(raw)
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _domain_rows(registry_path: Path) -> list[dict[str, Any]]:
    payload = load_canon_dict(registry_path)
    if payload.get("schema_version") != "polymath_domain_registry_v1":
        fail("SCHEMA_FAIL")
    validate_schema(payload, "polymath_domain_registry_v1")
    rows = payload.get("domains")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    return [row for row in rows if isinstance(row, dict)]


def _safe_policy_candidate(*, policy: dict[str, Any], topic_name: str, domain_id: str) -> bool:
    denylist = [str(x).strip().lower() for x in policy.get("denylist_keywords", []) if str(x).strip()]
    allowlist = [str(x).strip().lower() for x in policy.get("allowlist_keywords", []) if str(x).strip()]
    haystack = f"{topic_name} {domain_id}".lower()
    if any(token in haystack for token in denylist):
        return False
    if allowlist and not any(token in haystack for token in allowlist):
        return False
    return True


def _pick_void_candidate(void_rows: list[dict[str, Any]], existing_domain_ids: set[str]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for row in void_rows:
        if not isinstance(row, dict):
            continue
        domain_id = str(row.get("candidate_domain_id", "")).strip()
        if not domain_id or domain_id in existing_domain_ids:
            continue
        void_score = row.get("void_score_q32")
        score_q = int(void_score.get("q", 0)) if isinstance(void_score, dict) else 0
        if best is None:
            best = dict(row)
            best["_score_q"] = score_q
            continue
        if score_q > int(best.get("_score_q", 0)):
            best = dict(row)
            best["_score_q"] = score_q
            continue
        if score_q == int(best.get("_score_q", 0)) and domain_id < str(best.get("candidate_domain_id", "~")):
            best = dict(row)
            best["_score_q"] = score_q
    return best


def _q32_accuracy(preds: list[int], targets: list[int]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    correct = sum(1 for pred, target in zip(preds, targets) if int(pred) == int(target))
    return (correct * Q32_ONE) // len(targets)


def _majority_predictions(targets: list[int]) -> list[int]:
    positives = sum(1 for value in targets if int(value) > 0)
    negatives = len(targets) - positives
    majority = 1 if positives >= negatives else 0
    return [majority for _ in targets]


def _canonical_store_root(repo_root_path: Path) -> Path:
    env_value = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_value:
        store_root = Path(env_value).expanduser().resolve()
    else:
        store_root = (repo_root_path / ".omega_cache" / "polymath" / "store").resolve()
    store_root.mkdir(parents=True, exist_ok=True)
    for rel in ("indexes/urls_to_sha256.jsonl", "indexes/domain_to_artifacts.jsonl"):
        path = store_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return store_root


def _blob_size_bytes(*, store_root: Path, sha256: str) -> int:
    if not isinstance(sha256, str) or not sha256.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    digest = sha256.split(":", 1)[1]
    if len(digest) != 64:
        fail("SCHEMA_FAIL")
    path = store_root / "blobs" / "sha256" / digest
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    return int(path.stat().st_size)


def _tick_from_env(default_u64: int = 0) -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        return int(max(0, int(default_u64)))
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return int(max(0, int(default_u64)))
    return int(max(0, value))


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()

    void_report_path = root / str(pack.get("void_report_path_rel", "polymath/registry/polymath_void_report_v1.jsonl"))
    registry_path = root / str(pack.get("domain_registry_path_rel", "polymath/registry/polymath_domain_registry_v1.json"))
    policy_path = root / str(pack.get("domain_policy_path_rel", "polymath/domain_policy_v1.json"))

    state_root = out_dir.resolve() / "daemon" / "rsi_polymath_bootstrap_domain_v1" / "state"
    reports_dir = state_root / "reports"
    promotion_dir = state_root / "promotion"
    for path in (reports_dir, promotion_dir):
        path.mkdir(parents=True, exist_ok=True)

    if not registry_path.exists() or not registry_path.is_file():
        fail("MISSING_STATE_INPUT")
    if not policy_path.exists() or not policy_path.is_file():
        fail("MISSING_STATE_INPUT")

    void_rows = _load_jsonl(void_report_path)
    domain_rows = _domain_rows(registry_path)
    existing_ids = {str(row.get("domain_id", "")).strip() for row in domain_rows if str(row.get("domain_id", "")).strip()}

    candidate = _pick_void_candidate(void_rows, existing_domain_ids=existing_ids)
    if candidate is None:
        report = {
            "schema_version": "polymath_bootstrap_report_v1",
            "status": "NO_CANDIDATE",
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
        write_canon_json(reports_dir / "polymath_bootstrap_report_v1.json", report)
        print("OK")
        return

    policy = load_canon_dict(policy_path)
    if policy.get("schema_version") != "domain_policy_v1":
        fail("SCHEMA_FAIL")
    validate_schema(policy, "domain_policy_v1")

    candidate_domain_id = str(candidate.get("candidate_domain_id", "")).strip()
    candidate_topic_name = str(candidate.get("topic_name", "")).strip()
    candidate_topic_id = str(candidate.get("topic_id", "")).strip() or f"topic:{candidate_domain_id}"

    if not _safe_policy_candidate(policy=policy, topic_name=candidate_topic_name, domain_id=candidate_domain_id):
        blocked_row = {
            "schema_version": "polymath_domain_registry_v1",
            "domains": domain_rows
            + [
                {
                    "domain_id": candidate_domain_id,
                    "domain_name": candidate_topic_name,
                    "status": "BLOCKED_POLICY",
                    "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "topic_ids": [candidate_topic_id],
                    "domain_pack_rel": f"domains/{candidate_domain_id}/domain_pack_v1.json",
                    "notes": "blocked by domain policy",
                    "ready_for_conquer": False,
                    "ready_for_conquer_reason": "BLOCKED_POLICY",
                    "conquered_b": False,
                }
            ],
        }
        validate_schema(blocked_row, "polymath_domain_registry_v1")
        out_registry = out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json"
        out_registry.parent.mkdir(parents=True, exist_ok=True)
        write_canon_json(out_registry, blocked_row)

        report = {
            "schema_version": "polymath_bootstrap_report_v1",
            "status": "BLOCKED_POLICY",
            "domain_id": candidate_domain_id,
            "topic_name": candidate_topic_name,
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "domain_registry_rel": "polymath/registry/polymath_domain_registry_v1.json",
        }
        write_canon_json(reports_dir / "polymath_bootstrap_report_v1.json", report)
        print("OK")
        return

    store_root = _canonical_store_root(root)

    from tools.polymath.polymath_domain_bootstrap_v1 import bootstrap_domain
    from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes
    from tools.polymath.polymath_equivalence_suite_v1 import run_equivalence

    bootstrap = bootstrap_domain(
        domain_id=candidate_domain_id,
        domain_name=candidate_topic_name,
        topic_ids=[candidate_topic_id],
        domains_root=out_dir / "domains",
        store_root=store_root,
    )

    domain_pack_rel = f"domains/{bootstrap['domain_id']}/domain_pack_v1.json"
    domain_pack_path = out_dir / domain_pack_rel
    domain_pack = load_canon_dict(domain_pack_path)
    dataset_limit_u64 = max(1, int(pack.get("max_dataset_bytes_u64", _DEFAULT_MAX_DATASET_BYTES_U64)))
    blob_ids: set[str] = set()
    dataset_artifacts = domain_pack.get("dataset_artifacts")
    if isinstance(dataset_artifacts, list):
        for row in dataset_artifacts:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            digest = str(row.get("sha256", "")).strip()
            if digest:
                blob_ids.add(digest)

    tasks = domain_pack.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        fail("SCHEMA_FAIL")
    task = tasks[0]
    if not isinstance(task, dict):
        fail("SCHEMA_FAIL")
    split = task.get("split")
    if not isinstance(split, dict):
        fail("SCHEMA_FAIL")
    test_sha = str(split.get("test_sha256", "")).strip()
    train_sha = str(split.get("train_sha256", "")).strip()
    if train_sha:
        blob_ids.add(train_sha)
    if test_sha:
        blob_ids.add(test_sha)

    dataset_total_bytes_u64 = sum(_blob_size_bytes(store_root=store_root, sha256=digest) for digest in sorted(blob_ids))
    if int(dataset_total_bytes_u64) > int(dataset_limit_u64):
        blocked_row = {
            "schema_version": "polymath_domain_registry_v1",
            "domains": domain_rows
            + [
                {
                    "domain_id": str(bootstrap["domain_id"]),
                    "domain_name": candidate_topic_name,
                    "status": "BLOCKED_SIZE",
                    "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "topic_ids": [candidate_topic_id],
                    "domain_pack_rel": domain_pack_rel,
                    "capability_id": f"RSI_DOMAIN_{str(bootstrap['domain_id']).upper()}",
                    "dataset_artifact_sha256s": sorted(blob_ids),
                    "notes": f"dataset_size_bytes={int(dataset_total_bytes_u64)} exceeds limit={int(dataset_limit_u64)}",
                    "ready_for_conquer": False,
                    "ready_for_conquer_reason": "BLOCKED_SIZE",
                    "conquered_b": False,
                }
            ],
        }
        validate_schema(blocked_row, "polymath_domain_registry_v1")
        out_registry = out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json"
        out_registry.parent.mkdir(parents=True, exist_ok=True)
        write_canon_json(out_registry, blocked_row)

        report = {
            "schema_version": "polymath_bootstrap_report_v1",
            "status": "BLOCKED_SIZE",
            "domain_id": str(bootstrap["domain_id"]),
            "topic_name": candidate_topic_name,
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "domain_registry_rel": "polymath/registry/polymath_domain_registry_v1.json",
            "dataset_total_bytes_u64": int(dataset_total_bytes_u64),
            "dataset_limit_bytes_u64": int(dataset_limit_u64),
        }
        write_canon_json(reports_dir / "polymath_bootstrap_report_v1.json", report)
        print("OK")
        return

    test_rows = json.loads(load_blob_bytes(sha256=test_sha, store_root=store_root).decode("utf-8"))
    if not isinstance(test_rows, list):
        fail("SCHEMA_FAIL")
    targets = [int((row or {}).get("target", 0)) for row in test_rows if isinstance(row, dict)]
    preds = _majority_predictions(targets)
    accuracy_q32 = _q32_accuracy(preds, targets)

    candidate_outputs = {
        "schema_version": "polymath_candidate_outputs_v1",
        "domain_id": str(bootstrap["domain_id"]),
        "task_outputs": [
            {
                "task_id": str(task.get("task_id", "task_classify_v1")),
                "predictions": preds,
                "reported_metric": {"q": int(accuracy_q32)},
            }
        ],
    }
    candidate_outputs_rel = f"domains/{bootstrap['domain_id']}/corpus/candidate_outputs_v1.json"
    candidate_outputs_path = out_dir / candidate_outputs_rel
    write_canon_json(candidate_outputs_path, candidate_outputs)

    if verify_domain(
        state_dir=state_root,
        domain_pack_path=domain_pack_path,
        candidate_outputs_path=candidate_outputs_path,
    ) != "VALID":
        fail("VERIFY_ERROR")

    equivalence_rel = f"domains/{bootstrap['domain_id']}/corpus/equivalence_report_v1.json"
    run_equivalence(
        state_dir=state_root,
        domain_pack_path=domain_pack_path,
        reference_outputs_path=candidate_outputs_path,
        candidate_outputs_path=candidate_outputs_path,
        out_path=out_dir / equivalence_rel,
    )

    capability_id = f"RSI_DOMAIN_{bootstrap['domain_id'].upper()}"
    domain_rows_next = list(domain_rows)
    domain_rows_next.append(
        {
            "domain_id": str(bootstrap["domain_id"]),
            "domain_name": candidate_topic_name,
            "status": "ACTIVE",
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "topic_ids": [candidate_topic_id],
            "domain_pack_rel": domain_pack_rel,
            "capability_id": capability_id,
            "dataset_artifact_sha256s": [str((domain_pack.get("dataset_artifacts") or [{}])[0].get("sha256", ""))],
            "ready_for_conquer": True,
            "ready_for_conquer_reason": "BOOTSTRAPPED",
            "conquered_b": False,
        }
    )

    registry_out = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": domain_rows_next,
    }
    validate_schema(registry_out, "polymath_domain_registry_v1")

    out_registry_path = out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json"
    out_registry_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_registry_path, registry_out)

    generated_caps_path = out_dir / "polymath" / "registry" / "generated_capabilities_v1.jsonl"
    write_jsonl_line(
        generated_caps_path,
        {
            "campaign_id": "rsi_polymath_conquer_domain_v1",
            "capability_id": capability_id,
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "domain_id": str(bootstrap["domain_id"]),
            "schema_version": "polymath_generated_capability_v1",
        },
    )

    report = {
        "schema_version": "polymath_bootstrap_report_v1",
        "status": "BOOTSTRAPPED",
        "domain_id": str(bootstrap["domain_id"]),
        "domain_name": candidate_topic_name,
        "topic_id": candidate_topic_id,
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "domain_pack_rel": domain_pack_rel,
        "candidate_outputs_rel": candidate_outputs_rel,
        "equivalence_report_rel": equivalence_rel,
        "domain_registry_rel": "polymath/registry/polymath_domain_registry_v1.json",
        "capability_id": capability_id,
        "void_score_q32": int((candidate.get("void_score_q32") or {}).get("q", 0)),
    }
    write_canon_json(reports_dir / "polymath_bootstrap_report_v1.json", report)

    portfolio_rel = "polymath/registry/polymath_portfolio_v1.json"
    portfolio_payload = load_or_init_portfolio(root / portfolio_rel)
    bootstrap_entry(
        portfolio=portfolio_payload,
        domain_id=str(bootstrap["domain_id"]),
        train_sha256=str(train_sha),
        baseline_metric_q32=int(accuracy_q32),
        tick_u64=_tick_from_env(),
    )
    write_canon_json(out_dir / portfolio_rel, portfolio_payload)

    touched_paths = [
        domain_pack_rel,
        f"domains/{bootstrap['domain_id']}/README.md",
        f"domains/{bootstrap['domain_id']}/solver/baseline_solver_v1.py",
        f"domains/{bootstrap['domain_id']}/corpus/corpus_v1.json",
        "polymath/registry/polymath_domain_registry_v1.json",
        portfolio_rel,
    ]
    bundle = {
        "schema_version": "polymath_bootstrap_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": "rsi_polymath_bootstrap_domain_v1",
        "domain_id": str(bootstrap["domain_id"]),
        "domain_name": candidate_topic_name,
        "capability_id": capability_id,
        "activation_key": str(bootstrap["domain_id"]),
        "domain_pack_rel": domain_pack_rel,
        "domain_registry_rel": "polymath/registry/polymath_domain_registry_v1.json",
        "report_rel": "daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json",
        "touched_paths": sorted(set(touched_paths)),
    }
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "polymath_bootstrap_promotion_bundle_v1.json",
        bundle,
        id_field="bundle_id",
    )
    emit_test_plan_receipt(
        promotion_dir=promotion_dir,
        touched_paths=[str(row) for row in bundle_obj.get("touched_paths", []) if isinstance(row, str)],
        mode="promotion",
    )

    print("OK")


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_polymath_bootstrap_domain_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
