#!/usr/bin/env python3
"""Assemble the held-out test set into the layout run_all.py expects.

run_all.py --split test (and grade_all.py --test-dir) want, per document, a pair
of files in one folder:
    <test_set>/<label>_gold.json    and    <test_set>/<label>.tex

This gathers the private test golds (5 papers + chapters 11/12) and their .tex into
that folder. The output is INSTRUCTOR-ONLY; never copy it into the public course repo.

Sources (defaults, relative to the class_52017 area):
    paper golds   : instructor_only/papers_test_gold/*_gold.json   (skips *_orig.json)
    paper tex     : gold_standards/papers/test/<id>.tex
    chapter golds : gold_standards/gold_standard_chapter{N}.json   (6-type normalized)
    chapter tex   : <course-repo>/chapters/tex/chapter{N}.tex
"""

import argparse
import glob
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
CLASS = os.path.dirname(HERE)
DEFAULT_COURSE = "/mnt/c/Code/Github/BigDataProject_52017"


def main():
    ap = argparse.ArgumentParser(description="Assemble the held-out test set for run_all/grade_all.")
    ap.add_argument("--course-repo", default=DEFAULT_COURSE,
                    help="Course repo holding chapters/tex/chapter{11,12}.tex")
    ap.add_argument("--out", default=os.path.join(CLASS, "test_set"),
                    help="Output folder (instructor-only)")
    args = ap.parse_args()

    # Held-out test chapters (Ch2 is the worked example / train, NOT test)
    TEST_CHAPTERS = ("11", "12")

    os.makedirs(args.out, exist_ok=True)
    # clean previously assembled docs so a rebuild can't leave stale files
    for f in glob.glob(os.path.join(args.out, "*_gold.json")) + glob.glob(os.path.join(args.out, "*.tex")):
        os.remove(f)
    n = 0

    # --- Papers ---
    pg_dir = os.path.join(HERE, "papers_test_gold")
    ptex_dir = os.path.join(CLASS, "gold_standards", "papers", "test")
    for g in sorted(glob.glob(os.path.join(pg_dir, "*_gold.json"))):
        if g.endswith("_orig.json"):
            continue
        label = os.path.basename(g)[:-len("_gold.json")]
        tex = os.path.join(ptex_dir, f"{label}.tex")
        if not os.path.exists(tex):
            print(f"WARN  paper {label}: missing tex {tex} -- skipping")
            continue
        shutil.copy(g, os.path.join(args.out, f"{label}_gold.json"))
        shutil.copy(tex, os.path.join(args.out, f"{label}.tex"))
        print(f"paper    {label}")
        n += 1

    # --- Chapters 11/12 ---
    cg_dir = os.path.join(CLASS, "gold_standards")
    ctex_dir = os.path.join(args.course_repo, "chapters", "tex")
    for num in TEST_CHAPTERS:
        g = os.path.join(cg_dir, f"gold_standard_chapter{num}.json")
        if not os.path.exists(g):
            print(f"WARN  chapter Chapter{num}: missing gold {g} -- skipping")
            continue
        label = f"Chapter{num}"
        tex = os.path.join(ctex_dir, f"chapter{num}.tex")
        if not os.path.exists(tex):
            print(f"WARN  chapter {label}: missing tex {tex} -- skipping")
            continue
        shutil.copy(g, os.path.join(args.out, f"{label}_gold.json"))
        shutil.copy(tex, os.path.join(args.out, f"{label}.tex"))
        print(f"chapter  {label}")
        n += 1

    print(f"\n{n} test documents assembled in {args.out}")
    print(f"Use:  python3 run_all.py --split test --test-dir {args.out}")
    print(f"or:   python3 grade_all.py --submissions <dir> --test-dir {args.out}")


if __name__ == "__main__":
    main()
