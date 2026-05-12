"""Upload local tier3 files to HF Space in small batches, skipping already-uploaded ones.

Usage:
    python scripts/upload_tier3_batched.py [--batch-size 50] [--dry-run]
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi, list_repo_tree

SPACE_ID = "RHCPP/saranga"
PORTAL_DIR = Path(__file__).resolve().parent.parent / "portal"


def list_remote_files(api, prefix, ext):
    """List all files under prefix on the Space."""
    remote = set()
    try:
        items = list(list_repo_tree(SPACE_ID, repo_type="space",
                                     path_in_repo=prefix, recursive=True))
        for item in items:
            p = item.path if hasattr(item, "path") else str(item)
            if p.endswith(ext):
                remote.add(p)
    except Exception as e:
        print(f"  Warning listing {prefix}: {e}")
    return remote


def upload_batch(api, files, label="batch", max_retries=3):
    """Upload a list of (local_path, repo_path) tuples via a temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for local_path, repo_path in files:
            dest = Path(tmpdir) / repo_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(local_path, dest)
        for attempt in range(max_retries):
            try:
                api.upload_folder(
                    folder_path=tmpdir,
                    repo_id=SPACE_ID,
                    repo_type="space",
                )
                return True
            except Exception as e:
                err = str(e)
                if attempt < max_retries - 1:
                    wait = 30 * (attempt + 1)
                    print(f"    Retry {attempt+2}/{max_retries} in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"    FAILED: {e}")
                    return False
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Files per upload batch (default: 50)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api = HfApi()

    # Step 1: List what's already on the Space (nested paths)
    print("Listing remote files on Space...")
    remote_jsons = list_remote_files(api, "data/tier3", ".json")
    remote_htmls = list_remote_files(api, "graphs/tier3", ".html")
    print(f"  Remote: {len(remote_jsons)} JSONs, {len(remote_htmls)} HTMLs")

    # Step 2: List local files and find missing ones
    local_jsons = sorted(PORTAL_DIR.glob("data/tier3/**/*.json"))
    local_htmls = sorted(PORTAL_DIR.glob("graphs/tier3/**/*.html"))
    print(f"  Local:  {len(local_jsons)} JSONs, {len(local_htmls)} HTMLs")

    # Build upload list: (local_abs_path, path_in_repo)
    to_upload = []
    for f in local_jsons:
        repo_path = str(f.relative_to(PORTAL_DIR))
        # Check both nested and flat (old) paths
        fname = f.name
        flat_path = f"data/tier3/{fname}"
        if repo_path not in remote_jsons and flat_path not in remote_jsons:
            to_upload.append((str(f), repo_path))

    for f in local_htmls:
        repo_path = str(f.relative_to(PORTAL_DIR))
        fname = f.name
        flat_path = f"graphs/tier3/{fname}"
        if repo_path not in remote_htmls and flat_path not in remote_htmls:
            to_upload.append((str(f), repo_path))

    print(f"\n  To upload: {len(to_upload)} files")

    if args.dry_run:
        for _, rp in to_upload[:20]:
            print(f"    {rp}")
        if len(to_upload) > 20:
            print(f"    ... and {len(to_upload) - 20} more")
        return

    if not to_upload:
        print("Nothing to upload!")
        return

    # Step 3: Upload in batches
    total = len(to_upload)
    batch_size = args.batch_size
    failed = 0
    for i in range(0, total, batch_size):
        batch = to_upload[i:i + batch_size]
        end = i + len(batch)
        print(f"  Batch {i+1}-{end} of {total}...", end=" ", flush=True)
        if upload_batch(api, batch, f"batch {i+1}-{end}"):
            print("ok")
        else:
            print("FAILED")
            failed += 1

    print(f"\nDone! {total - failed * batch_size} files uploaded, {failed} batch(es) failed.")


if __name__ == "__main__":
    main()
