#!/usr/bin/env python3
"""Deterministic Oracle ladder pack generator (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import string
import sys
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj

_KIND_MAP = {"list": "LIST_INT", "string": "STRING"}
_TOKEN_POOL = ["", "a", "b", "c", "ab", "bc", "ca", "aa", "bb", "cc", "abc", "cab"]


def _ensure_u64(value: int) -> int:
    out = int(value)
    if out < 0 or out >= (1 << 64):
        raise ValueError("seed_u64 must be in [0, 2^64)")
    return out


def _seed_rng(seed_u64: int, kind: str, n_tasks: int) -> random.Random:
    digest = hashlib.sha256(f"oracle_packgen_v1|{int(seed_u64)}|{kind}|{int(n_tasks)}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _rand_list(rng: random.Random) -> list[int]:
    length = rng.randint(5, 40)
    return [rng.randint(-200, 200) for _ in range(length)]


def _stable_uniq(xs: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for row in xs:
        if row in seen:
            continue
        seen.add(row)
        out.append(int(row))
    return out


def _prefix_sum(xs: list[int]) -> list[int]:
    out: list[int] = []
    acc = 0
    for row in xs:
        acc += int(row)
        out.append(int(acc))
    return out


def _clamp_take(xs: list[Any], n: int) -> list[Any]:
    count = max(0, int(n))
    return list(xs[:count])


def _clamp_drop(xs: list[Any], n: int) -> list[Any]:
    count = max(0, int(n))
    return list(xs[count:])


def _mk_list_transform(rng: random.Random) -> tuple[Callable[[list[int]], Any], str]:
    family = int(rng.randint(1, 7))

    if family == 1:
        return (lambda xs: sorted(list(xs))), "L1"

    if family == 2:
        return (lambda xs: list(reversed(xs))), "L2"

    if family == 3:
        return (lambda xs: _stable_uniq(list(xs))), "L3"

    if family == 4:
        m = int(rng.randint(2, 9))
        r = int(rng.randint(0, m - 1))
        k = int(rng.randint(-20, 20))

        def _f(xs: list[int]) -> list[int]:
            return [int(row + k) for row in xs if row % m == r]

        return _f, f"L4_m{m}_r{r}_k{k}"

    if family == 5:
        k = int(rng.choice([-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6]))

        def _f(xs: list[int]) -> int:
            return int(sum(int(row * k) for row in xs))

        return _f, f"L5_k{k}"

    if family == 6:
        n = int(rng.randint(0, 64))
        mode_take = bool(rng.randint(0, 1) == 0)

        def _f(xs: list[int]) -> list[int]:
            ps = _prefix_sum(list(xs))
            return _clamp_take(ps, n) if mode_take else _clamp_drop(ps, n)

        return _f, f"L6_t{1 if mode_take else 0}_n{n}"

    n = int(rng.randint(0, 80))
    mode_take = bool(rng.randint(0, 1) == 0)

    def _f(xs: list[int]) -> list[int]:
        merged = list(xs) + list(reversed(xs))
        return _clamp_take(merged, n) if mode_take else _clamp_drop(merged, n)

    return _f, f"L7_t{1 if mode_take else 0}_n{n}"


def _rand_str(rng: random.Random) -> str:
    length = rng.randint(0, 80)
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(length))


def _slice_str(s: str, i: int, j: int) -> str:
    lo = max(0, min(int(i), len(s)))
    hi = max(0, min(int(j), len(s)))
    if hi < lo:
        hi = lo
    return s[lo:hi]


def _rand_token(rng: random.Random, *, min_len: int, max_len: int) -> str:
    choices = [row for row in _TOKEN_POOL if min_len <= len(row) <= max_len]
    if not choices:
        return ""
    return str(rng.choice(choices))


def _enc_token(token: str) -> str:
    text = str(token)
    return "e" if text == "" else text


def _mk_string_transform(rng: random.Random) -> tuple[Callable[[str], Any], str]:
    family = int(rng.randint(1, 5))

    if family == 1:
        i = int(rng.randint(-10, 90))
        j = int(rng.randint(-10, 90))
        return (lambda s: _slice_str(s, i, j)), f"S1_i{i}_j{j}"

    if family == 2:
        prefix = _rand_token(rng, min_len=0, max_len=5)
        suffix = _rand_token(rng, min_len=0, max_len=5)
        mode = int(rng.randint(0, 2))

        if mode == 0:
            return (lambda s: prefix + s), f"S2_m0_p{_enc_token(prefix)}_s{_enc_token(suffix)}"
        if mode == 1:
            return (lambda s: s + suffix), f"S2_m1_p{_enc_token(prefix)}_s{_enc_token(suffix)}"
        return (lambda s: prefix + s + suffix), f"S2_m2_p{_enc_token(prefix)}_s{_enc_token(suffix)}"

    if family == 3:
        old = _rand_token(rng, min_len=1, max_len=3)
        new = _rand_token(rng, min_len=0, max_len=3)
        return (lambda s: s.replace(old, new)), f"S3_o{_enc_token(old)}_n{_enc_token(new)}"

    if family == 4:
        sub = _rand_token(rng, min_len=1, max_len=4)
        return (lambda s: int(s.find(sub))), f"S4_u{_enc_token(sub)}"

    prefix = _rand_token(rng, min_len=0, max_len=3)
    suffix = _rand_token(rng, min_len=0, max_len=3)
    old = _rand_token(rng, min_len=1, max_len=3)
    new = _rand_token(rng, min_len=0, max_len=3)
    sub = _rand_token(rng, min_len=1, max_len=4)
    mode = int(rng.randint(0, 2))

    def _f(s: str) -> int:
        if mode == 0:
            c = prefix + s
        elif mode == 1:
            c = s + suffix
        else:
            c = prefix + s + suffix
        return int(c.replace(old, new).find(sub))

    return _f, f"S5_m{mode}_p{_enc_token(prefix)}_s{_enc_token(suffix)}_o{_enc_token(old)}_n{_enc_token(new)}_u{_enc_token(sub)}"


def _mk_examples_list(rng: random.Random, n: int, fn: Callable[[list[int]], Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(out) < n:
        inp = _rand_list(rng)
        key = json.dumps(inp, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"in": inp, "out": fn(inp)})
    return out


def _mk_examples_string(rng: random.Random, n: int, fn: Callable[[str], Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(out) < n:
        inp = _rand_str(rng)
        if inp in seen:
            continue
        seen.add(inp)
        out.append({"in": inp, "out": fn(inp)})
    return out


def _generate_tasks(kind: str, seed_u64: int, n_tasks: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kind_norm = str(kind).strip().lower()
    if kind_norm not in _KIND_MAP:
        raise ValueError("kind must be list|string")
    rng = _seed_rng(seed_u64, kind_norm, n_tasks)

    inputs_tasks: list[dict[str, Any]] = []
    hidden_tasks: list[dict[str, Any]] = []
    for idx in range(int(n_tasks)):
        if kind_norm == "list":
            fn, spec = _mk_list_transform(rng)
            public = _mk_examples_list(rng, 8, fn)
            hidden = _mk_examples_list(rng, 32, fn)
            kind_value = "LIST_INT"
        else:
            fn, spec = _mk_string_transform(rng)
            public = _mk_examples_string(rng, 8, fn)
            hidden = _mk_examples_string(rng, 32, fn)
            kind_value = "STRING"
        task_id = f"ORACLE_{kind_norm.upper()}_{int(seed_u64)}_{idx:04d}_{spec}"

        inputs_tasks.append(
            {
                "id": task_id,
                "kind": kind_value,
                "public_examples": public,
                "meta": {"max_ast_nodes_u32": 64},
            }
        )
        hidden_tasks.append(
            {
                "id": task_id,
                "hidden_examples": hidden,
            }
        )

    return inputs_tasks, hidden_tasks


def _write_pack(out_dir: Path, payload_no_id: dict[str, Any], schema_version: str) -> tuple[str, Path]:
    payload = dict(payload_no_id)
    payload.pop("pack_id", None)
    pack_id = canon_hash_obj(payload)
    payload["pack_id"] = pack_id
    digest = str(pack_id).split(":", 1)[1]
    path = out_dir / f"sha256_{digest}.{schema_version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)
    return str(pack_id), path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oracle_packgen_v1")
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--n_tasks", type=int, default=256)
    parser.add_argument("--out_dir", default="authority/holdouts/packs")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    seed_u64 = _ensure_u64(int(args.seed_u64))
    kind = str(args.kind).strip().lower()
    if kind not in _KIND_MAP:
        raise ValueError("--kind must be list|string")
    n_tasks = int(args.n_tasks)
    if n_tasks <= 0:
        raise ValueError("--n_tasks must be positive")

    out_dir = Path(str(args.out_dir)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs_tasks, hidden_tasks = _generate_tasks(kind=kind, seed_u64=seed_u64, n_tasks=n_tasks)
    inputs_payload = {
        "schema_version": "oracle_task_inputs_pack_v1",
        "pack_id": "sha256:" + ("0" * 64),
        "tasks": inputs_tasks,
    }
    hidden_payload = {
        "schema_version": "oracle_hidden_tests_pack_v1",
        "pack_id": "sha256:" + ("0" * 64),
        "tasks": hidden_tasks,
    }

    inputs_id, inputs_path = _write_pack(out_dir, inputs_payload, "oracle_task_inputs_pack_v1")
    hidden_id, hidden_path = _write_pack(out_dir, hidden_payload, "oracle_hidden_tests_pack_v1")

    summary = {
        "schema_version": "oracle_packgen_v1_summary",
        "seed_u64": int(seed_u64),
        "kind": str(kind),
        "n_tasks": int(n_tasks),
        "inputs_pack_id": str(inputs_id),
        "hidden_tests_pack_id": str(hidden_id),
        "inputs_pack_relpath": inputs_path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix(),
        "hidden_tests_pack_relpath": hidden_path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix(),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
