#!/usr/bin/env python3
"""
Visualize provider comparison from evaluation pipeline results.

Usage:
    python viz_eval_comparison.py --eval-dir definition_eval
    python viz_eval_comparison.py --eval-dir lemma_eval --structure-type lemma
"""

import argparse
import csv
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict

# ── Colours ────────────────────────────────────────────────────────────
PROVIDER_COLORS = {
    "anthropic":   "#6C63FF",
    "openai":      "#10A37F",
    "huggingface": "#FFB800",
    "manual":      "#EF5350",
}
C_TP   = "#66BB6A"
C_FP   = "#EF5350"
C_FN   = "#FFA726"
C_GOLD = "#37474F"
BG     = "#FAFAFA"


def get_color(provider):
    for key, color in PROVIDER_COLORS.items():
        if key in provider.lower():
            return color
    return "#9E9E9E"


def load_summary(path):
    """Load evaluation_results.csv → list of dicts."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            for k in ("num_gold_standards", "num_extracted", "true_positives",
                       "false_positives", "false_negatives"):
                r[k] = int(r[k])
            for k in ("precision", "recall", "f1_score"):
                r[k] = float(r[k])
            rows.append(r)
    return rows


def load_detailed(path):
    """Load detailed_matches.csv → list of dicts."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["similarity"] = float(r["similarity"])
            r["threshold"] = float(r["threshold"])
            rows.append(r)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Visualize evaluation comparison")
    parser.add_argument("--eval-dir", required=True, help="Directory with evaluation CSVs")
    parser.add_argument("--structure-type", default=None,
                        help="Structure type label (auto-detected from dir name if omitted)")
    args = parser.parse_args()

    eval_dir = args.eval_dir
    summary_path = os.path.join(eval_dir, "evaluation_results.csv")
    detailed_path = os.path.join(eval_dir, "detailed_matches.csv")

    if not os.path.exists(summary_path):
        print(f"ERROR: {summary_path} not found"); sys.exit(1)

    summary = load_summary(summary_path)
    detailed = load_detailed(detailed_path) if os.path.exists(detailed_path) else []

    # Auto-detect structure type from dir name
    stype = args.structure_type
    if not stype:
        dirname = os.path.basename(eval_dir.rstrip("/"))
        stype = dirname.replace("_eval", "").replace("_", " ").title()

    # ── Aggregate across papers per provider ───────────────────────────
    prov_agg = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "gold": 0, "ext": 0})
    papers = set()
    for r in summary:
        p = r["provider"]
        prov_agg[p]["tp"]   += r["true_positives"]
        prov_agg[p]["fp"]   += r["false_positives"]
        prov_agg[p]["fn"]   += r["false_negatives"]
        prov_agg[p]["gold"] += r["num_gold_standards"]
        prov_agg[p]["ext"]  += r["num_extracted"]
        papers.add(r["paper_id"])

    providers = sorted(prov_agg.keys(), key=lambda p: (p != "anthropic", p != "openai", p))
    n_papers = len(papers)

    # Compute macro P/R/F1
    for p in providers:
        a = prov_agg[p]
        a["precision"] = a["tp"] / (a["tp"] + a["fp"]) if (a["tp"] + a["fp"]) > 0 else 0
        a["recall"]    = a["tp"] / (a["tp"] + a["fn"]) if (a["tp"] + a["fn"]) > 0 else 0
        pr = a["precision"] + a["recall"]
        a["f1"] = 2 * a["precision"] * a["recall"] / pr if pr > 0 else 0

    # Per-provider similarity scores
    prov_sims = defaultdict(list)
    for r in detailed:
        prov_sims[r["provider"]].append(r["similarity"])

    # Per-paper F1 matrix (for heatmap if multi-paper)
    paper_ids = sorted(papers)
    prov_paper_f1 = {}
    for r in summary:
        prov_paper_f1[(r["provider"], r["paper_id"])] = r["f1_score"]

    # ── Figure layout ──────────────────────────────────────────────────
    n_rows = 2 if n_papers > 1 else 2
    fig = plt.figure(figsize=(18, 10), facecolor=BG)
    gs = gridspec.GridSpec(2, 3, hspace=0.38, wspace=0.34,
                           left=0.06, right=0.96, top=0.87, bottom=0.07)

    fig.suptitle(
        f"{stype} Extraction — Provider Comparison",
        fontsize=16, fontweight="bold", y=0.96,
    )
    fig.text(0.5, 0.915,
             f"{n_papers} paper{'s' if n_papers > 1 else ''}  |  "
             f"Gold: {prov_agg[providers[0]]['gold']}  |  "
             f"Jaccard threshold: {detailed[0]['threshold'] if detailed else 0.7}",
             ha="center", fontsize=11, color="#666")

    # ── 1. P / R / F1 grouped bars ────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(BG)
    metrics = ["Precision", "Recall", "F1"]
    x = np.arange(len(metrics))
    n_prov = len(providers)
    w = 0.7 / n_prov
    for i, p in enumerate(providers):
        a = prov_agg[p]
        vals = [a["precision"], a["recall"], a["f1"]]
        bars = ax1.bar(x + (i - n_prov / 2 + 0.5) * w, vals, w,
                       color=get_color(p), label=p, edgecolor="white", lw=0.7)
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                     f"{v:.2f}", ha="center", fontsize=7.5, fontweight="bold",
                     color=get_color(p))
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics, fontsize=10)
    ax1.set_ylim(0, 1.22)
    ax1.set_title("Precision / Recall / F1", fontweight="bold", fontsize=12)
    ax1.legend(fontsize=8, loc="upper right", framealpha=0.9)
    ax1.grid(axis="y", alpha=0.25)

    # ── 2. TP / FP / FN stacked bars per provider ─────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(BG)
    xp = np.arange(n_prov)
    tps = [prov_agg[p]["tp"] for p in providers]
    fps = [prov_agg[p]["fp"] for p in providers]
    fns = [prov_agg[p]["fn"] for p in providers]
    bw = 0.55
    ax2.bar(xp, tps, bw, color=C_TP, label="TP", edgecolor="white", lw=0.7)
    ax2.bar(xp, fps, bw, bottom=tps, color=C_FP, label="FP", edgecolor="white", lw=0.7)
    ax2.bar(xp, fns, bw, bottom=[t + f for t, f in zip(tps, fps)],
            color=C_FN, label="FN", edgecolor="white", lw=0.7)
    for i in range(n_prov):
        if tps[i]:
            ax2.text(i, tps[i] / 2, str(tps[i]), ha="center", va="center",
                     fontsize=10, fontweight="bold", color="white")
        if fps[i]:
            ax2.text(i, tps[i] + fps[i] / 2, str(fps[i]), ha="center", va="center",
                     fontsize=10, fontweight="bold", color="white")
        if fns[i]:
            ax2.text(i, tps[i] + fps[i] + fns[i] / 2, str(fns[i]), ha="center",
                     va="center", fontsize=10, fontweight="bold", color="white")
    ax2.set_xticks(xp)
    ax2.set_xticklabels(providers, fontsize=9)
    ax2.set_ylabel("Count")
    ax2.set_title("TP / FP / FN by Provider", fontweight="bold", fontsize=12)
    ax2.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
    ax2.grid(axis="y", alpha=0.25)

    # ── 3. Extraction count vs Gold ───────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor(BG)
    gold_count = prov_agg[providers[0]]["gold"]
    ext_counts = [prov_agg[p]["ext"] for p in providers]
    colors = [get_color(p) for p in providers]
    bars3 = ax3.bar(xp, ext_counts, bw, color=colors, edgecolor="white", lw=0.7)
    ax3.axhline(gold_count, color=C_GOLD, ls="--", lw=2, alpha=0.7)
    ax3.text(n_prov - 0.5, gold_count + 0.3, f"Gold = {gold_count}",
             fontsize=9.5, color=C_GOLD, fontweight="bold", ha="right")
    for i, b in enumerate(bars3):
        ax3.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3,
                 str(ext_counts[i]), ha="center", fontsize=10, fontweight="bold",
                 color=colors[i])
    ax3.set_xticks(xp)
    ax3.set_xticklabels(providers, fontsize=9)
    ax3.set_ylabel("Count")
    ax3.set_title("Extracted vs Gold Standard", fontweight="bold", fontsize=12)
    ax3.grid(axis="y", alpha=0.25)

    # ── 4. Similarity score distributions (box plots) ─────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor(BG)
    if prov_sims:
        sim_data = [prov_sims.get(p, []) for p in providers]
        bp = ax4.boxplot(sim_data, patch_artist=True, widths=0.5,
                         medianprops=dict(color="black", lw=2))
        for patch, p in zip(bp["boxes"], providers):
            patch.set_facecolor(get_color(p))
            patch.set_alpha(0.7)
        # Scatter individual points
        for i, (p, sims) in enumerate(zip(providers, sim_data)):
            if sims:
                jitter = np.random.normal(0, 0.04, len(sims))
                ax4.scatter(np.full(len(sims), i + 1) + jitter, sims,
                           color=get_color(p), alpha=0.5, s=20, zorder=3)
        threshold = detailed[0]["threshold"] if detailed else 0.7
        ax4.axhline(threshold, color="#D32F2F", ls="--", lw=1.5, alpha=0.7)
        ax4.text(n_prov + 0.3, threshold + 0.02, f"threshold = {threshold}",
                 fontsize=8.5, color="#D32F2F", fontweight="bold")
        ax4.set_xticklabels(providers, fontsize=9)
        ax4.set_ylabel("Jaccard Similarity")
        ax4.set_ylim(-0.05, 1.1)
    ax4.set_title("Similarity Score Distribution", fontweight="bold", fontsize=12)
    ax4.grid(axis="y", alpha=0.25)

    # ── 5. Per-paper F1 heatmap (if multi-paper) or F1 radar ──────────
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_facecolor(BG)

    if n_papers > 1:
        # Heatmap
        matrix = np.zeros((len(paper_ids), n_prov))
        for pi, pid in enumerate(paper_ids):
            for pj, prov in enumerate(providers):
                matrix[pi, pj] = prov_paper_f1.get((prov, pid), 0)
        im = ax5.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax5.set_xticks(range(n_prov))
        ax5.set_xticklabels(providers, fontsize=8, rotation=30, ha="right")
        ax5.set_yticks(range(len(paper_ids)))
        short_ids = [pid[:12] for pid in paper_ids]
        ax5.set_yticklabels(short_ids, fontsize=8)
        # Annotate cells
        for pi in range(len(paper_ids)):
            for pj in range(n_prov):
                val = matrix[pi, pj]
                txt_color = "white" if val < 0.5 else "black"
                ax5.text(pj, pi, f"{val:.2f}", ha="center", va="center",
                         fontsize=8.5, color=txt_color, fontweight="bold")
        plt.colorbar(im, ax=ax5, fraction=0.046, pad=0.04)
        ax5.set_title("F1 per Paper x Provider", fontweight="bold", fontsize=12)
    else:
        # Single paper — show match quality breakdown
        for i, p in enumerate(providers):
            sims = prov_sims.get(p, [])
            if not sims:
                continue
            matches = [s for s in sims if s >= (detailed[0]["threshold"] if detailed else 0.7)]
            misses = [s for s in sims if s < (detailed[0]["threshold"] if detailed else 0.7)]
            ax5.barh(i, len(matches), 0.5, color=C_TP, edgecolor="white", lw=0.7,
                     label="Match" if i == 0 else "")
            ax5.barh(i, len(misses), 0.5, left=len(matches), color=C_FP,
                     edgecolor="white", lw=0.7, label="No match" if i == 0 else "")
            ax5.text(len(matches) / 2, i, str(len(matches)) if matches else "",
                     ha="center", va="center", fontsize=10, fontweight="bold", color="white")
            if misses:
                ax5.text(len(matches) + len(misses) / 2, i, str(len(misses)),
                         ha="center", va="center", fontsize=10, fontweight="bold", color="white")
        ax5.set_yticks(range(n_prov))
        ax5.set_yticklabels(providers, fontsize=9)
        ax5.set_xlabel("Extractions")
        ax5.set_title("Match vs No-Match Count", fontweight="bold", fontsize=12)
        ax5.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
        ax5.grid(axis="x", alpha=0.25)

    # ── 6. F1 summary bar chart (horizontal, sorted) ─────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.set_facecolor(BG)
    f1_vals = [(p, prov_agg[p]["f1"]) for p in providers]
    f1_vals.sort(key=lambda x: x[1], reverse=True)
    y_pos = np.arange(len(f1_vals))
    f1_colors = [get_color(p) for p, _ in f1_vals]
    f1_scores = [v for _, v in f1_vals]
    f1_names  = [p for p, _ in f1_vals]

    bars6 = ax6.barh(y_pos, f1_scores, 0.55, color=f1_colors, edgecolor="white", lw=0.7)
    for i, (b, score) in enumerate(zip(bars6, f1_scores)):
        ax6.text(b.get_width() + 0.02, b.get_y() + b.get_height() / 2,
                 f"{score:.3f}", va="center", fontsize=11, fontweight="bold",
                 color=f1_colors[i])
    ax6.set_yticks(y_pos)
    ax6.set_yticklabels(f1_names, fontsize=10)
    ax6.set_xlim(0, 1.18)
    ax6.set_xlabel("F1 Score")
    ax6.set_title("F1 Ranking", fontweight="bold", fontsize=12)
    ax6.invert_yaxis()
    ax6.grid(axis="x", alpha=0.25)
    # Best marker
    ax6.text(f1_scores[0] / 2, 0, "BEST", ha="center", va="center",
             fontsize=11, fontweight="bold", color="white")

    # ── Save ───────────────────────────────────────────────────────────
    out_path = os.path.join(eval_dir, "eval_comparison.png")
    plt.savefig(out_path, dpi=180, facecolor=BG)
    plt.close()
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
