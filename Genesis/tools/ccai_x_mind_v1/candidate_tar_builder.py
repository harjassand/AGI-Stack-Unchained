#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .candidate_tar import build_candidate_tar
from .canonical_json import assert_no_floats, to_gcj1_bytes
from .hashes import do_payload_hash, mechanism_hash, sha256_hex


def _default_artifacts(seed: int) -> dict[str, dict[str, Any]]:
    del seed  # deterministic template for now
    mechanism = {
        "mechanism_id": "mech_world",
        "output_var": "y",
        "parents": ["x"],
        "kind": "linear",
        "params": {"b_fp": 0, "w_fp": 1000},
        "invariance_claims": [{"claim_id": "inv/world", "scope": "across_interventions", "evidence_hint": "toy"}],
        "identifiability": {"identified_by_interventions": ["do/probe"]},
    }
    mech_hash = mechanism_hash(mechanism)

    do_entries = []
    for token in ("exploit", "noop", "probe", "safe", "tamper"):
        payload = {"var_id": "x", "value_int": 0}
        do_entries.append(
            {
                "action_token": token,
                "target_mechanism_id": "mech_world",
                "do_kind": "clamp_var",
                "do_payload": payload,
                "expected_mech_hash_before": mech_hash,
                "do_payload_hash": do_payload_hash(payload),
            }
        )
    do_entries = sorted(do_entries, key=lambda e: (e["action_token"], e["target_mechanism_id"]))

    inference_kernel_isa = {
        "format": "inference_kernel_isa_v1",
        "schema_version": "1",
        "isa_id": "mind_isa_v1",
        "fixed_point": {
            "format_id": "q0_1000",
            "scale_int": 1000,
            "signed": True,
            "bits": 64,
            "rounding": "round_half_even",
            "saturation": "saturate",
        },
        "primitives": ["entropy", "normalize"],
        "schedule": {
            "max_iters": 4,
            "update_order": ["normalize", "entropy"],
            "tie_break_rule": {
                "primary": "min_total_G",
                "secondary": "min_risk",
                "tertiary": "lexicographic_action_token",
            },
        },
    }
    isa_hash = sha256_hex(to_gcj1_bytes(inference_kernel_isa))

    return {
        "markov_blanket_spec.json": {
            "format": "markov_blanket_spec_v1",
            "schema_version": "1",
            "blanket_id": "mind_blanket_v1",
            "channels": {
                "observation": {"mode": "read_only", "token_schema_id": "ccai_x_mind_observation_token_v1"},
                "action": {"mode": "write_only", "token_schema_id": "ccai_x_mind_action_token_v1"},
            },
            "side_channel_policy": {
                "network_allowed": False,
                "clock_allowed": False,
                "env_var_allowlist": ["env_lc_all", "env_path"],
                "fs_read_allowlist_prefixes": ["/tmp/ccai_x/ro"],
                "fs_write_allowlist_prefixes": ["/tmp/ccai_x/rw"],
            },
            "attestation_requirements": {
                "requires_syscall_log": True,
                "requires_io_transcript_hash_chain": True,
            },
        },
        "do_map.json": {
            "format": "do_map_v1",
            "schema_version": "1",
            "do_map_id": "mind_do_map_v1",
            "entries": do_entries,
        },
        "causal_mechanism_registry.json": {
            "format": "causal_mechanism_registry_v1",
            "schema_version": "1",
            "registry_id": "mind_registry_v1",
            "variables": [
                {"var_id": "x", "domain": {"kind": "int_range", "min_int": 0, "max_int": 1}},
                {"var_id": "y", "domain": {"kind": "int_range", "min_int": 0, "max_int": 1}},
            ],
            "mechanisms": [mechanism],
        },
        "inference_kernel_isa.json": inference_kernel_isa,
        "inference_kernel_program.json": {
            "format": "inference_kernel_program_v1",
            "schema_version": "1",
            "program_id": "mind_prog_v1",
            "isa_ref": {"isa_id": "mind_isa_v1", "sha256": isa_hash},
            "program": [
                {"op": "LOAD_MSG", "args": ["obs.o_int", "reg0"]},
                {"op": "STORE_BELIEF", "args": ["x", "reg0"]},
            ],
            "schedule": {
                "stages": [{"stage_id": "stage0", "start_ip": 0, "end_ip": 1, "max_iters": 1}],
                "max_total_iters": 1,
            },
            "tie_break_rules": {
                "primary": "min_total_G",
                "secondary": "min_risk",
                "tertiary": "lexicographic_action_token",
            },
        },
        "policy_prior.json": {
            "format": "policy_prior_v1",
            "schema_version": "1",
            "prior_id": "mind_prior_v1",
            "default_logprior_fp": -10,
            "policy_logprior": [
                {"policy_id": "pi_exploit", "logprior_fp": -5},
                {"policy_id": "pi_noop", "logprior_fp": -5},
                {"policy_id": "pi_probe", "logprior_fp": -1},
                {"policy_id": "pi_safe", "logprior_fp": -2},
                {"policy_id": "pi_tamper", "logprior_fp": -20},
            ],
            "complexity_weights": {"length_weight_fp": 1, "compute_weight_fp": 1},
        },
        "preference_capsule.json": {
            "format": "preference_capsule_v1",
            "schema_version": "1",
            "preference_id": "mind_pref_v1",
            "energy_bounds": {"min_energy_fp": 0, "max_energy_fp": 100000},
            "metrics": [
                {"metric_id": "ambiguity", "direction": "min", "weight_fp": 3},
                {"metric_id": "reward", "direction": "max", "weight_fp": 2},
                {"metric_id": "risk", "direction": "min", "weight_fp": 1},
            ],
            "admissibility": {
                "forbidden_action_tokens": ["tamper"],
                "max_horizon": 2,
                "max_branching": 5,
                "max_interventions_per_episode": 1,
            },
        },
        "coherence_operator.json": {
            "format": "coherence_operator_v1",
            "schema_version": "1",
            "operator_id": "coherence_v1",
            "method": "ipf_v1",
            "max_iters": 4,
            "residual_bound_fp": 5000,
            "damping_fp": 500,
            "merge_policy": ["belief_model", "belief_sensor"],
            "residual_definition": {"metric": "l1_fp", "rounding": "round_half_even"},
        },
    }


def _write_artifacts(artifact_dir: Path, artifacts: dict[str, dict[str, Any]]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        assert_no_floats(payload)
        (artifact_dir / name).write_bytes(to_gcj1_bytes(payload))


def main() -> int:
    parser = argparse.ArgumentParser(prog="ccai-x-mind-candidate-tar-builder")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out_tar", required=True)
    parser.add_argument("--artifact_dir", default=None)
    parser.add_argument("--print_id", action="store_true")
    args = parser.parse_args()

    out_tar = Path(args.out_tar)
    if args.artifact_dir:
        artifact_dir = Path(args.artifact_dir)
    else:
        artifact_dir = out_tar.parent / "_candidate_artifacts"
        artifacts = _default_artifacts(int(args.seed))
        _write_artifacts(artifact_dir, artifacts)

    candidate_id = build_candidate_tar(out_tar, artifact_dir)
    if args.print_id:
        print(candidate_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
