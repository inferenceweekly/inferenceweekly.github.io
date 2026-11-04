#!/usr/bin/env python3
"""Create the next issue file from templates/issue.md.

Usage:
    python scripts/new_issue.py "Speculative decoding goes mainstream"
    python scripts/new_issue.py "Title" --date 2026-11-16
"""
import argparse
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ISSUES = ROOT / "docs" / "issues"
TEMPLATE = ROOT / "templates" / "issue.md"


def next_monday(today: dt.date) -> dt.date:
    days = (7 - today.weekday()) % 7 or 7
    return today + dt.timedelta(days=days)


def next_number() -> int:
    numbers = [
        int(m.group(1))
        for p in ISSUES.rglob("*.md")
        if (m := re.search(r"^number:\s*(\d+)\s*$", p.read_text(encoding="utf-8"), re.M))
    ]
    return max(numbers, default=-1) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Issue title / theme")
    parser.add_argument("--date", help="Publish date YYYY-MM-DD (default: next Monday)")
    args = parser.parse_args()

    date = dt.date.fromisoformat(args.date) if args.date else next_monday(dt.date.today())
    number = next_number()
    target = ISSUES / f"{date:%Y}" / f"{date:%m}" / f"{date.isoformat()}.md"
    if target.exists():
        print(f"Already exists: {target}", file=sys.stderr)
        return 1

    body = TEMPLATE.read_text(encoding="utf-8").format(
        date=date.isoformat(), number=number, title=args.title
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    print(target.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
