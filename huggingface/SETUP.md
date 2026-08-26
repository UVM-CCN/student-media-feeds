# Hugging Face Dataset — One-Time Setup (Private + Manual Push)

This guide gets the current scrape results into a **private** Hugging Face
dataset that you share with your interns. It is a one-time manual upload —
no GitHub Actions automation yet.

When you're ready to automate (so each nightly scrape pushes to HF
automatically), see **[AUTOMATION_SETUP.md](AUTOMATION_SETUP.md)** in this same
directory.

## Why Hugging Face

- **Free** for datasets of any size, public or private
- **Citable** — datasets get a permanent URL and can receive a DOI
- **Easy access for collaborators** — `datasets.load_dataset("your-handle/...")`
- **Versioned** — every push is a git-style commit on the dataset repo
- **Solves the GitHub size problem** — keeps the code repo small while the
  full corpus + extracted text + per-publication corpora live on HF

## One-time setup

### 1. Create a Hugging Face account
[huggingface.co/join](https://huggingface.co/join) — free, takes 30 seconds.

### 2. Create the dataset repository
- Go to [huggingface.co/new-dataset](https://huggingface.co/new-dataset)
- **Owner**: your account (or your org if you create one)
- **Dataset name**: e.g. `student-journalism-news-deserts`
- **License**: CC-BY 4.0 (recommended for research datasets)
- **Visibility**: **Private** ← important for this setup

Your repo ID is `<owner>/<dataset-name>`. Keep this handy.

### 3. Generate a write token
- Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
- Click **New token**
- **Name**: `student-media-feeds-pipeline`
- **Role**: **Write**
- Copy the token (starts with `hf_`). You won't see it again.

### 4. Invite your interns as collaborators
Once the dataset repo exists:
- Open the dataset on HF (`huggingface.co/datasets/<your-repo-id>`)
- Click **Settings** in the dataset's top nav
- Scroll to **Collaborators** (or **Members** for org-owned datasets)
- For each intern, click **Add user**, enter their HF username, and grant
  **Read** access (or **Write** if you want them to push updates too)
- They'll need an HF account first — if they don't have one, send them
  [huggingface.co/join](https://huggingface.co/join)

Interns access the private dataset by either:

**Option A — CLI login (one time per machine):**
```bash
huggingface-cli login
# paste a read token they generate at huggingface.co/settings/tokens
```
After this, `datasets.load_dataset(...)` works transparently for any private
dataset they have access to.

**Option B — Pass a token explicitly:**
```python
from datasets import load_dataset
ds = load_dataset("your-handle/student-journalism-news-deserts", token="hf_...")
```

## Build and push the current scrape

```bash
# Install dependencies if you haven't yet
pip install -r requirements.txt

# Build the dataset bundle from the current pipeline state
python huggingface/build_hf_dataset.py

# Set credentials and push
export HF_REPO_ID="your-handle/student-journalism-news-deserts"
export HF_TOKEN="hf_xxxxxxxxxxxxxx"
python huggingface/sync_to_hf.py
```

First push will take 5–15 minutes for ~160 MB of files. When it's done, visit
`https://huggingface.co/datasets/<your-repo-id>` to confirm everything is there.

The auto-generated `README.md` (in `huggingface/dataset_build/`) becomes your
**Dataset Card** on HF. Edit it if you want to customize the description,
citation, author info, etc. — then re-run `sync_to_hf.py`.

## Re-running the push after a new scrape

Each time you want to push fresh data to HF (e.g., after running `scrape.py`
manually), just repeat the two commands:

```bash
python huggingface/build_hf_dataset.py
python huggingface/sync_to_hf.py
```

`sync_to_hf.py` is idempotent — `huggingface_hub` diffs internally, so only
changed files actually transfer. Subsequent pushes are usually 30–90 seconds.

## What ends up on HF

After a successful sync, your private HF dataset contains:

| File | Size (current) | Purpose |
|---|---|---|
| `README.md` | ~5 KB | Dataset Card (description, schema, citation) |
| `stories.parquet` | 5–20 MB | One row per story with full article text |
| `publication_corpora/*.txt` | 25–250 MB | Per-publication concatenated text |
| `publication_corpora_manifest.csv` | ~15 KB | Per-publication summary |
| `publication_story_index.csv` | 2–10 MB | Story → publication lookup |
| `bag_of_words.csv` | 2–5 MB | Corpus-wide word frequencies |

Total: typically 50–300 MB, growing over time. Well within HF's unlimited free
tier for private datasets.

## What stays on GitHub

Your code repo keeps:
- All `.py` files (the pipeline source)
- Curated inputs (`feeds/*.opml`, `feeds_*.txt`, `extra_urls.txt`)
- Documentation (`*.md`)
- Small derived data (`news_database.csv`, `analytics/analytics.json`)

Once you start using HF as the canonical home for the corpus, `full_text/` and
`publication_corpora/` can be `.gitignore`'d to keep the GitHub repo small.

## How interns use the dataset

After you've added them as collaborators and they've authenticated:

```python
from datasets import load_dataset
ds = load_dataset("your-handle/student-journalism-news-deserts")

# Or with pandas directly:
import pandas as pd
df = pd.read_parquet(
    "hf://datasets/your-handle/student-journalism-news-deserts/stories.parquet"
)
```

For the per-publication corpora workflow (the one your colleague is using):

```python
from huggingface_hub import snapshot_download
local_dir = snapshot_download(
    repo_id="your-handle/student-journalism-news-deserts",
    repo_type="dataset",
    allow_patterns=["publication_corpora/*.txt"],
)
# Files are now in local_dir/publication_corpora/
```

## Troubleshooting

- **`RepositoryNotFoundError`** — the repo ID is wrong or your token doesn't
  have access to that repo. Double-check both.
- **`401 Unauthorized`** — token is invalid or expired. Generate a new one.
- **Interns get `403 Forbidden`** — they aren't added as collaborators yet, or
  they're not authenticated on their machine. Have them run
  `huggingface-cli login`.
- **`413 Payload Too Large`** — individual file exceeds HF's 50 GB hard limit.
  Won't happen with this dataset, but if it does, split the file.
- **Sync is slow on first push** — first push uploads everything (5–15 min for
  ~160 MB). Subsequent pushes only upload changed files.

## Next step

When you're ready to wire this into your nightly GitHub Action so HF stays in
sync automatically, see **[AUTOMATION_SETUP.md](AUTOMATION_SETUP.md)**.
