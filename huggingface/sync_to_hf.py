"""
Push the built dataset to the Hugging Face Hub.

Reads from huggingface/dataset_build/ (created by build_hf_dataset.py) and
uploads to a dataset repository on the Hub. Designed to be idempotent and
safe to call after every nightly scrape — only changed files transfer.

Configuration:
    HF_REPO_ID — required. e.g. "uvm-ccn/student-journalism-news-deserts"
    HF_TOKEN   — required. Write-access token from
                 https://huggingface.co/settings/tokens

Both are read from environment variables. In GitHub Actions, store HF_TOKEN
as a repository secret and pass HF_REPO_ID as an env var in the workflow.

Internally uses `upload_large_folder`, which splits the upload into many
small commits (instead of one giant commit) so the HTTP request doesn't
time out on first push. Trade-off: the HF dataset history will have many
auto-named commits instead of one named per push.

Usage (local):
    export HF_REPO_ID="your-handle/student-journalism-news-deserts"
    export HF_TOKEN="hf_xxxxxxxx"
    python huggingface/sync_to_hf.py

Usage (CI): see huggingface/SETUP.md for the workflow snippet.

Requires:
    pip install huggingface_hub
"""
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import HfApi, create_repo
    from huggingface_hub.utils import RepositoryNotFoundError
except ImportError:
    print(
        "ERROR: huggingface_hub is required.\n"
        "Install with: pip install huggingface_hub",
        file=sys.stderr,
    )
    sys.exit(1)

BUILD_DIR = Path(__file__).resolve().parent / "dataset_build"


def main():
    repo_id = os.environ.get("HF_REPO_ID")
    token = os.environ.get("HF_TOKEN")

    if not repo_id:
        print("ERROR: HF_REPO_ID environment variable is not set.", file=sys.stderr)
        print("Example: export HF_REPO_ID='your-handle/student-journalism-news-deserts'", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("ERROR: HF_TOKEN environment variable is not set.", file=sys.stderr)
        print("Generate one at https://huggingface.co/settings/tokens (Write access)", file=sys.stderr)
        sys.exit(1)

    if not BUILD_DIR.is_dir():
        print(f"ERROR: {BUILD_DIR} does not exist.", file=sys.stderr)
        print("Run `python huggingface/build_hf_dataset.py` first.", file=sys.stderr)
        sys.exit(1)

    api = HfApi(token=token)

    # Ensure the dataset repo exists. create_repo is a no-op if it already does
    # and exist_ok=True; we still wrap in try to surface useful errors.
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
        print(f"Found existing dataset repo: {repo_id}")
    except RepositoryNotFoundError:
        print(f"Creating new dataset repo: {repo_id}")
        create_repo(
            repo_id=repo_id,
            repo_type="dataset",
            token=token,
            exist_ok=True,
        )

    file_count = sum(1 for p in BUILD_DIR.rglob("*") if p.is_file())
    total_mb = sum(p.stat().st_size for p in BUILD_DIR.rglob("*") if p.is_file()) / 1024 / 1024
    print(f"Uploading {file_count} files ({total_mb:.1f} MB) to {repo_id}...")
    print("Using upload_large_folder — this splits the upload into multiple")
    print("commits and resumes gracefully on failure. May take 10+ minutes")
    print("on first push. Progress reports print every 60 seconds.")
    print()

    # upload_large_folder is the recommended approach for any folder with
    # many files or substantial size. It's chunked, resumable, and avoids
    # the single-commit timeout that breaks upload_folder past ~1000 files.
    # (upload_folder times out on its commit POST when there are thousands
    # of files because HF's server takes too long to process the commit.)
    api.upload_large_folder(
        folder_path=str(BUILD_DIR),
        repo_id=repo_id,
        repo_type="dataset",
        ignore_patterns=["*.tmp", ".DS_Store", "__pycache__"],
        print_report=True,
        print_report_every=60,
    )

    print(f"Done. Dataset is live at: https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()
