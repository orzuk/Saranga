#!/usr/bin/env python3
"""Compare two extractions of the SAME paper(s) — e.g. opus-4.8/v4.1 vs opus-5/v5.

Answers "are the graphs similar, and if not, what changed?" by aligning the two
node sets with the project's existing Jaccard matcher (reused from
src/evaluate_extraction.py, so the matching semantics match the eval harness)
and reporting, per paper:

  * node/edge counts and per-type deltas
  * aligned nodes (with similarity), nodes only in A, nodes only in B
  * statement rewording on aligned nodes (sim < --exact-at)
  * type disagreements on aligned nodes
  * edge overlap / flips / only-in-A / only-in-B
  * v5-only field coverage (statement_short, origin, genus/differentia)

This is a symmetric *diff*, not a P/R/F1 scoring run — neither side is "gold".

Usage:
    python scripts/compare_extractions.py \
        --a corpus/silver/opus-4.8__v4.1 --b corpus/silver/opus-5__v5 \
        [--papers paper431,paper217] [--threshold 0.5] [--show 6] [--full]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
from evaluate_extraction import jaccard, node_text, match_nodes  # noqa: E402


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("nodes", d.get("objects", [])), d.get("edges", d.get("relations", [])), d.get("metadata", {})


def short(s, n=110):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def compare_one(pid, pa, pb, args):
    na, ea, ma = load(pa)
    nb, eb, mb = load(pb)

    print("\n" + "=" * 78)
    print("%s   A=%s (%s/%s)   B=%s (%s/%s)" % (
        pid, os.path.basename(os.path.dirname(pa)),
        ma.get("model", "?"), ma.get("prompt_version", "?"),
        os.path.basename(os.path.dirname(pb)),
        mb.get("model", "?"), mb.get("prompt_version", "?")))
    print("=" * 78)
    print("nodes: A=%d  B=%d  (%+d)     edges: A=%d  B=%d  (%+d)"
          % (len(na), len(nb), len(nb) - len(na), len(ea), len(eb), len(eb) - len(ea)))

    # ── per-type counts ──
    ta, tb = Counter(n.get("type") for n in na), Counter(n.get("type") for n in nb)
    types = sorted(set(ta) | set(tb))
    print("\nper-type   %-18s %5s %5s %6s" % ("type", "A", "B", "delta"))
    for t in types:
        d = tb[t] - ta[t]
        flag = "" if d == 0 else ("  <-- " + ("+%d" % d if d > 0 else str(d)))
        print("           %-18s %5d %5d %6s%s" % (t, ta[t], tb[t], ("%+d" % d), flag))

    # ── align nodes (B as "extracted", A as reference) ──
    matches, only_b, only_a, id_map = match_nodes(nb, na, args.threshold)
    print("\nalignment @jaccard>=%.2f : aligned=%d   only-in-A=%d   only-in-B=%d"
          % (args.threshold, len(matches), len(only_a), len(only_b)))
    if matches:
        sims = sorted(m[2] for m in matches)
        exact = sum(1 for m in matches if m[2] >= args.exact_at)
        print("  aligned similarity: median=%.2f  min=%.2f  near-identical(>=%.2f)=%d/%d"
              % (sims[len(sims) // 2], sims[0], args.exact_at, exact, len(matches)))

    # type disagreements
    tmis = [(m[0], m[1]) for m in matches if not m[3]]
    if tmis:
        print("\n  TYPE DISAGREEMENTS on aligned nodes (%d):" % len(tmis))
        for b, a in tmis[: args.show]:
            print("    A:%-14s -> B:%-14s | %s" % (a.get("type"), b.get("type"),
                                                   short(a.get("name") or node_text(a), 60)))

    # reworded statements
    rew = sorted([m for m in matches if m[2] < args.exact_at], key=lambda m: m[2])
    if rew:
        print("\n  REWORDED / PARTIAL matches (%d, lowest sim first):" % len(rew))
        for b, a, sim, _ in rew[: args.show]:
            print("    sim=%.2f  [%s] %s" % (sim, a.get("type"), short(a.get("name") or "", 60)))
            print("        A: %s" % short(node_text(a), args.width))
            print("        B: %s" % short(node_text(b), args.width))

    lim = None if args.full else args.show
    if only_a:
        print("\n  ONLY IN A (dropped by B) — %d:" % len(only_a))
        for n in only_a[:lim]:
            print("    [%-12s] %s" % (n.get("type"), short(n.get("name") or node_text(n), args.width)))
        if lim and len(only_a) > lim:
            print("    ... +%d more" % (len(only_a) - lim))
    if only_b:
        print("\n  ONLY IN B (new in B) — %d:" % len(only_b))
        for n in only_b[:lim]:
            print("    [%-12s] %s" % (n.get("type"), short(n.get("name") or node_text(n), args.width)))
        if lim and len(only_b) > lim:
            print("    ... +%d more" % (len(only_b) - lim))

    # ── edges: translate B's endpoints into A's id-space via the node alignment ──
    # (node ids differ between extractions, so name/id matching alone fails;
    #  id_map comes from match_nodes and maps B-node-id -> aligned A-node-id.)
    ka = {(e.get("source"), e.get("target"), e.get("type") or "uses") for e in ea}
    kb = set()
    unmappable = 0
    for e in eb:
        s, t = id_map.get(e.get("source")), id_map.get(e.get("target"))
        if s is None or t is None:
            unmappable += 1          # endpoint is a B-only node → cannot exist in A
            continue
        kb.add((s, t, e.get("type") or "uses"))
    both = ka & kb
    flips = {k for k in kb - ka if (k[1], k[0], k[2]) in ka}
    # only-A restricted to edges whose endpoints both aligned (else incomparable)
    aligned_a = set(id_map.values())
    ka_cmp = {k for k in ka if k[0] in aligned_a and k[1] in aligned_a}
    print("\nedges (compared in aligned node-space): shared=%d  only-A=%d  only-B=%d  "
          "direction-flips=%d" % (len(both), len(ka_cmp - kb), len(kb - ka), len(flips)))
    print("  (A edges comparable=%d/%d; B edges touching a B-only node=%d/%d — not comparable)"
          % (len(ka_cmp), len(ka), unmappable, len(eb)))
    et_a, et_b = Counter(e.get("type") for e in ea), Counter(e.get("type") for e in eb)
    print("  edge types A: %s" % dict(et_a))
    print("  edge types B: %s" % dict(et_b))
    noncanon = {t for t in et_b if t not in {
        "uses", "specializes", "generalizes", "proves", "solves",
        "illustrates", "tests", "resolves", "grounded_to"}}
    if noncanon:
        print("  !! NON-CANONICAL edge types in B: %s" % sorted(noncanon))

    # ── v5-only field coverage ──
    defs_b = [n for n in nb if n.get("type") == "definition"]
    print("\nB field coverage: statement_short=%d/%d  origin=%d/%d  "
          "definitions with genus=%d/%d  differentia=%d/%d"
          % (sum(1 for n in nb if n.get("statement_short")), len(nb),
             sum(1 for n in nb if n.get("origin")), len(nb),
             sum(1 for n in defs_b if n.get("genus")), len(defs_b),
             sum(1 for n in defs_b if n.get("differentia")), len(defs_b)))

    return {
        "paper": pid, "a_nodes": len(na), "b_nodes": len(nb),
        "a_edges": len(ea), "b_edges": len(eb),
        "aligned": len(matches), "only_a": len(only_a), "only_b": len(only_b),
        "type_mismatch": len(tmis),
        "edges_shared": len(both), "edge_flips": len(flips),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=os.path.join(REPO, "corpus/silver/opus-4.8__v4.1"))
    ap.add_argument("--b", default=os.path.join(REPO, "corpus/silver/opus-5__v5"))
    ap.add_argument("--papers", default=None, help="comma list; default = all in --b")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--exact-at", type=float, default=0.95)
    ap.add_argument("--show", type=int, default=6)
    ap.add_argument("--width", type=int, default=110)
    ap.add_argument("--full", action="store_true", help="list every only-in-A/B node")
    args = ap.parse_args()

    if args.papers:
        pids = [p.strip() for p in args.papers.split(",") if p.strip()]
    else:
        pids = sorted(f[:-5] for f in os.listdir(args.b) if f.endswith(".json"))

    rows = []
    for pid in pids:
        pa, pb = os.path.join(args.a, pid + ".json"), os.path.join(args.b, pid + ".json")
        if not (os.path.isfile(pa) and os.path.isfile(pb)):
            print("skip %s (missing in A or B)" % pid)
            continue
        rows.append(compare_one(pid, pa, pb, args))

    if rows:
        print("\n" + "=" * 78)
        print("SUMMARY")
        print("=" * 78)
        print("%-10s %11s %11s %8s %8s %8s %7s %8s" % (
            "paper", "nodes A/B", "edges A/B", "aligned", "onlyA", "onlyB", "typemis", "edgeshr"))
        for r in rows:
            print("%-10s %5d/%-5d %5d/%-5d %8d %8d %8d %7d %8d" % (
                r["paper"], r["a_nodes"], r["b_nodes"], r["a_edges"], r["b_edges"],
                r["aligned"], r["only_a"], r["only_b"], r["type_mismatch"], r["edges_shared"]))
        tot = lambda k: sum(r[k] for r in rows)  # noqa: E731
        print("%-10s %5d/%-5d %5d/%-5d %8d %8d %8d %7d %8d" % (
            "TOTAL", tot("a_nodes"), tot("b_nodes"), tot("a_edges"), tot("b_edges"),
            tot("aligned"), tot("only_a"), tot("only_b"),
            tot("type_mismatch"), tot("edges_shared")))
        if tot("a_nodes"):
            print("\nnode recall of A by B: %.1f%%   node growth B vs A: %+.1f%%" % (
                100.0 * tot("aligned") / tot("a_nodes"),
                100.0 * (tot("b_nodes") - tot("a_nodes")) / tot("a_nodes")))


if __name__ == "__main__":
    main()
