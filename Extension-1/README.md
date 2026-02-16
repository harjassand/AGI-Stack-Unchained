<h1 align="center">
  🔌 Extension-1
</h1>

<p align="center">
  <strong>The Proposer Layer for Autonomous Code Evolution</strong>
</p>

<p align="center">
  <code>RE3 Layer</code> •
  <a href="#overview">Overview</a> •
  <a href="#modules">Modules</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a>
</p>

---

## Overview

**Extension-1** contains the proposer-layer modules for the AGI Stack. As the RE3 (untrusted) layer, it generates candidate code modifications, architecture proposals, and domain discoveries that are then verified by CDEL-v2 (RE2) and certified by meta-core (RE1).

> ⚠️ **Security Note**: Extension-1 operates in an untrusted context. All outputs are verified by downstream layers before acceptance. This layer cannot modify verifiers, meta-core, or authority pins.

### Key Modules

| Module | Description | Status |
|--------|-------------|--------|
| **Genesis Engine SH-1** | Receipt-driven symbiotic optimization | Active (v0.3) |
| **self_improve_code_v1** | Code self-improvement module | Active |
| **caoe_v1** | Continuous Architecture Optimization Engine | Legacy (v1.1) |
| **agi-orchestrator** | High-level orchestration for AGI operations | Active |
| **CDEL** | Extension-specific CDEL utilities | Active |

### Latest Addition: Genesis Engine SH-1

The **Genesis Engine SH-1 (Symbiotic Harmony v1)** is the latest proposer, implementing receipt-driven meta-learning:

- **Location**: `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`
- **Key Innovation**: Learns from historical promotion/rejection patterns
- **Metrics**: PD (Promotion Density), XS (eXploration Score)
- **Output**: CCAP (Certified Capsule Proposal) bundles

---

## Architecture

```
Extension-1/
├── caoe_v1/                   # CAOE v1.1 implementation (legacy)
│   ├── wake/                  # Wake phase (anomaly mining)
│   ├── sleep/                 # Sleep phase (candidate synthesis)
│   ├── dawn/                  # Dawn phase (selection & learning)
│   ├── artifacts/             # Artifact generation
│   ├── cli/                   # Command-line interface
│   ├── state/                 # State management
│   └── tests/                 # Test suite
│
├── agi-orchestrator/          # High-level orchestration
│   ├── orchestrator/          # Core orchestrator
│   ├── pipelines/             # Processing pipelines
│   └── tests/                 # Test suite
│
├── self_improve_code_v1/      # Code self-improvement
│   ├── analyzer/              # Code analysis
│   ├── transformer/           # Code transformation
│   ├── validator/             # Validation logic
│   └── run.py                 # Main entry point
│
├── CDEL/                      # CDEL utilities for extensions
├── tests/                     # Integration tests
└── scripts/                   # Utility scripts
```

**Genesis Engine SH-1** is located in `tools/genesis_engine/` (not in Extension-1 directory):
```
tools/genesis_engine/
├── ge_symbiotic_optimizer_v0_3.py  # Main optimizer (519 lines)
├── sh1_pd_v1.py                    # Promotion Density extraction
├── sh1_xs_v1.py                    # eXploration Score computation
├── sh1_behavior_sig_v1.py          # Behavior signature & novelty
├── ge_audit_report_sh1_v0_1.py     # Audit report generation
└── tests/                          # Test suite
```

---

## Installation

```bash
# From repository root
cd Extension-1

# Install agi-orchestrator dependencies
pip install -e ./agi-orchestrator

# Install with CDEL
pip install -e ./CDEL
```

---

## Modules

### Genesis Engine SH-1 (Symbiotic Harmony v1)

The **Genesis Engine SH-1** implements receipt-driven self-improvement:

```
┌─────────────────────────────────────────────┐
│         Genesis Engine SH-1 Pipeline        │
├─────────────────────────────────────────────┤
│                                             │
│  Receipt Analysis → Bucket Planning        │
│     (PD/XS)           (HOTFIX/INC/EXP)      │
│                                             │
│  Patch Generation → CCAP Emission           │
│    (Templates)        (Universal)           │
│                                             │
└─────────────────────────────────────────────┘
```

**Key Features:**
- **PD (Promotion Density)**: Success rate per file (learns what works)
- **XS (eXploration Score)**: Balances exploitation vs exploration
- **Bucket Planning**: HOTFIX (high PD), INCREMENTAL (medium), EXPLORATORY (low)
- **Templates**: COMMENT_APPEND, JSON_TWEAK_COOLDOWN, JSON_TWEAK_BUDGET_HINT
- **Hard-Avoid Projection**: Prevents novelty laundering
- **CCAP Output**: Emits universal verification bundles

**Usage:**
```bash
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --runs_root runs/rsi_omega_daemon_v18_0/ \
  --out_dir proposals/sh1_v0_1/
```

**Campaign Integration:**
```bash
# Run via campaign
python3 CDEL-v2/cdel/v18_0/campaign_ge_symbiotic_optimizer_sh1_v0_1.py \
  --campaign_pack campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1/campaign_pack_v1.json \
  --out_dir runs/sh1_run/
```

### CAOE v1.1 (Legacy)

The **Continuous Architecture Optimization Engine** implements autopoietic evolution (legacy):

```
┌─────────────────────────────────────────────┐
│              CAOE v1.1 Cycle                │
├─────────────────────────────────────────────┤
│                                             │
│  ┌────────┐                                 │
│  │  WAKE  │ → Anomaly Mining                │
│  └────┬───┘                                 │
│       ↓                                     │
│  ┌────────┐                                 │
│  │ SLEEP  │ → Candidate Synthesis           │
│  └────┬───┘                                 │
│       ↓                                     │
│  ┌────────┐                                 │
│  │  DAWN  │ → Selection & Learning          │
│  └────┬───┘                                 │
│       ↓                                     │
│  [Next Epoch]                               │
│                                             │
└─────────────────────────────────────────────┘
```

[See full CAOE documentation →](caoe_v1/README.md)

### AGI Orchestrator

High-level orchestration for multi-component AGI operations:

```python
from agi_orchestrator import Orchestrator

orch = Orchestrator()
result = orch.run_pipeline("formal_math_promotion")
```

### Self-Improve Code v1

Automated code improvement with formal verification:

```python
from self_improve_code_v1 import CodeAnalyzer, CodeTransformer

analyzer = CodeAnalyzer()
issues = analyzer.analyze("./src")

transformer = CodeTransformer()
patches = transformer.generate_fixes(issues)
```

---

## Usage

### Run Genesis Engine SH-1

```bash
# Direct invocation
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --runs_root runs/rsi_omega_daemon_v18_0/ \
  --out_dir proposals/sh1_v0_1/

# Via campaign (when enabled)
python3 CDEL-v2/cdel/v18_0/campaign_ge_symbiotic_optimizer_sh1_v0_1.py \
  --campaign_pack campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1/campaign_pack_v1.json \
  --out_dir runs/sh1_run/

# Generate audit report
python3 tools/genesis_engine/ge_audit_report_sh1_v0_1.py \
  --runs_root runs/rsi_omega_daemon_v18_0/ \
  --out_dir reports/sh1_audit/
```

### Run CAOE Epoch (Legacy)

```bash
cd caoe_v1
python3 -m cli.caoe_proposer_cli_v1 run-epoch \
  --base-ontology ./ontology.json \
  --suitepack-dev ./suites/dev \
  --out-dir ./epoch_output
```

### Replay Epoch

```bash
python3 -m cli.caoe_proposer_cli_v1 replay-epoch \
  --epoch-dir ./epoch_output \
  --expected-id <candidate_id>
```

### Run Integration Tests

```bash
python3 -m pytest tests/ -v
```

---

## Testing

### Unit Tests

```bash
# Genesis Engine tests
PYTHONPATH='CDEL-v2:.' pytest tools/genesis_engine/tests/ -v

# CAOE tests
cd caoe_v1 && python3 -m pytest tests/ -v

# Orchestrator tests
cd agi-orchestrator && python3 -m pytest tests/ -v
```

### Integration Tests

```bash
cd Extension-1
python3 -m pytest tests/ -v
```

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CAOE_IDENTITY_CACHE_DIR` | Cache for identity evaluations |
| `CAOE_VERBOSE` | Enable verbose logging |
| `CAOE_TEST_DENY_HELDOUT_OPEN` | Block heldout access in tests |
| `GE_CONFIG_PATH` | Genesis Engine configuration path |

### Genesis Engine Configuration

Located in `tools/genesis_engine/ge_config_v1.json`:

```json
{
  "schema_version": "ge_config_v1",
  "bucket_fractions_q32": {
    "HOTFIX": 858993459,        // 20% (high PD files)
    "INCREMENTAL": 1717986918,  // 40% (medium PD)
    "EXPLORATORY": 1717986918   // 40% (low PD, high XS)
  },
  "opt_q32": 2576980378,        // Optimization parameter
  "templates": [
    "COMMENT_APPEND",
    "JSON_TWEAK_COOLDOWN",
    "JSON_TWEAK_BUDGET_HINT"
  ]
}
```

---

## Security Model

Extension-1 operates under these constraints:

1. **No Heldout Access** – Cannot read evaluation data
2. **Deterministic Outputs** – All candidates are reproducible
3. **Certificate Required** – All outputs verified by CDEL
4. **Quarantine on Failure** – Failed operators are quarantined
5. **Forbidden Paths** – Cannot modify `authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`

### Allowed Modification Paths

Extension-1 can only propose changes to:
- `orchestrator/`
- `tools/`
- `campaigns/`
- `polymath/registry/`

### Verification Flow

```
Extension-1 (Proposer)
    ↓
CCAP Bundle
    ↓
CDEL-v2 verify_ccap_v1.py (Verifier)
    ↓
meta-core (Constitutional Check)
    ↓
Promotion or Rejection
```

---

## Genesis Engine SH-1 Details

### Metrics

**PD (Promotion Density):**
- Measures success rate per file
- Formula: `promotions / (promotions + rejections)`
- High PD → File is "hot" (changes likely to be accepted)

**XS (eXploration Score):**
- Balances exploitation vs exploration
- Formula: `1.0 - PD` (simplified)
- High XS → File is "cold" (unexplored potential)

### Bucket Planning

| Bucket | PD Range | XS Range | Strategy |
|--------|----------|----------|----------|
| HOTFIX | High | Low | Exploit known-good files |
| INCREMENTAL | Medium | Medium | Balanced exploration |
| EXPLORATORY | Low | High | Explore untested files |

### Templates

| Template | Purpose | Example |
|----------|---------|---------|
| `COMMENT_APPEND` | Add explanatory comments | `# Optimization: reduce cooldown` |
| `JSON_TWEAK_COOLDOWN` | Adjust cooldown parameters | `"cooldown_ticks_u64": 10 → 5` |
| `JSON_TWEAK_BUDGET_HINT` | Adjust budget hints | `"budget_cost_hint_q32": 2.0 → 1.5` |

### Hard-Avoid Projection

Prevents "novelty laundering" by tracking behavior signatures:
- Computes fingerprint of patch effects
- Rejects patches that mimic previously rejected patterns
- Ensures genuine exploration, not disguised repetition

---

## Contributing

1. Changes must pass all tests
2. New features require documentation
3. Follow determinism requirements
4. No heldout data in proposer code
5. All proposals must emit CCAP bundles (for SH-1)

---

## License

See repository root LICENSE file.

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em><br>
  <em>Untrusted proposer layer with receipt-driven meta-learning</em>
</p>
