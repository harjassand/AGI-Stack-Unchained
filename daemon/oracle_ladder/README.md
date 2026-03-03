# Oracle Ladder State

Versioned operator-bank snapshots for oracle evolution and replay.

## Files

- `operator_bank_active.json`: Current active operator bank (`oracle_operator_bank_v1`).
- `sha256_*.oracle_operator_bank_v1.json`: Historical, hash-addressed operator bank snapshots.

## Contract

- Snapshot filenames embed the canonical SHA256 of the payload identity.
- Active bank changes should happen by pointer/value update to a valid bank artifact.
- Historical snapshots should remain immutable after publication.

## Typical Checks

```bash
ls daemon/oracle_ladder | head
cat daemon/oracle_ladder/operator_bank_active.json
```

Use this directory to audit oracle operator lineage across ticks and runs.
