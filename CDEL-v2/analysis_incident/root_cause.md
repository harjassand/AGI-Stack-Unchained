# Root Cause: duplicate module hash in order.log

## Incident summary

Run: `runs_full/distractor_before`  
Symptom: duplicate consecutive hash in `ledger/order.log` leads to symbol redefinition during audit:

```
audit failed: fast: module 174 symbol redefinition: junk_000173; full: module 174 symbol redefinition: junk_000173
```

## Evidence

- Duplicate consecutive hashes at lines 173–174 in `runs_full/distractor_before/ledger/order.log`.
- The duplicated hash resolves to a payload whose `new_symbols` contains `junk_000173` (redefinition).

## Root cause classification

**A/C (idempotency / exactly-once bug)**: the same payload hash was appended twice because the append step is not idempotent and is not protected by a “already appended” check.

### Code references

- `cdel/ledger/storage.py:44–48`  
  `append_order_log()` appends blindly with no idempotency check or lock.
- `cdel/ledger/verifier.py:170–190`  
  `commit_module()` appends the hash before updating the SQLite index.
- `cdel/bench/experiment.py:381–386`  
  `STATUS.json` is written via temp-file replace. A prior failure shows that this write can fail
  (`STATUS.json.tmp` missing), allowing resume to re-run a task even after the ledger append.

### Mechanism

If a run crashes **after** `append_order_log()` but **before** index update or status write, a resume can
re-run the same task. Because the SQLite index may not contain the symbol yet, freshness checks pass,
and the same payload hash is appended again. This creates a duplicate entry in `order.log` and a symbol
redefinition in the audit pass.

## Minimal reproducer (conceptual)

1. Commit a module (hash appended).
2. Simulate crash before SQLite/index update and status write.
3. Resume the same task; freshness check passes (index missing).
4. Append the same payload hash again.

## Why tests did not catch it

There was no test asserting that `order.log` is exactly-once/idempotent, and audits were optional.
Resume logic was not covered by an “append twice” safety test.
