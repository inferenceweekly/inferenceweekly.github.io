# Inference Weekly

A weekly, hand-curated digest of inference engineering, published at
**https://inferenceweekly.github.io**, by email via Buttondown, and by RSS.

Built with [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
(RSS plugin, plus a small hook that builds the date sidebar), deployed to GitHub Pages by GitHub Actions.

## Weekly workflow

| When | What happens |
|---|---|
| **Friday 09:00 (Istanbul)** | `curate.yml` scans every source in `curation/sources.yml` and opens a GitHub issue labelled `curation` with a checklist of the week's candidates |
| **Weekend** | Tick the items you want; add anything you found yourself |
| **Sunday** | `python scripts/new_issue.py "This week's theme"` → fill in the new file in `docs/issues/YYYY/MM/` → commit and push |
| **On push** | `deploy.yml` publishes the site and RSS feed; `buttondown-draft.yml` creates a **draft** email in Buttondown |
| **Monday morning** | Review the draft in Buttondown and press send |

## One-time setup

1. **Push this repo** to `inferenceweekly/inferenceweekly.github.io` (branch `main`).
2. **Enable Pages:** *Settings → Pages → Source: GitHub Actions*.
3. **Allow the curation job to open issues:** *Settings → Actions → General →
   Workflow permissions → Read and write permissions*.
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
  buttondown_draft.py    turn an issue into a Buttondown draft
.github/workflows/       deploy, weekly curation, Buttondown draft
hooks/issues_nav.py      builds the year/month/date sidebar automatically
```

## Moving to a custom domain later

Add the domain under *Settings → Pages → Custom domain*, update `site_url` in
`mkdocs.yml` and `SITE` in `scripts/buttondown_draft.py`. GitHub redirects the
old `github.io` address automatically.
