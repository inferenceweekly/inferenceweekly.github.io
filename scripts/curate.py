#!/usr/bin/env python3
"""Collect candidate links for the next issue from curation/sources.yml.

Writes a Markdown checklist (articles, papers, videos, repo releases and links
newly added to curated GitHub lists) that the weekly GitHub Action posts as a
GitHub issue for triage.

A source URL can be a feed, or a normal web page such as a blog index or a
YouTube channel (https://www.youtube.com/@handle): the script then finds the
page's RSS/Atom link by itself.

Usage:
    python scripts/curate.py                 # last 7 days, print to stdout
    python scripts/curate.py --days 14 -o candidates.md
"""
import argparse
import calendar
import datetime as dt
import html
import os
import pathlib
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "curation" / "sources.yml"
USER_AGENT = "InferenceWeeklyCurator/1.0 (+https://inferenceweekly.github.io)"
PRERELEASE = re.compile(r"(rc\d*|nightly|dev\d*|alpha|beta|pre-?release)\b", re.I)
MAX_RELEASES_PER_REPO = 2
MAX_ITEMS_PER_FEED = 15
HTTP_TIMEOUT = 20

FEED_LINK = re.compile(
    r"<link\b[^>]*\btype=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", re.I
)
HREF = re.compile(r"\bhref=[\"']([^\"']+)[\"']", re.I)
YT_CHANNEL_ID = re.compile(r'"(?:externalId|channelId)"\s*:\s*"(UC[\w-]{22})"')
YT_CANONICAL = re.compile(r"/channel/(UC[\w-]{22})")
MD_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)\)")


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


def http_get(url: str, **kwargs) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en", **kwargs.pop("headers", {})}
    cookies = {"CONSENT": "YES+1", "SOCS": "CAI"}  # skip YouTube's cookie-consent page
    return requests.get(url, headers=headers, cookies=cookies, timeout=HTTP_TIMEOUT, **kwargs)


def discover_feed(page_url: str) -> str | None:
    """Find the RSS/Atom feed advertised by a web page (blog index, YouTube channel...)."""
    response = http_get(page_url)
    response.raise_for_status()
    page = response.text
    for tag in FEED_LINK.findall(page):
        if href := HREF.search(tag):
            return urllib.parse.urljoin(response.url, html.unescape(href.group(1)))
    host = urllib.parse.urlparse(response.url).netloc
    if "youtube.com" in host:
        if match := (YT_CHANNEL_ID.search(page) or YT_CANONICAL.search(page)):
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={match.group(1)}"
    return None


def load_feed(url: str):
    """Parse url as a feed; if it's a web page instead, discover its feed and parse that."""
    feed = feedparser.parse(url, agent=USER_AGENT)
    if feed.entries:
        return feed, None
    try:
        found = discover_feed(url)
    except requests.RequestException as exc:
        return None, f"could not open page ({exc.__class__.__name__})"
    if not found:
        reason = feed.get("bozo_exception") or "no entries and no feed link on the page"
        return None, f"no feed found ({reason})"
    feed = feedparser.parse(found, agent=USER_AGENT)
    if feed.get("bozo") and not feed.entries:
        return None, f"found {found} but could not read it"
    return feed, None


def fetch(source: dict, since: dt.datetime, keywords: list[str]) -> tuple[dict, list, str | None]:
    feed, error = load_feed(source["url"])
    if error:
        return source, [], error
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


def github_api(endpoint: str, **params):
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    response = http_get(f"https://api.github.com/{endpoint}", headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def raw_file(repo: str, ref: str, path: str) -> str:
    response = http_get(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}")
    response.raise_for_status()
    return response.text


def links_in(markdown: str) -> dict[str, str]:
    """url -> link text for every non-image Markdown link."""
    return {url.rstrip("/"): text.strip() for text, url in MD_LINK.findall(markdown)}


def fetch_list_additions(entry: dict, since: dt.datetime) -> tuple[dict, list, str | None]:
    """Links added to a curated list (a GitHub repo's README) since `since`."""
    repo = entry["repo"]
    path = entry.get("path", "README.md")
    source = {"name": entry.get("name", repo), "url": f"https://github.com/{repo}"}
    try:
        branch = github_api(f"repos/{repo}")["default_branch"]
        before = github_api(
            f"repos/{repo}/commits", sha=branch, path=path,
            until=since.strftime("%Y-%m-%dT%H:%M:%SZ"), per_page=1,
        )
        now = links_in(raw_file(repo, branch, path))
        old = links_in(raw_file(repo, before[0]["sha"], path)) if before else {}
    except (requests.RequestException, KeyError, IndexError) as exc:
        return source, [], f"could not compare {path} ({exc.__class__.__name__})"
    added = [url for url in now if url not in old]
    items = [
        {"title": clean(now[url], 140), "link": url, "date": "", "summary": ""}
        for url in added[:MAX_ITEMS_PER_FEED]
    ]
    return source, items, None


def render(sections: dict[str, list], errors: list[str], since: dt.datetime) -> str:
    today = dt.date.today().isoformat()
    total = sum(len(items) for groups in sections.values() for _, items in groups)
    out = [
        f"Candidates published since **{since.date().isoformat()}** "
        f"(generated {today}, {total} items).",
        "",
        "Tick what goes into the next issue and paste any extra links as comments. "
        "When you're done, run **Actions → Compile issue → Run workflow**: it opens a "
        "pull request with the draft issue for you to finish.",
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
        results = list(pool.map(lambda l: fetch_list_additions(l, since), config.get("lists") or []))
        sections["New in curated lists"] = [(s, items) for s, items, _ in results]
        errors += [f"{s['name']}: {e}" for s, _, e in results if e]

    markdown = render(sections, errors, since)
    if args.output:
        pathlib.Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
