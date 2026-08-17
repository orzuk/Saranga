#!/usr/bin/env python3
"""Isolate the METRIC's contribution to the rule-extractor scores.

The distillation headline is F1 0.711 -> 0.735 on the 17-paper train set, but
precision FALLS (0.781 -> 0.736) while recall rises. Yaron's reading is that a
share of those "false positives" are good extractions the scorer cannot credit.
This measures that, by holding the extractor fixed and varying only the scorer.

What the current scorer cannot express (silver_distillation_merged.metrics):
it receives PLAIN TEXT LISTS bucketed per (paper, type) and greedy-matches 1-to-1.
So

  type mismatch  a theorem extracted as a proposition is only ever compared
                 against the proposition gold bucket -> one FP *and* one FN,
                 with the text never examined
  split          gold A extracted as A1+A2 -> one matches, the other is an FP
  merge          gold A,B extracted as one AB -> one matches, the other an FN

Three scorers over the SAME extracted/gold items:

  per_type   the current behaviour, reproduced here as the control
  crosstype  one pool per paper; a cross-type pair is allowed but its score is
             multiplied by node_similarity's graded TYPE_COMPAT, so
             theorem/proposition is cheap and theorem/definition is not
  grouped    crosstype, plus n:m group alignment from graph_similarity, so a
             split or merged statement can match as a group

Usage:
    python3 scripts/eval_metric_comparison.py --limit 20
    python3 scripts/eval_metric_comparison.py                # all papers
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for sub in ("src", "src/LLMVersion", "scripts"):
    sys.path.insert(0, str(REPO / sub))

import silver_distillation_merged as sdm                   # noqa: E402
import silver_distillation_sequential as seq               # noqa: E402
import node_similarity as NS                               # noqa: E402
import graph_similarity as GS                              # noqa: E402

THRESHOLD = 0.7
SILVER_JSON = REPO / "portal/data/tier2_test/json"
# parse_buckets expects <tex_dir>/<pid>/source/*.tex, but tier2_test stores the
# sources flat. Stage the expected layout rather than changing the harness, so
# the extraction path stays byte-identical to the one that produced the
# published numbers.
_FLAT_TEX = REPO / "portal/data/tier2_test/tex"
TEX_DIR = Path(os.environ.get("SARANGA_EVAL_STAGE",
                              "/tmp/saranga_eval_stage"))


def _stage_tex():
    made = 0
    for f in sorted(_FLAT_TEX.glob("*.tex")):
        d = TEX_DIR / f.stem / "source"
        d.mkdir(parents=True, exist_ok=True)
        t = d / f.name
        if not t.exists():
            t.write_bytes(f.read_bytes())
            made += 1
    return made
EVAL_DIR = REPO / "src/LLMVersion/merged_eval_silver_001_011_v3"


def _sim(a, b):
    """The harness's own text similarity, unchanged, so only the MATCHING
    strategy differs between scorers."""
    return sdm.jaccard_similarity(a, b)


def _type_factor(t1, t2):
    """Graded type compatibility from node_similarity (identical -> 1.0)."""
    if t1 == t2:
        return 1.0
    return NS.TYPE_COMPAT.get((t1, t2), NS.TYPE_COMPAT.get((t2, t1), 0.0))


def score_per_type(ext, gold):
    """Control: exactly what the harness does today, bucketed by type."""
    tp = ne = ng = 0
    for t in set(list(ext) + list(gold)):
        m = sdm.metrics(ext.get(t, []), gold.get(t, []), THRESHOLD)
        tp += m["tp"]; ne += m["n_extracted"]; ng += m["n_gold"]
    return tp, tp, ne, ng


def _flat(d):
    return [(t, s) for t, items in d.items() for s in items]


def score_crosstype(ext, gold):
    """One pool per paper; cross-type pairs allowed at a graded discount."""
    E, G = _flat(ext), _flat(gold)
    pairs = []
    for i, (te, se) in enumerate(E):
        for j, (tg, sg) in enumerate(G):
            f = _type_factor(te, tg)
            if f <= 0:
                continue
            s = _sim(se, sg) * f
            if s >= THRESHOLD:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    mi, mj = set(), set()
    for s, i, j in pairs:
        if i in mi or j in mj:
            continue
        mi.add(i); mj.add(j)
    return len(mi), len(mj), len(E), len(G)


def score_grouped(ext, gold):
    """crosstype + n:m groups, so a split or merged statement can match.

    A gold item is credited if the CONCATENATION of the extracted items that
    overlap it clears the threshold, and vice versa — the coverage idea from
    graph_similarity, applied to the text lists this harness works in.
    """
    E, G = _flat(ext), _flat(gold)
    used_e, used_g = set(), set()
    tp = 0
    # 1-to-1 first, so unambiguous matches are not consumed by a group.
    pairs = []
    for i, (te, se) in enumerate(E):
        for j, (tg, sg) in enumerate(G):
            f = _type_factor(te, tg)
            if f <= 0:
                continue
            s = _sim(se, sg) * f
            if s >= THRESHOLD:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    for s, i, j in pairs:
        if i in used_e or j in used_g:
            continue
        used_e.add(i); used_g.add(j); tp += 1
    # Then groups: an unmatched gold item vs the pooled leftover extracted text
    # of a compatible type (a SPLIT), and the mirror case (a MERGE).
    for j, (tg, sg) in enumerate(G):
        if j in used_g:
            continue
        cand = _group_members([E[i][1] for i in E_idx(E)], sg,
                              [i for i, (te, _s) in enumerate(E)
                               if i not in used_e and _type_factor(te, tg) > 0], E)
        if not cand:
            continue
        pooled = " ".join(E[i][1] for i in cand)
        if _sim(pooled, sg) >= THRESHOLD:
            used_g.add(j)
            for i in cand:
                used_e.add(i)
            tp += 1
    for i, (te, se) in enumerate(E):
        if i in used_e:
            continue
        cand = _group_members(None, se,
                              [j for j, (tg, _s) in enumerate(G)
                               if j not in used_g and _type_factor(te, tg) > 0], G)
        if not cand:
            continue
        pooled = " ".join(G[j][1] for j in cand)
        if _sim(se, pooled) >= THRESHOLD:
            used_e.add(i)
            for j in cand:
                used_g.add(j)
            tp += 1
    return len(used_e), len(used_g), len(E), len(G)



def E_idx(E):
    return range(len(E))


def _group_members(_unused, target, candidate_idx, pool):
    """Members of a split/merge group, with graph_similarity's OVERLAP GUARDS.

    Pooling every type-compatible leftover is what makes a group metric lie:
    concatenate enough unrelated text and containment against a short target
    goes to 1. graph_similarity solves this with a minimum shared-token count
    and a minimum Jaccard before two items may join a group; the same guards
    are applied here, plus its MAX_GROUP_SIZE cap.
    """
    tt = NS.tokenize(target)
    if not tt:
        return []
    keep = []
    for i in candidate_idx:
        ct = NS.tokenize(pool[i][1])
        if not ct:
            continue
        inter = len(tt & ct) if isinstance(tt, set) else len(set(tt) & set(ct))
        if inter < GS.DEFAULT_MIN_OVERLAP_TOKENS:
            continue
        union = len(set(tt) | set(ct))
        if union and inter / union < GS.DEFAULT_MIN_JACCARD:
            continue
        keep.append((inter, i))
    keep.sort(reverse=True)
    return [i for _n, i in keep[:GS.MAX_GROUP_SIZE]]

def prf(tp_e, tp_g, n_e, n_g):
    p = tp_e / n_e if n_e else 0.0
    r = tp_g / n_g if n_g else 0.0
    return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)


def gold_buckets(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for n in d.get("nodes") or []:
        t = n.get("type")
        if t not in sdm.FNAME_MAP:
            continue
        s = (n.get("statement_latex") or n.get("statement")
             or n.get("raw_latex") or "")
        if s:
            out.setdefault(t, []).append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    seq.set_match_metric("containment")         # what the headline numbers use
    types = list(sdm.FNAME_MAP)
    step00 = EVAL_DIR / "snapshots" / "step_00_initial"
    final = EVAL_DIR / "snapshots" / "step_17_paper450"

    _stage_tex()
    papers = sorted(p.stem for p in _FLAT_TEX.glob("*.tex")
                    if (SILVER_JSON / (p.stem + ".json")).exists())
    if a.limit:
        papers = papers[:a.limit]
    print("papers: %d   threshold %.2f   metric containment" % (len(papers), THRESHOLD))

    SCORERS = [("per_type  (current)", score_per_type),
               ("crosstype (graded)", score_crosstype),
               ("grouped   (n:m)", score_grouped)]
    acc = {(name, stage): [0, 0, 0, 0]
           for name, _ in SCORERS for stage in ("base", "final")}

    for k, pid in enumerate(papers, 1):
        gold = gold_buckets(SILVER_JSON / (pid + ".json"))
        if not gold:
            continue
        try:
            ext = {"base": sdm.parse_buckets(pid, TEX_DIR, types, eval_dir=step00),
                   "final": sdm.parse_buckets(pid, TEX_DIR, types, eval_dir=final)}
        except Exception as e:
            print("  skip %s (%s)" % (pid, str(e)[:60]))
            continue
        for name, fn_ in SCORERS:
            for stage in ("base", "final"):
                te, tg, ne, ng = fn_(ext[stage], gold)
                a_ = acc[(name, stage)]
                a_[0] += te; a_[1] += tg; a_[2] += ne; a_[3] += ng
        if k % 10 == 0:
            print("  ...%d/%d" % (k, len(papers)))

    print("\n  %-20s %-6s %7s %7s %7s %7s %7s %7s %7s"
          % ("scorer", "stage", "extOK", "gldOK", "nExt", "nGold", "P", "R", "F1"))
    base_f1 = {}
    for name, _ in SCORERS:
        for stage in ("base", "final"):
            te, tg, ne, ng = acc[(name, stage)]
            p, r, f1 = prf(te, tg, ne, ng)
            base_f1.setdefault(name, {})[stage] = f1
            print("  %-20s %-6s %7d %7d %7d %7d %7.3f %7.3f %7.3f"
                  % (name, stage, te, tg, ne, ng, p, r, f1))
        d = base_f1[name]["final"] - base_f1[name]["base"]
        print("  %-20s %-6s %46s dF1 %+0.3f" % ("", "", "", d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
