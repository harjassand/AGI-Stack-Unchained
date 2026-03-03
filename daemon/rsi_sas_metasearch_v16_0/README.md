# RSI SAS Metasearch v16.0 Daemon State

Runtime pack and toolchain configuration artifacts for v16.0 metasearch.

## Key Files

- `config/rsi_sas_metasearch_pack_v1.json`: Top-level metasearch pack descriptor.
- `config/toolchain_manifest_py_v1.json`: Python toolchain manifest.
- `config/toolchain_manifest_rust_v1.json`: Rust toolchain manifest.
- `config/trace_corpus/science_trace_corpus_suitepack_dev_v1.json`: Dev trace corpus suitepack.

## Contract Notes

- Pack and manifest hashes are replay-critical and should remain stable once promoted.
- Keep version suffixes explicit (`*_v1`) to preserve verifier compatibility.
