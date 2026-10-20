#!/usr/bin/env python3
"""Train the alg3 sentence tagger and write it as an extractor directory.

Separation of roles: the teacher's labels (the v6 silver) say WHICH sentences
start a node and of which type; a statistical learner, not the teacher, decides
how the cues combine. Every cue is a deterministic string test (alg3/features.py),
and the learned model is a table of weights over those tests, applied by a few
lines of Python at parse time: no neural network, no API call.

  anchor model   multinomial logistic regression over sentence features:
                 none / definition / claim / remark / ... for each prose sentence
  span model     multinomial logistic regression: how many sentences the node
                 anchored there covers (1..4 or to the end of its paragraph)
  decoding       sentences in document order; a sentence starts a node of type t
                 when P(t) is its largest type probability and >= tau_t; a sentence
                 inside an emitted node starts no other
  thresholds     tau_t chosen on out-of-fold predictions over the training papers
                 (folds by paper) to maximise the overall F of the whole extractor
                 (base parser + tagger) under the headline metric (m1g)

Model selection uses the validation papers only; the test papers are never read.

    python3 alg3/train.py --data alg3/cache/papers.pkl --out alg3/runs/<name>
"""
from __future__ import annotations

import argparse
import json
import pickle
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

REPO = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
for p in (HERE, REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_units as DU                                   # noqa: E402,F401  (unpickling)
import features as FT                                        # noqa: E402
import latex_facts as L                                      # noqa: E402
import unit_rules as UR                                      # noqa: E402

SPANS = ["1", "2", "3", "4", "para"]
GRID = [round(x, 2) for x in np.arange(0.15, 0.96, 0.05)]


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def views(papers: dict) -> dict:
    out = {}
    for pid, (_, p) in papers.items():
        out[pid] = FT.PaperView(p.text, L.extract_facts(p.text), p.sents)
    return out


def rows(pids, papers, pvs):
    """Anchor rows: (pid, sentence index, features, label) for every prose sentence."""
    X, y, g, idx = [], [], [], []
    for pid in pids:
        p, pv = papers[pid][1], pvs[pid]
        for i in range(len(p.sents)):
            X.append(FT.sentence_features(pv, i))
            n = p.anchor.get(i)
            y.append(n.type if n is not None else "none")
            g.append(pid)
            idx.append((pid, i))
    return X, np.array(y), np.array(g), idx


def span_label(p, n) -> str:
    k = n.last - n.first + 1
    if k <= 4:
        return str(k)
    return "para"


def span_rows(pids, papers, pvs):
    X, y, g = [], [], []
    for pid in pids:
        p, pv = papers[pid][1], pvs[pid]
        for i, n in p.anchor.items():
            X.append(FT.span_features(pv, i, n.type))
            y.append(span_label(p, n))
            g.append(pid)
    return X, np.array(y), np.array(g)


def prune_rare(X, min_count: int):
    c = Counter(k for d in X for k in d)
    keep = {k for k, v in c.items() if v >= min_count}
    return [{k: v for k, v in d.items() if k in keep} for d in X], keep


# ---------------------------------------------------------------------------
# decoding and scoring (the unit algorithm's matcher and accounting)
# ---------------------------------------------------------------------------

def decode(p, probs, classes, span_pred, tau) -> list:
    """probs: (n_sent, n_class); span_pred: sentence -> span string."""
    none = classes.index("none")
    out, covered = [], -1
    for i in range(len(p.sents)):
        if i <= covered:
            continue
        row = probs[i].copy()
        row[none] = -1
        c = int(np.argmax(row))
        t = classes[c]
        if row[c] < tau.get(t, 1.01):
            continue
        j = UR.span_end(p.sents, i, span_pred.get(i, "1"))
        out.append({"type": t, "start": p.sents[i].start, "end": p.sents[j].end, "uid": 0})
        covered = j
    return out


_TOK: dict = {}


def tokens(p, pred) -> frozenset:
    """A prediction's token set, cached (threshold tuning scores the same spans
    hundreds of times)."""
    key = (p.pid, pred["start"], pred["end"])
    if key not in _TOK:
        _TOK[key] = frozenset(DU.mm.tokens(p.text[pred["start"]:pred["end"]]))
    return _TOK[key]


def evaluate(scorer, papers: dict, pids, preds: dict) -> dict:
    tp = fp = neutral = 0.0
    targets = 0
    for pid in pids:
        p = papers[pid][1]
        targets += sum(not n.base_covered for n in p.nodes)
        ps = preds.get(pid, [])
        m = scorer.match(p, ps, [tokens(p, q) for q in ps])
        for i in range(len(ps)):
            k, w = m.get(i, (None, 0.0))
            if k is None:
                fp += 1
            elif p.nodes[k].base_covered:
                neutral += 1
            else:
                tp += w
                fp += 1 - w
    a_tp = sum(papers[q][1].base_tp for q in pids) + tp
    a_fp = sum(papers[q][1].base_fp for q in pids) + fp
    a_fn = max(sum(papers[q][1].n_silver for q in pids) - a_tp, 0)
    den = 2 * a_tp + a_fn + a_fp
    return {"tp": round(tp, 1), "fp": round(fp, 1), "neutral": int(neutral), "targets": targets,
            "P": round(a_tp / (a_tp + a_fp), 4) if a_tp + a_fp else 0.0,
            "R": round(a_tp / (a_tp + a_fn), 4) if a_tp + a_fn else 0.0,
            "F": round(2 * a_tp / den, 4) if den else 0.0}


def candidates(scorer, papers, pids, prob_by, classes, span_by) -> dict:
    """Per paper and sentence: the type it would be emitted with, its probability,
    the last sentence of its span, and every silver node it could match (the
    matcher's candidate pairs, node_metrics._pairs). Thresholds only decide
    which candidates are emitted, so tuning never touches text again."""
    none = classes.index("none")
    out = {}
    for pid in pids:
        p = papers[pid][1]
        G = [(n.type, n.tokens) for n in p.nodes]
        rows_ = []
        for i in range(len(p.sents)):
            row = prob_by[pid][i].copy()
            row[none] = -1
            c = int(np.argmax(row))
            t = classes[c]
            j = UR.span_end(p.sents, i, span_by[pid].get(i, "1"))
            tok = tokens(p, {"start": p.sents[i].start, "end": p.sents[j].end})
            rows_.append((t, float(row[c]), j, DU.NM._pairs([(t, tok)], G, scorer.weight, scorer.th)))
        out[pid] = rows_
    return out


def fast_eval(cands, papers, pids, tau) -> float:
    """Overall F of decode + evaluate, from candidates() (same result, no text)."""
    tp = fp = 0.0
    for pid in pids:
        p = papers[pid][1]
        covered, pairs = -1, []
        for i, (t, pr, j, m) in enumerate(cands[pid]):
            if i <= covered or pr < tau.get(t, 1.01):
                continue
            covered = j
            fp += 1
            pairs += [(s, jac, i, k, w) for s, jac, _, k, w in m]
        for k, w in DU.NM._greedy(pairs).values():
            fp -= 1
            if not p.nodes[k].base_covered:
                tp += w
                fp += 1 - w
    a_tp = sum(papers[q][1].base_tp for q in pids) + tp
    a_fp = sum(papers[q][1].base_fp for q in pids) + fp
    a_fn = max(sum(papers[q][1].n_silver for q in pids) - a_tp, 0)
    den = 2 * a_tp + a_fn + a_fp
    return 2 * a_tp / den if den else 0.0


def tune_tau(scorer, papers, pids, prob_by, classes, span_by, rounds: int = 3, e2e=None) -> tuple:
    """Coordinate ascent over per-type thresholds, maximising overall F: the unit
    matcher's (base counts + tagger), or with `e2e` the end-to-end F of the whole
    graph (the parser's own nodes + the tagger's, after the parser's merge)."""
    types = [c for c in classes if c != "none"]
    tau = {t: 0.5 for t in types}
    if e2e is not None:
        cands = e2e.candidates(papers, pids, prob_by, classes, span_by)
        score = lambda tr: e2e.fast(cands, pids, tr)            # noqa: E731
    else:
        cands = candidates(scorer, papers, pids, prob_by, classes, span_by)
        score = lambda tr: fast_eval(cands, papers, pids, tr)   # noqa: E731
    best = score(tau)
    for rnd in range(rounds):
        print(f"    [tau] round {rnd + 1}: F={best:.4f}", flush=True)
        changed = False
        for t in types:
            for v in GRID + [1.01]:
                if v == tau[t]:
                    continue
                trial = dict(tau, **{t: v})
                f = score(trial)
                if f > best + 1e-5:
                    best, tau, changed = f, trial, True
        if not changed:
            break
    # the fast path must agree with the full decode + evaluate
    preds = {pid: decode(papers[pid][1], prob_by[pid], classes, span_by[pid], tau) for pid in pids}
    full = e2e.full(papers, pids, preds) if e2e is not None else evaluate(scorer, papers, pids, preds)["F"]
    assert abs(round(full, 4) - round(best, 4)) < 2e-4, (full, best)
    return tau, best


# ---------------------------------------------------------------------------
# end-to-end objective: the whole graph against the Level-1 silver
# ---------------------------------------------------------------------------

GRAPHS = HERE / "runs/val_graphs/alg3_v2b"
SILVER = REPO / "corpus/silver/opus-5.5__v6"


def _txt(n) -> str:
    return n.get("raw_latex") or n.get("statement") or ""


class E2E:
    """analyze.py's graph metric (nodes, m1g, pooled) with the tagger's nodes
    swapped: the parser's own (non-distilled) nodes of a parsed graph stay fixed,
    the tagger's predictions are merged in as the parser merges them (dropped when
    a same-type kept node contains, or is contained in, 70% of its tokens) and the
    whole set is paired one-to-one with the Level-1 silver nodes."""

    def __init__(self, pids, graphs: Path = GRAPHS):
        import edge_metrics as EM
        import node_similarity as NS
        from distill_common import TYPES
        from graph_io import load_graph
        self.NS = NS
        types = set(TYPES)
        self.base, self.G, self.bpairs = {}, {}, {}
        for pid in pids:
            f = graphs / f"{pid}.json"
            if not f.is_file():
                continue
            pn, _ = load_graph(f)
            rn, _ = EM.level1(*load_graph(SILVER / f"{pid}.json"))
            B = [(n["type"], frozenset(DU.mm.tokens(_txt(n)))) for n in pn
                 if n["type"] in types and _txt(n).strip() and n.get("env_name") != "distilled"
                 and not str(n.get("id", "")).startswith("DIST_")]     # distilled proofs etc.
            G = [(n["type"], frozenset(DU.mm.tokens(n.get("statement") or ""))) for n in rn
                 if n["type"] in types and (n.get("statement") or "").strip()]
            self.base[pid], self.G[pid] = B, G
            self.bpairs[pid] = DU.NM._pairs(B, G, NS.type_compat, DU.NM.THRESHOLD)
        print(f"    [e2e] {len(self.base)} parsed graphs from {graphs.name}", flush=True)

    def covers(self, pid):
        return pid in self.base

    @staticmethod
    def _dup(t, tok, kept) -> bool:
        if not tok:
            return False
        for kt, kk in kept:
            if kt == t and kk and len(tok & kk) / min(len(tok), len(kk)) >= 0.7:
                return True
        return False

    def candidates(self, papers, pids, prob_by, classes, span_by) -> dict:
        none = classes.index("none")
        out = {}
        for pid in pids:
            p, B, G = papers[pid][1], self.base[pid], self.G[pid]
            rows_ = []
            for i in range(len(p.sents)):
                row = prob_by[pid][i].copy()
                row[none] = -1
                c = int(np.argmax(row))
                t = classes[c]
                j = UR.span_end(p.sents, i, span_by[pid].get(i, "1"))
                tok = tokens(p, {"start": p.sents[i].start, "end": p.sents[j].end})
                dup = self._dup(t, tok, B)
                pairs = [] if dup else [(s, jac, len(B) + i, k, w) for s, jac, _, k, w in
                                        DU.NM._pairs([(t, tok)], G, self.NS.type_compat, DU.NM.THRESHOLD)]
                rows_.append([t, float(row[c]), j, dup, pairs, tok, ()])
            # earlier candidates of the same type a candidate would duplicate (the
            # merge also drops a node contained in an already-kept distilled one)
            live = [i for i, r in enumerate(rows_) if r[1] >= GRID[0] and not r[3]]
            for x, i in enumerate(live):
                ti, ki = rows_[i][0], rows_[i][5]
                rows_[i][6] = tuple(k for k in live[:x] if self._dup(ti, ki, [(rows_[k][0], rows_[k][5])]))
            out[pid] = [tuple(r[:5]) + (r[6],) for r in rows_]
        return out

    def fast(self, cands, pids, tau) -> float:
        tp = 0.0
        pred = gold = 0
        for pid in pids:
            covered, pairs, n, kept = -1, list(self.bpairs[pid]), len(self.base[pid]), set()
            for i, (t, pr, j, dup, m, prior) in enumerate(cands[pid]):
                if i <= covered or pr < tau.get(t, 1.01):
                    continue
                covered = j
                if not dup and not any(k in kept for k in prior):
                    kept.add(i)
                    n += 1
                    pairs += m
            tp += sum(w for _, w in DU.NM._greedy(pairs).values())
            pred += n
            gold += len(self.G[pid])
        return 2 * tp / (pred + gold) if pred + gold else 0.0

    def full(self, papers, pids, preds, grow: bool = True) -> float:
        """Same number from decoded predictions (grow: a prediction is also dropped
        as a duplicate of an earlier kept prediction, as the merge does)."""
        tp = 0.0
        pred = gold = 0
        for pid in pids:
            p, B, G = papers[pid][1], self.base[pid], self.G[pid]
            P = list(B)
            for q in preds.get(pid, []):
                tok = tokens(p, q)
                if not self._dup(q["type"], tok, P if grow else B):
                    P.append((q["type"], tok))
            tp += sum(w for _, w in DU.NM._one_to_one(P, G, self.NS.type_compat, DU.NM.THRESHOLD).values())
            pred += len(P)
            gold += len(G)
        return 2 * tp / (pred + gold) if pred + gold else 0.0


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def class_weights(y, mode: str):
    """none | balanced | sqrt: rare node types weighted up (sqrt: halfway)."""
    if mode == "none":
        return None
    c = Counter(y)
    top = max(c.values())
    power = 1.0 if mode == "balanced" else 0.5
    return {k: (top / v) ** power for k, v in c.items()}


class GB:
    """Gradient-boosted trees (xgboost, multi:softprob) with the LogisticRegression
    interface used here (fit / predict_proba / classes_). Absent clues are 'missing'
    in xgboost's sparse input, so a tree tests only clues that fire."""
    PARAMS = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.1, "subsample": 0.8,
              "colsample_bytree": 0.5, "min_child_weight": 2, "tree_method": "hist"}

    def __init__(self, cw: str = "none", n_jobs: int = 8, **kw):
        self.cw, self.n_jobs, self.params = cw, n_jobs, dict(self.PARAMS, **kw)

    def fit(self, M, y):
        import xgboost as xgb
        self.classes_ = np.array(sorted(set(y)))
        code = {c: k for k, c in enumerate(self.classes_)}
        w = class_weights(y, self.cw)
        self.model = xgb.XGBClassifier(objective="multi:softprob", n_jobs=self.n_jobs, random_state=0,
                                       **self.params)
        self.model.fit(M, np.array([code[c] for c in y]),
                       sample_weight=None if w is None else np.array([w[c] for c in y]))
        return self

    def predict_proba(self, M):
        return self.model.predict_proba(M)

    def predict(self, M):
        return self.classes_[self.predict_proba(M).argmax(1)]


CLASSIFIER = {"kind": "lr", "n_jobs": 8}


def make_clf(C: float, y, cw: str, n_jobs: int | None = None):
    if CLASSIFIER["kind"] == "gb":
        return GB(cw, n_jobs or CLASSIFIER["n_jobs"])
    return LogisticRegression(C=C, max_iter=3000, solver="lbfgs", class_weight=class_weights(y, cw))


def fit_lr(X, y, C: float, cw: str = "none", kind: str = "lr"):
    """The anchor models use the --classifier (kind "anchor"); the span model is always LR."""
    vec = DictVectorizer(sparse=True)
    M = vec.fit_transform(X)
    clf = make_clf(C, y, cw) if kind == "anchor" else \
        LogisticRegression(C=C, max_iter=3000, solver="lbfgs", class_weight=class_weights(y, cw))
    clf.fit(M, y)
    return vec, clf


def predict_lr(vec, clf, X):
    return clf.predict_proba(vec.transform(X))


def by_paper(idx, probs):
    out = {}
    for (pid, i), row in zip(idx, probs):
        out.setdefault(pid, {})[i] = row
    return {pid: np.array([d[i] for i in sorted(d)]) for pid, d in out.items()}


def span_choices(pids, papers, pvs, svec, sclf, prob_by, classes):
    """Span chosen for every sentence, for the type it would be emitted with."""
    out = {}
    none = classes.index("none")
    for pid in pids:
        p, pv = papers[pid][1], pvs[pid]
        P = prob_by[pid].copy()
        P[:, none] = -1
        types = [classes[int(c)] for c in P.argmax(1)]
        X = [FT.span_features(pv, i, types[i]) for i in range(len(p.sents))]
        sp = sclf.predict(svec.transform(X)) if X else []
        out[pid] = {i: str(s) for i, s in enumerate(sp)}
    return out


def export(out: Path, vec, clf, svec, sclf, tau, meta: dict, stage2=None) -> None:
    out.mkdir(parents=True, exist_ok=True)

    def table(v, c, thresh=1e-4):
        names = v.get_feature_names_out()
        W = c.coef_
        weights = {}
        for j, name in enumerate(names):
            col = W[:, j]
            if np.max(np.abs(col)) >= thresh:
                weights[name] = [round(float(x), 5) for x in col]
        return {"classes": [str(x) for x in c.classes_],
                "intercept": [round(float(x), 5) for x in c.intercept_],
                "weights": weights}

    model = {"version": FT.FEATURES_VERSION, "anchor": table(vec, clf), "span": table(svec, sclf),
             "tau": tau, "meta": meta}
    if stage2 is not None:
        model["stage2"] = table(*stage2)
    (out / "sentence_model.json").write_text(json.dumps(model), encoding="utf-8")
    shutil.copy(HERE / "features.py", out / "alg3_features.py")
    shutil.copy(HERE / "runtime.py", out / "alg3_runtime.py")
    types = [t for t in (model.get("stage2") or model["anchor"])["classes"] if t != "none"]
    lines = [IMPORTER]
    for t in sorted(set(types) | set(DU.SCORED)):
        lines.append(f"\ndef extract_distilled_{t}(text):\n"
                     f"    return [d for d in _rt.extract(text) if d['structure_type'] == {t!r}]\n")
    (out / "distilled_rules.py").write_text("".join(lines), encoding="utf-8")


IMPORTER = '''# AUTO-GENERATED by alg3/train.py: a learned sentence tagger (alg3).
# The model is data (sentence_model.json next to this file); alg3_runtime.py
# applies it with the same feature code that trained it (alg3_features.py).
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.realpath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
import alg3_runtime as _rt


def extract_distilled_all(text):
    return _rt.extract(text)
'''


# ---------------------------------------------------------------------------

def _fit_fold(Mtr, ytr, Mte, C, cw, classes, kind="lr", n_jobs=1):
    CLASSIFIER["kind"] = kind
    clf = make_clf(C, ytr, cw, n_jobs)
    clf.fit(Mtr, ytr)
    cols = [classes.index(str(c)) for c in clf.classes_]
    return cols, clf.predict_proba(Mte)


FOLD_SEED: dict = {"seed": None}


def stage_probs(X, y, g, C, cw, folds, jobs: int = 5, vocab: str = "fold"):
    """Out-of-fold class probabilities (folds by paper, fitted in parallel).
    vocab "fold": each fold's clue vocabulary is built from its own training
    part (the released v2b); "global": once, from all training papers (v2b-fast).
    The two differ only in clues that occur in one fold alone."""
    from joblib import Parallel, delayed
    classes = sorted(set(y))
    seed = FOLD_SEED["seed"]
    gkf = GroupKFold(folds) if seed is None else GroupKFold(folds, shuffle=True, random_state=seed)
    splits = list(gkf.split(X, y, g))
    if vocab == "global":
        M = DictVectorizer(sparse=True).fit_transform(X)
        parts = [(M[tr], y[tr], M[te]) for tr, te in splits]
    else:
        parts = []
        for tr, te in splits:
            vec = DictVectorizer(sparse=True)
            parts.append((vec.fit_transform([X[j] for j in tr]), y[tr],
                          vec.transform([X[j] for j in te])))
    nj = max(1, CLASSIFIER["n_jobs"] // min(jobs, folds))
    res = Parallel(n_jobs=min(jobs, folds))(
        delayed(_fit_fold)(Mtr, ytr, Mte, C, cw, classes, CLASSIFIER["kind"], nj) for Mtr, ytr, Mte in parts)
    P = np.zeros((len(X), len(classes)))
    for (tr, te), (cols, Pf) in zip(splits, res):
        P[np.ix_(te, cols)] = Pf
    print(f"    [cv] {folds} folds fitted (vocabulary per {vocab})", flush=True)
    return P, classes


def with_context(X, idx, P, classes, papers):
    """X plus the second-pass context features built from probabilities P."""
    pb = by_paper(idx, P)
    out = []
    for d, (pid, i) in zip(X, idx):
        e = dict(d)
        e.update(FT.context_features(pb[pid], i, papers[pid][1].sents, classes))
        out.append(e)
    return out


def full_probs(vec, clf, X, classes):
    P = predict_lr(vec, clf, X)
    cols = [classes.index(str(c)) for c in clf.classes_]
    out = np.zeros((len(X), len(classes)))
    out[:, cols] = P
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "cache/papers.pkl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--C", type=float, default=0.3)
    ap.add_argument("--class-weight", default="none", choices=["none", "sqrt", "balanced"])
    ap.add_argument("--stack", action="store_true", help="second pass with neighbours' probabilities")
    ap.add_argument("--span-C", type=float, default=0.3)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=5, help="folds fitted at once")
    ap.add_argument("--vocab", choices=["fold", "global"], default="fold",
                    help="clue vocabulary of the cross-validation fits: per fold (released v2b) or global")
    ap.add_argument("--tau-rounds", type=int, default=3, help="coordinate-ascent rounds for the thresholds")
    ap.add_argument("--clues", default=None, help="teacher-invented clues (alg3/invent.py), JSON")
    ap.add_argument("--dump-oof", default=None, help="save out-of-fold train predictions (pickle)")
    ap.add_argument("--classifier", choices=["lr", "gb"], default="lr",
                    help="anchor model: logistic regression (released) or gradient-boosted trees (xgboost)")
    ap.add_argument("--threads", type=int, default=8, help="gb: CPU threads in all")
    ap.add_argument("--seed", type=int, default=None, help="shuffle the paper folds with this seed")
    ap.add_argument("--objective", choices=["unit", "e2e"], default="unit",
                    help="threshold objective: the unit matcher (default, released v2b) or the end-to-end graph F (opt-in)")
    ap.add_argument("--graphs", default=str(GRAPHS), help="parsed train+val graphs for --objective e2e (alg3/analyze.py --parse-train; v6 silver)")
    ap.add_argument("--silver", default=str(SILVER), help="silver graphs for the end-to-end score, <paper>.json (default v6)")
    a = ap.parse_args()
    globals()["SILVER"] = Path(a.silver)
    CLASSIFIER.update(kind=a.classifier, n_jobs=a.threads)
    FOLD_SEED["seed"] = a.seed
    t0 = time.time()
    clues = json.load(open(a.clues, encoding="utf-8")) if a.clues else []
    FT.set_clues(clues)
    papers = pickle.load(open(a.data, "rb"))
    train = sorted(p for p, (s, _) in papers.items() if s == "train")
    val = sorted(p for p, (s, _) in papers.items() if s == "val")
    assert not any(s == "test" for s, _ in papers.values()), "test papers in the training data"
    print(f"[alg3] {len(train)} train + {len(val)} val papers; C={a.C} class_weight={a.class_weight} "
          f"stack={a.stack} classifier={a.classifier}", flush=True)
    pvs = views(papers)
    scorer = DU.Scorer({pid: p for pid, (_, p) in papers.items()}, 0.7, metric="m1g")
    Xtr, ytr, gtr, itr = rows(train, papers, pvs)
    Xva, yva, gva, iva = rows(val, papers, pvs)
    Xtr, keep = prune_rare(Xtr, a.min_count)
    Xva = [{k: v for k, v in d.items() if k in keep} for d in Xva]
    print(f"[alg3] {len(Xtr)} train sentences, {len(keep)} features ({time.time() - t0:.0f}s)", flush=True)
    Str, sytr, sgtr = span_rows(train, papers, pvs)

    # stage 1: out-of-fold on train, full model for val
    P1, classes = stage_probs(Xtr, ytr, gtr, a.C, a.class_weight, a.folds, a.jobs, a.vocab)
    vec1, clf1 = fit_lr(Xtr, ytr, a.C, a.class_weight, kind="anchor")
    P1va = full_probs(vec1, clf1, Xva, classes)
    stage2 = None
    if a.stack:
        X2tr = with_context(Xtr, itr, P1, classes, papers)
        X2va = with_context(Xva, iva, P1va, classes, papers)
        Ptr, _ = stage_probs(X2tr, ytr, gtr, a.C, a.class_weight, a.folds, a.jobs, a.vocab)
        vec2, clf2 = fit_lr(X2tr, ytr, a.C, a.class_weight, kind="anchor")
        Pva = full_probs(vec2, clf2, X2va, classes)
        stage2 = (vec2, clf2)
    else:
        Ptr, Pva = P1, P1va
    print(f"[alg3] models fitted ({time.time() - t0:.0f}s)", flush=True)

    # spans (trained on the silver anchors), thresholds on out-of-fold train predictions
    svec, sclf = fit_lr(Str, sytr, a.span_C)
    prob_tr, prob_va = by_paper(itr, Ptr), by_paper(iva, Pva)
    span_tr = span_choices(train, papers, pvs, svec, sclf, prob_tr, classes)
    e2e = E2E(train + val, Path(a.graphs))
    assert all(e2e.covers(pid) for pid in train + val), "a train/val paper has no parsed graph"
    tau, f_oof = tune_tau(scorer, papers, train, prob_tr, classes, span_tr, a.tau_rounds,
                          e2e if a.objective == "e2e" else None)
    if a.dump_oof:
        dump = {pid: {"probs": prob_tr[pid], "classes": classes,
                      "preds": decode(papers[pid][1], prob_tr[pid], classes, span_tr[pid], tau)}
                for pid in train}
        with open(a.dump_oof, "wb") as fh:
            pickle.dump(dump, fh)
    span_va = span_choices(val, papers, pvs, svec, sclf, prob_va, classes)
    preds = {pid: decode(papers[pid][1], prob_va[pid], classes, span_va[pid], tau) for pid in val}
    rv = evaluate(scorer, papers, val, preds)
    base = evaluate(scorer, papers, val, {})
    preds_tr = {pid: decode(papers[pid][1], prob_tr[pid], classes, span_tr[pid], tau) for pid in train}
    e_oof = e2e.full(papers, train, preds_tr, grow=True)
    e_val = e2e.full(papers, val, preds, grow=True)
    print(f"[alg3] train OOF F={f_oof:.4f}  val {rv}  (base val F {base['F']})  "
          f"({time.time() - t0:.0f}s)", flush=True)
    print(f"[alg3] e2e OOF F={e_oof:.4f}  e2e val (simulated) F={e_val:.4f}  "
          f"unit OOF F={evaluate(scorer, papers, train, preds_tr)['F']:.4f}", flush=True)
    if a.classifier == "gb":
        meta = {"classifier": "gb", "params": GB.PARAMS, "train_oof_F": f_oof, "val": rv, "val_base": base}
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / "gb_eval.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        print(f"[alg3] gb: evaluation only, no extractor exported (tree export not written yet) -> {a.out}")
        return
    meta = {"C": a.C, "class_weight": a.class_weight, "stack": a.stack, "span_C": a.span_C,
            "vocab": a.vocab, "tau_rounds": a.tau_rounds, "seed": a.seed, "objective": a.objective,
            "e2e_oof_F": e_oof, "e2e_val_sim_F": e_val,
            "clues": a.clues, "n_clues": len(clues),
            "min_count": a.min_count, "folds": a.folds, "train_papers": train, "val_papers": val,
            "train_oof_F": f_oof, "val": rv, "val_base": base, "n_features": len(keep),
            "metric": "m1g, overall F (base parser + tagger), threshold 0.7"}
    export(Path(a.out), vec1, clf1, svec, sclf, tau, meta, stage2=stage2)
    if clues:
        (Path(a.out) / "alg3_clues.json").write_text(json.dumps(clues, indent=1), encoding="utf-8")
    print(f"[alg3] tau {tau}\n[alg3] extractor -> {a.out}  ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
