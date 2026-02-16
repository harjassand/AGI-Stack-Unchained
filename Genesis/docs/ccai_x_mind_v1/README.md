CCAI-X Mind v1 defines a deterministic, schema-validated family of artifacts for describing a "mind patch candidate" with proof-carrying inference, coherence gluing, and affordance randomization attestations.

1. Objects (all schemas live under `Genesis/schema/ccai_x_mind_v1/`):
   1. `markov_blanket_spec_v1`: allowable observation/action channels, side-channel prohibitions, and attestation expectations.
   2. `do_map_v1`: action tokens mapped to do-operations with payloads and pre-surgery mechanism binding.
   3. `intervention_log_entry_v1`: JSONL entry proving an intervention occurred, with hash chaining.
   4. `causal_mechanism_registry_v1`: variables, domains, and executable mechanisms.
   5. `inference_kernel_isa_v1`: deterministic fixed-point arithmetic and update schedule.
   6. `inference_kernel_program_v1`: executable ISA program with explicit schedule and tie-break rules.
   7. `workspace_state_v1`: minimal belief-state container with hash chain.
      - `workspace_state_v1.beliefs.variable_marginals[].prob_fp` must be the same length as `support` (enforced by conformance/tools).
   8. `efe_report_v1`: policy evaluation decomposition and tie-break witness.
   9. `policy_prior_v1`: log-priors and complexity weights for certifiable complexity.
   10. `preference_capsule_v1`: bounded preferences and admissibility limits.
   11. `coherence_operator_v1`: deterministic belief gluing with residual bound.
   12. `affordance_latent_v1`: episode-level psi-swap/do-map randomization attestations.
   13. `ccai_x_mind_patch_candidate_manifest_v1`: binds all artifacts into a candidate identity.

2. Integer-only rule and fixed-point interpretation:
   - All numeric fields are integers. Fixed-point values use the `fixed_point.scale_int` declared in `inference_kernel_isa_v1` (e.g., `q32_32` uses a scale of `2^32`). No floats, decimals, or exponent notation are allowed anywhere.

3. Sorting requirements (deterministic ordering enforced by conformance):
   - `markov_blanket_spec_v1.side_channel_policy.env_var_allowlist`: lexicographic ascending.
   - `markov_blanket_spec_v1.side_channel_policy.fs_read_allowlist_prefixes`: lexicographic ascending.
   - `markov_blanket_spec_v1.side_channel_policy.fs_write_allowlist_prefixes`: lexicographic ascending.
   - `do_map_v1.entries`: sorted by `action_token`, then `target_mechanism_id` (lexicographic).
   - `causal_mechanism_registry_v1.variables`: sorted by `var_id`.
   - `causal_mechanism_registry_v1.variables[].domain.values` (when `kind=int_enum`): ascending integer order.
   - `causal_mechanism_registry_v1.mechanisms`: sorted by `mechanism_id`.
   - `causal_mechanism_registry_v1.mechanisms[].parents`: lexicographic ascending.
   - `causal_mechanism_registry_v1.mechanisms[].invariance_claims`: sorted by `claim_id`.
   - `causal_mechanism_registry_v1.mechanisms[].identifiability.identified_by_interventions`: lexicographic ascending.
   - `inference_kernel_isa_v1.primitives`: lexicographic ascending.
   - `inference_kernel_program_v1.schedule.stages`: sorted by `stage_id`.
   - `workspace_state_v1.beliefs.variable_marginals`: sorted by `var_id`.
   - `workspace_state_v1.beliefs.variable_marginals[].support`: ascending integer order (strictly increasing).
   - `workspace_state_v1.beliefs.parameter_estimates`: sorted by `param_id`.
   - `efe_report_v1.policies`: sorted by `policy_id`.
   - `policy_prior_v1.policy_logprior`: sorted by `policy_id`.
   - `preference_capsule_v1.metrics`: sorted by `metric_id`.
   - `preference_capsule_v1.admissibility.forbidden_action_tokens`: lexicographic ascending.
   - `coherence_operator_v1.merge_policy`: lexicographic ascending.
   - `ccai_x_mind_patch_candidate_manifest_v1.artifacts`: sorted by `path`.

4. JSONL conventions for logs:
   - One object per line.
   - Each line is GCJ-1 canonical JSON with no extra whitespace.
   - Lines are separated by LF (`\n`) and the file ends with a final LF.

5. Mind v1 candidate tar (minimal structure + determinism rules):
   - Tar filename: `ccai_x_mind_patch_candidate_mind_v1.tar`
   - Manifest `format`: `ccai_x_mind_patch_candidate_mind_v1`
   - Required entries at tar root (sorted):
     1. `manifest.json`
     2. `markov_blanket_spec.json`
     3. `do_map.json`
     4. `causal_mechanism_registry.json`
     5. `inference_kernel_isa.json`
     6. `inference_kernel_program.json`
     7. `policy_prior.json`
     8. `preference_capsule.json`
     9. `coherence_operator.json`
   - The `manifest.json` must be a `ccai_x_mind_patch_candidate_mind_v1` object whose `artifacts[]` list matches the eight artifact files (order sorted by `path`).
   - All JSON files MUST be GCJ-1 canonical byte-for-byte before being placed in the tar.
   - Deterministic tar creation: entries sorted by name, `mtime=0`, `uid=0`, `gid=0`, `uname=""`, `gname=""`, and a stable mode (e.g., `0644`). No extra entries are allowed.
