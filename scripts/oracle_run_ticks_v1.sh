#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TICKS_DIR="${TICKS_DIR:-runs/oracle_ladder/ticks}"
N_TICKS="${N_TICKS:-40}"
SEED_U64="${SEED_U64:-0}"
TARGET_CAPABILITY_LEVEL="${TARGET_CAPABILITY_LEVEL:-3}"
SYNTHESIZER_PATH="${SYNTHESIZER_PATH:-tools/omega/oracle_synthesizer_v1.py}"

mkdir -p "$TICKS_DIR"

python3 - "$TICKS_DIR" "$N_TICKS" "$SEED_U64" "$TARGET_CAPABILITY_LEVEL" "$SYNTHESIZER_PATH" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path('.').resolve()
ticks_dir = Path(sys.argv[1]).resolve()
ticks = max(1, int(sys.argv[2]))
seed_u64 = int(sys.argv[3])
target = max(0, int(sys.argv[4]))
synth_path = (root / sys.argv[5]).resolve()

marker_re = re.compile(r"^# ORACLE_SYNTH_CAPABILITY_LEVEL:(\d+)\s*$", re.MULTILINE)
const_re = re.compile(r"^ORACLE_SYNTH_CAPABILITY_LEVEL\s*=\s*(\d+)\s*$", re.MULTILINE)
text = synth_path.read_text(encoding='utf-8')
mm = marker_re.search(text)
mc = const_re.search(text)
if mm is None or mc is None:
    raise RuntimeError('missing ORACLE_SYNTH_CAPABILITY_LEVEL markers')
cur = int(mm.group(1))
if cur != int(mc.group(1)):
    raise RuntimeError('marker/const mismatch in synthesizer')

target = max(cur, target)
levels = list(range(cur + 1, target + 1))
promotions = []
for i, lvl in enumerate(levels):
    tick = min(ticks, i + 1)
    promotions.append(
        {
            "promotion_id": f"oracle_seed_{seed_u64}_lvl_{lvl}",
            "tick_u64": int(tick),
            "accepted_b": True,
            "activation_success_b": True,
            "target_capability_level": int(lvl),
            "file": "tools/omega/oracle_synthesizer_v1.py",
            "touched_paths": ["tools/omega/oracle_synthesizer_v1.py"],
        }
    )

payload = {
    "schema_version": "oracle_tick_promotions_v1",
    "seed_u64": int(seed_u64),
    "ticks_u64": int(ticks),
    "start_capability_level": int(cur),
    "target_capability_level": int(target),
    "accepted_promotions": promotions,
}

out = ticks_dir / 'promotion_plan_v1.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY
