#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cdel.adoption.storage import read_head as read_adoption_head
from cdel.adoption.verifier import commit_adoption
from cdel.config import load_config_from_path
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.config import load_sealed_config
from cdel.sealed.crypto import key_id_from_public_key, public_key_from_private
from cdel.sealed.evalue import encoded_evalue_to_decimal, parse_decimal, parse_evalue
from cdel.sealed.harnesses import get_harness
from cdel.sealed.worker import issue_stat_cert, _require_matching_types


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concept", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--dev-config", required=True)
    parser.add_argument("--heldout-config", required=True)
    parser.add_argument("--seed-key", required=True)
    parser.add_argument("--min-dev-diff-sum", type=int, required=True)
    parser.add_argument("--request-out", required=True)
    parser.add_argument("--signed-cert-out", required=True)
    parser.add_argument("--module-out", required=True)
    parser.add_argument("--candidate-module", default=None)
    parser.add_argument("--heldout-suites-dir", default=None)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dev_cfg = load_config_from_path(root, Path(args.dev_config).resolve())
    heldout_cfg = load_config_from_path(root, Path(args.heldout_config).resolve())
    dev_sealed = load_sealed_config(dev_cfg.data, require_keys=False)
    heldout_sealed = load_sealed_config(heldout_cfg.data, require_keys=False)

    dev_episodes = _require_episodes(dev_cfg.data, "dev")
    heldout_episodes = _require_episodes(heldout_cfg.data, "heldout")
    dev_max_steps = int((dev_cfg.data.get("evaluator") or {}).get("step_limit", 100000))
    heldout_max_steps = int((heldout_cfg.data.get("evaluator") or {}).get("step_limit", 100000))

    private_key = os.environ.get("CDEL_SEALED_PRIVKEY")
    if not private_key:
        raise SystemExit("CDEL_SEALED_PRIVKEY is required for heldout issuance")

    heldout_cfg.data["sealed"]["public_key"] = public_key_from_private(private_key)
    heldout_cfg.data["sealed"]["key_id"] = key_id_from_public_key(heldout_cfg.data["sealed"]["public_key"])

    candidate_payload, extra_defs = _load_candidate_payload(args.candidate_module, Path(args.module_out))

    conn = idx.connect(str(heldout_cfg.sqlite_path))
    idx.init_schema(conn)
    if idx.symbol_exists(conn, args.candidate):
        raise SystemExit("candidate already exists in ledger; provide an uncommitted candidate module")

    symbols = [args.baseline, args.oracle]
    for name in symbols:
        if not idx.symbol_exists(conn, name):
            raise SystemExit(f"symbol not found in ledger: {name}")
    defs = load_definitions(heldout_cfg, conn, symbols)
    defs.update(extra_defs)

    _require_matching_types(defs[args.baseline], defs[args.candidate], defs[args.oracle])

    _require_candidate_tag(candidate_payload, args.concept, args.candidate)

    dev_eval_cfg = {
        "episodes": dev_episodes,
        "max_steps": dev_max_steps,
        "paired_seeds": True,
        "oracle_symbol": args.oracle,
        "eval_harness_id": dev_sealed.eval_harness_id,
        "eval_harness_hash": dev_sealed.eval_harness_hash,
        "eval_suite_hash": dev_sealed.eval_suite_hash,
    }
    _run_dev_eval(
        root,
        dev_eval_cfg,
        dev_cfg.data,
        defs,
        args.baseline,
        args.candidate,
        args.oracle,
        args.seed_key.encode("utf-8"),
        args.min_dev_diff_sum,
    )

    heldout_request = {
        "kind": "stat_cert",
        "concept": args.concept,
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": args.baseline,
        "candidate_symbol": args.candidate,
        "eval": {
            "episodes": heldout_episodes,
            "max_steps": heldout_max_steps,
            "paired_seeds": True,
            "oracle_symbol": args.oracle,
        },
        "risk": {"evalue_threshold": "1"},
    }
    _write_json(Path(args.request_out), heldout_request)

    heldout_suites_dir = Path(args.heldout_suites_dir).resolve() if args.heldout_suites_dir else None
    if heldout_suites_dir is not None and not heldout_suites_dir.exists():
        raise SystemExit("heldout suites dir not found")

    if heldout_suites_dir is None:
        cert = issue_stat_cert(
            heldout_cfg,
            heldout_request,
            private_key,
            args.seed_key.encode("utf-8"),
            extra_defs=extra_defs,
        )
    else:
        with _temp_env("CDEL_SUITES_DIR", str(heldout_suites_dir)):
            cert = issue_stat_cert(
                heldout_cfg,
                heldout_request,
                private_key,
                args.seed_key.encode("utf-8"),
                extra_defs=extra_defs,
            )
    _write_json(Path(args.signed_cert_out), cert)

    if not _passes_threshold(cert):
        raise SystemExit("heldout certificate below threshold")

    module = _assemble_module(heldout_cfg, candidate_payload, cert, args.baseline, args.oracle)
    result = commit_module(heldout_cfg, module)
    if not result.ok:
        reason = result.rejection.reason if result.rejection else "commit failed"
        raise SystemExit(reason)

    baseline_for_adoption = _current_adoption_baseline(heldout_cfg, args.concept, args.baseline)
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(heldout_cfg),
        "payload": {
            "concept": args.concept,
            "chosen_symbol": args.candidate,
            "baseline_symbol": baseline_for_adoption,
            "certificate": cert,
            "constraints": {},
        },
    }
    adopt_result = commit_adoption(heldout_cfg, adoption)
    if not adopt_result.ok:
        reason = adopt_result.rejection.reason if adopt_result.rejection else "adoption failed"
        raise SystemExit(reason)

    _write_json(Path(args.module_out), module)


def _require_episodes(data: dict, label: str) -> int:
    sealed = data.get("sealed") or {}
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError(f"{label} sealed.episodes must be positive int")
    return episodes


def _load_candidate_payload(candidate_module: str | None, module_out: Path) -> tuple[dict, dict]:
    path = Path(candidate_module) if candidate_module else module_out
    if not path.exists():
        raise SystemExit("candidate module required for promotion")
    payload = _load_payload(path)
    defs_raw = payload.get("definitions") or []
    if not isinstance(defs_raw, list) or not defs_raw:
        raise SystemExit("candidate module definitions missing")
    defs = {}
    for defn in defs_raw:
        parsed = parse_definition(defn)
        defs[parsed.name] = parsed
    return payload, defs


def _require_candidate_tag(payload: dict, concept: str, candidate: str) -> None:
    concepts = payload.get("concepts") or []
    if not any(
        isinstance(entry, dict)
        and entry.get("concept") == concept
        and entry.get("symbol") == candidate
        for entry in concepts
    ):
        raise SystemExit("candidate module missing concept tag")


def _run_dev_eval(
    root: Path,
    eval_cfg: dict,
    cfg_data: dict,
    defs: dict[str, object],
    baseline: str,
    candidate: str,
    oracle: str,
    seed_key: bytes,
    min_diff_sum: int,
) -> None:
    harness = get_harness(eval_cfg["eval_harness_id"])
    if harness.harness_hash != eval_cfg["eval_harness_hash"]:
        raise SystemExit("dev eval_harness_hash mismatch")

    domain = cfg_data.get("spec") or {}
    int_min = int(domain.get("int_min", -3))
    int_max = int(domain.get("int_max", 3))
    list_max_len = int(domain.get("list_max_len", 4))

    with _temp_env("CDEL_SUITES_DIR", None):
        diffs, _, _, _ = harness.run_episodes(
            eval_cfg=eval_cfg,
            defs_env=defs,
            baseline_symbol=baseline,
            candidate_symbol=candidate,
            oracle_symbol=oracle,
            seed_key=seed_key,
            project_root=root,
            int_min=int_min,
            int_max=int_max,
            list_max_len=list_max_len,
            fun_symbols=[],
            artifact_dir=None,
        )

    diff_sum = sum(diffs)
    if diff_sum < min_diff_sum:
        raise SystemExit(f"dev diff_sum {diff_sum} below threshold {min_diff_sum}")


def _passes_threshold(cert: dict) -> bool:
    risk = cert.get("risk") or {}
    alpha_i = parse_decimal(str(risk.get("alpha_i")))
    threshold = parse_decimal(str(risk.get("evalue_threshold")))
    payload = cert.get("certificate") or {}
    evalue = parse_evalue(payload.get("evalue"), "promotion evalue")
    return encoded_evalue_to_decimal(evalue) * alpha_i >= threshold


def _assemble_module(cfg, payload: dict, cert: dict, baseline: str, oracle: str) -> dict:
    specs = list(payload.get("specs") or [])
    specs.append(cert)
    declared_deps = list(payload.get("declared_deps") or [])
    for name in (baseline, oracle):
        if name not in declared_deps:
            declared_deps.append(name)
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            **payload,
            "specs": specs,
            "declared_deps": declared_deps,
        },
    }


def _current_adoption_baseline(cfg, concept: str, baseline: str) -> str | None:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    current = idx.latest_adoption_for_concept(conn, concept)
    if current is None:
        return None
    current_symbol = current.get("chosen_symbol")
    if current_symbol != baseline:
        raise SystemExit("baseline does not match current adoption")
    return current_symbol


def _load_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "payload" in payload:
        payload = payload["payload"]
    if not isinstance(payload, dict):
        raise SystemExit("candidate module payload must be an object")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


@contextmanager
def _temp_env(key: str, value: str | None):
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


if __name__ == "__main__":
    main()
