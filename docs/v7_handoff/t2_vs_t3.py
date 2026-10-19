#!/usr/bin/env python3
"""T2 (LLM silver) against T3 (rule-based) on the same papers, and the T2 per-paper panel figure.

    python3 docs/v7_handoff/t2_vs_t3.py corpus/silver/opus-5.5__v7 corpus/silver/opus-5.5__v7/rules_units \\
        [--fig ../Papers/Saranga/figures/100k_t2_panels] [--out docs/v7_handoff/t2_vs_t3_v7.json]

Per paper, with no node alignment: Level-1 node counts per type (mean in each tier, Pearson r across
papers), the conclusion rate of theorem-like results (non-empty `conclusions`), and whether the graph
is acyclic (excluded, as in the finishing step's cycle check: `mention` edges, `alternative`
proves edges, and a result's edge into its own proof). For T2 alone: DAG depth (longest path
over Level-1 nodes, mention edges excluded) against nodes per paper, and proofs per paper against
mean steps per decomposed proof, drawn as the paper's two-panel figure.
"""
import argparse
import json
from pathlib import Path

import networkx as nx
import numpy as np

TYPES = ["theorem", "lemma", "proposition", "corollary", "claim", "definition", "proof"]
THM = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture"}
STEPS = {"proof_step", "algorithm_step"}


def graph(g, level1_only=False):
    keep = {n["id"] for n in g["nodes"] if not (level1_only and n["type"] in STEPS)}
    G = nx.DiGraph()
    G.add_nodes_from(keep)
    own = {(e["target"], e["source"]) for e in g["edges"] if e.get("type") == "proves"}   # a proof citing its own result
    G.add_edges_from((e["source"], e["target"]) for e in g["edges"]
                     if not e.get("mention") and not e.get("alternative") and (e["source"], e["target"]) not in own
                     and e["source"] in keep and e["target"] in keep)
    return G


def stats(g):
    l1 = [n for n in g["nodes"] if n["type"] not in STEPS]
    thm = [n for n in l1 if n["type"] in THM]
    proofs = {n["id"] for n in l1 if n["type"] == "proof"}
    steps = [n for n in g["nodes"] if n["type"] == "proof_step" and n.get("parent_id") in proofs]
    decomposed = {n["parent_id"] for n in steps}
    G1 = graph(g, level1_only=True)
    return {**{t: sum(n["type"] == t for n in l1) for t in TYPES},
            "thm": len(thm), "concl": sum(bool(n.get("conclusions")) for n in thm),
            "acyclic": nx.is_directed_acyclic_graph(graph(g)),
            "nodes": len(g["nodes"]), "proofs": len(proofs), "steps_per_proof": len(steps) / len(decomposed) if decomposed else 0,
            "depth": nx.dag_longest_path_length(G1) if nx.is_directed_acyclic_graph(G1) else None}


def figure(rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    color = "#8B5CF6"
    x = np.array([r["nodes"] for r in rows if r["depth"] is not None])
    y = np.array([r["depth"] for r in rows if r["depth"] is not None])
    p = np.array([r["proofs"] for r in rows if r["steps_per_proof"]])
    s = np.array([r["steps_per_proof"] for r in rows if r["steps_per_proof"]])
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 3.2))
    for ax, u, v, xl, yl, title, loc in ((a, x, y, "Nodes per paper", "DAG depth (Level-1 nodes)",
                                          "(a) Graph size vs. reasoning depth", 0.03),
                                         (b, p, s, "Proofs per paper", "Avg. steps per decomposed proof",
                                          "(b) Proof count vs. proof granularity", 0.97)):
        ax.scatter(u, v, c=color, s=18, alpha=0.55, edgecolors="white", linewidth=0.3, zorder=3)
        z = np.polyfit(u, v, 1)
        xs = np.linspace(u.min(), u.max(), 100)
        ax.plot(xs, np.polyval(z, xs), "--", color="#999999", linewidth=0.7, zorder=1)
        ha = "left" if loc < 0.5 else "right"
        ax.text(loc, 0.95, f"r = {np.corrcoef(u, v)[0, 1]:.2f}", transform=ax.transAxes, fontsize=7, color="#666666", va="top", ha=ha)
        ax.text(loc, 0.87, f"n = {len(u)} papers", transform=ax.transAxes, fontsize=6.5, color="#888888", va="top", ha=ha)
        ax.set_xlabel(xl, fontsize=8)
        ax.set_ylabel(yl, fontsize=8)
        ax.set_title(title, fontsize=9, pad=6)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(f"T2 corpus: {len(rows)} LLM-extracted papers (Claude Opus 5.5, prompt v7)", fontsize=9.5, y=1.02)
    fig.tight_layout(w_pad=2.5)
    for ext in ("pdf", "png"):
        fig.savefig(f"{path}.{ext}", bbox_inches="tight")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("t2")
    ap.add_argument("t3")
    ap.add_argument("--fig")
    ap.add_argument("--out")
    a = ap.parse_args()
    ids = sorted(p.stem for p in Path(a.t2).glob("*.json") if (Path(a.t3) / p.name).is_file())
    t2 = [stats(json.loads((Path(a.t2) / f"{i}.json").read_text())) for i in ids]
    t3 = [stats(json.loads((Path(a.t3) / f"{i}.json").read_text())) for i in ids]
    res = {"papers": len(ids), "types": {}}
    for t in TYPES:
        u, v = np.array([r[t] for r in t2]), np.array([r[t] for r in t3])
        res["types"][t] = {"t2_mean": round(u.mean(), 1), "t3_mean": round(v.mean(), 1),
                           "r": round(float(np.corrcoef(u, v)[0, 1]), 2)}
    res["conclusion_rate"] = {k: round(sum(r["concl"] for r in x) / sum(r["thm"] for r in x), 3)
                              for k, x in (("t2", t2), ("t3", t3))}
    res["acyclic"] = {"both": sum(p["acyclic"] and q["acyclic"] for p, q in zip(t2, t3)),
                      "t3_only": sum(q["acyclic"] and not p["acyclic"] for p, q in zip(t2, t3)),
                      "t2_only": sum(p["acyclic"] and not q["acyclic"] for p, q in zip(t2, t3)),
                      "neither": sum(not p["acyclic"] and not q["acyclic"] for p, q in zip(t2, t3))}
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    if a.fig:
        figure(t2, a.fig)
        print("wrote", a.fig + ".pdf")


if __name__ == "__main__":
    main()
