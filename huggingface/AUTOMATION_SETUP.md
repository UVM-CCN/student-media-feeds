# Hugging Face Dataset — Automating with GitHub Actions

This guide picks up where [SETUP.md](SETUP.md) left off. It wires the nightly
GitHub Action to push the dataset to Hugging Face automatically after each
scrape, so you never have to push manually again.

**Prerequisites** — do these first:
1. Complete the steps in [SETUP.md](SETUP.md)
2. Confirm you can manually run `python huggingface/sync_to_hf.py` and the
   dataset appears on HF
3. Decide whether the dataset will stay private or go public (see step 3 below)

## What this changes

After this is set up, every nightly run of `.github/workflows/daily-scrape.yml`
will:

```
1. scrape.py (RSS + cascade + BERTopic + full-text + analytics + corpora + bag-of-words)
2. validate_news_csv.py
3. git commit + push  ─── lightweight code/CSV/JSON updates
4. build_hf_dataset.py  ─── repackage everything into HF-friendly format
5. sync_to_hf.py  ─── push to Hugging Face Hub
```

GitHub gets the small artifacts (CSV, JSON, dashboard data). Hugging Face gets
the heavy corpus (Parquet, full text, per-publication files, bag-of-words).

## Step 1: Add the HF token to GitHub Actions secrets

In your code repo on GitHub:
- **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
- **Name**: `HF_TOKEN`
- **Value**: your `hf_...` write token (the same one you used for the manual push)
- Save

The token stays encrypted and is only visible to the workflow at runtime.

## Step 2: Add the repo ID as a workflow variable

Same Settings page, **Variables** tab:
- **New repository variable**
- **Name**: `HF_REPO_ID`
- **Value**: `<owner>/<dataset-name>` (e.g., `uvm-ccn/student-journalism-news-deserts`)
- Save

Variables aren't secret, just convenient — keeps the repo ID out of the workflow
file so you can change it without editing YAML.

## Step 3 (optional): Switch the HF dataset to public

If you want the dataset to be citable, indexable by Google, and accessible
without authentication, switch it from Private to Public:

- Open the dataset on HF (`huggingface.co/datasets/<your-repo-id>`)
- Click **Settings**
- Scroll to **Change visibility** → switch to **Public**

Things to consider before going public:
- Make sure the Dataset Card (`README.md`) is polished — it's the first thing
  visitors see
- Confirm the license you chose (CC-BY 4.0 in the auto-generated card) is what
  you want
- Removing existing intern collaborators is fine — public visibility supersedes
  per-user access

Skip this step if you want to keep it private indefinitely. The automation works
the same either way.

## Step 4: Patch the workflow file

Add these two steps to `.github/workflows/daily-scrape.yml` **after** the
existing `Commit and push if changes` step:

```yaml
      - name: Build Hugging Face dataset bundle
        run: python huggingface/build_hf_dataset.py

      - name: Push to Hugging Face Hub
        env:
          HF_REPO_ID: ${{ vars.HF_REPO_ID }}
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: python huggingface/sync_to_hf.py
```

The full updated workflow file should look like:

```yaml
name: Daily News Scrape

on:
  schedule:
    - cron: '59 23 * * *'
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest

    permissions:
      contents: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run scraper
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python scrape.py

      - name: Validate CSV output
        run: python scripts/validate_news_csv.py news_database.csv

      - name: Commit and push if changes
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add news_database.csv analytics/
          git diff --quiet && git diff --staged --quiet || (git commit -m "Update news database and analytics - $(date -u +'%Y-%m-%d %H:%M:%S UTC')" && git push)

      # ─── NEW STEPS ───────────────────────────────────────────────────────
      - name: Build Hugging Face dataset bundle
        run: python huggingface/build_hf_dataset.py

      - name: Push to Hugging Face Hub
        env:
          HF_REPO_ID: ${{ vars.HF_REPO_ID }}
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: python huggingface/sync_to_hf.py
      # ────────────────────────────────────────────────────────────────────
```

## Step 5: Verify with a manual workflow run

Don't wait for the next nightly cron — trigger the workflow manually to confirm
it works:

- Go to your GitHub repo → **Actions** → **Daily News Scrape**
- Click **Run workflow** (top right) → **Run workflow** (in the dropdown)
- Watch the run. The two new steps should appear at the bottom.

If both green-check, you're done. If the HF steps fail:
- **`401 Unauthorized`** — the `HF_TOKEN` secret is wrong or expired
- **`RepositoryNotFoundError`** — the `HF_REPO_ID` variable is wrong, or the
  token doesn't have access to that repo
- **`ModuleNotFoundError: huggingface_hub`** — `requirements.txt` wasn't
  re-installed; check that the `Install dependencies` step ran

## Step 6 (optional): Clean up the GitHub repo

Once HF sync is verified working for a few nights, you can stop committing the
heavy data files to GitHub. Add to `.gitignore`:

```
full_text/
publication_corpora/
```

Then untrack them from git:

```bash
git rm -r --cached full_text/ publication_corpora/
git commit -m "Move heavy corpus data to Hugging Face dataset"
git push
```

After this, the GitHub repo stays small (~20 MB of code + small data), and
contributors who need the corpus locally have two options:

1. **Pull from HF** (recommended): `datasets.load_dataset("your-handle/...")`
   — works for every story including ones whose source URLs have died
2. **Re-scrape**: `python fetch_full_text.py` — works for stories with live
   source URLs (link rot will eventually break this for older stories)

The HF dataset becomes the canonical archive of the corpus.

## Timing

Steady-state extra time added to each nightly GitHub Action:
- Build step: ~10 seconds (Parquet conversion is fast)
- Sync step: ~30–90 seconds (huggingface_hub diffs internally; only changed
  files transfer)

First Action run after wiring this up will be longer because every file is
new on HF — expect 5–15 minutes added to that one run. After that, daily sync
is fast.
