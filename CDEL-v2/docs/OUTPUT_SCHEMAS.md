# Output Schemas

This file defines the stable JSON output shapes used by external tooling.

All outputs include a top-level `schema_version` integer. Any breaking
change requires bumping the version and adding compatibility notes here.

## Solve Suite Scoreboard (`suite_scoreboard.json`)

Schema version: 1

Required top-level fields:

- `schema_version`
- `meta` (object: `git_commit`, `config_hash`, `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`)
- `config` (object: suite/limit/episodes/budget/max_candidates/max_context_symbols/strategy/distractor fields)
- `tasks` (array of per-task records with `task_id`, `concept`, `family`, `accepted`, `attempts`)
- `summary` (object: `processed`, `solved`, `rejected`, `reuse_ratio`, `avg_closure_symbols`,
  `avg_concept_candidates`, `candidates_per_concept`, `closure_symbols_dist`,
  `active_candidates`, `inactive_candidates`)

## Solve Suite Ablations (`ablations_results.json`)

Schema version: 1

Required top-level fields:

- `schema_version`
- `meta` (object: `git_commit`, `config_hash`, `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`)
- `config` (object: suite/limit/strategies/episodes/max_candidates/budget_per_task/max_context_symbols/deterministic)
- `strategies` (object keyed by strategy name; each value includes `report` and `summary`)
- `summary` (object keyed by strategy name with solve metrics)

## Solve Stress (`stress_results.json`)

Schema version: 1

Required top-level fields:

- `schema_version`
- `meta` (object: `git_commit`, `config_hash`, `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`)
- `config` (object: tasks/episodes/budget/strategy/reuse_every)
- `steps` (array of per-step records with `task_id`, `accepted`, `alpha`, `modules`, `budget_remaining`)
- `summary` (object: `processed`, `accepted`, `rejected`, `reuse_ratio`, `avg_closure_symbols`)

## Consolidation Report (`consolidation_report.json`)

Schema version: 1

Required top-level fields:

- `schema_version`
- `meta` (object: `git_commit`, `config_hash`, `eval_harness_id`, `eval_harness_hash`, `eval_suite_hash`)
- `concept` (string)
- `policy` (string)
- `topk` (int)
- `active_symbol` (string or null)
- `summary` (object: `candidates`, `active`, `inactive`)
- `ranked` (array of candidate rows with `symbol`, `module_hash`, `active`,
  `closure_symbols`, `alpha_i`, `threshold`, `evalue`, `margin`)

