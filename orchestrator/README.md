# 🎭 Orchestrator

**Campaign Orchestration Layer for AGI Stack**

---

## Overview

This directory contains orchestration modules that manage campaign execution, including CLI entry points and shared utilities.

---

## Quick Reference

### Structure

```
orchestrator/
├── __init__.py                    # Package initialization
├── common/                        # Shared utilities
│   └── run_invoker_v1.py         # Campaign invocation
├── omega_v18_0/                   # Omega v18.0 orchestration
├── rsi_omega_daemon_v18_0.py     # Omega daemon CLI entry
├── rsi_sas_science_v13_0.py      # SAS Science CLI
├── rsi_sas_system_v14_0.py       # SAS System CLI
├── rsi_sas_kernel_v15_0.py       # SAS Kernel CLI
├── rsi_sas_metasearch_v16_1.py   # SAS Metasearch CLI
├── rsi_sas_val_v17_0.py          # SAS VAL CLI
├── rsi_sas_code_v12_0.py         # SAS Code CLI
└── tools/                         # Orchestration tools
```

---

## CLI Entry Points

### Omega Daemon

```bash
python3 -m orchestrator.rsi_omega_daemon_v18_0 \
  --config campaigns/rsi_omega_daemon_v18_0/omega_pack_v1.json \
  --out-dir runs/my_run
```

### Individual Campaigns

```bash
# SAS Science
python3 orchestrator/rsi_sas_science_v13_0.py \
  --out-dir runs/sas_science_run

# SAS System
python3 orchestrator/rsi_sas_system_v14_0.py \
  --out-dir runs/sas_system_run

# SAS Kernel
python3 orchestrator/rsi_sas_kernel_v15_0.py \
  --out-dir runs/sas_kernel_run

# SAS VAL
python3 orchestrator/rsi_sas_val_v17_0.py \
  --out-dir runs/sas_val_run
```

---

## Common Module

The `common/` directory contains shared orchestration utilities:

### run_invoker_v1.py

Campaign invocation with subprocess isolation:

```python
from orchestrator.common.run_invoker_v1 import invoke_campaign

exit_code = invoke_campaign(
    campaign_id="rsi_sas_science_v13_0",
    out_dir=Path("./runs/tick_42"),
    env_overrides={"V13_MAX_CANDIDATES": "8"}
)
```

---

## Campaign CLIs

Each campaign CLI (`rsi_*.py`) follows this pattern:

1. Parse arguments
2. Load campaign pack
3. Set up environment
4. Execute campaign
5. Generate receipts
6. Return exit code

### Example: SAS Science v13.0

```python
# rsi_sas_science_v13_0.py
def main():
    args = parse_args()
    pack = load_pack(args.config or default_pack())
    
    # Execute campaign phases
    candidates = discover_theories(pack)
    evaluated = evaluate_on_heldout(candidates)
    best = select_best(evaluated)
    
    # Generate receipts
    write_receipts(args.out_dir, best)
    
    return 0 if best.improvement > threshold else 1
```

---

## Omega v18.0 Orchestration

The `omega_v18_0/` subdirectory contains Omega-specific orchestration:

| Module | Purpose |
|--------|---------|
| `dispatcher.py` | Campaign dispatch logic |
| `environment.py` | Environment setup |
| `receipts.py` | Receipt generation |

---

## For Agents

### Quick Patterns

```bash
# List all CLI entry points
ls *.py

# Find campaign implementations
find . -name "rsi_*.py"

# Check common utilities
ls common/

# View CLI arguments
python3 orchestrator/rsi_sas_science_v13_0.py --help
```

### Key Entry Points

| Campaign | CLI |
|----------|-----|
| Omega Daemon | `orchestrator/rsi_omega_daemon_v18_0.py` |
| SAS Science | `orchestrator/rsi_sas_science_v13_0.py` |
| SAS System | `orchestrator/rsi_sas_system_v14_0.py` |
| SAS Kernel | `orchestrator/rsi_sas_kernel_v15_0.py` |
| SAS VAL | `orchestrator/rsi_sas_val_v17_0.py` |

---

*See CDEL-v2 for verifier implementations and campaigns/ for configuration packs.*
