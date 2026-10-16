#!/usr/bin/env python3
"""Papers against their blueprints: the realistic test of an extractor on a blueprint's dependencies.

For each blueprint that closely follows one arXiv paper (survey table: source_latex 'arxiv', source_match
'restates' or 'reorganises'), the paper's LaTeX is fetched and extracted (rule set, cached in
corpus/gold_blueprints/<id>/paper/), and each blueprint statement is aligned with a result of the paper:
  1. by the number the blueprint gives it in its name ("[Lemma 3.2]"), through the paper's own numbering;
  2. the rest by statement similarity (node_metrics pairing, token overlap >= 0.5).
The extraction is then scored against the blueprint's dependencies among the aligned statements only
(graph_score presets 'author' and 'author_inv': path recall, precision among aligned results).

Writes <id>/paper/pair_scores.json and corpus/gold_blueprints/paper_pairs_summary.json.
    score_bp_papers.py [--threshold 0.5]
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src"), str(Path(__file__).resolve().parent), str(REPO / "portal")]
import graph_score as GS                                # noqa: E402
import latex_facts                                      # noqa: E402
import score_gold                                       # noqa: E402

BP = REPO / "corpus/gold_blueprints"
SURVEY = Path("/tmp/claude-1000/blueprint_survey/blueprints.jsonl")
_NUM = re.compile(r"(?i)\b(theorem|lemma|proposition|corollary|definition|claim|remark|conjecture|prop|thm|lem|cor|def)\.?\s*~?\s*"
                  r"([0-9A-Z]+(?:\.[0-9]+)*[a-z]?)\b")
_ABBR = {"prop": "proposition", "thm": "theorem", "lem": "lemma", "cor": "corollary", "def": "definition"}


_NOT_ONE_PAPER = {"teorth/expdb"}                       # a database of bounds from many papers


def pairs():
    out = []
    for r in map(json.loads, open(SURVEY)):
        ids = re.findall(r"\d{4}\.\d{4,5}", r.get("source_arxiv") or "")
        d = BP / r["repo"].replace("/", "__")
        m = json.loads((d / "meta.json").read_text()) if (d / "meta.json").is_file() else {}
        if (r["repo"] not in _NOT_ONE_PAPER and r.get("source_latex") == "arxiv" and r.get("source_match") in ("restates", "reorganises") and 1 <= len(ids) <= 2
                and m.get("n_proofs") and not m.get("degenerate")):
            out.append((d, ids[0]))
    return out


def align(bp_nodes, paper, tex, threshold):
    """{blueprint node id: paper node id}: by quoted number, then by statement similarity."""
    fx = latex_facts.extract_facts(tex)
    num_of_label = {lab: (v.get("number"), v.get("id")) for lab, v in fx.get("labels", {}).items()}
    facts = {f["id"]: f for f in fx.get("facts", [])}
    node_of_label = {lab: (v.get("node") if isinstance(v, dict) else v)
                     for lab, v in ((paper.get("metadata") or {}).get("labels") or {}).items()}
    node_of_label |= {n["label"]: n["id"] for n in paper["nodes"] if n.get("label")}
    by_num = {}
    for lab, (num, fid) in num_of_label.items():
        f = facts.get(fid)
        if num and f and lab in node_of_label:
            by_num[(f.get("type"), str(num))] = node_of_label[lab]
    out, taken = {}, set()
    for n in bp_nodes:
        m = _NUM.search(n.get("name") or "")
        if m:
            t = _ABBR.get(m.group(1).lower(), m.group(1).lower())
            p = by_num.get((t, m.group(2))) or next((v for (tt, num), v in by_num.items() if num == m.group(2)), None)
            if p and p not in taken:
                out[n["id"]] = p; taken.add(p)
    rest_b = [n for n in bp_nodes if n["id"] not in out]
    rest_p = [n for n in paper["nodes"] if n["id"] not in taken and n.get("type") not in GS._NOT_RESULTS]
    for i, (j, _) in GS.match_nodes(rest_p, rest_b, "m1g", "text", threshold).items():
        out[rest_b[j]["id"]] = rest_p[i]["id"]
    return out, sum(1 for n in bp_nodes if n["id"] in out and _NUM.search(n.get("name") or ""))


def one(d, aid, threshold):
    import build_blueprint_review as BR
    BR.our_paper(aid, d / "paper")                      # fetch + rule extraction, cached
    paper = json.loads((d / "paper/full.json").read_text())
    src = d / "paper/source"
    tex = latex_facts.read_tex(str(latex_facts.find_main_tex(src)))
    gold = json.loads((d / "graph.json").read_text())
    results = [n for n in gold["nodes"] if n.get("type") not in GS._NOT_RESULTS]
    a, by_number = align(results, paper, tex, threshold)
    # the alignment as shared labels, every other label dropped, so the scorer pairs exactly these nodes
    tag = {b: f"_al{k}" for k, b in enumerate(a)}
    gold = dict(gold, nodes=[{k: v for k, v in n.items() if k not in ("label", "labels")} | ({"labels": [tag[n["id"]]]} if n["id"] in tag else {})
                             for n in gold["nodes"]], metadata={})
    back = {p: tag[b] for b, p in a.items()}
    pred = dict(paper, nodes=[{k: v for k, v in n.items() if k not in ("label", "labels")} | ({"labels": [back[n["id"]]]} if n["id"] in back else {})
                              for n in paper["nodes"]], metadata={})
    keep = set(a) | {n["id"] for n in gold["nodes"] if n.get("type") in GS._NOT_RESULTS}
    gold["nodes"] = [n for n in gold["nodes"] if n["id"] in keep]      # aligned statements (and their proofs)
    out = {"arxiv": aid, "blueprint_statements": len(results), "aligned": len(a), "aligned_by_number": by_number,
           "paper_results": sum(n.get("type") not in GS._NOT_RESULTS for n in paper["nodes"])}
    for p in ("author", "author_inv"):
        c = GS.score(pred, gold, **{**GS.PRESETS[p], "skip_tags": ()})
        out[p] = c | GS.pooled([c])
    (d / "paper/pair_scores.json").write_text(json.dumps(out, indent=1))
    return d.name, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    res = {}
    for d, aid in pairs():
        try:
            k, out = one(d, aid, a.threshold)
            res[k] = out
            print(f"{k:45s} {aid:11s} aligned {out['aligned']:4d}/{out['blueprint_statements']:4d} "
                  f"(by number {out['aligned_by_number']:3d})  deps F1 {out['author']['edge_F1']:.2f} / inv {out['author_inv']['edge_F1']:.2f}", flush=True)
        except Exception as e:                          # noqa: BLE001
            print(f"{d.name:45s} {aid:11s} FAILED {e!r}"[:200], flush=True)
    s = {p: score_gold.summary({k: {"rules": {p: v[p]}} for k, v in res.items()}, ["rules"], [p])[f"rules/{p}"]
         for p in ("author", "author_inv")}
    s["coverage"] = {"pairs": len(res), "statements": sum(v["blueprint_statements"] for v in res.values()),
                     "aligned": sum(v["aligned"] for v in res.values())}
    (BP / "paper_pairs_summary.json").write_text(json.dumps(s, indent=1))
    print(json.dumps({p: {k: round(v, 3) for k, v in s[p].items() if k in ("node_F1", "edge_P", "edge_R", "edge_F1")} for p in ("author", "author_inv")}), s["coverage"])


if __name__ == "__main__":
    main()
