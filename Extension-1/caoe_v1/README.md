<h1 align="center">
  🧬 CAOE v1.1
</h1>

<p align="center">
  <strong>Continuous Architecture Optimization Engine</strong>
</p>

<p align="center">
  <em>Autopoietic Evolution for Self-Improving AI Systems</em>
</p>

<p align="center">
  <a href="#overview">Overview</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#the-wake-sleep-dawn-cycle">Cycle</a> •
  <a href="#operators">Operators</a> •
  <a href="#usage">Usage</a> •
  <a href="#api-reference">API</a>
</p>

---

## Overview

**CAOE v1.1** (Continuous Architecture Optimization Engine) is the autopoietic evolution system that enables recursive self-improvement in the AGI Stack. It operates as an untrusted proposer (RE3) that generates architectural candidates, which are then certified by CDEL-v2 (RE2).

### Key Principles

| Principle | Description |
|-----------|-------------|
| **Autopoietic** | Self-organizing, continuously improving |
| **Deterministic** | Bit-identical outputs across runs |
| **Certified-Only** | All changes verified externally |
| **Fail-Closed** | Errors terminate, never proceed |

---

## Architecture

```
caoe_v1/
├── wake/                      # Wake Phase
│   ├── wake_anomaly_miner_v1.py    # Anomaly detection
│   └── anomaly_buffer_schema_v1.json
│
├── sleep/                     # Sleep Phase
│   ├── absop_isa_v1.py            # Operator ISA
│   ├── synth/                      # Synthesis engine
│   │   └── bounded_program_enumerator_v1.py
│   └── operators/                  # Abstraction operators
│       ├── coarse_grain_merge_v1.py
│       ├── latent_reify_v1.py
│       ├── stability_latent_detect_v1_1.py
│       ├── efe_tune_v1_1.py
│       └── option_compile_v1.py
│
├── dawn/                      # Dawn Phase
│   ├── selector_v1.py             # Candidate selection
│   ├── learner_v1.py              # Weight learning
│   └── monitor_falsifiers_v1.py   # Governance flags
│
├── artifacts/                 # Artifact generation
│   ├── ids_v1.py                  # Candidate ID derivation
│   └── candidate_tar_writer_v1.py # Tar packaging
│
├── state/                     # State management
│   └── proposer_state_schema_v1.json
│
├── cli/                       # Command-line interface
│   └── caoe_proposer_cli_v1.py
│
├── tests/                     # Test suite
│   ├── test_candidate_tar_determinism_v1.py
│   ├── test_state_update_determinism_v1.py
│   └── test_no_heldout_read_v1.py
│
├── api_v1.py                  # Core API utilities
├── CANONICALIZATION.md        # Canonicalization rules
└── README.md                  # This file
```

---

## The Wake-Sleep-Dawn Cycle

CAOE operates in a continuous three-phase cycle:

```
┌─────────────────────────────────────────────────────────────┐
│                    CAOE Evolution Cycle                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   WAKE (Perception)                                          │
│   ┌─────────────────────────────────────────────────┐       │
│   │ • Run identity candidate on dev suite           │       │
│   │ • Collect worst-performing regimes              │       │
│   │ • Mine anomalies → caoe_anomaly_buffer_v1       │       │
│   └─────────────────────────────────────────────────┘       │
│                          ↓                                   │
│   SLEEP (Synthesis)                                          │
│   ┌─────────────────────────────────────────────────┐       │
│   │ • Read anomaly buffer                           │       │
│   │ • Apply abstraction operators (AbsOps)          │       │
│   │ • Enumerate bounded programs                    │       │
│   │ • Generate candidate proposals                  │       │
│   └─────────────────────────────────────────────────┘       │
│                          ↓                                   │
│   DAWN (Selection)                                           │
│   ┌─────────────────────────────────────────────────┐       │
│   │ • Evaluate candidates (CDEL)                    │       │
│   │ • Apply safety contracts (C-INV, C-MDL, etc.)   │       │
│   │ • Select best candidate                         │       │
│   │ • Update operator weights                       │       │
│   └─────────────────────────────────────────────────┘       │
│                          ↓                                   │
│              [Return to WAKE with new ontology]              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Operators

CAOE v1.1 includes 8 abstraction operators:

### Core Operators

| Operator | ID | Description |
|----------|-----|-------------|
| **Coarse Grain Merge** | `ABSOP_COARSE_GRAIN_MERGE_V1` | Merges fine-grained symbols into coarser abstractions |
| **Latent Reify** | `ABSOP_LATENT_REIFY_V1` | Reifies latent patterns as explicit symbols |
| **Stability Latent Detect** | `ABSOP_STABILITY_LATENT_DETECT_V1_1` | Detects stable bits across time |
| **EFE Tune** | `ABSOP_EFE_TUNE_V1_1` | Tunes Expected Free Energy parameters |
| **Option Compile** | `ABSOP_OPTION_COMPILE_V1` | Compiles action sequences into macros |
| **Option Compile v1.1** | `ABSOP_OPTION_COMPILE_V1_1` | Enhanced macro compilation |
| **Template Extract** | `ABSOP_TEMPLATE_EXTRACT_V1` | Extracts common patterns (dormant) |
| **Render Canonicalize Phi** | `ABSOP_RENDER_CANONICALIZE_PHI_V1_1` | Canonical phi rendering |

### Operator Ranking

Operators are ranked by learned weights:

```python
# From absop_isa_v1.py
def operator_rankings(weights: dict) -> list[str]:
    # Sort by weight descending, then by op_id for determinism
    return sorted(
        ALLOWED_OP_IDS,
        key=lambda op: (-weights.get(op, 100), op)
    )
```

---

## Usage

### Run an Evolution Epoch

```bash
python3 -m cli.caoe_proposer_cli_v1 run-epoch \
  --base-ontology ./base_ontology.json \
  --suitepack-dev ./suites/dev \
  --out-dir ./epoch_output
```

### Replay an Epoch (Verification)

```bash
python3 -m cli.caoe_proposer_cli_v1 replay-epoch \
  --epoch-dir ./epoch_output \
  --expected-id abc123...
```

### Run Tests

```bash
# All tests
python3 -m pytest tests/ -v

# Determinism tests
python3 -m pytest tests/test_candidate_tar_determinism_v1.py -v
python3 -m pytest tests/test_state_update_determinism_v1.py -v

# Security tests (no heldout access)
python3 -m pytest tests/test_no_heldout_read_v1.py -v
```

---

## API Reference

### Core API (`api_v1.py`)

```python
from caoe_v1 import api_v1

# Canonical JSON serialization
bytes_out = api_v1.canonical_json_bytes(obj)

# Load JSON with strict parsing
data = api_v1.load_json_strict(path)

# Save with atomic write
api_v1.save_json_atomic(path, data)
```

### ID Generation (`artifacts/ids_v1.py`)

```python
from caoe_v1.artifacts import ids_v1

# Hash JSON object
hash_hex = ids_v1.hash_json(obj)

# Generate candidate ID
cid = ids_v1.candidate_id(
    manifest=manifest,
    ontology_patch=patch,
    mechanism_diff=diff,
    programs_by_path=programs
)
```

### Anomaly Mining (`wake/wake_anomaly_miner_v1.py`)

```python
from caoe_v1.wake import wake_anomaly_miner_v1

# Mine anomalies from evaluation results
buffer = wake_anomaly_miner_v1.mine_anomalies(
    eval_results=results,
    top_k_regimes=10
)
```

### Candidate Synthesis (`sleep/absop_isa_v1.py`)

```python
from caoe_v1.sleep import absop_isa_v1

# Propose candidates from anomaly buffer
candidates = absop_isa_v1.propose_candidates(
    anomaly_buffer=buffer,
    state=proposer_state,
    max_candidates=16
)
```

### Selection (`dawn/selector_v1.py`)

```python
from caoe_v1.dawn import selector_v1

# Select best candidate
selected = selector_v1.select(
    candidates=candidates,
    evaluation_results=results
)
```

### Learning (`dawn/learner_v1.py`)

```python
from caoe_v1.dawn import learner_v1

# Update state based on selection
new_state = learner_v1.update_state(
    state=current_state,
    selected_candidate=selected,
    evaluation_decision=decision
)
```

---

## Bounded Program Enumerator

The enumerator generates candidate programs within strict bounds:

```python
from caoe_v1.sleep.synth import bounded_program_enumerator_v1

programs = bounded_program_enumerator_v1.enumerate_programs(
    inputs=[{"name": "x", "dtype": "int8"}],
    outputs=[{"name": "y", "dtype": "int8"}],
    max_ops=3,
    max_constants=2,
    limit=16
)
```

### Supported Operations

| Operation | Arity | Description |
|-----------|-------|-------------|
| `GET` | 1 | Variable reference |
| `SLICE` | 2 | Bit slicing |
| `XOR` | 2 | Bitwise XOR |
| `CONST` | 0 | Constant literal |
| `COUNT1` | 1 | Popcount |
| `ARGMIN` | 1 | Argmin index |
| `ARGMAX` | 1 | Argmax index |

---

## State Management

### Proposer State Schema

```json
{
  "current_epoch": 42,
  "operator_weights": {
    "ABSOP_COARSE_GRAIN_MERGE_V1": 150,
    "ABSOP_LATENT_REIFY_V1": 120
  },
  "operator_quarantine_until_epoch": {},
  "recent_anomaly_regimes": [...],
  "history": [...],
  "macro_stage_enabled": true
}
```

### Weight Updates

```
On PASS: weight += 50
On FAIL: weight -= 30
On C-ANTI violation: quarantine for 5 epochs
```

---

## Canonicalization

All CAOE artifacts follow strict canonicalization:

1. **JSON**: UTF-8, sorted keys, no trailing whitespace
2. **Tar**: Deterministic ordering, fixed timestamps
3. **Hashes**: SHA-256 of canonical bytes

See [CANONICALIZATION.md](CANONICALIZATION.md) for full specification.

---

## Safety Contracts

CAOE enforces four contracts via CDEL:

| Contract | Description | On Failure |
|----------|-------------|------------|
| `C-INV` | Invariance on dev suite | Reject |
| `C-MDL` | MDL improvement | Reject |
| `C-DO` | No heldout regression | Reject |
| `C-ANTI` | No catastrophic failure | Quarantine |

---

## Governance Flags

Monitor system health via `monitor_falsifiers_v1.py`:

| Flag | Description |
|------|-------------|
| `ontology_bloat_proxy` | Symbol count growing too fast |
| `stagnation_proxy` | No improvements for N epochs |
| `macro_magic_proxy` | Macro stage over-reliance |
| `degenerate_proxy` | Degenerate candidates |

---

## Testing

### Determinism Tests

```bash
# Candidate tar must be byte-identical
python3 -m pytest tests/test_candidate_tar_determinism_v1.py -v

# State updates must be deterministic
python3 -m pytest tests/test_state_update_determinism_v1.py -v
```

### Security Tests

```bash
# Verify no heldout data access
export CAOE_TEST_DENY_HELDOUT_OPEN=1
python3 -m pytest tests/test_no_heldout_read_v1.py -v
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Non-deterministic output | Check random seeds, sorting |
| Operator quarantined | Wait 5 epochs or check C-ANTI |
| No candidates generated | Check anomaly buffer, operator weights |
| Hash mismatch | Verify canonicalization |

---

## Contributing

1. All code must be deterministic
2. No heldout data access in proposer
3. Full test coverage required
4. Document all public APIs

---

## License

See repository root LICENSE file.
