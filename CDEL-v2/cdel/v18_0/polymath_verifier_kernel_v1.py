"""Pinned verifier kernel for polymath DomainPack DSL (v1)."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

from .omega_common_v1 import Q32_ONE, fail, load_canon_dict, repo_root, validate_schema


def _resolve_store_roots(state_dir: Path) -> list[Path]:
    out: list[Path] = []
    env_store_root = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_store_root:
        env_path = Path(env_store_root).expanduser().resolve()
        if env_path.exists() and env_path.is_dir():
            out.append(env_path)

    for parent in [state_dir.resolve(), *state_dir.resolve().parents]:
        for candidate in (
            parent / "polymath" / "store",
            parent / ".omega_cache" / "polymath" / "store",
        ):
            if candidate.exists() and candidate.is_dir():
                out.append(candidate)
    repo_store = repo_root() / "polymath" / "store"
    if repo_store.exists() and repo_store.is_dir():
        out.append(repo_store)
    repo_cache_store = repo_root() / ".omega_cache" / "polymath" / "store"
    if repo_cache_store.exists() and repo_cache_store.is_dir():
        out.append(repo_cache_store)
    unique: list[Path] = []
    seen = set()
    for row in out:
        key = row.as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _blob_bytes(sha256: str, store_roots: list[Path]) -> bytes:
    if not isinstance(sha256, str) or not sha256.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    hexd = sha256.split(":", 1)[1]
    if len(hexd) != 64:
        fail("SCHEMA_FAIL")

    candidate_paths = [root / "blobs" / "sha256" / hexd for root in store_roots]
    for path in candidate_paths:
        if not path.exists() or not path.is_file():
            continue
        data = path.read_bytes()
        got = __import__("hashlib").sha256(data).hexdigest()
        if got != hexd:
            fail("NONDETERMINISTIC")
        return data
    fail("MISSING_STATE_INPUT")
    return b""


def _load_json_blob(sha256: str, store_roots: list[Path]) -> Any:
    raw = _blob_bytes(sha256, store_roots)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        fail("SCHEMA_FAIL")
    return None


def _load_task_rows(task: dict[str, Any], store_roots: list[Path]) -> tuple[list[Any], list[Any]]:
    split = task.get("split")
    if not isinstance(split, dict):
        fail("SCHEMA_FAIL")
    train_sha = str(split.get("train_sha256", "")).strip()
    test_sha = str(split.get("test_sha256", "")).strip()
    train_rows = _load_json_blob(train_sha, store_roots)
    test_rows = _load_json_blob(test_sha, store_roots)
    if not isinstance(train_rows, list) or not isinstance(test_rows, list):
        fail("SCHEMA_FAIL")
    return train_rows, test_rows


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    fail("SCHEMA_FAIL")
    return 0


def _accuracy_q32(preds: list[Any], targets: list[Any]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    correct = 0
    for pred, target in zip(preds, targets):
        if _as_int(pred) == _as_int(target):
            correct += 1
    return (correct * Q32_ONE) // len(targets)


def _f1_q32(preds: list[Any], targets: list[Any]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    tp = fp = fn = 0
    for pred, target in zip(preds, targets):
        pred_b = 1 if _as_int(pred) > 0 else 0
        target_b = 1 if _as_int(target) > 0 else 0
        if pred_b == 1 and target_b == 1:
            tp += 1
        elif pred_b == 1 and target_b == 0:
            fp += 1
        elif pred_b == 0 and target_b == 1:
            fn += 1
    den = (2 * tp) + fp + fn
    if den <= 0:
        return 0
    return ((2 * tp) * Q32_ONE) // den


def _rmse_q32(preds: list[Any], targets: list[Any]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    sum_sq = 0
    for pred, target in zip(preds, targets):
        diff = _as_int(pred) - _as_int(target)
        sum_sq += diff * diff
    scaled = (sum_sq * (Q32_ONE * Q32_ONE)) // len(targets)
    return int(math.isqrt(max(0, scaled)))


def _logloss_q32(preds: list[Any], targets: list[Any]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    loss = 0.0
    eps = 1e-9
    for pred, target in zip(preds, targets):
        raw = pred
        if isinstance(raw, (int, float)):
            p = float(raw)
        elif isinstance(raw, str):
            p = float(raw)
        else:
            fail("SCHEMA_FAIL")
            p = 0.5
        p = max(eps, min(1.0 - eps, p))
        t = 1 if _as_int(target) > 0 else 0
        loss += -(t * math.log(p) + (1 - t) * math.log(1.0 - p))
    avg = loss / len(targets)
    return max(0, int(avg * Q32_ONE))


def _constraint_satisfaction_rate_q32(preds: list[Any]) -> int:
    if not preds:
        fail("SCHEMA_FAIL")
    ok = 0
    for pred in preds:
        if isinstance(pred, bool):
            ok += 1 if pred else 0
            continue
        if isinstance(pred, dict):
            ok += 1 if bool(pred.get("satisfied", False)) else 0
            continue
        ok += 1 if _as_int(pred) > 0 else 0
    return (ok * Q32_ONE) // len(preds)


def _retrieval_q32(preds: list[Any], targets: list[Any]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    hits = 0
    for pred, target in zip(preds, targets):
        if isinstance(pred, list):
            hits += 1 if target in pred else 0
        else:
            hits += 1 if pred == target else 0
    return (hits * Q32_ONE) // len(targets)


def _metric_q32(metric: str, preds: list[Any], targets: list[Any]) -> int:
    if metric == "accuracy":
        return _accuracy_q32(preds, targets)
    if metric == "f1":
        return _f1_q32(preds, targets)
    if metric == "rmse":
        return _rmse_q32(preds, targets)
    if metric == "logloss":
        return _logloss_q32(preds, targets)
    if metric == "constraint_satisfaction_rate":
        return _constraint_satisfaction_rate_q32(preds)
    if metric == "retrieval":
        return _retrieval_q32(preds, targets)
    fail("SCHEMA_FAIL")
    return 0


def _reported_metric_q32(row: dict[str, Any]) -> int:
    metric = row.get("reported_metric")
    if isinstance(metric, dict) and set(metric.keys()) == {"q"}:
        value = metric.get("q")
        if isinstance(value, int):
            return value
    fail("SCHEMA_FAIL")
    return 0


def _targets_from_rows(rows: list[Any]) -> list[Any]:
    targets: list[Any] = []
    for row in rows:
        if not isinstance(row, dict) or "target" not in row:
            fail("SCHEMA_FAIL")
        targets.append(row["target"])
    return targets


def _task_outputs_map(candidate_outputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = candidate_outputs.get("task_outputs")
    if not isinstance(outputs, list):
        fail("SCHEMA_FAIL")
    out: dict[str, dict[str, Any]] = {}
    for row in outputs:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        task_id = str(row.get("task_id", "")).strip()
        preds = row.get("predictions")
        if not task_id or not isinstance(preds, list):
            fail("SCHEMA_FAIL")
        out[task_id] = row
    return out


def _metamorphic_passes(
    *,
    template: str,
    metric: str,
    preds: list[Any],
    targets: list[Any],
    dataset_rows: list[Any],
    params: dict[str, Any] | None,
) -> bool:
    _ = params
    if template == "schema_round_trip":
        encoded = json.dumps(dataset_rows, sort_keys=True, separators=(",", ":"))
        decoded = json.loads(encoded)
        return decoded == dataset_rows
    if template == "permutation_invariance":
        base = _metric_q32(metric, preds, targets)
        rev = _metric_q32(metric, list(reversed(preds)), list(reversed(targets)))
        return base == rev
    if template == "label_permutation_invariance":
        if metric not in {"accuracy", "f1"}:
            return True
        flipped_preds = [1 - (1 if _as_int(value) > 0 else 0) for value in preds]
        flipped_targets = [1 - (1 if _as_int(value) > 0 else 0) for value in targets]
        return _metric_q32(metric, preds, targets) == _metric_q32(metric, flipped_preds, flipped_targets)
    if template == "unit_scaling_consistency":
        if metric != "rmse":
            return True
        factor = 10
        scaled_preds = [_as_int(value) * factor for value in preds]
        scaled_targets = [_as_int(value) * factor for value in targets]
        base = _metric_q32(metric, preds, targets)
        scaled = _metric_q32(metric, scaled_preds, scaled_targets)
        return scaled == (base * factor)
    fail("SCHEMA_FAIL")
    return False


def verify_domain(
    *,
    state_dir: Path,
    domain_pack_path: Path,
    candidate_outputs_path: Path,
) -> str:
    domain_pack = load_canon_dict(domain_pack_path)
    validate_schema(domain_pack, "polymath_domain_pack_v1")
    if domain_pack.get("schema_version") != "polymath_domain_pack_v1":
        fail("SCHEMA_FAIL")

    candidate_outputs = load_canon_dict(candidate_outputs_path)
    if str(candidate_outputs.get("domain_id", "")) != str(domain_pack.get("domain_id", "")):
        fail("SCHEMA_FAIL")
    task_map = _task_outputs_map(candidate_outputs)
    store_roots = _resolve_store_roots(state_dir)
    if not store_roots:
        fail("MISSING_STATE_INPUT")

    dataset_artifacts = domain_pack.get("dataset_artifacts")
    if not isinstance(dataset_artifacts, list):
        fail("SCHEMA_FAIL")
    for row in dataset_artifacts:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        _blob_bytes(str(row.get("sha256", "")), store_roots)

    tasks = domain_pack.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        fail("SCHEMA_FAIL")
    for task in tasks:
        if not isinstance(task, dict):
            fail("SCHEMA_FAIL")
        task_id = str(task.get("task_id", "")).strip()
        if not task_id:
            fail("SCHEMA_FAIL")
        out_row = task_map.get(task_id)
        if out_row is None:
            fail("SCHEMA_FAIL")

        _train_rows, test_rows = _load_task_rows(task, store_roots)
        targets = _targets_from_rows(test_rows)
        preds = out_row.get("predictions")
        if not isinstance(preds, list):
            fail("SCHEMA_FAIL")
        if len(preds) != len(targets):
            fail("SCHEMA_FAIL")

        metric_name = str(task.get("metric", "")).strip()
        computed_q32 = _metric_q32(metric_name, preds, targets)
        if computed_q32 != _reported_metric_q32(out_row):
            fail("NONDETERMINISTIC")

        task_type = str(task.get("task_type", "")).strip()
        if task_type in {"simulation_check", "theorem_check"}:
            if metric_name != "constraint_satisfaction_rate":
                fail("SCHEMA_FAIL")

    metamorphic = domain_pack.get("metamorphic_tests")
    if not isinstance(metamorphic, list):
        fail("SCHEMA_FAIL")
    for row in metamorphic:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        template = str(row.get("template", "")).strip()
        task_id = str(row.get("task_id", "")).strip()
        if not task_id:
            if len(tasks) != 1:
                fail("SCHEMA_FAIL")
            task = tasks[0]
            if not isinstance(task, dict):
                fail("SCHEMA_FAIL")
            task_id = str(task.get("task_id", "")).strip()
        task = next((candidate for candidate in tasks if isinstance(candidate, dict) and str(candidate.get("task_id", "")) == task_id), None)
        if not isinstance(task, dict):
            fail("SCHEMA_FAIL")
        out_row = task_map.get(task_id)
        if out_row is None:
            fail("SCHEMA_FAIL")

        _train_rows, test_rows = _load_task_rows(task, store_roots)
        targets = _targets_from_rows(test_rows)
        preds = out_row.get("predictions")
        if not isinstance(preds, list):
            fail("SCHEMA_FAIL")

        if not _metamorphic_passes(
            template=template,
            metric=str(task.get("metric", "")),
            preds=preds,
            targets=targets,
            dataset_rows=test_rows,
            params=row.get("params") if isinstance(row.get("params"), dict) else None,
        ):
            fail("NONDETERMINISTIC")

    oracles = domain_pack.get("oracles")
    if not isinstance(oracles, list):
        fail("SCHEMA_FAIL")
    for oracle in oracles:
        if not isinstance(oracle, dict):
            fail("SCHEMA_FAIL")
        hashes = oracle.get("response_sha256")
        if not isinstance(hashes, list):
            fail("SCHEMA_FAIL")
        for digest in hashes:
            _blob_bytes(str(digest), store_roots)

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_verifier_kernel_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--domain_pack", required=True)
    parser.add_argument("--candidate_outputs", required=True)
    args = parser.parse_args()

    if str(args.mode) != "full":
        fail("MODE_UNSUPPORTED")
    print(
        verify_domain(
            state_dir=Path(args.state_dir).resolve(),
            domain_pack_path=Path(args.domain_pack).resolve(),
            candidate_outputs_path=Path(args.candidate_outputs).resolve(),
        )
    )


if __name__ == "__main__":
    main()
