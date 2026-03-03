# benchmark_suite_sets

> Path: `authority/benchmark_suite_sets`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `anchor_suite_set_v1.json`: JSON contract, config, or artifact.
- `micdrop_anchor_suite_set_v1.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10564205039456103181_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_10646050240228439994_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_11158203696238121938_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_115263103181038160_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_123_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_12791621293112785869_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_13802460363450740402_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_14813559100601098698_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_17461300049777240311_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_178512057557035294_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_287066686630732695_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_4012867327180807471_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_4384153701131113945_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_456_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_6723020109120126629_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_7754119724544166340_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_789_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_790_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_8915874441870607280_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_novelty_seed_9590784750949113058_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_v2_seed_123456789_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_v2_seed_1688823821546474032_suite_set.json`: JSON contract, config, or artifact.
- `micdrop_v2_seed_2715516532031033669_suite_set.json`: JSON contract, config, or artifact.
- ... and 12 more files.

## File-Type Surface

- `json`: 37 files

## Operational Checks

```bash
ls -la authority/benchmark_suite_sets
find authority/benchmark_suite_sets -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/benchmark_suite_sets | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
