#!/usr/bin/env python3
"""Structural metrics over a Saranga paper graph, for the AI-vs-human comparison.

Every metric here is computed from the unified JSON alone — no re-reading the
paper, no LLM. Grouped by what they are supposed to capture, and each is stated
with the confound it has to survive.

THE CENTRAL PROBLEM is that almost every graph quantity grows with paper size,
and the AI-attributed papers are much shorter than typical (median 8 pages
against 20-40 for math.AG). A metric that correlates ~1.0 with node count is not
measuring "how AI proves things", it is measuring "AI papers are shorter" — which
the arXiv metadata already says and which needs no graph.

So this module reports SIZE separately, and `--check` measures each metric's
correlation with size so a metric can be disqualified before it is used.

Usage:
    python3 discovery_suite/ai_math/graph_metrics.py corpus/silver/opus-5__v5.1
    python3 discovery_suite/ai_math/graph_metrics.py <dir> --check
    python3 discovery_suite/ai_math/graph_metrics.py <dir> --csv out.csv
"""
import argparse
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim",
                "conjecture"}
LEVEL2 = {"proof_step", "algorithm_step"}
DEPENDENCY = {"uses", "generalizes", "specializes"}


def _load(path):
    d = json.load(open(path, encoding="utf-8"))
    nodes = [n for n in (d.get("nodes") or []) if n.get("type") not in LEVEL2]
    ids = {n["id"] for n in nodes}
    edges = [e for e in (d.get("edges") or [])
             if e.get("source") in ids and e.get("target") in ids
             and e.get("source") != e.get("target")]
    return d.get("metadata") or {}, nodes, edges


def _depths(nodes, edges):
    """Longest-path depth per node: one more than its deepest support."""
    preds = defaultdict(list)
    for e in edges:
        if str(e.get("type") or "uses") in DEPENDENCY:
            preds[e["target"]].append(e["source"])
    memo, stack_guard = {}, set()

    def d(i):
        if i in memo:
            return memo[i]
        if i in stack_guard:            # cycle: treat as a root
            return 0
        stack_guard.add(i)
        v = max((d(p) + 1 for p in preds.get(i, ())), default=0)
        stack_guard.discard(i)
        memo[i] = v
        return v

    for n in nodes:
        d(n["id"])
    return memo


_SEC = re.compile(r"^\s*(\d+(?:\.\d+)*)")


def _section_num(s):
    """Leading section number as a float: '3.4 Noise-Contrastive' -> 3.4."""
    m = _SEC.match(str(s or ""))
    if not m:
        return None
    parts = m.group(1).split(".")
    try:
        return int(parts[0]) + (int(parts[1]) / 100.0 if len(parts) > 1 else 0.0)
    except ValueError:
        return None


def metrics(path):
    meta, nodes, edges = _load(path)
    n = len(nodes)
    if n < 5:
        return None
    ty = {x["id"]: x.get("type") for x in nodes}
    outd, ind = defaultdict(int), defaultdict(int)
    for e in edges:
        outd[e["source"]] += 1
        ind[e["target"]] += 1
    dep = _depths(nodes, edges)
    thm = [x["id"] for x in nodes if x.get("type") in THEOREM_LIKE]
    # "Headline" results: theorem-like with nothing depending on them.
    heads = [i for i in thm if outd[i] == 0]
    per_level = defaultdict(int)
    for i, v in dep.items():
        per_level[v] += 1
    longest = max(dep.values()) if dep else 0
    width = max(per_level.values()) if per_level else 0

    m = {"paper": os.path.basename(path)[:-5]}

    # ── SIZE (controls, not findings) ──────────────────────────────────
    m["n_nodes"] = n
    m["n_edges"] = len(edges)
    m["density"] = len(edges) / n

    # ── DEPTH ─────────────────────────────────────────────────────────
    # Raw longest path scales with size; depth_norm divides it out, and
    # depth_of_main asks the question that actually matters — how much
    # scaffolding stands under the paper's own headline results.
    m["depth_longest"] = longest
    m["depth_norm"] = longest / math.log(n + 1)
    m["depth_of_main"] = (sum(dep.get(i, 0) for i in heads) / len(heads)) if heads else 0
    m["depth_mean_thm"] = (sum(dep.get(i, 0) for i in thm) / len(thm)) if thm else 0

    # ── BREADTH / SHAPE ───────────────────────────────────────────────
    # aspect is the size-free one: a wide flat graph and a narrow deep graph
    # differ in aspect even at identical node counts.
    m["width_max"] = width
    m["aspect"] = width / max(1, longest)          # r=0.66 with size — not size-free
    # Shape at fixed size. A DAG of n nodes laid out as a balanced tree has
    # width ~ sqrt(n) and depth ~ sqrt(n), so dividing each by sqrt(n) gives a
    # ratio that does not inherit n. (An earlier attempt here multiplied and
    # divided by sqrt(n) in the same expression, which cancels to `aspect`
    # exactly and measured identically — a formula that looked normalised and
    # was not.)
    # Measured: depth/sqrt(n) comes out r=-0.14 with size, but width/sqrt(n) is
    # still 0.68 — these graphs widen FASTER than sqrt(n) while deepening slower.
    # So depth normalises cleanly and width does not, and width-based metrics
    # need size as a covariate rather than a divisor.
    m["width_norm"] = width / math.sqrt(n)         # r=0.68 — still size-linked
    m["depth_sqrt_norm"] = longest / math.sqrt(n)  # r=-0.14 — clean
    m["branch_in_thm"] = (sum(ind[i] for i in thm) / len(thm)) if thm else 0

    # ── REACH: how far a result travels before it is used ─────────────
    # Distance in SECTIONS between where something is stated and where it is
    # used. A lemma proved in §2 and used in §7 is doing different work from
    # one used three lines later. Needs `section`, which 100% of nodes carry.
    spans = []
    sec = {x["id"]: _section_num(x.get("section")) for x in nodes}
    for e in edges:
        a, b = sec.get(e["source"]), sec.get(e["target"])
        if a is not None and b is not None:
            spans.append(abs(b - a))
    m["reach_mean"] = (sum(spans) / len(spans)) if spans else 0
    m["reach_max"] = max(spans) if spans else 0
    m["reach_frac_far"] = (sum(1 for s in spans if s >= 1.0) / len(spans)) if spans else 0

    # ── REUSE: is a result load-bearing or used once? ─────────────────
    reused = [i for i in dep if outd[i] >= 2]
    m["frac_reused"] = len(reused) / n
    m["max_out"] = max(outd.values()) if outd else 0

    # ── EXTERNAL RELIANCE: standing on prior work vs self-contained ───
    ext = [x["id"] for x in nodes if x.get("origin") == "external"]
    m["frac_external"] = len(ext) / n
    m["frac_edges_from_ext"] = (sum(1 for e in edges if e["source"] in set(ext))
                                / len(edges)) if edges else 0

    # ── COMPOSITION ───────────────────────────────────────────────────
    m["frac_definition"] = sum(1 for x in nodes if x.get("type") == "definition") / n
    m["frac_thm_like"] = len(thm) / n
    n_lem = sum(1 for x in nodes if x.get("type") == "lemma")
    n_top = sum(1 for x in nodes if x.get("type") in ("theorem", "proposition"))
    m["lemma_per_theorem"] = n_lem / max(1, n_top)
    m["n_headline"] = len(heads)
    return m


# `aspect` was claimed size-free here and measured r=0.66 against node count on
# the 200-paper corpus — the --check flag caught it. Demoted: width_max grows with
# size faster than depth does, so their ratio inherits it. Use it only with size
# as a covariate, or replace it with a width normalised by sqrt(n).
SIZE_FREE_CLAIM = ("depth_norm", "depth_sqrt_norm",
                   "reach_mean", "reach_frac_far",
                   "frac_reused", "frac_external", "frac_edges_from_ext",
                   "frac_definition", "frac_thm_like", "lemma_per_theorem",
                   "density", "branch_in_thm", "depth_of_main")


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--check", action="store_true",
                    help="report each metric's correlation with paper size")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    rows = []
    for p in sorted(glob.glob(os.path.join(a.directory, "*.json"))):
        try:
            m = metrics(p)
        except Exception as e:
            print("  skip %s (%s)" % (os.path.basename(p), str(e)[:50]), file=sys.stderr)
            continue
        if m:
            rows.append(m)
    if not rows:
        print("no papers")
        return 1
    keys = [k for k in rows[0] if k != "paper"]

    print("papers: %d\n" % len(rows))
    print("  %-22s %9s %9s %9s" % ("metric", "median", "p10", "p90"))
    for k in keys:
        v = sorted(r[k] for r in rows)
        print("  %-22s %9.3f %9.3f %9.3f"
              % (k, v[len(v) // 2], v[int(len(v) * .1)], v[int(len(v) * .9)]))

    if a.check:
        size = [r["n_nodes"] for r in rows]
        print("\n  correlation with n_nodes — a metric near |1| is SIZE in disguise")
        print("  %-22s %8s  %s" % ("metric", "r", "verdict"))
        for k in keys:
            if k == "n_nodes":
                continue
            r = _pearson(size, [x[k] for x in rows])
            tag = ("SIZE PROXY — do not use" if abs(r) > 0.80 else
                   "size-linked, needs control" if abs(r) > 0.50 else
                   "usable")
            star = " *" if k in SIZE_FREE_CLAIM and abs(r) > 0.50 else ""
            print("  %-22s %8.2f  %s%s" % (k, r, tag, star))
        print("\n  * = claimed size-free in the source but is not; fix or drop.")

    if a.csv:
        import csv as _csv
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=["paper"] + keys)
            w.writeheader()
            w.writerows(rows)
        print("\nwrote %s" % a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
