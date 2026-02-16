"""Interleave two JSONL task streams deterministically."""

from __future__ import annotations

import argparse
from pathlib import Path


def read_lines(path: Path) -> list[str]:
    lines = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                lines.append(line)
    return lines


def write_lines(lines: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def interleave(main: list[str], extra: list[str], k: int) -> list[str]:
    out: list[str] = []
    extra_idx = 0
    for line in main:
        out.append(line)
        for _ in range(k):
            if extra_idx >= len(extra):
                break
            out.append(extra[extra_idx])
            extra_idx += 1
    if extra_idx < len(extra):
        out.extend(extra[extra_idx:])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", required=True)
    parser.add_argument("--extra", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pattern", choices=["before", "after", "interleave"], required=True)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    main_lines = read_lines(Path(args.main))
    extra_lines = read_lines(Path(args.extra))

    if args.pattern == "before":
        merged = extra_lines + main_lines
    elif args.pattern == "after":
        merged = main_lines + extra_lines
    else:
        merged = interleave(main_lines, extra_lines, args.k)

    write_lines(merged, Path(args.out))


if __name__ == "__main__":
    main()
