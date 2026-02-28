# backup_restore

## Purpose
Operational runbook for backup_restore in single-node APF-SC production mode.

## Primary Commands
1. apfsc_preflight --base-config config/base.toml --profile-config config/profiles/prod_single_node.toml
2. apfscctl --socket "/Library/Application Support/APFSC/run/apfscd.sock" status
3. apfscctl --socket "/Library/Application Support/APFSC/run/apfscd.sock" health

## Notes
- Keep holdout and hidden challenge content sealed.
- Run release qualification before publish.
