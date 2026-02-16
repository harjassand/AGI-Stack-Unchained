"""Generate a deterministic capacity filler task stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--out", default="tasks/stream_capacity_filler.jsonl")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as fh:
        for i in range(1, args.n + 1):
            sym = f"cap_fill_{i:06d}"
            task = {
                "task_id": f"CAP_{i:04d}",
                "new_symbol": sym,
                "type": "Int -> Int",
                "allowed_deps": [],
                "specs": [
                    {
                        "kind": "forall",
                        "vars": [{"name": "n", "type": {"tag": "int"}}],
                        "domain": {
                            "int_min": -2,
                            "int_max": 2,
                            "list_max_len": 0,
                            "fun_symbols": [],
                        },
                        "assert": {
                            "tag": "prim",
                            "op": "eq_int",
                            "args": [
                                {"tag": "app", "fn": {"tag": "sym", "name": sym}, "args": [{"tag": "var", "name": "n"}]},
                                {"tag": "var", "name": "n"},
                            ],
                        },
                    }
                ],
            }
            fh.write(json.dumps(task, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
