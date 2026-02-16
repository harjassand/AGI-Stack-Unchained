<h1 align="center">
  🔒 CDEL-v2
</h1>

<p align="center">
  <strong>Certified Definitional Extension Ledger - The Verification Layer</strong>
</p>

<p align="center">
  <code>RE2 Layer</code> •
  <a href="#overview">Overview</a> •
  <a href="#navigation">Navigation</a> •
  <a href="#latest-version">Latest (v18.0)</a> •
  <a href="#usage">Usage</a>
</p>

---

## Overview

**CDEL-v2** is the certified execution layer (RE2) of the AGI Stack. It provides deterministic verifiers for all campaigns, enabling replay-based validation of every system modification. With ~50,000+ lines of fail-closed verification code, CDEL-v2 ensures that every operation is reproducible, verifiable, and mathematically sound.

### Key Principles

| Principle | Description |
|-----------|-------------|
| **Fail-Closed** | All verifiers default to rejection on any error |
| **Deterministic** | Same inputs always produce identical outputs (Q32 arithmetic) |
| **Content-Addressed** | All artifacts identified by SHA-256 hash |
| **Replayable** | Every operation can be reproduced for verification |
| **Bit-Exact** | Q32 fixed-point ensures bit-level reproducibility |

### Latest Additions (v18.0 + SH-1)

- **Omega Daemon Verifier**: 1,334 lines of deterministic replay logic
- **CCAP Universal Verifier**: 758 lines for arbitrary patch verification
- **Authority System Integration**: Cryptographic pins for evaluation kernels
- **Receipt-Driven Verification**: Historical outcome tracking for meta-learning

---

## Navigation

### Quick Access

| What you need | Where to look |
|---------------|---------------|
| **Latest version** | `cdel/v18_0/` |
| **Omega daemon verifier** | `cdel/v18_0/verify_rsi_omega_daemon_v1.py` |
| **CCAP verifier** | `cdel/v18_0/verify_ccap_v1.py` |
| **Campaign verifiers** | `cdel/v{X}/verify_rsi_*.py` |
| **Canonical JSON** | `cdel/v1_7r/canon.py` |
| **Omega daemon tests** | `cdel/v18_0/tests_omega_daemon/` |
| **CCAP tests** | `cdel/v18_0/tests_ccap/` |
| **Campaign tests** | `cdel/v{X}/tests/` or `cdel/v{X}/tests_*/` |

### Version Directories

| Version | Feature | Key Verifier | LOC |
|---------|---------|--------------|-----|
| **v18_0** | **Omega Daemon + CCAP** | `verify_rsi_omega_daemon_v1.py`, `verify_ccap_v1.py` | 2,092 |
| v17_0 | SAS VAL | `verify_rsi_sas_val_v1.py` | 856 |
| v16_0-v16_1 | SAS Metasearch | `verify_rsi_sas_metasearch_v1.py` | 743 |
| v15_0 | SAS Kernel | `verify_rsi_sas_kernel_v1.py` | 621 |
| v14_0 | SAS System | `verify_rsi_sas_system_v1.py` | 589 |
| v13_0 | SAS Science | `verify_rsi_sas_science_v1.py` | 1,124 |
| v12_0 | SAS Code | `verify_rsi_sas_code_v1.py` | 498 |
| v11_0-v11_3 | Arch Synthesis | `verify_rsi_arch_synthesis_v1.py` | 672 |
| v10_0 | Model Genesis | `verify_rsi_model_genesis_v1.py` | 534 |
| v7_0 | Alignment | `verify_rsi_alignment_v1.py` | 181 |
| v1_5r-v6_0 | Foundation | Various verifiers | ~5,000 |

**Total Verification Code**: ~50,000+ lines across all versions

---

## Latest Version (v18.0)

### Omega Daemon Components

```
cdel/v18_0/
├── omega_observer_v1.py        # Metric collection (content-addressed)
├── omega_decider_v1.py         # Policy-based decision making
├── omega_promoter_v1.py        # Promotion and subverifier orchestration
├── omega_activator_v1.py       # meta-core activation
├── omega_runaway_v1.py         # Runaway mode escalation
├── omega_common_v1.py          # Shared utilities
├── verify_rsi_omega_daemon_v1.py  # Main verifier (1,334 lines)
├── verify_ccap_v1.py           # CCAP universal verifier (758 lines)
├── tests_omega_daemon/         # Omega daemon test suite (100+ tests)
└── tests_ccap/                 # CCAP test suite (20+ tests)
```

### Key Functions

| Module | Function | Purpose |
|--------|----------|---------|
| `omega_observer_v1` | `observe()` | Collect metrics from campaigns |
| `omega_decider_v1` | `decide()` | Generate decision plan via temperature bands |
| `omega_promoter_v1` | `run_promotion()` | Handle artifact promotion |
| `omega_runaway_v1` | `check_runaway()` | Escalate compute budget on stalls |
| `verify_rsi_omega_daemon_v1` | `verify()` | Full deterministic replay (1,334 lines) |
| `verify_ccap_v1` | `verify()` | Universal patch verification (758 lines) |

### CCAP (Certified Capsule Proposal) Protocol

The CCAP verifier enables universal verification for arbitrary code patches:

**Three-Stage Pipeline:**
1. **REALIZE**: Apply patch and validate schema
2. **SCORE**: Run evaluation kernel benchmarks
3. **FINAL_AUDIT**: Verify promotion criteria

**Enforcement:**
- Patch allowlists (`authority/ccap_patch_allowlists_v1.json`)
- Evaluation kernels (`authority/evaluation_kernels/`)
- Authority pins (`authority/authority_pins_v1.json`)

### Usage Example

```python
from cdel.v18_0.omega_observer_v1 import observe
from cdel.v18_0.omega_decider_v1 import decide
from cdel.v18_0.verify_rsi_omega_daemon_v1 import verify

# Observe system state
observation, obs_hash = observe(
    tick_u64=42,
    active_manifest_hash="sha256:...",
    policy_hash="sha256:...",
    registry_hash="sha256:...",
    objectives_hash="sha256:..."
)

# Make decision
decision, dec_hash = decide(
    tick_u64=42,
    state=current_state,
    observation_report=observation,
    observation_report_hash=obs_hash,
    policy=policy,
    registry=registry
)

# Verify a tick
verify(
    payload_dir=Path("runs/my_run/tick_00042"),
    parent_payload_dir=Path("runs/my_run/tick_00041"),
    repo_root=Path("."),
    mode="full"
)
```

---

## Quickstart (Development)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Compile and test
python -m compileall -q cdel tests
pytest -q
```

## Smoke Tests

```bash
scripts/smoke_e2e.sh
scripts/smoke_rebuild.sh
scripts/smoke_statcert_adopt.sh
scripts/smoke_generalization_experiment.sh
```

---

## CLI Examples

```bash
# Initialize CDEL environment
cdel init --budget 1000000

# Run tasks
cdel run-tasks tasks/stream_min.jsonl --generator enum --out runs/min

# Check invariants
cdel check-invariants

# Evaluate expression
cdel eval --expr '{"tag":"app","fn":{"tag":"sym","name":"inc"},"args":[{"tag":"int","value":1}]}'
```

---

## Canonical JSON (GCJ-1)

The canonical JSON module is used across all versions for deterministic hashing:

```python
from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, load_canon_json, write_canon_json

# Compute hash
content_hash = sha256_prefixed(canon_bytes(my_object))

# Load canonical JSON
data = load_canon_json(Path("artifact.json"))

# Write canonical JSON
write_canon_json(Path("output.json"), data)
```

**GCJ-1 Rules:**
1. UTF-8 encoding
2. Keys sorted alphabetically
3. No trailing whitespace
4. LF line endings
5. Minimal JSON formatting

---

## Testing

### Run All Tests

```bash
# All v18.0 Omega daemon tests
python3 -m pytest cdel/v18_0/tests_omega_daemon/ -v

# CCAP tests
python3 -m pytest cdel/v18_0/tests_ccap/ -v

# Specific test file
python3 -m pytest cdel/v18_0/tests_omega_daemon/test_omega_decider.py -v

# With coverage
python3 -m pytest cdel/ --cov=cdel --cov-report=html
```

### Test Patterns

All tests follow determinism requirements:

```python
def test_decision_determinism():
    """Verify decision is deterministic."""
    result1 = decide(**inputs)
    result2 = decide(**inputs)
    assert result1 == result2
    
def test_hash_stability():
    """Verify hash is stable across runs."""
    hash1 = sha256_prefixed(canon_bytes(obj))
    hash2 = sha256_prefixed(canon_bytes(obj))
    assert hash1 == hash2
```

---

## Q32 Arithmetic

CDEL-v2 uses Q32 fixed-point arithmetic for deterministic, bit-exact computation:

**Q32 Format:**
- 32-bit signed integer representing a fixed-point number
- Range: ±2,147,483,648
- Precision: ~2^-32 (9 decimal digits)

**Example:**
```python
from cdel.v18_0.omega_common_v1 import q32_from_float, q32_to_float, q32_mul

# Convert to Q32
q32_value = q32_from_float(0.75)  # 3221225472

# Multiply in Q32
result = q32_mul(q32_value, q32_from_float(2.0))  # 1.5 in Q32

# Convert back
float_result = q32_to_float(result)  # 1.5
```

**Benefits:**
- Bit-exact reproducibility across platforms
- No floating-point rounding errors
- Verifiable arithmetic operations

**Limitations:**
- Limited precision compared to FP64
- No support for deep learning gradients

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/stat_cert_runbook.md` | Stat cert + CAL adoption flow |
| `docs/sealed_signing.md` | Canonicalization contract |
| `docs/learning_claims.md` | Learning definition and risk control |

---

## Architecture

```
CDEL-v2/
├── cdel/                    # Main package
│   ├── v1_5r/ ... v18_0/   # Version directories (56 distinct verifiers)
│   ├── cli.py              # CLI interface
│   ├── solve.py            # Constraint solver
│   └── config.py           # Configuration
├── tests/                   # Cross-version tests
├── scripts/                 # Utility scripts
└── docs/                    # Documentation
```

---

## For Agents

### Finding Things Quickly

```bash
# Find all verifiers
find cdel -name "verify_rsi_*.py" | sort

# Find tests for v18.0
find cdel/v18_0 -name "test_*.py"

# Search for a function
grep -r "def observe(" cdel/v18_0/

# Find schema usage
grep -r "omega_state_v1" cdel/v18_0/
```

### Key Entry Points

| Task | Entry Point |
|------|-------------|
| Verify a tick | `cdel.v18_0.verify_rsi_omega_daemon_v1.verify()` |
| Verify CCAP | `cdel.v18_0.verify_ccap_v1.verify()` |
| Observe metrics | `cdel.v18_0.omega_observer_v1.observe()` |
| Make decision | `cdel.v18_0.omega_decider_v1.decide()` |
| Promote artifact | `cdel.v18_0.omega_promoter_v1.run_promotion()` |
| Hash content | `cdel.v1_7r.canon.sha256_prefixed()` |
| Q32 arithmetic | `cdel.v18_0.omega_common_v1.q32_*()` |

---

## Verification Statistics

### Code Metrics

- **Total Verifiers**: 56 distinct verifiers across all versions
- **Total Verification LOC**: ~50,000+ lines
- **Largest Verifier**: `verify_rsi_omega_daemon_v1.py` (1,334 lines)
- **Test Coverage**: 200+ tests across all versions

### Verification Depth

| Component | Verification Type | LOC |
|-----------|-------------------|-----|
| Omega Daemon | Full deterministic replay | 1,334 |
| CCAP | Universal patch verification | 758 |
| SAS Science | Theory discovery validation | 1,124 |
| SAS VAL | Native code lift verification | 856 |
| SAS Metasearch | Search optimization validation | 743 |
| **Total** | **Fail-closed verification** | **~50,000+** |

---

## License

See repository root LICENSE file.

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em><br>
  <em>~50,000+ lines of fail-closed verification code</em>
</p>
