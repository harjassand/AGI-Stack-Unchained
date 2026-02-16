#!/usr/bin/env python3
import io
import tarfile
from copy import deepcopy
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_mind_v1.canonical_json import assert_no_floats, to_gcj1_bytes  # noqa: E402
from ccai_x_mind_v1.candidate_tar import build_candidate_tar  # noqa: E402
from ccai_x_mind_v1.hashes import (  # noqa: E402
    ZERO_HASH,
    candidate_id_from_tar,
    do_payload_hash,
    intervention_log_link_hash,
    mechanism_hash,
    sha256_hex,
    workspace_state_hash,
)

ROOT = TOOLS_DIR.parent
VEC_DIR = ROOT / "test_vectors" / "ccai_x_mind_v1"


def write_json(path: Path, obj) -> None:
    assert_no_floats(obj)
    path.write_bytes(to_gcj1_bytes(obj))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    lines = [to_gcj1_bytes(row) for row in rows]
    data = b"\n".join(lines) + b"\n"
    path.write_bytes(data)


def write_text(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8")


def make_vectors() -> None:
    VEC_DIR.mkdir(parents=True, exist_ok=True)

    mechanism = {
        "mechanism_id": "mech_y",
        "output_var": "y",
        "parents": ["x"],
        "kind": "linear",
        "params": {"b_fp": 0, "w_fp": 1000},
        "invariance_claims": [
            {"claim_id": "inv/mech_y", "scope": "across_interventions", "evidence_hint": "synthetic"}
        ],
        "identifiability": {"identified_by_interventions": ["do/set_x_1"]},
    }

    mechanism_registry = {
        "format": "causal_mechanism_registry_v1",
        "schema_version": "1",
        "registry_id": "toy_registry_mind_v1",
        "variables": [
            {"var_id": "x", "domain": {"kind": "int_range", "min_int": 0, "max_int": 1}},
            {"var_id": "y", "domain": {"kind": "int_range", "min_int": 0, "max_int": 1}},
        ],
        "mechanisms": [mechanism],
    }

    do_payload = {"var_id": "x", "value_int": 1}
    expected_mech_hash_before = mechanism_hash(mechanism)
    expected_do_payload_hash = do_payload_hash(do_payload)

    do_map = {
        "format": "do_map_v1",
        "schema_version": "1",
        "do_map_id": "do_map_mind_v1",
        "entries": [
            {
                "action_token": "do/set_x_1",
                "target_mechanism_id": "mech_y",
                "do_kind": "clamp_var",
                "do_payload": do_payload,
                "expected_mech_hash_before": expected_mech_hash_before,
                "do_payload_hash": expected_do_payload_hash,
            }
        ],
    }

    markov_blanket_spec = {
        "format": "markov_blanket_spec_v1",
        "schema_version": "1",
        "blanket_id": "blanket_mind_v1",
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
    }

    inference_kernel_isa = {
        "format": "inference_kernel_isa_v1",
        "schema_version": "1",
        "isa_id": "ccai_x_mind_isa_v1",
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
            "max_iters": 8,
            "update_order": ["normalize", "entropy"],
            "tie_break_rule": {
                "primary": "min_total_G",
                "secondary": "min_risk",
                "tertiary": "lexicographic_action_token",
            },
        },
    }

    inference_kernel_program = {
        "format": "inference_kernel_program_v1",
        "schema_version": "1",
        "program_id": "mind_prog_v1",
        "isa_ref": {"isa_id": "ccai_x_mind_isa_v1", "sha256": sha256_hex(to_gcj1_bytes(inference_kernel_isa))},
        "program": [
            {"op": "LOAD_MSG", "args": ["obs.o_int", "reg0"]},
            {"op": "STORE_BELIEF", "args": ["x", "reg0"]},
        ],
        "schedule": {
            "stages": [
                {"stage_id": "stage0", "start_ip": 0, "end_ip": 1, "max_iters": 1}
            ],
            "max_total_iters": 1,
        },
        "tie_break_rules": {
            "primary": "min_total_G",
            "secondary": "min_risk",
            "tertiary": "lexicographic_action_token",
        },
    }

    policy_prior = {
        "format": "policy_prior_v1",
        "schema_version": "1",
        "prior_id": "prior_mind_v1",
        "default_logprior_fp": -100,
        "policy_logprior": [
            {"policy_id": "pi_exploit", "logprior_fp": -2},
            {"policy_id": "pi_probe", "logprior_fp": -1},
        ],
        "complexity_weights": {"length_weight_fp": 1, "compute_weight_fp": 1},
    }

    preference_capsule = {
        "format": "preference_capsule_v1",
        "schema_version": "1",
        "preference_id": "pref_mind_v1",
        "energy_bounds": {"min_energy_fp": 0, "max_energy_fp": 100000},
        "metrics": [
            {"metric_id": "ambiguity", "direction": "min", "weight_fp": 3},
            {"metric_id": "reward", "direction": "max", "weight_fp": 2},
            {"metric_id": "risk", "direction": "min", "weight_fp": 1},
        ],
        "admissibility": {
            "forbidden_action_tokens": ["tamper"],
            "max_horizon": 2,
            "max_branching": 3,
            "max_interventions_per_episode": 1,
        },
    }

    coherence_operator = {
        "format": "coherence_operator_v1",
        "schema_version": "1",
        "operator_id": "cohere_mind_v1",
        "method": "ipf_v1",
        "max_iters": 4,
        "residual_bound_fp": 10,
        "damping_fp": 500,
        "merge_policy": ["belief_model", "belief_sensor"],
        "residual_definition": {"metric": "l1_fp", "rounding": "round_half_even"},
    }

    affordance_latent = {
        "format": "affordance_latent_v1",
        "schema_version": "1",
        "episode_id": "ep0001",
        "psi_seed_commitment": sha256_hex(b"psi_seed:1"),
        "do_map_permutation_digest": sha256_hex(b"perm:noop"),
        "psi_class": "swap_actions_v1",
    }

    beliefs0 = {
        "variable_marginals": [
            {"var_id": "x", "support": [0, 1], "prob_fp": [500, 500]},
            {"var_id": "y", "support": [0, 1], "prob_fp": [750, 250]},
        ],
        "parameter_estimates": [
            {"param_id": "mech_y.w_fp", "value_fp": 1000}
        ],
    }
    state_hash0 = workspace_state_hash(ZERO_HASH, beliefs0)
    workspace_state0 = {
        "format": "workspace_state_v1",
        "schema_version": "1",
        "t": 0,
        "prev_state_hash": ZERO_HASH,
        "beliefs": beliefs0,
        "state_hash": state_hash0,
    }

    beliefs1 = deepcopy(beliefs0)
    beliefs1["variable_marginals"][0]["prob_fp"] = [0, 1000]
    state_hash1 = workspace_state_hash(state_hash0, beliefs1)
    workspace_state1 = {
        "format": "workspace_state_v1",
        "schema_version": "1",
        "t": 1,
        "prev_state_hash": state_hash0,
        "beliefs": beliefs1,
        "state_hash": state_hash1,
    }

    efe_report = {
        "format": "efe_report_v1",
        "schema_version": "1",
        "t": 0,
        "candidate_id": "0" * 64,
        "isa_id": "ccai_x_mind_isa_v1",
        "policy_set_id": "one_step",
        "policies": [
            {
                "policy_id": "pi_exploit",
                "actions": ["exploit"],
                "risk_fp": 8,
                "ambiguity_fp": 60,
                "epistemic_fp": 1,
                "complexity_fp": 1,
                "total_G_fp": 70,
            },
            {
                "policy_id": "pi_probe",
                "actions": ["probe"],
                "risk_fp": 10,
                "ambiguity_fp": 30,
                "epistemic_fp": 5,
                "complexity_fp": 1,
                "total_G_fp": 46,
            },
        ],
        "chosen_policy_id": "pi_probe",
        "chosen_action_token": "probe",
        "tie_break_witness": {
            "rule": "min_total_G_then_min_risk_then_lex",
            "compared_against_policy_id": "pi_exploit",
        },
    }

    # Write JSON vectors
    write_json(VEC_DIR / "markov_blanket_spec.json", markov_blanket_spec)
    write_json(VEC_DIR / "do_map.json", do_map)
    write_json(VEC_DIR / "causal_mechanism_registry.json", mechanism_registry)
    write_json(VEC_DIR / "policy_prior.json", policy_prior)
    write_json(VEC_DIR / "preference_capsule.json", preference_capsule)
    write_json(VEC_DIR / "inference_kernel_isa.json", inference_kernel_isa)
    write_json(VEC_DIR / "inference_kernel_program.json", inference_kernel_program)
    write_json(VEC_DIR / "coherence_operator.json", coherence_operator)
    write_json(VEC_DIR / "workspace_state.json", workspace_state0)
    write_json(VEC_DIR / "efe_report.json", efe_report)
    write_json(VEC_DIR / "affordance_latent.json", affordance_latent)

    # Intervention log
    mechanism_after = deepcopy(mechanism)
    mechanism_after["params"] = {"b_fp": 0, "clamped": 1, "w_fp": 1000}
    mech_hash_after = mechanism_hash(mechanism_after)

    entry0 = {
        "format": "intervention_log_entry_v1",
        "schema_version": "1",
        "t": 0,
        "action_token": "do/set_x_1",
        "target_mechanism_id": "mech_y",
        "mech_hash_before": expected_mech_hash_before,
        "mech_hash_after": mech_hash_after,
        "do_payload_hash": expected_do_payload_hash,
        "prev_link_hash": ZERO_HASH,
        "link_hash": ZERO_HASH,
    }
    entry0["link_hash"] = intervention_log_link_hash(ZERO_HASH, entry0)

    # Transcript (minimal)
    transcript = [
        {
            "format": "ccai_x_mind_transcript_step_v1",
            "schema_version": "1",
            "t": 0,
            "observation_token": {"o_int": 1, "noise_fp": 10},
            "action_token": "probe",
        }
    ]

    # Write JSONL vectors
    write_jsonl(VEC_DIR / "intervention_log.jsonl", [entry0])
    write_jsonl(VEC_DIR / "workspace_state.jsonl", [workspace_state0, workspace_state1])
    write_jsonl(VEC_DIR / "efe_report.jsonl", [efe_report])
    write_jsonl(VEC_DIR / "transcript.jsonl", transcript)

    # Build candidate tar and update candidate_id
    candidate_tar_path = VEC_DIR / "ccai_x_mind_patch_candidate_mind_v1.tar"
    candidate_id = build_candidate_tar(candidate_tar_path, VEC_DIR)

    # Update efe_report candidate_id in both json and jsonl (canonical bytes)
    efe_report["candidate_id"] = candidate_id
    write_json(VEC_DIR / "efe_report.json", efe_report)
    write_jsonl(VEC_DIR / "efe_report.jsonl", [efe_report])

    # Write expected hashes
    write_text(VEC_DIR / "expected_candidate_id.txt", candidate_id)
    write_text(VEC_DIR / "expected_workspace_state_hash.txt", state_hash1)
    write_text(VEC_DIR / "expected_intervention_log_final_link_hash.txt", entry0["link_hash"])
    write_text(VEC_DIR / "expected_efe_report_digest.txt", sha256_hex(to_gcj1_bytes(efe_report)))
    write_text(VEC_DIR / "expected_do_payload_hash.txt", expected_do_payload_hash)
    write_text(VEC_DIR / "expected_mechanism_hash.txt", expected_mech_hash_before)


if __name__ == "__main__":
    make_vectors()
