#!/usr/bin/env python3
"""Batch-grade student extractors, caching scores and (re)building the leaderboard.

Expected submissions layout (one folder per student/team, filled by your intake
puller -- GitHub Classroom clone or Moodle download):

    submissions/<id>/annotate_chapter.py

For each student and each split it produces, via run_all.py:

    results/<id>/<split>/summary.csv      (+ per-doc annotations, *_eval.csv, *_report.txt)

Caching: if results/<id>/<split>/summary.csv already exists it is REUSED and the
extractor is NOT re-run, unless --force-rerun is given. Then make_leaderboard.py
is called to (re)write the leaderboard.

Examples:
    python3 grade_all.py --submissions submissions --out results
    python3 grade_all.py --split both --test-dir /path/to/test_set
    python3 grade_all.py --force-rerun --model Qwen/Qwen2.5-7B-Instruct
"""

import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
# Course repo that holds run_all.py (the student-facing runner).
DEFAULT_RUNNER = "/mnt/c/Code/Github/BigDataProject_52017/src/run_all.py"


def find_extractor(student_dir):
    """Locate the student's annotate_chapter.py (top level, else anywhere, else the
    only .py file). Returns a path or None."""
    direct = os.path.join(student_dir, "annotate_chapter.py")
    if os.path.exists(direct):
        return direct
    hits = glob.glob(os.path.join(student_dir, "**", "annotate_chapter.py"), recursive=True)
    if hits:
        return sorted(hits, key=len)[0]
    pys = [p for p in glob.glob(os.path.join(student_dir, "**", "*.py"), recursive=True)]
    return pys[0] if len(pys) == 1 else None


def file_hash(path):
    """SHA-256 of a file's bytes (used to group identical submissions)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(rep_sid, ext, split, out_dir, runner, test_dir, model, force_rerun):
    """Run run_all.py for a single representative submission + split. Returns a
    short status string. Skips (cached) if a summary.csv already exists."""
    summary = os.path.join(out_dir, "summary.csv")
    if os.path.exists(summary) and not force_rerun:
        return f"[{rep_sid}/{split}] cached"
    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, runner, "--extractor", ext, "--split", split, "--out-dir", out_dir]
    if test_dir:
        cmd += ["--test-dir", test_dir]
    if model:
        cmd += ["--model", model]
    logpath = os.path.join(out_dir, "run.log")
    try:
        with open(logpath, "w", encoding="utf-8") as lf:
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode
    except Exception as e:  # one submission's failure must not kill the batch
        return f"[{rep_sid}/{split}] ERROR: {e}"
    ok = os.path.exists(summary)
    return f"[{rep_sid}/{split}] {'OK' if ok else 'no summary (see ' + logpath + ')'} (rc={rc})"


def main():
    ap = argparse.ArgumentParser(description="Batch-grade student extractors and build the leaderboard.")
    ap.add_argument("--submissions", default="submissions",
                    help="Directory with one subfolder per student/team (default: submissions)")
    ap.add_argument("--out", default="results",
                    help="Where per-student score folders are written (default: results)")
    ap.add_argument("--runner", default=DEFAULT_RUNNER, help="Path to run_all.py")
    ap.add_argument("--split", choices=["train", "test", "both"], default="both")
    ap.add_argument("--test-dir", default=None,
                    help="Folder with held-out test golds + tex, laid out for run_all "
                         "(<label>_gold.json + <label>.tex). Needed for the test split.")
    ap.add_argument("--model", default=None, help="Model passed to each extractor")
    ap.add_argument("--force-rerun", action="store_true",
                    help="Always re-run extraction even if a summary.csv already exists (default: off)")
    ap.add_argument("--leaderboard", default="LEADERBOARD.md", help="Output leaderboard path")
    ap.add_argument("--anonymize", action="store_true", help="Anonymize student ids on the board")
    ap.add_argument("--no-board", action="store_true", help="Do not (re)build the leaderboard")
    ap.add_argument("--rank-by", choices=["test", "train"], default="test",
                    help="Passed to make_leaderboard: which split to rank by (default: test)")
    ap.add_argument("--note", default="", help="Passed to make_leaderboard: student-facing line under the title")
    ap.add_argument("--board-title", default=None, help="Passed to make_leaderboard as --title")
    ap.add_argument("--dedupe", "--identical", dest="dedupe", action="store_true",
                    help="Group submissions by extractor content hash, run each UNIQUE "
                         "extractor once, and copy its scores to identical submissions. "
                         "Safe to leave on permanently: with all-distinct submissions "
                         "every one is graded separately. Ideal for the all-baseline board.")
    ap.add_argument("--jobs", "-j", type=int, default=1,
                    help="Run this many unique extractors in parallel (default: 1). "
                         "On HF they parallelize; on a single cluster GPU the shared "
                         "vLLM server batches, so the gain is smaller.")
    args = ap.parse_args()

    splits = ["train", "test"] if args.split == "both" else [args.split]
    students = sorted(d for d in glob.glob(os.path.join(args.submissions, "*")) if os.path.isdir(d))
    if not students:
        print(f"No student folders found in {args.submissions}/")
        return

    # Resolve each submission's extractor; drop folders without one.
    subs = []  # list of (sid, ext)
    for sd in students:
        sid = os.path.basename(sd)
        ext = find_extractor(sd)
        if not ext:
            print(f"=== {sid} === no annotate_chapter.py found -- skipping")
            continue
        subs.append((sid, ext))

    # Group by content hash when --dedupe; otherwise each submission is its own group.
    # groups: hash -> {"rep": (sid, ext), "members": [sid, ...]}
    groups = {}
    for sid, ext in subs:
        key = file_hash(ext) if args.dedupe else f"{sid}:{ext}"
        g = groups.setdefault(key, {"rep": (sid, ext), "members": []})
        g["members"].append(sid)

    reps = [g["rep"] for g in groups.values()]
    dup_total = len(subs) - len(reps)
    print(f"Submissions: {len(subs)} | unique extractors: {len(reps)} "
          f"| duplicates copied: {dup_total} | splits: {splits} | jobs: {args.jobs} "
          f"| dedupe: {args.dedupe} | force-rerun: {args.force_rerun}")

    # 1) Run every unique (representative, split) -- in parallel across --jobs workers.
    tasks = [(rep_sid, ext, split)
             for (rep_sid, ext) in reps for split in splits]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futs = {pool.submit(run_one, rep_sid, ext, split,
                            os.path.join(args.out, rep_sid, split),
                            args.runner, args.test_dir, args.model, args.force_rerun): (rep_sid, split)
                for (rep_sid, ext, split) in tasks}
        for fut in as_completed(futs):
            print("  " + fut.result())

    # 2) Copy each representative's scores to its identical members.
    for g in groups.values():
        rep_sid = g["rep"][0]
        for sid in g["members"]:
            if sid == rep_sid:
                continue
            for split in splits:
                src = os.path.join(args.out, rep_sid, split)
                dst = os.path.join(args.out, sid, split)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"  [{sid}] copied scores from identical {rep_sid}")

    if not args.no_board:
        mk = os.path.join(HERE, "make_leaderboard.py")
        cmd = [sys.executable, mk, "--results", args.out, "--out", args.leaderboard,
               "--rank-by", args.rank_by]
        if args.note:
            cmd += ["--note", args.note]
        if args.board_title:
            cmd += ["--title", args.board_title]
        if args.anonymize:
            cmd.append("--anonymize")
        print("\n=== leaderboard ===")
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
