#!/usr/bin/env python3
"""All-kinds edges: one learned scorer over candidate pairs of every kind (alg3/edges.py only
adds definition -> user edges and filters the parser's own).

Every ordered pair (s, t) that some cheap channel proposes is a candidate:
  term     s is a definition (or a defining display) whose term/symbol t uses (edges.pairs_of)
  ref      t \\refs a \\label of s (or s of t: the reverse orientation is a candidate too)
  parser   the parser has an edge between s and t (either direction)
  near     s is one of the 3 nodes before t in the document, or the next one
  proof    t is a proof and s the result just before it (and the reverse)
  rare     s is among t's 3 nodes sharing the most rare tokens (both orientations)
Clues of a pair: its channels and their strengths, the two node types, document order and
distance (positions found in the LaTeX source, not the graph's list order), same section,
rare-token overlap, how s ranks among t's candidates. Two logistic regressions, as edges.py:
stage 1 on the clues, stage 2 adding the stage-1 probabilities of related pairs (the reverse
pair, t's other sources, s's other targets, two hops s -> y -> t, s with t's neighbours and
with t's proof partner). The graph's edges are then exactly the candidates scoring >= the
threshold (parser edges included: those below it are dropped). Thresholds and the choice
between versions use out-of-fold TRAIN predictions and the VAL papers; test is never read.

    python3 alg3/edges_all.py train --graphs DIR --silver DIR --split CSV --tex DIR --out MODEL_DIR
    python3 alg3/edges_all.py apply --graphs DIR --tex DIR --model MODEL_DIR --out OUT_DIR
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import json
import math
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path[:0] = [str(HERE), str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
import edges as ED                                            # noqa: E402

LAB = re.compile(r"\\label\{([^{}]+)\}")
REF = re.compile(r"\\(?:eq|c|C|auto|name)?ref\*?\{([^{}]+)\}")
WORD = re.compile(r"\\[A-Za-z]{2,}|[A-Za-z]{4,}")
SECTION = re.compile(r"\\(?:section|chapter)\*?\{")
RESULT = {"theorem", "lemma", "proposition", "corollary", "claim"}
STEPS = {"proof_step", "algorithm_step"}
STOPW = {"that", "with", "this", "then", "from", "have", "which", "where", "there", "such", "where", "each",
         "\\label", "\\ref", "\\begin", "\\end", "\\cite", "\\emph", "\\text", "\\mathrm", "\\left", "\\right",
         "\\frac", "\\eqref", "\\item", "\\textit", "\\mathcal", "\\mathbb", "\\in", "\\le", "\\leq", "\\geq"}


REL = re.compile(r":=|=:|\\coloneqq|\\equiv|\\triangleq|\\stackrel\{[^{}]*\}\{=\}|(?<![<>!:])=(?!=)|\\in(?![A-Za-z])"
                 r"|\\subseteq?|\\le(?:q)?(?![A-Za-z])|\\ge(?:q)?(?![A-Za-z])|<|>|\\to(?![A-Za-z])|\\colon|\\sim(?![A-Za-z])")
ARGS = re.compile(r"^(.+?)\s*(?:\\left)?\((?:[^()]|\([^()]*\))*(?:\\right)?\)\s*$")
SUBJ = re.compile(r"(?:^|[.;:]\s+)(?:an?|the)?\s*((?:[a-z][a-z\-']+\s+){0,3}[a-z][a-z\-']{2,})\s*(?:,[^,]{0,40},\s*)?"
                  r"\s+(?:is|are)\s+(?:(?:then\s+)?(?:called|said|defined|termed|one|a|an|the|by\s+definition)\b)", re.I)
NOTION = re.compile(r"\b(?:notion|concept|class|family|definition|use)\s+of\s+(?:an?\s+|the\s+)?((?:[a-z][a-z\-']+\s+){0,3}[a-z][a-z\-']{2,})", re.I)
ADJ = re.compile(r"\bsay\s+(?:that\s+)?(?:\$[^$]+\$|it|they|[a-z]+)\s+(?:is|are)\s+(?:an?\s+)?([a-z][a-z\-]{3,}(?:\s+[a-z][a-z\-]{3,})?)", re.I)
MACRO = re.compile(r"\\([A-Za-z]*(?:def|term|dfn|emph|textbf)[A-Za-z]*)\s*\{([^{}]{2,60})\}")


def def_candidates(text: str, name: str = "") -> list:
    """edges.candidates plus what it misses: the left side of a relation in any math chunk (long
    chunks included), that side without its arguments (W_j(s) -> W_j), an unmarked subject
    ('A Willmore surface is ...'), 'the notion of X', 'say that it is X', custom term macros."""
    cs = ED.candidates(text, name)
    seen = {c["key"] for c in cs}

    def add(t, kind_, math, pos):
        key = ED.mnorm(t) if math else ED.wnorm(t)
        if not key or key in seen or len(key) > 60 or (not math and (key in ED.STOP or len(key) < 3)):
            return
        seen.add(key)
        cs.append({"text": t, "key": key, "kind": kind_, "math": math, "pos": pos, "first": pos < 200,
                   "head": ED.head(t) if math else None})
    for m in ED.MATH.finditer(text or ""):
        chunk = re.sub(r"\\label\{[^{}]*\}", "", m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(6) or "")
        lhs = REL.split(chunk, maxsplit=1)[0].strip().strip(",.")
        if lhs and lhs != chunk.strip() and len(lhs) <= 40:
            add(lhs, "rel_lhs", True, m.start())
            a = ARGS.match(lhs)
            if a:
                add(a.group(1), "rel_lhs_noargs", True, m.start())
    for rx, k in ((SUBJ, "subject"), (NOTION, "notion"), (ADJ, "say_adj")):
        for m in rx.finditer(re.sub(r"\$[^$]*\$", " $ ", text or "")):
            add(m.group(1), k, False, m.start(1))
    for m in MACRO.finditer(text or ""):
        add(m.group(2), "macro_" + ("def" if "def" in m.group(1).lower() or "dfn" in m.group(1).lower() else "mark"),
            "$" in m.group(2), m.start())
    return cs


def origin(n: dict) -> str:
    """Where a node comes from: the tagger's prose ('tagger'), an environment ('env'), or a parser
    inline pattern (its name, e.g. 'inline_let')."""
    e = n.get("env_name")
    return "tagger" if e == "distilled" else (e if e and e.startswith("inline") else ("env" if e else "none"))


def kind(t: str) -> str:
    return "result" if t in RESULT else t


def _b(x, cuts):
    return bisect.bisect_left(cuts, x)


def _sq(t: str) -> str:
    return re.sub(r"\s+", "", t or "")


# ── a paper: positions, sections, tokens ───────────────────────────────────
class View:
    def __init__(self, graph: dict, tex: str | None):
        self.nodes = [n for n in graph.get("nodes", []) if n.get("type") not in STEPS]
        self.by = {n["id"]: n for n in self.nodes}
        self.txt = {n["id"]: ED.node_text(n) for n in self.nodes}
        src = _sq(tex) if tex else ""
        secs = [m.start() for m in SECTION.finditer(src)]
        pos = {}
        for i, n in enumerate(self.nodes):
            t, k = _sq(self.txt[n["id"]]), -1
            if src:
                for a in (0, len(t) // 4, len(t) // 2, 3 * len(t) // 4, max(0, len(t) - 30)):
                    pr = t[a:a + 30]
                    if len(pr) >= 8:
                        k = src.find(pr)
                        if k >= 0:
                            break
            pos[n["id"]] = k
        cont = {}                                    # an equation not found: its container's place
        for e in graph.get("edges", []):
            if e.get("type") == "uses" and self.by.get(e["source"], {}).get("type") == "equation":
                cont.setdefault(e["source"], e["target"])
        last = 0.0
        for i, n in enumerate(self.nodes):           # fall back: the container, else after the previous
            p = pos[n["id"]]
            if p < 0:
                c = cont.get(n["id"])
                p = pos.get(c, -1) if c else -1
                p = p + 0.5 if p >= 0 else last + 0.1
            pos[n["id"]] = p
            last = p
        if not src:
            pos = {n["id"]: float(i) for i, n in enumerate(self.nodes)}
        self.pos = pos
        self.rank = {i: r for r, i in enumerate(sorted(pos, key=lambda i: pos[i]))}
        self.order = sorted(pos, key=lambda i: pos[i])
        self.sec = {i: bisect.bisect_right(secs, pos[i]) for i in pos}
        self.labs = {i: set(LAB.findall(t)) for i, t in self.txt.items()}
        self.refs = {i: collections.Counter(x.strip() for m in REF.findall(t) for x in m.split(",") if x.strip())
                     for i, t in self.txt.items()}
        self.toks = {i: {w.lower() if not w.startswith("\\") else w for w in WORD.findall(t)} - STOPW
                     for i, t in self.txt.items()}
        df = collections.Counter(w for s in self.toks.values() for w in s)
        N = max(1, len(self.nodes))
        self.idf = {w: math.log(N / c) for w, c in df.items() if c <= max(2, 0.05 * N)}
        self.rare = {i: {w for w in s if w in self.idf} for i, s in self.toks.items()}
        self.parser = {}
        for e in graph.get("edges", []):
            if not e.get("provenance") and e["source"] in self.by and e["target"] in self.by:
                self.parser.setdefault((e["source"], e["target"]), e)

    def rare_score(self, a, b) -> float:
        return sum(self.idf[w] for w in self.rare[a] & self.rare[b])



def cand_doc_feats(c: dict, later: int, earlier: int) -> dict:
    k, m = c["kind"], c["math"]
    lb, eb = _b(later, (0, 1, 3, 8, 20)), _b(earlier, (0, 1, 3, 8))
    return {f"later={lb}": 1.0, f"earlier={eb}": 1.0, f"later={lb}|earlier={eb}": 1.0,
            f"later={lb}|kind={k}": 1.0, f"earlier={eb}|kind={k}": 1.0, f"later={lb}|math={m}": 1.0,
            f"fresh={earlier == 0}|kind={k}": 1.0}


def _views(v: View) -> dict:
    if not hasattr(v, "_tv"):
        v._tv = {i: (ED.math_regions(t), ED.wnorm(re.sub(r"\$[^$]*\$", " ", t))) for i, t in v.txt.items()}
    return v._tv


def scored_candidates(v: View, d: str, dmodel) -> list:
    """[(candidate, p, {x id: how})] of definition d: def_candidates with local + document clues."""
    tv = _views(v)
    text = v.txt[d]
    out = []
    for i, c in enumerate(def_candidates(text, v.by[d].get("name") or "")):
        hits = {x["id"]: how for x in v.nodes if x["id"] != d and x["type"] not in STEPS
                for how in [ED.uses(c, v.txt[x["id"]], *tv[x["id"]])] if how}
        later = sum(1 for x in hits if v.rank[x] > v.rank[d] and v.by[x]["type"] != "equation")
        earlier = sum(1 for x in hits if v.rank[x] < v.rank[d] and v.by[x]["type"] != "equation")
        f = {**ED.cand_features(c, text, i), **cand_doc_feats(c, later, earlier)}
        out.append((c, f, dmodel.p(f) if dmodel else 0.0, hits))
    return out


def term_pairs(v: View, dmodel) -> list:
    """[(D, X, clues)]: definition D, a node X using one of D's likely definienda (the v7 term rule:
    every LATER Level-1 node that uses the definiendum or the symbol it introduces)."""
    out = []
    for dn in v.nodes:
        d = dn["id"]
        if dn["type"] != "definition":
            continue
        sc = [(c, p, hits) for c, _f, p, hits in scored_candidates(v, d, dmodel) if p >= 0.05]
        if not sc:
            continue
        top = max(p for _c, p, _h in sc)
        nhi = sum(p >= 0.3 for _c, p, _h in sc)
        by_x = collections.defaultdict(list)
        for c, p, hits in sc:
            for x, how in hits.items():
                by_x[x].append((c, p, how))
        later_users = sorted((x for x in by_x if v.rank[x] > v.rank[d] and v.by[x]["type"] != "equation"),
                             key=lambda x: v.rank[x])
        uo = {x: r for r, x in enumerate(later_users)}
        for x, ms in by_x.items():
            c, p, how = max(ms, key=lambda m: m[1] * {"exact": 1, "word": 0.9, "head": 0.6}[m[2]])
            kt = kind(v.by[x]["type"])
            later = v.rank[x] > v.rank[d]
            pb = _b(p, (0.1, 0.2, 0.35, 0.5, 0.7, 0.85))
            od = origin(dn)
            f = {f"t_src={od}": 1.0, f"t_src={od}|p={_b(p, (0.3, 0.6))}": 1.0, f"t_src={od}|how={how}": 1.0,
                 f"t_dlen={_b(len(v.txt[d]), (80, 200, 500, 1200))}": 1.0, f"t_src={od}|x={kt}": 1.0,
                 f"t_how={how}": 1.0, f"t_p={pb}": 1.0, "t_p_raw": p, f"t_how={how}|p={pb}": 1.0,
                 f"t_later={later}": 1.0, f"t_later={later}|x={kt}": 1.0, f"t_how={how}|x={kt}": 1.0,
                 f"t_how={how}|later={later}|p={_b(p, (0.3, 0.6))}": 1.0,
                 f"t_kind={c['kind']}": 1.0, f"t_top={p == top}": 1.0, f"t_nhi={min(nhi, 4)}": 1.0,
                 f"t_nmatch={min(len(ms), 4)}": 1.0,
                 f"t_single={bool(c['math'] and re.fullmatch(r'[A-Za-z]', c['key']))}": 1.0,
                 f"t_users={_b(len(later_users), (1, 3, 8, 20, 50))}": 1.0}
            if x in uo:
                f[f"t_use_order={min(uo[x], 6)}"] = 1.0
                f[f"t_use_order={min(uo[x], 6)}|x={kt}"] = 1.0
            out.append((d, x, f))
    return out


def definiendum_rows(v: View, rnodes: list, al: dict) -> list:
    """Training rows for the definiendum model: our definitions aligned to silver definitions."""
    rid = {n["id"]: n for n in rnodes}
    rows = []
    for dn in v.nodes:
        r = rid.get(al.get(dn["id"]))
        if dn["type"] != "definition" or not r or r["type"] != "definition" or not r.get("definiendum"):
            continue
        maths, words = ED.definiendum_pieces(r["definiendum"])
        for c, f, _p, _h in scored_candidates(v, dn["id"], None):
            rows.append((f, int(ED.is_definiendum(c, maths, words))))
    return rows

# ── candidates and their clues ──────────────────────────────────────────────
def candidates(v: View, dmodel) -> list:
    """[(s, t, feats)] for one paper."""
    C = collections.defaultdict(dict)                # (s, t) -> channel clues
    for d, x, f in term_pairs(v, dmodel):
        g = C[(d, x)]
        g["ch:term"] = 1.0
        g.update(f)
    owner = collections.defaultdict(set)
    for i, ls in v.labs.items():
        for lab in ls:
            owner[lab].add(i)
    for t, rc in v.refs.items():
        for lab, n in rc.items():
            own = owner.get(lab, ())
            inner = min((len(v.txt[o]) for o in own), default=0)
            for s in own:
                if s != t:
                    tag = "inner" if len(v.txt[s]) == inner else "outer"
                    C[(s, t)]["ch:ref"] = 1.0
                    C[(s, t)][f"ref_{tag}"] = 1.0
                    C[(s, t)][f"ref_{tag}|k={kind(v.by[s]['type'])}>{kind(v.by[t]['type'])}"] = 1.0
                    C[(s, t)][f"ref_n={min(n, 3)}"] = 1.0
                    C[(t, s)]["ch:ref_back"] = 1.0
    for (s, t), e in v.parser.items():
        C[(s, t)]["ch:parser"] = 1.0
        C[(s, t)][f"pe={e['type']}"] = 1.0
        C[(s, t)][f"pe_conf={_b(e.get('confidence', 1), (0.5, 0.8, 0.99))}"] = 1.0
        C[(t, s)]["ch:parser_back"] = 1.0
    o = v.order
    for r, t in enumerate(o):
        for k in (1, 2, 3):
            if r - k >= 0:
                C[(o[r - k], t)][f"ch:near_prev{k}"] = 1.0
        if r + 1 < len(o):
            C[(o[r + 1], t)]["ch:near_next1"] = 1.0
        if v.by[t]["type"] == "proof":
            for k in (1, 2, 3):
                if r - k >= 0 and kind(v.by[o[r - k]]["type"]) == "result":
                    C[(t, o[r - k])]["ch:proof_of"] = 1.0
                    C[(o[r - k], t)]["ch:proof_of_back"] = 1.0
                    break
    ids = [n["id"] for n in v.nodes]
    for t in ids:
        if not v.rare[t]:
            continue
        sc = sorted(((v.rare_score(s, t), s) for s in ids if s != t and v.rare[s]), reverse=True)[:3]
        for r, (x, s) in enumerate(sc):
            if x >= 3:
                C[(s, t)][f"ch:rare{r}"] = 1.0
                C[(t, s)][f"ch:rare_back{r}"] = 1.0
    per_t = collections.defaultdict(list)
    for (s, t) in C:
        per_t[t].append(s)
    out = []
    for (s, t), g in C.items():
        if s not in v.by or t not in v.by or s == t:
            continue
        ts, tt = v.by[s]["type"], v.by[t]["type"]
        ks, kt = kind(ts), kind(tt)
        fwd = v.rank[s] < v.rank[t]
        gap = abs(v.rank[s] - v.rank[t])
        rs = v.rare_score(s, t)
        chs = sorted(k[3:].rstrip("0123456789") for k in g if k.startswith("ch:"))
        sig = "+".join(dict.fromkeys(chs))
        f = dict(g)
        os_, ot = origin(v.by[s]), origin(v.by[t])
        f.update({f"os={os_}": 1.0, f"ot={ot}": 1.0, f"os={os_}|ot={ot}": 1.0, f"os={os_}|sig={sig}": 1.0,
                  f"ts={ts}": 1.0, f"tt={tt}": 1.0, f"k={ks}>{kt}": 1.0, f"tp={ts}>{tt}": 1.0,
                  f"fwd={fwd}": 1.0, f"k={ks}>{kt}|fwd={fwd}": 1.0,
                  f"gap={_b(gap, (1, 2, 4, 8, 16, 32, 64))}": 1.0, f"k={ks}>{kt}|gap={_b(gap, (1, 3, 10, 30))}": 1.0,
                  f"samesec={v.sec[s] == v.sec[t]}": 1.0, f"secgap={_b(abs(v.sec[s] - v.sec[t]), (0, 1, 2, 4))}": 1.0,
                  f"rare={_b(rs, (0, 3, 6, 10, 15, 25))}": 1.0, "rare_raw": min(rs, 40) / 40,
                  f"sig={sig}": 1.0, f"k={ks}>{kt}|sig={sig}": 1.0,
                  f"nsrc_t={_b(len(per_t[t]), (2, 5, 10, 20, 40))}": 1.0})
        for c in dict.fromkeys(chs):
            f[f"k={ks}>{kt}|ch={c}"] = 1.0
            f[f"ch={c}|fwd={fwd}"] = 1.0
        out.append((s, t, f))
    by_t = collections.defaultdict(list)
    for i, (s, t, f) in enumerate(out):
        by_t[t].append(i)
    for t, idx in by_t.items():                      # how s ranks among t's candidates
        for r, i in enumerate(sorted(idx, key=lambda i: -out[i][2]["rare_raw"])):
            out[i][2][f"rank_rare={min(r, 4)}"] = 1.0
        prev = sorted((i for i in idx if v.rank[out[i][0]] < v.rank[t]), key=lambda i: -v.rank[out[i][0]])
        for r, i in enumerate(prev):
            out[i][2][f"rank_prev={min(r, 5)}"] = 1.0
        # s among t's preceding DEFINITION sources (term channel), nearest first
        pdef = [i for i in prev if "ch:term" in out[i][2] and v.by[out[i][0]]["type"] == "definition"]
        for r, i in enumerate(pdef):
            out[i][2][f"closest_def={min(r, 4)}"] = 1.0
            out[i][2][f"closest_def={min(r, 4)}|x={kind(v.by[t]['type'])}"] = 1.0
    by_s = collections.defaultdict(list)
    for i, (s, t, f) in enumerate(out):
        if "ch:term" in f:
            by_s[s].append(i)
    for s, idx in by_s.items():                      # t among s's term users, in document order after s
        later = sorted((i for i in idx if v.rank[out[i][1]] > v.rank[s]), key=lambda i: v.rank[out[i][1]])
        nl = len(later)
        for r, i in enumerate(later):
            f = out[i][2]
            kt = kind(v.by[out[i][1]]["type"])
            f[f"use_order={min(r, 6)}"] = 1.0
            f[f"use_order={min(r, 6)}|x={kt}"] = 1.0
            f[f"use_frac={_b(r / max(1, nl), (0.05, 0.15, 0.3, 0.6))}"] = 1.0
            nonq = sum(1 for j in later[:r] if v.by[out[j][1]]["type"] != "equation")
            f[f"use_order_noneq={min(nonq, 6)}"] = 1.0
        for i in idx:
            out[i][2][f"n_later_users={_b(nl, (1, 3, 6, 12, 25, 50))}"] = 1.0
            if v.rank[out[i][1]] < v.rank[s]:
                out[i][2]["use_before_def"] = 1.0
    return out


def stack_features(v: View, rows: list, q: list) -> list:
    P = {(s, t): p for (s, t, _f), p in zip(rows, q)}
    by_t, by_s = collections.defaultdict(list), collections.defaultdict(list)
    for (s, t, _f), p in zip(rows, q):
        by_t[t].append(p)
        by_s[s].append(p)
    st = {t: sorted(x, reverse=True) for t, x in by_t.items()}
    ss = {s: sorted(x, reverse=True) for s, x in by_s.items()}
    hi = collections.defaultdict(list)
    for (s, t, _f), p in zip(rows, q):
        if p >= 0.2:
            hi[s].append(t)
    partner = collections.defaultdict(set)
    for (s, t), e in v.parser.items():
        if e["type"] == "proves":
            partner[s].add(t)
            partner[t].add(s)
    o, rank = v.order, v.rank
    out = []
    for (s, t, f), p in zip(rows, q):
        z = math.log(max(p, 1e-6) / max(1 - p, 1e-6))
        rev = P.get((t, s), 0.0)
        other_t = next((x for x in st[t] if x != p), 0.0)
        r = rank[t]
        nb = max((P.get((s, o[j]), 0.0) for j in (r - 1, r + 1) if 0 <= j < len(o)), default=0.0)
        pt = max((P.get((s, y), 0.0) for y in partner.get(t, ())), default=0.0)
        two = max((min(P.get((s, y), 0.0), P.get((y, t), 0.0)) for y in hi.get(s, ()) if y != t), default=0.0)
        pb = _b(p, (0.1, 0.2, 0.35, 0.5, 0.7))
        ks, kt = kind(v.by[s]["type"]), kind(v.by[t]["type"])
        g = {k: x for k, x in f.items() if k.startswith(("k=", "ch:", "sig=", "fwd="))}
        g.update({"s1_logit": z, f"s1_p={pb}": 1.0, f"s1_k={ks}>{kt}|p={pb}": 1.0,
                  "s1_rev": rev, f"s1_rev={_b(rev, (0.1, 0.3, 0.6))}|p={pb}": 1.0,
                  "s1_other_t": other_t, "s1_gap_t": p - other_t,
                  f"s1_rank_t={min(st[t].index(p), 5)}": 1.0, f"s1_rank_s={min(ss[s].index(p), 10) // 2}": 1.0,
                  f"s1_nt_hi={_b(sum(x >= 0.3 for x in st[t]), (0, 1, 3, 6, 12))}": 1.0,
                  f"s1_ns_hi={_b(sum(x >= 0.3 for x in ss[s]), (0, 2, 5, 12, 30))}": 1.0,
                  "s1_nb": nb, f"s1_nb={_b(nb, (0.1, 0.3, 0.6))}|p={pb}": 1.0,
                  "s1_partner": pt, f"s1_partner={_b(pt, (0.1, 0.3, 0.6))}|p={pb}": 1.0,
                  "s1_two": two, f"s1_two={_b(two, (0.1, 0.3, 0.6))}|p={pb}": 1.0})
        out.append(g)
    return out


# ── runtime ─────────────────────────────────────────────────────────────────
class Model:
    def __init__(self, model_dir):
        d = json.load(open(Path(model_dir) / "model.json", encoding="utf-8"))
        self.dmodel, self.s1 = ED.LR(d["definiendum"]), ED.LR(d["stage1"])
        self.s2 = ED.LR(d["stage2"]) if d.get("stage2") else None
        self.threshold, self.id = d["threshold"], d.get("id", Path(model_dir).name)


def score_graph(graph: dict, tex: str | None, m: Model) -> list:
    v = View(graph, tex)
    rows = candidates(v, m.dmodel)
    q = [m.s1.p(f) for _s, _t, f in rows]
    if m.s2 is not None:
        q = [m.s2.p(g) for g in stack_features(v, rows, q)]
    return v, [(s, t, p) for (s, t, _f), p in zip(rows, q)]


def apply(graph: dict, tex: str | None, m: Model, threshold: float | None = None) -> dict:
    """Replace the graph's edges by the candidates scoring >= threshold, in place. A dropped
    parser edge from an equation to the node containing it is kept as the equation's parent_id."""
    th = m.threshold if threshold is None else threshold
    v, scored = score_graph(graph, tex, m)
    keep = {(s, t) for s, t, p in scored if p >= th}
    new = []
    for e in graph.get("edges", []):
        k = (e["source"], e["target"])
        if k in keep or e["source"] not in v.by or e["target"] not in v.by:
            new.append(e)
            keep.discard(k)
            continue
        eq, box = v.by.get(e["source"]), v.by.get(e["target"])
        if eq["type"] == "equation" and e["type"] == "uses" and not eq.get("parent_id") \
                and _sq(ED.node_text(eq)) and _sq(ED.node_text(eq)) in _sq(ED.node_text(box)):
            eq["parent_id"] = box["id"]
    pmap = {(s, t): p for s, t, p in scored}
    for s, t in sorted(keep, key=lambda k: -pmap[k]):
        typ = "proves" if v.by[s]["type"] == "proof" and kind(v.by[t]["type"]) == "result" else "uses"
        new.append({"source": s, "target": t, "type": typ, "confidence": round(pmap[(s, t)], 3), "provenance": m.id})
    graph["edges"] = new
    return graph


# ── training ────────────────────────────────────────────────────────────────
_W: dict = {}


def _init(graphs, silver, tex, dmodel):
    _W.update(graphs=Path(graphs), silver=Path(silver), tex=Path(tex), dmodel=ED.LR(dmodel) if dmodel else None)


def _defrows(pid):
    import edge_metrics as EM
    from graph_io import load_graph
    g = json.load(open(_W["graphs"] / f"{pid}.json", encoding="utf-8"))
    v = View(g, _tex_of(_W["tex"], pid))
    rn, _ = EM.level1(*load_graph(_W["silver"] / f"{pid}.json"))
    pn, _ = load_graph(_W["graphs"] / f"{pid}.json")
    return definiendum_rows(v, rn, EM.align(pn, rn))


def _tex_of(tex_dir: Path, pid: str) -> str | None:
    import latex_facts as L
    m = L.find_main_tex(tex_dir / pid / "source")
    return open(m, encoding="utf-8", errors="ignore").read() if m else None


def _paper(pid):
    import edge_metrics as EM
    from graph_io import load_graph
    g = json.load(open(_W["graphs"] / f"{pid}.json", encoding="utf-8"))
    v = View(g, _tex_of(_W["tex"], pid))
    rows = candidates(v, _W["dmodel"])
    rn, re_ = EM.level1(*load_graph(_W["silver"] / f"{pid}.json"))
    rid = {n["id"] for n in rn}
    pn, _ = load_graph(_W["graphs"] / f"{pid}.json")
    al = EM.align(pn, rn)
    gold = {(e["source"], e["target"]) for e in re_ if e["source"] in rid and e["target"] in rid}
    y = [int((al.get(s), al.get(t)) in gold and al.get(s) != al.get(t)) for s, t, _f in rows]
    return pid, g, rows, y, len(gold)


def fit(X, y, C):
    return ED.LR.fit(X, y, C, class_weight=None)


def pooled_f1(papers, q, th):
    tp = pr = ref = 0
    for pid, (rows, y, nref) in papers.items():
        for p, l in zip(q[pid], y):
            if p >= th:
                pr += 1
                tp += l
        ref += nref
    P, R = tp / max(1, pr), tp / max(1, ref)
    return 2 * P * R / max(1e-9, P + R), P, R


def cmd_train(a):
    import multiprocessing as mp
    t0 = time.time()
    split = {r.get("arxiv_id") or r["paper_id"]: r["split"] for r in csv.DictReader(open(a.split))}
    train = sorted(p for p, s in split.items() if s == "train")
    val = sorted(p for p, s in split.items() if s == "val")
    with mp.Pool(a.workers, initializer=_init, initargs=(a.graphs, a.silver, a.tex, None)) as pool:
        drows = [r for rows in pool.imap_unordered(_defrows, train) for r in rows]
    dmodel = fit([f for f, _l in drows], [l for _f, l in drows], 0.3)
    print(f"[definiendum] {len(drows)} candidates of train definitions, {sum(l for _f, l in drows)} positive "
          f"({time.time() - t0:.0f}s)", flush=True)
    with mp.Pool(a.workers, initializer=_init, initargs=(a.graphs, a.silver, a.tex, dmodel)) as pool:
        data = {pid: (g, rows, y, nref) for pid, g, rows, y, nref in pool.imap_unordered(_paper, train + val)}
    npairs = sum(len(d[1]) for d in data.values())
    npos = sum(sum(d[2]) for p, d in data.items() if p in train)
    print(f"[data] {len(data)} papers, {npairs} candidate pairs, {npos} positive (train); "
          f"reachable by candidates: {npos}/{sum(data[p][3] for p in train)} silver edges ({time.time() - t0:.0f}s)", flush=True)
    rnd = random.Random(a.seed)
    tr = list(train)
    rnd.shuffle(tr)
    folds = [tr[k::5] for k in range(5)]

    def oof(featfn, C):
        q = {}
        for k in range(5):
            held = set(folds[k])
            X = [f for p in train if p not in held for f in featfn(p)]
            Y = [l for p in train if p not in held for l in data[p][2]]
            m = ED.LR(fit(X, Y, C))
            for p in folds[k]:
                q[p] = [m.p(f) for f in featfn(p)]
        m = ED.LR(fit([f for p in train for f in featfn(p)], [l for p in train for l in data[p][2]], C))
        for p in val:
            q[p] = [m.p(f) for f in featfn(p)]
        return q, m
    s1_feats = {p: [f for _s, _t, f in data[p][1]] for p in data}
    q1, m1 = oof(lambda p: s1_feats[p], a.C)
    views = {p: View(data[p][0], _tex_of(Path(a.tex), p)) for p in data}
    s2_feats = {p: stack_features(views[p], data[p][1], q1[p]) for p in data}
    q2, m2 = oof(lambda p: s2_feats[p], a.C2)
    P_tr = {p: (data[p][1], data[p][2], data[p][3]) for p in train}
    P_va = {p: (data[p][1], data[p][2], data[p][3]) for p in val}
    ths = [x / 100 for x in range(10, 71)]
    res = {}
    for name, q in (("stage1", q1), ("stage2", q2)):
        best = max(ths, key=lambda th: pooled_f1(P_tr, q, th)[0])
        fo, po, ro = pooled_f1(P_tr, q, best)
        fv, pv, rv = pooled_f1(P_va, q, best)
        res[name] = (fo, best, fv)
        print(f"[{name}] threshold {best}: train OOF F1 {fo:.4f} (P {po:.3f} R {ro:.3f}) | "
              f"val F1 {fv:.4f} (P {pv:.3f} R {rv:.3f})", flush=True)
    use2 = res["stage2"][0] > res["stage1"][0] + 0.001         # stage 2 only if it helps out of fold
    th = res["stage2" if use2 else "stage1"][1]
    print(f"[choice] {'stage1 + stage2' if use2 else 'stage1 only'} (by train OOF), threshold {th}", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model = {"id": out.name, "kind": "allpairs", "threshold": th, "definiendum": dmodel,
             "stage1": {"vocab": m1.vocab, "coef": m1.coef, "intercept": m1.b},
             "stage2": {"vocab": m2.vocab, "coef": m2.coef, "intercept": m2.b} if use2 else None,
             "train": {"oof_F1": round(res["stage2" if use2 else "stage1"][0], 4),
                       "val_F1": round(res["stage2" if use2 else "stage1"][2], 4),
                       "seed": a.seed, "C": a.C, "C2": a.C2, "graphs": str(a.graphs), "silver": str(a.silver),
                       "split": str(a.split), "papers": {"train": len(train), "val": len(val)}}}
    (out / "model.json").write_text(json.dumps(model), encoding="utf-8")
    print(f"[model] -> {out} ({time.time() - t0:.0f}s)")


def cmd_apply(a):
    m = Model(a.model)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(Path(a.graphs).glob("*.json")):
        g = json.load(open(f, encoding="utf-8"))
        apply(g, _tex_of(Path(a.tex), f.stem) if a.tex else None, m, a.threshold)
        (out / f.name).write_text(json.dumps(g), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--graphs", required=True)
    t.add_argument("--silver", required=True)
    t.add_argument("--split", required=True)
    t.add_argument("--tex", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--C", type=float, default=0.3)
    t.add_argument("--C2", type=float, default=0.3)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--workers", type=int, default=6)
    p = sub.add_parser("apply")
    p.add_argument("--graphs", required=True)
    p.add_argument("--tex", default=None)
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()
    {"train": cmd_train, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    main()
