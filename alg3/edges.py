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
  stack        a second logistic regression that rescores each pair from the first-stage
               probabilities of related pairs (D's other users, X's other sources, D with X's
               neighbours, with X's proof or proved result, two hops D -> Y -> X); trained on
               the first stage's out-of-fold probabilities (`stack_features`).
The threshold is chosen by the edge F1 of the whole graph on out-of-fold predictions for the
TRAIN papers (5 folds by paper); the VAL papers are scored at it (and the VAL curve printed),
for choosing between models; test is scored once, with edge_metrics.py. The model is saved as JSON (vocabulary + weights), so applying it needs no
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
import functools
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SKIP_X = {"proof_step", "algorithm_step"}
SOURCES = {"definition", "equation"}      # an equation is a source through a defining display (X := ...)
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
LHS = re.compile(r":=|\\coloneqq|\\equiv|\\triangleq|=:|(?<![<>!:])=(?!=)")
NAME = re.compile(r"^\s*\[([^\]]{2,60})\]")
SPACES = re.compile(r"\\[,;:! ]|\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle)\b|\s+")
FONT = (r"(?:mathcal|mathbb|mathfrak|mathscr|mathbf|mathrm|mathsf|operatorname|widehat|hat|"
        r"widetilde|tilde|bar|overline|vec|check|dot|ddot|boldsymbol|bm|[A-Za-z]{1,2})")
HEAD = re.compile(r"\\" + FONT + r"\{[^{}]+\}|\\[A-Za-z]+|[A-Za-z]")
FONT_ARG = re.compile(r"(\\" + FONT + r")\s+(\\[A-Za-z]+|[A-Za-z0-9])")    # \mathcal L -> \mathcal{L}
STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is", "be", "set", "map", "function"}


def _flat(s) -> str:
    """v7 graphs may hold a list of strings where v6 had one string (name, definiendum)."""
    return "; ".join(str(x) for x in s if x) if isinstance(s, (list, tuple)) else (s or "")


def mnorm(s: str) -> str:
    """Math without spacing, one spelling per symbol: \\mathcal L, {\\mathcal L} and
    \\mathcal{L} agree, and so do e_{u} and e_u."""
    s = _flat(s)
    s = SPACES.sub("", FONT_ARG.sub(r"\1{\2}", s or ""))
    s = re.sub(r"\{(\\[A-Za-z]+\{[^{}]*\})\}", r"\1", s)
    return re.sub(r"([_^])\{([A-Za-z0-9])\}", r"\1\2", s).strip("$")


def head(m: str) -> str | None:
    h = HEAD.match(mnorm(m))
    return h.group(0) if h else None


def wnorm(s: str) -> str:
    s = re.sub(r"\$[^$]*\$|\\[A-Za-z]+\*?|[{}~]", " ", _flat(s))
    return re.sub(r"\s+", " ", s).strip().lower()


def candidates(text: str, name: str = "") -> list[dict]:
    """[{text, kind, math, pos, ...}] in order of first appearance."""
    out, seen = [], set()
    name = _flat(name)
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
        lhs = LHS.split(chunk, maxsplit=1)[0]
        if lhs != chunk and mnorm(lhs):
            add(lhs, "math_lhs", True, m.start())
        add(chunk, "math", True, m.start())
    for m in MATH.finditer(text or ""):                       # displays: the left side of each line
        body = m.group(1) or m.group(4) or m.group(6)
        if not body:
            continue
        body = re.sub(r"\\(?:label|tag)\{[^{}]*\}|\\(?:nonumber|notag)|\\(?:begin|end)\{[a-z]+\*?\}", "", body)
        for line in re.split(r"\\\\", body):
            line = line.replace("&", "")
            lhs = LHS.split(line, maxsplit=1)[0]
            if lhs != line and 0 < len(mnorm(lhs)) <= 40:
                add(lhs, "display_lhs", True, m.start())
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


@functools.lru_cache(maxsize=1 << 16)
def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def uses(c: dict, text: str, math_norm: str, words: str) -> str | None:
    """How a node's text uses candidate c: 'exact', 'head', 'word' or None. (Each regex runs only
    where its literal occurs: a match implies the substring, so the answer is the same, faster.)"""
    if c["math"]:
        if c["key"] and c["key"] in math_norm:
            return "exact"
        h = c["head"]
        if h and h in math_norm:
            if h.startswith("\\"):
                if _rx(re.escape(h) + r"(?![A-Za-z])").search(math_norm):
                    return "head"
            elif _rx(r"(?<![A-Za-z\\])" + re.escape(h) + r"(?![A-Za-z])").search(math_norm):
                return "head"
        return None
    if c["key"] in words and _rx(r"\b" + re.escape(c["key"]) + r"(?:s|es)?\b").search(words):
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
        if d["type"] not in SOURCES:
            continue
        cs = [c for c in def_candidates(d, dmodel) if c["p"] >= MIN_CAND_P
              and (d["type"] == "definition" or c["kind"] == "display_lhs")]
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
                f"src={d['type']}": 1.0, f"src={d['type']}|how={how}": 1.0, f"how={how}": 1.0, f"p={_b(c['p'], (0.2, 0.4, 0.6, 0.8))}": 1.0, "p_raw": c["p"],
                f"kind={c['kind']}": 1.0, f"how={how}|p={_b(c['p'], (0.3, 0.6))}": 1.0,
                f"x={x['type']}": 1.0, f"x={x['type']}|how={how}": 1.0,
                f"after={dist > 0}": 1.0, f"dist={_b(abs(dist), (1, 3, 8, 20, 50))}": 1.0,
                f"spread={_b(spread, (0.02, 0.05, 0.1, 0.2, 0.4))}": 1.0,
                f"spread={_b(spread, (0.05, 0.2))}|how={how}": 1.0,
                f"n_match={min(len(ms), 4)}": 1.0,
                f"single_letter={bool(c['math'] and re.fullmatch(r'[A-Za-z]', c['key']))}": 1.0,
                "best_p_x_exact": max((m[0]["p"] for m in ms if m[1] == "exact"), default=0.0),
                "best_p_x_word": max((m[0]["p"] for m in ms if m[1] == "word"), default=0.0)}))
    # relational clues: how D ranks among the sources that X uses (by strength, by nearness)
    per_x = collections.defaultdict(list)
    for i, (_d, xid, _f) in enumerate(out):
        per_x[xid].append(i)
    for xid, idx in per_x.items():
        strength = sorted(idx, key=lambda i: -out[i][2]["p_raw"])
        near = sorted(idx, key=lambda i: (order[xid] < order[out[i][0]], abs(order[xid] - order[out[i][0]])))
        for r, i in enumerate(strength):
            out[i][2][f"rank_p={min(r, 3)}"] = 1.0
        for r, i in enumerate(near):
            out[i][2][f"rank_near={min(r, 3)}"] = 1.0
        for i in idx:
            out[i][2][f"n_src={_b(len(idx), (1, 2, 4, 8))}"] = 1.0
    return out


def stack_features(graph: dict, rows: list, q: list) -> list:
    """Second-stage clues of each pair (D, X): its first-stage probability and those of the
    related pairs: D's other users, X's other sources, D with X's neighbours, D with the proof of
    X (or the result X proves)."""
    nodes = graph.get("nodes", [])
    order = {n["id"]: i for i, n in enumerate(nodes)}
    ids = [n["id"] for n in nodes]
    partner = collections.defaultdict(set)
    for e in graph.get("edges", []):
        if e["type"] == "proves":
            partner[e["source"]].add(e["target"])
            partner[e["target"]].add(e["source"])
    P = {(r[0], r[1]): p for r, p in zip(rows, q)}
    by_d, by_x = collections.defaultdict(list), collections.defaultdict(list)
    for r, p in zip(rows, q):
        by_d[r[0]].append(p)
        by_x[r[1]].append(p)
    sd = {d: sorted(v, reverse=True) for d, v in by_d.items()}
    users = collections.defaultdict(list)
    for r, p in zip(rows, q):
        if p >= 0.2:
            users[r[0]].append(r[1])
    xtype = {n["id"]: n["type"] for n in nodes}
    sx = {x: sorted(v, reverse=True) for x, v in by_x.items()}
    out = []
    for r, p in zip(rows, q):
        d, x, f = r[0], r[1], r[2]
        i = order[x]
        nb = max((P.get((d, ids[j]), 0.0) for j in (i - 1, i + 1) if 0 <= j < len(ids)), default=0.0)
        pt = max((P.get((d, y), 0.0) for y in partner.get(x, ())), default=0.0)
        others_x = [v for v in sx[x] if v != p] or [0.0]
        g = dict(f)
        z = math.log(max(p, 1e-6) / max(1 - p, 1e-6))
        g.update({"s1_logit": z, f"s1_p={_b(p, (0.1, 0.2, 0.3, 0.45, 0.6))}": 1.0,
                  f"s1_rank_d={min(sd[d].index(p), 10) // 2}": 1.0,
                  f"s1_rank_x={min(sx[x].index(p), 4)}": 1.0,
                  f"s1_nd_hi={_b(sum(v >= 0.25 for v in sd[d]), (0, 2, 5, 12, 30))}": 1.0,
                  f"s1_nx_hi={_b(sum(v >= 0.25 for v in sx[x]), (0, 1, 3, 6))}": 1.0,
                  "s1_max_other_x": others_x[0], "s1_nb": nb, "s1_partner": pt,
                  f"s1_partner={_b(pt, (0.05, 0.25, 0.5))}|p={_b(p, (0.15, 0.35))}": 1.0,
                  f"s1_nb={_b(nb, (0.05, 0.25, 0.5))}|p={_b(p, (0.15, 0.35))}": 1.0})
        pb = _b(p, (0.15, 0.3, 0.5))
        two = max((min(P.get((d, y), 0.0), P.get((y, x), 0.0)) for y in users.get(d, ()) if y != x), default=0.0)
        hows = [k for k in f if k.startswith("how=") and "|" not in k]
        g.update({"s1_two_hop": two, f"s1_two={_b(two, (0.1, 0.25, 0.5))}|p={pb}": 1.0,
                  f"s1_x={xtype[x]}|p={pb}": 1.0, f"s1_d={xtype[d]}|p={pb}": 1.0,
                  f"s1_{hows[0] if hows else 'how=?'}|p={pb}": 1.0,
                  f"s1_rank_x={min(sx[x].index(p), 3)}|p={pb}": 1.0,
                  "s1_gap_x": p - others_x[0]})
        out.append(g)
    return out


# ── the parser's own edges: keep or drop ────────────────────────────────────
LABEL = re.compile(r"\\label\{([^{}]+)\}")
REF = re.compile(r"\\(?:eq|c|C|auto)?ref\*?\{([^{}]+)\}")
STARRED = re.compile(r"begin\{[a-z]+\*\}|^\s*(?:\$\$|\\\[)")      # unnumbered display
DEFINING = re.compile(r":=|=:|coloneqq|triangleq|\\equiv|\\stackrel")


def parser_edge_rows(g: dict) -> list:
    """[(edge, features)] for the parser's edges of one graph (learned edges skipped)."""
    nodes = g.get("nodes", [])
    by = {n["id"]: n for n in nodes}
    order = {n["id"]: i for i, n in enumerate(nodes)}
    labels = {n["id"]: set(LABEL.findall(node_text(n))) for n in nodes}
    refs = {n["id"]: collections.Counter(REF.findall(node_text(n))) for n in nodes}
    refcount = collections.Counter()
    for c in refs.values():
        refcount.update(c)
    edges = [e for e in g.get("edges", []) if not e.get("provenance")]
    outd = collections.Counter(e["source"] for e in edges)
    ind = collections.Counter(e["target"] for e in edges)
    cont = collections.defaultdict(list)                     # container -> its equations, in order
    for e in edges:
        if by.get(e["source"], {}).get("type") == "equation" and e["type"] == "uses":
            cont[e["target"]].append(e["source"])
    rows = []
    for e in edges:
        s, t = by.get(e["source"]), by.get(e["target"])
        if s is None or t is None:
            continue
        ts, tt = s["type"], t["type"]
        explicit = bool(labels[s["id"]] & set(refs[t["id"]]))
        f = {f"k={ts}>{tt}|{e['type']}": 1.0, f"src={ts}": 1.0, f"tgt={tt}": 1.0, f"et={e['type']}": 1.0,
             f"conf={_b(e.get('confidence', 1), (0.5, 0.8, 0.99))}": 1.0, f"mention={'mention' in e}": 1.0,
             f"dist={_b(abs(order[t['id']] - order[s['id']]), (1, 3, 10, 30))}": 1.0,
             f"after={order[t['id']] > order[s['id']]}": 1.0,
             f"outd={_b(outd[s['id']], (1, 3, 8, 20))}": 1.0, f"ind={_b(ind[t['id']], (1, 3, 8, 20))}": 1.0,
             f"explicit_ref={explicit}": 1.0, f"k={ts}>{tt}|explicit={explicit}": 1.0}
        for side, n in (("s", s), ("t", t)):
            if n["type"] != "equation":
                continue
            txt, labs = node_text(n), labels[n["id"]]
            nref = sum(refcount[x] for x in labs) - sum(refs[n["id"]][x] for x in labs)   # refs from elsewhere
            env = re.match(r"\s*\\begin\{([a-z]+)", txt)
            f.update({f"{side}eq_label={bool(labs)}": 1.0, f"{side}eq_refs={_b(nref, (0, 1, 3))}": 1.0,
                      f"{side}eq_def={bool(DEFINING.search(txt))}": 1.0,
                      f"{side}eq_star={bool(STARRED.search(txt))}": 1.0,
                      f"{side}eq_len={_b(len(txt), (60, 150, 400))}": 1.0,
                      f"{side}eq_env={env.group(1) if env else 'display'}": 1.0})
            if side == "s" and e["type"] == "uses" and cont.get(t["id"]):
                eqs = cont[t["id"]]
                k = eqs.index(s["id"]) if s["id"] in eqs else -1
                f[f"pos={'first' if k == 0 else 'last' if k == len(eqs) - 1 else 'mid'}"] = 1.0
                f[f"n_eq={_b(len(eqs), (1, 3, 8))}"] = 1.0
                f[f"k={ts}>{tt}|refs={_b(nref, (0, 1))}"] = 1.0
        rows.append((e, f))
    return rows


def _squash(t: str) -> str:
    return re.sub(r"\s+", "", t or "")


def filter_edges(graph: dict, probs: list, th: float) -> int:
    """Drop the parser edges (in parser_edge_rows order) whose keep-probability is below th.
    A dropped edge from an equation to the node whose text contains it (the parser's
    'equation in' edge: containment, not a dependency) is kept as the equation's
    `parent_id`, so the viewer still shows the equation in that node's panel."""
    by = {n["id"]: n for n in graph.get("nodes", [])}
    drop = set()
    for (e, _f), p in zip(parser_edge_rows(graph), probs):
        if p >= th:
            continue
        drop.add(id(e))
        eq, box = by.get(e["source"]), by.get(e["target"])
        if eq and box and eq["type"] == "equation" and e["type"] == "uses" and not eq.get("parent_id"):
            body = _squash(node_text(eq))
            if body and body in _squash(node_text(box)):
                eq["parent_id"] = box["id"]
    n = len(graph.get("edges", []))
    graph["edges"] = [e for e in graph.get("edges", []) if id(e) not in drop]
    return n - len(graph["edges"])


# ── runtime: the parser hook ────────────────────────────────────────────────
class EdgeModel:
    """A trained model directory (extractors/edges/<id>/model.json)."""
    def __init__(self, model_dir):
        d = json.load(open(Path(model_dir) / "model.json", encoding="utf-8"))
        self.allpairs = None
        if d.get("kind") == "allpairs":                 # alg3/edges_all.py: every edge kind, needs the .tex
            import edges_all
            self.allpairs = edges_all.Model(model_dir)
            self.id, self.threshold = self.allpairs.id, self.allpairs.threshold
            return
        self.dmodel, self.pmodel = LR(d["definiendum"]), LR(d["pairs"])
        self.threshold, self.id = d["threshold"], d.get("id", Path(model_dir).name)
        self.filter = LR(d["filter"]) if d.get("filter") else None     # keep/drop the parser's edges
        self.drop_below = d.get("drop_below", 0.0)
        self.stack = LR(d["stack"]) if d.get("stack") else None


def add_edges(graph: dict, model: EdgeModel, threshold: float | None = None, tex: str | None = None) -> int:
    """Drop the parser edges the filter rejects (if the model has one), then add the model's
    definition -> user `uses` edges to a unified graph dict, in place; pairs already linked
    (either direction) are left alone. Returns the number added. An all-pairs model
    (alg3/edges_all.py) instead sets the graph's edges to its scored candidates and uses `tex`,
    the paper's main LaTeX source, for document order (without it: the graph's list order)."""
    if model.allpairs is not None:
        import edges_all
        n0 = len(graph.get("edges", []))
        edges_all.apply(graph, tex, model.allpairs, threshold)
        return len(graph.get("edges", [])) - n0
    th = model.threshold if threshold is None else threshold
    if model.filter is not None:
        filter_edges(graph, [model.filter.p(f) for _e, f in parser_edge_rows(graph)], model.drop_below)
    rows = pairs_of(graph.get("nodes", []), model.dmodel)
    q = [model.pmodel.p(f) for _d, _x, f in rows]
    if model.stack is not None:
        q = [model.stack.p(g) for g in stack_features(graph, rows, q)]
    scored = [(did, xid, p) for (did, xid, _f), p in zip(rows, q)]
    return _add(graph, scored, th, model.id)


def _add(graph: dict, scored: list, th: float, prov: str) -> int:
    """Add the (D id, X id, probability) pairs at or above th, in place."""
    linked = {(e["source"], e["target"]) for e in graph.get("edges", [])}
    linked |= {(t, s) for s, t in linked}
    added = 0
    for did, xid, p in scored:
        if p >= th and (did, xid) not in linked:
            graph.setdefault("edges", []).append({"source": did, "target": xid, "type": "uses",
                                                  "confidence": round(p, 3), "provenance": prov})
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


def definiendum_pieces(d):
    d = _flat(d)
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


def paper_pairs(EM, graph_dir: Path, papers: list, dmodel: LR) -> dict:
    """{pid: (graph, [(D id, X id, features, label or None)])}; label = the Level-1 silver has
    the edge (None: an endpoint not aligned, not used for training)."""
    out, cover = {}, collections.Counter()
    for pid in papers:
        f = graph_dir / f"{pid}.json"
        if not f.is_file():
            continue
        g = json.load(open(f))
        rnodes, redges = _level1_ref(EM, pid)
        m = EM.align(g["nodes"], rnodes)
        rtype = {n["id"]: n["type"] for n in rnodes}
        rows, seen = [], set()
        for did, xid, feats in pairs_of(g["nodes"], dmodel):
            a, b = m.get(did), m.get(xid)
            lab = None if a is None or b is None else int((a, b) in redges)
            rows.append((did, xid, feats, lab))
            seen.add((a, b))
        inv = {v: k for k, v in m.items()}
        for a, b in redges:
            if rtype.get(a) == "definition" and a in inv and b in inv:
                cover["reachable"] += 1
                cover["covered"] += (a, b) in seen
        out[pid] = (g, rows)
    n = sum(r[3] is not None for _g, rows in out.values() for r in rows)
    pos = sum(r[3] == 1 for _g, rows in out.values() for r in rows)
    print(f"[pairs] {n} labelled pairs, {pos} positive; candidate filter covers "
          f"{cover['covered']}/{cover['reachable']} reachable definition edges "
          f"({cover['covered'] / max(1, cover['reachable']):.1%})")
    return out


def fit_pairs(pp: dict, pids: list) -> dict:
    """Pairs with an unaligned endpoint are trained as negatives: the edge metric counts them as
    false positives."""
    X = [f for pid in pids for _d, _x, f, _lab in pp[pid][1]]
    y = [lab or 0 for pid in pids for _d, _x, _f, lab in pp[pid][1]]
    return LR.fit(X, y, 0.3)


def curve_f1(EM, pp: dict, probs: dict, ths) -> dict:
    """{threshold: (P, R, F1)} of the whole graphs with the pairs at or above it added."""
    tot = {th: collections.Counter() for th in ths}
    for pid, (g, rows) in pp.items():
        for th in ths:
            h = json.loads(json.dumps(g))
            _add(h, [(d, x, p) for (d, x, _f, _l), p in zip(rows, probs[pid])], th, "eval")
            tot[th] += EM.score_paper(h, EM.SILVER / f"{pid}.json")
    return {th: EM.prf(c) for th, c in tot.items()}


THS = (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 2.0)
DROP_THS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)


def filter_data(EM, pp: dict) -> dict:
    """{pid: [(features, label or None)]} for the parser edges of the graphs in pp; label =
    the Level-1 silver has the edge (None: both ends align to one silver node, not scored)."""
    out = {}
    for pid, (g, _rows) in pp.items():
        rnodes, redges = _level1_ref(EM, pid)
        m = EM.align(g["nodes"], rnodes)
        rows = []
        for e, f in parser_edge_rows(g):
            a, b = m.get(e["source"]), m.get(e["target"])
            rows.append((f, None if a is not None and a == b else
                         int(a is not None and b is not None and (a, b) in redges)))
        out[pid] = rows
    return out


def fit_filter(fd: dict, pids: list) -> dict:
    X = [f for p in pids for f, lab in fd[p] if lab is not None]
    y = [lab for p in pids for _f, lab in fd[p] if lab is not None]
    return LR.fit(X, y, 0.3)


def parser_f1(EM, pp: dict, probs: dict, th: float) -> tuple:
    tot = collections.Counter()
    for pid, (g, _rows) in pp.items():
        h = json.loads(json.dumps(g))
        filter_edges(h, probs[pid], th)
        tot += EM.score_paper(h, EM.SILVER / f"{pid}.json")
    return EM.prf(tot)


def cmd_train(a):
    EM = _metrics()
    if a.silver:
        EM.SILVER = Path(a.silver).resolve()
    if a.split:
        EM.SPLIT = Path(a.split).resolve()
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
    tp = paper_pairs(EM, Path(a.graphs), train, D)
    vp = paper_pairs(EM, Path(a.graphs), val, D)
    pids = sorted(tp)
    if a.seed:                                               # reshuffle the fold assignment
        import random
        random.Random(a.seed).shuffle(pids)
    # 1. the filter on the parser's edges: out-of-fold keep-probabilities pick drop_below
    ftr, fva = filter_data(EM, tp), filter_data(EM, vp)
    foof = {}
    for k in range(5):
        held = set(pids[k::5])
        F = LR(fit_filter(ftr, [p for p in pids if p not in held]))
        foof.update({pid: [F.p(f) for f, _l in ftr[pid]] for pid in held})
    fmodel = fit_filter(ftr, pids)
    F = LR(fmodel)
    fval = {pid: [F.p(f) for f, _l in rows] for pid, rows in fva.items()}
    fcurve = {}
    for th in DROP_THS:
        fcurve[th] = (parser_f1(EM, tp, foof, th), parser_f1(EM, vp, fval, th))
        (op, orr, of), (p, r, f) = fcurve[th]
        print(f"[filter] drop below {th:.2f}: parser edges OOF P {op:.3f} R {orr:.3f} F1 {of:.3f} | "
              f"val P {p:.3f} R {r:.3f} F1 {f:.3f}")
    drop = max(DROP_THS, key=lambda th: fcurve[th][0][2])
    for pid in pids:
        filter_edges(tp[pid][0], foof[pid], drop)
    for pid in vp:
        filter_edges(vp[pid][0], fval[pid], drop)
    print(f"[filter] drop below {drop} (best OOF); definition edges are added to the filtered graphs")
    # 2. definition edges: out-of-fold probabilities on the train papers pick the threshold
    oof = {}
    for k in range(5):
        held = pids[k::5]
        L = LR(fit_pairs(tp, [p for p in pids if p not in set(held)]))
        oof.update({pid: [L.p(f) for _d, _x, f, _l in tp[pid][1]] for pid in held})
    pairs = fit_pairs(tp, pids)
    L = LR(pairs)
    vq = {pid: [L.p(f) for _d, _x, f, _l in rows] for pid, (_g, rows) in vp.items()}
    # 3. the second stage, on the first stage's out-of-fold probabilities (same folds)
    s2 = {pid: (tp[pid][0], [(d, x, g, lab) for (d, x, _f, lab), g in
                             zip(tp[pid][1], stack_features(tp[pid][0], tp[pid][1], oof[pid]))]) for pid in pids}
    oof2 = {}
    for k in range(5):
        held = pids[k::5]
        L2 = LR(fit_pairs(s2, [p for p in pids if p not in set(held)]))
        oof2.update({pid: [L2.p(f) for _d, _x, f, _l in s2[pid][1]] for pid in held})
    stack = fit_pairs(s2, pids)
    L2 = LR(stack)
    v2 = {pid: [L2.p(g) for g in stack_features(g0, rows, vq[pid])] for pid, (g0, rows) in vp.items()}
    o1, v1 = curve_f1(EM, tp, oof, (0.25,))[0.25], curve_f1(EM, vp, vq, (0.25,))[0.25]
    print(f"[stage1] threshold 0.25: OOF F1 {o1[2]:.3f} | val F1 {v1[2]:.3f}")
    oof, vq = oof2, v2
    oc = curve_f1(EM, tp, oof, THS)
    vc = curve_f1(EM, vp, vq, THS)
    curve = []
    for th in THS:
        (op, orr, of), (p, r, f) = oc[th], vc[th]
        curve.append({"threshold": th, "oof_P": round(op, 4), "oof_R": round(orr, 4), "oof_F1": round(of, 4),
                      "P": round(p, 4), "R": round(r, 4), "F1": round(f, 4)})
        print(f"[curve] threshold {th if th < 1 else 'none':>4}: OOF P {op:.3f} R {orr:.3f} F1 {of:.3f} | "
              f"val P {p:.3f} R {r:.3f} F1 {f:.3f}")
    best = (max(THS[:-1], key=lambda th: oc[th][2]),)
    best = (vc[best[0]][2], best[0])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"id": out.name, "definiendum": dmodel, "pairs": pairs, "threshold": best[1],
           "filter": fmodel, "drop_below": drop, "stack": stack}
    json.dump(doc, open(out / "model.json", "w"))
    json.dump({"extractor_id": out.name, "kind": "definition_edges", "code": "alg3/edges.py",
               "trained_on": {"graphs": str(Path(a.graphs)), "train_papers": len(train), "val_papers": len(val)},
               "silver": str(EM.SILVER.relative_to(REPO)), "split": str(EM.SPLIT.relative_to(REPO)),
               "threshold": best[1], "val_curve": curve, "drop_below": drop,
               "filter_curve": [{"drop_below": th, "oof_F1": round(o[2], 4), "val_P": round(v[0], 4),
                                 "val_R": round(v[1], 4), "val_F1": round(v[2], 4)} for th, (o, v) in fcurve.items()],
               "date": datetime.date.today().isoformat()}, open(out / "recipe.json", "w"), indent=1)
    print(f"[val] threshold {best[1]} (best OOF F1 {oc[best[1]][2]:.3f}): val F1 {best[0]:.3f} -> {out}")


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
    t.add_argument("--seed", type=int, default=0, help="shuffle the papers before the 5 folds (0: by id)")
    t.add_argument("--silver", default=None, help="silver graphs, <paper>.json (default: edge_metrics.SILVER, v6)")
    t.add_argument("--split", default=None, help="split CSV (default: edge_metrics.SPLIT, v6 6-2-2)")
    p = sub.add_parser("apply", help="add the model's edges to a folder of graphs")
    p.add_argument("--graphs", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    {"train": cmd_train, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    main()
