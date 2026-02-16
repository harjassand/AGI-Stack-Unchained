<h1 align="center">
  🔐 Authority
</h1>

<p align="center">
  <strong>Cryptographic Root of Trust for AGI Stack</strong>
</p>

<p align="center">
  <code>v18.0 + SH-1</code> •
  <a href="#overview">Overview</a> •
  <a href="#authority-pins">Pins</a> •
  <a href="#evaluation-kernels">Evaluation Kernels</a> •
  <a href="#patch-allowlists">Allowlists</a>
</p>

---

## Overview

The **Authority** directory contains the cryptographic root of trust for the AGI Stack. It defines:

1. **Authority Pins**: Immutable references to trusted components
2. **Evaluation Kernels**: Benchmark suites for CCAP verification
3. **Operator Pools**: Sandbox configurations for code execution
4. **Patch Allowlists**: Permitted modification paths for CCAP patches
5. **DSBX Profiles**: Deterministic sandbox profiles
6. **Build Recipes**: Reproducible build configurations

> ⚠️ **Security Note**: This directory is **forbidden** from modification by all proposers (Extension-1, Genesis Engine SH-1). Only manual, audited changes are permitted.

---

## Architecture

```
authority/
├── authority_pins_v1.json         # Root of trust (immutable)
│
├── evaluation_kernels/            # Benchmark suites (2 files)
│   ├── ek_omega_v18_0_v1.json    # Omega v18.0 evaluation kernel
│   └── ek_sas_val_v17_0_v1.json  # SAS VAL v17.0 evaluation kernel
│
├── operator_pools/                # Sandbox configurations (3 files)
│   ├── operator_pool_core_v1.json
│   ├── operator_pool_sas_v1.json
│   └── operator_pool_omega_v1.json
│
├── dsbx_profiles/                 # Sandbox profiles (1 file)
│   └── dsbx_omega_v18_0_default.json
│
├── build_recipes/                 # Build configurations (1 file)
│   └── omega_v18_0_default.json
│
├── ccap_patch_allowlists_v1.json  # Patch allowlist rules
│
├── boundary_event_sets/           # Boundary event definitions (1 file)
│   └── boundary_events_v1.json
│
└── gir_integrators/               # GIR integrator configs (1 file)
    └── gir_integrator_omega_v1.json
```

---

## Authority Pins

**File**: `authority_pins_v1.json`

**Purpose**: Cryptographic pins for all trusted components

**Schema**: `authority_pins_v1`

### Structure

```json
{
  "schema_version": "authority_pins_v1",
  "active_ek_id": "sha256:...",
  "active_op_pool_ids": ["sha256:..."],
  "active_dsbx_profile_ids": ["sha256:..."],
  "ccap_patch_allowlists_id": "sha256:...",
  "re1_constitution_state_id": "sha256:...",
  "re2_verifier_state_id": "sha256:...",
  "canon_version_ids": {
    "ccap_can_v": "sha256:...",
    "ir_can_v": "sha256:...",
    "obs_can_v": "sha256:...",
    "op_can_v": "sha256:..."
  },
  "env_contract_id": "sha256:...",
  "toolchain_root_id": "sha256:..."
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `active_ek_id` | Hash of active evaluation kernel |
| `active_op_pool_ids` | Hashes of active operator pools |
| `active_dsbx_profile_ids` | Hashes of active sandbox profiles |
| `ccap_patch_allowlists_id` | Hash of CCAP patch allowlists |
| `re1_constitution_state_id` | Hash of meta-core constitution state |
| `re2_verifier_state_id` | Hash of CDEL-v2 verifier state |
| `canon_version_ids` | Hashes of canonical version specifications |
| `env_contract_id` | Hash of environment contract |
| `toolchain_root_id` | Hash of toolchain root |

### Verification Process

```python
from cdel.v1_7r.canon import load_canon_dict, canon_bytes, sha256_prefixed

# 1. Load authority pins
pins = load_canon_dict("authority/authority_pins_v1.json")

# 2. Load evaluation kernel
ek_path = "authority/evaluation_kernels/ek_omega_v18_0_v1.json"
ek = load_canon_dict(ek_path)

# 3. Verify hash
expected_hash = pins["active_ek_id"]
actual_hash = sha256_prefixed(canon_bytes(ek))

if actual_hash != expected_hash:
    raise RuntimeError("AUTH_HASH_MISMATCH")
```

---

## Evaluation Kernels

**Directory**: `evaluation_kernels/`

**Purpose**: Define benchmark suites for CCAP verification

### Schema: `evaluation_kernel_v1`

```json
{
  "schema_version": "evaluation_kernel_v1",
  "ek_id": "ek_omega_v18_0_v1",
  "scoring_impl": {
    "kind": "OMEGA_BENCHMARK_SUITE",
    "code_ref": {
      "path": "CDEL-v2/cdel/v18_0/omega_benchmark_suite_v1.py",
      "entry_point": "run_benchmark_suite"
    }
  },
  "stages": [
    {
      "stage_id": "REALIZE",
      "timeout_s": 30,
      "gates": []
    },
    {
      "stage_id": "SCORE",
      "timeout_s": 3600,
      "gates": []
    },
    {
      "stage_id": "FINAL_AUDIT",
      "timeout_s": 30,
      "gates": [
        {
          "kind": "MIN_METRIC_Q32",
          "metric_id": "accuracy_q32",
          "threshold_q32": 3865470566
        }
      ]
    }
  ]
}
```

### Key Components

| Component | Description |
|-----------|-------------|
| `ek_id` | Unique identifier for this evaluation kernel |
| `scoring_impl` | Implementation reference (code path + entry point) |
| `stages` | Three-stage pipeline (REALIZE, SCORE, FINAL_AUDIT) |
| `gates` | Promotion criteria (e.g., minimum accuracy) |

### Available Evaluation Kernels

| EK ID | Purpose | Benchmark Suite |
|-------|---------|-----------------|
| `ek_omega_v18_0_v1` | Omega daemon verification | `omega_benchmark_suite_v1.py` |
| `ek_sas_val_v17_0_v1` | SAS VAL verification | `sas_val_benchmark_suite_v1.py` |

---

## Operator Pools

**Directory**: `operator_pools/`

**Purpose**: Define sandbox configurations for code execution

### Schema: `operator_pool_v1`

```json
{
  "schema_version": "operator_pool_v1",
  "op_pool_id": "operator_pool_core_v1",
  "operators": [
    {
      "op_id": "omega_v18_0_default",
      "dsbx_profile_id": "dsbx_omega_v18_0_default",
      "build_recipe_id": "omega_v18_0_default"
    }
  ]
}
```

### Key Components

| Component | Description |
|-----------|-------------|
| `op_pool_id` | Unique identifier for this operator pool |
| `operators` | List of operator configurations |
| `op_id` | Operator identifier |
| `dsbx_profile_id` | Sandbox profile to use |
| `build_recipe_id` | Build recipe to use |

### Available Operator Pools

| Pool ID | Purpose |
|---------|---------|
| `operator_pool_core_v1` | Core Omega operations |
| `operator_pool_sas_v1` | SAS campaign operations |
| `operator_pool_omega_v1` | Omega-specific operations |

---

## CCAP Patch Allowlists

**File**: `ccap_patch_allowlists_v1.json`

**Purpose**: Define permitted modification paths for CCAP patches

### Schema: `ccap_patch_allowlists_v1`

```json
{
  "schema_version": "ccap_patch_allowlists_v1",
  "allowlists": {
    "OMEGA_CORE": {
      "allowed_prefixes": [
        "orchestrator/",
        "tools/",
        "campaigns/",
        "polymath/registry/"
      ],
      "forbidden_prefixes": [
        "authority/",
        "meta-core/",
        "CDEL-v2/",
        "Genesis/"
      ]
    }
  }
}
```

### Enforcement Rules

**Allowed Prefixes**: Files matching these prefixes CAN be modified
**Forbidden Prefixes**: Files matching these prefixes CANNOT be modified (overrides allowed)

**Example**:
- `orchestrator/omega_v18_0/decider_v1.py` → ✅ ALLOWED
- `tools/genesis_engine/ge_config_v1.json` → ✅ ALLOWED
- `authority/authority_pins_v1.json` → ❌ FORBIDDEN
- `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` → ❌ FORBIDDEN

### Verification Logic

```python
def _path_forbidden_by_allowlists(path_rel: str, allowlists: dict) -> bool:
    # Check if path matches any allowed prefix
    allowed = False
    for prefix in allowlists.get("allowed_prefixes", []):
        if path_rel.startswith(prefix):
            allowed = True
            break
    
    # Check if path matches any forbidden prefix (overrides allowed)
    for prefix in allowlists.get("forbidden_prefixes", []):
        if path_rel.startswith(prefix):
            return True  # Forbidden
    
    return not allowed
```

---

## DSBX Profiles

**Directory**: `dsbx_profiles/`

**Purpose**: Define deterministic sandbox profiles

### Schema: `dsbx_profile_v1`

```json
{
  "schema_version": "dsbx_profile_v1",
  "dsbx_profile_id": "dsbx_omega_v18_0_default",
  "timeout_s": 3600,
  "max_memory_mb": 8192,
  "max_cpu_cores": 4,
  "network_access": false,
  "filesystem_access": {
    "read_only": ["/usr", "/lib", "/bin"],
    "read_write": ["./workspace"],
    "forbidden": ["/etc", "/var", "/root"]
  }
}
```

---

## Build Recipes

**Directory**: `build_recipes/`

**Purpose**: Define reproducible build configurations

### Schema: `build_recipe_v1`

```json
{
  "schema_version": "build_recipe_v1",
  "build_recipe_id": "omega_v18_0_default",
  "steps": [
    {
      "step_id": "install_deps",
      "command": ["pip", "install", "-e", "."]
    },
    {
      "step_id": "run_tests",
      "command": ["pytest", "-v"]
    }
  ]
}
```

---

## Security Model

### Immutability

The `authority/` directory is **immutable** from the perspective of proposers:
- Extension-1 cannot propose changes
- Genesis Engine SH-1 cannot propose changes
- CCAP patches targeting `authority/` are rejected

### Manual Updates Only

Changes to `authority/` require:
1. Manual file editing
2. Security audit
3. Constitutional review
4. Unanimous approval from maintainers
5. Hash update in `authority_pins_v1.json`

### Verification Chain

```
Authority Pins (Root of Trust)
    ↓
Evaluation Kernels
    ↓
Operator Pools
    ↓
DSBX Profiles
    ↓
Build Recipes
    ↓
Patch Allowlists
```

All components are cryptographically linked via SHA-256 hashes.

---

## For Agents

### Quick Reference

| What you need | Where to look |
|---------------|---------------|
| **Authority pins** | `authority_pins_v1.json` |
| **Evaluation kernels** | `evaluation_kernels/` |
| **Operator pools** | `operator_pools/` |
| **Patch allowlists** | `ccap_patch_allowlists_v1.json` |
| **DSBX profiles** | `dsbx_profiles/` |
| **Build recipes** | `build_recipes/` |

### Common Patterns

```bash
# Verify authority pins
python3 -c "
from cdel.v1_7r.canon import load_canon_dict
pins = load_canon_dict('authority/authority_pins_v1.json')
print(f'Active EK: {pins[\"active_ek_id\"]}')
"

# List evaluation kernels
ls -l authority/evaluation_kernels/

# View patch allowlists
cat authority/ccap_patch_allowlists_v1.json | jq .
```

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| v1.0 | 2026-02-11 | Initial authority system with CCAP support |

---

## License

See repository root LICENSE file.

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em><br>
  <em>Cryptographic root of trust for verifiable autonomy</em>
</p>
