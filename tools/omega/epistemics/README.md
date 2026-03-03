# epistemics

> Path: `tools/omega/epistemics`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `common_v1.py`: Python module or executable script.
- `re0_capture_audio_window_v1.py`: Python module or executable script.
- `re0_capture_camera_live_v1.py`: Python module or executable script.
- `re0_capture_video_pinned_decode_v1.py`: Python module or executable script.
- `re0_capture_vision_fixed_cadence_v1.py`: Python module or executable script.
- `re0_chunk_bytestream_rabin_v1.py`: Python module or executable script.
- `re0_fetch_web_live_v1.py`: Python module or executable script.
- `re0_fetch_web_v1.py`: Python module or executable script.
- `re0_infer_mob_v1.py`: Python module or executable script.
- `re0_infer_vision_mob_v2.py`: Python module or executable script.
- `re0_instruction_strip_v1.py`: Python module or executable script.
- `re0_outbox_episode_v1.py`: Python module or executable script.
- `re0_segment_html_live_v1.py`: Python module or executable script.
- `re0_segment_html_v1.py`: Python module or executable script.
- `re0_segment_vision_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 16 files

## Operational Checks

```bash
ls -la tools/omega/epistemics
find tools/omega/epistemics -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/epistemics | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
