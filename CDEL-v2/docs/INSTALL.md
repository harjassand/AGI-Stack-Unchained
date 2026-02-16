# Install

Recommended Python: 3.11+

Minimal runtime (CLI + core library):

```bash
python -m pip install -e ".[core]"
```

Developer/test install:

```bash
python -m pip install -e ".[dev]"
```

Notes:

- Editable installs generate `*.egg-info` metadata (ignored by this repo).
- Run scripts from the repo root; do not rely on packaged metadata.

Reproducible installs (optional):

- Use a lock file tool (e.g., `pip-compile` or `uv pip compile`) to pin exact
  versions for your environment.

