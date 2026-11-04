#!/usr/bin/env python3
"""Turn a curation issue into a draft newsletter issue.

Collects every ticked item ("- [x] [Title](url)") from the curation issue body
and every link posted in its comments, sorts them into Read / Watch / Repos,
and writes docs/issues/YYYY/MM/YYYY-MM-DD.md using the usual front matter.

Usage:
    python scripts/compile_issue.py --body body.md --comments comments.json \
        [--title "This week in inference"] [--date 2026-11-09]

Prints the path of the file it created.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from new_issue import ISSUES, next_monday, next_number  # noqa: E402

TICKED = re.compile(r"^\s*[-*]\s+\[[xX]\]\s+\[(?P<title>[^\]]+)\]\((?P<url>[^)\s]+)\)")
SOURCE = re.compile(r"^\*\*(?P<name>.+?)\*\*\s*$")
SECTION = re.compile(r"^##\s+(?P<name>.+?)\s*$")
MD_LINK = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)")
BARE_URL = re.compile(r"(?<![(\[])\bhttps?://[^\s<>()\]]+")
NOTE = "TODO: one line on why it matters."


def kind_of(url: str, section: str = "") -> str:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    if section == "Videos" or host in {"youtube.com", "youtu.be", "m.youtube.com"}:
        return "watch"
    if section == "Repo releases" or host == "github.com":
        return "repos"
    return "read"


def github_repo(url: str) -> str | None:
    parts = urllib.parse.urlparse(url).path.strip("/").split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def site_name(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def fetch_title(url: str) -> str | None:
    """Best-effort page title for links pasted without one."""
    try:
        import requests
    except ImportError:
        return None
    headers = {"User-Agent": "InferenceWeeklyCurator/1.0 (+https://inferenceweekly.github.io)"}
    try:
        if kind_of(url) == "watch":
            r = requests.get(
                "https://www.youtube.com/oembed",
                params={"url": url, "format": "json"},
                headers=headers,
                timeout=10,
            )
            if r.ok:
                data = r.json()
                return data.get("title"), data.get("author_name")
            return None
        r = requests.get(url, headers=headers, timeout=10)
        match = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
        if match:
            import html

            return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip(), None
    except Exception:
        return None
    return None


def from_body(body: str) -> list[dict]:
    items, section, source = [], "", ""
    for line in body.splitlines():
        if m := SECTION.match(line):
            section, source = m.group("name"), ""
        elif m := SOURCE.match(line):
            source = m.group("name")
        elif m := TICKED.match(line):
            url = m.group("url")
            title = m.group("title")
            kind = kind_of(url, section)
            if kind == "repos" and section == "Repo releases":
                title = f"{source} {title}"  # e.g. "vllm-project/vllm v0.12.0"
                source = ""
            items.append({"title": title, "url": url, "source": source, "kind": kind})
    return items


def from_comments(comments: list[dict], lookup_titles: bool) -> list[dict]:
    items = []
    for comment in comments:
        text = comment.get("body") or ""
        seen_in_md = set()
        for m in MD_LINK.finditer(text):
            seen_in_md.add(m.group("url"))
            items.append(_comment_item(m.group("title"), m.group("url"), lookup_titles=False))
        for m in BARE_URL.finditer(text):
            url = m.group(0).rstrip(".,;:!?")
            if url not in seen_in_md:
                items.append(_comment_item(None, url, lookup_titles))
    return items


def _comment_item(title: str | None, url: str, lookup_titles: bool) -> dict:
    kind = kind_of(url)
    source = ""
    if kind == "repos" and (repo := github_repo(url)):
        title = title or repo
        source = "GitHub"
    if not title and lookup_titles:
        found = fetch_title(url)
        if found:
            title, author = found
            source = author or ""
    return {
        "title": title or url,
        "url": url,
        "source": source or site_name(url),
        "kind": kind,
    }


def dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        key = item["url"].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def render(items: list[dict], date: dt.date, number: int, title: str) -> str:
    def line(item: dict) -> str:
        source = f", *{item['source']}*" if item["source"] else ""
        return f"- **[{item['title']}]({item['url']})**{source}. {NOTE}"

    sections = [
        ("read", ":material-book-open-variant: Read"),
        ("watch", ":material-youtube: Watch"),
        ("repos", ":material-github: Repos"),
    ]
    out = [
        "---",
        f"date: {date.isoformat()}",
        f"number: {number}",
        f'title: "#{number}: {title}"',
        "---",
        "",
        f"# #{number}: {title}",
        "",
        "TODO: one-sentence summary of this week's theme.",
        "",
    ]
    for kind, heading in sections:
        chosen = [i for i in items if i["kind"] == kind]
        if chosen:
            out += [f"## {heading}", "", *map(line, chosen), ""]
    out += [
        "---",
        "",
        "*Found something for next week? [Submit a link](../../../submit.md) "
        "or reply to this email.*",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--body", required=True, help="Curation issue body (Markdown file)")
    parser.add_argument("--comments", required=True, help="Issue comments (GitHub API JSON file)")
    parser.add_argument("--title", default="This week in inference")
    parser.add_argument("--date", help="Publish date YYYY-MM-DD (default: next Monday)")
    parser.add_argument("--no-lookup", action="store_true", help="Don't fetch titles for bare URLs")
    args = parser.parse_args()

    body = pathlib.Path(args.body).read_text(encoding="utf-8")
    comments = json.loads(pathlib.Path(args.comments).read_text(encoding="utf-8"))
    items = dedupe(from_body(body) + from_comments(comments, not args.no_lookup))
    if not items:
        print("No ticked items or comment links found in the curation issue.", file=sys.stderr)
        return 1

    date = dt.date.fromisoformat(args.date) if args.date else next_monday(dt.date.today())
    target = ISSUES / f"{date:%Y}" / f"{date:%m}" / f"{date.isoformat()}.md"
    if target.exists():
        print(f"Already exists: {target.relative_to(ROOT)}", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(items, date, next_number(), args.title), encoding="utf-8")
    counts = {k: sum(i["kind"] == k for i in items) for k in ("read", "watch", "repos")}
    print(target.relative_to(ROOT))
    print(f"read={counts['read']} watch={counts['watch']} repos={counts['repos']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
