"""Upload HTML graph visualizations to HF Space in batches per category."""
import os
import sys
import time
import tempfile
from pathlib import Path
from huggingface_hub import upload_folder

BASE = "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k"
REPO_ID = "RHCPP/saranga"
BATCH_SIZE = 100
MAX_RETRIES = 3


def upload_batch(files, cat_name, attempt=1):
    """Upload a batch of files, retry on transient errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            os.symlink(f, os.path.join(tmpdir, f.name))
        try:
            upload_folder(
                folder_path=tmpdir,
                repo_id=REPO_ID,
                repo_type="space",
                path_in_repo=f"html/{cat_name}",
            )
            return True
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 30 * attempt
                print(f"    Error: {e}. Retrying in {wait}s (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                return upload_batch(files, cat_name, attempt + 1)
            else:
                print(f"    FAILED after {MAX_RETRIES} attempts: {e}")
                return False


def upload_category(cat_dir: Path, cat_name: str):
    htmls = sorted(cat_dir.glob("*.html"))
    total = len(htmls)
    if total == 0:
        print(f"  {cat_name}: no HTML files, skipping")
        return

    failed = 0
    for batch_start in range(0, total, BATCH_SIZE):
        batch = htmls[batch_start : batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)
        print(f"  {cat_name}: uploading {batch_start+1}-{batch_end} of {total}")

        if not upload_batch(batch, cat_name):
            failed += 1

    if failed:
        print(f"  {cat_name}: WARNING — {failed} batch(es) failed")
    else:
        print(f"  {cat_name} done ({total} files)")


def main():
    base = Path(BASE)
    categories = sorted(d.parent.name for d in base.glob("*/html") if d.is_dir())

    # Allow filtering to specific categories via CLI args
    if len(sys.argv) > 1:
        categories = [c for c in categories if c in sys.argv[1:]]

    print(f"Uploading {len(categories)} categories, batch size {BATCH_SIZE}")
    for cat in categories:
        cat_dir = base / cat / "html"
        print(f"Category: {cat}")
        upload_category(cat_dir, cat)

    print("All done!")


if __name__ == "__main__":
    main()
