# Inference Weekly

A weekly, hand-curated digest of inference engineering, published at
**https://inferenceweekly.github.io**, by email via Buttondown, and by RSS.

Built with [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
(RSS plugin, plus a small hook that builds the date sidebar), deployed to GitHub Pages by GitHub Actions.

## Weekly workflow

| When | What happens |
|---|---|
| **Friday 09:00 (Istanbul)** | `curate.yml` scans every source in `curation/sources.yml` and opens a GitHub issue labelled `curation` with a checklist of the week's candidates |
| **During the week** | Tick the items you want, and paste any extra links (articles, videos, repos) as comments on that issue |
| **When you're done picking** | *Actions → Compile issue → Run workflow*: builds the issue file from your ticks and comment links, sorted into Read / Watch / Repos, and opens a pull request |
| **In the pull request** | Replace every `TODO:` with your own line, remove or reorder items, then merge |
| **On merge** | The site and RSS feed update, a Buttondown **draft** is created, and the curation issue closes |
| **Monday morning** | Review the draft in Buttondown and press send |

The site refuses to publish, and no email draft is created, while an issue still contains `TODO:`.
You can still write an issue by hand with `python scripts/new_issue.py "Title"`.

## One-time setup

1. **Push this repo** to `inferenceweekly/inferenceweekly.github.io` (branch `main`).
2. **Enable Pages:** *Settings → Pages → Source: GitHub Actions*.
3. **Let workflows open issues and pull requests:** *Settings → Actions → General →
   Workflow permissions* → **Read and write permissions**, and tick
   **Allow GitHub Actions to create and approve pull requests**.
4. **Buttondown:** create an account with the username `inferenceweekly`
   (this makes the signup form on the home page work). Then
   *Settings → API* → copy the key → add it to the repo as the secret
   `BUTTONDOWN_API_KEY` (*Settings → Secrets and variables → Actions*).
   Without the secret the draft workflow simply skips.
5. **Add YouTube channels** to `curation/sources.yml` (instructions inside),
   and check the first curation issue for any feeds marked as failed.
6. Optional: *Actions → Weekly curation → Run workflow* to get a first batch now.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve                       # http://127.0.0.1:8000
python scripts/curate.py --days 7  # print this week's candidates
```

## Layout

```
docs/
  index.md               home page + subscribe form
  issues/YYYY/MM/        one Markdown file per issue (YYYY-MM-DD.md)
  about.md, submit.md
templates/issue.md       section template used by new_issue.py
curation/sources.yml     feeds, keywords and repos to watch
scripts/
  new_issue.py           create the next numbered issue
  curate.py              collect candidates from feeds and GitHub releases
  compile_issue.py       turn ticked items + comment links into a draft issue
  buttondown_draft.py    turn an issue into a Buttondown draft
.github/workflows/       deploy, weekly curation, compile issue, Buttondown draft
hooks/issues_nav.py      builds the year/month/date sidebar automatically
```

## Moving to a custom domain later

Add the domain under *Settings → Pages → Custom domain*, update `site_url` in
`mkdocs.yml` and `SITE` in `scripts/buttondown_draft.py`. GitHub redirects the
old `github.io` address automatically.
