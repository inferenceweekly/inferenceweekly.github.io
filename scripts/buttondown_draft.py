#!/usr/bin/env python3
"""Create a Buttondown DRAFT email from an issue Markdown file.

Usage (needs BUTTONDOWN_API_KEY in the environment):
    python scripts/buttondown_draft.py docs/issues/2026/11/2026-11-16.md

The draft links back to the web version and strips site-only syntax
(front matter, Material icons, relative links).
"""
import os
import pathlib
import re
import sys

import requests
import yaml

SITE = "https://inferenceweekly.github.io"
API = "https://api.buttondown.com/v1/emails"


def split_front_matter(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        return {}, text
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def web_url(meta: dict) -> str:
    date = str(meta["date"])
    year, month, _ = date.split("-")
    return f"{SITE}/issues/{year}/{month}/{date}/"


def to_email(body: str, url: str) -> str:
    body = re.sub(r"^# .*\n+", "", body.lstrip(), count=1)          # title becomes the subject
    body = re.sub(r":material-[a-z0-9-]+:\s*", "", body)    # site-only icons
    body = re.sub(r"\]\((?:\.\./)+submit\.md\)", f"]({SITE}/submit/)", body)
    header = f"*[Read this issue on the web]({url})*\n\n"
    return header + body.strip() + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    key = os.environ.get("BUTTONDOWN_API_KEY")
    if not key:
        print("BUTTONDOWN_API_KEY is not set; skipping.", file=sys.stderr)
        return 0

    meta, body = split_front_matter(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    payload = {
        "subject": f"Inference Weekly {meta.get('title', '').strip()}",
        "body": to_email(body, web_url(meta)),
        "status": "draft",
    }
    response = requests.post(
        API, json=payload, headers={"Authorization": f"Token {key}"}, timeout=30
    )
    if response.status_code >= 300:
        print(f"Buttondown error {response.status_code}: {response.text}", file=sys.stderr)
        return 1
    print(f"Draft created: {payload['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
