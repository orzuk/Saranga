"""Atlas, step 2: resolve the citations of atlas_pilot.json's links to arXiv papers from the citing paper's own
bibliography (\\bibitem in the .tex, .bbl / .bib in the source tarball), matched to the arXiv metadata snapshot by
an explicit arXiv id or by title (+ first author's surname). Also step 1: keep only problems that are open
(open_problem, conjecture, or a problem whose text says it is open).

    python3 atlas_bib.py [--limit N]        -> atlas_bib.json
"""
import argparse, collections, json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
import provenance as PV                   # bibliography parsing, arXiv ids in entries, the arXiv tree index  # noqa: E402

AX = "/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data"
PAPERS = f"{AX}/all_arxiv_papers"
META = f"{AX}/arxiv-metadata-oai-snapshot.json"
OPEN = re.compile(r"\bopen\b|unsolved|unknown|remains|\bconjectur|question of|asked (?:whether|if)|\bwe ask\b|"
                  r"it would be interesting|not known|is there\b|does there exist|\?", re.I)
BARE_NEW = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b")
strip_v = lambda a: re.sub(r"v\d+$", "", a)


def norm(s):
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def segments(entry):
    """Candidate titles of an entry: bib title field, \\newblock pieces, quoted / \\emph{} / {\\em } spans, sentences."""
    c = []
    m = re.search(r"\btitle\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", entry, re.I | re.S)
    if m:
        c.append(m.group(1))
    c += re.split(r"\\newblock", entry)
    c += re.findall(r"``(.+?)''", entry, re.S) + re.findall(r"\\(?:emph|textit|textsl)\{([^{}]+)\}", entry)
    c += re.findall(r"\{\\(?:em|it|sl)\s+([^{}]+)\}", entry)
    c += re.split(r"[.,;:]\s", entry)
    return [n for n in (norm(x) for x in c) if len(n.split()) >= 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    pilot = json.load(open("atlas_pilot.json"))
    links = [l for l in pilot["links"] if l["kind"] != "restated" or l["type"] != "problem" or OPEN.search(l["text"])]
    st = collections.Counter(f"{l['kind']}:{l.get('type', '')}" for l in pilot["links"])
    kept = collections.Counter(f"{l['kind']}:{l.get('type', '')}" for l in links)
    print("links before", dict(st), "\nafter open filter", dict(kept), flush=True)
    if a.limit:
        keep = sorted({l["paper"] for l in links})[:a.limit]
        links = [l for l in links if l["paper"] in set(keep)]
    need = collections.defaultdict(set)
    for l in links:
        for c in l["cited"]:
            if not c.get("arxiv"):
                need[l["paper"]].add(c["key"])

    # arXiv titles
    titles, surname, date = {}, {}, {}
    with open(META) as fh:
        for line in fh:
            r = json.loads(line)
            t = norm(r.get("title"))
            if len(t.split()) >= 3:
                titles.setdefault(t, r["id"])
            ap_ = r.get("authors_parsed") or []
            surname[r["id"]] = {norm(x[0]) for x in ap_[:6] if x}
            v = r.get("versions") or [{}]
            date[r["id"]] = (v[0].get("created") or "")[5:16]
    print(len(titles), "arXiv titles", flush=True)

    dirs = PV.arxiv_source_dirs(PAPERS)
    print(len(dirs), "paper folders", flush=True)
    resolved, how, info = {}, collections.Counter(), {}
    for i, (p, keys) in enumerate(need.items()):
        if p not in dirs:
            how["no_source"] += len(keys)
            continue
        src = dirs[p]
        tex = next(iter(sorted(src.glob("*.tex"))), src / "_")
        bib = {k: v["text"] for k, v in PV.bibliography(tex, src_dir=src).items()}
        for k in keys:
            e = bib.get(k)
            if e is None:
                how["key_not_in_bib"] += 1
                continue
            ys = [int(y) for y in re.findall(r"(?<!\d)((?:18|19|20)\d\d)(?!\d)", e) if 1850 <= int(y) <= 2026]
            info[(p, k)] = {"bib_year": ys[-1] if ys else None, "entry": " ".join(e.split())[:300]}
            m = BARE_NEW.search(e)
            aid = PV.arxiv_id_in(e) or (m.group(1) if m else None)
            if aid and aid in surname:
                resolved[(p, k)] = (aid, "id")
                how["by_id"] += 1
                continue
            ne = norm(e)
            hit = None
            for s in segments(e):
                cand = titles.get(s)
                if cand and cand != p and (not surname[cand] or any(x and x in ne.split() for x in surname[cand])):
                    hit = cand
                    break
            if hit:
                resolved[(p, k)] = (hit, "title")
                how["by_title"] += 1
            else:
                how["unmatched"] += 1
        if i % 2000 == 0:
            print(i, len(need), dict(how), flush=True)
    print("keys", dict(how), flush=True)

    res = collections.Counter()
    for l in links:
        for c in l["cited"]:
            if not c.get("arxiv") and (l["paper"], c["key"]) in resolved:
                c["arxiv"], c["via"] = resolved[(l["paper"], c["key"])]
            elif c.get("arxiv"):
                c.setdefault("via", "theoremgraph")
            c.update(info.get((l["paper"], c["key"]), {}))
            if c.get("arxiv"):
                c["arxiv_date"] = date.get(c["arxiv"], "")
        l["paper_date"] = date.get(l["paper"], "")
        res[(l["kind"], "any_cite_to_arxiv")] += any(c.get("arxiv") for c in l["cited"])
        res[(l["kind"], "any_cite_dated")] += any(c.get("arxiv") or c.get("bib_year") for c in l["cited"])
        res[(l["kind"], "total")] += 1
    out = {f"{k}:{v}": n for (k, v), n in sorted(res.items())}
    print(out, flush=True)
    json.dump({"filter": dict(kept), "keys": dict(how), "resolution": out, "links": links}, open("atlas_bib.json", "w"))


if __name__ == "__main__":
    main()
