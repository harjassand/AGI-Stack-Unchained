"""VPVM STARK prover (stark_vm_v1).

This module builds the proof-carrying artifacts used by the PCLP fast-path.

v1 security posture:
  - This is a *real STARK* (Merkle commitments + FRI + AIR checks) over a
    deterministic "commitment machine" AIR (see vpvm_stark_air_v1.py).
  - QXRL replay is still the source of truth for training/eval correctness; the
    STARK here proves the binding/commitment statement that is used by the
    existing verifier wiring.

Determinism:
  - No floats, no randomness.
  - All transcript challenges are Poseidon-derived from committed roots and
    public input hashes.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Any

from ..omega_common_v1 import fail
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from .gld_field_v1 import CosetDomainV1, P_GOLDILOCKS, f, inv, mul, primitive_root_of_unity, sub
from .pclp_common_v1 import (
    COMMIT_ALGO_ID_ROLLHASH32X2_V1,
    DC1_ID_Q32_V1,
    EUDRSU_PCLP_SCHEMA_INVALID,
    PROOF_SYSTEM_ID_STARK_VM_V1,
    ROLLHASH32X2_BATCH_U32_PER_ROW_V1,
    SCHEMA_PCLP_BUNDLE_V1,
    SCHEMA_STARK_VM_PROOF_V1,
    SCHEMA_VPVM_CONFIG_V1,
    SCHEMA_VPVM_PUBLIC_INPUTS_V1,
    VPVM_ID_Q32_V1,
    bytes32_to_hex64,
    compute_public_inputs_base_hash32,
    compute_public_inputs_hash32,
    compute_rollhash32x2_commitments_v1,
    compute_self_hash_id_omit,
    dataset_examples_to_u32_stream_v1,
    sha256_id_to_digest32,
    weights_manifest_to_u32_stream_v1,
)
from .poseidon_gld_v1 import PoseidonParamsGldV1, parse_poseidon_params_gld_v1_bin, poseidon_sponge_hash32_felts_v1, poseidon_sponge_hash32_v1
from .stark_fft_gld_v1 import eval_poly_on_coset, interpolate_poly_from_evals
from .stark_merkle_poseidon_v1 import PoseidonMerkleTreeV1
from .stark_transcript_poseidon_v1 import PoseidonTranscriptV1
from .vpvm_stark_air_v1 import VpvmCommitTraceLayoutV1, eval_transition_constraints_v1, mix_constraints_v1


def _make_pclp_relpath(*, artifact_id: str, suffix: str) -> str:
    hex64 = str(artifact_id).split(":", 1)[1]
    return f"polymath/registry/eudrs_u/pclp/sha256_{hex64}.{suffix}"


def _make_aref(*, artifact_id: str, suffix: str) -> dict[str, str]:
    return {"artifact_id": str(artifact_id).strip(), "artifact_relpath": _make_pclp_relpath(artifact_id=artifact_id, suffix=suffix)}


def build_vpvm_config_v1(
    *,
    opset_id: str,
    max_steps_u32: int,
    poseidon_params_ref: dict[str, str],
) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    """Return (config_obj, config_bytes, ArtifactRefV1)."""

    try:
        poseidon_params_ref = require_artifact_ref_v1(poseidon_params_ref)
    except Exception:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    cfg: dict[str, Any] = {
        "schema_id": SCHEMA_VPVM_CONFIG_V1,
        "vpvm_config_id": "sha256:" + ("0" * 64),
        "field": {"field_id": "goldilocks64_v1", "p_hex": "ffffffff00000001"},
        "stark": {"security_level_bits_u32": 128, "blowup_factor_u32": 8},
        "fri": {
            "folding_factor_u32": 2,
            "num_queries_u32": 60,
            "grinding_bits_u32": 0,
            "max_remainder_degree_u32": 64,
        },
        "hash": {"commitment_hash_id": "poseidon_gld_v1", "poseidon_params_ref": poseidon_params_ref},
        "trace": {
            "max_steps_u32": int(max_steps_u32),
            "num_registers_u32": 16,
            "word_bits_u32": 64,
            "q32_shift_u32": 32,
            "endianness": "LE",
            "air_id": "vpvm_q32_air_v1",
            "opset_id": str(opset_id),
        },
        "range_check": {"byte_lookup_kind": "lookup256_v1"},
    }
    cfg["vpvm_config_id"] = compute_self_hash_id_omit(cfg, id_field="vpvm_config_id")
    cfg_bytes = gcj1_canon_bytes(cfg)
    cfg_artifact_id = sha256_prefixed(cfg_bytes)
    cfg_ref = _make_aref(artifact_id=cfg_artifact_id, suffix="vpvm_config_v1.json")
    return dict(cfg), bytes(cfg_bytes), dict(cfg_ref)


def build_vpvm_public_inputs_v1(
    *,
    opset_id: str,
    training_manifest_id: str,
    dataset_manifest_id: str,
    eval_manifest_id: str,
    lut_manifest_id: str,
    wroot_before_id: str,
    wroot_after_id: str,
    h_train_tail32_hex_expected: str,
    h_eval_tail32_hex_expected: str,
    scorecard_artifact_id_expected: str,
    vpvm_config_obj: dict[str, Any],
    poseidon_params_bin: bytes,
    program_bytes: bytes,
    # Content inputs used for rollhash32x2 commitments (binding to artifact contents).
    lut_bytes: bytes | None = None,
    examples: list[Any] | None = None,
    weights_before: Any | None = None,
    weights_after: Any | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, str], bytes, bytes]:
    """Return (public_inputs_obj, bytes, ArtifactRefV1, pi_base_hash32, main_trace_root32).

    r_bind and rollhash32x2 commitments are derived from:
      - public_inputs_base_hash32
      - Poseidon-Merkle root of the main trace commitment (deterministic)
    """

    if lut_bytes is None or examples is None or weights_before is None or weights_after is None:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    base_pi: dict[str, Any] = {
        "opset_id": str(opset_id),
        "dc1_id": DC1_ID_Q32_V1,
        "training_manifest_id": str(training_manifest_id),
        "dataset_manifest_id": str(dataset_manifest_id),
        "eval_manifest_id": str(eval_manifest_id),
        "lut_manifest_id": str(lut_manifest_id),
        "wroot_before_id": str(wroot_before_id),
        "wroot_after_id": str(wroot_after_id),
        "h_train_tail32_hex_expected": str(h_train_tail32_hex_expected),
        "h_eval_tail32_hex_expected": str(h_eval_tail32_hex_expected),
        "scorecard_artifact_id_expected": str(scorecard_artifact_id_expected),
        # v1 caps: fixed permissive caps (pinned by public_inputs_hash32).
        "caps": {
            "mem": {
                "max_addr_u64": 18446744073709551615,
                "allowed_segs_u8": [0, 1, 2, 3],
                "seg_limits": [
                    {"seg_u8": 0, "max_addr_u64": 18446744073709551615},
                    {"seg_u8": 1, "max_addr_u64": 18446744073709551615},
                    {"seg_u8": 2, "max_addr_u64": 18446744073709551615},
                    {"seg_u8": 3, "max_addr_u64": 18446744073709551615},
                ],
            }
        },
    }

    # Base hash (omits commitments and tails expected).
    pi_base_hash32 = compute_public_inputs_base_hash32(base_pi)

    # Main trace commitment root (Poseidon-Merkle over LDE row hashes).
    cfg_max_steps_u32 = int(vpvm_config_obj.get("trace", {}).get("max_steps_u32", 0))
    blowup = int(vpvm_config_obj.get("stark", {}).get("blowup_factor_u32", 0))
    if cfg_max_steps_u32 <= 0 or blowup <= 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    poseidon_params = parse_poseidon_params_gld_v1_bin(bytes(poseidon_params_bin))

    program_id = sha256_prefixed(bytes(program_bytes))
    n_trace, m_lde = _commit_trace_sizes_v1(
        blowup_factor_u32=int(blowup),
        program_bytes=bytes(program_bytes),
        lut_bytes=bytes(lut_bytes),
        examples=list(examples),
        weights_before=weights_before,
        weights_after=weights_after,
    )
    if n_trace > cfg_max_steps_u32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    main_base_cols = _build_main_base_cols_v1(
        program_bytes=bytes(program_bytes),
        lut_bytes=bytes(lut_bytes),
        examples=list(examples),
        weights_before=weights_before,
        weights_after=weights_after,
        n_trace_u32=int(n_trace),
    )
    main_root32, _main_tree, _main_lde_cols = _build_main_trace_commitment_v1(
        params=poseidon_params,
        base_cols=main_base_cols,
        n_trace_u32=int(n_trace),
        m_lde_u32=int(m_lde),
        blowup_factor_u32=int(blowup),
    )

    # Derive r_bind challenges from transcript(base_hash, main_root).
    tr = PoseidonTranscriptV1(params=poseidon_params)
    tr.absorb_bytes32(bytes(pi_base_hash32))
    tr.absorb_bytes32(bytes(main_root32))
    r_bind_f0 = int(tr.squeeze_field()) % P_GOLDILOCKS
    r_bind_f1 = int(tr.squeeze_field()) % P_GOLDILOCKS

    commits = compute_rollhash32x2_commitments_v1(
        r_bind_u64_0=int(r_bind_f0),
        r_bind_u64_1=int(r_bind_f1),
        program_bytes=bytes(program_bytes),
        lut_bytes=bytes(lut_bytes),
        examples=list(examples),
        weights_before=weights_before,
        weights_after=weights_after,
    )
    commitments: dict[str, Any] = {
        "commit_algo_id": COMMIT_ALGO_ID_ROLLHASH32X2_V1,
        "r_bind_u64_0": int(r_bind_f0),
        "r_bind_u64_1": int(r_bind_f1),
        "weights_before_commit_f0": int(commits["weights_before_commit_f0"]),
        "weights_before_commit_f1": int(commits["weights_before_commit_f1"]),
        "weights_after_commit_f0": int(commits["weights_after_commit_f0"]),
        "weights_after_commit_f1": int(commits["weights_after_commit_f1"]),
        "dataset_commit_f0": int(commits["dataset_commit_f0"]),
        "dataset_commit_f1": int(commits["dataset_commit_f1"]),
        "lut_commit_f0": int(commits["lut_commit_f0"]),
        "lut_commit_f1": int(commits["lut_commit_f1"]),
        "program_commit_f0": int(commits["program_commit_f0"]),
        "program_commit_f1": int(commits["program_commit_f1"]),
    }

    pi_full = dict(base_pi)
    pi_full["commitments"] = commitments

    pi_hash32 = compute_public_inputs_hash32(pi_full)
    vpvm_config_id = str(vpvm_config_obj.get("vpvm_config_id", "")).strip()

    obj: dict[str, Any] = {
        "schema_id": SCHEMA_VPVM_PUBLIC_INPUTS_V1,
        "vpvm_id": VPVM_ID_Q32_V1,
        "vpvm_config_id": str(vpvm_config_id),
        "program_id": str(program_id),
        "public_inputs_hash32_hex": bytes32_to_hex64(pi_hash32),
        "public_inputs_base_hash32_hex": bytes32_to_hex64(pi_base_hash32),
        "public_inputs": pi_full,
    }
    out_bytes = gcj1_canon_bytes(obj)
    art_id = sha256_prefixed(out_bytes)
    ref = _make_aref(artifact_id=art_id, suffix="vpvm_public_inputs_v1.json")
    return dict(obj), bytes(out_bytes), dict(ref), bytes(pi_base_hash32), bytes(main_root32)


def build_stark_vm_proof_v1_bin(
    *,
    vpvm_config_obj: dict[str, Any],
    poseidon_params_bin: bytes,
    vpvm_public_inputs_obj: dict[str, Any],
    program_bytes: bytes,
    lut_bytes: bytes | None = None,
    examples: list[Any] | None = None,
    weights_before: Any | None = None,
    weights_after: Any | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    """Return (proof_header_obj, proof_bytes, ArtifactRefV1)."""

    if lut_bytes is None or examples is None or weights_before is None or weights_after is None:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Parse params and basic config.
    poseidon_params = parse_poseidon_params_gld_v1_bin(bytes(poseidon_params_bin))
    cfg_id = str(vpvm_config_obj.get("vpvm_config_id", "")).strip()
    max_steps_u32 = int(vpvm_config_obj.get("trace", {}).get("max_steps_u32", 0))
    blowup = int(vpvm_config_obj.get("stark", {}).get("blowup_factor_u32", 0))
    if max_steps_u32 <= 0 or blowup <= 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    fri_cfg = dict(vpvm_config_obj.get("fri", {}))
    num_queries_u32 = int(fri_cfg.get("num_queries_u32", 0))
    max_rem_deg_u32 = int(fri_cfg.get("max_remainder_degree_u32", 0))
    if num_queries_u32 < 0 or max_rem_deg_u32 <= 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Recompute public input hashes and bind to base hash (normative).
    pi_obj = dict(vpvm_public_inputs_obj.get("public_inputs", {}))
    pi_hash32 = compute_public_inputs_hash32(pi_obj)
    if bytes32_to_hex64(pi_hash32) != str(vpvm_public_inputs_obj.get("public_inputs_hash32_hex", "")).strip():
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    pi_base_hash32 = compute_public_inputs_base_hash32(pi_obj)
    if bytes32_to_hex64(pi_base_hash32) != str(vpvm_public_inputs_obj.get("public_inputs_base_hash32_hex", "")).strip():
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Build main trace commitment root and derive r_bind from transcript.
    program_id = sha256_prefixed(bytes(program_bytes))
    n_trace, m_lde = _commit_trace_sizes_v1(
        blowup_factor_u32=int(blowup),
        program_bytes=bytes(program_bytes),
        lut_bytes=bytes(lut_bytes),
        examples=list(examples),
        weights_before=weights_before,
        weights_after=weights_after,
    )
    if n_trace > max_steps_u32:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    public_inputs = dict(pi_obj)
    main_base_cols = _build_main_base_cols_v1(
        program_bytes=bytes(program_bytes),
        lut_bytes=bytes(lut_bytes),
        examples=list(examples),
        weights_before=weights_before,
        weights_after=weights_after,
        n_trace_u32=int(n_trace),
    )
    main_root32, main_tree, main_lde_cols = _build_main_trace_commitment_v1(
        params=poseidon_params,
        base_cols=main_base_cols,
        n_trace_u32=int(n_trace),
        m_lde_u32=int(m_lde),
        blowup_factor_u32=int(blowup),
    )

    tr = PoseidonTranscriptV1(params=poseidon_params)
    tr.absorb_bytes32(bytes(pi_base_hash32))
    tr.absorb_bytes32(bytes(main_root32))
    r_bind_f0 = int(tr.squeeze_field()) % P_GOLDILOCKS
    r_bind_f1 = int(tr.squeeze_field()) % P_GOLDILOCKS

    # Aux trace depends on r_bind; commit it.
    aux_root32, aux_tree, aux_lde_cols = _build_aux_trace_commitment_v1(
        params=poseidon_params,
        main_base_pi=public_inputs,
        r_bind_f0=int(r_bind_f0),
        r_bind_f1=int(r_bind_f1),
        n_trace_u32=int(n_trace),
        m_lde_u32=int(m_lde),
        blowup_factor_u32=int(blowup),
        main_base_cols=main_base_cols,
    )

    # Bind aux root and full public inputs hash before deriving composition/Fri challenges.
    tr.absorb_bytes32(bytes(aux_root32))
    tr.absorb_bytes32(bytes(pi_hash32))

    # Challenges for composition polynomial.
    alpha_mix = int(tr.squeeze_field()) % P_GOLDILOCKS
    if alpha_mix == 0:
        alpha_mix = 1
    layout = VpvmCommitTraceLayoutV1()
    rho_main = [int(tr.squeeze_field()) % P_GOLDILOCKS for _ in range(len(layout.MAIN_COLS))]
    rho_aux = [int(tr.squeeze_field()) % P_GOLDILOCKS for _ in range(len(layout.AUX_COLS))]
    rho_q = int(tr.squeeze_field()) % P_GOLDILOCKS

    # Compute composition evaluations on the LDE domain.
    omega_m = primitive_root_of_unity(int(m_lde))
    shift = _choose_lde_shift_v1(n_trace_u32=int(n_trace), omega_n=pow(int(omega_m), int(blowup), P_GOLDILOCKS))
    comp_evals = _compute_composition_evals_v1(
        n_trace_u32=int(n_trace),
        m_lde_u32=int(m_lde),
        blowup_factor_u32=int(blowup),
        omega_m=int(omega_m),
        shift=int(shift),
        main_lde_cols=main_lde_cols,
        aux_lde_cols=aux_lde_cols,
        r_bind_f0=int(r_bind_f0),
        r_bind_f1=int(r_bind_f1),
        alpha_mix=int(alpha_mix),
        rho_main=rho_main,
        rho_aux=rho_aux,
        rho_q=int(rho_q),
        commitments=dict(public_inputs.get("commitments", {})),
    )

    # Commit to composition polynomial (FRI layer 0 root).
    comp_root32, fri_proof = _prove_fri_v1(
        params=poseidon_params,
        transcript=tr,
        domain=CosetDomainV1(size=int(m_lde), omega=int(omega_m), shift=int(shift)),
        evals0=comp_evals,
        num_queries_u32=int(num_queries_u32),
        max_remainder_degree_u32=int(max_rem_deg_u32),
    )

    # Derive query indices (must match FRI proof openings).
    q_indices = [int(q.index_u32) for q in fri_proof.query_openings]
    trace_openings = _build_trace_openings_payload_v1(
        main_tree=main_tree,
        aux_tree=aux_tree,
        main_lde_cols=main_lde_cols,
        aux_lde_cols=aux_lde_cols,
        query_indices=q_indices,
        blowup_factor_u32=int(blowup),
    )

    fri_payload = _encode_fri_proof_payload_v1(fri_proof)
    payload = _encode_stark_vm_payload_v1(trace_openings=trace_openings, fri_payload=fri_payload)

    header_no_payload: dict[str, Any] = {
        "schema_id": SCHEMA_STARK_VM_PROOF_V1,
        "proof_system_id": PROOF_SYSTEM_ID_STARK_VM_V1,
        "vpvm_id": VPVM_ID_Q32_V1,
        "vpvm_config_id": str(cfg_id),
        "program_id": str(program_id),
        "public_inputs_hash32_hex": bytes32_to_hex64(pi_hash32),
        "trace_len_u32": int(n_trace),
        "main_trace_root32_hex": bytes32_to_hex64(main_root32),
        "aux_trace_root32_hex": bytes32_to_hex64(aux_root32),
        "composition_root32_hex": bytes32_to_hex64(comp_root32),
        "fri_roots32_hex": [bytes32_to_hex64(bytes(r)) for r in fri_proof.layer_roots32],
        "commitment_hash_id": str(vpvm_config_obj.get("hash", {}).get("commitment_hash_id", "")).strip(),
        "fri_params": {
            "folding_factor_u32": int(fri_cfg.get("folding_factor_u32", 0)),
            "num_queries_u32": int(num_queries_u32),
            "grinding_bits_u32": int(fri_cfg.get("grinding_bits_u32", 0)),
            "max_remainder_degree_u32": int(max_rem_deg_u32),
        },
    }

    header = dict(header_no_payload)
    header["proof_payload_len_u32"] = int(len(payload))
    header["proof_payload_sha256_hex"] = hashlib.sha256(bytes(payload)).hexdigest()

    header_bytes = gcj1_canon_bytes(header)
    proof = struct.pack("<I", int(len(header_bytes)) & 0xFFFFFFFF) + header_bytes + payload

    art_id = sha256_prefixed(proof)
    ref = _make_aref(artifact_id=art_id, suffix="vpvm_proof_v1.bin")
    return dict(header), bytes(proof), dict(ref)


def build_pclp_bundle_v1(
    *,
    vpvm_config_ref: dict[str, str],
    public_inputs_ref: dict[str, str],
    program_bin_ref: dict[str, str],
    proof_bin_ref: dict[str, str],
    opset_id: str,
    training_manifest_ref: dict[str, str],
    dataset_manifest_ref: dict[str, str],
    eval_manifest_ref: dict[str, str],
    invsqrt_lut_manifest_ref: dict[str, str],
    wroot_after_ref: dict[str, str],
    h_train_tail32_hex: str,
    scorecard_ref: dict[str, str],
    h_eval_tail32_hex: str,
    reason_code_on_fail: str,
) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    """Return (bundle_obj, bundle_bytes, ArtifactRefV1)."""

    vpvm_config_ref = require_artifact_ref_v1(vpvm_config_ref)
    public_inputs_ref = require_artifact_ref_v1(public_inputs_ref)
    program_bin_ref = require_artifact_ref_v1(program_bin_ref)
    proof_bin_ref = require_artifact_ref_v1(proof_bin_ref)
    training_manifest_ref = require_artifact_ref_v1(training_manifest_ref)
    dataset_manifest_ref = require_artifact_ref_v1(dataset_manifest_ref)
    eval_manifest_ref = require_artifact_ref_v1(eval_manifest_ref)
    invsqrt_lut_manifest_ref = require_artifact_ref_v1(invsqrt_lut_manifest_ref)
    wroot_after_ref = require_artifact_ref_v1(wroot_after_ref)
    scorecard_ref = require_artifact_ref_v1(scorecard_ref)

    bundle: dict[str, Any] = {
        "schema_id": SCHEMA_PCLP_BUNDLE_V1,
        "pclp_bundle_id": "sha256:" + ("0" * 64),
        "proof_system_id": PROOF_SYSTEM_ID_STARK_VM_V1,
        "vpvm_id": VPVM_ID_Q32_V1,
        "vpvm_config_ref": vpvm_config_ref,
        "public_inputs_ref": public_inputs_ref,
        "program_bin_ref": program_bin_ref,
        "proof_bin_ref": proof_bin_ref,
        "bindings": {
            "opset_id": str(opset_id),
            "dc1_id": DC1_ID_Q32_V1,
            "training_manifest_ref": training_manifest_ref,
            "dataset_manifest_ref": dataset_manifest_ref,
            "eval_manifest_ref": eval_manifest_ref,
            "invsqrt_lut_manifest_ref": invsqrt_lut_manifest_ref,
        },
        "expected_outputs": {
            "wroot_after_ref": wroot_after_ref,
            "h_train_tail32_hex": str(h_train_tail32_hex),
            "scorecard_ref": scorecard_ref,
            "h_eval_tail32_hex": str(h_eval_tail32_hex),
            "reason_code_on_fail": str(reason_code_on_fail),
        },
    }
    bundle["pclp_bundle_id"] = compute_self_hash_id_omit(bundle, id_field="pclp_bundle_id")
    bundle_bytes = gcj1_canon_bytes(bundle)
    art_id = sha256_prefixed(bundle_bytes)
    ref = _make_aref(artifact_id=art_id, suffix="pclp_bundle_v1.json")
    return dict(bundle), bytes(bundle_bytes), dict(ref)


__all__ = [
    "build_pclp_bundle_v1",
    "build_stark_vm_proof_v1_bin",
    "build_vpvm_config_v1",
    "build_vpvm_public_inputs_v1",
]


_U32LE = struct.Struct("<I")
_U64LE = struct.Struct("<Q")


def _next_pow2(n: int) -> int:
    x = int(n)
    if x <= 1:
        return 1
    return 1 << int(x - 1).bit_length()


def _commit_trace_sizes_v1(
    *,
    blowup_factor_u32: int,
    program_bytes: bytes,
    lut_bytes: bytes,
    examples: list[Any],
    weights_before: Any,
    weights_after: Any,
) -> tuple[int, int]:
    """Return (n_trace, m_lde) for the v1 commitment-machine trace.

    Trace steps stream the full content item streams used by rollhash32x2:
      - program bytes
      - LUT bytes
      - dataset example u32 stream
      - weights before u32 stream
      - weights after u32 stream
    plus a single padding row.
    """

    prog_n = len(bytes(program_bytes))
    lut_n = len(bytes(lut_bytes))
    ds_n = len(dataset_examples_to_u32_stream_v1(list(examples)))
    wb_n = len(weights_manifest_to_u32_stream_v1(weights_before))
    wa_n = len(weights_manifest_to_u32_stream_v1(weights_after))

    k = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)

    def _rows(n_items: int) -> int:
        return (int(n_items) + k - 1) // k

    steps = _rows(prog_n) + _rows(lut_n) + _rows(ds_n) + _rows(wb_n) + _rows(wa_n) + 1
    n_trace = _next_pow2(int(steps))
    m_lde = int(n_trace) * int(blowup_factor_u32)
    if (m_lde & (m_lde - 1)) != 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return int(n_trace), int(m_lde)


def _choose_lde_shift_v1(*, n_trace_u32: int, omega_n: int) -> int:
    """Pick a deterministic coset shift such that denominators stay non-zero."""

    n = int(n_trace_u32)
    g_last = pow(int(omega_n) % P_GOLDILOCKS, n - 1, P_GOLDILOCKS)  # omega^{-1}
    for cand in [3, 5, 7, 11, 13, 17, 19, 23]:
        s = int(cand) % P_GOLDILOCKS
        if s == 0 or s == 1 or s == g_last:
            continue
        # Ensure s^n != 1 so Z(x)=x^n-1 is non-zero on the coset.
        if pow(s, n, P_GOLDILOCKS) == 1:
            continue
        return int(s)
    fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return 3


def _hash_row_v1(params: PoseidonParamsGldV1, row_felts: list[int]) -> bytes:
    return poseidon_sponge_hash32_felts_v1(params, felts=[int(v) % P_GOLDILOCKS for v in row_felts])


def _build_main_base_cols_v1(
    *,
    program_bytes: bytes,
    lut_bytes: bytes,
    examples: list[Any],
    weights_before: Any,
    weights_after: Any,
    n_trace_u32: int,
) -> dict[str, list[int]]:
    """Build base-domain main trace columns (size n_trace)."""

    program_items = [int(b) for b in bytes(program_bytes)]
    lut_items = [int(b) for b in bytes(lut_bytes)]
    dataset_items = dataset_examples_to_u32_stream_v1(list(examples))
    weights_before_items = weights_manifest_to_u32_stream_v1(weights_before)
    weights_after_items = weights_manifest_to_u32_stream_v1(weights_after)

    k = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)

    def _pad(items: list[int]) -> list[int]:
        n = len(items)
        pad = (-n) % k
        if pad:
            items = list(items) + [0] * int(pad)
        return list(items)

    program_items = _pad(program_items)
    lut_items = _pad(lut_items)
    dataset_items = _pad(dataset_items)
    weights_before_items = _pad(weights_before_items)
    weights_after_items = _pad(weights_after_items)

    items_by_stream: list[tuple[str, list[int]]] = [
        ("sel_program", program_items),
        ("sel_lut", lut_items),
        ("sel_dataset", dataset_items),
        ("sel_w_before", weights_before_items),
        ("sel_w_after", weights_after_items),
    ]

    layout = VpvmCommitTraceLayoutV1()
    cols: dict[str, list[int]] = {name: [0] * int(n_trace_u32) for name in layout.MAIN_COLS}
    pos = 0
    for sel_name, items in items_by_stream:
        if (len(items) % k) != 0:
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        for off in range(0, len(items), k):
            if pos >= int(n_trace_u32):
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            for s in ["sel_program", "sel_lut", "sel_dataset", "sel_w_before", "sel_w_after", "sel_pad"]:
                cols[s][pos] = 1 if s == sel_name else 0
            block = items[off : off + k]
            if len(block) != k:
                fail(EUDRSU_PCLP_SCHEMA_INVALID)
            for i in range(k):
                it = block[i]
                if not isinstance(it, int) or it < 0 or it > 0xFFFFFFFF:
                    fail(EUDRSU_PCLP_SCHEMA_INVALID)
                cols[f"item{i}"][pos] = int(it) & 0xFFFFFFFF
            pos += 1

    # Pad suffix.
    while pos < int(n_trace_u32):
        for s in ["sel_program", "sel_lut", "sel_dataset", "sel_w_before", "sel_w_after"]:
            cols[s][pos] = 0
        cols["sel_pad"][pos] = 1
        for i in range(k):
            cols[f"item{i}"][pos] = 0
        pos += 1

    return cols


def _lde_cols_from_base(
    *,
    base_cols: dict[str, list[int]],
    n_trace_u32: int,
    m_lde_u32: int,
    blowup_factor_u32: int,
    omega_m: int,
    shift: int,
) -> dict[str, list[int]]:
    omega_n = pow(int(omega_m) % P_GOLDILOCKS, int(blowup_factor_u32), P_GOLDILOCKS)
    out: dict[str, list[int]] = {}
    for name, base in base_cols.items():
        base_evals = [int(v) % P_GOLDILOCKS for v in base]
        if len(base_evals) != int(n_trace_u32):
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        coeffs = interpolate_poly_from_evals(base_evals, int(omega_n))
        out[name] = [int(v) % P_GOLDILOCKS for v in eval_poly_on_coset(coeffs=coeffs, omega_m=int(omega_m), shift=int(shift), m=int(m_lde_u32))]
    return out


def _build_main_trace_commitment_v1(
    *,
    params: PoseidonParamsGldV1,
    base_cols: dict[str, list[int]],
    n_trace_u32: int,
    m_lde_u32: int,
    blowup_factor_u32: int,
) -> tuple[bytes, PoseidonMerkleTreeV1, dict[str, list[int]]]:
    omega_m = primitive_root_of_unity(int(m_lde_u32))
    omega_n = pow(int(omega_m) % P_GOLDILOCKS, int(blowup_factor_u32), P_GOLDILOCKS)
    shift = _choose_lde_shift_v1(n_trace_u32=int(n_trace_u32), omega_n=int(omega_n))
    lde_cols = _lde_cols_from_base(
        base_cols=base_cols,
        n_trace_u32=int(n_trace_u32),
        m_lde_u32=int(m_lde_u32),
        blowup_factor_u32=int(blowup_factor_u32),
        omega_m=int(omega_m),
        shift=int(shift),
    )
    layout = VpvmCommitTraceLayoutV1()
    leaves = []
    for i in range(int(m_lde_u32)):
        row = [int(lde_cols[name][i]) for name in layout.MAIN_COLS]
        leaves.append(_hash_row_v1(params, row))
    tree = PoseidonMerkleTreeV1.build(params=params, leaves32=leaves)
    return bytes(tree.root32), tree, lde_cols


def _build_aux_trace_commitment_v1(
    *,
    params: PoseidonParamsGldV1,
    main_base_pi: dict[str, Any],
    r_bind_f0: int,
    r_bind_f1: int,
    n_trace_u32: int,
    m_lde_u32: int,
    blowup_factor_u32: int,
    main_base_cols: dict[str, list[int]],
) -> tuple[bytes, PoseidonMerkleTreeV1, dict[str, list[int]]]:
    _ = main_base_pi
    layout = VpvmCommitTraceLayoutV1()
    # Build base aux columns by executing the commitment machine.
    aux_cols: dict[str, list[int]] = {name: [0] * int(n_trace_u32) for name in layout.AUX_COLS}

    acc = [0] * len(layout.AUX_COLS)
    for t in range(int(n_trace_u32)):
        for j, name in enumerate(layout.AUX_COLS):
            aux_cols[name][t] = int(acc[j]) % P_GOLDILOCKS
        if t + 1 >= int(n_trace_u32):
            break
        k = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)
        its = [int(main_base_cols[f"item{i}"][t]) % P_GOLDILOCKS for i in range(k)]
        sel = {
            "program": int(main_base_cols["sel_program"][t]),
            "lut": int(main_base_cols["sel_lut"][t]),
            "dataset": int(main_base_cols["sel_dataset"][t]),
            "w_before": int(main_base_cols["sel_w_before"][t]),
            "w_after": int(main_base_cols["sel_w_after"][t]),
        }

        def _upd(cur: int, is_sel: int, r: int) -> int:
            if int(is_sel) != 1:
                return int(cur) % P_GOLDILOCKS
            rr = int(r) % P_GOLDILOCKS
            acc0 = int(cur) % P_GOLDILOCKS
            for it in its:
                acc0 = (acc0 * rr + int(it)) % P_GOLDILOCKS
            return int(acc0)

        # Order matches AUX_COLS.
        acc[0] = _upd(acc[0], sel["program"], int(r_bind_f0))
        acc[1] = _upd(acc[1], sel["program"], int(r_bind_f1))
        acc[2] = _upd(acc[2], sel["lut"], int(r_bind_f0))
        acc[3] = _upd(acc[3], sel["lut"], int(r_bind_f1))
        acc[4] = _upd(acc[4], sel["dataset"], int(r_bind_f0))
        acc[5] = _upd(acc[5], sel["dataset"], int(r_bind_f1))
        acc[6] = _upd(acc[6], sel["w_before"], int(r_bind_f0))
        acc[7] = _upd(acc[7], sel["w_before"], int(r_bind_f1))
        acc[8] = _upd(acc[8], sel["w_after"], int(r_bind_f0))
        acc[9] = _upd(acc[9], sel["w_after"], int(r_bind_f1))

    # LDE and Merkle commit.
    omega_m = primitive_root_of_unity(int(m_lde_u32))
    omega_n = pow(int(omega_m) % P_GOLDILOCKS, int(blowup_factor_u32), P_GOLDILOCKS)
    shift = _choose_lde_shift_v1(n_trace_u32=int(n_trace_u32), omega_n=int(omega_n))
    lde_cols = _lde_cols_from_base(
        base_cols=aux_cols,
        n_trace_u32=int(n_trace_u32),
        m_lde_u32=int(m_lde_u32),
        blowup_factor_u32=int(blowup_factor_u32),
        omega_m=int(omega_m),
        shift=int(shift),
    )
    leaves = []
    for i in range(int(m_lde_u32)):
        row = [int(lde_cols[name][i]) for name in layout.AUX_COLS]
        leaves.append(_hash_row_v1(params, row))
    tree = PoseidonMerkleTreeV1.build(params=params, leaves32=leaves)
    return bytes(tree.root32), tree, lde_cols


def _compute_composition_evals_v1(
    *,
    n_trace_u32: int,
    m_lde_u32: int,
    blowup_factor_u32: int,
    omega_m: int,
    shift: int,
    main_lde_cols: dict[str, list[int]],
    aux_lde_cols: dict[str, list[int]],
    r_bind_f0: int,
    r_bind_f1: int,
    alpha_mix: int,
    rho_main: list[int],
    rho_aux: list[int],
    rho_q: int,
    commitments: dict[str, Any],
) -> list[int]:
    layout = VpvmCommitTraceLayoutV1()
    if len(rho_main) != len(layout.MAIN_COLS) or len(rho_aux) != len(layout.AUX_COLS):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Expected final accumulators from public inputs commitments.
    exp = [
        int(commitments.get("program_commit_f0", 0)),
        int(commitments.get("program_commit_f1", 0)),
        int(commitments.get("lut_commit_f0", 0)),
        int(commitments.get("lut_commit_f1", 0)),
        int(commitments.get("dataset_commit_f0", 0)),
        int(commitments.get("dataset_commit_f1", 0)),
        int(commitments.get("weights_before_commit_f0", 0)),
        int(commitments.get("weights_before_commit_f1", 0)),
        int(commitments.get("weights_after_commit_f0", 0)),
        int(commitments.get("weights_after_commit_f1", 0)),
    ]
    exp = [int(v) % P_GOLDILOCKS for v in exp]

    n = int(n_trace_u32)
    m = int(m_lde_u32)
    b = int(blowup_factor_u32)
    omega_n = pow(int(omega_m) % P_GOLDILOCKS, int(b), P_GOLDILOCKS)
    g_last = pow(int(omega_n), n - 1, P_GOLDILOCKS)
    inv_n = inv(n % P_GOLDILOCKS)

    # Precompute x points on the LDE coset domain.
    dom = CosetDomainV1(size=m, omega=int(omega_m), shift=int(shift))

    out = [0] * m
    for i in range(m):
        # Current/next rows for AIR transition evaluation.
        j = (i + b) & (m - 1)
        cur_main = [int(main_lde_cols[name][i]) for name in layout.MAIN_COLS]
        nxt_main = [int(main_lde_cols[name][j]) for name in layout.MAIN_COLS]
        cur_aux = [int(aux_lde_cols[name][i]) for name in layout.AUX_COLS]
        nxt_aux = [int(aux_lde_cols[name][j]) for name in layout.AUX_COLS]

        tc = eval_transition_constraints_v1(
            cur_main=cur_main,
            nxt_main=nxt_main,
            cur_aux=cur_aux,
            nxt_aux=nxt_aux,
            r_bind_f0=int(r_bind_f0),
            r_bind_f1=int(r_bind_f1),
        )
        t_mix = mix_constraints_v1(constraints=tc, alpha_mix=int(alpha_mix))

        # Boundary mixes.
        b0_mix = mix_constraints_v1(constraints=cur_aux, alpha_mix=int(alpha_mix))
        sel_pad = int(cur_main[layout.MAIN_COLS.index("sel_pad")]) % P_GOLDILOCKS
        k_items = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)
        items = [int(cur_main[layout.MAIN_COLS.index(f"item{i}")]) % P_GOLDILOCKS for i in range(k_items)]
        blast_constraints = [sub(sel_pad, 1), *items] + [sub(int(cur_aux[k]), exp[k]) for k in range(len(exp))]
        blast_mix = mix_constraints_v1(constraints=blast_constraints, alpha_mix=int(alpha_mix))

        x = int(dom.x_at(i)) % P_GOLDILOCKS
        z = (pow(int(x), n, P_GOLDILOCKS) - 1) % P_GOLDILOCKS
        inv_z = inv(int(z))

        # Q(x) = t_mix*(x-g_last)/Z(x) + b0_mix/(n*(x-1)) + blast_mix*g_last/(n*(x-g_last))
        qx = (int(t_mix) * (x - int(g_last)) % P_GOLDILOCKS) * int(inv_z) % P_GOLDILOCKS
        qx = (qx + int(b0_mix) * int(inv_n) % P_GOLDILOCKS * int(inv((x - 1) % P_GOLDILOCKS)) % P_GOLDILOCKS) % P_GOLDILOCKS
        qx = (qx + int(blast_mix) * int(inv_n) % P_GOLDILOCKS * int(g_last) % P_GOLDILOCKS * int(inv((x - int(g_last)) % P_GOLDILOCKS)) % P_GOLDILOCKS) % P_GOLDILOCKS

        # Composition polynomial is just the quotient evaluation (optionally scaled by rho_q).
        # Important: do NOT add raw trace columns here; that would make the degree scale with n_trace
        # and break the pinned max_remainder_degree_u32 bound.
        out[i] = (int(rho_q) * int(qx)) % P_GOLDILOCKS

    return [int(v) % P_GOLDILOCKS for v in out]


def _hash_felt_leaf_v1(params: PoseidonParamsGldV1, v: int) -> bytes:
    return poseidon_sponge_hash32_v1(params, data=_U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF))


def _prove_fri_v1(
    *,
    params: PoseidonParamsGldV1,
    transcript: PoseidonTranscriptV1,
    domain: CosetDomainV1,
    evals0: list[int],
    num_queries_u32: int,
    max_remainder_degree_u32: int,
):
    """Interactive FRI using the Poseidon transcript (roots absorbed per round)."""

    from .stark_fft_gld_v1 import fold_fri_layer, poly_degree_from_evals
    from .stark_fri_v1 import FriProofV1, FriQueryOpeningV1

    evals = [int(v) % P_GOLDILOCKS for v in list(evals0)]
    if len(evals) != int(domain.size) or (len(evals) & (len(evals) - 1)) != 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Remainder layer size: pow2 >= 2*max_remainder_degree.
    rem_size = 1
    target = max(1, 2 * int(max_remainder_degree_u32))
    while rem_size < target:
        rem_size <<= 1

    layers: list[list[int]] = []
    trees: list[PoseidonMerkleTreeV1] = []
    roots: list[bytes] = []
    alphas: list[int] = []
    dom = domain

    while True:
        layers.append(list(evals))
        leaves = [_hash_felt_leaf_v1(params, v) for v in evals]
        tree = PoseidonMerkleTreeV1.build(params=params, leaves32=leaves)
        trees.append(tree)
        roots.append(bytes(tree.root32))
        transcript.absorb_bytes32(bytes(tree.root32))

        if len(evals) <= rem_size:
            break

        alpha = int(transcript.squeeze_field()) % P_GOLDILOCKS
        if alpha == 0:
            alpha = 1
        alphas.append(int(alpha))

        xs = [dom.x_at(i) for i in range(len(evals))]
        evals = fold_fri_layer(evals=evals, domain_x=xs, alpha=int(alpha))
        # Domain update: omega^2, shift^2, size/2.
        dom = CosetDomainV1(size=len(evals), omega=(int(dom.omega) * int(dom.omega)) % P_GOLDILOCKS, shift=(int(dom.shift) * int(dom.shift)) % P_GOLDILOCKS)

    remainder_evals = tuple(int(v) % P_GOLDILOCKS for v in layers[-1])
    # Degree bound check (defensive): remainder degree <= max_remainder_degree.
    if not poly_degree_from_evals(evals=list(remainder_evals), omega=int(dom.omega), max_degree_inclusive=int(max_remainder_degree_u32)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    # Query indices derived after all roots are absorbed.
    qn = int(num_queries_u32)
    query_indices = [int(transcript.squeeze_u64()) % int(domain.size) for _ in range(qn)]

    openings: list[FriQueryOpeningV1] = []
    for idx0 in query_indices:
        idx = int(idx0)
        vals_lo: list[int] = []
        vals_hi: list[int] = []
        auth_lo: list[tuple[bytes, ...]] = []
        auth_hi: list[tuple[bytes, ...]] = []
        for layer_i in range(len(layers) - 1):
            layer = layers[layer_i]
            m = len(layer)
            half = m // 2
            pair = idx ^ half
            vals_lo.append(int(layer[idx]) % P_GOLDILOCKS)
            vals_hi.append(int(layer[pair]) % P_GOLDILOCKS)
            auth_lo.append(tuple(trees[layer_i].open(idx).auth_path32))
            auth_hi.append(tuple(trees[layer_i].open(pair).auth_path32))
            idx = idx & (half - 1)
        openings.append(FriQueryOpeningV1(index_u32=int(idx0), vals_lo=tuple(vals_lo), vals_hi=tuple(vals_hi), auth_lo=tuple(auth_lo), auth_hi=tuple(auth_hi)))

    fri = FriProofV1(layer_roots32=tuple(roots), alphas=tuple(alphas), remainder_evals=remainder_evals, query_openings=tuple(openings))
    return bytes(roots[0]), fri


def _encode_fri_proof_payload_v1(fri_proof) -> bytes:
    from .stark_fri_v1 import encode_fri_proof_payload_v1

    return bytes(encode_fri_proof_payload_v1(fri_proof))


def _build_trace_openings_payload_v1(
    *,
    main_tree: PoseidonMerkleTreeV1,
    aux_tree: PoseidonMerkleTreeV1,
    main_lde_cols: dict[str, list[int]],
    aux_lde_cols: dict[str, list[int]],
    query_indices: list[int],
    blowup_factor_u32: int,
) -> list[dict[str, Any]]:
    layout = VpvmCommitTraceLayoutV1()
    m = int(main_tree.leaf_count)
    b = int(blowup_factor_u32)
    out: list[dict[str, Any]] = []
    for idx0 in query_indices:
        i = int(idx0) % m
        j = (i + b) & (m - 1)
        m_op = main_tree.open(i)
        m_op_n = main_tree.open(j)
        a_op = aux_tree.open(i)
        a_op_n = aux_tree.open(j)
        out.append(
            {
                "index_u32": int(i),
                "main_row": [int(main_lde_cols[name][i]) % P_GOLDILOCKS for name in layout.MAIN_COLS],
                "main_auth": [bytes(x) for x in m_op.auth_path32],
                "main_row_next": [int(main_lde_cols[name][j]) % P_GOLDILOCKS for name in layout.MAIN_COLS],
                "main_auth_next": [bytes(x) for x in m_op_n.auth_path32],
                "aux_row": [int(aux_lde_cols[name][i]) % P_GOLDILOCKS for name in layout.AUX_COLS],
                "aux_auth": [bytes(x) for x in a_op.auth_path32],
                "aux_row_next": [int(aux_lde_cols[name][j]) % P_GOLDILOCKS for name in layout.AUX_COLS],
                "aux_auth_next": [bytes(x) for x in a_op_n.auth_path32],
            }
        )
    return out


def _encode_stark_vm_payload_v1(*, trace_openings: list[dict[str, Any]], fri_payload: bytes) -> bytes:
    out = bytearray()
    out += _U32LE.pack(int(len(trace_openings)) & 0xFFFFFFFF)
    for q in trace_openings:
        out += _U32LE.pack(int(q["index_u32"]) & 0xFFFFFFFF)
        for v in q["main_row"]:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q["main_auth"])) & 0xFFFFFFFF)
        for node in q["main_auth"]:
            out += bytes(node)
        for v in q["main_row_next"]:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q["main_auth_next"])) & 0xFFFFFFFF)
        for node in q["main_auth_next"]:
            out += bytes(node)
        for v in q["aux_row"]:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q["aux_auth"])) & 0xFFFFFFFF)
        for node in q["aux_auth"]:
            out += bytes(node)
        for v in q["aux_row_next"]:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q["aux_auth_next"])) & 0xFFFFFFFF)
        for node in q["aux_auth_next"]:
            out += bytes(node)

    out += _U32LE.pack(int(len(fri_payload)) & 0xFFFFFFFF)
    out += bytes(fri_payload)
    return bytes(out)
