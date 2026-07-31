#!/usr/bin/env python3
"""Verbatim / anti-hallucination audit for extracted knowledge-graph JSONs.

The extraction prompts require every `statement` to be a literal span from the
source .tex (no paraphrase, no recall-from-memory). This is the automated gate
for that claim — the single most important quality check before trusting an
extraction run at scale.

For each node it asks: does `statement` appear in the .tex? Three tolerances,
applied in order, all of which the prompt explicitly permits as mechanical
cleanup (so they are NOT hallucinations):

  exact        — appears verbatim after whitespace collapse
  cleaned      — appears after also stripping \\label{...}, LaTeX comments,
                 and normalizing spacing inside math
  head         — the first --head-chars of the statement appears (catches
                 differing trailing cleanup / truncation)
  NOT FOUND    — none of the above → a genuine fabrication candidate

Usage:
    python scripts/audit_verbatim.py [--dir corpus/silver/opus-5__v5]
                                     [--tex-dir corpus/silver/tex]
                                     [--papers paper431,paper217] [--show 5]
Exit code is 1 if any NOT FOUND statements exist (usable as a CI gate).
"""
import argparse
import glob
import json
import os
import re
import sys


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def strip_comments(s):
    # drop % comments but keep escaped \%
    return re.sub(r"(?<!\\)%.*?$", "", s or "", flags=re.M)


def clean(s):
    s = strip_comments(s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\s+", "", s)          # ignore all spacing (math spacing varies)
    return s


def audit_paper(pid, json_path, tex_path, args):
    d = json.load(open(json_path, encoding="utf-8"))
    raw = open(tex_path, encoding="utf-8", errors="replace").read()
    tex_c = collapse(strip_comments(raw))
    tex_k = clean(raw)

    counts = {"exact": 0, "cleaned": 0, "head": 0, "missing": 0, "empty": 0}
    missing = []
    for n in d.get("nodes", []):
        st = collapse(n.get("statement", ""))
        if not st:
            counts["empty"] += 1
            continue
        if st in tex_c:
            counts["exact"] += 1
        elif clean(st) in tex_k:
            counts["cleaned"] += 1
        elif len(st) >= args.head_chars and clean(st[: args.head_chars]) in tex_k:
            counts["head"] += 1
        else:
            counts["missing"] += 1
            missing.append((n.get("id"), n.get("type"), st))
    return counts, missing, len(d.get("nodes", []))


def main():
    ap = argparse.ArgumentParser()
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--dir", default=os.path.join(REPO, "corpus/silver/opus-5__v5"))
    ap.add_argument("--tex-dir", action="append", default=None,
                    help="dir holding <paper>.tex; repeatable (default: corpus/silver/tex "
                         "and corpus/silver/tex_pool)")
    ap.add_argument("--papers", default=None)
    ap.add_argument("--head-chars", type=int, default=60)
    ap.add_argument("--show", type=int, default=5)
    args = ap.parse_args()

    tex_dirs = args.tex_dir or [os.path.join(REPO, "corpus/silver/tex"),
                                os.path.join(REPO, "corpus/silver/tex_pool")]

    def find_tex(pid):
        for d in tex_dirs:
            cand = os.path.join(d, pid.replace("/", "_") + ".tex")
            if os.path.isfile(cand):
                return cand
        return None

    if args.papers:
        pids = [p.strip() for p in args.papers.split(",") if p.strip()]
    else:
        pids = sorted(os.path.basename(f)[:-5] for f in glob.glob(os.path.join(args.dir, "*.json")))

    print("%-10s %6s %7s %8s %6s %11s" % ("paper", "nodes", "exact", "cleaned", "head", "NOT FOUND"))
    tot = {"exact": 0, "cleaned": 0, "head": 0, "missing": 0}
    n_nodes = 0
    all_missing = []
    for pid in pids:
        jp = os.path.join(args.dir, pid + ".json")
        tp = find_tex(pid)
        if not (os.path.isfile(jp) and tp):
            print("%-10s  (missing json or tex — skipped)" % pid)
            continue
        c, miss, nn = audit_paper(pid, jp, tp, args)
        n_nodes += nn
        for k in tot:
            tot[k] += c[k]
        flag = "" if c["missing"] == 0 else "   <-- REVIEW"
        print("%-10s %6d %7d %8d %6d %11d%s"
              % (pid, nn, c["exact"], c["cleaned"], c["head"], c["missing"], flag))
        all_missing += [(pid,) + m for m in miss]

    ok = tot["exact"] + tot["cleaned"] + tot["head"]
    print("\ntotal nodes with a statement: %d" % ok_total(tot))
    print("traceable to source: %d  (exact %d / cleaned %d / head %d)" % (
        ok, tot["exact"], tot["cleaned"], tot["head"]))
    print("NOT FOUND (fabrication candidates): %d" % tot["missing"])
    if ok_total(tot):
        print("verbatim fidelity: %.2f%%" % (100.0 * ok / ok_total(tot)))

    if all_missing:
        print("\n--- fabrication candidates (first %d) ---" % args.show)
        for pid, nid, ntype, st in all_missing[: args.show]:
            print("  %s %s [%s]: %s" % (pid, nid, ntype, st[:160]))
        return 1
    return 0


def ok_total(tot):
    return tot["exact"] + tot["cleaned"] + tot["head"] + tot["missing"]


if __name__ == "__main__":
    sys.exit(main())
