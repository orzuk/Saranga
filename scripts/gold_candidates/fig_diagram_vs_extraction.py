#!/usr/bin/env python3
"""Figure for the paper: an author's dependency diagram next to the dependencies two extractors find
among the same results (Sec. 5). Panel (a) is the diagram as printed; (b) and (c) redraw its results in
the same places, with each drawn arrow green when the extractor has it (directly or through a path),
red dashed when it misses it, and the extractor's other dependencies between these results orange.

    fig_diagram_vs_extraction.py --out <png>      (default: 2510.25963, its Fig. 3)
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch    # noqa: E402
from PIL import Image                                             # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
import graph_score as GS                                          # noqa: E402

PAPER = "2510.25963"
CROP = (60, 120, 680, 320)                     # Fig. 3 on the page image (left, top, right, bottom)
# the diagram's results, where the drawing puts them (x, y), and their printed names
BOXES = {"G1": (0.5, 0.88, "Thm 4.1"), "G2": (0.33, 0.55, "Lem 5.2"), "G3": (0.78, 0.55, "Lem 6.15"),
         "G4": (0.13, 0.2, "Lem 5.3"), "G5": (0.47, 0.2, "Lem 5.5"), "G6": (0.8, 0.2, "Lem 5.4")}
DRAWN = {("G2", "G1"), ("G3", "G1"), ("G4", "G2"), ("G5", "G2"), ("G6", "G2")}     # the arrows of Fig. 3


def found(pred: dict, gold: dict):
    """(drawn arrows found, other dependencies) of an extraction among the boxes of BOXES."""
    gn = [n for n in GS._with_labels(gold) if n["id"] in BOXES]
    pn = GS._with_labels(pred)
    p2g = {pn[i]["id"]: gn[j]["id"] for i, (j, _) in GS.match_nodes(pn, gn, "m1g", "label").items()}
    res = {n["id"] for n in pn if n.get("type") not in GS._NOT_RESULTS}
    dep = {(p2g[a], p2g[b]) for a, b in GS.dependencies(pn, pred["edges"], res)
           if a in p2g and b in p2g and p2g[a] != p2g[b]}
    gold_all = {(e["source"], e["target"]) for e in gold["edges"]}
    return DRAWN & GS._implied(dep), dep - GS._implied(gold_all)


def panel(ax, title, hit, extra):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    ax.axis("off")
    ax.set_title(title, fontsize=10)
    for g, (x, y, name) in BOXES.items():
        ax.add_patch(FancyBboxPatch((x - 0.09, y - 0.055), 0.18, 0.11, boxstyle="round,pad=0.01",
                                    fc="white", ec="black", lw=0.9))
        ax.text(x, y, name, ha="center", va="center", fontsize=8.5)

    def arrow(a, b, color, style):
        (x1, y1, _), (x2, y2, _) = BOXES[a], BOXES[b]
        if abs(y1 - y2) < 0.01:                  # same row: arc above the boxes, top to top
            start, end, rad = (x1, y1 + 0.055), (x2, y2 + 0.055), (-0.45 if x2 > x1 else 0.45)
        else:
            dy = 0.055 if y2 > y1 else -0.055
            start, end, rad = (x1, y1 + dy), (x2, y2 - dy), 0.08
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=10, color=color, lw=1.4,
                                     linestyle=style, connectionstyle=f"arc3,rad={rad}"))
    for a, b in sorted(DRAWN):
        arrow(a, b, "#1a9850" if (a, b) in hit else "#d73027", "-" if (a, b) in hit else "--")
    for a, b in sorted(extra):
        arrow(a, b, "#f28e2b", "-")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = REPO / "corpus" / "gold_candidates" / "papers" / PAPER
    gold = json.loads((d / "gold.json").read_text())
    v7 = json.loads((REPO / "corpus" / "silver" / "opus-5.5__v7_gold" / f"{PAPER}.json").read_text())
    rules = json.loads((d / "rules.json").read_text())
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.2), gridspec_kw={"width_ratios": [1.25, 1, 1]})
    axs[0].imshow(Image.open(d / "figpage2.png").crop(CROP))
    axs[0].axis("off")
    axs[0].set_title("(a) the authors' diagram", fontsize=10)
    for ax, (title, pred) in zip(axs[1:], (("(b) LLM extractor", v7), ("(c) rule-based extractor", rules))):
        hit, extra = found(pred, gold)
        panel(ax, f"{title}: {len(hit)}/{len(DRAWN)} arrows", hit, extra)
    fig.tight_layout()
    fig.savefig(a.out, dpi=200)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
