"""Conquer a bootstrapped polymath domain via deterministic solver improvements (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import Q32_ONE, canon_hash_obj, fail, load_canon_dict, load_jsonl, repo_root, validate_schema, write_hashed_json
from .omega_test_plan_v1 import emit_test_plan_receipt
from .polymath_portfolio_v1 import conquer_entry, load_or_init_portfolio
from .polymath_verifier_kernel_v1 import verify_domain


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_polymath_conquer_domain_pack_v1":
        fail("SCHEMA_FAIL")
    return payload


def _load_registry(path: Path) -> list[dict[str, Any]]:
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "polymath_domain_registry_v1":
        fail("SCHEMA_FAIL")
    validate_schema(payload, "polymath_domain_registry_v1")
    rows = payload.get("domains")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    return [row for row in rows if isinstance(row, dict)]


def _no_ready_skip_reason_counts() -> dict[str, int]:
    return {
        "NOT_ACTIVE": 0,
        "CONQUERED": 0,
        "NOT_READY_FOR_CONQUER": 0,
        "TARGET_DOMAIN_NOT_FOUND": 0,
        "DOMAIN_PACK_REL_MISSING": 0,
        "DOMAIN_PACK_PATH_MISSING": 0,
    }


def _skip_sample(*, domain_id: str, reason: str, detail: str) -> dict[str, str]:
    return {
        "domain_id": str(domain_id),
        "reason": str(reason),
        "detail": str(detail),
    }


def _ready_for_conquer(row: dict[str, Any]) -> bool:
    # Backward-compat: legacy registry rows may omit readiness fields.
    if "ready_for_conquer" not in row:
        return True
    return bool(row.get("ready_for_conquer", False))


def _domain_selection_diagnostics(*, rows: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    sorted_rows = sorted(rows, key=lambda row: str(row.get("domain_id", "")))
    skip_reasons = _no_ready_skip_reason_counts()
    skip_samples: list[dict[str, str]] = []
    eligible_domains: list[dict[str, Any]] = []
    domains_active_u64 = 0

    for row in sorted_rows:
        if not isinstance(row, dict):
            continue
        domain_id = str(row.get("domain_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if status != "ACTIVE":
            skip_reasons["NOT_ACTIVE"] = int(skip_reasons["NOT_ACTIVE"]) + 1
            skip_samples.append(_skip_sample(domain_id=domain_id, reason="NOT_ACTIVE", detail=f"status={status or '<empty>'}"))
            continue

        domains_active_u64 += 1
        if bool(row.get("conquered_b", False)):
            skip_reasons["CONQUERED"] = int(skip_reasons["CONQUERED"]) + 1
            skip_samples.append(_skip_sample(domain_id=domain_id, reason="CONQUERED", detail="conquered_b=true"))
            continue

        if not _ready_for_conquer(row):
            ready_reason = str(row.get("ready_for_conquer_reason", "")).strip()
            skip_reasons["NOT_READY_FOR_CONQUER"] = int(skip_reasons["NOT_READY_FOR_CONQUER"]) + 1
            skip_samples.append(
                _skip_sample(
                    domain_id=domain_id,
                    reason="NOT_READY_FOR_CONQUER",
                    detail=f"ready_for_conquer=false reason={ready_reason or '<empty>'}",
                )
            )
            continue

        domain_pack_rel = str(row.get("domain_pack_rel", "")).strip()
        if not domain_pack_rel:
            skip_reasons["DOMAIN_PACK_REL_MISSING"] = int(skip_reasons["DOMAIN_PACK_REL_MISSING"]) + 1
            skip_samples.append(_skip_sample(domain_id=domain_id, reason="DOMAIN_PACK_REL_MISSING", detail="domain_pack_rel missing"))
            continue

        domain_pack_path = (root / domain_pack_rel).resolve()
        if not domain_pack_path.exists() or not domain_pack_path.is_file():
            skip_reasons["DOMAIN_PACK_PATH_MISSING"] = int(skip_reasons["DOMAIN_PACK_PATH_MISSING"]) + 1
            skip_samples.append(
                _skip_sample(
                    domain_id=domain_id,
                    reason="DOMAIN_PACK_PATH_MISSING",
                    detail=f"path_missing={domain_pack_rel}",
                )
            )
            continue

        eligible_domains.append(row)

    skip_samples.sort(
        key=lambda row: (
            str(row.get("domain_id", "")),
            str(row.get("reason", "")),
            str(row.get("detail", "")),
        )
    )
    return {
        "domains_seen_u64": int(len(sorted_rows)),
        "domains_active_u64": int(domains_active_u64),
        "domains_eligible_u64": int(len(eligible_domains)),
        "skip_reasons": skip_reasons,
        "skip_samples": skip_samples,
        "eligible_domains": eligible_domains,
    }


def _registry_mark_conquered(*, rows: list[dict[str, Any]], domain_id: str, now_iso: str) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        next_row = dict(row)
        if str(next_row.get("domain_id", "")).strip() == domain_id:
            next_row["conquered_b"] = True
            next_row["conquered_at_utc"] = str(now_iso)
            next_row["ready_for_conquer"] = False
            next_row["ready_for_conquer_reason"] = "CONQUERED"
        out.append(next_row)
    payload = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": out,
    }
    validate_schema(payload, "polymath_domain_registry_v1")
    return payload


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _write_no_ready_domain_report(
    *,
    reports_dir: Path,
    reason_code: str = "",
    domain_id: str = "",
    domain_pack_rel: str = "",
    domains_seen_u64: int = 0,
    domains_active_u64: int = 0,
    domains_eligible_u64: int = 0,
    skip_reasons: dict[str, int] | None = None,
    skip_samples: list[dict[str, str]] | None = None,
) -> None:
    resolved_skip_reasons = _no_ready_skip_reason_counts()
    if isinstance(skip_reasons, dict):
        for key in resolved_skip_reasons.keys():
            resolved_skip_reasons[key] = int(skip_reasons.get(key, 0))
    resolved_skip_samples = sorted(
        [
            _skip_sample(
                domain_id=str(row.get("domain_id", "")),
                reason=str(row.get("reason", "")),
                detail=str(row.get("detail", "")),
            )
            for row in (skip_samples or [])
            if isinstance(row, dict)
        ],
        key=lambda row: (
            str(row.get("domain_id", "")),
            str(row.get("reason", "")),
            str(row.get("detail", "")),
        ),
    )[:10]
    report: dict[str, Any] = {
        "schema_version": "polymath_conquer_report_v1",
        "status": "NO_READY_DOMAIN",
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "domains_seen_u64": int(domains_seen_u64),
        "domains_active_u64": int(domains_active_u64),
        "domains_eligible_u64": int(domains_eligible_u64),
        "skip_reasons": resolved_skip_reasons,
        "skip_samples": resolved_skip_samples,
    }
    if domain_id:
        report["domain_id"] = domain_id
    if domain_pack_rel:
        report["domain_pack_rel"] = domain_pack_rel
    if reason_code:
        report["reason_code"] = reason_code
    write_canon_json(reports_dir / "polymath_conquer_report_v1.json", report)


def _resolved_store_root(root: Path) -> Path:
    env_value = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    repo_cache = (root / ".omega_cache" / "polymath" / "store").resolve()
    if repo_cache.exists() and repo_cache.is_dir():
        return repo_cache
    return (root / "polymath" / "store").resolve()


def _q32_accuracy(preds: list[int], targets: list[int]) -> int:
    if len(preds) != len(targets) or not targets:
        fail("SCHEMA_FAIL")
    correct = sum(1 for pred, target in zip(preds, targets) if int(pred) == int(target))
    return (correct * Q32_ONE) // len(targets)


def _q32_f1(preds: list[int], targets: list[int]) -> int:
    tp = fp = fn = 0
    for pred, target in zip(preds, targets):
        pred_b = 1 if int(pred) > 0 else 0
        target_b = 1 if int(target) > 0 else 0
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


def _majority_predictions(targets: list[int]) -> list[int]:
    positives = sum(1 for value in targets if int(value) > 0)
    negatives = len(targets) - positives
    majority = 1 if positives >= negatives else 0
    return [majority for _ in targets]


def _metric_q32(metric: str, preds: list[int], targets: list[int]) -> int:
    if metric == "accuracy":
        return _q32_accuracy(preds, targets)
    if metric == "f1":
        return _q32_f1(preds, targets)
    fail("SCHEMA_FAIL")
    return 0


def _metric_improved(metric: str, baseline_q32: int, improved_q32: int) -> bool:
    if metric in {"rmse", "logloss"}:
        return int(improved_q32) < int(baseline_q32)
    return int(improved_q32) > int(baseline_q32)


def _target_binary(row: dict[str, Any]) -> int:
    return 1 if int(row.get("target", 0)) > 0 else 0


def _stable_example_id(*, row: dict[str, Any], idx: int) -> str:
    value = str(row.get("example_id", "")).strip()
    if value:
        return value
    return f"row:{int(idx)}"


def _tokenize(row: dict[str, Any], token_family: str) -> list[str]:
    input_row = row.get("input")
    if not isinstance(input_row, dict):
        return []
    if token_family == "smiles_char_unigram":
        smiles = input_row.get("smiles")
        if smiles is None:
            return []
        return [f"smiles:{ch}" for ch in str(smiles)]
    if token_family == "smiles_char_bigram":
        smiles = str(input_row.get("smiles", ""))
        if not smiles:
            return []
        return [f"smiles:{smiles[i:i + 2]}" for i in range(max(0, len(smiles) - 1))]
    if token_family == "text_word_unigram":
        text = input_row.get("text")
        if text is None:
            return []
        return [f"text:{token}" for token in str(text).lower().split() if token]
    if token_family == "text_char_trigram":
        text = str(input_row.get("text", "")).lower()
        if len(text) < 3:
            return [f"text3:{text}"] if text else []
        return [f"text3:{text[i:i + 3]}" for i in range(len(text) - 2)]
    fail("SCHEMA_FAIL")
    return []


def _candidate_token_families(rows: list[dict[str, Any]]) -> list[str]:
    has_smiles = False
    has_text = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        input_row = row.get("input")
        if not isinstance(input_row, dict):
            continue
        if input_row.get("smiles") is not None:
            has_smiles = True
        if input_row.get("text") is not None:
            has_text = True
    out: list[str] = []
    if has_smiles:
        out.extend(["smiles_char_unigram", "smiles_char_bigram"])
    if has_text:
        out.extend(["text_word_unigram", "text_char_trigram"])
    if not out:
        out = [
            "smiles_char_unigram",
            "smiles_char_bigram",
            "text_word_unigram",
            "text_char_trigram",
        ]
    return out


def _split_train_val(train_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_split: list[dict[str, Any]] = []
    val_split: list[dict[str, Any]] = []
    for idx, row in enumerate(train_rows):
        if not isinstance(row, dict):
            continue
        digest = hashlib.sha256(_stable_example_id(row=row, idx=idx).encode("utf-8")).hexdigest()
        fold = int(digest, 16) % 5
        if fold == 0:
            val_split.append(row)
        else:
            train_split.append(row)
    if not train_split and val_split:
        train_split = list(val_split)
    if not val_split and train_split:
        val_split = [train_split[0]]
    if not train_split or not val_split:
        fail("SCHEMA_FAIL")
    return train_split, val_split


def _nb_predict_with_config(
    *,
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    token_family: str,
    alpha_f64: float,
) -> tuple[list[int], int]:
    alpha = float(alpha_f64)
    if alpha <= 0:
        fail("SCHEMA_FAIL")
    class_counts = {0: 0, 1: 0}
    token_totals = {0: 0, 1: 0}
    token_counts: dict[int, dict[str, int]] = {0: {}, 1: {}}
    vocab: set[str] = set()

    for row in train_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        label = _target_binary(row)
        class_counts[label] = int(class_counts[label]) + 1
        for token in _tokenize(row, token_family):
            vocab.add(token)
            bucket = token_counts[label]
            bucket[token] = int(bucket.get(token, 0)) + 1
            token_totals[label] = int(token_totals[label]) + 1

    total_train = int(class_counts[0]) + int(class_counts[1])
    if total_train <= 0:
        fail("SCHEMA_FAIL")
    majority = 1 if int(class_counts[1]) >= int(class_counts[0]) else 0
    if not vocab:
        return [majority for _ in test_rows], 0

    vocab_size = len(vocab)
    out: list[int] = []
    for row in test_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        tokens = _tokenize(row, token_family)
        scores: dict[int, float] = {}
        for label in (0, 1):
            prior = (int(class_counts[label]) + alpha) / (float(total_train) + (2.0 * alpha))
            score = math.log(prior)
            denom = float(int(token_totals[label]) + (alpha * vocab_size))
            token_bucket = token_counts[label]
            for token in tokens:
                token_count = int(token_bucket.get(token, 0))
                score += math.log((token_count + alpha) / denom)
            scores[label] = score
        if float(scores[1]) == float(scores[0]):
            out.append(majority)
        else:
            out.append(1 if float(scores[1]) > float(scores[0]) else 0)
    return out, int(vocab_size)


def _search_best_config(*, train_rows: list[dict[str, Any]], metric_id: str) -> dict[str, Any]:
    search_families = _candidate_token_families(train_rows)
    train_split, val_split = _split_train_val(train_rows)
    val_targets = [_target_binary(row) for row in val_split]

    best: dict[str, Any] | None = None
    for token_family in sorted(search_families):
        for alpha_f64 in (0.5, 1.0, 2.0):
            val_preds, model_complexity = _nb_predict_with_config(
                train_rows=train_split,
                test_rows=val_split,
                token_family=token_family,
                alpha_f64=float(alpha_f64),
            )
            val_metric_q32 = int(_metric_q32(metric_id, val_preds, val_targets))
            config = {
                "token_family": token_family,
                "alpha_num_u64": int(round(float(alpha_f64) * 10.0)),
                "alpha_den_u64": 10,
            }
            config_id = f"{token_family}|alpha={float(alpha_f64):.1f}"
            candidate = {
                "config_id": config_id,
                "config": config,
                "val_metric_q32": val_metric_q32,
                "model_complexity_u64": int(model_complexity),
            }
            if best is None:
                best = candidate
                continue
            if int(candidate["val_metric_q32"]) > int(best["val_metric_q32"]):
                best = candidate
                continue
            if int(candidate["val_metric_q32"]) < int(best["val_metric_q32"]):
                continue
            if int(candidate["model_complexity_u64"]) < int(best["model_complexity_u64"]):
                best = candidate
                continue
            if int(candidate["model_complexity_u64"]) > int(best["model_complexity_u64"]):
                continue
            if str(candidate["config_id"]) < str(best["config_id"]):
                best = candidate
    if best is None:
        fail("SCHEMA_FAIL")
    return best


def _alpha_from_config(config: dict[str, Any]) -> float:
    if "alpha_f64" in config:
        try:
            alpha = float(config.get("alpha_f64", 0))
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")
        if alpha <= 0:
            fail("SCHEMA_FAIL")
        return alpha
    try:
        num = int(config.get("alpha_num_u64", 0))
        den = int(config.get("alpha_den_u64", 1))
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return 1.0
    if num <= 0 or den <= 0:
        fail("SCHEMA_FAIL")
    return float(num) / float(den)


def _proposal_path(store_root: Path, proposal_id: str) -> Path:
    if not isinstance(proposal_id, str) or not proposal_id.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    return store_root / "refinery" / "proposals" / f"{proposal_id}.polymath_refinery_proposal_v1.json"


def _load_refinery_cached_config(*, store_root: Path, domain_id: str, train_sha: str) -> dict[str, Any] | None:
    index_path = store_root / "refinery" / "indexes" / "domain_train_to_best.jsonl"
    if not index_path.exists() or not index_path.is_file():
        return None
    rows = load_jsonl(index_path)
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        if str(row.get("domain_id", "")) != domain_id:
            continue
        if str(row.get("train_sha256", "")) != train_sha:
            continue
        proposal_id = str(row.get("proposal_id", "")).strip()
        if not proposal_id:
            continue
        proposal_path = _proposal_path(store_root, proposal_id)
        if not proposal_path.exists() or not proposal_path.is_file():
            continue
        proposal = load_canon_dict(proposal_path)
        no_id = dict(proposal)
        no_id.pop("proposal_id", None)
        if str(proposal.get("proposal_id", "")) != canon_hash_obj(no_id):
            continue
        if str(proposal.get("domain_id", "")) != domain_id:
            continue
        if str(proposal.get("train_sha256", "")) != train_sha:
            continue
        config = proposal.get("config")
        if not isinstance(config, dict):
            continue
        token_family = str(config.get("token_family", "")).strip()
        if token_family not in {
            "smiles_char_unigram",
            "smiles_char_bigram",
            "text_word_unigram",
            "text_char_trigram",
        }:
            continue
        try:
            alpha_value = float(_alpha_from_config(config))
        except Exception:  # noqa: BLE001
            continue
        if alpha_value <= 0:
            continue
        alpha_num_u64 = config.get("alpha_num_u64")
        alpha_den_u64 = config.get("alpha_den_u64")
        if isinstance(alpha_num_u64, int) and isinstance(alpha_den_u64, int) and alpha_num_u64 > 0 and alpha_den_u64 > 0:
            cfg = {
                "token_family": token_family,
                "alpha_num_u64": int(alpha_num_u64),
                "alpha_den_u64": int(alpha_den_u64),
            }
        else:
            cfg = {
                "token_family": token_family,
                "alpha_num_u64": int(round(alpha_value * 1000.0)),
                "alpha_den_u64": 1000,
            }
        return {
            "proposal_id": proposal_id,
            "config_id": str(proposal.get("config_id", "")),
            "config": cfg,
            "val_metric_q32": int(proposal.get("val_metric_q32", 0)),
            "model_complexity_u64": int(proposal.get("model_complexity_u64", 0)),
        }
    return None


def _tick_from_env(default_u64: int = 0) -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        return int(max(0, int(default_u64)))
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return int(max(0, int(default_u64)))
    return int(max(0, value))


def _shadow_solver_source(*, train_sha: str, config_id: str, config: dict[str, Any]) -> str:
    config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return f"""#!/usr/bin/env python3
\"\"\"Deterministic shadow solver for polymath binary classification.\"\"\"

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes

_TRAIN_SHA256 = "{train_sha}"
_CONFIG_ID = "{config_id}"
_CONFIG = json.loads('{config_json}')


def _store_root() -> Path:
    env_value = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / ".omega_cache" / "polymath" / "store").resolve()


def _target_binary(row: dict[str, Any]) -> int:
    return 1 if int(row.get("target", 0)) > 0 else 0


def _tokenize(row: dict[str, Any], token_family: str) -> list[str]:
    input_row = row.get("input")
    if not isinstance(input_row, dict):
        return []
    if token_family == "smiles_char_unigram":
        smiles = input_row.get("smiles")
        if smiles is None:
            return []
        return [f"smiles:{{ch}}" for ch in str(smiles)]
    if token_family == "smiles_char_bigram":
        smiles = str(input_row.get("smiles", ""))
        if not smiles:
            return []
        return [f"smiles:{{smiles[i:i + 2]}}" for i in range(max(0, len(smiles) - 1))]
    if token_family == "text_word_unigram":
        text = input_row.get("text")
        if text is None:
            return []
        return [f"text:{{token}}" for token in str(text).lower().split() if token]
    if token_family == "text_char_trigram":
        text = str(input_row.get("text", "")).lower()
        if len(text) < 3:
            return [f"text3:{{text}}"] if text else []
        return [f"text3:{{text[i:i + 3]}}" for i in range(len(text) - 2)]
    raise RuntimeError("SCHEMA_FAIL")


def _nb_predict(train_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[int]:
    token_family = str(_CONFIG.get("token_family", ""))
    alpha_num = int(_CONFIG.get("alpha_num_u64", 0))
    alpha_den = int(_CONFIG.get("alpha_den_u64", 1))
    if alpha_num > 0 and alpha_den > 0:
        alpha = float(alpha_num) / float(alpha_den)
    else:
        alpha = float(_CONFIG.get("alpha_f64", 1.0))
    if alpha <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    class_counts = {{0: 0, 1: 0}}
    token_totals = {{0: 0, 1: 0}}
    token_counts: dict[int, dict[str, int]] = {{0: {{}}, 1: {{}}}}
    vocab: set[str] = set()

    for row in train_rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        label = _target_binary(row)
        class_counts[label] = int(class_counts[label]) + 1
        for token in _tokenize(row, token_family):
            vocab.add(token)
            bucket = token_counts[label]
            bucket[token] = int(bucket.get(token, 0)) + 1
            token_totals[label] = int(token_totals[label]) + 1

    total_train = int(class_counts[0]) + int(class_counts[1])
    if total_train <= 0:
        raise RuntimeError("SCHEMA_FAIL")
    majority = 1 if int(class_counts[1]) >= int(class_counts[0]) else 0
    if not vocab:
        return [majority for _ in rows]

    vocab_size = len(vocab)
    out: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        tokens = _tokenize(row, token_family)
        scores: dict[int, float] = {{}}
        for label in (0, 1):
            prior = (int(class_counts[label]) + alpha) / (float(total_train) + (2.0 * alpha))
            score = math.log(prior)
            denom = float(int(token_totals[label]) + (alpha * vocab_size))
            bucket = token_counts[label]
            for token in tokens:
                score += math.log((int(bucket.get(token, 0)) + alpha) / denom)
            scores[label] = score
        if float(scores[1]) == float(scores[0]):
            out.append(majority)
        else:
            out.append(1 if float(scores[1]) > float(scores[0]) else 0)
    return out


def predict(rows: list[dict[str, Any]]) -> list[int]:
    train_blob = load_blob_bytes(sha256=_TRAIN_SHA256, store_root=_store_root())
    train_rows = json.loads(train_blob.decode("utf-8"))
    if not isinstance(train_rows, list):
        raise RuntimeError("SCHEMA_FAIL")
    clean_train = [row for row in train_rows if isinstance(row, dict)]
    clean_rows = [row for row in rows if isinstance(row, dict)]
    return _nb_predict(clean_train, clean_rows)
"""


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()
    source_store_root = _resolved_store_root(root)

    registry_path = root / str(pack.get("domain_registry_path_rel", "polymath/registry/polymath_domain_registry_v1.json"))
    domains = _load_registry(registry_path)
    selection_diag = _domain_selection_diagnostics(rows=domains, root=root)
    eligible_domains = list(selection_diag.get("eligible_domains", []))
    skip_reasons = selection_diag.get("skip_reasons")
    if not isinstance(skip_reasons, dict):
        skip_reasons = _no_ready_skip_reason_counts()
    skip_samples = [
        _skip_sample(
            domain_id=str(row.get("domain_id", "")),
            reason=str(row.get("reason", "")),
            detail=str(row.get("detail", "")),
        )
        for row in selection_diag.get("skip_samples", [])
        if isinstance(row, dict)
    ]

    target_domain_id = str(pack.get("target_domain_id", "")).strip()
    selected: dict[str, Any] | None = None
    if target_domain_id:
        for row in eligible_domains:
            if str(row.get("domain_id", "")) == target_domain_id:
                selected = row
                break
        if selected is None:
            skip_reasons["TARGET_DOMAIN_NOT_FOUND"] = int(skip_reasons.get("TARGET_DOMAIN_NOT_FOUND", 0)) + 1
            skip_samples.append(
                _skip_sample(
                    domain_id=target_domain_id,
                    reason="TARGET_DOMAIN_NOT_FOUND",
                    detail=f"target_domain_id={target_domain_id} not found",
                )
            )
    elif eligible_domains:
        for row in eligible_domains:
            if str(row.get("domain_id", "")) == "pubchem_weight300":
                selected = row
                break
        if selected is None:
            selected = eligible_domains[0]

    state_root = out_dir.resolve() / "daemon" / "rsi_polymath_conquer_domain_v1" / "state"
    reports_dir = state_root / "reports"
    promotion_dir = state_root / "promotion"
    for path in (reports_dir, promotion_dir):
        path.mkdir(parents=True, exist_ok=True)

    if selected is None:
        _write_no_ready_domain_report(
            reports_dir=reports_dir,
            domains_seen_u64=int(selection_diag.get("domains_seen_u64", 0)),
            domains_active_u64=int(selection_diag.get("domains_active_u64", 0)),
            domains_eligible_u64=int(selection_diag.get("domains_eligible_u64", 0)),
            skip_reasons=skip_reasons,
            skip_samples=skip_samples,
        )
        print("OK")
        return

    domain_id = str(selected.get("domain_id", "")).strip()
    domain_pack_rel = str(selected.get("domain_pack_rel", "")).strip()
    if not domain_id or not domain_pack_rel:
        fail("SCHEMA_FAIL")

    src_domain_root = root / Path(domain_pack_rel).parent
    dst_domain_root = out_dir / Path(domain_pack_rel).parent
    if not src_domain_root.exists() or not src_domain_root.is_dir():
        _write_no_ready_domain_report(
            reports_dir=reports_dir,
            reason_code="MISSING_DOMAIN_PACK",
            domain_id=domain_id,
            domain_pack_rel=domain_pack_rel,
        )
        print("OK")
        return
    _copy_tree(src_domain_root, dst_domain_root)

    domain_pack_path = out_dir / domain_pack_rel
    domain_pack = load_canon_dict(domain_pack_path)
    validate_schema(domain_pack, "polymath_domain_pack_v1")

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

    from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes

    try:
        test_rows = json.loads(load_blob_bytes(sha256=test_sha, store_root=source_store_root).decode("utf-8"))
        train_rows = json.loads(load_blob_bytes(sha256=train_sha, store_root=source_store_root).decode("utf-8"))
    except Exception:  # noqa: BLE001
        _write_no_ready_domain_report(
            reports_dir=reports_dir,
            reason_code="MISSING_STORE_BLOB",
            domain_id=domain_id,
            domain_pack_rel=domain_pack_rel,
        )
        print("OK")
        return
    if not isinstance(test_rows, list):
        fail("SCHEMA_FAIL")
    if not isinstance(train_rows, list):
        fail("SCHEMA_FAIL")
    targets = [int((row or {}).get("target", 0)) for row in test_rows if isinstance(row, dict)]
    train_clean = [row for row in train_rows if isinstance(row, dict)]
    test_clean = [row for row in test_rows if isinstance(row, dict)]
    if len(test_clean) != len(targets):
        fail("SCHEMA_FAIL")
    if not train_clean:
        fail("SCHEMA_FAIL")

    metric_id = str(task.get("metric", "")).strip()

    refinery_cache_hit_b = False
    cached = _load_refinery_cached_config(store_root=source_store_root, domain_id=domain_id, train_sha=train_sha)
    if cached is None:
        selected_search = _search_best_config(train_rows=train_clean, metric_id=metric_id)
        selected_config_id = str(selected_search["config_id"])
        selected_config = dict(selected_search["config"])
        val_metric_q32 = int(selected_search["val_metric_q32"])
    else:
        refinery_cache_hit_b = True
        selected_config_id = str(cached["config_id"])
        selected_config = dict(cached["config"])
        val_metric_q32 = int(cached["val_metric_q32"])

    baseline_preds = _majority_predictions(targets)
    improved_preds, model_complexity_u64 = _nb_predict_with_config(
        train_rows=train_clean,
        test_rows=test_clean,
        token_family=str(selected_config.get("token_family", "")),
        alpha_f64=float(_alpha_from_config(selected_config)),
    )

    baseline_metric_q32 = _metric_q32(metric_id, baseline_preds, targets)
    improved_metric_q32 = _metric_q32(metric_id, improved_preds, targets)

    baseline_outputs = {
        "schema_version": "polymath_candidate_outputs_v1",
        "domain_id": domain_id,
        "task_outputs": [
            {
                "task_id": str(task.get("task_id", "task_classify_v1")),
                "predictions": baseline_preds,
                "reported_metric": {"q": int(baseline_metric_q32)},
            }
        ],
    }
    improved_outputs = {
        "schema_version": "polymath_candidate_outputs_v1",
        "domain_id": domain_id,
        "task_outputs": [
            {
                "task_id": str(task.get("task_id", "task_classify_v1")),
                "predictions": improved_preds,
                "reported_metric": {"q": int(improved_metric_q32)},
            }
        ],
    }

    baseline_outputs_rel = f"domains/{domain_id}/corpus/baseline_outputs_v1.json"
    improved_outputs_rel = f"domains/{domain_id}/corpus/improved_outputs_v1.json"
    write_canon_json(out_dir / baseline_outputs_rel, baseline_outputs)
    write_canon_json(out_dir / improved_outputs_rel, improved_outputs)

    prev_store_env = os.environ.get("OMEGA_POLYMATH_STORE_ROOT")
    if not str(prev_store_env or "").strip():
        os.environ["OMEGA_POLYMATH_STORE_ROOT"] = source_store_root.as_posix()
    try:
        if verify_domain(
            state_dir=state_root,
            domain_pack_path=domain_pack_path,
            candidate_outputs_path=out_dir / baseline_outputs_rel,
        ) != "VALID":
            fail("VERIFY_ERROR")
        if verify_domain(
            state_dir=state_root,
            domain_pack_path=domain_pack_path,
            candidate_outputs_path=out_dir / improved_outputs_rel,
        ) != "VALID":
            fail("VERIFY_ERROR")
    finally:
        if str(prev_store_env or "").strip():
            os.environ["OMEGA_POLYMATH_STORE_ROOT"] = str(prev_store_env)
        else:
            os.environ.pop("OMEGA_POLYMATH_STORE_ROOT", None)

    improved = _metric_improved(metric_id, baseline_metric_q32, improved_metric_q32)
    status = "IMPROVED" if improved else "NO_IMPROVEMENT"

    solver_shadow_rel = f"domains/{domain_id}/solver/shadow_solver_v1.py"
    (out_dir / solver_shadow_rel).write_text(
        _shadow_solver_source(train_sha=train_sha, config_id=selected_config_id, config=selected_config),
        encoding="utf-8",
    )

    portfolio_rel = "polymath/registry/polymath_portfolio_v1.json"
    portfolio_payload = load_or_init_portfolio(root / portfolio_rel)
    conquer_entry(
        portfolio=portfolio_payload,
        domain_id=domain_id,
        train_sha256=train_sha,
        metric_q32=int(improved_metric_q32),
        improved_b=bool(improved),
        cache_hit_b=bool(refinery_cache_hit_b),
        tick_u64=_tick_from_env(),
    )
    write_canon_json(out_dir / portfolio_rel, portfolio_payload)

    report = {
        "schema_version": "polymath_conquer_report_v1",
        "status": status,
        "domain_id": domain_id,
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "domain_pack_rel": domain_pack_rel,
        "metric_id": metric_id,
        "baseline_metric_q32": int(baseline_metric_q32),
        "improved_metric_q32": int(improved_metric_q32),
        "baseline_outputs_rel": baseline_outputs_rel,
        "improved_outputs_rel": improved_outputs_rel,
        "solver_shadow_rel": solver_shadow_rel,
        "domain_registry_rel": "polymath/registry/polymath_domain_registry_v1.json",
        "portfolio_rel": portfolio_rel,
        "val_metric_q32": int(val_metric_q32),
        "selected_config_id": selected_config_id,
        "refinery_cache_hit_b": bool(refinery_cache_hit_b),
        "model_complexity_u64": int(model_complexity_u64),
    }
    write_canon_json(reports_dir / "polymath_conquer_report_v1.json", report)

    require_improvement = bool(pack.get("require_improvement_b", True))
    if require_improvement and not improved:
        print("OK")
        return

    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
    registry_payload = _registry_mark_conquered(rows=domains, domain_id=domain_id, now_iso=now_iso)
    out_registry = out_dir / "polymath" / "registry" / "polymath_domain_registry_v1.json"
    out_registry.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_registry, registry_payload)

    touched_paths = sorted(
        {
            solver_shadow_rel,
            "polymath/registry/polymath_domain_registry_v1.json",
            portfolio_rel,
        }
    )
    bundle = {
        "schema_version": "polymath_conquer_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": "rsi_polymath_conquer_domain_v1",
        "domain_id": domain_id,
        "metric_id": metric_id,
        "baseline_metric_q32": int(baseline_metric_q32),
        "improved_metric_q32": int(improved_metric_q32),
        "activation_key": f"{domain_id}:{int(improved_metric_q32)}",
        "report_rel": "daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json",
        "touched_paths": touched_paths,
    }
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "polymath_conquer_promotion_bundle_v1.json",
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
    parser = argparse.ArgumentParser(prog="campaign_polymath_conquer_domain_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
