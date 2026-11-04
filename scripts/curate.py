#!/usr/bin/env python3
"""Collect candidate links for the next issue from curation/sources.yml.

Writes a Markdown checklist (articles, papers, videos, repo releases) that the
weekly GitHub Action posts as a GitHub issue for triage.

Usage:
    python scripts/curate.py                 # last 7 days, print to stdout
    python scripts/curate.py --days 14 -o candidates.md
"""
import argparse
import calendar
import datetime as dt
import html
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import feedparser
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "curation" / "sources.yml"
USER_AGENT = "InferenceWeeklyCurator/1.0 (+https://inferenceweekly.github.io)"
PRERELEASE = re.compile(r"(rc\d*|nightly|dev\d*|alpha|beta|pre-?release)\b", re.I)
MAX_RELEASES_PER_REPO = 2
MAX_ITEMS_PER_FEED = 15


def published(entry) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return dt.datetime.fromtimestamp(calendar.timegm(value), tz=dt.timezone.utc)
    return None


def clean(text: str, limit: int = 160) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def matches(entry, keywords: list[str]) -> bool:
    haystack = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    return any(k.lower() in haystack for k in keywords)


def fetch(source: dict, since: dt.datetime, keywords: list[str]) -> tuple[dict, list, str | None]:
    feed = feedparser.parse(source["url"], agent=USER_AGENT)
    if feed.get("bozo") and not feed.entries:
        return source, [], str(feed.get("bozo_exception", "unreadable feed"))
    items = []
    for entry in feed.entries:
        when = published(entry)
        if when and when < since:
            continue
        if source.get("filter") and not matches(entry, keywords):
            continue
        items.append(
            {
                "title": clean(entry.get("title", "(untitled)"), 140),
                "link": entry.get("link", ""),
                "date": when.date().isoformat() if when else "",
                "summary": clean(entry.get("summary", "")),
            }
        )
        if len(items) >= MAX_ITEMS_PER_FEED:
            break
    return source, items, None


def fetch_releases(repo: str, since: dt.datetime) -> tuple[dict, list, str | None]:
    source = {"name": repo, "url": f"https://github.com/{repo}/releases.atom"}
    _, items, error = fetch(source, since, [])
    items = [i for i in items if not PRERELEASE.search(i["title"])][:MAX_RELEASES_PER_REPO]
    return source, items, error


def render(sections: dict[str, list], errors: list[str], since: dt.datetime) -> str:
    today = dt.date.today().isoformat()
    total = sum(len(items) for groups in sections.values() for _, items in groups)
    out = [
        f"Candidates published since **{since.date().isoformat()}** "
        f"(generated {today}, {total} items).",
        "",
        "Tick what goes into the next issue, then run "
        "`python scripts/new_issue.py \"<title>\"` and write it up.",
        "",
    ]
    for heading, groups in sections.items():
        groups = [(s, items) for s, items in groups if items]
        if not groups:
            continue
        out.append(f"## {heading}")
        out.append("")
        for source, items in groups:
            out.append(f"**{source['name']}**")
            out.append("")
            for item in items:
                date = f" · {item['date']}" if item["date"] else ""
                out.append(f"- [ ] [{item['title']}]({item['link']}){date}")
                if item["summary"] and heading != "Repo releases":
                    out.append(f"  <br><sub>{item['summary']}</sub>")
            out.append("")
    if errors:
        out.append("<details><summary>Feeds that failed</summary>")
        out.append("")
        out.extend(f"- {e}" for e in errors)
        out.append("")
        out.append("</details>")
    if total == 0:
        out.append("_No new items found. Check the failed feeds above._")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("-o", "--output", help="Write Markdown here instead of stdout")
    args = parser.parse_args()

    config = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    keywords = config.get("keywords", [])
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)

    feed_groups = {
        "Articles": config.get("articles") or [],
        "Papers": config.get("papers") or [],
        "Videos": config.get("videos") or [],
    }
    sections: dict[str, list] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for heading, sources in feed_groups.items():
            results = list(pool.map(lambda s: fetch(s, since, keywords), sources))
            sections[heading] = [(s, items) for s, items, _ in results]
            errors += [f"{s['name']}: {e}" for s, _, e in results if e]
        results = list(pool.map(lambda r: fetch_releases(r, since), config.get("repos") or []))
        sections["Repo releases"] = [(s, items) for s, items, _ in results]
        errors += [f"{s['name']}: {e}" for s, _, e in results if e]

    markdown = render(sections, errors, since)
    if args.output:
        pathlib.Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
