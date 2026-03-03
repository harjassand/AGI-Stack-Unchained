# sealed

> Path: `Extension-1/CDEL/cdel/sealed`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `harnesses/`: component subtree.

## Key Files

- `__init__.py`: Python module or executable script.
- `canon.py`: Python module or executable script.
- `config.py`: Python module or executable script.
- `crypto.py`: Python module or executable script.
- `evalue.py`: Python module or executable script.
- `protocol.py`: Python module or executable script.
- `suites.py`: Python module or executable script.
- `worker.py`: Python module or executable script.

## File-Type Surface

- `py`: 8 files

## Operational Checks

```bash
ls -la Extension-1/CDEL/cdel/sealed
find Extension-1/CDEL/cdel/sealed -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/CDEL/cdel/sealed | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
