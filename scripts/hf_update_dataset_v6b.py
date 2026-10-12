#!/usr/bin/env python3
"""Replace the 100K corpus on the Hugging Face dataset RHCPP/saranga with the v6b run.

Run ON THE CLUSTER (where the run lives), logged in to Hugging Face with a write token:

    python3 scripts/hf_update_dataset_v6b.py \
        /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v6b

For each category it uploads <cat>/json/*.json and the category reports (*.csv, *.json at
the top of <cat>/), and deletes the old pre-built pages <cat>/html/ (the portal now builds
pages on the fly). File names are unchanged (<id>_rules.json), so old files are overwritten.
Resumable: re-running skips what is already uploaded.
"""
import sys
from pathlib import Path

from huggingface_hub import HfApi

REPO = "RHCPP/saranga"
CATS = ["cs_CC", "cs_DS", "cs_IT", "cs_LG", "math_AG", "math_AP", "math_AT", "math_CA", "math_CO", "math_DG",
        "math_FA", "math_GR", "math_LO", "math_NA", "math_NT", "math_OC", "math_PR", "math_RT", "math_ph", "stat_TH"]


def main(run_dir):
    run = Path(run_dir)
    api = HfApi()
    missing = [c for c in CATS if not (run / c / "json").is_dir()]
    if missing:
        sys.exit(f"missing json/ for: {missing}")
    # 1. upload json/ and the category reports straight from the run directory
    #    (large-folder upload: many files, resumable, multi-threaded)
    allow = [p for c in CATS for p in (f"{c}/json/*.json", f"{c}/*.csv", f"{c}/*.json")]
    api.upload_large_folder(repo_id=REPO, repo_type="dataset", folder_path=str(run), allow_patterns=allow)
    # 2. drop the old pre-built pages
    for c in CATS:
        try:
            api.delete_folder(path_in_repo=f"{c}/html", repo_id=REPO, repo_type="dataset",
                              commit_message=f"Remove old pre-built pages for {c} (built on the fly now)")
        except Exception as e:                       # noqa: BLE001  (already gone)
            print(f"  {c}/html: {e}")
    print("done")


if __name__ == "__main__":
    main(sys.argv[1])
