#!/usr/bin/env python3
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\]\(([^)]+)\)")


def iter_markdown_files():
    yield ROOT / "README.md"
    for path in (ROOT / "docs").glob("*.md"):
        yield path
    for path in (ROOT / "ledger_sim").glob("*.md"):
        yield path


def is_external(link: str) -> bool:
    return link.startswith("http://") or link.startswith("https://") or link.startswith("mailto:")


def main() -> int:
    errors = []
    for md_path in iter_markdown_files():
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            link = match.group(1).strip()
            if not link or link.startswith("#") or is_external(link):
                continue
            link = link.split("#", 1)[0]
            target = (md_path.parent / link).resolve()
            if not target.exists():
                errors.append(f"{md_path}: missing link target {link}")

    if errors:
        for err in errors:
            print(err)
        return 1

    print("markdown link check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
