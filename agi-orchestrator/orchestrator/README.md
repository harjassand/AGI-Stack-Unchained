# orchestrator

> Path: `agi-orchestrator/orchestrator`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `boundless_math_v8_0/`: component subtree.
- `daemon_v6_0/`: component subtree.
- `daemon_v7_0/`: component subtree.
- `daemon_v8_0_math/`: component subtree.
- `domains/`: component subtree.
- `eval/`: component subtree.
- `proposer/`: component subtree.
- `sas_math_v11_0/`: component subtree.
- `superego_v7_0/`: component subtree.
- `superego_v8_0/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `agent_controller.py`: Python module or executable script.
- `agent_policy.py`: Python module or executable script.
- `agent_transcript.py`: Python module or executable script.
- `cdel_client.py`: Python module or executable script.
- `concept_registry.py`: Python module or executable script.
- `context_pack.py`: Python module or executable script.
- `counterexamples.py`: Python module or executable script.
- `embedding.py`: Python module or executable script.
- `heldout_rotation.py`: Python module or executable script.
- `ledger_view.py`: Python module or executable script.
- `llm_backend.py`: Python module or executable script.
- `llm_backend_replay.py`: Python module or executable script.
- `llm_cache.py`: Python module or executable script.
- `llm_call_log.py`: Python module or executable script.
- `llm_limits.py`: Python module or executable script.
- `metrics.py`: Python module or executable script.
- `plan_skill.py`: Python module or executable script.
- `plan_skill_store.py`: Python module or executable script.
- `promote.py`: Python module or executable script.
- `pyut_utils.py`: Python module or executable script.
- `ranking.py`: Python module or executable script.
- `retrieval.py`: Python module or executable script.
- `rsi_daemon_v6_0.py`: Python module or executable script.
- `rsi_daemon_v7_0.py`: Python module or executable script.
- ... and 10 more files.

## File-Type Surface

- `py`: 35 files

## Operational Checks

```bash
ls -la agi-orchestrator/orchestrator
find agi-orchestrator/orchestrator -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/orchestrator | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
