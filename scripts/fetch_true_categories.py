#!/usr/bin/env python3
"""Fetch each pool paper's TRUE primary category from the arXiv API.

`extraction_targets_opus5.csv` records only the category the paper was *sampled
from*. arXiv returns cross-listed papers for a category query, so that column is
not the primary listing (confirmed: 1609.00771v2 sits in the math_GR slot but is
primarily math.DS). Attributing per-subfield metrics to the sampled category
would therefore misfile cross-listed papers.

Writes corpus/silver/true_categories.csv with:
    arxiv_id, sampled_from, primary_category, all_categories, title

Purely additive - touches no extraction output.
"""
import csv, os, re, sys, time, urllib.request, xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(REPO, "corpus/silver/extraction_targets_opus5.csv")
OUT  = os.path.join(REPO, "corpus/silver/true_categories.csv")
API  = "http://export.arxiv.org/api/query?id_list=%s&max_results=%d"
NS   = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def fetch(ids):
    url = API % (",".join(ids), len(ids))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return ET.fromstring(r.read())
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def main():
    rows = list(csv.DictReader(open(POOL, encoding="utf-8")))
    # only the 100 actually extracted (batches 1-5, 1 per category per batch)
    bycat = {}
    for r in rows:
        bycat.setdefault(r["category"], []).append(r)
    want = []
    for b in range(5):
        for cat in sorted(bycat):
            for r in bycat[cat][b:b + 1]:
                want.append((r["arxiv_id"], r["category"]))

    sampled = dict(want)
    out = []
    for grp in chunks([a for a, _ in want], 50):
        # arXiv id_list wants bare ids (version suffix is accepted)
        root = fetch(grp)
        for e in root.findall("a:entry", NS):
            raw = e.findtext("a:id", "", NS)
            aid = raw.rsplit("/", 1)[-1] if raw else ""
            prim = e.find("arxiv:primary_category", NS)
            prim = prim.get("term") if prim is not None else ""
            cats = ";".join(c.get("term") for c in e.findall("a:category", NS))
            title = re.sub(r"\s+", " ", e.findtext("a:title", "", NS)).strip()
            base = aid.split("v")[0]
            key = next((k for k in sampled if k.split("v")[0] == base), aid)
            out.append({
                "arxiv_id": key,
                "sampled_from": sampled.get(key, ""),
                "primary_category": prim,
                "all_categories": cats,
                "title": title,
            })
        time.sleep(3)

    got = {o["arxiv_id"] for o in out}
    for aid, cat in want:
        if aid not in got:
            out.append({"arxiv_id": aid, "sampled_from": cat,
                        "primary_category": "", "all_categories": "", "title": ""})

    out.sort(key=lambda o: o["arxiv_id"])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["arxiv_id", "sampled_from",
                                          "primary_category", "all_categories", "title"])
        w.writeheader(); w.writerows(out)

    miss = sum(1 for o in out if not o["primary_category"])
    mism = [o for o in out if o["primary_category"]
            and o["primary_category"].replace(".", "_") != o["sampled_from"]]
    print("wrote %s  (%d rows, %d unresolved)" % (OUT, len(out), miss))
    print("primary != sampled_from: %d/%d" % (len(mism), len(out)))
    for o in mism:
        print("   %-16s sampled=%-10s primary=%-10s  %s"
              % (o["arxiv_id"], o["sampled_from"], o["primary_category"], o["title"][:58]))


if __name__ == "__main__":
    main()
