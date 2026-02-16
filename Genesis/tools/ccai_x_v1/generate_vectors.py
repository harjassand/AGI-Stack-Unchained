#!/usr/bin/env python3
import io
import sys
import tarfile
from copy import deepcopy
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from ccai_x_v1.canonical_json import assert_no_floats, to_gcj1_bytes  # noqa: E402
from ccai_x_v1.hashes import (  # noqa: E402
    ZERO_HASH,
    candidate_id_from_components,
    candidate_id_from_tar,
    do_payload_hash,
    intervention_log_link_hash,
    mechanism_hash,
    sha256_hex,
    workspace_state_hash,
)

ROOT = TOOLS_DIR.parent
VEC_DIR = ROOT / "test_vectors" / "ccai_x_v1"


def write_json(path: Path, obj) -> None:
    assert_no_floats(obj)
    path.write_bytes(to_gcj1_bytes(obj))


def write_text(path: Path, text: str) -> None:
    path.write_text(text + "\n", encoding="utf-8")


def make_vectors() -> None:
    VEC_DIR.mkdir(parents=True, exist_ok=True)

    mechanism = {
        "mechanism_id": "mech_y",
        "output_var": "y",
        "parents": ["x"],
        "kind": "linear",
        "params": {"b_fp": 0, "w_fp": 4294967296},
        "invariance_claims": [
            {
                "claim_id": "inv/mech_y",
                "scope": "across_interventions",
                "evidence_hint": "synthetic"
            }
        ],
        "identifiability": {"identified_by_interventions": ["do/clamp_x_1"]},
    }

    mechanism_registry = {
        "format": "causal_mechanism_registry_v1",
        "schema_version": "1",
        "registry_id": "toy_registry_v1",
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
        "do_map_id": "do_map_v1",
        "entries": [
            {
                "action_token": "do/clamp_x_1",
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
        "blanket_id": "blanket_v1",
        "channels": {
            "observation": {
                "mode": "read_only",
                "token_schema_id": "ccai_x_observation_token_v1",
            },
            "action": {"mode": "write_only", "token_schema_id": "ccai_x_action_token_v1"},
        },
        "side_channel_policy": {
            "network_allowed": False,
            "clock_allowed": False,
            "env_var_allowlist": ["env_lc_all", "env_path"],
            "fs_read_allowlist_prefixes": [
                "/tmp/ccai_x/ro",
                "/var/lib/ccai_x/ro",
            ],
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
        "isa_id": "ccai_x_isa_v1",
        "fixed_point": {
            "format_id": "q32_32",
            "scale_int": 4294967296,
            "signed": True,
            "bits": 64,
            "rounding": "round_half_even",
            "saturation": "saturate",
        },
        "primitives": ["entropy", "normalize", "resample_deterministic"],
        "schedule": {
            "max_iters": 128,
            "update_order": ["normalize", "entropy"],
            "tie_break_rule": {
                "primary": "min_total_G",
                "secondary": "min_risk",
                "tertiary": "lexicographic_action_token",
            },
        },
    }

    policy_prior = {
        "format": "policy_prior_v1",
        "schema_version": "1",
        "prior_id": "prior_v1",
        "default_logprior_fp": -100,
        "policy_logprior": [
            {"policy_id": "pi_a", "logprior_fp": -10},
            {"policy_id": "pi_b", "logprior_fp": -20},
        ],
        "complexity_weights": {"length_weight_fp": 1, "compute_weight_fp": 2},
    }

    preference_capsule = {
        "format": "preference_capsule_v1",
        "schema_version": "1",
        "preference_id": "pref_v1",
        "energy_bounds": {"min_energy_fp": 0, "max_energy_fp": 100000},
        "metrics": [
            {"metric_id": "reward", "direction": "max", "weight_fp": 2},
            {"metric_id": "risk", "direction": "min", "weight_fp": 1},
        ],
        "admissibility": {
            "forbidden_action_tokens": [],
            "max_horizon": 5,
            "max_branching": 2,
            "max_interventions_per_episode": 1,
        },
    }

    beliefs = {
        "variable_marginals": [
            {"var_id": "x", "support": [0, 1], "prob_fp": [2147483648, 2147483648]},
            {"var_id": "y", "support": [0, 1], "prob_fp": [4294967296, 0]},
        ],
        "parameter_estimates": [
            {"param_id": "mech_y.w_fp", "value_fp": 4294967296}
        ],
    }
    state_hash = workspace_state_hash(ZERO_HASH, beliefs)
    workspace_state = {
        "format": "workspace_state_v1",
        "schema_version": "1",
        "t": 0,
        "prev_state_hash": ZERO_HASH,
        "beliefs": beliefs,
        "state_hash": state_hash,
    }

    # Write JSON vectors
    write_json(VEC_DIR / "markov_blanket_spec.json", markov_blanket_spec)
    write_json(VEC_DIR / "do_map.json", do_map)
    write_json(VEC_DIR / "mechanism_registry.json", mechanism_registry)
    write_json(VEC_DIR / "policy_prior.json", policy_prior)
    write_json(VEC_DIR / "preference_capsule.json", preference_capsule)
    write_json(VEC_DIR / "inference_kernel_isa.json", inference_kernel_isa)
    write_json(VEC_DIR / "workspace_state.json", workspace_state)

    # Intervention log
    mechanism_after = deepcopy(mechanism)
    mechanism_after["params"] = {"b_fp": 0, "clamped": 1, "w_fp": 4294967296}
    mech_hash_after = mechanism_hash(mechanism_after)

    entry0 = {
        "format": "intervention_log_entry_v1",
        "schema_version": "1",
        "t": 0,
        "action_token": "do/clamp_x_1",
        "target_mechanism_id": "mech_y",
        "mech_hash_before": expected_mech_hash_before,
        "mech_hash_after": mech_hash_after,
        "do_payload_hash": expected_do_payload_hash,
        "prev_link_hash": ZERO_HASH,
        "link_hash": ZERO_HASH,
    }
    link_hash0 = intervention_log_link_hash(ZERO_HASH, entry0)
    entry0["link_hash"] = link_hash0

    entry1 = {
        "format": "intervention_log_entry_v1",
        "schema_version": "1",
        "t": 1,
        "action_token": "do/clamp_x_1",
        "target_mechanism_id": "mech_y",
        "mech_hash_before": mech_hash_after,
        "mech_hash_after": mech_hash_after,
        "do_payload_hash": expected_do_payload_hash,
        "prev_link_hash": link_hash0,
        "link_hash": ZERO_HASH,
    }
    link_hash1 = intervention_log_link_hash(link_hash0, entry1)
    entry1["link_hash"] = link_hash1

    lines = [to_gcj1_bytes(entry0), to_gcj1_bytes(entry1)]
    (VEC_DIR / "intervention_log.jsonl").write_bytes(b"\n".join(lines) + b"\n")

    # Create manifest and tar
    artifact_paths = [
        "do_map.json",
        "inference_kernel_isa.json",
        "markov_blanket_spec.json",
        "mechanism_registry.json",
        "policy_prior.json",
        "preference_capsule.json",
    ]

    artifacts = []
    for path in sorted(artifact_paths):
        data = (VEC_DIR / path).read_bytes()
        artifacts.append(
            {
                "path": path,
                "sha256": sha256_hex(data),
                "bytes_len": len(data),
            }
        )

    manifest = {
        "format": "ccai_x_mind_patch_candidate_manifest_v1",
        "schema_version": "1",
        "task_id": "ccai_x_v1",
        "candidate_id": ZERO_HASH,
        "artifacts": artifacts,
    }
    artifact_blobs = {
        "do_map.json": (VEC_DIR / "do_map.json").read_bytes(),
        "inference_kernel_isa.json": (VEC_DIR / "inference_kernel_isa.json").read_bytes(),
        "markov_blanket_spec.json": (VEC_DIR / "markov_blanket_spec.json").read_bytes(),
        "mechanism_registry.json": (VEC_DIR / "mechanism_registry.json").read_bytes(),
        "policy_prior.json": (VEC_DIR / "policy_prior.json").read_bytes(),
        "preference_capsule.json": (VEC_DIR / "preference_capsule.json").read_bytes(),
    }
    candidate_id = candidate_id_from_components(manifest, artifact_blobs)
    manifest["candidate_id"] = candidate_id
    manifest_bytes = to_gcj1_bytes(manifest)

    tar_path = VEC_DIR / "ccai_x_mind_patch_candidate_v1.tar"
    tar_entries = {
        "manifest.json": manifest_bytes,
    }
    for path in artifact_paths:
        tar_entries[path] = artifact_blobs[path]

    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(tar_entries.keys()):
            data = tar_entries[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))

    candidate_id = candidate_id_from_tar(str(tar_path))

    efe_report = {
        "format": "efe_report_v1",
        "schema_version": "1",
        "t": 0,
        "candidate_id": candidate_id,
        "isa_id": "ccai_x_isa_v1",
        "policy_set_id": "policy_set_v1",
        "policies": [
            {
                "policy_id": "pi_a",
                "actions": ["do/clamp_x_1"],
                "risk_fp": 10,
                "ambiguity_fp": 0,
                "epistemic_fp": 0,
                "complexity_fp": 5,
                "total_G_fp": 15,
            },
            {
                "policy_id": "pi_b",
                "actions": ["do/hold"],
                "risk_fp": 12,
                "ambiguity_fp": 0,
                "epistemic_fp": 0,
                "complexity_fp": 4,
                "total_G_fp": 16,
            },
        ],
        "chosen_policy_id": "pi_a",
        "chosen_action_token": "do/clamp_x_1",
        "tie_break_witness": {
            "rule": "min_total_G_then_min_risk_then_lex",
            "compared_against_policy_id": "pi_b",
        },
    }
    write_json(VEC_DIR / "efe_report.json", efe_report)

    # Expected hashes
    write_text(VEC_DIR / "expected_do_payload_hash.txt", expected_do_payload_hash)
    write_text(VEC_DIR / "expected_mechanism_hash.txt", expected_mech_hash_before)
    write_text(VEC_DIR / "expected_intervention_log_final_link_hash.txt", link_hash1)
    write_text(VEC_DIR / "expected_workspace_state_hash.txt", state_hash)
    write_text(VEC_DIR / "expected_candidate_id.txt", candidate_id)


if __name__ == "__main__":
    make_vectors()
