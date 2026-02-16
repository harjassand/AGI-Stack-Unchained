"""Generate distractor module tasks for ledger inflation experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _var(name: str) -> dict:
    return {"tag": "var", "name": name}


def _sym(name: str) -> dict:
    return {"tag": "sym", "name": name}


def _int(value: int) -> dict:
    return {"tag": "int", "value": value}


def _prim(op: str, *args: dict) -> dict:
    return {"tag": "prim", "op": op, "args": list(args)}


def _app(fn: dict, *args: dict) -> dict:
    return {"tag": "app", "fn": fn, "args": list(args)}


def _forall_eq(name: str) -> dict:
    n = _var("n")
    return {
        "kind": "forall",
        "vars": [{"name": "n", "type": {"tag": "int"}}],
        "domain": {"int_min": -1, "int_max": 1, "list_max_len": 0, "fun_symbols": []},
        "assert": _prim("eq_int", _app(_sym(name), n), n),
    }


def make_task(symbol: str, task_id: str) -> dict:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": [symbol],
            "definitions": [
                {
                    "name": symbol,
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": _var("n"),
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [_forall_eq(symbol)],
        },
    }
    return {"task_id": task_id, "module": module, "certificate_mode": "bounded"}


def write_jsonl(tasks: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    tasks = []
    for i in range(1, args.n + 1):
        symbol = f"junk_{i:06d}"
        task_id = f"J{i:06d}"
        tasks.append(make_task(symbol, task_id))
    write_jsonl(tasks, Path(args.out))


if __name__ == "__main__":
    main()
