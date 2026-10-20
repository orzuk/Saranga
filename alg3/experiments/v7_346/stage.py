"""Stage the v7 pool of 346 papers for alg3 (gitignored, symlinks only) -> alg3/cache/v7_346/:
    silver/<pid>.json        v7 graphs: corpus/silver/opus-5.5__v7 (200) + opus-5.5__v7_gold (146)
    tex/<pid>/source/<pid>.tex  sources: corpus/silver/tex_staged (silver), tex_pool (gold, diagram stripped)
    split_A.csv  split_v7_346.csv as is (210/68/68)
    split_S.csv  only the 200 silver papers train/val (the gold train/val rows -> 'unused'; test kept)
    split_G.csv  only the 146 gold-author papers train/val (likewise)
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
S = REPO / "corpus/silver"
OUT = REPO / "alg3/cache/v7_346"

rows = list(csv.DictReader(open(S / "split_v7_346.csv", encoding="utf-8")))
(OUT / "silver").mkdir(parents=True, exist_ok=True)
for r in rows:
    pid, gold = r["arxiv_id"], r["source"] == "gold_author"
    j = S / ("opus-5.5__v7_gold" if gold else "opus-5.5__v7") / f"{pid}.json"
    t = S / "tex_pool" / f"{pid}.tex" if gold else S / "tex_staged" / pid / "source" / f"{pid}.tex"
    assert j.is_file() and t.is_file(), pid
    dj, dt = OUT / "silver" / f"{pid}.json", OUT / "tex" / pid / "source" / f"{pid}.tex"
    dt.parent.mkdir(parents=True, exist_ok=True)
    for d, src in ((dj, j), (dt, t)):
        if not d.exists():
            d.symlink_to(src)
for tag, keep in (("A", {"silver", "gold_author"}), ("S", {"silver"}), ("G", {"gold_author"})):
    with open(OUT / f"split_{tag}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow(dict(r, split="unused") if r["source"] not in keep and r["split"] != "test" else r)
print(f"staged {len(rows)} papers -> {OUT}")
