# benchmark_suites

> Path: `authority/benchmark_suites`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `micdrop_algo_suite_v1.json`: JSON contract, config, or artifact.
- `micdrop_logic_suite_v1.json`: JSON contract, config, or artifact.
- `micdrop_math_suite_v1.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_arith.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_dsl.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_graph.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_numbertheory.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_string.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_arith.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_dsl.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_graph.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_numbertheory.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_string.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_arith.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_dsl.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_graph.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_numbertheory.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_string.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_arith.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_dsl.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_graph.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_numbertheory.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_string.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_123_arith.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_123_dsl.json`: JSON contract, config, or artifact.
- ... and 137 more files.

## File-Type Surface

- `json`: 162 files

## Operational Checks

```bash
ls -la authority/benchmark_suites
find authority/benchmark_suites -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/benchmark_suites | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
