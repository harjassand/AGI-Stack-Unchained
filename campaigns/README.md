# Campaigns

This directory is the RE2 campaign configuration corpus for AGI Stack.

Last updated: **2026-02-14**.

## Purpose

Campaigns are versioned, deterministic configuration bundles that drive proposal,
validation, evaluation, and promotion behavior in verifiers and orchestrators.

Most campaigns are consumed by:

- `daemon/` (Omega-managed dispatch, promotion, and subruns)
- `orchestrator/` (campaign entrypoints for directly-invoked runs)
- `CDEL-v2/cdel/` verifiers (canonical deterministic replay and attestations)

A campaign directory is usually a pure data package. It should not contain executable
code unless the campaign architecture specifically requires it.

## Why this folder matters

1. **Determinism**: packs point to exact artifact trees and are expected to be
   canonicalized and hashable.
2. **Replayability**: the same pack path and same referenced inputs produce the
   same campaign outcome.
3. **Policy enforcement**: trust and safety policies (allowlists, budgets,
   objectives, policies, registries) are centrally controlled through this layer.
4. **Reproducibility**: every external pointer is repository-relative and explicit.

## Core conventions (must be preserved)

- Campaign references are repo-relative POSIX paths (for example
  `campaigns/rsi_sas_math_v11_1/rsi_sas_math_pack_v1.json`).
- JSON remains canonical for verification/hash compatibility (including explicit,
  deterministic ordering of serializations).
- Campaign and evidence lists are ordered and include explicit sort keys when used
  as sets.
- Paths/refs in campaign manifests should be immutable pointers, not implicit lookups.
- Do not introduce float arithmetic assumptions inside campaign manifests; numeric
  policy fields should follow project conventions for determinism.

## Naming pattern

Campaign directory names follow this pattern:

`rsi_<theme>_<variant>_v<semver-like>_?`

Examples:

- `rsi_omega_daemon_v19_0`
- `rsi_sas_math_v11_3`
- `rsi_real_thermo_v5_0`

Recommended reading for a new campaign:

- use `rsi_{domain}_v{major}_{minor?}`.
- include at least one `_pack_*.json` entrypoint.
- keep referenced assets colocated under the same directory.

## What to find in a campaign directory

A typical campaign directory contains:

- one or more primary pack files (`*_pack_*.json`)
- optional environment or safety fixtures (`*_fixture_*.json`)
- policy, budget, registry, objective, and allowlist configs
- toolchain manifests and policy references
- domain artifacts (families, datasets, macros, inputs, etc.)

Names vary by family. The important invariant is that the pack file references all
supporting artifacts through explicit relative paths.

## Quick commands

```bash
# List every campaign directory
find campaigns -mindepth 1 -maxdepth 1 -type d | sort

# List every current campaign pack (top-level)
find campaigns -mindepth 2 -maxdepth 2 -name "*_pack_*.json" | sort

# Locate campaigns without explicit pack file at top level
find campaigns -mindepth 1 -maxdepth 1 -type d | while read d; do
  if ! find "$d" -maxdepth 2 -name "*_pack_*.json" | grep -q .; then
    echo "${d#campaigns/}"
  fi
done

# Grep pack and policy references (canonical path style)
rg -n '"(.*)_rel"|"(.*)_path"' campaigns -g '*_pack_*.json'
```

## Campaign families in this repo

As of 2026-02-14 the directory contains 74 campaign folders and 99 top-level pack files.

### Omega family

- `rsi_omega_apply_shadow_proposal_v1`
- `rsi_omega_daemon_v18_0`
- `rsi_omega_daemon_v18_0_prod`
- `rsi_omega_daemon_v19_0`
- `rsi_omega_daemon_v19_0_llm_enabled`
- `rsi_omega_daemon_v19_0_unified`
- `rsi_omega_self_optimize_core_v1`
- `rsi_omega_skill_alignment_v1`
- `rsi_omega_skill_boundless_math_v1`
- `rsi_omega_skill_boundless_science_v1`
- `rsi_omega_skill_eff_flywheel_v1`
- `rsi_omega_skill_model_genesis_v1`
- `rsi_omega_skill_ontology_v1`
- `rsi_omega_skill_persistence_v1`
- `rsi_omega_skill_swarm_v1`
- `rsi_omega_skill_thermo_v1`
- `rsi_omega_skill_transfer_v1`

### SAS family

- `rsi_sas_code_v12_0`
- `rsi_sas_kernel_v15_0`
- `rsi_sas_kernel_v15_1`
- `rsi_sas_math_v11_0`
- `rsi_sas_math_v11_1`
- `rsi_sas_math_v11_2`
- `rsi_sas_math_v11_3`
- `rsi_sas_metasearch_v16_0`
- `rsi_sas_metasearch_v16_1`
- `rsi_sas_science_v13_0`
- `rsi_sas_system_demon_v14_0`
- `rsi_sas_system_v14_0`
- `rsi_sas_val_v17_0`

### Polymath family

- `rsi_polymath_bootstrap_domain_v1`
- `rsi_polymath_conquer_domain_v1`
- `rsi_polymath_scout_v1`

### Real family

- `rsi_real_csi_v2_2`
- `rsi_real_demon_v3`
- `rsi_real_demon_v4`
- `rsi_real_demon_v5_autonomy`
- `rsi_real_demon_v6_efficiency`
- `rsi_real_demon_v8_csi`
- `rsi_real_demon_v9_hardening`
- `rsi_real_flywheel_v2_0`
- `rsi_real_hardening_v2_3`
- `rsi_real_ignite_v1`
- `rsi_real_integrity_v1`
- `rsi_real_omega_v4_0`
- `rsi_real_onto_v2`
- `rsi_real_portfolio_v1`
- `rsi_real_recursive_ontology_v2_1`
- `rsi_real_recursive_ontology_v2_1_source`
- `rsi_real_recursive_ontology_v2_1_target`
- `rsi_real_science_v1`
- `rsi_real_swarm_v3_0`
- `rsi_real_swarm_v3_1`
- `rsi_real_swarm_v3_2`
- `rsi_real_swarm_v3_3`
- `rsi_real_thermo_v5_0`
- `rsi_real_transfer_v1`

### Alignment / boundless / genesis / daemon / misc

- `rsi_alignment_v7_0`
- `rsi_alignment_v8_0`
- `rsi_alignment_v9_0`
- `rsi_arch_synthesis_v11_0`
- `rsi_boundless_math_v8_0`
- `rsi_boundless_science_v9_0`
- `rsi_daemon_v6_0`
- `rsi_daemon_v7_0`
- `rsi_daemon_v8_0_math`
- `rsi_eudrs_u_eval_cac_v1`
- `rsi_eudrs_u_index_rebuild_v1`
- `rsi_eudrs_u_ontology_update_v1`
- `rsi_eudrs_u_train_v1`
- `rsi_ge_symbiotic_optimizer_sh1_v0_1`
- `rsi_model_genesis_v10_0`
- `rsi_agi_orchestrator_llm_v1`
- `grand_challenges`

## Entry points and execution

- **Omega daemon** (RE2 orchestration):

  ```bash
  python3 -m daemon.rsi_omega_daemon_v18_0     --config campaigns/rsi_omega_daemon_v18_0/omega_pack_v1.json     --out-dir runs/my_omega_run
  ```

  See `daemon/README.md` for current CLI flags and run state layout.

- **Campaign CLI entrypoints** exist in `orchestrator/` for several families.
  Current examples:

  - `orchestrator/rsi_model_genesis_v10_0.py`
  - `orchestrator/rsi_eudrs_u_train_v1.py`
  - `orchestrator/rsi_sas_code_v12_0.py`
  - `orchestrator/rsi_sas_science_v13_0.py`
  - `orchestrator/rsi_sas_system_v14_0.py`
  - `orchestrator/rsi_sas_kernel_v15_0.py`
  - `orchestrator/rsi_sas_metasearch_v16_1.py`
  - `orchestrator/rsi_sas_val_v17_0.py`

- Legacy/legacy-style campaign harnesses live in versioned RE2 folders (`CDEL-v2/cdel/v1_5r`, `v1_6r`, `v1_7r`, `v1_8r`, `v1_9r`, `v2_0`, `v2_1`) and are used via their
  `run_rsi_campaign.py` entry scripts.

## Verifier and proof chain checkpoints

- Every active campaign family has corresponding verifier modules in `CDEL-v2/cdel/v*`.
- Campaign promotion evidence should be emitted as campaign-specific bundles and
  validated by verifier replay.
- For EUDRS-U families, promotion summaries must follow
  `eudrs_u_promotion_summary_v1` and provide digest references for all required
  downstream evidence artifacts.

## Helpful checks for campaign authors

- Validate pack references before running:
  - confirm all `_rel` / `_path` values are resolvable repo-relative files
  - confirm all manifest hashes in referenced files match their payloads
- Confirm schema versions:
  - pack `schema_version` and each auxiliary manifest schema/version fields
- Keep binary policy files deterministic and replayable across machines.

```bash
# Basic preflight sanity check
rg -n '"schema_version"|"schema"|"_rel"|"_path"'   campaigns/<campaign_dir> -g '*.json' | head -n 200
```

```bash
# Verify campaign has at least one pack
[ -n "$(find campaigns/<campaign_dir> -maxdepth 2 -name '*_pack_*.json')" ] ||   echo "No top-level pack found"
```

## Authoring notes

When adding a new campaign to this folder:

1. Create a new `rsi_<name>_vX_Y` directory.
2. Add one authoritative pack file (`*_pack_v*.json`).
3. Add all referenced artifacts in the same directory tree.
4. Keep all JSON canonical and deterministic.
5. Update orchestrator/daemon and capability references if the campaign must be
   dispatchable by Omega.
6. Add a `README.md` for unusual layout or execution constraints when needed.

This README is intended as an index and operating reference for campaign pack governance.
