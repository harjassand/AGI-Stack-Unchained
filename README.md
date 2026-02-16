<h1 align="center">
  🧠 AGI Stack
</h1>

<p align="center">
  <strong>Recursive Self-Improvement Infrastructure with Constitutional Guarantees</strong>
</p>

<p align="center">
  <code>v18.0 + SH-1</code> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#navigation">Navigation</a> •
  <a href="#documentation">Documentation</a>
</p>

---

## Overview

**AGI Stack** is a comprehensive infrastructure for recursive self-improvement (RSI) with constitutional safety guarantees. The system operates through a four-layer trust hierarchy where untrusted proposers generate candidates, certified verifiers validate them, and a minimal trusted computing base enforces constitutional constraints.

### Current Version: v18.0 + SH-1

**Latest Features:**
- **Omega Daemon v18.0**: Unified orchestration with deterministic tick-based execution
- **Genesis Engine SH-1**: Receipt-driven meta-learning with symbiotic optimization
- **CCAP Protocol**: Universal verification for arbitrary code patches
- **Authority System**: Cryptographic pins for evaluation kernels and patch allowlists
- **Polymath Refinery**: Deterministic domain proposal generation

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Recursive Self-Improvement** | Autonomous code evolution through verified campaigns |
| **Constitutional Governance** | Immutable safety constraints enforced by meta-core |
| **Deterministic Replay** | Every operation is reproducible via Q32 arithmetic |
| **Fail-Closed Security** | All components default to rejection on error |
| **Receipt-Driven Learning** | SH-1 learns from historical promotion/rejection patterns |
| **Universal Verification** | CCAP enables single verifier for arbitrary patches |

### What This System IS and IS NOT

**✓ This IS:**
- A world-class RSI infrastructure with ~50,000+ lines of verification code
- Deterministic, verifiable self-improvement with cryptographic proofs
- Fail-closed safety preventing treacherous turns
- Receipt-driven meta-learning (SH-1) improving proposal quality

**✗ This IS NOT:**
- Artificial General Intelligence (AGI) or Artificial Superintelligence (ASI)
- A deep learning system (no PyTorch/TensorFlow/JAX)
- Connected to the real world (sandboxed filesystem only)
- Capable of multimodal learning or creative reasoning

**For a comprehensive gap analysis**, see [`AGI_Stack_Gap_Analysis_to_AGI_ASI.md`](./AGI_Stack_Gap_Analysis_to_AGI_ASI.md)

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Rust 1.70+** (for meta-core verifier)
- **Git** (for version control)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd AGI-Stack-Clean

# Bootstrap the environment
./scripts/bootstrap_stack.sh

# Activate virtual environment
source .venv/bin/activate

# Run tests
python3 -m pytest CDEL-v2/cdel/v18_0/tests_omega_daemon/ -v
```

### First Run

```bash
# Set required paths
export PYTHONPATH="CDEL-v2:."
export AGI_ROOT="$(pwd)/runs"

# Run the Omega daemon (development profile)
python3 CDEL-v2/cdel/v18_0/run_omega_daemon_v1.py \
  --pack campaigns/rsi_omega_daemon_v18_0/omega_pack_v1.json \
  --out runs/my_first_run

# Monitor with Mission Control
python3 -m mission_control.server --runs_root ./runs --port 8080
# Open http://localhost:8080
```

---

## Architecture

### Trust Layers (RE1-RE4)

```
┌────────────────────────────────────────────────────────────────┐
│                    AGI STACK ARCHITECTURE                       │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐                                       │
│  │  RE1: meta-core     │ ← Trusted Computing Base (TCB)        │
│  │  Constitutional     │   Immutable verification kernel        │
│  │  Verification       │   Rust-based cryptographic proofs     │
│  └─────────┬───────────┘                                       │
│            ↓ verifies                                           │
│  ┌─────────────────────┐                                       │
│  │  RE2: CDEL-v2       │ ← Certified Execution Layer            │
│  │  Deterministic      │   Verifiers, campaigns, promotion      │
│  │  Replay + Q32       │   ~50,000+ LOC verification            │
│  └─────────┬───────────┘                                       │
│            ↓ validates                                          │
│  ┌─────────────────────┐                                       │
│  │  RE3: Extension-1   │ ← Proposer Layer (Untrusted)           │
│  │  Candidate          │   CAOE, self-improvement, proposals    │
│  │  Generation         │   Genesis Engine SH-1                 │
│  └─────────┬───────────┘                                       │
│            ↓ conforms to                                        │
│  ┌─────────────────────┐                                       │
│  │  RE4: Genesis       │ ← Specification Layer                  │
│  │  Schemas &          │   JSON schemas, protocols, contracts   │
│  │  Protocols          │   Authority pins, allowlists          │
│  └─────────────────────┘                                       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Directory Map

| Directory | Layer | Purpose |
|-----------|-------|---------|
| [`meta-core/`](meta-core/README.md) | RE1 | Trusted Computing Base, constitutional verification |
| [`CDEL-v2/`](CDEL-v2/README.md) | RE2 | Certified execution, verifiers, campaigns |
| [`Extension-1/`](Extension-1/README.md) | RE3 | Proposers, CAOE, Genesis Engine SH-1 |
| [`Genesis/`](Genesis/README.md) | RE4 | Schemas, protocols, specifications |
| [`authority/`](authority/) | RE4 | Authority pins, evaluation kernels, patch allowlists |
| [`campaigns/`](campaigns/README.md) | RE2 | Campaign configuration packs (11 total) |
| [`daemon/`](daemon/) | RE2 | Persistent daemon implementations |
| [`orchestrator/`](orchestrator/) | RE2 | Campaign orchestration |
| [`polymath/`](polymath/README.md) | - | Domain registry and management |
| [`tools/`](tools/README.md) | - | Mission control, utilities, Genesis Engine |
| [`runs/`](runs/) | - | Execution output artifacts (content-addressed) |
| [`scripts/`](scripts/README.md) | - | Utility and bootstrap scripts |

---

## Navigation

### For Humans

| What you need | Where to look |
|---------------|---------------|
| **Get started** | [Quick Start](#quick-start) above |
| **Understand architecture** | [AGI_Stack_Complete_Repository_Report.md](AGI_Stack_Complete_Repository_Report.md) (2,500+ lines) |
| **Gap analysis to AGI/ASI** | [AGI_Stack_Gap_Analysis_to_AGI_ASI.md](AGI_Stack_Gap_Analysis_to_AGI_ASI.md) |
| **Core components** | Component READMEs linked in [Directory Map](#directory-map) |
| **Latest features (v18.0 + SH-1)** | [`CDEL-v2/cdel/v18_0/`](CDEL-v2/cdel/v18_0/) |
| **Genesis Engine SH-1** | [`tools/genesis_engine/`](tools/genesis_engine/) |
| **CCAP Protocol** | [`CDEL-v2/cdel/v18_0/verify_ccap_v1.py`](CDEL-v2/cdel/v18_0/verify_ccap_v1.py) |
| **Authority System** | [`authority/`](authority/) |
| **Run tests** | `python3 -m pytest CDEL-v2/cdel/v18_0/tests_omega_daemon/ -v` |
| **Monitoring** | `python3 -m mission_control.server --runs_root ./runs` |

### For Agents

**See [`agents.md`](agents.md) for a comprehensive AI agent navigation guide.**

Quick reference:

| What you need | Where to look |
|---------------|---------------|
| **Omega daemon verifier** | `CDEL-v2/cdel/v18_0/verify_rsi_omega_daemon_v1.py` |
| **CCAP verifier** | `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` |
| **Campaign verifiers** | `CDEL-v2/cdel/v{X}/verify_rsi_*.py` |
| **Campaign packs** | `campaigns/rsi_{name}_v{X}/` |
| **Run outputs** | `runs/rsi_{name}_v{X}_{date}/` |
| **JSON schemas** | `Genesis/schema/v{X}/` |
| **Authority pins** | `authority/authority_pins_v1.json` |
| **Evaluation kernels** | `authority/evaluation_kernels/` |
| **Patch allowlists** | `authority/ccap_patch_allowlists_v1.json` |
| **Constitution/contracts** | `meta-core/meta_constitution/v{X}/` |
| **Daemon implementations** | `daemon/rsi_{name}_v{X}/` |
| **Test files** | `CDEL-v2/cdel/v{X}/tests*/test_*.py` |

---

## Core Components

### Omega Daemon v18.0

The unified orchestration daemon that manages the entire RSI loop:

```
┌────────────────────────────────────────────────────────────────┐
│                   OMEGA TICK LIFECYCLE                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│   OBSERVE → DIAGNOSE → DECIDE → DISPATCH → EXECUTE            │
│      ↑                                         │                │
│      └── ACTIVATE ← PROMOTE ← VERIFY ←─────────┘                │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

- **Location**: `CDEL-v2/cdel/v18_0/`
- **Key files**: `omega_observer_v1.py`, `omega_decider_v1.py`, `omega_promoter_v1.py`
- **Verifier**: `verify_rsi_omega_daemon_v1.py` (1,334 lines of replay logic)
- **Capabilities**: 11 total campaigns, 3-6 actively enabled

### Genesis Engine SH-1 (Symbiotic Harmony v1)

Receipt-driven self-improvement with meta-learning:

```
Receipt Analysis → Bucket Planning → Patch Generation → CCAP Emission
     (PD/XS)         (HOTFIX/INC/EXP)    (Templates)      (Universal)
```

- **Location**: `tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py`
- **Key Features**:
  - **PD (Promotion Density)**: Success rate per file
  - **XS (eXploration Score)**: Novelty vs exploitation balance
  - **Bucket Planning**: HOTFIX, INCREMENTAL, EXPLORATORY
  - **Templates**: COMMENT_APPEND, JSON_TWEAK_COOLDOWN, JSON_TWEAK_BUDGET_HINT
  - **Hard-Avoid Projection**: Prevents novelty laundering

### CCAP (Certified Capsule Proposal) Protocol

Universal verification for arbitrary code patches:

- **Location**: `CDEL-v2/cdel/v18_0/verify_ccap_v1.py` (758 lines)
- **Stages**: REALIZE → SCORE → FINAL_AUDIT
- **Enforcement**: Patch allowlists (`authority/ccap_patch_allowlists_v1.json`)
- **Campaigns**: 2 CCAP-enabled campaigns (currently disabled/staged)

### Authority System

Cryptographic root of trust for system components:

- **Authority Pins**: `authority/authority_pins_v1.json`
- **Evaluation Kernels**: `authority/evaluation_kernels/ek_omega_v18_0_v1.json`
- **Operator Pools**: `authority/operator_pools/operator_pool_core_v1.json`
- **Patch Allowlists**: `authority/ccap_patch_allowlists_v1.json`

### Polymath System

Domain discovery and conquest:

- **Registry**: `polymath/registry/polymath_registry_v1.csv`
- **Refinery Proposer**: `tools/polymath/polymath_refinery_proposer_v1.py`
- **Campaigns**: Scout, Bootstrap, Conquer

### Campaign System

Atomic units of work producing verifiable outputs:

- **SAS-Science v13.0**: Scientific theory discovery
- **SAS-System v14.0**: System optimization
- **SAS-Kernel v15.0**: Kernel operations
- **SAS-Metasearch v16.0-v16.1**: Search optimization
- **SAS-VAL v17.0**: Native code lift
- **Omega Daemon v18.0**: Unified orchestration
- **Genesis Engine SH-1 v0.1**: Symbiotic optimization (staged)
- **Polymath Scout v1**: Domain discovery (staged)

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AGI_ROOT` | Root directory for AGI Stack operations |
| `PYTHONPATH` | Should include `CDEL-v2` and repo root |
| `OMEGA_RUNAWAY_ENABLED` | Enable runaway mode (1/0) |
| `OMEGA_MAX_TICKS_U64` | Maximum ticks before exit |
| `META_CORE_ROOT` | Override meta-core location |

### Key Configuration Files

| File | Purpose |
|------|---------|
| `campaigns/*/omega_pack_v1.json` | Campaign configuration pack |
| `campaigns/*/omega_policy_v1.json` | Omega daemon policy |
| `campaigns/*/omega_capability_registry_v2.json` | Campaign registry |
| `campaigns/*/omega_objectives_v1.json` | Optimization objectives |
| `authority/authority_pins_v1.json` | Authority pins for system components |
| `authority/ccap_patch_allowlists_v1.json` | CCAP patch allowlists |

---

## Testing

### Run All Tests

```bash
# Omega daemon tests (comprehensive)
python3 -m pytest CDEL-v2/cdel/v18_0/tests_omega_daemon/ -v

# CCAP tests
python3 -m pytest CDEL-v2/cdel/v18_0/tests_ccap/ -v

# Genesis Engine tests
PYTHONPATH='CDEL-v2:.' pytest tools/genesis_engine/tests/ -v

# meta-core tests
python3 -m pytest meta-core/tests_orchestration/ -v

# Extension-1 tests
python3 -m pytest Extension-1/tests/ -v
```

### Smoke Tests

```bash
./scripts/bootstrap_stack.sh          # Bootstrap environment
./scripts/e2e_formal_math_promotion.sh # E2E promotion test
```

---

## Documentation

| Document | Description | Lines |
|----------|-------------|-------|
| [`AGI_Stack_Complete_Repository_Report.md`](AGI_Stack_Complete_Repository_Report.md) | Comprehensive technical report | 2,500+ |
| [`AGI_Stack_Gap_Analysis_to_AGI_ASI.md`](AGI_Stack_Gap_Analysis_to_AGI_ASI.md) | Gap analysis to AGI/ASI | 500+ |
| [`agents.md`](agents.md) | AI agent navigation guide | - |
| [`Directive.md`](Directive.md) | Current development directive | - |
| Component READMEs | Detailed component documentation | - |

---

## Version History

| Version | Date | Key Features |
|---------|------|--------------|
| v1.5r | 2026-01-30 | RSI foundation, epoch tracking |
| v4.0 | 2026-02-01 | Omega unbounded loop |
| v7.0 | 2026-02-02 | Alignment verification (Superego Protocol) |
| v11.0-v11.3 | 2026-02-03 | Architecture synthesis |
| v13.0 | 2026-02-05 | SAS science |
| v16.0-v16.1 | 2026-02-06 | SAS metasearch |
| v17.0 | 2026-02-07 | SAS VAL native lift |
| **v18.0** | **2026-02-08** | **Omega daemon unification, runaway mode** |
| **v18.0 + SH-1** | **2026-02-11** | **Genesis Engine SH-1, CCAP protocol, Authority system** |

---

## Production Readiness

### Current State

- **Active Campaigns**: 3-6 campaigns actively enabled (varies by deployment profile)
- **CCAP Campaigns**: 2 campaigns staged for CCAP rollout (currently disabled)
- **Total Campaign Count**: 11 distinct capabilities across 6 major versions
- **Verification Depth**: ~50,000+ lines of fail-closed verification code
- **Test Coverage**: 200+ tests across all components

### Deployment Profiles

- **Development**: `campaigns/rsi_omega_daemon_v18_0/` (all campaigns enabled)
- **Production**: `campaigns/rsi_omega_daemon_v18_0_prod/` (conservative subset)
- **Runaway**: Extended autonomous operation with metric-driven escalation

---

## Contributing

1. All changes must pass tests
2. New features require documentation
3. Follow determinism requirements (Q32 arithmetic)
4. Constitutional changes require formal review
5. No modifications to forbidden paths (`authority/`, `meta-core/`, `CDEL-v2/`, `Genesis/`)

---

## License

See LICENSE file.

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em><br>
  <em>A stepping stone to AGI, not AGI itself.</em>
</p>
