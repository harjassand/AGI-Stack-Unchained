# 🔧 Tools

**Utility Tools and Mission Control for AGI Stack**

---

## Overview

This directory contains utility tools for monitoring, debugging, and managing AGI Stack operations, including the **Genesis Engine SH-1** self-improvement system.

---

## Quick Reference

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `genesis_engine/` | **SH-1 symbiotic optimizer** (receipt-driven self-improvement) |
| `mission_control/` | Web dashboard for monitoring runs |
| `omega_mission_control/` | Omega-specific monitoring |
| `omega/` | Omega daemon utilities |
| `polymath/` | Polymath domain tools (Refinery Proposer) |
| `math_checker_v1/` | Mathematical proof checking |

---

## Genesis Engine SH-1

**Location**: `genesis_engine/`

**Purpose**: Receipt-driven self-improvement with meta-learning

**Key Components**:
- `ge_symbiotic_optimizer_v0_3.py` - Main optimizer (847 lines)
- `sh1_pd_v1.py` - Promotion Density extraction (160 lines)
- `sh1_xs_v1.py` - eXperience Snapshot builder (413 lines)
- `sh1_behavior_sig_v1.py` - Behavior signature & novelty (207 lines)
- `ge_audit_report_sh1_v0_1.py` - Audit report generation

**Configuration**: `genesis_engine/config/ge_config_v1.json`

**Usage**:
```bash
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --subrun_out_dir runs/sh1_run/ \
  --ge_config_path tools/genesis_engine/config/ge_config_v1.json \
  --authority_pins_path authority/authority_pins_v1.json \
  --recent_runs_root runs/ \
  --max_ccaps 1
```

**Key Features**:
- **PD (Promotion Density)**: Success rate per file
- **XS (eXploration Score)**: Novelty vs exploitation balance
- **Bucket Planning**: HOTFIX (60%), INCREMENTAL (20%), EXPLORATORY (20%)
- **Templates**: COMMENT_APPEND, JSON_TWEAK_COOLDOWN, JSON_TWEAK_BUDGET_HINT
- **Hard-Avoid Projection**: Prevents novelty laundering
- **CCAP Output**: Emits universal verification bundles

---

## Mission Control

### Starting the Dashboard

```bash
# Start Mission Control server
python3 -m mission_control.server --runs_root ./runs --port 8080

# Then open http://localhost:8080
```

### Features

- Real-time tick monitoring
- Campaign execution history
- Metric visualization
- Promotion tracking
- Error analysis

---

## Omega Tools

The `omega/` directory contains Omega daemon utilities:

| Tool | Purpose |
|------|---------|
| State inspection | View and debug daemon state |
| Tick replay | Replay specific ticks |
| Metric analysis | Analyze collected metrics |
| Overnight runner | `omega_overnight_runner_v1.py` for extended runs |

---

## Polymath Tools

The `polymath/` directory contains domain management tools:

| Tool | Purpose |
|------|---------|
| **Refinery Proposer** | `polymath_refinery_proposer_v1.py` - Deterministic domain proposals |
| Domain viewer | Inspect domain registry |
| Portfolio analyzer | Analyze domain portfolio |
| Cache manager | Manage domain cache |

**Refinery Proposer Usage**:
```bash
python3 tools/polymath/polymath_refinery_proposer_v1.py \
  --registry polymath/registry/polymath_registry_v1.csv \
  --out_dir proposals/polymath/ \
  --max_proposals 10
```

---

## Weekend Launcher

```bash
# Launch weekend runaway mode
./launch_omega_runaway_weekend_v18_1_recovery.sh
```

This script:
1. Configures runaway mode
2. Sets objectives
3. Starts Omega daemon
4. Monitors progress

---

## Math Checker

The `math_checker_v1/` validates mathematical proofs:

```bash
python3 -m tools.math_checker_v1.check \
  --proof path/to/proof.json
```

---

## For Agents

### Quick Patterns

```bash
# Start monitoring
python3 -m mission_control.server --runs_root ./runs

# Run Genesis Engine SH-1
python3 tools/genesis_engine/ge_symbiotic_optimizer_v0_3.py \
  --subrun_out_dir runs/sh1/ \
  --max_ccaps 1

# Run Polymath Refinery
python3 tools/polymath/polymath_refinery_proposer_v1.py \
  --registry polymath/registry/polymath_registry_v1.csv \
  --out_dir proposals/

# Find all tools
find . -name "*.py" -type f | head -20

# List mission control files
ls mission_control/

# List omega tools
ls omega/

# List Genesis Engine files
ls genesis_engine/
```

---

*See component READMEs for detailed tool documentation.*

---

<p align="center">
  <em>Generated: 2026-02-11 | Version: 18.0 + SH-1</em>
</p>
