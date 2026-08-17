#!/usr/bin/env python3
"""Index the opus-5 v5.1 corpus into corpus/silver/metadata.csv (additively).

Why this is separate from build_silver_corpus.py
------------------------------------------------
That builder MIRRORS three external/portal source dirs into corpus/silver/, and
it starts by wiping every `<model>__<prompt>` dir. opus-5__v5.1 is different: it
is AUTHORITATIVE IN PLACE — the 200 JSONs under corpus/silver/opus-5__v5.1/ are
the only copy (they are committed; there is no external source to re-mirror
from). Folding it into the mirroring builder would mean a rebuild run on a
machine without the external pool deletes it.

So this script is additive and non-destructive: it rewrites ONLY the v5.1 rows
of metadata.csv and leaves every other row byte-identical. Idempotent.

Also stamps the `span_usable` column on every row — see --help of
scripts/audit_verbatim.py and corpus/silver/README.md. opus-4.7/v3_combined is
`no`: that prompt never asked for verbatim text, and a 50-paper audit found only
0.34% of its statements are literal spans of the source .tex.

Usage:
    python scripts/index_opus5_v51.py [--dry-run]
"""
import argparse
import csv
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILVER = os.path.join(REPO, "corpus/silver")
CORPUS = os.path.join(SILVER, "opus-5__v5.1")
TEX_POOL = os.path.join(SILVER, "tex_pool")
META = os.path.join(SILVER, "metadata.csv")
SPLIT_CSV = os.path.join(SILVER, "split_opus5.csv")
TARGETS = os.path.join(SILVER, "extraction_targets_opus5.csv")

MODEL = "opus-5"
PROMPT = "v5.1"
PROMPT_FILE = "scripts/opus_extract_prompt_v5_1.md"

# Which extraction configs produce literal spans of the source .tex, and so may
# be used for distillation / evaluation / plagiarism / alignment work.
# Measured Aug 2026, 50-paper random sample per config (seed 42).
SPAN_USABLE = {
    ("opus-5", "v5.1"): "yes",          # 99.73% literal, 0.00% paraphrase
    ("opus-4.8", "v4.1"): "yes",        # 89.57% literal, 0.47% paraphrase
    ("opus-4.7", "v4.1"): "yes",        # same prompt as above
    ("opus-4.7", "v3_combined"): "no",  # 0.34% literal, 93.26% paraphrase
}

NEW_COL = "span_usable"


def load_rows(path):
    if not os.path.isfile(path):
        sys.exit("missing %s — run build_silver_corpus.py first" % path)
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows, cols = load_rows(META)
    if NEW_COL not in cols:
        cols = cols + [NEW_COL]

    if not os.path.isfile(SPLIT_CSV):
        sys.exit("missing %s — run scripts/assign_split_opus5.py first" % SPLIT_CSV)
    split = {r["arxiv_id"]: r["split"]
             for r in csv.DictReader(open(SPLIT_CSV, encoding="utf-8"))}
    tgt = {r["arxiv_id"]: r
           for r in csv.DictReader(open(TARGETS, encoding="utf-8"))}

    kept = [r for r in rows if not (r.get("model") == MODEL
                                    and r.get("prompt_version") == PROMPT)]
    replaced = len(rows) - len(kept)

    new = []
    missing_split = []
    for jp in sorted(glob.glob(os.path.join(CORPUS, "*.json"))):
        aid = os.path.basename(jp)[:-5]
        doc = json.load(open(jp, encoding="utf-8"))
        meta = doc.get("metadata", {}) or {}
        if aid not in split:
            missing_split.append(aid)
            continue
        t = tgt.get(aid, {})
        tex_rel = os.path.relpath(os.path.join(TEX_POOL, aid + ".tex"), REPO)
        new.append({
            "paper_id": aid,
            "arxiv_id": aid,
            "arxiv_source": "filename",
            "arxiv_match_score": "",
            "split": split[aid],
            "test_idx": "", "tier": "",
            "model": MODEL,
            "prompt_version": PROMPT,
            "prompt_version_raw": meta.get("prompt_version", PROMPT),
            "prompt_file": PROMPT_FILE,
            "extraction_date": meta.get("extraction_date", ""),
            "annotator": meta.get("annotator", ""),
            "primary_category": t.get("category_arxiv", ""),
            "all_categories": "", "published": t.get("year", ""),
            "title": meta.get("title", ""),
            "short_name": "", "topic": "",
            "n_nodes": len(doc.get("nodes", [])),
            "n_edges": len(doc.get("edges", [])),
            "json_path": os.path.relpath(jp, REPO),
            "tex_path": tex_rel,
            # tex_pool is gitignored (regenerable via fetch_tex_for_targets.py),
            # so has_tex is about THIS checkout, not about the corpus.
            "has_tex": "yes" if os.path.isfile(os.path.join(TEX_POOL, aid + ".tex")) else "no",
            NEW_COL: SPAN_USABLE[(MODEL, PROMPT)],
        })

    if missing_split:
        sys.exit("%d extracted paper(s) have no split assignment; re-run "
                 "scripts/assign_split_opus5.py: %s"
                 % (len(missing_split), ", ".join(missing_split[:5])))

    # Fail SAFE: an extraction config we have not audited is "no", never blank.
    # A blank would pass a `span_usable != "no"` filter, so a future prompt
    # revision would be silently trusted for span-level work before anyone has
    # checked whether it actually copies from the .tex. Unproven == unusable;
    # add a row to SPAN_USABLE once it has been audited.
    unaudited = set()
    for r in kept:
        key = (r.get("model"), r.get("prompt_version"))
        if key not in SPAN_USABLE:
            unaudited.add(key)
        r[NEW_COL] = SPAN_USABLE.get(key, "no")

    out = kept + new
    from collections import Counter
    print("metadata.csv: %d existing rows kept (%d v5.1 rows replaced), "
          "%d v5.1 rows written -> %d total" % (len(kept), replaced, len(new), len(out)))
    print("  v5.1 split:", dict(Counter(r["split"] for r in new)))
    print("  span_usable:", dict(Counter((r.get("model"), r.get("prompt_version"),
                                          r[NEW_COL]) for r in out)))
    if unaudited:
        print("  WARNING %d config(s) not in SPAN_USABLE -> marked 'no' "
              "(unaudited, so not trusted for span-level work): %s"
              % (len(unaudited), ", ".join("%s/%s" % k for k in sorted(unaudited))))
    n_tex = sum(1 for r in new if r["has_tex"] == "yes")
    print("  v5.1 tex present in this checkout: %d/%d "
          "(tex_pool is gitignored; refetch with fetch_tex_for_targets.py)"
          % (n_tex, len(new)))

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    with open(META, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, restval="")
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in cols})
    print("\nwrote %s" % os.path.relpath(META, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
