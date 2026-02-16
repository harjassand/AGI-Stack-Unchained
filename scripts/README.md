# 📜 scripts

**Utility Scripts for AGI Stack Operations**

---

## Overview

This directory contains bootstrap and end-to-end test scripts for the AGI Stack.

---

## Scripts

### bootstrap_stack.sh

**Purpose**: Initialize the development environment and install all dependencies.

```bash
./scripts/bootstrap_stack.sh
```

**What it does**:
1. Creates Python virtual environment (`.venv`)
2. Installs core dependencies (jsonschema, blake3, cryptography)
3. Installs pytest for testing
4. Installs CDEL-v2 in editable mode
5. Installs AGI Orchestrator in editable mode

**Prerequisites**:
- Python 3.11+
- pip

**Output**:
```
Creating virtual environment...
Installing core dependencies...
Installing CDEL...
Installing AGI Orchestrator...
Bootstrap complete!
```

---

### e2e_formal_math_promotion.sh

**Purpose**: Run end-to-end formal math promotion pipeline.

```bash
./scripts/e2e_formal_math_promotion.sh
```

**What it does**:
1. Initializes CDEL environment
2. Runs formal math evaluation suite
3. Checks promotion criteria
4. Generates promotion report

**Environment Variables**:
| Variable | Required | Description |
|----------|----------|-------------|
| `HELDOUT_SUITES_DIR` | Yes | Path to heldout test suites |
| `ALLOW_DEV_HELDOUT_FALLBACK` | No | Set to `1` for dev testing |

**Example (dev mode)**:
```bash
export ALLOW_DEV_HELDOUT_FALLBACK=1
./scripts/e2e_formal_math_promotion.sh
```

---

### e2e_formal_math_distill_promotion.sh

**Purpose**: Run end-to-end formal math promotion with distillation.

```bash
./scripts/e2e_formal_math_distill_promotion.sh
```

**What it does**:
1. All steps from `e2e_formal_math_promotion.sh`
2. Additionally runs distillation pipeline
3. Validates distilled model meets criteria

**Environment Variables**:
Same as `e2e_formal_math_promotion.sh`

---

## Usage Examples

### Full Development Setup

```bash
# Bootstrap environment
./scripts/bootstrap_stack.sh

# Activate virtual environment
source .venv/bin/activate

# Run tests
python3 -m pytest meta-core/tests_orchestration/ -v
```

### Production E2E Testing

```bash
# Set heldout suites path
export HELDOUT_SUITES_DIR=/path/to/heldout/suites

# Run formal math promotion
./scripts/e2e_formal_math_promotion.sh
```

---

## Troubleshooting

### Bootstrap Fails

| Error | Solution |
|-------|----------|
| `python3: command not found` | Install Python 3.11+ |
| `pip: command not found` | Install pip |
| `Permission denied` | Run `chmod +x scripts/*.sh` |
| `genesis_engine not found` | Comment out that line in bootstrap |

### E2E Script Fails

| Error | Solution |
|-------|----------|
| `HELDOUT_SUITES_DIR is required` | Set environment variable |
| `Module not found` | Run bootstrap first |
| `Permission denied` | Check file permissions |

---

## Contributing

When adding new scripts:
1. Add executable permission (`chmod +x`)
2. Include help documentation (`--help` flag)
3. Document in this README
4. Add error handling for missing dependencies

---

## License

See repository root LICENSE file.
