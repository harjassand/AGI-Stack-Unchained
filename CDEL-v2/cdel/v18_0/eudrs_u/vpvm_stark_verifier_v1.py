"""VPVM STARK verifier (stark_vm_v1, v1).

This verifier checks:
  - proof header schema + deterministic binding to config/program/public inputs
  - public input hash rules (GCJ-1)
  - Poseidon-Merkle openings for main/aux trace commitments
  - AIR constraint satisfaction at query points (via composition polynomial)
  - FRI low-degree proof of the composition polynomial

Fail-closed: any mismatch maps to one primary PCLP reason code.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

from ..omega_common_v1 import validate_schema
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_prefixed
from .gld_field_v1 import CosetDomainV1, P_GOLDILOCKS, inv, primitive_root_of_unity, sub
from .pclp_common_v1 import (
    COMMIT_ALGO_ID_ROLLHASH32X2_V1,
    EUDRSU_PCLP_PROOF_INVALID,
    EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH,
    EUDRSU_PCLP_SCHEMA_INVALID,
    ROLLHASH32X2_BATCH_U32_PER_ROW_V1,
    SCHEMA_STARK_VM_PROOF_V1,
    bytes32_to_hex64,
    compute_public_inputs_base_hash32,
    compute_public_inputs_hash32,
    compute_rollhash32x2_commitments_v1,
    hex64_to_bytes32,
    is_power_of_two_u32,
)
from .poseidon_gld_v1 import PoseidonParamsGldV1, parse_poseidon_params_gld_v1_bin, poseidon_sponge_hash32_felts_v1, poseidon_sponge_hash32_v1
from .stark_fri_v1 import FriProofV1, decode_fri_proof_payload_v1
from .stark_merkle_poseidon_v1 import MerkleOpeningV1, verify_merkle_opening_v1
from .stark_transcript_poseidon_v1 import PoseidonTranscriptV1
from .vpvm_stark_air_v1 import VpvmCommitTraceLayoutV1, eval_transition_constraints_v1, mix_constraints_v1


_U32LE = struct.Struct("<I")
_U64LE = struct.Struct("<Q")


def _parse_proof_v1_bin(proof_bytes: bytes) -> tuple[dict[str, Any], bytes, bytes]:
    mv = memoryview(bytes(proof_bytes))
    if mv.ndim != 1 or len(mv) < 4:
        raise ValueError("bad proof bytes")
    header_len = int(struct.unpack_from("<I", mv, 0)[0])
    if header_len < 0 or 4 + header_len > len(mv):
        raise ValueError("bad header length")
    header_bytes = bytes(mv[4 : 4 + header_len])
    header_obj = gcj1_loads_and_verify_canonical(header_bytes)
    if not isinstance(header_obj, dict):
        raise ValueError("header not dict")
    payload = bytes(mv[4 + header_len :])
    return dict(header_obj), header_bytes, payload


def _choose_lde_shift_v1(*, n_trace_u32: int, omega_n: int) -> int:
    n = int(n_trace_u32)
    g_last = pow(int(omega_n) % P_GOLDILOCKS, n - 1, P_GOLDILOCKS)
    for cand in [3, 5, 7, 11, 13, 17, 19, 23]:
        s = int(cand) % P_GOLDILOCKS
        if s == 0 or s == 1 or s == g_last:
            continue
        if pow(s, n, P_GOLDILOCKS) == 1:
            continue
        return int(s)
    raise ValueError("no shift")


def _hash_row_v1(params: PoseidonParamsGldV1, row_felts: list[int]) -> bytes:
    return poseidon_sponge_hash32_felts_v1(params, felts=[int(v) % P_GOLDILOCKS for v in row_felts])


def _hash_felt_leaf_v1(params: PoseidonParamsGldV1, v: int) -> bytes:
    return poseidon_sponge_hash32_v1(params, data=_U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF))


def _decode_stark_vm_payload_v1(*, payload: bytes) -> tuple[list[dict[str, Any]], FriProofV1]:
    mv = memoryview(bytes(payload))
    off = 0

    def _u32() -> int:
        nonlocal off
        if off + 4 > len(mv):
            raise ValueError("eof u32")
        (x,) = _U32LE.unpack_from(mv, off)
        off += 4
        return int(x)

    def _u64() -> int:
        nonlocal off
        if off + 8 > len(mv):
            raise ValueError("eof u64")
        (x,) = _U64LE.unpack_from(mv, off)
        off += 8
        return int(x) % P_GOLDILOCKS

    qn = _u32()
    layout = VpvmCommitTraceLayoutV1()
    main_w = len(layout.MAIN_COLS)
    aux_w = len(layout.AUX_COLS)
    openings: list[dict[str, Any]] = []
    for _ in range(qn):
        idx = _u32()
        main_row = [_u64() for _ in range(main_w)]
        main_auth_n = _u32()
        main_auth: list[bytes] = []
        for _ in range(main_auth_n):
            if off + 32 > len(mv):
                raise ValueError("eof auth")
            main_auth.append(bytes(mv[off : off + 32]))
            off += 32
        main_row_next = [_u64() for _ in range(main_w)]
        main_auth_next_n = _u32()
        main_auth_next: list[bytes] = []
        for _ in range(main_auth_next_n):
            if off + 32 > len(mv):
                raise ValueError("eof auth next")
            main_auth_next.append(bytes(mv[off : off + 32]))
            off += 32
        aux_row = [_u64() for _ in range(aux_w)]
        aux_auth_n = _u32()
        aux_auth: list[bytes] = []
        for _ in range(aux_auth_n):
            if off + 32 > len(mv):
                raise ValueError("eof aux auth")
            aux_auth.append(bytes(mv[off : off + 32]))
            off += 32
        aux_row_next = [_u64() for _ in range(aux_w)]
        aux_auth_next_n = _u32()
        aux_auth_next: list[bytes] = []
        for _ in range(aux_auth_next_n):
            if off + 32 > len(mv):
                raise ValueError("eof aux auth next")
            aux_auth_next.append(bytes(mv[off : off + 32]))
            off += 32

        openings.append(
            {
                "index_u32": int(idx),
                "main_row": main_row,
                "main_auth": main_auth,
                "main_row_next": main_row_next,
                "main_auth_next": main_auth_next,
                "aux_row": aux_row,
                "aux_auth": aux_auth,
                "aux_row_next": aux_row_next,
                "aux_auth_next": aux_auth_next,
            }
        )

    fri_len = _u32()
    if off + fri_len != len(mv):
        raise ValueError("bad fri payload length")
    fri_payload = bytes(mv[off : off + fri_len])
    fri = decode_fri_proof_payload_v1(fri_payload)
    return openings, fri


def _expected_fri_rounds(*, m_lde: int, max_remainder_degree: int) -> tuple[int, int, int]:
    rem_size = 1
    target = max(1, 2 * int(max_remainder_degree))
    while rem_size < target:
        rem_size <<= 1
    if rem_size > int(m_lde):
        rem_size = int(m_lde)
    rounds = 0
    size = int(m_lde)
    while size > rem_size:
        size //= 2
        rounds += 1
    layers = rounds + 1  # includes remainder layer
    return int(rounds), int(rem_size), int(layers)


def _verify_fri_v1(
    *,
    params: PoseidonParamsGldV1,
    transcript: PoseidonTranscriptV1,
    domain: CosetDomainV1,
    fri: FriProofV1,
    num_queries_u32: int,
    max_remainder_degree_u32: int,
) -> tuple[bool, list[int]]:
    try:
        m0 = int(domain.size)
        rounds, rem_size, layers = _expected_fri_rounds(m_lde=m0, max_remainder_degree=int(max_remainder_degree_u32))
        if len(fri.layer_roots32) != layers:
            return False, []
        if len(fri.alphas) != rounds:
            return False, []
        if len(fri.query_openings) != int(num_queries_u32):
            return False, []
        if len(fri.remainder_evals) != rem_size:
            return False, []

        # Absorb roots and re-derive alphas.
        alphas: list[int] = []
        for i, r in enumerate(fri.layer_roots32):
            transcript.absorb_bytes32(bytes(r))
            if i < rounds:
                a = int(transcript.squeeze_field()) % P_GOLDILOCKS
                if a == 0:
                    a = 1
                alphas.append(int(a))
                if int(fri.alphas[i]) % P_GOLDILOCKS != int(a):
                    return False, []

        # Derive query indices and check they match proof.
        q_expected = [int(transcript.squeeze_u64()) % m0 for _ in range(int(num_queries_u32))]
        if [int(q.index_u32) for q in fri.query_openings] != q_expected:
            return False, []

        # Verify remainder root matches.
        rem_leaves = [_hash_felt_leaf_v1(params, int(v)) for v in fri.remainder_evals]
        # Recompute remainder Merkle root.
        from .stark_merkle_poseidon_v1 import PoseidonMerkleTreeV1

        rem_tree = PoseidonMerkleTreeV1.build(params=params, leaves32=list(rem_leaves))
        if bytes(rem_tree.root32) != bytes(fri.layer_roots32[-1]):
            return False, []

        # Verify remainder degree bound (treating as scaled-by-shift polynomial is OK).
        from .stark_fft_gld_v1 import poly_degree_from_evals

        omega = int(domain.omega)
        shift = int(domain.shift)
        size = int(domain.size)
        for _ in range(rounds):
            omega = (omega * omega) % P_GOLDILOCKS
            shift = (shift * shift) % P_GOLDILOCKS
            size //= 2
        if not poly_degree_from_evals(evals=list(int(v) % P_GOLDILOCKS for v in fri.remainder_evals), omega=int(omega), max_degree_inclusive=int(max_remainder_degree_u32)):
            return False, []

        # Verify query openings and folding relations.
        omega_r = int(domain.omega)
        shift_r = int(domain.shift)
        m_r = int(domain.size)
        for q in fri.query_openings:
            idx0 = int(q.index_u32) % m0
            idx = idx0
            if len(q.vals_lo) != rounds or len(q.vals_hi) != rounds:
                return False, []
            if len(q.auth_lo) != rounds or len(q.auth_hi) != rounds:
                return False, []
            omega_r = int(domain.omega)
            shift_r = int(domain.shift)
            m_r = int(domain.size)
            for layer_i in range(rounds):
                half = m_r // 2
                pair = idx ^ half
                # Verify Merkle openings at this layer.
                leaf_lo = _hash_felt_leaf_v1(params, int(q.vals_lo[layer_i]))
                leaf_hi = _hash_felt_leaf_v1(params, int(q.vals_hi[layer_i]))
                op_lo = MerkleOpeningV1(leaf32=leaf_lo, index_u32=int(idx), auth_path32=tuple(q.auth_lo[layer_i]))
                op_hi = MerkleOpeningV1(leaf32=leaf_hi, index_u32=int(pair), auth_path32=tuple(q.auth_hi[layer_i]))
                if not verify_merkle_opening_v1(params=params, opening=op_lo, expected_root32=bytes(fri.layer_roots32[layer_i])):
                    return False, []
                if not verify_merkle_opening_v1(params=params, opening=op_hi, expected_root32=bytes(fri.layer_roots32[layer_i])):
                    return False, []

                # Folding relation check.
                alpha = int(alphas[layer_i]) % P_GOLDILOCKS
                x = (shift_r * pow(omega_r, idx & (half - 1), P_GOLDILOCKS)) % P_GOLDILOCKS
                inv2 = (P_GOLDILOCKS + 1) // 2
                v_idx = int(q.vals_lo[layer_i]) % P_GOLDILOCKS
                v_pair = int(q.vals_hi[layer_i]) % P_GOLDILOCKS
                # Openings are stored as (idx, idx^half). For folding we need (i, i+half) where i is in the first half.
                if idx & half:
                    # idx is i+half (second half): v_idx = f(-x), v_pair = f(x).
                    fx = v_pair
                    fmx = v_idx
                else:
                    fx = v_idx
                    fmx = v_pair
                even = (fx + fmx) * inv2 % P_GOLDILOCKS
                odd = (fx - fmx) * inv2 % P_GOLDILOCKS
                odd = odd * inv(x) % P_GOLDILOCKS
                folded = (even + alpha * odd) % P_GOLDILOCKS

                idx_next = idx & (half - 1)
                if layer_i + 1 < rounds:
                    if int(q.vals_lo[layer_i + 1]) % P_GOLDILOCKS != int(folded) % P_GOLDILOCKS:
                        return False, []
                else:
                    if int(fri.remainder_evals[idx_next]) % P_GOLDILOCKS != int(folded) % P_GOLDILOCKS:
                        return False, []
                idx = idx_next
                omega_r = (omega_r * omega_r) % P_GOLDILOCKS
                shift_r = (shift_r * shift_r) % P_GOLDILOCKS
                m_r = half

        return True, q_expected
    except Exception:
        return False, []


def verify_stark_vm_proof_v1(
    *,
    vpvm_config_obj: dict[str, Any],
    poseidon_params_bin: bytes,
    vpvm_public_inputs_obj: dict[str, Any],
    program_bytes: bytes,
    proof_bytes: bytes,
    # Content inputs required to recompute rollhash32x2 commitments (v1).
    lut_bytes: bytes | None = None,
    examples: list[Any] | None = None,
    weights_before: Any | None = None,
    weights_after: Any | None = None,
) -> tuple[bool, str]:
    """Verify stark_vm_v1 proof.

    Returns (ok, reason_code) where reason_code is one of:
      - EUDRSU_PCLP_SCHEMA_INVALID
      - EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
      - EUDRSU_PCLP_PROOF_INVALID
    """

    if lut_bytes is None or examples is None or weights_before is None or weights_after is None:
        return False, EUDRSU_PCLP_SCHEMA_INVALID

    try:
        header_obj, _header_canon_bytes, payload = _parse_proof_v1_bin(bytes(proof_bytes))
        validate_schema(header_obj, SCHEMA_STARK_VM_PROOF_V1)
    except Exception:
        return False, EUDRSU_PCLP_SCHEMA_INVALID

    try:
        params = parse_poseidon_params_gld_v1_bin(bytes(poseidon_params_bin))

        cfg_id = str(vpvm_config_obj.get("vpvm_config_id", "")).strip()
        if str(header_obj.get("vpvm_config_id", "")).strip() != cfg_id:
            return False, EUDRSU_PCLP_PROOF_INVALID

        max_steps_u32 = int(vpvm_config_obj.get("trace", {}).get("max_steps_u32", 0))
        blowup = int(vpvm_config_obj.get("stark", {}).get("blowup_factor_u32", 0))
        fri_cfg = dict(vpvm_config_obj.get("fri", {}))
        if blowup <= 0:
            return False, EUDRSU_PCLP_PROOF_INVALID

        # Public input hash rules (normative).
        pi_obj = dict(vpvm_public_inputs_obj.get("public_inputs", {}))
        pi_hash32 = compute_public_inputs_hash32(pi_obj)
        if bytes32_to_hex64(pi_hash32) != str(vpvm_public_inputs_obj.get("public_inputs_hash32_hex", "")).strip():
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        pi_base_hash32 = compute_public_inputs_base_hash32(pi_obj)
        if bytes32_to_hex64(pi_base_hash32) != str(vpvm_public_inputs_obj.get("public_inputs_base_hash32_hex", "")).strip():
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        # Header binds to program bytes.
        program_id = sha256_prefixed(bytes(program_bytes))
        if str(header_obj.get("program_id", "")).strip() != str(program_id).strip():
            return False, EUDRSU_PCLP_PROOF_INVALID
        if str(header_obj.get("public_inputs_hash32_hex", "")).strip() != bytes32_to_hex64(pi_hash32):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        # Trace length + pinned FRI params.
        n_trace = int(header_obj.get("trace_len_u32", 0))
        if not is_power_of_two_u32(n_trace) or n_trace <= 0:
            return False, EUDRSU_PCLP_PROOF_INVALID
        if int(max_steps_u32) > 0 and n_trace > int(max_steps_u32):
            return False, EUDRSU_PCLP_PROOF_INVALID

        for k in ["folding_factor_u32", "num_queries_u32", "grinding_bits_u32", "max_remainder_degree_u32"]:
            if int(header_obj.get("fri_params", {}).get(k, -1)) != int(fri_cfg.get(k, -2)):
                return False, EUDRSU_PCLP_PROOF_INVALID

        m_lde = int(n_trace) * int(blowup)
        if (m_lde & (m_lde - 1)) != 0 or m_lde <= 0:
            return False, EUDRSU_PCLP_PROOF_INVALID

        # Decode payload: trace openings + FRI proof.
        trace_openings, fri = _decode_stark_vm_payload_v1(payload=bytes(payload))

        # Header roots must match FRI proof roots.
        if bytes32_to_hex64(bytes(fri.layer_roots32[0])) != str(header_obj.get("composition_root32_hex", "")).strip():
            return False, EUDRSU_PCLP_PROOF_INVALID
        hdr_fri_roots = [str(x).strip() for x in list(header_obj.get("fri_roots32_hex", []))]
        if hdr_fri_roots != [bytes32_to_hex64(bytes(r)) for r in fri.layer_roots32]:
            return False, EUDRSU_PCLP_PROOF_INVALID

        main_root32 = hex64_to_bytes32(str(header_obj.get("main_trace_root32_hex", "")).strip())
        aux_root32 = hex64_to_bytes32(str(header_obj.get("aux_trace_root32_hex", "")).strip())
        comp_root32 = hex64_to_bytes32(str(header_obj.get("composition_root32_hex", "")).strip())

        # Transcript: derive r_bind and commitments, then composition challenges.
        tr = PoseidonTranscriptV1(params=params)
        tr.absorb_bytes32(bytes(pi_base_hash32))
        tr.absorb_bytes32(bytes(main_root32))
        r0 = int(tr.squeeze_field()) % P_GOLDILOCKS
        r1 = int(tr.squeeze_field()) % P_GOLDILOCKS

        commitments = dict(pi_obj.get("commitments", {}))
        if str(commitments.get("commit_algo_id", "")).strip() != COMMIT_ALGO_ID_ROLLHASH32X2_V1:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if int(commitments.get("r_bind_u64_0", -1)) != int(r0):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if int(commitments.get("r_bind_u64_1", -1)) != int(r1):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        commits_exp = compute_rollhash32x2_commitments_v1(
            r_bind_u64_0=int(r0),
            r_bind_u64_1=int(r1),
            program_bytes=bytes(program_bytes),
            lut_bytes=bytes(lut_bytes),
            examples=list(examples),
            weights_before=weights_before,
            weights_after=weights_after,
        )
        for k in [
            "program_commit_f0",
            "program_commit_f1",
            "lut_commit_f0",
            "lut_commit_f1",
            "dataset_commit_f0",
            "dataset_commit_f1",
            "weights_before_commit_f0",
            "weights_before_commit_f1",
            "weights_after_commit_f0",
            "weights_after_commit_f1",
        ]:
            if int(commitments.get(k, -1)) != int(commits_exp.get(k)):
                return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        # Composition challenges.
        tr.absorb_bytes32(bytes(aux_root32))
        tr.absorb_bytes32(bytes(pi_hash32))
        alpha_mix = int(tr.squeeze_field()) % P_GOLDILOCKS
        if alpha_mix == 0:
            alpha_mix = 1
        layout = VpvmCommitTraceLayoutV1()
        rho_main = [int(tr.squeeze_field()) % P_GOLDILOCKS for _ in range(len(layout.MAIN_COLS))]
        rho_aux = [int(tr.squeeze_field()) % P_GOLDILOCKS for _ in range(len(layout.AUX_COLS))]
        rho_q = int(tr.squeeze_field()) % P_GOLDILOCKS

        # Verify FRI (absorbs FRI roots and derives query indices).
        omega_m = primitive_root_of_unity(int(m_lde))
        omega_n = pow(int(omega_m), int(blowup), P_GOLDILOCKS)
        shift = _choose_lde_shift_v1(n_trace_u32=int(n_trace), omega_n=int(omega_n))
        ok_fri, q_expected = _verify_fri_v1(
            params=params,
            transcript=tr,
            domain=CosetDomainV1(size=int(m_lde), omega=int(omega_m), shift=int(shift)),
            fri=fri,
            num_queries_u32=int(fri_cfg.get("num_queries_u32", 0)),
            max_remainder_degree_u32=int(fri_cfg.get("max_remainder_degree_u32", 0)),
        )
        if not ok_fri:
            return False, EUDRSU_PCLP_PROOF_INVALID

        if len(trace_openings) != len(q_expected):
            return False, EUDRSU_PCLP_PROOF_INVALID
        if [int(o.get("index_u32", -1)) for o in trace_openings] != q_expected:
            return False, EUDRSU_PCLP_PROOF_INVALID

        # Check Merkle openings for main/aux traces and constraint consistency with composition values.
        b = int(blowup)
        dom = CosetDomainV1(size=int(m_lde), omega=int(omega_m), shift=int(shift))
        g_last = pow(int(omega_n), int(n_trace) - 1, P_GOLDILOCKS)
        inv_n = inv(int(n_trace) % P_GOLDILOCKS)

        # Expected final accumulators in AUX_COLS order.
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

        # Build a mapping from query index -> FRI layer0 opened value for that index.
        fri_vals0_by_idx: dict[int, int] = {int(q.index_u32): int(q.vals_lo[0]) % P_GOLDILOCKS for q in fri.query_openings}

        for op in trace_openings:
            idx = int(op["index_u32"]) % int(m_lde)
            idx_next = (idx + b) & (int(m_lde) - 1)

            main_row = [int(v) % P_GOLDILOCKS for v in list(op["main_row"])]
            main_row_next = [int(v) % P_GOLDILOCKS for v in list(op["main_row_next"])]
            aux_row = [int(v) % P_GOLDILOCKS for v in list(op["aux_row"])]
            aux_row_next = [int(v) % P_GOLDILOCKS for v in list(op["aux_row_next"])]

            # Main trace merkle openings.
            leaf_main = _hash_row_v1(params, main_row)
            open_main = MerkleOpeningV1(leaf32=leaf_main, index_u32=int(idx), auth_path32=tuple(bytes(x) for x in op["main_auth"]))
            if not verify_merkle_opening_v1(params=params, opening=open_main, expected_root32=bytes(main_root32)):
                return False, EUDRSU_PCLP_PROOF_INVALID
            leaf_main_n = _hash_row_v1(params, main_row_next)
            open_main_n = MerkleOpeningV1(leaf32=leaf_main_n, index_u32=int(idx_next), auth_path32=tuple(bytes(x) for x in op["main_auth_next"]))
            if not verify_merkle_opening_v1(params=params, opening=open_main_n, expected_root32=bytes(main_root32)):
                return False, EUDRSU_PCLP_PROOF_INVALID

            # Aux trace merkle openings.
            leaf_aux = _hash_row_v1(params, aux_row)
            open_aux = MerkleOpeningV1(leaf32=leaf_aux, index_u32=int(idx), auth_path32=tuple(bytes(x) for x in op["aux_auth"]))
            if not verify_merkle_opening_v1(params=params, opening=open_aux, expected_root32=bytes(aux_root32)):
                return False, EUDRSU_PCLP_PROOF_INVALID
            leaf_aux_n = _hash_row_v1(params, aux_row_next)
            open_aux_n = MerkleOpeningV1(leaf32=leaf_aux_n, index_u32=int(idx_next), auth_path32=tuple(bytes(x) for x in op["aux_auth_next"]))
            if not verify_merkle_opening_v1(params=params, opening=open_aux_n, expected_root32=bytes(aux_root32)):
                return False, EUDRSU_PCLP_PROOF_INVALID

            # Constraint consistency via composition polynomial check at this x.
            tc = eval_transition_constraints_v1(
                cur_main=main_row,
                nxt_main=main_row_next,
                cur_aux=aux_row,
                nxt_aux=aux_row_next,
                r_bind_f0=int(r0),
                r_bind_f1=int(r1),
            )
            t_mix = mix_constraints_v1(constraints=tc, alpha_mix=int(alpha_mix))
            b0_mix = mix_constraints_v1(constraints=aux_row, alpha_mix=int(alpha_mix))
            sel_pad = int(main_row[layout.MAIN_COLS.index("sel_pad")]) % P_GOLDILOCKS
            k_items = int(ROLLHASH32X2_BATCH_U32_PER_ROW_V1)
            items = [int(main_row[layout.MAIN_COLS.index(f"item{i}")]) % P_GOLDILOCKS for i in range(k_items)]
            blast_constraints = [sub(sel_pad, 1), *items] + [sub(int(aux_row[k]), exp[k]) for k in range(len(exp))]
            blast_mix = mix_constraints_v1(constraints=blast_constraints, alpha_mix=int(alpha_mix))

            x = int(dom.x_at(idx)) % P_GOLDILOCKS
            z = (pow(int(x), int(n_trace), P_GOLDILOCKS) - 1) % P_GOLDILOCKS
            inv_z = inv(int(z))
            qx = (int(t_mix) * (x - int(g_last)) % P_GOLDILOCKS) * int(inv_z) % P_GOLDILOCKS
            qx = (qx + int(b0_mix) * int(inv_n) % P_GOLDILOCKS * int(inv((x - 1) % P_GOLDILOCKS)) % P_GOLDILOCKS) % P_GOLDILOCKS
            qx = (qx + int(blast_mix) * int(inv_n) % P_GOLDILOCKS * int(g_last) % P_GOLDILOCKS * int(inv((x - int(g_last)) % P_GOLDILOCKS)) % P_GOLDILOCKS) % P_GOLDILOCKS

            # Composition polynomial is just the quotient evaluation (optionally scaled by rho_q).
            # See prover note: raw trace columns must not be added, or the degree would scale with n_trace.
            comp = (int(rho_q) * int(qx)) % P_GOLDILOCKS

            opened_comp = int(fri_vals0_by_idx.get(int(idx), -1)) % P_GOLDILOCKS
            if int(opened_comp) != int(comp):
                return False, EUDRSU_PCLP_PROOF_INVALID

        # Storage-level payload integrity (fail-closed).
        payload_len_u32 = int(header_obj.get("proof_payload_len_u32", -1))
        if payload_len_u32 != int(len(payload)):
            return False, EUDRSU_PCLP_PROOF_INVALID
        if hashlib.sha256(bytes(payload)).hexdigest() != str(header_obj.get("proof_payload_sha256_hex", "")).strip():
            return False, EUDRSU_PCLP_PROOF_INVALID

        return True, ""
    except Exception:
        return False, EUDRSU_PCLP_SCHEMA_INVALID


__all__ = ["verify_stark_vm_proof_v1"]
