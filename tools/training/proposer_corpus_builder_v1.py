#!/usr/bin/env python3
"""Deterministic Step-3A corpus builder (receipts -> SFT + DPO datasets)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from proposer_corpus_schemas_v1 import SchemaValidationError, repo_root, validate_payload
from proposer_redaction_v1 import (
    Q32_HALF,
    Q32_ONE,
    forbidden_path_hits,
    is_toxic_reject_reason,
    pair_weight_q32_for_reason,
    redact_reason_code,
    redaction_policy_material_v1,
    text_forbidden_hits,
    utility_class_from_fields,
)

_SHA256_ZERO = "sha256:" + ("0" * 64)
_ROLE_PATCH_DRAFTER = "PATCH_DRAFTER_V1"
_CANDIDATE_KIND_PATCH = "PATCH"
_CANDIDATE_KIND_EXT = "EXT"

_TRAIN_FRACTION_Q32 = (Q32_ONE * 8) // 10
_VAL_FRACTION_Q32 = Q32_ONE // 10
_TEST_FRACTION_Q32 = Q32_ONE // 10

_TOXIC_PAIR_DROP_CODE = "PAIR_REJECT_TOXIC"


class BuildError(RuntimeError):
    def __init__(self, reason_code: str, *, forbidden_hits: int = 0):
        self.reason_code = str(reason_code)
        self.forbidden_hits = int(max(0, forbidden_hits))
        super().__init__(self.reason_code)


class CorpusBuildResult(dict):
    pass


class TickContext(dict):
    pass


def _canon_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canon_hash_obj(payload: Any) -> str:
    return _sha256_prefixed(_canon_bytes(payload))


def _to_json_line(payload: dict[str, Any]) -> bytes:
    return _canon_bytes(payload) + b"\n"


def _json_dumps_deterministic(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BuildError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        raise BuildError("SCHEMA_FAIL")
    return payload


def _write_canon_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canon_bytes(payload) + b"\n")


def _write_canon_json_immutable(path: Path, payload: dict[str, Any]) -> None:
    data = _canon_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != data:
            raise BuildError("IMMUTABLE_BLOB_CONFLICT")
        return
    path.write_bytes(data)


def _write_blob_immutable(*, blobs_dir: Path, data: bytes, kind: str, ext: str) -> tuple[str, Path]:
    digest = hashlib.sha256(data).hexdigest()
    blob_id = f"sha256:{digest}"
    path = blobs_dir / f"sha256_{digest}.{kind}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != data:
            raise BuildError("IMMUTABLE_BLOB_CONFLICT")
    else:
        path.write_bytes(data)
    return blob_id, path


def _latest(path: Path, pattern: str) -> Path | None:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    return rows[-1] if rows else None


def _pick_json_file(path: Path, *, suffix: str) -> Path | None:
    hashed = _latest(path, f"sha256_*.{suffix}")
    if hashed is not None:
        return hashed
    plain = path / suffix
    if plain.exists() and plain.is_file():
        return plain
    return None


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="proposer_corpus_builder_v1")
    parser.add_argument("--runs_root", required=True)
    parser.add_argument("--out_root", required=True)
    parser.add_argument("--ek_id", required=True)
    parser.add_argument("--kernel_ledger_id", required=True)
    parser.add_argument("--max_runs_u64", type=int, default=5000)
    parser.add_argument("--seed_u64", type=int, default=0)
    return parser.parse_args(argv)


def _assert_out_root(out_root: Path) -> None:
    normalized = out_root.resolve().as_posix()
    if "daemon/proposer_models/datasets" not in normalized:
        raise BuildError("OUT_ROOT_INVALID")


def _deterministic_run_dirs(*, runs_root: Path, max_runs_u64: int, seed_u64: int) -> list[Path]:
    rows = sorted([path for path in runs_root.iterdir() if path.is_dir()], key=lambda p: p.as_posix())
    max_runs = int(max(0, max_runs_u64))
    if max_runs <= 0:
        return []
    if len(rows) <= max_runs:
        return rows

    ranked: list[tuple[str, str, Path]] = []
    for row in rows:
        key = hashlib.sha256(f"{int(seed_u64)}|{row.name}".encode("utf-8")).hexdigest()
        ranked.append((key, row.name, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:max_runs]]


def _resolve_official_promotion_receipt(*, run_dir: Path, dispatch_id: str) -> Path | None:
    if dispatch_id:
        dispatch_promo = run_dir / "state" / "dispatch" / dispatch_id / "promotion"
        path = _pick_json_file(dispatch_promo, suffix="omega_promotion_receipt_v1.json")
        if path is not None:
            return path
    any_dispatch = _latest(run_dir / "state" / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    if any_dispatch is not None:
        return any_dispatch
    return _pick_json_file(run_dir / "promotion", suffix="omega_promotion_receipt_v1.json")


def _find_tick_contexts(run_dir: Path) -> list[TickContext]:
    contexts: list[TickContext] = []
    seen: set[Path] = set()

    subrun_state_dirs = sorted(
        run_dir.glob("state/subruns/*/daemon/rsi_proposer_arena_v1/state"),
        key=lambda p: p.as_posix(),
    )
    for state_dir in subrun_state_dirs:
        state_dir = state_dir.resolve()
        if state_dir in seen:
            continue
        seen.add(state_dir)
        subrun_root = state_dir.parents[2]
        subrun_name = subrun_root.name
        dispatch_id = subrun_name.split("_", 1)[0] if "_" in subrun_name else ""
        promo_path = _resolve_official_promotion_receipt(run_dir=run_dir, dispatch_id=dispatch_id)
        context_id = f"{run_dir.name}:{dispatch_id or subrun_name}"
        contexts.append(
            TickContext(
                run_id=run_dir.name,
                context_id=context_id,
                run_dir=run_dir,
                state_dir=state_dir,
                subrun_root=subrun_root,
                dispatch_id=dispatch_id,
                official_promotion_path=promo_path,
            )
        )

    direct_state = sorted(run_dir.glob("daemon/rsi_proposer_arena_v1/state"), key=lambda p: p.as_posix())
    for state_dir in direct_state:
        state_dir = state_dir.resolve()
        if state_dir in seen:
            continue
        seen.add(state_dir)
        promo_path = _resolve_official_promotion_receipt(run_dir=run_dir, dispatch_id="")
        contexts.append(
            TickContext(
                run_id=run_dir.name,
                context_id=run_dir.name,
                run_dir=run_dir,
                state_dir=state_dir,
                subrun_root=run_dir,
                dispatch_id="",
                official_promotion_path=promo_path,
            )
        )

    contexts.sort(key=lambda row: str(row.get("context_id", "")))
    return contexts


def _resolve_relpath(base_dirs: list[Path], relpath: str) -> Path | None:
    rel = str(relpath).strip().replace("\\", "/")
    if not rel or rel.startswith("/"):
        return None
    for base in base_dirs:
        candidate = (base / rel).resolve()
        try:
            candidate.relative_to(base.resolve())
        except Exception:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _find_arena_run_receipt(state_dir: Path) -> dict[str, Any] | None:
    arena_dir = state_dir / "arena"
    path = _pick_json_file(arena_dir, suffix="proposer_arena_run_receipt_v1.json")
    if path is None:
        return None
    payload = _read_json(path)
    if str(payload.get("schema_version", "")).strip() != "proposer_arena_run_receipt_v1":
        return None
    return payload


def _find_selection_receipt(state_dir: Path) -> dict[str, Any] | None:
    arena_dir = state_dir / "arena"
    path = _pick_json_file(arena_dir, suffix="arena_selection_receipt_v1.json")
    if path is None:
        return None
    payload = _read_json(path)
    if str(payload.get("schema_version", "")).strip() != "arena_selection_receipt_v1":
        return None
    return payload


def _find_winner_candidate_payload(*, state_dir: Path, winner_candidate_id: str) -> dict[str, Any] | None:
    candidates_dir = state_dir / "candidates"
    if not candidates_dir.exists() or not candidates_dir.is_dir():
        return None

    for path in sorted(candidates_dir.glob("*.arena_candidate_v1.json"), key=lambda p: p.as_posix()):
        payload = _read_json(path)
        if str(payload.get("schema_version", "")).strip() != "arena_candidate_v1":
            continue
        if str(payload.get("candidate_id", "")).strip() == winner_candidate_id:
            return payload

    plain = candidates_dir / "arena_candidate_v1.json"
    if plain.exists() and plain.is_file():
        payload = _read_json(plain)
        if str(payload.get("schema_version", "")).strip() == "arena_candidate_v1" and str(payload.get("candidate_id", "")).strip() == winner_candidate_id:
            return payload
    return None


def _load_promotion_bundle(*, state_dir: Path, subrun_root: Path, run_dir: Path, winner_candidate_id: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    promotion_dir = state_dir / "promotion"
    bundle_paths = sorted(promotion_dir.glob("*.omega_promotion_bundle_ccap_v1.json"), key=lambda p: p.as_posix())
    if not bundle_paths:
        raise BuildError("MISSING_PROMOTION_BUNDLE")

    selected_bundle: dict[str, Any] | None = None
    for path in bundle_paths:
        payload = _read_json(path)
        if str(payload.get("schema_version", "")).strip() != "omega_promotion_bundle_ccap_v1":
            continue
        if str(payload.get("activation_key", "")).strip() == winner_candidate_id:
            selected_bundle = payload
            break
    if selected_bundle is None:
        selected_bundle = _read_json(bundle_paths[-1])

    patch_rel = str(selected_bundle.get("patch_relpath", "")).strip()
    ccap_rel = str(selected_bundle.get("ccap_relpath", "")).strip()
    bundle_path_hits = forbidden_path_hits(
        [patch_rel, ccap_rel, *list(selected_bundle.get("touched_paths") or [])]
    )
    if bundle_path_hits:
        raise BuildError("FORBIDDEN_PATH_OR_TEXT_HIT", forbidden_hits=len(bundle_path_hits))

    base_dirs = [promotion_dir.resolve(), subrun_root.resolve(), run_dir.resolve()]
    patch_path = _resolve_relpath(base_dirs, patch_rel)
    if patch_path is None:
        raise BuildError("MISSING_PATCH_BLOB")
    patch_text = patch_path.read_bytes().decode("utf-8", errors="replace")

    ccap_payload: dict[str, Any] | None = None
    ccap_path = _resolve_relpath(base_dirs, ccap_rel)
    if ccap_path is not None:
        ccap_payload = _read_json(ccap_path)

    return selected_bundle, patch_text, ccap_payload


def _load_benchmark_receipts(subrun_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bench_root = subrun_root / "bench"
    if not bench_root.exists() or not bench_root.is_dir():
        return rows

    for path in sorted(bench_root.rglob("*.benchmark_run_receipt_v2.json"), key=lambda p: p.as_posix()):
        payload = _read_json(path)
        if str(payload.get("schema_version", "")).strip() == "benchmark_run_receipt_v2":
            rows.append(payload)
    for path in sorted(bench_root.rglob("benchmark_run_receipt_v2.json"), key=lambda p: p.as_posix()):
        payload = _read_json(path)
        if str(payload.get("schema_version", "")).strip() == "benchmark_run_receipt_v2":
            rows.append(payload)
    return rows


def _load_ccap_receipt_and_refutation(*, run_dir: Path, dispatch_id: str, subrun_root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    candidates: list[Path] = []
    if dispatch_id:
        verifier = run_dir / "state" / "dispatch" / dispatch_id / "verifier"
        candidates.extend([verifier])
    candidates.extend(
        [
            subrun_root / "verifier",
            subrun_root / "ccap",
            run_dir / "verifier",
        ]
    )

    ccap_receipt: dict[str, Any] | None = None
    ccap_refutation: dict[str, Any] | None = None
    for root in candidates:
        if not root.exists() or not root.is_dir():
            continue
        if ccap_receipt is None:
            path = _pick_json_file(root, suffix="ccap_receipt_v1.json")
            if path is not None:
                payload = _read_json(path)
                if str(payload.get("schema_version", "")).strip() == "ccap_receipt_v1":
                    ccap_receipt = payload
        if ccap_refutation is None:
            path = _pick_json_file(root, suffix="ccap_refutation_cert_v1.json")
            if path is not None:
                payload = _read_json(path)
                if str(payload.get("schema_version", "")).strip() == "ccap_refutation_cert_v1":
                    ccap_refutation = payload
    return ccap_receipt, ccap_refutation


def _extract_regime_ids(*, benchmark_receipts: list[dict[str, Any]], ccap_payload: dict[str, Any] | None, fallback_ek_id: str) -> tuple[str, str | None]:
    if benchmark_receipts:
        first = benchmark_receipts[0]
        ek = str(first.get("ek_id", "")).strip()
        ledger = str(first.get("extensions_ledger_id", "")).strip()
        if ek:
            return ek, ledger or None

    if isinstance(ccap_payload, dict):
        meta = ccap_payload.get("meta")
        if isinstance(meta, dict):
            ek = str(meta.get("ek_id", "")).strip()
            if ek:
                return ek, None

    return fallback_ek_id, None


def _official_outcome_and_reason(*, promotion_payload: dict[str, Any], ccap_refutation: dict[str, Any] | None) -> tuple[str, str]:
    result = promotion_payload.get("result")
    status = str((result or {}).get("status", "")).strip().upper()
    outcome = "PROMOTED" if status == "PROMOTED" else "REJECTED"
    reason = (result or {}).get("reason_code")
    if outcome == "REJECTED" and not reason and isinstance(ccap_refutation, dict):
        reason = ccap_refutation.get("refutation_code")
    return outcome, redact_reason_code(reason)


def _candidate_kind(candidate_payload: dict[str, Any], run_payload: dict[str, Any]) -> str:
    raw = str(candidate_payload.get("candidate_kind", run_payload.get("winner_kind", ""))).strip().upper()
    if raw in {"PATCH", "PATCH_PROPOSAL"}:
        return _CANDIDATE_KIND_PATCH
    if raw in {"KERNEL_EXT_PROPOSAL", "EXT", "EXTENSION"}:
        return _CANDIDATE_KIND_EXT
    return raw


def _ensure_no_forbidden(*, paths: list[str], prompt_text: str, response_text: str, serialized: str) -> int:
    hits = forbidden_path_hits(paths)
    text_hits = text_forbidden_hits(prompt_text) + text_forbidden_hits(response_text) + text_forbidden_hits(serialized)
    total_hits = len(set(hits)) + len(set(text_hits))
    if total_hits > 0:
        raise BuildError("FORBIDDEN_PATH_OR_TEXT_HIT", forbidden_hits=total_hits)
    return 0


def _build_prompt_text(*, candidate_kind: str, derived_touched_paths: list[str], recent_reason_codes: list[str], patch_text: str) -> str:
    derived = _json_dumps_deterministic(sorted(derived_touched_paths))
    reasons = _json_dumps_deterministic(list(recent_reason_codes))
    return (
        f"candidate_kind={candidate_kind}\n"
        f"derived_touched_paths={derived}\n"
        f"recent_reason_codes={reasons}\n"
        "context_patch_begin\n"
        f"{patch_text}\n"
        "context_patch_end\n"
    )


def _example_id_material(*, prompt_text: str, response_text: str, label: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_text": prompt_text,
        "response_text": response_text,
        "label": label,
        "metadata": metadata,
    }


def _build_single_example(
    *,
    context: TickContext,
    ek_filter: str,
    ledger_filter: str,
    recent_reason_codes: list[str],
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    state_dir = Path(str(context["state_dir"]))
    run_dir = Path(str(context["run_dir"]))
    subrun_root = Path(str(context["subrun_root"]))

    promo_path = context.get("official_promotion_path")
    if not isinstance(promo_path, Path) or not promo_path.exists():
        return None, None, "MISSING_PROMOTION_RECEIPT"
    promotion_payload = _read_json(promo_path)

    run_payload = _find_arena_run_receipt(state_dir)
    if run_payload is None:
        return None, None, "MISSING_ARENA_RUN_RECEIPT"

    winner_candidate_id = str(run_payload.get("winner_candidate_id", "")).strip()
    if not winner_candidate_id:
        return None, None, "MISSING_WINNER_CANDIDATE"

    selection_payload = _find_selection_receipt(state_dir)
    inputs_descriptor_id = str((selection_payload or {}).get("inputs_descriptor_id", _SHA256_ZERO)).strip() or _SHA256_ZERO

    candidate_payload = _find_winner_candidate_payload(state_dir=state_dir, winner_candidate_id=winner_candidate_id)
    if candidate_payload is None:
        return None, None, "MISSING_WINNER_CANDIDATE_PAYLOAD"

    bundle_payload, patch_text, ccap_payload = _load_promotion_bundle(
        state_dir=state_dir,
        subrun_root=subrun_root,
        run_dir=run_dir,
        winner_candidate_id=winner_candidate_id,
    )

    benchmark_receipts = _load_benchmark_receipts(subrun_root)
    _ccap_receipt, ccap_refutation = _load_ccap_receipt_and_refutation(
        run_dir=run_dir,
        dispatch_id=str(context.get("dispatch_id", "")),
        subrun_root=subrun_root,
    )

    extracted_ek_id, extracted_ledger_id = _extract_regime_ids(
        benchmark_receipts=benchmark_receipts,
        ccap_payload=ccap_payload,
        fallback_ek_id=str((promotion_payload.get("result") or {}).get("ek_id", "")).strip() or ek_filter,
    )

    if extracted_ek_id != ek_filter:
        return None, None, "REGIME_FILTER_EK_MISMATCH"
    if extracted_ledger_id != ledger_filter:
        return None, None, "REGIME_FILTER_LEDGER_MISMATCH"

    outcome, redacted_reason = _official_outcome_and_reason(promotion_payload=promotion_payload, ccap_refutation=ccap_refutation)

    agent_id = str(run_payload.get("winner_agent_id", candidate_payload.get("agent_id", ""))).strip()
    if not agent_id:
        agent_id = "unknown_agent"

    candidate_kind = _candidate_kind(candidate_payload, run_payload)
    if candidate_kind != _CANDIDATE_KIND_PATCH:
        return None, redacted_reason, "UNSUPPORTED_CANDIDATE_KIND"

    declared_touched_paths = sorted(str(row) for row in list(candidate_payload.get("declared_touched_paths") or []))
    derived_touched_paths = sorted(str(row) for row in list(candidate_payload.get("derived_touched_paths") or []))

    prompt_text = _build_prompt_text(
        candidate_kind=candidate_kind,
        derived_touched_paths=derived_touched_paths,
        recent_reason_codes=recent_reason_codes,
        patch_text=patch_text,
    )
    response_text = patch_text

    declared_class = promotion_payload.get("declared_class")
    effect_class = promotion_payload.get("effect_class")
    utility_class = utility_class_from_fields(declared_class=declared_class, effect_class=effect_class)

    weight_q32 = Q32_ONE if outcome == "PROMOTED" else pair_weight_q32_for_reason(redacted_reason)

    label = {
        "official_outcome": outcome,
        "official_reason_code": redacted_reason,
        "utility_class": utility_class,
        "weight_q32": int(weight_q32),
    }
    metadata = {
        "candidate_kind": candidate_kind,
        "declared_touched_paths": declared_touched_paths,
        "derived_touched_paths": derived_touched_paths,
    }

    example_id = _canon_hash_obj(
        _example_id_material(
            prompt_text=prompt_text,
            response_text=response_text,
            label=label,
            metadata=metadata,
        )
    )

    payload = {
        "schema_version": "proposer_sft_example_v1",
        "example_id": example_id,
        "role": _ROLE_PATCH_DRAFTER,
        "inputs_descriptor_id": inputs_descriptor_id,
        "agent_id": agent_id,
        "candidate_id": winner_candidate_id,
        "ek_id": extracted_ek_id,
        "kernel_ledger_id": extracted_ledger_id,
        "prompt_text": prompt_text,
        "response_text": response_text,
        "label": label,
        "metadata": metadata,
    }

    serialized = _json_dumps_deterministic(payload)
    _ensure_no_forbidden(
        paths=(declared_touched_paths + derived_touched_paths + [str(bundle_payload.get("patch_relpath", "")), str(bundle_payload.get("ccap_relpath", ""))]),
        prompt_text=prompt_text,
        response_text=response_text,
        serialized=serialized,
    )

    validate_payload(payload, "proposer_sft_example_v1")
    return payload, redacted_reason, None


def _group_key_for_example(example: dict[str, Any]) -> str:
    return _canon_hash_obj(
        {
            "ek_id": str(example.get("ek_id", "")),
            "kernel_ledger_id": str(example.get("kernel_ledger_id", "")),
            "role": str(example.get("role", "")),
            "derived_touched_paths": sorted(
                str(row)
                for row in list(
                    ((example.get("metadata") or {}).get("derived_touched_paths") or [])
                )
            ),
        }
    )


def _build_dpo_pairs(sft_examples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sft_examples:
        grouped[_group_key_for_example(row)].append(row)

    pairs: list[dict[str, Any]] = []
    drop_hist = Counter()

    for group_key in sorted(grouped.keys()):
        rows = grouped[group_key]
        chosen = sorted(
            [row for row in rows if str((row.get("label") or {}).get("official_outcome", "")) == "PROMOTED"],
            key=lambda row: str(row.get("example_id", "")),
        )
        rejected_all = sorted(
            [row for row in rows if str((row.get("label") or {}).get("official_outcome", "")) == "REJECTED"],
            key=lambda row: str(row.get("example_id", "")),
        )

        rejected: list[dict[str, Any]] = []
        for row in rejected_all:
            reason = str((row.get("label") or {}).get("official_reason_code", "")).strip()
            if is_toxic_reject_reason(reason):
                drop_hist[_TOXIC_PAIR_DROP_CODE] += 1
                continue
            rejected.append(row)

        if not chosen or not rejected:
            continue

        for chosen_row in chosen:
            for rejected_row in rejected[:4]:
                pair_weight_q32 = pair_weight_q32_for_reason((rejected_row.get("label") or {}).get("official_reason_code"))
                pair_payload = {
                    "schema_version": "proposer_dpo_pair_v1",
                    "pair_id": _SHA256_ZERO,
                    "role": str(chosen_row.get("role", "")),
                    "ek_id": str(chosen_row.get("ek_id", "")),
                    "kernel_ledger_id": str(chosen_row.get("kernel_ledger_id", "")),
                    "group_key": group_key,
                    "prompt_text": str(chosen_row.get("prompt_text", "")),
                    "chosen_response_text": str(chosen_row.get("response_text", "")),
                    "rejected_response_text": str(rejected_row.get("response_text", "")),
                    "pair_weight_q32": int(pair_weight_q32),
                    "chosen_example_id": str(chosen_row.get("example_id", "")),
                    "rejected_example_id": str(rejected_row.get("example_id", "")),
                }
                pair_payload["pair_id"] = _canon_hash_obj({k: v for k, v in pair_payload.items() if k != "pair_id"})
                validate_payload(pair_payload, "proposer_dpo_pair_v1")
                pairs.append(pair_payload)

    pairs.sort(key=lambda row: str(row.get("pair_id", "")))
    return pairs, drop_hist


def _runs_root_rel(runs_root: Path) -> str:
    root = repo_root().resolve()
    abs_runs = runs_root.resolve()
    try:
        return abs_runs.relative_to(root).as_posix()
    except Exception:
        return abs_runs.as_posix()


def _build_manifest(
    *,
    corpus_id: str,
    build_config_id: str,
    runs_root_rel: str,
    included_run_ids: list[str],
    ek_id: str,
    kernel_ledger_id: str,
    sft_count: int,
    dpo_count: int,
    sft_blob_id: str,
    dpo_blob_id: str,
    redaction_policy_id: str,
) -> dict[str, Any]:
    manifest = {
        "schema_version": "proposer_training_corpus_manifest_v1",
        "corpus_id": corpus_id,
        "build_config_id": build_config_id,
        "runs_root_rel": runs_root_rel,
        "included_run_ids": included_run_ids,
        "ek_id": ek_id,
        "kernel_ledger_id": kernel_ledger_id,
        "counts": {
            "sft_examples_u64": int(max(0, sft_count)),
            "dpo_pairs_u64": int(max(0, dpo_count)),
        },
        "splits": {
            "train_fraction_q32": int(_TRAIN_FRACTION_Q32),
            "val_fraction_q32": int(_VAL_FRACTION_Q32),
            "test_fraction_q32": int(_TEST_FRACTION_Q32),
        },
        "sft_examples_blob_id": sft_blob_id,
        "dpo_pairs_blob_id": dpo_blob_id,
        "redaction_policy_id": redaction_policy_id,
        "hashes": {
            "sft_examples_sha256": sft_blob_id,
            "dpo_pairs_sha256": dpo_blob_id,
        },
    }
    validate_payload(manifest, "proposer_training_corpus_manifest_v1")
    return manifest


def _write_receipt(*, manifests_dir: Path, payload: dict[str, Any]) -> Path:
    validate_payload(payload, "proposer_corpus_build_receipt_v1")
    receipt_hash = _canon_hash_obj(payload)
    receipt_path = manifests_dir / f"sha256_{receipt_hash.split(':', 1)[1]}.proposer_corpus_build_receipt_v1.json"
    _write_canon_json_immutable(receipt_path, payload)
    return receipt_path


def build_corpus(*, args: argparse.Namespace) -> CorpusBuildResult:
    runs_root = Path(str(args.runs_root)).resolve()
    out_root = Path(str(args.out_root)).resolve()
    ek_id = str(args.ek_id).strip()
    kernel_ledger_id = str(args.kernel_ledger_id).strip()
    max_runs_u64 = int(max(0, int(args.max_runs_u64)))
    seed_u64 = int(max(0, int(args.seed_u64)))

    if not runs_root.exists() or not runs_root.is_dir():
        raise BuildError("MISSING_RUNS_ROOT")
    _assert_out_root(out_root)

    blobs_dir = out_root / "blobs" / "sha256"
    manifests_dir = out_root / "manifests"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    selected_run_dirs = _deterministic_run_dirs(runs_root=runs_root, max_runs_u64=max_runs_u64, seed_u64=seed_u64)

    all_contexts: list[TickContext] = []
    for run_dir in selected_run_dirs:
        all_contexts.extend(_find_tick_contexts(run_dir))
    all_contexts.sort(key=lambda row: str(row.get("context_id", "")))

    sft_examples: list[dict[str, Any]] = []
    drop_hist = Counter()
    forbidden_path_hits_u64 = 0
    included_run_ids: list[str] = []
    recent_reason_codes: list[str] = []

    for context in all_contexts:
        try:
            example, reason_for_history, drop_reason = _build_single_example(
                context=context,
                ek_filter=ek_id,
                ledger_filter=kernel_ledger_id,
                recent_reason_codes=list(recent_reason_codes),
            )
        except BuildError as exc:
            if exc.reason_code == "FORBIDDEN_PATH_OR_TEXT_HIT":
                forbidden_path_hits_u64 += int(max(1, exc.forbidden_hits))
                raise
            drop_hist[exc.reason_code] += 1
            continue

        if reason_for_history:
            recent_reason_codes.append(str(reason_for_history))

        if drop_reason:
            drop_hist[drop_reason] += 1
            continue

        if example is None:
            drop_hist["DROP_UNKNOWN"] += 1
            continue

        validate_payload(example, "proposer_sft_example_v1")
        sft_examples.append(example)
        included_run_ids.append(str(context.get("run_id", "")))

    sft_examples.sort(key=lambda row: str(row.get("example_id", "")))

    dpo_pairs, dpo_drop_hist = _build_dpo_pairs(sft_examples)
    drop_hist.update(dpo_drop_hist)

    sft_bytes = b"".join(_to_json_line(row) for row in sft_examples)
    dpo_bytes = b"".join(_to_json_line(row) for row in dpo_pairs)

    (out_root / "sft_examples.jsonl").write_bytes(sft_bytes)
    (out_root / "dpo_pairs.jsonl").write_bytes(dpo_bytes)

    sft_text = sft_bytes.decode("utf-8", errors="replace")
    dpo_text = dpo_bytes.decode("utf-8", errors="replace")
    forbidden_text_hits_count = len(text_forbidden_hits(sft_text)) + len(text_forbidden_hits(dpo_text))
    forbidden_path_hits_u64 += int(max(0, forbidden_text_hits_count))
    if forbidden_path_hits_u64 > 0:
        raise BuildError("FORBIDDEN_PATH_OR_TEXT_HIT", forbidden_hits=forbidden_path_hits_u64)

    sft_blob_id, sft_blob_path = _write_blob_immutable(
        blobs_dir=blobs_dir,
        data=sft_bytes,
        kind="proposer_sft_examples_v1",
        ext="jsonl",
    )
    dpo_blob_id, dpo_blob_path = _write_blob_immutable(
        blobs_dir=blobs_dir,
        data=dpo_bytes,
        kind="proposer_dpo_pairs_v1",
        ext="jsonl",
    )

    build_config_material = {
        "schema_version": "proposer_corpus_build_config_v1",
        "runs_root_rel": _runs_root_rel(runs_root),
        "ek_id": ek_id,
        "kernel_ledger_id": kernel_ledger_id,
        "max_runs_u64": max_runs_u64,
        "seed_u64": seed_u64,
    }
    build_config_id = _canon_hash_obj(build_config_material)
    redaction_policy_id = _canon_hash_obj(redaction_policy_material_v1())

    manifest_payload = _build_manifest(
        corpus_id=_SHA256_ZERO,
        build_config_id=build_config_id,
        runs_root_rel=_runs_root_rel(runs_root),
        included_run_ids=sorted(set(included_run_ids)),
        ek_id=ek_id,
        kernel_ledger_id=kernel_ledger_id,
        sft_count=len(sft_examples),
        dpo_count=len(dpo_pairs),
        sft_blob_id=sft_blob_id,
        dpo_blob_id=dpo_blob_id,
        redaction_policy_id=redaction_policy_id,
    )

    corpus_id = _canon_hash_obj({k: v for k, v in manifest_payload.items() if k != "corpus_id"})
    manifest_payload["corpus_id"] = corpus_id
    validate_payload(manifest_payload, "proposer_training_corpus_manifest_v1")

    manifest_path = manifests_dir / f"sha256_{corpus_id.split(':', 1)[1]}.proposer_training_corpus_manifest_v1.json"
    _write_canon_json_immutable(manifest_path, manifest_payload)

    receipt_payload = {
        "schema_version": "proposer_corpus_build_receipt_v1",
        "corpus_id": corpus_id,
        "status": "OK",
        "reason_code": "OK",
        "dropped_rows_u64": int(sum(drop_hist.values())),
        "drop_reason_histogram": {k: int(v) for k, v in sorted(drop_hist.items())},
        "forbidden_path_hits_u64": int(forbidden_path_hits_u64),
    }
    receipt_path = _write_receipt(manifests_dir=manifests_dir, payload=receipt_payload)

    return CorpusBuildResult(
        corpus_id=corpus_id,
        manifest_path=manifest_path,
        receipt_path=receipt_path,
        sft_blob_path=sft_blob_path,
        dpo_blob_path=dpo_blob_path,
        sft_examples_u64=len(sft_examples),
        dpo_pairs_u64=len(dpo_pairs),
    )


def _fail_and_write_receipt(*, out_root: Path, reason_code: str, forbidden_hits: int, dropped_rows_u64: int, drop_hist: Counter[str]) -> Path:
    manifests_dir = out_root / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "proposer_corpus_build_receipt_v1",
        "corpus_id": _SHA256_ZERO,
        "status": "FAIL",
        "reason_code": str(reason_code),
        "dropped_rows_u64": int(max(0, dropped_rows_u64)),
        "drop_reason_histogram": {k: int(v) for k, v in sorted(drop_hist.items())},
        "forbidden_path_hits_u64": int(max(0, forbidden_hits)),
    }
    return _write_receipt(manifests_dir=manifests_dir, payload=payload)


def main(argv: list[str] | None = None) -> int:
    parsed = _parse_args(argv if argv is not None else sys.argv[1:])
    out_root = Path(str(parsed.out_root)).resolve()

    drop_hist = Counter()
    try:
        result = build_corpus(args=parsed)
        print(
            _json_dumps_deterministic(
                {
                    "status": "OK",
                    "corpus_id": result["corpus_id"],
                    "manifest_path": str(result["manifest_path"]),
                    "receipt_path": str(result["receipt_path"]),
                    "sft_examples_u64": int(result["sft_examples_u64"]),
                    "dpo_pairs_u64": int(result["dpo_pairs_u64"]),
                }
            )
        )
        return 0
    except (BuildError, SchemaValidationError) as exc:
        reason_code = str(exc)
        forbidden_hits = int(getattr(exc, "forbidden_hits", 0))
        drop_hist[reason_code] += 1
        receipt_path = _fail_and_write_receipt(
            out_root=out_root,
            reason_code=reason_code,
            forbidden_hits=forbidden_hits,
            dropped_rows_u64=sum(drop_hist.values()),
            drop_hist=drop_hist,
        )
        print(
            _json_dumps_deterministic(
                {
                    "status": "FAIL",
                    "reason_code": reason_code,
                    "receipt_path": str(receipt_path),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
