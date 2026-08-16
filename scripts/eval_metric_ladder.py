#!/usr/bin/env python3
"""A ladder of extraction metrics, each relaxing exactly ONE assumption.

The headline number today (M1) demands that an extraction match a gold node of
the SAME type, one-to-one, at containment >= 0.7. Three separate disagreements
are folded into that single score, and the audit showed they are not small:
misclassification, granularity (a span nested in a bigger gold node), and span
boundaries. Reporting one number cannot tell them apart.

Each rung relaxes one more constraint, so the GAP between consecutive rungs is
the cost of that one disagreement:

  M1 strict      same type, 1:1, containment >= t        <- what we report today
  M2 any-type    ...but type is ignored                  gap(M1->M2) = misclassification
  M3 nested-ok   ...but a span inside a gold node counts  gap(M2->M3) = granularity
                 and several spans may cover one gold
  M4 coverage    token-level, no node structure at all    appendix: content captured

M3 is the one to look at when asking "did we find the structure at all". Its
precision asks: is every span we emitted part of something real? Its recall
asks: is every gold node covered by what we emitted? Neither cares how the
content was divided into nodes, which is exactly the granularity argument.

Usage:
    python scripts/eval_metric_ladder.py --cache <buckets_cache.json>
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import distillation_analysis as da
from silver_distillation_sequential import FNAME_MAP
from silver_distillation_merged import load_gold_texts
from latex_clean import clean_latex_to_text

TYPES = list(FNAME_MAP.keys())


def tok(s):
    return da.tokenize_latex(clean_latex_to_text(s or "").lower())


def sym_contain(a, b):
    """Containment with min() denominator — the current matcher's similarity."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def greedy(ext_toks, gold_toks, th):
    """Greedy 1:1 matching, highest similarity first. Returns TP count."""
    pairs = []
    for i, e in enumerate(ext_toks):
        for j, g in enumerate(gold_toks):
            s = sym_contain(e, g)
            if s >= th:
                pairs.append((s, i, j))
    pairs.sort(reverse=True)
    me, mg = set(), set()
    for s, i, j in pairs:
        if i in me or j in mg:
            continue
        me.add(i); mg.add(j)
    return len(me)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--eval-dir", default="src/LLMVersion/merged_eval_silver_001_011_v3")
    ap.add_argument("--gold-dir", default=None)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--cover", type=float, default=0.7,
                    help="M3: fraction of a span that must be accounted for")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cache = json.load(open(args.cache, encoding="utf-8"))
    gold_dir = Path(args.gold_dir) if args.gold_dir else \
        (REPO / args.eval_dir).resolve() / "_split_eval" / "gold"
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in TYPES}
    meta = {r["paper_id"]: r for r in
            csv.DictReader(open(REPO / "corpus/silver/metadata.csv", encoding="utf-8"))
            if r["prompt_version"] == "v4.1"}

    METRICS = ["M1_strict", "M2_anytype", "M3_nested", "M4_coverage"]
    acc = defaultdict(lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0}))

    for pid, entry in cache.items():
        m = meta.get(pid)
        if not m:
            continue
        grp = "train" if m["split"] == "train" else f"test-{m['tier']}"
        gold_by_type = {t: [tok(g) for g in gold[t].get(pid, [])] for t in TYPES}
        gold_all = [g for t in TYPES for g in gold_by_type[t]]

        for tag in ("base", "final"):
            ext_by_type = {t: [tok(x) for x in entry[tag][t]] for t in TYPES}
            ext_all = [e for t in TYPES for e in ext_by_type[t]]

            # --- M1: per type, 1:1, threshold ---
            tp = sum(greedy(ext_by_type[t], gold_by_type[t], args.threshold)
                     for t in TYPES)
            a = acc[grp][("M1_strict", tag)]
            a["tp"] += tp; a["fp"] += len(ext_all) - tp; a["fn"] += len(gold_all) - tp

            # --- M2: type ignored, still 1:1 ---
            tp2 = greedy(ext_all, gold_all, args.threshold)
            a = acc[grp][("M2_anytype", tag)]
            a["tp"] += tp2; a["fp"] += len(ext_all) - tp2; a["fn"] += len(gold_all) - tp2

            # --- M3: nesting + decomposition allowed, type ignored ---
            # precision: is this span part of something real?
            supported = sum(
                1 for e in ext_all
                if e and any(len(e & g) / len(e) >= args.cover for g in gold_all))
            # recall: is this gold node accounted for by what we emitted?
            union_ext = set().union(*ext_all) if ext_all else set()
            covered = sum(1 for g in gold_all
                          if g and len(g & union_ext) / len(g) >= args.cover)
            a = acc[grp][("M3_nested", tag)]
            a["tp"] += supported
            a["fp"] += len(ext_all) - supported
            a["fn"] += len(gold_all) - covered
            # note: tp is used for precision, (tp+fn) side uses `covered`
            a.setdefault("cov", 0)
            a["cov"] += covered

            # --- M4: token coverage, no nodes at all ---
            union_gold = set().union(*gold_all) if gold_all else set()
            inter = len(union_ext & union_gold)
            a = acc[grp][("M4_coverage", tag)]
            a["tp"] += inter
            a["fp"] += len(union_ext) - inter
            a["fn"] += len(union_gold) - inter

    def score(d, name):
        if name in ("M3_nested",):
            # precision from supported spans, recall from covered gold
            tp, fp = d["tp"], d["fp"]
            cov, fn = d.get("cov", 0), d["fn"]
            p = tp / (tp + fp) if (tp + fp) else 0.0
            r = cov / (cov + fn) if (cov + fn) else 0.0
            return p, r, (2 * p * r / (p + r) if (p + r) else 0.0)
        return prf(d["tp"], d["fp"], d["fn"])

    labels = {"M1_strict": "M1 strict     (type + 1:1 + 0.7)",
              "M2_anytype": "M2 any-type   (ignore type)",
              "M3_nested": "M3 nested-ok  (+ granularity)",
              "M4_coverage": "M4 coverage   (tokens, no nodes)"}
    rows = []
    for grp in ["train", "test-B_math_shift", "test-A_matched_ML"]:
        if grp not in acc:
            continue
        print(f"\n{'='*74}\n{grp}\n{'='*74}")
        print(f"{'metric':<34} {'base F1':>8} {'final F1':>9} {'dF1':>7}   "
              f"{'base P/R':>13} {'final P/R':>13}")
        prev = None
        for name in METRICS:
            pb, rb, fb = score(acc[grp][(name, "base")], name)
            pf, rf, ff = score(acc[grp][(name, "final")], name)
            gap = f"  (+{fb-prev:.3f} vs prev)" if prev is not None else ""
            print(f"{labels[name]:<34} {fb:>8.3f} {ff:>9.3f} {ff-fb:>+7.3f}   "
                  f"{pb:>6.3f}/{rb:<6.3f} {pf:>6.3f}/{rf:<6.3f}{gap}")
            prev = fb
            rows.append({"group": grp, "metric": name,
                         "base_f1": round(fb, 4), "final_f1": round(ff, 4),
                         "delta": round(ff - fb, 4),
                         "base_p": round(pb, 4), "base_r": round(rb, 4),
                         "final_p": round(pf, 4), "final_r": round(rf, 4)})

    print(f"\n{'='*74}\nWhat each gap costs the STRICT score (base rules)\n{'='*74}")
    print(f"{'split':<22} {'misclassif.':>12} {'granularity':>12}")
    for grp in ["train", "test-B_math_shift", "test-A_matched_ML"]:
        if grp not in acc:
            continue
        f = {n: score(acc[grp][(n, "base")], n)[2] for n in METRICS}
        print(f"{grp:<22} {f['M2_anytype']-f['M1_strict']:>+12.3f} "
              f"{f['M3_nested']-f['M2_anytype']:>+12.3f}")

    out = Path(args.out) if args.out else \
        (REPO / args.eval_dir).resolve() / "metric_ladder.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
