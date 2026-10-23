#!/usr/bin/env python3
"""Atlas, step 4: time to resolution and stale open problems, from the judged links.

    atlas_analyze.py --links links_rc.json --verdicts verdicts.json --ext ext_candidates.json \
                     --ext-verdicts ext_cands_verdicts.tsv --kourovka kourovka.json --out atlas_report.json

Inputs: links_rc.json (the restated / claim links of atlas_bib.json, numbered by lid), verdicts.json (the LLM
pass, INSTRUCTIONS.md: lid -> [lid, KEEP, STATUS, SRC, NAME, POSER, NOTE]), the AI-claim matches
(join_external.py + their judged verdicts) and the parsed Kourovka Notebook (parse_kourovka.py).

Time to resolution: a claim that settles a problem in full (proved / disproved / answered) and cites where the
problem was posed (SRC = origin) gives  year of the claiming paper - year of the cited source.
Stale: a problem restated as open with its source cited (SRC = origin), grouped by its normalized name over
papers; age = latest open mention - earliest source year. A group is flagged AI-claimed when any of its links
matches (same) a VibeMathed or OpenAI entry, and resolved-in-corpus when some claim of the corpus settles a
problem of the same name. A second run with --group-cands / --group-verdicts adds the name-level AI matches
(each stale group's name against every VibeMathed / OpenAI / whataifound entry, judged).
"""
import argparse
import collections
import json
import re
import statistics

FULL = {"proved", "disproved", "answered"}
STOP = {"the", "of", "a", "an", "on", "for", "in", "and", "to", "conjecture", "problem", "question", "open", "s"}


def year(s):
    m = re.search(r"(?:18|19|20)\d\d", s or "")
    return int(m.group()) if m else None


def key(name):
    """A grouping key for a problem name: its content words, sorted."""
    w = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower().replace("erdős", "erdos").replace("'s", "")).split()
    return " ".join(sorted({x for x in w if x not in STOP}))


def source_year(link):
    """Year of the first cited source with a year: the arXiv date, else the bibliography year."""
    for c in link["cited"]:
        y = year(c.get("arxiv_date")) or c.get("bib_year")
        if y:
            return y
    return None


def quantiles(xs):
    xs = sorted(xs)
    q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]          # noqa: E731
    return {"n": len(xs), "median": statistics.median(xs), "q25": q(.25), "q75": q(.75), "q90": q(.9)} if xs else {"n": 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for a in ("links", "verdicts", "ext", "ext_verdicts", "kourovka", "out"):
        ap.add_argument("--" + a.replace("_", "-"), required=True)
    ap.add_argument("--group-cands", help="name-level AI-claim candidates (group_cands.json) of a first run")
    ap.add_argument("--group-verdicts", help="their judged verdicts (k, same/variant/no, note)")
    a = ap.parse_args()
    by_name = collections.defaultdict(set)
    if a.group_cands and a.group_verdicts:
        gc = json.load(open(a.group_cands))
        for line in open(a.group_verdicts):
            f = line.rstrip("\n").split("\t")
            if f[0].isdigit() and f[1] == "same":
                by_name[gc[int(f[0])]["name"]].add(gc[int(f[0])]["ext"])
    L = json.load(open(a.links))
    V = {int(k): v for k, v in json.load(open(a.verdicts)).items()}

    # AI-claimed links (judged 'same' as a VibeMathed / OpenAI entry)
    cands = json.load(open(a.ext))["tfidf"]
    ai = collections.defaultdict(list)
    for line in open(a.ext_verdicts):
        f = line.rstrip("\n").split("\t")
        if f[0].isdigit() and f[1] == "same":
            c = cands[int(f[0])]
            ai[c["lid"]].append(f'{c["ext"]}:{c["ext_id"]} ({c["ext_resolution"]})')

    # 1. time to resolution
    lags, by_status, examples = [], collections.defaultdict(list), []
    solved_keys = set()
    for i, v in V.items():
        l = L[i]
        if l["kind"] != "claim" or v[1] != "y":
            continue
        if v[2] in FULL:
            solved_keys.add(key(v[4]))
        py, sy = year(l.get("paper_date")), source_year(l)
        if v[2] in FULL and v[3] == "origin" and py and sy and 0 <= py - sy <= 150:
            lags.append(py - sy)
            by_status[v[2]].append(py - sy)
            examples.append((py - sy, l["paper"], v[4]))
    kour = [p["answer_year"] - p["year_posed"] for p in json.load(open(a.kourovka))
            if p.get("solved") and p.get("answer_year") and p.get("year_posed") and p["answer_year"] >= p["year_posed"]]
    ttr = {"atlas_claims_citing_origin": quantiles(lags), "by_status": {k: quantiles(x) for k, x in by_status.items()},
           "kourovka_archive": quantiles(kour),
           "longest": [{"years": y, "paper": p, "name": n} for y, p, n in sorted(examples, reverse=True)[:25]]}

    # 2. stale open problems
    groups = collections.defaultdict(lambda: {"names": collections.Counter(), "papers": set(), "src_years": [],
                                              "mention_years": [], "ai": set(), "posers": collections.Counter()})
    for i, v in V.items():
        l = L[i]
        if l["kind"] != "restated" or v[1] != "y" or v[2] not in ("open", "partial") or v[3] != "origin":
            continue
        k = key(v[4])
        if not k:
            continue
        g = groups[k]
        g["names"][v[4]] += 1
        g["papers"].add(l["paper"])
        if v[5] != "-":
            g["posers"][v[5]] += 1
        sy, py = source_year(l), year(l.get("paper_date"))
        if sy:
            g["src_years"].append(sy)
        if py:
            g["mention_years"].append(py)
        g["ai"].update(ai.get(i, []))
    rows = []
    for k, g in groups.items():
        if not g["src_years"] or not g["mention_years"]:
            continue
        name = g["names"].most_common(1)[0][0]
        g["ai"].update(by_name.get(name, ()))
        rows.append({"name": name, "poser": (g["posers"].most_common(1) or [("", 0)])[0][0],
                     "papers": len(g["papers"]), "source_year": min(g["src_years"]), "last_open_mention": max(g["mention_years"]),
                     "age": max(g["mention_years"]) - min(g["src_years"]), "ai_claimed": sorted(g["ai"]),
                     "resolved_in_corpus": k in solved_keys, "paper_ids": sorted(g["papers"])[:10]})
    rows.sort(key=lambda r: (-r["papers"], -r["age"]))
    stale = [r for r in rows if r["age"] >= 20 and not r["resolved_in_corpus"]]
    rep = {"time_to_resolution": ttr,
           "stale_summary": {"problem_groups": len(rows), "open_20y_plus": len(stale),
                             "of_which_ai_claimed": sum(1 for r in stale if r["ai_claimed"]),
                             "multi_paper_groups": sum(1 for r in rows if r["papers"] >= 2)},
           "stale": stale[:300], "all_groups": rows}
    json.dump(rep, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"time_to_resolution": {k: v for k, v in ttr.items() if k != "longest"},
                      "stale_summary": rep["stale_summary"]}, indent=1))
    print("\nmost-mentioned stale (>= 20 years, not resolved in corpus):")
    for r in stale[:25]:
        print(f'  {r["papers"]:3d} papers  {r["source_year"]}-{r["last_open_mention"]}  {r["name"][:60]}'
              + (f'  [AI: {", ".join(r["ai_claimed"])[:60]}]' if r["ai_claimed"] else ""))


if __name__ == "__main__":
    main()
