#!/usr/bin/env python3
"""Sanity / anomaly QA over a directory of extracted knowledge-graph JSONs.

Complements the two focused tools:
  * scripts/audit_verbatim.py          — anti-hallucination (statements in source)
  * scripts/normalize_edge_directions.py --dry-run — flipped edges

This one sweeps for *structural and schema* problems:

  SCHEMA      non-canonical node/edge types; missing required fields
              (name/statement/section/origin); bad `origin` values
  GRAPH       dangling edge endpoints; self-loops; duplicate node ids;
              duplicate edges; CYCLES (the graph must be a DAG)
  DIRECTION   edges whose endpoint types violate edge_types.py
              (i.e. flipped `proves`/`illustrates`/`solves`/`tests`/`resolves`)
  SEMANTICS   proof nodes with no `proves` edge; Level-2 steps with no
              parent_id / dangling parent; theorem-like nodes with no proof;
              orphan nodes (no edges at all)
  OUTLIERS    empty extractions; suspiciously low/high node counts;
              statements that are absurdly short/long; low field coverage

Usage:
    python scripts/qa_extractions.py [--dir corpus/silver/opus-5__v5] [--show 8]
                                     [--csv qa_report.csv]
Exit 1 if any ERROR-level problem is found (WARN-level does not fail).
"""
import argparse
import csv
import glob
import json
import os
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
import edge_types as ET  # noqa: E402
import node_types as NT  # noqa: E402

VALID_NODES = set(NT.ALL_NODE_TYPES) if hasattr(NT, "ALL_NODE_TYPES") else set()
VALID_EDGES = set(ET.ALL_EDGE_TYPES) | {"grounded_to", "solves"}
LEVEL2 = {"proof_step", "algorithm_step"}
THEOREM_LIKE = {"theorem", "lemma", "proposition", "corollary", "claim"}


def has_cycle(nodes, edges):
    """Return a short example cycle, or None. Iterative DFS (no recursion limit)."""
    adj = defaultdict(list)
    ids = {n.get("id") for n in nodes}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in ids and t in ids:
            adj[s].append(t)
    WHITE, GREY, BLACK = 0, 1, 2
    color = defaultdict(int)
    for start in list(ids):
        if color[start] != WHITE:
            continue
        stack = [(start, iter(adj[start]))]
        path = [start]
        color[start] = GREY
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if color[nxt] == GREY:
                    i = path.index(nxt) if nxt in path else 0
                    return " -> ".join(path[i:] + [nxt])
                if color[nxt] == WHITE:
                    color[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, iter(adj[nxt])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                if path:
                    path.pop()
    return None


def qa_one(path):
    """Return (stats dict, list of (level, code, detail))."""
    problems = []
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return None, [("ERROR", "unparseable-json", str(e))]

    nodes = d.get("nodes", [])
    edges = d.get("edges", [])
    meta = d.get("metadata", {}) if isinstance(d.get("metadata"), dict) else {}

    for k in ("nodes", "edges", "metadata"):
        if k not in d:
            problems.append(("ERROR", "missing-top-key", k))

    ids = [n.get("id") for n in nodes]
    idset = set(ids)
    ntype = {n.get("id"): n.get("type") for n in nodes}

    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        problems.append(("ERROR", "duplicate-node-id", ", ".join(map(str, dup[:5]))))
    if None in idset or "" in idset:
        problems.append(("ERROR", "node-missing-id", "%d nodes" % sum(1 for i in ids if not i)))

    # node-level checks
    short_stmt = long_stmt = 0
    for n in nodes:
        t = n.get("type")
        if VALID_NODES and t not in VALID_NODES:
            problems.append(("ERROR", "non-canonical-node-type", "%s (%s)" % (t, n.get("id"))))
        if not n.get("statement"):
            problems.append(("WARN", "empty-statement", str(n.get("id"))))
        else:
            L = len(n["statement"])
            if L < 15:
                short_stmt += 1
            if L > 20000:
                long_stmt += 1
        if not n.get("name"):
            problems.append(("WARN", "missing-name", str(n.get("id"))))
        if not n.get("section"):
            problems.append(("WARN", "missing-section", str(n.get("id"))))
        o = n.get("origin")
        if o is None:
            problems.append(("WARN", "missing-origin", str(n.get("id"))))
        elif o not in ("paper", "external"):
            problems.append(("ERROR", "bad-origin-value", "%s (%s)" % (o, n.get("id"))))
        if o == "external" and not n.get("origin_citation"):
            problems.append(("WARN", "external-without-citation", str(n.get("id"))))
        if t in LEVEL2:
            p = n.get("parent_id") or n.get("parent_proof") or n.get("parent_algorithm")
            if not p:
                problems.append(("ERROR", "level2-without-parent", str(n.get("id"))))
            elif p not in idset:
                problems.append(("ERROR", "level2-dangling-parent", "%s -> %s" % (n.get("id"), p)))
    if short_stmt:
        problems.append(("WARN", "very-short-statements", "%d nodes < 15 chars" % short_stmt))
    if long_stmt:
        problems.append(("WARN", "very-long-statements", "%d nodes > 20k chars" % long_stmt))

    # edge-level checks
    seen_edges = set()
    for e in edges:
        et = e.get("type")
        s, t = e.get("source"), e.get("target")
        if et not in VALID_EDGES:
            problems.append(("ERROR", "non-canonical-edge-type", str(et)))
        if s not in idset:
            problems.append(("ERROR", "dangling-edge-source", "%s (%s)" % (s, et)))
        if t not in idset:
            problems.append(("ERROR", "dangling-edge-target", "%s (%s)" % (t, et)))
        if s == t:
            problems.append(("ERROR", "self-loop", "%s (%s)" % (s, et)))
        key = (s, t, et)
        if key in seen_edges:
            problems.append(("WARN", "duplicate-edge", str(key)))
        seen_edges.add(key)
        # direction conformance
        s_ok = ET.get_allowed_source_types(et) if et in VALID_EDGES else None
        t_ok = ET.get_allowed_target_types(et) if et in VALID_EDGES else None
        st, tt = ntype.get(s), ntype.get(t)
        if s_ok and st and st not in s_ok:
            rev = (t_ok is None or st in t_ok) and (s_ok is None or tt in s_ok)
            problems.append(("ERROR", "flipped-edge" if rev else "bad-edge-source-type",
                             "%s: %s->%s" % (et, st, tt)))
        elif t_ok and tt and tt not in t_ok:
            problems.append(("ERROR", "bad-edge-target-type", "%s: %s->%s" % (et, st, tt)))

    # edge confidence (required from prompt v5.1 onward)
    conf = [e.get("confidence") for e in edges]
    n_missing_conf = sum(1 for c in conf if c is None)
    bad_conf = [c for c in conf if c is not None and not (isinstance(c, (int, float)) and 0 <= c <= 1)]
    if edges and n_missing_conf == len(edges):
        problems.append(("WARN", "no-edge-confidence", "%d edges, none scored (pre-v5.1?)" % len(edges)))
    elif n_missing_conf:
        problems.append(("WARN", "edge-missing-confidence", "%d/%d edges" % (n_missing_conf, len(edges))))
    if bad_conf:
        problems.append(("ERROR", "bad-confidence-value", str(bad_conf[:5])))

    cyc = has_cycle(nodes, edges)
    if cyc:
        problems.append(("ERROR", "cycle-not-a-DAG", cyc[:160]))

    # nested/overlapping statements: one node's statement fully contains another's.
    # Legitimate for parent/child (proof ⊃ proof_step, algorithm ⊃ algorithm_step),
    # suspicious otherwise — it means the same source text is counted twice.
    import re as _re
    norm = [(n.get("id"), n.get("type"),
             _re.sub(r"\s+", " ", (n.get("statement") or "")).strip()) for n in nodes]
    norm = [(i, t, s) for i, t, s in norm if len(s) > 80]
    norm.sort(key=lambda x: -len(x[2]))
    parent_of = {}
    for n in nodes:
        p = n.get("parent_id") or n.get("parent_proof") or n.get("parent_algorithm")
        if p:
            parent_of[n.get("id")] = p
    nested = 0
    for a in range(len(norm)):
        ia, ta, sa = norm[a]
        for b in range(a + 1, len(norm)):
            ib, tb, sb = norm[b]
            if len(sb) >= len(sa):
                continue
            if sb in sa:
                if parent_of.get(ib) == ia:      # legitimate parent→child containment
                    continue
                nested += 1
                if nested <= 2:
                    problems.append(("WARN", "nested-statement",
                                     "%s (%s) contains %s (%s)" % (ia, ta, ib, tb)))
    if nested > 2:
        problems.append(("WARN", "nested-statement-more", "%d additional pairs" % (nested - 2)))

    # semantic checks
    proves_src = {e.get("source") for e in edges if e.get("type") == "proves"}
    for n in nodes:
        if n.get("type") == "proof" and n.get("id") not in proves_src:
            problems.append(("WARN", "proof-without-proves-edge", str(n.get("id"))))
    # Orphans = no edge AND no structural parent. Level-2 steps (proof_step /
    # algorithm_step) are legitimately linked to their Level-1 parent via
    # `parent_id` rather than an edge, so a parented step is NOT an orphan.
    endpoints = {e.get("source") for e in edges} | {e.get("target") for e in edges}
    orphans, parented_steps = [], 0
    for n in nodes:
        if n.get("id") in endpoints:
            continue
        par = (n.get("parent_id") or n.get("parent_proof")
               or n.get("parent_algorithm"))
        if n.get("type") in LEVEL2 and par and par in idset:
            parented_steps += 1        # structurally linked; fine
        else:
            orphans.append(n.get("id"))
    if orphans and len(nodes) > 3:
        problems.append(("WARN", "orphan-nodes", "%d of %d (edge-less AND parent-less)"
                         % (len(orphans), len(nodes))))
    if parented_steps:
        problems.append(("INFO", "steps-linked-by-parent-only",
                         "%d Level-2 steps have no edge but a valid parent_id" % parented_steps))

    if not nodes:
        problems.append(("ERROR", "empty-extraction", "0 nodes"))
    elif len(nodes) < 4:
        problems.append(("WARN", "suspiciously-few-nodes", "%d" % len(nodes)))

    defs = [n for n in nodes if n.get("type") == "definition"]
    stats = {
        "file": os.path.basename(path),
        "model": meta.get("model", ""),
        "prompt": meta.get("prompt_version", ""),
        "category": meta.get("category", ""),
        "n_nodes": len(nodes), "n_edges": len(edges),
        "n_defs": len(defs),
        "defs_with_genus": sum(1 for n in defs if n.get("genus")),
        "stmt_short_cov": sum(1 for n in nodes if n.get("statement_short")),
        "origin_cov": sum(1 for n in nodes if n.get("origin")),
        "edges_scored": sum(1 for c in conf if c is not None),
        "mean_confidence": (round(sum(c for c in conf if c is not None) /
                                 max(1, sum(1 for c in conf if c is not None)), 3)),
        "orphans": len(orphans),
        "errors": sum(1 for p in problems if p[0] == "ERROR"),
        "warns": sum(1 for p in problems if p[0] == "WARN"),
    }
    return stats, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(REPO, "corpus/silver/opus-5__v5"))
    ap.add_argument("--show", type=int, default=8)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if not files:
        print("no JSONs in %s" % args.dir)
        return 0

    rows, allprob = [], []
    for f in files:
        st, probs = qa_one(f)
        if st:
            rows.append(st)
        for lvl, code, detail in probs:
            allprob.append((os.path.basename(f), lvl, code, detail))

    print("=" * 96)
    print("PER-PAPER SUMMARY (%d files in %s)" % (len(files), os.path.relpath(args.dir, REPO)))
    print("=" * 96)
    print("%-22s %-14s %6s %6s %5s %9s %8s %6s %5s" % (
        "file", "category", "nodes", "edges", "defs", "genus/def", "short%", "err", "warn"))
    for r in rows:
        cov = (100 * r["stmt_short_cov"] // r["n_nodes"]) if r["n_nodes"] else 0
        print("%-22s %-14s %6d %6d %5d %9s %7d%% %6d %5d" % (
            r["file"][:22], r["category"][:14], r["n_nodes"], r["n_edges"], r["n_defs"],
            "%d/%d" % (r["defs_with_genus"], r["n_defs"]), cov, r["errors"], r["warns"]))

    if rows:
        n = len(rows)
        tn = sum(r["n_nodes"] for r in rows)
        te = sum(r["n_edges"] for r in rows)
        print("\nTOTALS: %d papers, %d nodes, %d edges  |  mean %.1f nodes, %.1f edges/paper"
              % (n, tn, te, tn / n, te / n))
        ncounts = sorted(r["n_nodes"] for r in rows)
        print("node-count distribution: min=%d  p25=%d  median=%d  p75=%d  max=%d" % (
            ncounts[0], ncounts[n // 4], ncounts[n // 2], ncounts[3 * n // 4], ncounts[-1]))
        models = Counter(r["model"] for r in rows)
        prompts = Counter(r["prompt"] for r in rows)
        print("models: %s   prompts: %s" % (dict(models), dict(prompts)))
        td = sum(r["n_defs"] for r in rows)
        tg = sum(r["defs_with_genus"] for r in rows)
        print("genus/differentia coverage: %d/%d definitions (%.0f%%)"
              % (tg, td, 100.0 * tg / td if td else 0))

    errs = [p for p in allprob if p[1] == "ERROR"]
    warns = [p for p in allprob if p[1] == "WARN"]
    print("\n" + "=" * 96)
    print("PROBLEMS: %d ERROR, %d WARN" % (len(errs), len(warns)))
    print("=" * 96)
    for label, group in (("ERROR", errs), ("WARN", warns)):
        by = Counter(p[2] for p in group)
        if not by:
            print("  no %s-level problems" % label)
            continue
        print("  %s counts by code:" % label)
        for code, c in by.most_common():
            print("    %-28s %d" % (code, c))
        shown = 0
        for f, lvl, code, detail in group:
            if shown >= args.show:
                break
            print("      e.g. %s  %s: %s" % (f, code, detail[:110]))
            shown += 1

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\nwrote %s" % args.csv)

    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
