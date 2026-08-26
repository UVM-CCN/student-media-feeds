# Accessing the Student Journalism Dataset on Hugging Face

You're being given access to a private dataset of stories collected from
U.S. student journalism outlets. This guide walks you through the setup —
takes about 10 minutes the first time, then it just works.

If anything in this doc is unclear, ask Ben.

## What you'll need

- A computer with Python 3.9+ installed
- An internet connection
- Ability to install Python packages with `pip` (or `uv pip`, or `conda` — whatever you normally use)

---

## Step 1: Create a Hugging Face account

Go to [huggingface.co/join](https://huggingface.co/join) and sign up. It's free.
You can use your school email or any personal email.

After signing up:
- Confirm your email (check your inbox)
- Pick a **username** — this is what Ben needs to invite you to the dataset.
  You'll see it on your profile page as `huggingface.co/your-username`.

## Step 2: Send your Hugging Face username to Ben

Email or message Ben your HF username (just the `your-username` part, not the
full URL). He'll add you as a collaborator on the dataset.

**Wait for confirmation that you've been added before continuing to Step 3.**

## Step 3: Install the Python packages you'll need

In a terminal, run:

```bash
pip install huggingface_hub datasets pandas pyarrow
```

(If you use `uv`, `poetry`, or `conda`, install the same four packages with
whatever syntax you normally use.)

What each one does:
- `huggingface_hub` — talks to Hugging Face (authentication, downloading)
- `datasets` — the standard way to load a dataset
- `pandas` — what you'll probably use to filter and analyze data
- `pyarrow` — required by pandas to read Parquet files (the dataset's format)

## Step 4: Create a personal access token

Hugging Face needs a token to confirm it's really you accessing the private
dataset.

1. Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Click **New token**
3. Give it a name like `local-laptop` (any name is fine)
4. For **Role**, choose **Read** (you only need to read the data, not write to it)
5. Click **Generate token**
6. **Copy the token immediately** — it starts with `hf_...`. You won't be able
   to see it again after closing this page.

If you ever lose the token, just generate a new one — old tokens can be
revoked from the same page.

## Step 5: Log in from your terminal

In your terminal, run:

```bash
huggingface-cli login
```

Paste your token when prompted (it won't show as you type, that's normal).
Press Enter.

You should see `Login successful`. You only need to do this once per computer.

## Step 6: Verify you can access the dataset

Open a Python interpreter (`python` in your terminal) or a Jupyter notebook
and run:

```python
import pandas as pd

# Replace YOUR_HF_HANDLE with the dataset owner Ben tells you
df = pd.read_parquet(
    "hf://datasets/YOUR_HF_HANDLE/student-media-feeds/stories.parquet"
)

print(f"Loaded {len(df)} stories")
print(df.head())
print(df.columns.tolist())
```

If this prints story counts and a table, **you're done with setup.** 🎉

If you get an error, see the Troubleshooting section at the bottom.

---

## How to use the dataset

### Get all stories with their full article text

```python
import pandas as pd
df = pd.read_parquet(
    "hf://datasets/YOUR_HF_HANDLE/student-media-feeds/stories.parquet"
)
# Each row is one story; df["full_text"] is the article body
```

### Filter by publication

```python
stanford = df[df["source"] == "The Stanford Daily"]
```

### Get all stories from a particular state's outlets
You'll need to join against an outlet→state mapping. Ask Ben for that file
if you need it.

### Download the per-publication corpora (for vector analysis)

Each publication's stories are concatenated into a single `.txt` file. Useful
for TF-IDF, topic modeling, or any analysis where each publication is one
"document."

```python
from huggingface_hub import snapshot_download

local_dir = snapshot_download(
    repo_id="YOUR_HF_HANDLE/student-media-feeds",
    repo_type="dataset",
    allow_patterns=["publication_corpora/*.txt"],
)

# Files are now downloaded to local_dir
import os, glob
paths = sorted(glob.glob(f"{local_dir}/publication_corpora/*.txt"))
print(f"{len(paths)} publication corpora downloaded to {local_dir}")
```

### Get the corpus-wide word frequencies

```python
bag = pd.read_csv(
    "hf://datasets/YOUR_HF_HANDLE/student-media-feeds/bag_of_words.csv"
)
print(bag.head(20))  # top 20 most frequent words
```

### Get the per-story → publication lookup

```python
index = pd.read_csv(
    "hf://datasets/YOUR_HF_HANDLE/student-media-feeds/publication_story_index.csv"
)
```

---

## Reference: what's in the dataset

| File | What it is |
|---|---|
| `stories.parquet` | The main dataset. One row per story with title, source, link, published date, theme, sentiment, keywords, and full article text. |
| `publication_corpora/*.txt` | Per-publication concatenated article text. One file per outlet. |
| `publication_corpora_manifest.csv` | Per-publication summary: name, story count, total words, date range. |
| `publication_story_index.csv` | Lookup table — which publication each story belongs to, with metadata. |
| `bag_of_words.csv` | Word frequencies across the entire corpus. Columns: rank, word, count, document_frequency. |
| `README.md` | Description of the dataset and how it was collected. |

Columns in `stories.parquet`:

| Column | Description |
|---|---|
| `source` | Publication name (e.g. "The Stanford Daily") |
| `title` | Article headline |
| `link` | Original article URL |
| `published` | Publication date (ISO format when parseable) |
| `captured_at` | When our scraper ingested the story |
| `theme` | Topic label from BERTopic, or "Unclassified" |
| `keywords` | Pipe-delimited keywords from the headline + summary |
| `sentiment_label` | `positive`, `neutral`, or `negative` |
| `sentiment_score` | Number from -1 to 1 |
| `extraction_status` | `ok` if full text was extracted, otherwise an error code |
| `full_text` | The article body. Empty for stories where extraction failed (~2% of rows) |

---

## Troubleshooting

**`403 Forbidden` when loading the dataset**
You aren't added as a collaborator yet, or you didn't run `huggingface-cli login`
on this computer. Try the login again. If that doesn't fix it, message Ben to
confirm your username is on the dataset's collaborator list.

**`401 Unauthorized`**
Your token expired or was revoked. Generate a new one (Step 4) and re-run
`huggingface-cli login`.

**`ModuleNotFoundError: No module named 'pyarrow'`**
Run `pip install pyarrow` — it's needed to read Parquet files.

**`RepositoryNotFoundError`**
Either the dataset name in your code is misspelled, or you don't have access
yet. Double-check both.

**Login token isn't being picked up**
On some systems the token is saved per-shell. Try opening a fresh terminal
window and running your script there. Or pass the token explicitly:

```python
from huggingface_hub import login
login(token="hf_xxx")  # paste your token

# then continue with pd.read_parquet(...)
```

**Anything else** — message Ben with the exact error message.
