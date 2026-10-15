#!/usr/bin/env python3
"""Edge-level metrics: predicted graphs against reference (silver) graphs. The sibling of
node_metrics.py.

Nodes are aligned first with the m1g one-to-one pairing of node_metrics (token
containment >= 0.7, pairs weighted by node_similarity.type_compat). A predicted edge is
correct when its two endpoints map to the two endpoints of a reference edge, in the same
direction (relied-upon -> relier). The headline ignores edge types (any dependency counts);
a typed variant is reported too. Pooled (micro) over papers:

    precision = correct predicted edges / predicted edges
    recall    = reference edges found   / reference edges
    reachable = reference edges whose two endpoints were both aligned: the ceiling for
                any edge builder working on these nodes

The reference is collapsed to Level 1 first (node_similarity.collapse_to_level1: proof and
algorithm steps folded into their parent, their edges lifted onto it), which is what a graph
without step nodes can express at best. A predicted edge whose two ends align to the same
reference node (an equation and the theorem it sits in) is not a dependency in this sense:
it is dropped and counted as 'collapsed'.

    python3 src/LLMVersion/edge_metrics.py corpus/silver/opus-5.5__v6/tagger_v6 [more dirs] \
        [--split test] [--by-kind] [--keep-steps]
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "src")]
import match_modes as mm                                    # noqa: E402
import node_metrics as NM                                   # noqa: E402
import node_similarity as NS                                # noqa: E402
from graph_io import load_graph                             # noqa: E402

SILVER = REPO / "corpus/silver/opus-5.5__v6"
SPLIT = REPO / "corpus/silver/split_v6_6-2-2.csv"
RESULT = {"theorem", "lemma", "proposition", "corollary", "claim"}
STEPS = set(NS.LEVEL2_TYPES)


def pred_text(n) -> str:
    return n.get("raw_latex") or n.get("statement") or ""


def align(pred_nodes, ref_nodes, th=NM.THRESHOLD) -> dict:
    """{pred id: ref id}, the m1g one-to-one pairing."""
    P = [(n["type"], mm.tokens(pred_text(n))) for n in pred_nodes]
    G = [(n["type"], mm.tokens(n.get("statement") or "")) for n in ref_nodes]
    pairs = NM._one_to_one(P, G, NS.type_compat, th)
    return {pred_nodes[i]["id"]: ref_nodes[j]["id"] for i, (j, _w) in pairs.items()}


def level1(nodes, edges):
    """collapse_to_level1, after pointing every step at its top non-step ancestor (a step
    nested in a step would otherwise keep edges to a node that no longer exists)."""
    by_id = {n.get("id"): n for n in nodes}

    def owner(i):
        """The first non-step ancestor of step i (None if the chain breaks or loops)."""
        seen = set()
        while i in by_id and by_id[i].get("type") in STEPS and i not in seen:
            seen.add(i)
            i = by_id[i].get("parent_id")
        return i if i in by_id and by_id[i].get("type") not in STEPS else None
    flat = []
    for n in nodes:
        if n.get("type") in STEPS:
            o = owner(n.get("parent_id"))
            if o is not None:
                n = dict(n, parent_id=o)
        flat.append(n)
    return NS.collapse_to_level1(flat, edges)


def kind(t: str) -> str:
    return "result" if t in RESULT else ("step" if t in STEPS else t)


def edge_kind(e, ref_nodes) -> str:
    """Coarse category of a reference edge, for the breakdown."""
    a, b = kind(ref_nodes[e["source"]]["type"]), kind(ref_nodes[e["target"]]["type"])
    if e["type"] == "proves":
        return "proves"
    if "step" in (a, b):
        return "involves a step"
    if b == "proof" and a in ("definition", "result"):
        return f"{a} -> proof"
    return f"{a} -> X" if a in ("definition", "result", "equation") else "other"


def score_paper(pred, ref, keep_steps: bool = False) -> collections.Counter:
    """Counts for one paper; `pred` and `ref` are graph dicts or paths."""
    pn, pe = load_graph(pred)
    rn, re_ = load_graph(ref)
    if not keep_steps:
        rn, re_ = level1(rn, re_)
    c = collections.Counter()
    rnodes = {n["id"]: n for n in rn}
    m = align(pn, rn)
    aligned = set(m.values())
    redges = {(e["source"], e["target"]): e for e in re_ if e["source"] in rnodes and e["target"] in rnodes}
    rtyped = {(s, t, e["type"]) for (s, t), e in redges.items()}
    found = set()
    for e in pe:
        s, t = m.get(e["source"]), m.get(e["target"])
        if s is not None and s == t:
            c["collapsed"] += 1
            continue
        c["pred"] += 1
        if s is None or t is None:
            c["pred_unaligned"] += 1
        elif (s, t) in redges and (s, t) not in found:
            c["tp"] += 1
            found.add((s, t))
            c["tp_typed"] += (s, t, e.get("type")) in rtyped
    for (s, t), e in redges.items():
        k = edge_kind(e, rnodes)
        c["ref"] += 1
        c[f"ref|{k}"] += 1
        if s in aligned and t in aligned:
            c["reachable"] += 1
            c[f"reach|{k}"] += 1
        c[f"found|{k}"] += (s, t) in found
    return c


def prf(c) -> tuple:
    return NS.prf(c["tp"], c["tp"], c["pred"] - c["tp"], c["ref"] - c["tp"])


def split_ids(split: str | None) -> set | None:
    if not split or split == "all":
        return None
    return {r.get("arxiv_id") or r["paper_id"] for r in csv.DictReader(open(SPLIT)) if r["split"] == split}


def score_dir(pred_dir: Path, split: str | None = "test", ref_dir: Path = SILVER,
              keep_steps: bool = False) -> collections.Counter:
    keep = split_ids(split)
    tot = collections.Counter()
    for f in sorted(Path(pred_dir).glob("*.json")):
        if keep is not None and f.stem not in keep:
            continue
        r = Path(ref_dir) / f.name
        if r.is_file():
            tot += score_paper(f, r, keep_steps)
            tot["papers"] += 1
    return tot


def report(name: str, c, by_kind: bool = False) -> None:
    p, r, f = prf(c)
    ft = NS.prf(c["tp_typed"], c["tp_typed"], c["pred"] - c["tp_typed"], c["ref"] - c["tp_typed"])[2]
    print(f"{name:34} papers {c['papers']:3} | pred {c['pred']:6} ref {c['ref']:6} | P {p:.3f} R {r:.3f} "
          f"F1 {f:.3f} | typed F1 {ft:.3f} | reachable {c['reachable'] / max(1, c['ref']):.3f} | collapsed {c['collapsed']}")
    if by_kind:
        for k in sorted({k.split("|", 1)[1] for k in c if k.startswith("ref|")}, key=lambda k: -c[f"ref|{k}"]):
            g = c[f"ref|{k}"]
            print(f"    {k:22} ref {g:6}  reachable {c[f'reach|{k}'] / g:.3f}  found {c[f'found|{k}'] / g:.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pred_dirs", nargs="+")
    ap.add_argument("--split", default="test", help="train | val | test | all (default test)")
    ap.add_argument("--ref", default=str(SILVER), help="reference graphs, <paper>.json")
    ap.add_argument("--by-kind", action="store_true", help="recall per reference edge category")
    ap.add_argument("--keep-steps", action="store_true", help="score against the reference WITH its steps")
    a = ap.parse_args()
    for d in a.pred_dirs:
        tag = f" [{a.split}{', steps kept' if a.keep_steps else ''}]"
        report(Path(d).name + tag, score_dir(Path(d), a.split, Path(a.ref), a.keep_steps), a.by_kind)


if __name__ == "__main__":
    main()
