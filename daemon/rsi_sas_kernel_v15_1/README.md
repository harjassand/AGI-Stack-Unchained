# RSI SAS Kernel v15.1 Daemon State

Runtime configuration and corpus pointers for the v15.1 SAS kernel flow.

## Key Artifact

- `config/brain_corpus/brain_corpus_suitepack_heldout_v1.json`: Heldout brain corpus suitepack descriptor (`brain_corpus_suitepack_v1`).

## Operating Rules

- Keep suitepack descriptors deterministic and schema-versioned.
- Treat this directory as configuration/data state, not executable source.
