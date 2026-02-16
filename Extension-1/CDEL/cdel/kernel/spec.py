"""Spec checking with bounded domain enumeration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import product

from cdel.kernel.ast import Definition, Term
from cdel.kernel.eval import BoolVal, Evaluator, FunVal, IntVal, ListVal, OptionVal, PairVal
from cdel.kernel.parse import parse_term, parse_specs_vars
from cdel.kernel.proof import ProofError, check_proof_spec
from cdel.kernel.types import BOOL, FunType, INT, ListType, OptionType, PairType, Type
from cdel.sealed.crypto import crypto_available, verify_signature
from cdel.sealed.evalue import (
    AlphaSchedule,
    alpha_for_round,
    encoded_evalue_equal,
    encoded_evalue_to_decimal,
    format_decimal,
    hoeffding_mixture_evalue,
    parse_alpha_schedule,
    parse_decimal,
    parse_evalue,
    encode_evalue,
)
from cdel.sealed.protocol import stat_cert_signing_bytes


class SpecError(Exception):
    pass


@dataclass(frozen=True)
class SpecStats:
    spec_work: int
    stat_cert_count: int = 0


@dataclass(frozen=True)
class StatCertContext:
    alpha_total: Decimal
    alpha_schedule: AlphaSchedule
    round_start: int
    allowed_keys: dict[str, str]
    eval_harness_id: str
    eval_harness_hash: str
    eval_suite_hash: str


def check_specs(
    specs: list[dict],
    defs: dict[str, Definition],
    sym_types: dict[str, Type],
    step_limit: int,
    stat_ctx: StatCertContext | None = None,
) -> SpecStats:
    work = 0
    stat_cert_count = 0
    for spec in specs:
        kind = spec.get("kind")
        if kind == "forall":
            vars_list = spec.get("vars") or []
            if not isinstance(vars_list, list):
                raise SpecError("spec vars must be a list")
            env_names, var_types = parse_specs_vars(vars_list)
            term = parse_term(spec.get("assert"), env_names)
            domain = spec.get("domain") or {}
            int_min = int(domain.get("int_min"))
            int_max = int(domain.get("int_max"))
            list_max_len = int(domain.get("list_max_len"))
            fun_symbols = domain.get("fun_symbols") or []
            if not isinstance(fun_symbols, list):
                raise SpecError("fun_symbols must be a list")
            if int_min > int_max:
                raise SpecError("spec domain int_min greater than int_max")
            if list_max_len < 0:
                raise SpecError("spec domain list_max_len negative")
            domains = [
                _domain_for_type(t, int_min, int_max, list_max_len, fun_symbols, sym_types)
                for t in var_types
            ]
            for assignment in product(*domains):
                env_vals: list[object] = []
                for value in assignment:
                    env_vals.insert(0, value)
                evaluator = Evaluator(step_limit)
                result = evaluator.eval_term(term, env_vals, defs)
                work += 1
                if not isinstance(result, BoolVal):
                    raise SpecError("spec assert did not evaluate to bool")
                if not result.value:
                    raise SpecError("spec assertion failed")
        elif kind in {"proof", "proof_unbounded"}:
            try:
                work += check_proof_spec(spec, defs, step_limit)
            except ProofError as exc:
                raise SpecError(f"PROOF_INVALID: {exc}") from exc
        elif kind == "stat_cert":
            if stat_ctx is None:
                raise SpecError("stat_cert requires stat_ctx")
            round_idx = stat_ctx.round_start + stat_cert_count
            work += _check_stat_cert_spec(spec, defs, stat_ctx, round_idx)
            stat_cert_count += 1
        else:
            raise SpecError("only forall, proof, proof_unbounded, and stat_cert specs are supported")
    return SpecStats(spec_work=work, stat_cert_count=stat_cert_count)


def _check_stat_cert_spec(
    spec: dict,
    defs: dict[str, Definition],
    ctx: StatCertContext,
    round_idx: int,
) -> int:
    metric = spec.get("metric")
    if metric != "accuracy":
        raise SpecError("stat_cert metric must be accuracy")
    concept = spec.get("concept")
    if not isinstance(concept, str) or not concept:
        raise SpecError("stat_cert concept missing")
    null = spec.get("null")
    if null not in {"no_improvement", "no_regression"}:
        raise SpecError("stat_cert null must be no_improvement or no_regression")
    baseline = spec.get("baseline_symbol")
    candidate = spec.get("candidate_symbol")
    if not isinstance(baseline, str) or not isinstance(candidate, str):
        raise SpecError("stat_cert baseline_symbol and candidate_symbol must be strings")
    if baseline not in defs:
        raise SpecError("stat_cert baseline_symbol not found")
    if candidate not in defs:
        raise SpecError("stat_cert candidate_symbol not found")

    eval_cfg = spec.get("eval") or {}
    if not isinstance(eval_cfg, dict):
        raise SpecError("stat_cert eval must be an object")
    episodes = _require_int_field(eval_cfg, "episodes", "stat_cert eval")
    if episodes <= 0:
        raise SpecError("stat_cert eval episodes must be positive")
    _require_int_field(eval_cfg, "max_steps", "stat_cert eval")
    paired = eval_cfg.get("paired_seeds")
    if not isinstance(paired, bool):
        raise SpecError("stat_cert eval paired_seeds must be bool")
    oracle_symbol = eval_cfg.get("oracle_symbol")
    if not isinstance(oracle_symbol, str):
        raise SpecError("stat_cert eval oracle_symbol must be string")
    if oracle_symbol not in defs:
        raise SpecError("stat_cert oracle_symbol not found")
    harness_id = eval_cfg.get("eval_harness_id")
    harness_hash = eval_cfg.get("eval_harness_hash")
    suite_hash = eval_cfg.get("eval_suite_hash")
    if harness_id != ctx.eval_harness_id:
        raise SpecError("stat_cert eval_harness_id mismatch")
    if harness_hash != ctx.eval_harness_hash:
        raise SpecError("stat_cert eval_harness_hash mismatch")
    if suite_hash != ctx.eval_suite_hash:
        raise SpecError("stat_cert eval_suite_hash mismatch")

    risk = spec.get("risk") or {}
    if not isinstance(risk, dict):
        raise SpecError("stat_cert risk must be an object")
    alpha_i_raw = risk.get("alpha_i")
    threshold_raw = risk.get("evalue_threshold")
    alpha_i = _parse_decimal_field(alpha_i_raw, "stat_cert risk alpha_i")
    threshold = _parse_decimal_field(threshold_raw, "stat_cert risk evalue_threshold")
    schedule_raw = risk.get("alpha_schedule")
    try:
        schedule = parse_alpha_schedule(schedule_raw)
    except (ValueError, InvalidOperation) as exc:
        raise SpecError("stat_cert alpha_schedule invalid") from exc
    if format_decimal(schedule.coefficient) != format_decimal(ctx.alpha_schedule.coefficient):
        raise SpecError("stat_cert alpha_schedule coefficient mismatch")
    if schedule.name != ctx.alpha_schedule.name or schedule.exponent != ctx.alpha_schedule.exponent:
        raise SpecError("stat_cert alpha_schedule mismatch")

    expected_alpha = alpha_for_round(ctx.alpha_total, round_idx, ctx.alpha_schedule)
    if format_decimal(alpha_i) != format_decimal(expected_alpha):
        raise SpecError("stat_cert alpha_i does not match schedule")

    certificate = spec.get("certificate") or {}
    if not isinstance(certificate, dict):
        raise SpecError("stat_cert certificate must be an object")
    schema_version = certificate.get("evalue_schema_version")
    if schema_version is None:
        raise SpecError("stat_cert evalue_schema_version missing")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise SpecError("stat_cert evalue_schema_version must be int")
    if schema_version != 2:
        raise SpecError("stat_cert evalue_schema_version unsupported")
    n = _require_int_field(certificate, "n", "stat_cert certificate")
    if n != episodes:
        raise SpecError("stat_cert certificate n mismatch")
    baseline_successes = _require_int_field(certificate, "baseline_successes", "stat_cert certificate")
    candidate_successes = _require_int_field(certificate, "candidate_successes", "stat_cert certificate")
    diff_sum = _require_int_field(certificate, "diff_sum", "stat_cert certificate")
    diff_min = _require_int_field(certificate, "diff_min", "stat_cert certificate")
    diff_max = _require_int_field(certificate, "diff_max", "stat_cert certificate")
    if baseline_successes < 0 or baseline_successes > n:
        raise SpecError("stat_cert baseline_successes out of range")
    if candidate_successes < 0 or candidate_successes > n:
        raise SpecError("stat_cert candidate_successes out of range")
    if diff_min != -1 or diff_max != 1:
        raise SpecError("stat_cert diff bounds must be -1 and 1")
    if diff_sum != candidate_successes - baseline_successes:
        raise SpecError("stat_cert diff_sum mismatch")
    evalue_raw = certificate.get("evalue")
    try:
        evalue = parse_evalue(evalue_raw, "stat_cert certificate evalue")
    except ValueError as exc:
        raise SpecError("stat_cert certificate evalue invalid") from exc
    expected_evalue = encode_evalue(hoeffding_mixture_evalue(diff_sum, n))
    if not encoded_evalue_equal(evalue, expected_evalue):
        raise SpecError("stat_cert evalue mismatch")
    signature = certificate.get("signature")
    if not isinstance(signature, str) or not signature:
        raise SpecError("stat_cert signature missing")
    signature_scheme = certificate.get("signature_scheme")
    if not isinstance(signature_scheme, str) or not signature_scheme:
        raise SpecError("stat_cert signature_scheme missing")
    key_id = certificate.get("key_id")
    if not isinstance(key_id, str) or not key_id:
        raise SpecError("stat_cert key_id missing")

    if encoded_evalue_to_decimal(evalue) * alpha_i < threshold:
        raise SpecError("stat_cert evalue below threshold")

    if not crypto_available():
        raise SpecError("stat_cert crypto backend unavailable")

    public_key = ctx.allowed_keys.get(key_id)
    if not public_key:
        raise SpecError("stat_cert key_id not allowed")
    signing_bytes = stat_cert_signing_bytes(spec)
    if not verify_signature(public_key, signing_bytes, signature, signature_scheme):
        raise SpecError("stat_cert signature invalid")

    return n


def _require_int_field(source: dict, label: str, context: str) -> int:
    value = source.get(label)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"{context} {label} must be int")
    return value


def _parse_decimal_field(value: object, context: str) -> Decimal:
    if not isinstance(value, str):
        raise SpecError(f"{context} must be string decimal")
    try:
        return parse_decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SpecError(f"{context} invalid decimal") from exc


def _domain_for_type(
    typ: Type,
    int_min: int,
    int_max: int,
    list_max_len: int,
    fun_symbols: list[str],
    sym_types: dict[str, Type],
) -> list[object]:
    if typ == INT:
        return [IntVal(i) for i in range(int_min, int_max + 1)]
    if typ == BOOL:
        return [BoolVal(False), BoolVal(True)]
    if isinstance(typ, ListType):
        elems = _domain_for_type(typ.elem, int_min, int_max, list_max_len, fun_symbols, sym_types)
        return _list_domain(elems, list_max_len)
    if isinstance(typ, OptionType):
        elems = _domain_for_type(typ.elem, int_min, int_max, list_max_len, fun_symbols, sym_types)
        values = [OptionVal(False, None)]
        values.extend(OptionVal(True, elem) for elem in elems)
        return values
    if isinstance(typ, PairType):
        left = _domain_for_type(typ.left, int_min, int_max, list_max_len, fun_symbols, sym_types)
        right = _domain_for_type(typ.right, int_min, int_max, list_max_len, fun_symbols, sym_types)
        return [PairVal(l, r) for l, r in product(left, right)]
    if isinstance(typ, FunType):
        values = []
        for name in fun_symbols:
            sym_type = sym_types.get(name)
            if sym_type is None:
                raise SpecError(f"fun_symbol not found: {name}")
            if sym_type != typ:
                continue
            values.append(FunVal(name))
        if not values:
            raise SpecError("no fun_symbols available for function domain")
        return values
    raise SpecError("unsupported type in spec domain")


def _list_domain(elems: list[object], max_len: int) -> list[ListVal]:
    lists: list[ListVal] = [ListVal(tuple())]
    if max_len <= 0:
        return lists
    for length in range(1, max_len + 1):
        for combo in product(elems, repeat=length):
            lists.append(ListVal(tuple(combo)))
    return lists
