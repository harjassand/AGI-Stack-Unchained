<h1 align="center">
  📜 Genesis
</h1>

<p align="center">
  <strong>Specification Layer for AGI Stack (RE4)</strong>
</p>

<p align="center">
  <code>v18.0 + SH-1</code> •
  <a href="#overview">Overview</a> •
  <a href="#schemas">Schemas</a> •
  <a href="#protocols">Protocols</a> •
  <a href="#authority-system">Authority</a>
</p>

---

## Overview

**Genesis** is the specification layer (RE4) of the AGI Stack, providing normative schemas, protocols, and contracts for the entire system. It defines the "what" and "how" of system components without implementing them.

> Keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are interpreted as described in RFC 2119.

### Role in AGI Stack

```
┌────────────────────────────────────────────┐
│           AGI Stack Layers                  │
├────────────────────────────────────────────┤
│                                             │
│  RE1: meta-core (Trusted Computing Base)   │
│       ↓ enforces                            │
│  RE2: CDEL-v2 (Certified Execution)        │
│       ↓ validates                           │
│  RE3: Extension-1 (Proposers)              │
│       ↓ conforms to                         │
│  RE4: Genesis (Specifications) ← YOU ARE HERE │
│                                             │
└────────────────────────────────────────────┘
```

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| JSON schemas for all artifacts | Implementation code |
| Protocol specifications | CDEL integrations |
| Contract taxonomy | Genesis integrations |
| Authority pins | Verifier logic |
| Evaluation kernels | Campaign code |
| CCAP protocol specs | SH-1 optimizer code |

---

## Architecture

```
Genesis/
├── schema/                    # Normative JSON schemas (532 files)
│   ├── v18_0/                # Omega v18.0 schemas
│   ├── v17_0/                # SAS VAL schemas
│   ├── v16_0/                # SAS Metasearch schemas
│   └── ...                   # Earlier versions
│
├── docs/                      # Protocol specifications (28 files)
│   ├── evaluate_protocol.md
│   ├── canonicalization.md
│   ├── alpha_ledger.md
│   ├── privacy_ledger.md
│   ├── compute_ledger.md
│   ├── contract_taxonomy.md
│   ├── robustness_spec.md
│   └── tcb_boundary.md
│
├── api/                       # Wire protocols
│   ├── evaluate_v1.openapi.yaml
│   └── README.md
│
├── conformance/               # Black-box harness (13 files)
│   ├── run.py
│   ├── run.sh
│   └── tests/
│
├── examples/                  # Capsule examples (6 files)
│   ├── algorithm.capsule.json
│   ├── world_model.capsule.json
│   ├── causal_model.capsule.json
│   ├── policy.capsule.json
│   └── experiment.capsule.json
│
├── test_vectors/              # Canonicalization vectors (45 files)
├── tools/                     # Validation tools (28 files)
├── ledger_sim/                # Executable simulators (4 files)
├── extensions/                # Protocol extensions (22 files)
│
├── README.md                  # This file
├── SPEC_VERSION               # Current version
├── CHANGELOG.md               # Version history
├── CONTRIBUTING.md            # Contribution guide
└── CODEOWNERS                 # Auto-assign reviewers
```

---

## Schemas

### Latest Schemas (v18.0 + SH-1)

**Omega Daemon Schemas**:
- `omega_state_v1`: Daemon state snapshot
- `omega_observation_v1`: Metric collection report
- `omega_decision_v1`: Policy-based decision
- `omega_promotion_bundle_v1`: Standard promotion bundle
- `omega_promotion_bundle_ccap_v1`: CCAP promotion bundle

**CCAP Protocol Schemas**:
- `ccap_bundle_v1`: Certified Capsule Proposal bundle
- `ccap_receipt_v1`: Verification outcome receipt
- `ccap_refutation_cert_v1`: Rejection certificate
- `ccap_patch_allowlists_v1`: Patch allowlist rules

**SH-1 Genesis Engine Schemas**:
- `ge_config_v1`: Genesis Engine configuration
- `ge_pd_v1`: Proposal Descriptor (PD)
- `ge_xs_snapshot_v1`: eXperience Snapshot (XS)
- `ge_behavior_sig_v1`: Behavior signature

**Authority System Schemas**:
- `authority_pins_v1`: Cryptographic pins for system components
- `evaluation_kernel_v1`: Evaluation kernel specification
- `operator_pool_v1`: Operator pool configuration
- `dsbx_profile_v1`: Sandbox profile

### Schema Versioning

All schemas follow semantic versioning:
- `{name}_v{major}_{minor}`: e.g., `omega_state_v1_0`
- Breaking changes increment major version
- Backward-compatible changes increment minor version

### Example Schema: `ccap_bundle_v1`

```json
{
  "schema_version": "ccap_bundle_v1",
  "ccap_id": "sha256:...",
  "kind": "PATCH",
  "base_tree_id": "sha256:...",
  "ek_id": "ek_omega_v18_0_v1",
  "op_pool_id": "operator_pool_core_v1",
  "build_recipe_id": "omega_v18_0_default",
  "patch_blob_id": "sha256:...",
  "pd_id": "sha256:...",
  "beh_id": "sha256:..."
}
```

---

## Protocols

### CCAP (Certified Capsule Proposal) Protocol

**Purpose**: Universal verification for arbitrary code patches

**Specification**: See `docs/ccap_protocol.md` (if exists) or CCAP verifier implementation

**Three-Stage Pipeline**:
1. **REALIZE**: Apply patch and validate schema
2. **SCORE**: Run evaluation kernel benchmarks
3. **FINAL_AUDIT**: Verify promotion criteria

**Key Components**:
- **CCAP Bundle**: Proposal artifact
- **Evaluation Kernel**: Benchmark suite
- **Operator Pool**: Sandbox configuration
- **Patch Allowlist**: Permitted modification paths
- **CCAP Receipt**: Verification outcome

**Workflow**:
```
Proposer → CCAP Bundle → CCAP Verifier → CCAP Receipt → Promotion
```

### Canonical JSON (GCJ-1)

**Purpose**: Deterministic JSON serialization for content-addressing

**Rules**:
1. UTF-8 encoding
2. Keys sorted alphabetically
3. No trailing whitespace
4. LF line endings (`\n`)
5. Minimal JSON formatting (2-space indent)

**Implementation**: `CDEL-v2/cdel/v1_7r/canon.py`

### Evaluate Protocol

**Purpose**: Standard interface for running evaluation kernels

**Specification**: `docs/evaluate_protocol.md`

**Stages**:
- `REALIZE`: Apply changes and build
- `SCORE`: Run benchmarks
- `FINAL_AUDIT`: Verify promotion gates

---

## Authority System

The **Authority System** provides a cryptographic root of trust for system components.

**Location**: `../authority/` (sibling directory to Genesis)

### Authority Pins

**File**: `authority/authority_pins_v1.json`

**Purpose**: Immutable references to trusted components

**Structure**:
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
  }
}
```

### Evaluation Kernels

**Directory**: `authority/evaluation_kernels/`

**Purpose**: Define benchmark suites for CCAP verification

**Example**: `ek_omega_v18_0_v1.json`

**Structure**:
```json
{
  "schema_version": "evaluation_kernel_v1",
  "ek_id": "ek_omega_v18_0_v1",
  "scoring_impl": {
    "kind": "OMEGA_BENCHMARK_SUITE",
    "code_ref": {
      "path": "CDEL-v2/cdel/v18_0/omega_benchmark_suite_v1.py"
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

### Operator Pools

**Directory**: `authority/operator_pools/`

**Purpose**: Define sandbox configurations for code execution

**Example**: `operator_pool_core_v1.json`

**Structure**:
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

### CCAP Patch Allowlists

**File**: `authority/ccap_patch_allowlists_v1.json`

**Purpose**: Define permitted modification paths for CCAP patches

**Structure**:
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

---

## Conformance

### Conformance Harness

**Location**: `conformance/`

**Purpose**: Black-box testing of CDEL implementations

**Usage**:
```bash
cd conformance
./run.sh --implementation /path/to/cdel
```

### Test Vectors

**Location**: `test_vectors/`

**Purpose**: Canonical JSON test cases

**Usage**:
```bash
python3 tools/validate_canon.py test_vectors/
```

---

## For Developers

### Adding a New Schema

1. Create schema file: `schema/v{X}_{Y}/{name}_v{X}_{Y}.json`
2. Add JSON Schema validation rules
3. Update `CHANGELOG.md`
4. Add test vectors to `test_vectors/`
5. Update conformance tests

### Validating Schemas

```bash
# Validate all schemas
python3 tools/validate_schemas.py

# Validate specific schema
python3 tools/validate_schemas.py schema/v18_0/omega_state_v1.json
```

### Generating Documentation

```bash
# Generate schema docs
python3 tools/generate_schema_docs.py --out docs/schemas/

# Generate protocol docs
python3 tools/generate_protocol_docs.py --out docs/protocols/
```

---

## For Agents

### Quick Reference

| What you need | Where to look |
|---------------|---------------|
| **Latest schemas** | `schema/v18_0/` |
| **CCAP specs** | `docs/ccap_protocol.md` or CCAP verifier |
| **Authority pins** | `../authority/authority_pins_v1.json` |
| **Evaluation kernels** | `../authority/evaluation_kernels/` |
| **Patch allowlists** | `../authority/ccap_patch_allowlists_v1.json` |
| **Canonical JSON** | `docs/canonicalization.md` |
| **Test vectors** | `test_vectors/` |

### Finding Schemas

```bash
# List all v18.0 schemas
find schema/v18_0 -name "*.json" | sort

# Find CCAP-related schemas
grep -r "ccap" schema/ --include="*.json"

# Find SH-1 schemas
grep -r "ge_" schema/ --include="*.json"
```

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| 1.0.1 | 2026-02-11 | Added CCAP protocol, SH-1 schemas, Authority system |
| 1.0.0 | 2026-02-01 | Initial Genesis specification |

See `CHANGELOG.md` for detailed version history.

---

## Contributing

See `CONTRIBUTING.md` for contribution guidelines.

---

## License

See repository root LICENSE file.

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em><br>
  <em>Specification layer for verifiable autonomy</em>
</p>
