# Contributing

This spec pack is maintained via pull requests. Direct pushes to `main` are not allowed.

## Branching

Use feature branches:

- `schema/*`
- `docs/*`
- `ledger/*`
- `tools/*`
- `phase2/*`

## Required Checks (CI)

All PRs must pass:

- Schema validation (`tools/validate_schema.py`)
- Canonicalization test vectors (`tools/canonicalize.py --verify`)
- Receipt verification (`tools/verify_receipt.py`)
- Ledger simulators (`ledger_sim/*.py`)
- Markdown link check (`tools/check_links.py`)

## Commit Conventions

Use machine-parsable commit prefixes:

- `schema: ...`
- `docs: ...`
- `ledger: ...`
- `tools: ...`
- `test: ...`

Keep commits small and atomic, and ensure tests pass per commit when possible.

## PR Description Template

Include:

- **Normative impact**: breaking / non-breaking / tests only
- **Affected files**: list of files or directories
- **Tests run**: commands executed

## Versioning

- Update `SPEC_VERSION` for any normative change.
- Update `CHANGELOG.md` with a clear summary and migration notes for breaking changes.
- Tag releases as `vMAJOR.MINOR.PATCH`.
