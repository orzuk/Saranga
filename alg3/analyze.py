#!/usr/bin/env python3
"""Errors of an extractor on the VALIDATION papers (never test).

Sentence mode: per-type errors of the alg3 tagger alone (prose sentences, base-covered
nodes neutral):

    python3 alg3/analyze.py --model alg3/runs/v1 [--examples 3]

Graph mode: the whole parsed graph (parser + rules, optionally + a learned edge model)
against the silver graph collapsed to Level 1, with the scorer's m1g node pairing
(node_metrics) and the edge alignment of edge_metrics. Node errors are split into

    wrong type   paired with a silver node of another type (m1g gives partial credit)
    ("inside" is tested by text position, not by shared words)
    spurious     unpaired prediction, by where it lies: inside a silver node that is paired
                 (an extra piece) or missed (a fragment of it; m3 forgives both), partial
                 overlap (Jaccard >= 0.3), or no overlap with any silver node
    missed       unpaired silver node: inside a larger prediction (granularity; its type and
                 whether it is paired), split into smaller predictions, partial overlap
                 (Jaccard >= 0.3), or none of these

and edge errors (Level-1 silver edges, kinds of edge_metrics.edge_kind) into missed
(no endpoint pair / endpoints aligned but no edge) and spurious (unaligned endpoint / both
aligned but not a silver edge / silver edge in the other direction). Graphs are parsed
once into alg3/runs/val_graphs/<name>/ (delete the folder to re-parse).

    python3 alg3/analyze.py --rules-dir extractors/rules/silver_v6__sentence_tagger__2026-10 \
        --edge-model extractors/edges/silver_v6__defterm_edges__2026-10 --name alg3_v2b_edges
"""
from __future__ import annotations

import argparse
import importlib.util
import pickle
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (HERE, REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_units as DU                                   # noqa: E402
import latex_facts as L                                      # noqa: E402
import train as TR                                           # noqa: E402


def load_runtime(model_dir: Path):
    sys.path.insert(0, str(model_dir))
    spec = importlib.util.spec_from_file_location("alg3_runtime", model_dir / "alg3_runtime.py")
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    return rt


def sentence_mode(a):
    papers = pickle.load(open(a.data, "rb"))
    val = sorted(p for p, (s, _) in papers.items() if s == "val")
    rt = load_runtime(Path(a.model))
    scorer = DU.Scorer({pid: p for pid, (_, p) in papers.items()}, 0.7, metric="m1g")
    by_type = defaultdict(lambda: Counter())
    conf = Counter()
    fps, fns = defaultdict(list), defaultdict(list)
    preds_all = {}
    for pid in val:
        p = papers[pid][1]
        preds = [dict(n, uid=0) for n in rt.tag(p.text, L.extract_facts(p.text), p.sents)]
        preds_all[pid] = preds
        m = scorer.match(p, preds, [TR.tokens(p, q) for q in preds])
        taken = {k for k, _ in m.values()}
        for i, pred in enumerate(preds):
            k, w = m.get(i, (None, 0.0))
            if k is not None:
                n = p.nodes[k]
                if n.base_covered:
                    by_type[pred["type"]]["neutral"] += 1
                    continue
                by_type[pred["type"]]["tp"] += w
                by_type[pred["type"]]["fp"] += 1 - w
                if n.type != pred["type"]:
                    conf[(n.type, pred["type"])] += 1
            else:
                by_type[pred["type"]]["fp"] += 1
                fps[pred["type"]].append((pid, p.text[pred["start"]:pred["end"]][:160]))
        for k, n in enumerate(p.nodes):
            if not n.base_covered:
                by_type[n.type]["gold"] += 1
            if k not in taken and not n.base_covered:
                fns[n.type].append((pid, p.text[n.start:n.end][:160]))
    print(TR.evaluate(scorer, papers, val, preds_all))
    print(f"\n{'type':<13}{'gold':>6}{'tp':>8}{'fp':>8}{'fn':>6}{'P':>7}{'R':>7}")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]["gold"]):
        tp, fp, g = c["tp"], c["fp"], c["gold"]
        print(f"{t:<13}{g:>6}{tp:>8.1f}{fp:>8.1f}{len(fns[t]):>6}"
              f"{(tp / (tp + fp) if tp + fp else 0):>7.2f}{(tp / g if g else 0):>7.2f}")
    print("\ntype confusions (silver -> predicted):", conf.most_common(8))
    rnd = random.Random(0)
    for t in ("definition", "claim", "remark", "theorem"):
        print(f"\n== {t}: sample FP")
        for x in rnd.sample(fps[t], min(a.examples, len(fps[t]))):
            print("   ", x[0], repr(x[1]))
        print(f"== {t}: sample FN")
        for x in rnd.sample(fns[t], min(a.examples, len(fns[t]))):
            print("   ", x[0], repr(x[1]))


# ── graph mode ──────────────────────────────────────────────────────────────
SPLIT = REPO / "corpus/silver/split_v6_6-2-2.csv"
SILVER = REPO / "corpus/silver/opus-5.5__v6"
TEX = REPO / "corpus/silver/tex_staged"
_W: dict = {}


def _parse_init(rules_dir, edge_model):
    import edges as ED
    _W["rules"] = rules_dir
    _W["edges"] = (ED, ED.EdgeModel(edge_model)) if edge_model else None


def _parse_one(job):
    """Parse one paper as parse_batch does (unified graph, + learned edges) into out."""
    import contextlib
    import io
    import json
    from math_paper_parser import PaperParser
    pid, out = job
    main = L.find_main_tex(TEX / pid / "source")
    d = {"nodes": [], "edges": []}
    if main:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                d = PaperParser(paper_id=pid, extraction_mode="rules",
                                rules_dir=_W["rules"]).parse_file(str(main)).to_unified_dict()
            if _W["edges"]:
                _W["edges"][0].add_edges(d, _W["edges"][1], tex=Path(main).read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:                                    # noqa: BLE001
            print(f"  [warn] parse failed for {pid}: {type(e).__name__}: {e}", flush=True)
    Path(out).write_text(json.dumps(d), encoding="utf-8")
    return pid


def val_ids(splits=("val",)) -> list:
    import csv
    assert "test" not in splits, "test is scored once, at the end, with compare_distillers"
    return sorted(r.get("arxiv_id") or r["paper_id"] for r in csv.DictReader(open(SPLIT))
                  if r["split"] in splits)


def parse_val(a) -> Path:
    """Parse the val papers (and --parse-train: the train papers too, e.g. to train
    alg3/edges.py on graphs of the current code) into alg3/runs/val_graphs/<name>/."""
    import multiprocessing as mp
    out = HERE / "runs/val_graphs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    pids = val_ids(("train", "val") if a.parse_train else ("val",))
    todo = [(pid, str(out / f"{pid}.json")) for pid in pids if not (out / f"{pid}.json").is_file()]
    if todo:
        print(f"parsing {len(todo)} papers -> {out}", flush=True)
        with mp.Pool(a.workers, initializer=_parse_init, initargs=(a.rules_dir, a.edge_model)) as pool:
            for _ in pool.imap_unordered(_parse_one, todo):
                pass
    return out


def _txt(n) -> str:
    return n.get("raw_latex") or n.get("statement") or ""


def _squash(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def _inside(small: str, big: str) -> bool:
    """Does the text `small` lie inside the text `big` (both squashed)? Tested by position,
    with a 60-character probe from its middle, not by shared words: a short sentence shares
    its words with almost any long proof."""
    if not small or len(small) >= len(big):
        return False
    probe = small[len(small) // 4: len(small) // 4 + 60] if len(small) > 80 else small
    return probe in big


def graph_mode(a):
    import edge_metrics as EM
    import match_modes as mm
    import node_metrics as NM
    import node_similarity as NS
    from graph_io import load_graph
    from distill_common import TYPES
    types = set(TYPES)
    gdir = parse_val(a)
    cat = Counter()                                  # (kind, category, type) -> count
    ex = defaultdict(list)                           # same key -> [(pid, text)]
    node_c = Counter()                               # pooled m1g counts
    per = defaultdict(Counter)                       # type -> pred, gold, tp_p, tp_r
    ecat, eex = Counter(), defaultdict(list)
    ec = Counter()
    empty = 0
    for pid in val_ids():
        pn_all, pe = load_graph(gdir / f"{pid}.json")
        rn_all, re_ = EM.level1(*load_graph(SILVER / f"{pid}.json"))
        pn = [n for n in pn_all if n["type"] in types and _txt(n).strip()]
        rn = [n for n in rn_all if n["type"] in types and (n.get("statement") or "").strip()]
        empty += not pn
        P = [(n["type"], mm.tokens(_txt(n))) for n in pn]
        G = [(n["type"], mm.tokens(n.get("statement") or "")) for n in rn]
        m = NM._one_to_one(P, G, NS.type_compat, NM.THRESHOLD)
        taken = {j for j, _ in m.values()}
        PS = [_squash(_txt(n)) for n in pn]
        GS = [_squash(n.get("statement") or "") for n in rn]
        node_c["pred"] += len(P)
        node_c["gold"] += len(G)
        for tp_, _a in P:
            per[tp_]["pred"] += 1
        for tg, _b in G:
            per[tg]["gold"] += 1
        for i, (j, w) in m.items():
            per[P[i][0]]["tp_p"] += w
            per[G[j][0]]["tp_r"] += w
        for i, (tp, a_) in enumerate(P):
            src = "tagger" if pn[i].get("env_name") == "distilled" else "parser"
            if i in m:
                j, w = m[i]
                node_c["tp"] += w
                if rn[j]["type"] != tp:
                    key = ("node", "wrong type", f"{rn[j]['type']} -> {tp}")
                    cat[key] += 1
                    ex[key].append((pid, src, _txt(pn[i])))
                continue
            ins = [j for j in range(len(G)) if _inside(PS[i], GS[j])]
            if ins:
                j = min(ins, key=lambda j: len(G[j][1]))
                how = f"inside a {'paired' if j in taken else 'missed'} silver {G[j][0]}"
            elif any(b and NM._jaccard(a_, b) >= 0.3 for _t, b in G):
                how = "partial overlap"
            else:
                how = "no overlap"
            key = ("node", f"spurious/{how}", f"{tp} [{src}]")
            cat[key] += 1
            ex[key].append((pid, src, _txt(pn[i])))
        for j, (tg, b) in enumerate(G):
            if j in taken:
                continue
            big = [i for i in range(len(P)) if _inside(GS[j], PS[i])]
            if big:
                i = min(big, key=lambda i: len(P[i][1]))
                how = f"inside a predicted {P[i][0]}{' (paired)' if i in m else ''}"
            elif any(_inside(PS[i], GS[j]) for i in range(len(P))):
                how = "split into smaller predictions"
            elif any(a_ and NM._jaccard(a_, b) >= 0.3 for _t, a_ in P):
                how = "partial overlap"
            else:
                how = "no overlap"
            key = ("node", f"missed/{how}", tg)
            cat[key] += 1
            ex[key].append((pid, "", rn[j].get("statement") or ""))
        # edges
        rnodes = {n["id"]: n for n in rn_all}
        pnodes = {n["id"]: n for n in pn_all}
        al = EM.align(pn_all, rn_all)
        inv = {v: k for k, v in al.items()}
        redges = {(e["source"], e["target"]): e for e in re_ if e["source"] in rnodes and e["target"] in rnodes}
        found = set()
        for e in pe:
            s, t = al.get(e["source"]), al.get(e["target"])
            if s is not None and s == t:
                continue
            ps, pt = pnodes.get(e["source"], {}), pnodes.get(e["target"], {})
            pk = f"{EM.kind(ps.get('type', '?'))} -> {EM.kind(pt.get('type', '?'))} ({e['type']}" \
                 f"{', learned' if e.get('provenance') else ''})"
            ec["pred"] += 1
            if s is None or t is None:
                c = "spurious/unaligned endpoint"
            elif (s, t) in redges and (s, t) not in found:
                found.add((s, t))
                ec["tp"] += 1
                continue
            elif (t, s) in redges:
                c = "spurious/reversed"
            else:
                c = "spurious/not in silver"
            ecat[("edge", c, pk)] += 1
            eex[("edge", c, pk)].append((pid, f"{ps.get('id')}->{pt.get('id')}",
                                         _txt(ps)[:70] + "  ==>  " + _txt(pt)[:70]))
        for (s, t), e in redges.items():
            ec["ref"] += 1
            if (s, t) in found:
                continue
            k = EM.edge_kind(e, rnodes)
            miss = [x for x in (s, t) if x not in inv]
            c = "missed/endpoint not found" if miss else "missed/endpoints found, no edge"
            if miss:
                c += f" ({'+'.join(sorted({EM.kind(rnodes[x]['type']) for x in miss}))})"
            ecat[("edge", c, k)] += 1
            eex[("edge", c, k)].append((pid, f"{s}->{t} [{e['type']}]",
                                        (rnodes[s].get("statement") or "")[:70] + "  ==>  "
                                        + (rnodes[t].get("statement") or "")[:70]))
    tp, pr, g = node_c["tp"], node_c["pred"], node_c["gold"]
    P_, R_ = tp / pr, tp / g
    print(f"{gdir.name}: {len(val_ids())} val papers ({empty} with no node) | nodes m1g pooled "
          f"P {P_:.3f} R {R_:.3f} F1 {2 * P_ * R_ / (P_ + R_):.3f} (pred {pr}, silver {g})")
    P_, R_ = ec["tp"] / max(1, ec["pred"]), ec["tp"] / max(1, ec["ref"])
    print(f"   edges pooled P {P_:.3f} R {R_:.3f} F1 {2 * P_ * R_ / max(1e-9, P_ + R_):.3f} "
          f"(pred {ec['pred']}, silver L1 {ec['ref']})")
    print(f"\n   {'type':<13}{'silver':>7}{'pred':>6}{'P':>7}{'R':>7}{'F1':>7}")
    for t, c in sorted(per.items(), key=lambda x: -x[1]["gold"]):
        P_ = c["tp_p"] / c["pred"] if c["pred"] else 0.0
        R_ = c["tp_r"] / c["gold"] if c["gold"] else 0.0
        print(f"   {t:<13}{c['gold']:>7}{c['pred']:>6}{P_:>7.3f}{R_:>7.3f}"
              f"{(2 * P_ * R_ / (P_ + R_) if P_ + R_ else 0):>7.3f}")
    for title, C, E in (("NODE", cat, ex), ("EDGE", ecat, eex)):
        tot = Counter()
        for (_k, c, _t), n in C.items():
            c = re.sub(r"inside a predicted \w+", "inside a larger prediction", re.sub(r" [(].*", "", c))
            tot[re.sub(r"silver \w+", "silver node", c)] += n
        print(f"\n== {title} errors by category: " + ", ".join(f"{c} {n}" for c, n in tot.most_common()))
        print(f"   top {a.top} (category | type), ranked by count:")
        for (k, c, t), n in C.most_common(a.top):
            print(f"   {n:5}  {c:<46} {t}")
    rnd = random.Random(0)
    for C, E in ((cat, ex), (ecat, eex)):
        for key, n in C.most_common(a.show):
            print(f"\n-- {key[1]} | {key[2]}  ({n})")
            for x in rnd.sample(E[key], min(a.examples, len(E[key]))):
                print(f"   {x[0]} {x[1]}: {' '.join(x[2].split())[:220]!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", help="sentence mode: an alg3 model dir (alg3/runs/<v>)")
    ap.add_argument("--data", default=str(HERE / "cache/papers.pkl"))
    ap.add_argument("--rules-dir", help="graph mode: the rule dir to parse with")
    ap.add_argument("--edge-model", default=None, help="graph mode: learned edge model (alg3/edges.py)")
    ap.add_argument("--name", help="graph mode: name of the parsed-graph folder")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--parse-train", action="store_true", help="graph mode: also parse the train papers")
    ap.add_argument("--top", type=int, default=25, help="graph mode: categories listed")
    ap.add_argument("--show", type=int, default=8, help="graph mode: categories with examples")
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    if a.rules_dir:
        a.name = a.name or Path(a.rules_dir).name + ("+edges" if a.edge_model else "")
        graph_mode(a)
    elif a.model:
        sentence_mode(a)
    else:
        ap.error("give --model (sentence mode) or --rules-dir (graph mode)")


if __name__ == "__main__":
    main()
