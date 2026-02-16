"""ISA policy primitives for VAL v17.0."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed

VAL_AARCH64_SHA256_SUBSET_V1 = {
    "ldr",
    "str",
    "ld1",
    "st1",
    "add",
    "sub",
    "subs",
    "eor",
    "and",
    "orr",
    "mov",
    "cmp",
    "ror",
    "lsr",
    "lsl",
    "rev32",
    "sha256h",
    "sha256h2",
    "sha256su0",
    "sha256su1",
    "b.ne",
    "ret",
}

ALWAYS_FORBIDDEN_MNEMONICS = {
    "svc",
    "hvc",
    "smc",
    "eret",
    "mrs",
    "msr",
    "br",
    "blr",
    "bl",
    "dc",
    "ic",
    "dsb",
    "dmb",
    "isb",
}

REGISTER_RE = re.compile(r"\b(?:x|w|v|q)[0-9]+\b|\bsp\b", re.IGNORECASE)


@dataclass(frozen=True)
class ValPolicy:
    schema_version: str
    require_safety_before_exec: bool
    require_semantic_identity: bool
    require_dual_decoder_parity: bool
    require_dual_lifter_parity: bool
    max_code_bytes: int
    max_blocks_len: int
    forbidden_insn_mnemonics: tuple[str, ...]
    forbidden_regs: tuple[str, ...]
    allowed_isa_profile: str
    require_feature_crypto_sha2: bool
    equivalence_vectors: dict[str, int]
    perf_gate_valcycles_num: int
    perf_gate_valcycles_den: int
    perf_gate_wallclock_num: int
    perf_gate_wallclock_den: int
    benchmark_reps: int
    benchmark_warmup_reps: int
    spawn_gate_baseline_min: int

    @property
    def policy_hash(self) -> str:
        obj = {
            "schema_version": self.schema_version,
            "require_safety_before_exec": self.require_safety_before_exec,
            "require_semantic_identity": self.require_semantic_identity,
            "require_dual_decoder_parity": self.require_dual_decoder_parity,
            "require_dual_lifter_parity": self.require_dual_lifter_parity,
            "max_code_bytes": self.max_code_bytes,
            "max_blocks_len": self.max_blocks_len,
            "forbidden_insn_mnemonics": list(self.forbidden_insn_mnemonics),
            "forbidden_regs": list(self.forbidden_regs),
            "allowed_isa_profile": self.allowed_isa_profile,
            "require_feature_crypto_sha2": self.require_feature_crypto_sha2,
            "equivalence_vectors": self.equivalence_vectors,
            "perf_gate_valcycles_num": self.perf_gate_valcycles_num,
            "perf_gate_valcycles_den": self.perf_gate_valcycles_den,
            "perf_gate_wallclock_num": self.perf_gate_wallclock_num,
            "perf_gate_wallclock_den": self.perf_gate_wallclock_den,
            "benchmark_reps": self.benchmark_reps,
            "benchmark_warmup_reps": self.benchmark_warmup_reps,
            "spawn_gate_baseline_min": self.spawn_gate_baseline_min,
        }
        return sha256_prefixed(canon_bytes(obj))


class ValPolicyError(ValueError):
    pass


def parse_policy(obj: dict[str, Any]) -> ValPolicy:
    if obj.get("schema_version") != "sas_val_policy_v1":
        raise ValPolicyError("INVALID:SCHEMA_FAIL")
    try:
        policy = ValPolicy(
            schema_version=str(obj["schema_version"]),
            require_safety_before_exec=bool(obj["require_safety_before_exec"]),
            require_semantic_identity=bool(obj["require_semantic_identity"]),
            require_dual_decoder_parity=bool(obj["require_dual_decoder_parity"]),
            require_dual_lifter_parity=bool(obj["require_dual_lifter_parity"]),
            max_code_bytes=int(obj["max_code_bytes"]),
            max_blocks_len=int(obj["max_blocks_len"]),
            forbidden_insn_mnemonics=tuple(str(x).lower() for x in obj["forbidden_insn_mnemonics"]),
            forbidden_regs=tuple(str(x).lower() for x in obj["forbidden_regs"]),
            allowed_isa_profile=str(obj["allowed_isa_profile"]),
            require_feature_crypto_sha2=bool(obj["require_feature_crypto_sha2"]),
            equivalence_vectors=dict(obj["equivalence_vectors"]),
            perf_gate_valcycles_num=int(obj["perf_gate_valcycles_num"]),
            perf_gate_valcycles_den=int(obj["perf_gate_valcycles_den"]),
            perf_gate_wallclock_num=int(obj["perf_gate_wallclock_num"]),
            perf_gate_wallclock_den=int(obj["perf_gate_wallclock_den"]),
            benchmark_reps=int(obj["benchmark_reps"]),
            benchmark_warmup_reps=int(obj["benchmark_warmup_reps"]),
            spawn_gate_baseline_min=int(obj["spawn_gate_baseline_min"]),
        )
    except Exception as exc:
        raise ValPolicyError("INVALID:SCHEMA_FAIL") from exc

    if policy.allowed_isa_profile != "VAL_AARCH64_SHA256_SUBSET_V1":
        raise ValPolicyError("INVALID:SCHEMA_FAIL")
    if policy.max_code_bytes <= 0 or policy.max_blocks_len <= 0:
        raise ValPolicyError("INVALID:SCHEMA_FAIL")
    return policy


def allowed_mnemonics_for_policy(policy: ValPolicy) -> set[str]:
    if policy.allowed_isa_profile == "VAL_AARCH64_SHA256_SUBSET_V1":
        return set(VAL_AARCH64_SHA256_SUBSET_V1)
    return set()


def extract_registers(operands: list[str]) -> set[str]:
    out: set[str] = set()
    for operand in operands:
        for match in REGISTER_RE.findall(str(operand).lower()):
            out.add(match)
    return out


__all__ = [
    "ALWAYS_FORBIDDEN_MNEMONICS",
    "VAL_AARCH64_SHA256_SUBSET_V1",
    "ValPolicy",
    "ValPolicyError",
    "allowed_mnemonics_for_policy",
    "extract_registers",
    "parse_policy",
]
