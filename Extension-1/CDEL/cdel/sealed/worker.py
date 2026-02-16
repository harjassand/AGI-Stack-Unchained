"""Sealed evaluator worker for stat_cert certificates."""

from __future__ import annotations

import argparse
import json
import os
import random
from hashlib import blake2b
from pathlib import Path

from blake3 import blake3

from cdel.config import load_config
from cdel.kernel.eval import (
    BoolVal,
    Evaluator,
    EvalError,
    FunVal,
    IntVal,
    ListVal,
    OptionVal,
    PairVal,
    Value,
)
from cdel.kernel.types import BOOL, INT, FunType, ListType, OptionType, PairType, Type, type_norm
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions
from cdel.sealed.config import load_sealed_config
from cdel.sealed.crypto import key_id_from_public_key, public_key_from_private, sign_bytes
from cdel.sealed.evalue import alpha_for_round, encode_evalue, format_decimal, hoeffding_mixture_evalue, parse_alpha_schedule
from cdel.sealed.protocol import stat_cert_signing_bytes


def main() -> None:
    parser = argparse.ArgumentParser(prog="cdel-sealed-worker")
    parser.add_argument("--root", default=".", help="project root")
    parser.add_argument("--request", default="-", help="stat_cert JSON (or '-' for stdin)")
    parser.add_argument("--out", default="-", help="output path (or '-' for stdout)")
    parser.add_argument("--private-key", default=None, help="base64 ed25519 private key")
    parser.add_argument("--seed-key", default=None, help="seed key for episode generation")
    parser.add_argument("--artifact-dir", default=None, help="write per-episode artifacts for audit")
    parser.add_argument("--candidate-module", default=None, help="module JSON with candidate definitions")
    args = parser.parse_args()

    cfg = load_config(Path(args.root).resolve())
    request = _load_json(args.request)
    private_key = args.private_key or os.environ.get("CDEL_SEALED_PRIVKEY")
    if not private_key:
        raise SystemExit("missing private key (use --private-key or CDEL_SEALED_PRIVKEY)")
    seed_key = args.seed_key or os.environ.get("CDEL_SEALED_SEED")
    if not seed_key:
        raise SystemExit("missing seed key (use --seed-key or CDEL_SEALED_SEED)")

    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else None
    extra_defs = _load_candidate_defs(args.candidate_module) if args.candidate_module else None
    result = issue_stat_cert(
        cfg,
        request,
        private_key,
        seed_key.encode("utf-8"),
        artifact_dir=artifact_dir,
        extra_defs=extra_defs,
    )
    _write_json(args.out, result)


def issue_stat_cert(
    cfg,
    spec: dict,
    private_key: str,
    seed_key: bytes,
    artifact_dir: Path | None = None,
    extra_defs: dict[str, object] | None = None,
) -> dict:
    if spec.get("kind") != "stat_cert":
        raise ValueError("request must be stat_cert spec")
    concept = spec.get("concept")
    if not isinstance(concept, str) or not concept:
        raise ValueError("stat_cert concept missing")
    sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
    baseline = spec.get("baseline_symbol")
    candidate = spec.get("candidate_symbol")
    eval_cfg = spec.get("eval") or {}
    if not isinstance(eval_cfg, dict):
        raise ValueError("eval must be object")
    oracle = eval_cfg.get("oracle_symbol")
    if not isinstance(baseline, str) or not isinstance(candidate, str) or not isinstance(oracle, str):
        raise ValueError("baseline/candidate/oracle must be strings")

    episodes = eval_cfg.get("episodes")
    max_steps = eval_cfg.get("max_steps")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError("eval episodes must be positive int")
    if not isinstance(max_steps, int) or max_steps <= 0:
        raise ValueError("eval max_steps must be positive int")
    paired = eval_cfg.get("paired_seeds")
    if not isinstance(paired, bool):
        raise ValueError("eval paired_seeds must be bool")

    eval_cfg = _fill_eval_config(eval_cfg, sealed_cfg)
    fun_symbols_raw = eval_cfg.get("fun_symbols")
    fun_symbols: list[str] = []
    if fun_symbols_raw is not None:
        if not isinstance(fun_symbols_raw, list) or any(not isinstance(item, str) for item in fun_symbols_raw):
            raise ValueError("eval fun_symbols must be a list of strings")
        fun_symbols = list(fun_symbols_raw)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    symbols = []
    for name in (baseline, candidate, oracle):
        if idx.symbol_exists(conn, name):
            symbols.append(name)
    defs = load_definitions(cfg, conn, symbols) if symbols else {}
    if extra_defs:
        defs.update(extra_defs)
    for name in (baseline, candidate, oracle):
        if name not in defs:
            raise ValueError(f"symbol not found: {name}")
    baseline_def = defs[baseline]
    candidate_def = defs[candidate]
    oracle_def = defs[oracle]
    _require_matching_types(baseline_def, candidate_def, oracle_def)

    domain = cfg.data.get("spec") or {}
    int_min = int(domain.get("int_min", -3))
    int_max = int(domain.get("int_max", 3))
    list_max_len = int(domain.get("list_max_len", 4))

    baseline_successes = 0
    candidate_successes = 0
    diffs: list[int] = []
    artifact_rows: list[dict] | None = [] if artifact_dir is not None else None
    for episode in range(episodes):
        rng = random.Random(_episode_seed(seed_key, baseline, candidate, oracle, episode))
        args = [
            _random_value(param.typ, rng, int_min, int_max, list_max_len, fun_symbols)
            for param in oracle_def.params
        ]
        oracle_val = _safe_apply(oracle, args, defs, max_steps)
        baseline_val = _safe_apply(baseline, args, defs, max_steps)
        candidate_val = _safe_apply(candidate, args, defs, max_steps)
        baseline_correct = oracle_val is not None and baseline_val == oracle_val
        candidate_correct = oracle_val is not None and candidate_val == oracle_val
        if baseline_correct:
            baseline_successes += 1
        if candidate_correct:
            candidate_successes += 1
        diff = int(candidate_correct) - int(baseline_correct)
        diffs.append(diff)
        if artifact_rows is not None:
            artifact_rows.append(
                {
                    "episode": episode,
                    "baseline_correct": baseline_correct,
                    "candidate_correct": candidate_correct,
                    "diff": diff,
                }
            )

    diff_sum = sum(diffs)
    diff_min = -1
    diff_max = 1
    evalue = hoeffding_mixture_evalue(diff_sum, episodes)
    encoded_evalue = encode_evalue(evalue)
    transcript_hash = blake3(_encode_diffs(diffs)).hexdigest()
    if artifact_dir is not None:
        _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

    cert = {
        "evalue_schema_version": 2,
        "n": episodes,
        "baseline_successes": baseline_successes,
        "candidate_successes": candidate_successes,
        "diff_sum": diff_sum,
        "diff_min": diff_min,
        "diff_max": diff_max,
        "evalue": encoded_evalue.to_dict(),
        "transcript_hash": transcript_hash,
        "signature": "",
        "signature_scheme": "ed25519",
        "key_id": key_id_from_public_key(public_key_from_private(private_key)),
    }
    risk = _fill_risk(spec.get("risk"), sealed_cfg, conn)
    out = dict(spec)
    out["eval"] = eval_cfg
    out["risk"] = risk
    out["certificate"] = cert
    signing_bytes = stat_cert_signing_bytes(out)
    cert["signature"] = sign_bytes(private_key, signing_bytes)
    return out


def _require_matching_types(baseline, candidate, oracle) -> None:
    baseline_type = FunType(tuple(p.typ for p in baseline.params), baseline.ret_type)
    candidate_type = FunType(tuple(p.typ for p in candidate.params), candidate.ret_type)
    oracle_type = FunType(tuple(p.typ for p in oracle.params), oracle.ret_type)
    if baseline_type != candidate_type or baseline_type != oracle_type:
        raise ValueError(
            "type mismatch: "
            f"{type_norm(baseline_type)} vs {type_norm(candidate_type)} vs {type_norm(oracle_type)}"
        )


def _safe_apply(symbol: str, args: list[Value], defs: dict, max_steps: int) -> Value | None:
    evaluator = Evaluator(max_steps)
    try:
        return evaluator._apply(FunVal(symbol), args, defs)
    except (EvalError, ValueError):
        return None


def _random_value(
    typ: Type,
    rng: random.Random,
    int_min: int,
    int_max: int,
    list_max_len: int,
    fun_symbols: list[str],
) -> Value:
    if typ == INT:
        return IntVal(rng.randint(int_min, int_max))
    if typ == BOOL:
        return BoolVal(bool(rng.randint(0, 1)))
    if isinstance(typ, ListType):
        length = rng.randint(0, max(0, list_max_len))
        items = tuple(
            _random_value(typ.elem, rng, int_min, int_max, list_max_len, fun_symbols) for _ in range(length)
        )
        return ListVal(items)
    if isinstance(typ, OptionType):
        if rng.randint(0, 1) == 0:
            return OptionVal(False, None)
        return OptionVal(True, _random_value(typ.elem, rng, int_min, int_max, list_max_len, fun_symbols))
    if isinstance(typ, PairType):
        left = _random_value(typ.left, rng, int_min, int_max, list_max_len, fun_symbols)
        right = _random_value(typ.right, rng, int_min, int_max, list_max_len, fun_symbols)
        return PairVal(left, right)
    if isinstance(typ, FunType):
        if not fun_symbols:
            raise ValueError("eval fun_symbols required for function arguments")
        return FunVal(rng.choice(fun_symbols))
    raise ValueError(f"unsupported argument type: {typ}")


def _episode_seed(seed_key: bytes, baseline: str, candidate: str, oracle: str, episode: int) -> int:
    h = blake2b(seed_key, digest_size=8)
    h.update(baseline.encode("utf-8"))
    h.update(candidate.encode("utf-8"))
    h.update(oracle.encode("utf-8"))
    h.update(episode.to_bytes(8, "big"))
    return int.from_bytes(h.digest(), "big")


def _encode_diffs(diffs: list[int]) -> bytes:
    return "\n".join(str(d) for d in diffs).encode("utf-8")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _load_json(path: str) -> dict:
    if path == "-":
        return json.loads(Path("/dev/stdin").read_text(encoding="utf-8"))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_candidate_defs(path: str) -> dict[str, object]:
    payload = _load_json(path)
    module = payload.get("payload") if isinstance(payload, dict) and "payload" in payload else payload
    if not isinstance(module, dict):
        raise ValueError("candidate module payload must be an object")
    defs_raw = module.get("definitions") or []
    if not isinstance(defs_raw, list):
        raise ValueError("candidate module definitions must be a list")
    defs = {}
    for defn in defs_raw:
        parsed = parse_definition(defn)
        defs[parsed.name] = parsed
    return defs


def _write_json(path: str, payload: dict) -> None:
    data = json.dumps(payload, sort_keys=True)
    if path == "-":
        print(data)
        return
    Path(path).write_text(data + "\n", encoding="utf-8")


def _fill_eval_config(eval_cfg: dict, sealed_cfg) -> dict:
    eval_cfg = dict(eval_cfg)
    for field, value in (
        ("eval_harness_id", sealed_cfg.eval_harness_id),
        ("eval_harness_hash", sealed_cfg.eval_harness_hash),
        ("eval_suite_hash", sealed_cfg.eval_suite_hash),
    ):
        if field in eval_cfg and eval_cfg[field] != value:
            raise ValueError(f"eval {field} mismatch")
        eval_cfg[field] = value
    return eval_cfg


def _fill_risk(risk: object, sealed_cfg, conn) -> dict:
    if risk is None:
        risk = {}
    if not isinstance(risk, dict):
        raise ValueError("risk must be object")
    state = idx.get_stat_cert_state(conn)
    round_idx = 1 if state is None else state[0]
    alpha_i = alpha_for_round(sealed_cfg.alpha_total, round_idx, sealed_cfg.alpha_schedule)
    schedule = {
        "name": sealed_cfg.alpha_schedule.name,
        "exponent": sealed_cfg.alpha_schedule.exponent,
        "coefficient": format_decimal(sealed_cfg.alpha_schedule.coefficient),
    }
    if "alpha_schedule" in risk:
        try:
            parsed = parse_alpha_schedule(risk["alpha_schedule"])
        except Exception as exc:
            raise ValueError("risk alpha_schedule invalid") from exc
        if (
            parsed.name != sealed_cfg.alpha_schedule.name
            or parsed.exponent != sealed_cfg.alpha_schedule.exponent
            or format_decimal(parsed.coefficient) != format_decimal(sealed_cfg.alpha_schedule.coefficient)
        ):
            raise ValueError("risk alpha_schedule mismatch")
    if "alpha_i" in risk and risk["alpha_i"] != format_decimal(alpha_i):
        raise ValueError("risk alpha_i mismatch")
    risk["alpha_i"] = format_decimal(alpha_i)
    risk.setdefault("evalue_threshold", "1")
    risk["alpha_schedule"] = schedule
    return risk


if __name__ == "__main__":
    main()
