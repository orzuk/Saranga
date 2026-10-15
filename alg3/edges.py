#!/usr/bin/env python3
"""Definition -> user edges, learned from the v6 silver (the alg3 approach applied to edges).

59% of the silver's dependency edges (steps folded) link a definition to the nodes that use
its term or symbol; the parser's edge builder (math_paper_parser._build_relations) finds 2.7%
of them. This adds them, deterministically and with no API call at parse time.

Candidates (fixed rules) of a definition's LaTeX: inline math chunks, the left side of := / =,
marked text (\\emph, \\textit, quotes), words after cue phrases ("called", "denoted by", ...),
the environment's title. A node USES a candidate when the candidate's normalised math occurs in
its math, or its head symbol does (T in T_q for T_p), or its words occur as whole words.
Two logistic regressions over deterministic clues, as alg3:
  definiendum  which candidates are the thing defined; label = the silver's `definiendum`
               field, on the silver definitions of the TRAIN papers;
  pairs        does node X use definition D; clues = the candidate's definiendum probability,
               how it is used, how many nodes of the paper use it, X's type, order, distance;
               trained on rule graphs of the TRAIN papers, labelled by the Level-1 silver through
               the m1g node alignment (src/LLMVersion/edge_metrics.py).
The threshold is chosen on the VAL papers by the edge F1 of the whole graph; test is scored once,
with edge_metrics.py. The model is saved as JSON (vocabulary + weights), so applying it needs no
scikit-learn.

    python3 alg3/edges.py train --graphs corpus/silver/opus-5.5__v6/tagger_v6 \\
        --out extractors/edges/silver_v6__defterm_edges__2026-10
    python3 alg3/edges.py apply --graphs DIR --model extractors/edges/<id> --out OUT_DIR
    # at parse time (off by default):  parse_batch.py ... --edge-model extractors/edges/<id>
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SKIP_X = {"proof_step", "algorithm_step"}
MIN_CAND_P = 0.05


# ── terms: candidates of a definition and how a node uses them ──────────────
MATH = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\]"
                  r"|\\begin\{(equation|align|gather|multline|eqnarray)\*?\}(.+?)\\end\{\5\*?\}", re.S)
INLINE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)|\\\((.+?)\\\)", re.S)
MARKED = re.compile(r"\\(?:emph|textit|textbf|textsl|underline)\s*\{((?:[^{}]|\{[^{}]*\})+)\}"
                    r"|\{\\(?:em|it|bf|itshape|bfseries|sl)\s+((?:[^{}]|\{[^{}]*\})+)\}"
                    r"|``([^`']{2,60})''|\"([^\"]{2,60})\"")
CUE = re.compile(r"\b(?:called|is said to be|are said to be|termed|known as|refer(?:red)? to (?:it |them )?as"
                 r"|we say that [^.]{0,60}? (?:is|are)|denoted? by|we denote|we write|we call [^.]{0,40}?)"
                 r"\s+(?:an?\s+|the\s+)?([^,.;:()]{2,60}?)(?=\s*(?:[,.;:()]|\bif\b|\bwhen\b|\bprovided\b|\bwhere\b|$))", re.I)
NAME = re.compile(r"^\s*\[([^\]]{2,60})\]")
SPACES = re.compile(r"\\[,;:! ]|\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle)\b|\s+")
HEAD = re.compile(r"\\(?:mathcal|mathbb|mathfrak|mathscr|mathbf|mathrm|mathsf|operatorname|widehat|hat|"
                  r"widetilde|tilde|bar|overline|vec|check|dot|ddot|boldsymbol|bm)\s*\{[^{}]+\}|\\[A-Za-z]+|[A-Za-z]")
STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is", "be", "set", "map", "function"}


def mnorm(s: str) -> str:
    return SPACES.sub("", s or "").strip("$")


def head(m: str) -> str | None:
    h = HEAD.match(mnorm(m))
    return h.group(0) if h else None


def wnorm(s: str) -> str:
    s = re.sub(r"\$[^$]*\$|\\[A-Za-z]+\*?|[{}~]", " ", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def candidates(text: str, name: str = "") -> list[dict]:
    """[{text, kind, math, pos, ...}] in order of first appearance."""
    out, seen = [], set()
    first = re.split(r"(?<=[.!?])\s", text or "", maxsplit=1)[0]

    def add(t, kind, math, pos):
        key = (mnorm(t) if math else wnorm(t))
        if not key or key in seen or (not math and (key in STOP or len(key) < 3)):
            return
        seen.add(key)
        out.append({"text": t, "key": key, "kind": kind, "math": math, "pos": pos,
                    "first": pos < len(first), "head": head(t) if math else None})
    if name:
        add(name, "name", False, 0)
        for m in INLINE.finditer(name):
            add(m.group(1) or m.group(2), "name_math", True, 0)
    for m in INLINE.finditer(text or ""):
        chunk = m.group(1) or m.group(2)
        if len(mnorm(chunk)) > 40:
            continue
        lhs = re.split(r":=|\\coloneqq|\\equiv|\\triangleq|=:|(?<![<>!:])=(?!=)", chunk)[0]
        if lhs != chunk and mnorm(lhs):
            add(lhs, "math_lhs", True, m.start())
        add(chunk, "math", True, m.start())
    for m in MARKED.finditer(text or ""):
        t = next(g for g in m.groups() if g)
        add(t, "marked", "$" in t and not wnorm(t), m.start())
    for m in CUE.finditer(text or ""):
        t = m.group(1)
        math = bool(INLINE.fullmatch(t.strip()))
        add(t.strip().strip("$") if math else t, "cue", math, m.start())
    return out


def cand_features(c: dict, text: str, n_cands: int) -> dict:
    t = text or ""
    before = wnorm(t[max(0, c["pos"] - 40):c["pos"]])[-30:]
    f = {f"kind={c['kind']}": 1.0, f"math={c['math']}": 1.0, f"first={c['first']}": 1.0,
         f"rank={min(n_cands, 6)}": 1.0}
    if c["math"]:
        k = c["key"]
        f[f"mlen={min(len(k), 12) // 3}"] = 1.0
        f[f"single_letter={bool(re.fullmatch(r'[A-Za-z]', k))}"] = 1.0
        f[f"has_sub={'_' in k}"] = 1.0
        f[f"has_paren={'(' in k}"] = 1.0
        f[f"cmd_head={(c['head'] or '').startswith(chr(92))}"] = 1.0
        f[f"is_relation={bool(re.search(r'[<>]|leq|geq|subset|in(?![a-z])|to(?![a-z])', k))}"] = 1.0
    else:
        n = len(c["key"].split())
        f[f"words={min(n, 5)}"] = 1.0
    for w in before.split()[-3:]:
        f[f"prev={w}"] = 1.0
    if re.search(r"\b(?:let|denote|define|call|write|say|be|by)\s*$", before):
        f["after_cue_verb"] = 1.0
    return f


def math_regions(text: str) -> str:
    """All math of a text, normalised and joined (the haystack for symbol uses)."""
    return " ".join(mnorm(m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(6) or "")
                    for m in MATH.finditer(text or ""))


def uses(c: dict, text: str, math_norm: str, words: str) -> str | None:
    """How a node's text uses candidate c: 'exact', 'head', 'word' or None."""
    if c["math"]:
        if c["key"] and c["key"] in math_norm:
            return "exact"
        h = c["head"]
        if h:
            if h.startswith("\\"):
                if re.search(re.escape(h) + r"(?![A-Za-z])", math_norm):
                    return "head"
            elif re.search(r"(?<![A-Za-z\\])" + re.escape(h) + r"(?![A-Za-z])", math_norm):
                return "head"
        return None
    if re.search(r"\b" + re.escape(c["key"]) + r"(?:s|es)?\b", words):
        return "word"
    return None


# ── a logistic regression stored as JSON ────────────────────────────────────
class LR:
    def __init__(self, d: dict):
        self.vocab, self.coef, self.b = d["vocab"], d["coef"], d["intercept"]

    def p(self, feats: dict) -> float:
        z = self.b + sum(v * self.coef[self.vocab[k]] for k, v in feats.items() if k in self.vocab)
        return 1.0 / (1.0 + math.exp(-z))

    @staticmethod
    def fit(X: list, y: list, C: float, **kw) -> dict:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        vec = DictVectorizer()
        clf = LogisticRegression(C=C, max_iter=3000, **kw).fit(vec.fit_transform(X), y)
        return {"vocab": {k: int(i) for k, i in vec.vocabulary_.items()},
                "coef": [float(x) for x in clf.coef_[0]], "intercept": float(clf.intercept_[0])}


def node_text(n) -> str:
    return n.get("raw_latex") or n.get("statement") or ""


def def_candidates(n, dmodel: LR) -> list:
    text = node_text(n)
    cs = candidates(text, n.get("name") or "")
    for i, c in enumerate(cs):
        c["p"] = dmodel.p(cand_features(c, text, i))
    return cs


def _b(x, cuts):
    for i, c in enumerate(cuts):
        if x <= c:
            return i
    return len(cuts)


def pairs_of(nodes: list, dmodel: LR) -> list:
    """[(D id, X id, features)] for every candidate pair of one graph."""
    order = {n["id"]: i for i, n in enumerate(nodes)}
    by_id = {n["id"]: n for n in nodes}
    view = {n["id"]: (math_regions(node_text(n)), wnorm(re.sub(r"\$[^$]*\$", " ", node_text(n))))
            for n in nodes}
    out = []
    for d in nodes:
        if d["type"] != "definition":
            continue
        cs = [c for c in def_candidates(d, dmodel) if c["p"] >= MIN_CAND_P]
        by_x = collections.defaultdict(list)
        for c in cs:
            hits = [(x["id"], how) for x in nodes if x is not d and x["type"] not in SKIP_X
                    for how in [uses(c, node_text(x), *view[x["id"]])] if how]
            spread = len(hits) / max(1, len(nodes))
            for xid, how in hits:
                by_x[xid].append((c, how, spread))
        for xid, ms in by_x.items():
            x = by_id[xid]
            c, how, spread = max(ms, key=lambda m: m[0]["p"] * {"exact": 1, "word": 0.9, "head": 0.6}[m[1]])
            dist = order[xid] - order[d["id"]]
            out.append((d["id"], xid, {
                f"how={how}": 1.0, f"p={_b(c['p'], (0.2, 0.4, 0.6, 0.8))}": 1.0, "p_raw": c["p"],
                f"kind={c['kind']}": 1.0, f"how={how}|p={_b(c['p'], (0.3, 0.6))}": 1.0,
                f"x={x['type']}": 1.0, f"x={x['type']}|how={how}": 1.0,
                f"after={dist > 0}": 1.0, f"dist={_b(abs(dist), (1, 3, 8, 20, 50))}": 1.0,
                f"spread={_b(spread, (0.02, 0.05, 0.1, 0.2, 0.4))}": 1.0,
                f"spread={_b(spread, (0.05, 0.2))}|how={how}": 1.0,
                f"n_match={min(len(ms), 4)}": 1.0,
                f"single_letter={bool(c['math'] and re.fullmatch(r'[A-Za-z]', c['key']))}": 1.0,
                "best_p_x_exact": max((m[0]["p"] for m in ms if m[1] == "exact"), default=0.0),
                "best_p_x_word": max((m[0]["p"] for m in ms if m[1] == "word"), default=0.0)}))
    return out


# ── runtime: the parser hook ────────────────────────────────────────────────
class EdgeModel:
    """A trained model directory (extractors/edges/<id>/model.json)."""
    def __init__(self, model_dir):
        d = json.load(open(Path(model_dir) / "model.json", encoding="utf-8"))
        self.dmodel, self.pmodel = LR(d["definiendum"]), LR(d["pairs"])
        self.threshold, self.id = d["threshold"], d.get("id", Path(model_dir).name)


def add_edges(graph: dict, model: EdgeModel, threshold: float | None = None) -> int:
    """Add the model's definition -> user `uses` edges to a unified graph dict, in place;
    pairs already linked (either direction) are left alone. Returns the number added."""
    th = model.threshold if threshold is None else threshold
    linked = {(e["source"], e["target"]) for e in graph.get("edges", [])}
    linked |= {(t, s) for s, t in linked}
    added = 0
    for did, xid, f in pairs_of(graph.get("nodes", []), model.dmodel):
        p = model.pmodel.p(f)
        if p >= th and (did, xid) not in linked:
            graph.setdefault("edges", []).append({"source": did, "target": xid, "type": "uses",
                                                  "confidence": round(p, 3), "provenance": model.id})
            linked |= {(did, xid), (xid, did)}
            added += 1
    return added


# ── training ────────────────────────────────────────────────────────────────
def _metrics():
    sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
    import edge_metrics as EM                               # noqa: E402
    return EM


def split_of(EM) -> dict:
    import csv
    return {r.get("arxiv_id") or r["paper_id"]: r["split"] for r in csv.DictReader(open(EM.SPLIT))}


def definiendum_pieces(d: str):
    maths = {mnorm(m.group(1) or m.group(2)) for m in INLINE.finditer(d or "")}
    words = {wnorm(p) for p in re.split(r"[;,]", re.sub(r"\$[^$]*\$", " ", d or "")) if wnorm(p)}
    return {m for m in maths if m}, {w for w in words if len(w) >= 3}


def is_definiendum(c, maths, words) -> bool:
    k = c["key"]
    pool, ratio = (maths, 0.6) if c["math"] else (words, 0.5)
    return any(k == m or ((k in m or m in k) and len(min(k, m, key=len)) >= 2
                          and len(min(k, m, key=len)) / len(max(k, m, key=len)) >= ratio) for m in pool)


def train_definiendum(EM, papers: list) -> dict:
    X, y = [], []
    for pid in papers:
        for n in json.load(open(EM.SILVER / f"{pid}.json"))["nodes"]:
            if n["type"] != "definition" or not n.get("definiendum"):
                continue
            text = n.get("statement") or ""
            maths, words = definiendum_pieces(n["definiendum"])
            for i, c in enumerate(candidates(text, n.get("name") or "")):
                X.append(cand_features(c, text, i))
                y.append(int(is_definiendum(c, maths, words)))
    print(f"[definiendum] {len(y)} candidates, {sum(y)} positive")
    return LR.fit(X, y, 0.5, class_weight="balanced")


def _level1_ref(EM, pid):
    from graph_io import load_graph
    nodes, edges = EM.level1(*load_graph(EM.SILVER / f"{pid}.json"))
    return nodes, {(e["source"], e["target"]) for e in edges}


def train_pairs(EM, graph_dir: Path, papers: list, dmodel: LR) -> dict:
    X, y, cover = [], [], collections.Counter()
    for pid in papers:
        f = graph_dir / f"{pid}.json"
        if not f.is_file():
            continue
        g = json.load(open(f))
        rnodes, redges = _level1_ref(EM, pid)
        m = EM.align(g["nodes"], rnodes)
        rtype = {n["id"]: n["type"] for n in rnodes}
        seen = set()
        for did, xid, feats in pairs_of(g["nodes"], dmodel):
            a, b = m.get(did), m.get(xid)
            if a is None or b is None:
                continue
            X.append(feats)
            y.append(int((a, b) in redges))
            seen.add((a, b))
        inv = {v: k for k, v in m.items()}
        for a, b in redges:
            if rtype.get(a) == "definition" and a in inv and b in inv:
                cover["reachable"] += 1
                cover["covered"] += (a, b) in seen
    print(f"[pairs] {len(y)} training pairs, {sum(y)} positive; candidate filter covers "
          f"{cover['covered']}/{cover['reachable']} reachable definition edges "
          f"({cover['covered'] / max(1, cover['reachable']):.1%})")
    return LR.fit(X, y, 0.3)


def val_f1(EM, graph_dir: Path, papers: list, model: EdgeModel, th: float) -> tuple:
    tot = collections.Counter()
    for pid in papers:
        f = graph_dir / f"{pid}.json"
        if f.is_file():
            g = json.load(open(f))
            add_edges(g, model, th)
            tot += EM.score_paper(g, EM.SILVER / f"{pid}.json")
    return EM.prf(tot)


def cmd_train(a):
    EM = _metrics()
    sp = split_of(EM)
    train = sorted(p for p, s in sp.items() if s == "train")
    val = sorted(p for p, s in sp.items() if s == "val")
    dmodel = train_definiendum(EM, train)
    D = LR(dmodel)
    hit = tot = 0
    for pid in val:
        for n in json.load(open(EM.SILVER / f"{pid}.json"))["nodes"]:
            if n["type"] == "definition" and n.get("definiendum"):
                cs = def_candidates({"raw_latex": n.get("statement"), "name": n.get("name")}, D)
                tot += 1
                if cs:
                    hit += is_definiendum(max(cs, key=lambda c: c["p"]), *definiendum_pieces(n["definiendum"]))
    print(f"[definiendum] val: top candidate is (part of) the silver definiendum for {hit}/{tot} = {hit / max(1, tot):.1%}")
    pairs = train_pairs(EM, Path(a.graphs), train, D)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"id": out.name, "definiendum": dmodel, "pairs": pairs, "threshold": None}
    json.dump(doc, open(out / "model.json", "w"))
    model = EdgeModel(out)
    curve, best = [], (val_f1(EM, Path(a.graphs), val, model, 2.0)[2], None)
    print(f"[val] without the model: F1 {best[0]:.3f}")
    for th in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
        p, r, f = val_f1(EM, Path(a.graphs), val, model, th)
        curve.append({"threshold": th, "P": round(p, 4), "R": round(r, 4), "F1": round(f, 4)})
        print(f"[val] threshold {th}: P {p:.3f} R {r:.3f} F1 {f:.3f}")
        best = max(best, (f, th), key=lambda x: x[0])
    doc["threshold"] = best[1]
    json.dump(doc, open(out / "model.json", "w"))
    json.dump({"extractor_id": out.name, "kind": "definition_edges", "code": "alg3/edges.py",
               "trained_on": {"graphs": str(Path(a.graphs)), "train_papers": len(train), "val_papers": len(val)},
               "silver": str(EM.SILVER.relative_to(REPO)), "split": str(EM.SPLIT.relative_to(REPO)),
               "threshold": best[1], "val_curve": curve,
               "date": datetime.date.today().isoformat()}, open(out / "recipe.json", "w"), indent=1)
    print(f"[val] chosen threshold {best[1]} (F1 {best[0]:.3f}) -> {out}")


def cmd_apply(a):
    model = EdgeModel(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    added = 0
    for f in sorted(Path(a.graphs).glob("*.json")):
        g = json.load(open(f))
        added += add_edges(g, model, a.threshold)
        json.dump(g, open(out / f.name, "w"), ensure_ascii=False)
    print(f"{added} definition edges added (threshold {a.threshold or model.threshold}) -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="train on the train papers, pick the threshold on val")
    t.add_argument("--graphs", required=True, help="rule graphs of the silver papers (e.g. .../tagger_v6)")
    t.add_argument("--out", required=True, help="model directory, e.g. extractors/edges/<id>")
    p = sub.add_parser("apply", help="add the model's edges to a folder of graphs")
    p.add_argument("--graphs", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    {"train": cmd_train, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    main()
