"""MkDocs hook: build the left sidebar from the issue files (year > month > date).

Issues live at docs/issues/YYYY/MM/YYYY-MM-DD.md. This hook turns them into

    Welcome
    2026
      November
        2026-11-16
        2026-11-09
    ...
    Books
    Submit a link
    About

newest first, so adding an issue never requires touching mkdocs.yml.
It also replaces the {{ latest_issue }} placeholder on the home page with a
link to the most recent issue.
"""
import calendar
import pathlib
import re

ISSUE = re.compile(r"^issues/(\d{4})/(\d{2})/(\d{4})-(\d{2})-(\d{2})\.md$")
_latest: dict = {}


def _issues(docs_dir: str) -> list[tuple[int, int, int, str]]:
    found = []
    for path in pathlib.Path(docs_dir, "issues").rglob("*.md"):
        rel = path.relative_to(docs_dir).as_posix()
        m = ISSUE.match(rel)
        if m:
            year, month, _, _, day = (int(g) for g in m.groups())
            found.append((year, month, day, rel))
    return sorted(found, reverse=True)


def on_config(config, **kwargs):
    issues = _issues(config["docs_dir"])
    nav: list = [{"Welcome": "index.md"}]

    years: dict[int, dict[int, list]] = {}
    for year, month, day, rel in issues:
        years.setdefault(year, {}).setdefault(month, []).append(
            {f"{year:04d}-{month:02d}-{day:02d}": rel}
        )
    for year, months in years.items():
        nav.append(
            {str(year): [{calendar.month_name[m]: entries} for m, entries in months.items()]}
        )

    nav += [{"Books": "books.md"}, {"Submit a link": "submit.md"}, {"About": "about.md"}]
    config["nav"] = nav

    _latest.clear()
    if issues:
        _latest["path"] = issues[0][3]
    return config


def on_page_markdown(markdown, page, **kwargs):
    if "{{ latest_issue }}" not in markdown:
        return markdown
    if not _latest:
        return markdown.replace("{{ latest_issue }}", "_The first issue is on its way._")
    path = _latest["path"]
    title = path
    text = pathlib.Path(page.file.abs_src_path).parent.joinpath(path)
    match = re.search(r'^title:\s*"?(.+?)"?\s*$', text.read_text(encoding="utf-8"), re.M)
    if match:
        title = match.group(1)
    return markdown.replace("{{ latest_issue }}", f"[{title}]({path})")


# The sidebar labels issues by date ("2026-11-09"), but the RSS feed should use the
# real issue title. MkDocs runs on_page_content for every page before rendering
# any of them, and the RSS plugin reads page.title there at priority -75. So
# swap each issue's title in here, then restore all date labels before the
# first page is rendered.
_swapped: list = []


def on_page_content(html, page, **kwargs):
    if ISSUE.match(page.file.src_uri) and page.meta.get("title"):
        _swapped.append((page, page.title))
        page.title = page.meta["title"]
    return html


def on_page_context(context, page, **kwargs):
    while _swapped:
        swapped_page, nav_title = _swapped.pop()
        swapped_page.title = nav_title
    return context
