"""E-value helpers and alpha-spending schedule."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext, localcontext


getcontext().prec = 50

P_SERIES_COEFF = Decimal("0.60792710185402662866")  # 6 / pi^2
ALPHA_QUANT = Decimal("1e-24")
EVALUE_SIG_DIGITS = 24
EVALUE_MANTISSA_QUANT = Decimal(1).scaleb(-(EVALUE_SIG_DIGITS - 1))


def parse_decimal(value: str) -> Decimal:
    return Decimal(value)


def format_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise InvalidOperation("non-finite decimal")
    exp = value.adjusted()
    needed = max(exp + 1, 1) + abs(ALPHA_QUANT.as_tuple().exponent)
    with localcontext() as ctx:
        ctx.prec = max(getcontext().prec, needed)
        quantized = value.quantize(ALPHA_QUANT, rounding=ROUND_HALF_UP)
    return format(quantized, "f")


@dataclass(frozen=True)
class EncodedEvalue:
    mantissa: Decimal
    exponent10: int

    def to_dict(self) -> dict:
        return {"mantissa": format_mantissa(self.mantissa), "exponent10": self.exponent10}


def format_mantissa(value: Decimal) -> str:
    if not value.is_finite():
        raise InvalidOperation("non-finite mantissa")
    with localcontext() as ctx:
        ctx.prec = max(getcontext().prec, EVALUE_SIG_DIGITS + 4)
        quantized = value.quantize(EVALUE_MANTISSA_QUANT, rounding=ROUND_HALF_UP)
    return format(quantized, "f")


def encode_evalue(value: Decimal) -> EncodedEvalue:
    if not value.is_finite() or value <= 0:
        raise InvalidOperation("invalid evalue")
    exp10 = int(value.adjusted())
    with localcontext() as ctx:
        ctx.prec = max(getcontext().prec, EVALUE_SIG_DIGITS + 6)
        mantissa = value.scaleb(-exp10)
        mantissa = mantissa.quantize(EVALUE_MANTISSA_QUANT, rounding=ROUND_HALF_UP)
    if mantissa == Decimal("10"):
        mantissa = Decimal("1").quantize(EVALUE_MANTISSA_QUANT)
        exp10 += 1
    return EncodedEvalue(mantissa=mantissa, exponent10=exp10)


def parse_evalue(raw: object, label: str) -> EncodedEvalue:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    mantissa_raw = raw.get("mantissa")
    exponent_raw = raw.get("exponent10")
    if not isinstance(mantissa_raw, str) or not mantissa_raw:
        raise ValueError(f"{label} mantissa must be a string")
    if isinstance(exponent_raw, bool) or not isinstance(exponent_raw, int):
        raise ValueError(f"{label} exponent10 must be an int")
    mantissa = parse_decimal(mantissa_raw)
    if not mantissa.is_finite():
        raise ValueError(f"{label} mantissa must be finite")
    if mantissa <= 0 or mantissa >= 10:
        raise ValueError(f"{label} mantissa out of range")
    if format_mantissa(mantissa) != mantissa_raw:
        raise ValueError(f"{label} mantissa not canonical")
    return EncodedEvalue(mantissa=mantissa, exponent10=exponent_raw)


def encoded_evalue_to_decimal(encoded: EncodedEvalue) -> Decimal:
    return encoded.mantissa.scaleb(encoded.exponent10)


def encoded_evalue_equal(left: EncodedEvalue, right: EncodedEvalue) -> bool:
    return left.exponent10 == right.exponent10 and format_mantissa(left.mantissa) == format_mantissa(
        right.mantissa
    )


@dataclass(frozen=True)
class AlphaSchedule:
    name: str
    exponent: int
    coefficient: Decimal


def parse_alpha_schedule(schedule: dict) -> AlphaSchedule:
    if not isinstance(schedule, dict):
        raise ValueError("alpha_schedule must be an object")
    name = schedule.get("name")
    if not isinstance(name, str):
        raise ValueError("alpha_schedule name must be a string")
    if name != "p_series":
        raise ValueError("alpha_schedule name must be p_series")
    exponent = schedule.get("exponent", 2)
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent <= 1:
        raise ValueError("alpha_schedule exponent must be int > 1")
    coeff_raw = schedule.get("coefficient", str(P_SERIES_COEFF))
    coefficient = parse_decimal(str(coeff_raw))
    return AlphaSchedule(name=name, exponent=exponent, coefficient=coefficient)


def alpha_for_round(alpha_total: Decimal, round_idx: int, schedule: AlphaSchedule) -> Decimal:
    if round_idx <= 0:
        raise ValueError("round_idx must be positive")
    result = alpha_total * schedule.coefficient / (Decimal(round_idx) ** schedule.exponent)
    return result.quantize(ALPHA_QUANT)


def hoeffding_mixture_evalue(sum_diff: int, n: int) -> Decimal:
    if n <= 0:
        return Decimal("1")
    total = Decimal(sum_diff)
    denom = (Decimal(1) + Decimal(n)).sqrt()
    exponent = (total * total) / (Decimal(2) * (Decimal(1) + Decimal(n)))
    return exponent.exp() / denom


def safe_parse_decimal(value: str, label: str) -> Decimal:
    try:
        return parse_decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal for {label}") from exc
