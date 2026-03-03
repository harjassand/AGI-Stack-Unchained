# operators

> Path: `Extension-1/caoe_v1/sleep/operators`

## Mission

Extension layer modules for proposal, generation, and self-improvement capabilities.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `coarse_grain_merge_v1.py`: Python module or executable script.
- `efe_tune_v1_1.py`: Python module or executable script.
- `hysteresis_filter_v1_2.py`: Python module or executable script.
- `latent_reify_v1.py`: Python module or executable script.
- `option_compile_v1_1.py`: Python module or executable script.
- `rate_scale_repeat_option_v1_2.py`: Python module or executable script.
- `render_canonicalize_phi_v1_1.py`: Python module or executable script.
- `stability_latent_detect_v1_1.py`: Python module or executable script.
- `template_extract_v1.py`: Python module or executable script.
- `temporal_denoise_phi_v1_2.py`: Python module or executable script.

## File-Type Surface

- `py`: 10 files

## Operational Checks

```bash
ls -la Extension-1/caoe_v1/sleep/operators
find Extension-1/caoe_v1/sleep/operators -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Extension-1/caoe_v1/sleep/operators | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
