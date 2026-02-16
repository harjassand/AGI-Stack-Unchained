# LLM Backends (agi-orchestrator)

This repo supports deterministic LLM usage via a harvest then replay workflow.

## Determinism Model

1. Run with a `*_harvest` backend once to append prompt/response pairs into a replay file.
2. Commit or pin the replay file as a normal artifact (never a secret).
3. Re-run with the matching `*_replay` backend to get byte-for-byte stable outputs.

Never commit API keys.

## Common Env Vars

- `ORCH_LLM_BACKEND`:
  - `mock`
  - `replay`
  - `openai_harvest` | `openai_replay`
  - `anthropic_harvest` | `anthropic_replay`
  - `gemini_harvest` | `gemini_replay`
- `ORCH_LLM_REPLAY_PATH`: path to a JSONL replay file.
  - Required for all `*_harvest` and `*_replay` backends.
  - Required for the generic `replay` backend.
- `ORCH_LLM_LIVE_OK=1`: required for all `*_harvest` backends (fail-closed guardrail).
- `ORCH_LLM_CACHE_DIR` (optional): prompt cache directory.

## OpenAI

- `ORCH_LLM_BACKEND=openai_harvest|openai_replay`
- `ORCH_OPENAI_MODEL=...` (Responses-compatible, typically `gpt-*` or `o*`)
- `OPENAI_API_KEY=...` (harvest only)
- `ORCH_LLM_REPLAY_PATH=...`
- `ORCH_LLM_LIVE_OK=1` (harvest only)

## Anthropic

- `ORCH_LLM_BACKEND=anthropic_harvest|anthropic_replay`
- `ORCH_ANTHROPIC_MODEL=...` (must start with `claude-`)
- `ANTHROPIC_API_KEY=...` (harvest only)
- `ORCH_ANTHROPIC_VERSION=2023-06-01` (optional)
- `ORCH_LLM_REPLAY_PATH=...`
- `ORCH_LLM_LIVE_OK=1` (harvest only)

## Gemini (Google)

- `ORCH_LLM_BACKEND=gemini_harvest|gemini_replay`
- `ORCH_GEMINI_MODEL=...` (must start with `gemini-`)
- `GOOGLE_API_KEY=...` (harvest only)
- `ORCH_LLM_REPLAY_PATH=...`
- `ORCH_LLM_LIVE_OK=1` (harvest only)

