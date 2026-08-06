#!/usr/bin/env python3
"""Fetch arXiv LaTeX sources for extraction targets into a local staging dir.

Keeps the flaky network work out of the extraction agents: this downloads
`arxiv.org/e-print/<id>`, picks the main .tex, and writes it to
corpus/silver/tex_pool/<arxiv_id>.tex so agents just read a local file.

Handles: .tar.gz bundles (picks the main tex — the one with \\documentclass,
else the largest), single gzipped .tex, and plain .tex. Skips ids already
fetched (resumable). Rate-limited to be polite to arXiv.

Usage:
    python scripts/fetch_tex_for_targets.py --ids 1710.09079v3,1104.1135v3
    python scripts/fetch_tex_for_targets.py --batch 1 --per-cat 1   # 1/category
"""
import argparse
import csv
import gzip
import io
import os
import re
import sys
import tarfile
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(REPO, "corpus/silver/extraction_targets_opus5.csv")
OUT = os.path.join(REPO, "corpus/silver/tex_pool")
UA = "Saranga-research/1.0 (mailto:or.zuk@mail.huji.ac.il)"


INPUT_RE = re.compile(rb"\\(?:input|include)\s*\{([^}]+)\}")


def _resolve_member(name, members):
    """Find a tar member matching an \\input{name} reference (tex ext optional)."""
    cands = [name, name + ".tex", name.lstrip("./"), name.lstrip("./") + ".tex"]
    for c in cands:
        if c in members:
            return c
    base = os.path.basename(name)
    for c in (base, base + ".tex"):
        for m in members:
            if os.path.basename(m) == c:
                return m
    return None


def inline_inputs(body, members, depth=0, seen=None):
    """Recursively splice \\input{}/\\include{} members into `body`.

    Multi-file papers keep their real content in \\input'ed files; without this
    the extraction sees only the shell (missing intro/results/appendices).
    Figure includes (.pdf_tex/.pdf_t) and missing members are left untouched.
    """
    if depth > 6:
        return body
    seen = seen if seen is not None else set()

    def sub(m):
        ref = m.group(1).decode("utf-8", "replace").strip()
        if ref.endswith((".sty", ".cls", ".bst", ".bbl", ".aux",
                         ".pdf_tex", ".pdf_t", ".pstex_t")):
            return m.group(0)
        tgt = _resolve_member(ref, members)
        if not tgt or tgt in seen:
            return m.group(0)
        seen.add(tgt)
        inner = inline_inputs(members[tgt], members, depth + 1, seen)
        return b"\n%% [inlined " + tgt.encode() + b"]\n" + inner + b"\n"

    return INPUT_RE.sub(sub, body)


def pick_main_tex(members_bytes):
    """From {name: bytes} choose the main .tex, with \\input files spliced in."""
    texs = {n: b for n, b in members_bytes.items() if n.lower().endswith(".tex")}
    if not texs:
        return None, None
    # Score every candidate rather than taking the first with a preamble: a
    # submission can ship several compilable .tex files (a standalone figure or
    # table file carries its own \documentclass), and tar order is arbitrary.
    # 1505.06386v1 picked a 3 KB fig/all.tex over the 64 KB real body this way.
    def score(n):
        b = texs[n]
        return (bool(re.search(rb"\\documentclass", b)),
                bool(re.search(rb"\\begin\{document\}", b)),
                bool(re.search(rb"\\title", b)),
                len(b))

    main = max(texs, key=score)
    return main, inline_inputs(members_bytes[main], members_bytes)


def fetch_one(aid, retries=3):
    url = "https://arxiv.org/e-print/%s" % aid
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=90).read()
            break
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    else:
        return None, "download failed: %s" % last

    # tar bundle?
    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw))
        mb = {}
        for m in tf.getmembers():
            if m.isfile() and m.name.lower().endswith(".tex"):
                mb[m.name] = tf.extractfile(m).read()
        name, body = pick_main_tex(mb)
        if body is None:
            return None, "tar contained no .tex"
        return body, "tar:%s" % name
    except tarfile.ReadError:
        pass

    # single gzipped file?
    try:
        body = gzip.decompress(raw)
        return body, "gz"
    except Exception:
        pass

    # plain?
    if raw.lstrip()[:1] in (b"\\", b"%"):
        return raw, "plain"
    return None, "unrecognized format (%d bytes)" % len(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default=None, help="comma list of arxiv ids")
    ap.add_argument("--batch", type=int, default=None,
                    help="batch number (1-based); takes the Nth paper of each category")
    ap.add_argument("--per-cat", type=int, default=1)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--out-dir", default=OUT,
                    help="where to write <id>.tex; default = the silver tex pool. "
                         "Use corpus/gold/tex for the gold set.")
    args = ap.parse_args()

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    else:
        rows = list(csv.DictReader(open(POOL, encoding="utf-8")))
        bycat = {}
        for r in rows:
            bycat.setdefault(r["category"], []).append(r)
        lo = (args.batch - 1) * args.per_cat
        hi = lo + args.per_cat
        ids = [r["arxiv_id"] for c in sorted(bycat) for r in bycat[c][lo:hi]]

    print("fetching %d sources -> %s" % (len(ids), os.path.relpath(out_dir, REPO)))
    ok = skip = fail = 0
    failures = []
    for i, aid in enumerate(ids, 1):
        dst = os.path.join(out_dir, aid.replace("/", "_") + ".tex")
        if os.path.isfile(dst) and os.path.getsize(dst) > 500:
            print("  [%2d/%d] %-16s already have" % (i, len(ids), aid))
            skip += 1
            continue
        body, how = fetch_one(aid)
        if body is None:
            print("  [%2d/%d] %-16s FAIL %s" % (i, len(ids), aid, how))
            fail += 1
            failures.append((aid, how))
        else:
            open(dst, "wb").write(body)
            print("  [%2d/%d] %-16s ok %6d bytes (%s)" % (i, len(ids), aid, len(body), how))
            ok += 1
        time.sleep(args.delay)

    print("\nfetched=%d  already-had=%d  failed=%d" % (ok, skip, fail))
    for aid, why in failures:
        print("  FAILED %s: %s" % (aid, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
