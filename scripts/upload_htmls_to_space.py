"""Upload HTML graph visualizations to HF Space in batches of 500 per category."""
import os
import sys
import tempfile
from pathlib import Path
from huggingface_hub import upload_folder

BASE = "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k"
REPO_ID = "RHCPP/saranga"
BATCH_SIZE = 500


def upload_category(cat_dir: Path, cat_name: str):
    htmls = sorted(cat_dir.glob("*.html"))
    total = len(htmls)
    if total == 0:
        print(f"  {cat_name}: no HTML files, skipping")
        return

    for batch_start in range(0, total, BATCH_SIZE):
        batch = htmls[batch_start : batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)
        print(f"  {cat_name}: uploading {batch_start+1}-{batch_end} of {total}")

        # Create temp dir with symlinks for this batch
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in batch:
                os.symlink(f, os.path.join(tmpdir, f.name))

            upload_folder(
                folder_path=tmpdir,
                repo_id=REPO_ID,
                repo_type="space",
                path_in_repo=f"html/{cat_name}",
            )

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
