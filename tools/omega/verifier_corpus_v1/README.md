# Verifier Corpus v1

Store hash-addressed Omega daemon `state` directories here for verifier equivalence checks.

Expected layout:

- `tools/omega/verifier_corpus_v1/<case_id>/state/`
- `tools/omega/verifier_corpus_v1/<case_id>/meta.json` (optional)

The `verifier_equivalence_suite_v1.py` tool scans this directory recursively for `state` dirs.

Current layout also includes:

- `tools/omega/verifier_corpus_v1/INDEX.json`: deterministic case index.
- `tools/omega/verifier_corpus_v1/<case_id>/state`: symlink to a concrete archived `runs/.../state` directory.
- `tools/omega/verifier_corpus_v1/<case_id>/meta.json`: case metadata and source path.
