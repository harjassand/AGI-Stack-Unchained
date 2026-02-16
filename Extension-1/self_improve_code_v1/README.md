# self_improve_code_v1 (RE3+++)

Deterministic RSI-style meta-optimizer with black-box devscreen and CDEL executors.

Entry points:
- `run.py`: orchestrate a full run.
- `replay/replay_v1.py`: recompute ranking/state from logs only.
- `verify/verify_run_v1.py`: verify hashes/rolling history and candidate IDs.

Config files:
- `run_config_example.json`: real integration template (RE1/RE2).
- `run_config_stub.json`: fully deterministic stub config for local proof runs.

All outputs live under `Extension-1/runs/self_improve_code_v1/<run_id>/`.
