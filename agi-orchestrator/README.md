# agi-orchestrator

Untrusted campaign orchestrator layer for AGI Stack that proposes, validates, evaluates, and promotes CDEL modules under sealed- evaluation gates.

This package is the implementation behind the `rsi_agi_orchestrator_*` campaigns and supports standalone orchestration runs for local candidate development.

## Scope and role in the stack

- **Trust layer**: RE3/RE2 boundary (untrusted proposer, trusted CDEL verification).
- **Primary function**: generate typed candidates, run candidate-level validation + dev evaluation, run heldout/safety stat-cert gates, then emit CDEL commit/adopt operations.
- **Execution surface**: CLI at `scripts/run_orchestrator.py` and reusable modules under `orchestrator/`.

## Repository map

- `orchestrator/`
  - Core loop, candidate types, proposers, eval wrappers, CDEL adapter, manifest/scoreboard writers.
- `scripts/`
  - CLI wrappers, smoke suites, bootstrap scripts, suite mining helpers.
- `configs/`
  - Sealed dev/heldout (and safety) TOML configs keyed by domain.
- `suites/`
  - Hash-pointer files for currently approved dev sets.
- `sealed_suites/`
  - Content-addressed dev suites used by local validation.
- `constraints/`
  - Constraint specs used for optional safety channels.
- `docs/`
  - Suite growth/rotation policy docs.
- `tests/`
  - Deterministic regression and safety unit tests for proposers, validation, eval contract, and replay behaviors.

## High-level pipeline

1. **Workspace bootstrap**
   - Ensures `root_dir` exists and initializes a local CDEL workspace if needed.
2. **Concept + oracle context**
   - Resolves baseline/oracle symbols and function type signature.
3. **Context retrieval**
   - Loads top-k context symbols for prompt/candidate generation.
4. **Candidate generation**
   - Template proposer (default), repair proposer, optional LLM proposer, optional agent proposer.
5. **Validation + dedup**
   - JSON schema + structural limits + duplicate hash filtering.
6. **Dev eval**
   - Runs dev evaluation and captures counterexamples.
7. **Ranking**
   - Sort order: higher `diff_sum`, then lower AST nodes, then lower `new_symbols` count.
8. **Heldout (and optional safety) certs**
   - Requests stat cert for heldout and safety channels through CDEL worker.
9. **Commit/adopt**
   - Builds module + adoption payloads and executes CDEL `commit` then `adopt`.
10. **Artifact emission**
    - Writes `manifest.json`, `scoreboard.json`, and per-candidate sub-artifacts.

Run command prints the resulting `run_dir` path on success.

## CLI usage

```bash
python scripts/run_orchestrator.py --help
```

### Required execution inputs

- `--root <path>`: CDEL workspace root.
- Either:
  - `--domain <domain_id>` and optional overrides, **or**
  - explicit `--concept`, `--oracle`, `--dev-config`, `--heldout-config`.

## CLI flags

- `--root` (required)
- `--domain` (optional): auto-load defaults from domain package.
- `--concept` (optional with domain mode)
- `--oracle` (optional with domain mode)
- `--dev-config`
- `--heldout-config`
- `--heldout-suites-dir` (optional)
- `--safety-config` (optional)
- `--safety-suites-dir` (optional)
- `--constraints-spec` (optional)
- `--seed-key` (default `sealed-seed`)
- `--min-dev-diff-sum` (default `1`)
- `--max-attempts` (default `1`)
- `--max-heldout-attempts` (default `1`)
- `--max-context-symbols` (default `20`)
- `--max-counterexamples` (default `3`)
- `--proposers` (default `template,repair`)
- `--run-id` (optional fixed output folder name)
- `--runs-dir` (default `runs`)
- `--baseline` (optional explicit baseline symbol override)
- `--rng-seed` (default `0`)

Proposer list entries are comma-separated and interpreted case-insensitively. Recognized names are:
- `template`
- `repair`
- `llm`
- `agent`

### Useful one-liners

```bash
# Direct concept run
python scripts/run_orchestrator.py \
  --root ./tmp-workspace \
  --concept algo.is_even \
  --oracle is_even_oracle \
  --dev-config configs/sealed_io_dev.toml \
  --heldout-config configs/sealed_io_heldout.toml \
  --heldout-suites-dir sealed_suites \
  --runs-dir runs
```

```bash
# Domain run with presets
python scripts/run_orchestrator.py \
  --root ./tmp-workspace \
  --domain io-algorithms-v1 \
  --dev-config configs/sealed_io_dev.toml \
  --heldout-config configs/sealed_io_heldout.toml \
  --heldout-suites-dir sealed_suites \
  --proposers template,repair,llm \
  --max-attempts 3
```

## Domain presets

- `env-gridworld-v1`
- `io-algorithms-v1`
- `python-ut-v1`

If `--domain` is used, concept/oracle/baseline/config defaults are loaded from that domain module.

## LLM backend configuration

`orchestrator.run` supports LLM-backed proposal through proposer `llm`.

- `ORCH_LLM_BACKEND`
  - `mock` (default)
  - `replay`
  - `openai_replay`
  - `anthropic_replay`
  - `openai_harvest`
  - `anthropic_harvest`
  - `mlx`
- `ORCH_LLM_REPLAY_PATH` (required for replay/harvest modes)
- `ORCH_LLM_CACHE_DIR` (optional prompt/response cache directory)
- `ORCH_LLM_MOCK_RESPONSE` and `ORCH_LLM_MOCK_MODE`
- `ORCH_OPENAI_MODEL`, `ORCH_ANTHROPIC_MODEL`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- `ORCH_MLX_MODEL`, `ORCH_MLX_REVISION`, `ORCH_MLX_ADAPTER_PATH`, `ORCH_MLX_TRUST_REMOTE_CODE`
- `ORCH_LLM_SEED_U64`
- `ORCH_LLM_MAX_PROMPT_CHARS`, `ORCH_LLM_MAX_RESPONSE_CHARS`, `ORCH_LLM_MAX_CALLS`
- Harvest backends require `ORCH_LLM_LIVE_OK=1`.

Gemini backends are removed. Legacy `gemini_*` backend selection fails closed.

A per-run backend log is emitted under manifest `llm.calls` as hashes (`prompt_hash`, `response_hash`, cache hit, index).

## Candidate and validation contracts

The candidate payload must include required lists/fields and satisfy:
- `new_symbols`: non-empty list
- `definitions`: non-empty list
- `concepts`: list
- length limits from active `validation_limits`

The default validation limits are:
- `max_new_symbols=1`
- `max_ast_nodes=50`
- `max_ast_depth=20`

For LLM proposer and repair flows, proposer limits are also capped by
`max_new_symbols`/`max_ast_nodes` and can be constrained further by domain overrides.

## Config files and suite policy

Sealed config files are TOML and minimally require:
- `sealed.eval_harness_id`
- `sealed.eval_harness_hash`
- `sealed.eval_suite_hash`
- `sealed.episodes`

Common configs are under `configs/` with names like:
- `sealed_io_dev.toml`
- `sealed_io_heldout.toml`
- `sealed_env_dev.toml`
- `sealed_pyut_safety_*` etc.

Suite pointers live in `suites/*_dev_current.json` and must match hashes under `sealed_suites/`.

Safety gate fields are optional and use `--safety-config`, `--safety-suites-dir`, and `--constraints-spec`.

See `agi-orchestrator/docs/suite_growth_and_rotation.md` for sanctioned suite lifecycle practices.

## Output layout

Example run directory: `<runs-dir>/<run-id>/`

- `manifest.json`
  - run metadata
  - `accepted` + `reason`
  - dev/heldout hashes
  - attempts with per-attempt metadata
  - LLM settings and call logs
  - full CDEL command audit log
- `scoreboard.json`
  - aggregate stats from dev eval rows and heldout summary
- `candidates/`
  - one folder per attempt index
  - `candidate.json`
  - `dev_artifacts/`
  - `dev_eval.json`
  - `counterexamples.json`
  - `heldout_request.json` and `heldout_cert.json` when heldout is reached
  - `safety_request.json` and `safety_cert.json` if safety is enabled
  - `module.json`, `adoption.json` for accepted candidates
- `llm_cache/` (when configured)

## Determinism and reproducibility guidance

- Candidate hashing uses canonical JSON encoding.
- Ranked order is deterministic and stable.
- Set `--run-id` for reproducible output paths.
- Use replay backends (`ORCH_LLM_REPLAY_PATH`) for fully deterministic LLM paths.
- Use fixed `--rng-seed` and stable proposal ordering when debugging drift.

## Promotion and gating notes

- Heldout certification is hard-blocking.
- Safety certification is additional hard-blocking when safety inputs are provided.
- If required suite dirs are missing, promotion halts with explicit reasons such as:
  - `heldout_suites_missing`
  - `safety_config_missing`
  - `safety_suites_missing`
  - `constraints_spec_missing`
  - `heldout_issue_failed`
  - `safety_issue_failed`
  - `heldout_below_threshold`
  - `safety_below_threshold`

## Local setup and development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# bootstrap and smoke checks
./scripts/dev_bootstrap.sh
pytest -q
python scripts/check_suite_integrity.py
```

## Smoke entry points

- `./scripts/smoke_orchestrator_io_e2e.sh`
- `./scripts/smoke_orchestrator_env_e2e.sh`
- `./scripts/smoke_orchestrator_tooluse_agent_e2e.sh`
- `./scripts/smoke_orchestrator_io_with_mock_llm.sh`
- `./scripts/smoke_orchestrator_io_with_mock_llm_retry.sh`
- `./scripts/smoke_orchestrator_io_with_replay_backend.sh`
- `./scripts/smoke_orchestrator_pyut_with_replay_backend.sh`
- `./scripts/smoke_orchestrator_llm_budget_exceeded.sh`
- `./scripts/smoke_orchestrator_env_hard_uplift.sh`

## Integration touchpoints in the larger system

- Root `orchestrator/` package exports and wraps these modules for legacy compatibility.
- Campaign `orchestrator/rsi_agi_orchestrator_llm_v1.py` is the Omega-dispatchable CDEL campaign wrapper for this orchestrator.

## Versioning

`agi-orchestrator` metadata is in `agi-orchestrator/pyproject.toml` and currently declares:
- Python `>=3.11`
- dependency on pinned `cdel[sealed]`
- extra `dev` dependency `pytest`
