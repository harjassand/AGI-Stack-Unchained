"""Generate a fragmentation stress task stream."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def var(name: str) -> dict:
    return {"tag": "var", "name": name}


def sym(name: str) -> dict:
    return {"tag": "sym", "name": name}


def int_lit(value: int) -> dict:
    return {"tag": "int", "value": value}


def prim(op: str, *args: dict) -> dict:
    return {"tag": "prim", "op": op, "args": list(args)}


def app(fn: dict, *args: dict) -> dict:
    return {"tag": "app", "fn": fn, "args": list(args)}


def t_int() -> dict:
    return {"tag": "int"}


def forall(vars_list: list[dict], assert_term: dict, int_min: int = -2, int_max: int = 2) -> dict:
    return {
        "kind": "forall",
        "vars": vars_list,
        "domain": {
            "int_min": int_min,
            "int_max": int_max,
            "list_max_len": 0,
            "fun_symbols": [],
        },
        "assert": assert_term,
    }


def _base_tasks() -> list[dict]:
    n = var("n")
    tasks = [
        {
            "task_id": "F0001",
            "task_group": "fragmentation_stress",
            "certificate_mode": "bounded",
            "new_symbol": "inc",
            "type": "Int -> Int",
            "allowed_deps": [],
            "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym("inc"), n), prim("add", n, int_lit(1))))],
        },
        {
            "task_id": "F0002",
            "task_group": "fragmentation_stress",
            "certificate_mode": "bounded",
            "new_symbol": "add2",
            "type": "Int -> Int",
            "allowed_deps": ["inc"],
            "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym("add2"), n), prim("add", n, int_lit(2))))],
        },
        {
            "task_id": "F0003",
            "task_group": "fragmentation_stress",
            "certificate_mode": "bounded",
            "new_symbol": "add4",
            "type": "Int -> Int",
            "allowed_deps": ["add2"],
            "specs": [forall([{"name": "n", "type": t_int()}], prim("eq_int", app(sym("add4"), n), prim("add", n, int_lit(4))))],
        },
    ]
    return tasks


def generate_tasks(n: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    tasks = _base_tasks()
    idx = len(tasks) + 1
    allowed = ["inc", "add2", "add4"]
    while len(tasks) < n:
        k = rng.randint(3, 9)
        name = f"add_{k}_{idx}"
        n_var = var("n")
        task = {
            "task_id": f"F{idx:04d}",
            "task_group": "fragmentation_stress",
            "certificate_mode": "bounded",
            "new_symbol": name,
            "type": "Int -> Int",
            "allowed_deps": allowed,
            "specs": [
                forall(
                    [{"name": "n", "type": t_int()}],
                    prim("eq_int", app(sym(name), n_var), prim("add", n_var, int_lit(k))),
                )
            ],
        }
        tasks.append(task)
        idx += 1
    return tasks


def write_jsonl(tasks: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for task in tasks:
            fh.write(json.dumps(task, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    tasks = generate_tasks(args.n, seed=args.seed)
    write_jsonl(tasks, Path(args.out))


if __name__ == "__main__":
    main()
