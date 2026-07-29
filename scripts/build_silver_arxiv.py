#!/usr/bin/env python3
"""Fill missing arxiv_id for the silver corpus via arXiv title search.

Reads corpus/silver/manifest.csv, finds distinct papers with no arxiv_id, queries
the arXiv API by title, and writes results into corpus/silver/.arxiv_cache.json
(paper_id -> {arxiv_id, primary_category, all_categories, published,
matched_title, score}). Then re-run build_silver_corpus.py to fold them in.

Rate-limited to be polite to the arXiv API (~3 s/request). Idempotent: cached
papers are skipped, so it resumes if interrupted. Fuzzy title-match score is
recorded so low-confidence matches can be reviewed.
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "corpus/silver")
MANIFEST = os.path.join(OUT, "manifest.csv")
CACHE = os.path.join(OUT, ".arxiv_cache.json")
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def query(title, retries=3):
    q = urllib.parse.urlencode({
        "search_query": 'ti:"%s"' % title.replace('"', ""),
        "max_results": 5,
    })
    url = "http://export.arxiv.org/api/query?" + q
    for attempt in range(retries):
        try:
            raw = urllib.request.urlopen(url, timeout=30).read()
            return ET.fromstring(raw)
        except Exception as e:
            if attempt == retries - 1:
                print("   ! query failed: %s" % e, file=sys.stderr)
                return None
            time.sleep(5)


def best_match(root, want_title):
    want = norm(want_title)
    best = None
    for entry in root.findall(ATOM + "entry"):
        cand = entry.findtext(ATOM + "title") or ""
        score = SequenceMatcher(None, want, norm(cand)).ratio()
        aid = entry.findtext(ATOM + "id") or ""
        aid = aid.rsplit("/abs/", 1)[-1]
        prim = entry.find(ARXIV + "primary_category")
        prim = prim.get("term") if prim is not None else ""
        cats = ";".join(c.get("term") for c in entry.findall(ATOM + "category"))
        published = (entry.findtext(ATOM + "published") or "")[:10]
        rec = {
            "arxiv_id": aid, "primary_category": prim, "all_categories": cats,
            "published": published, "matched_title": cand.strip(),
            "score": round(score, 3),
        }
        if best is None or score > best["score"]:
            best = rec
    return best


def main():
    cache = json.load(open(CACHE)) if os.path.isfile(CACHE) else {}

    # distinct papers lacking an arxiv id, with their best title
    want = {}
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r["paper_id"]
            if r["arxiv_id"]:
                continue
            if pid in cache and cache[pid].get("arxiv_id"):
                continue
            if r["title"] and (pid not in want or len(r["title"]) > len(want[pid])):
                want[pid] = r["title"]

    todo = sorted(want)
    print("papers needing lookup: %d" % len(todo))
    for i, pid in enumerate(todo, 1):
        title = want[pid]
        root = query(title)
        if root is None:
            cache[pid] = {"arxiv_id": "", "score": 0, "title_queried": title}
        else:
            m = best_match(root, title)
            cache[pid] = (m or {"arxiv_id": "", "score": 0})
            cache[pid]["title_queried"] = title
        flag = "" if cache[pid].get("score", 0) >= 0.9 else "  <-- LOW, review"
        print("  [%3d/%3d] %s -> %s (%.2f)%s" % (
            i, len(todo), pid, cache[pid].get("arxiv_id") or "NONE",
            cache[pid].get("score", 0), flag))
        json.dump(cache, open(CACHE, "w"), indent=1)  # checkpoint each step
        time.sleep(3)

    resolved = sum(1 for v in cache.values() if v.get("arxiv_id"))
    print("cache now holds %d entries, %d resolved" % (len(cache), resolved))


if __name__ == "__main__":
    main()
