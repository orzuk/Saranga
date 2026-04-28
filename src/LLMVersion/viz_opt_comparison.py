#!/usr/bin/env python3
"""
Visualize prompt optimization results from optimization_history.json.

Usage:
    python viz_opt_comparison.py --opt-dir definition_optimization
    python viz_opt_comparison.py --opt-dir lemma_optimization --structure-type lemma
"""

import argparse
import json
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── Colours ────────────────────────────────────────────────────────────
C_PREC = "#2196F3"
C_REC  = "#4CAF50"
C_F1   = "#FF9800"
C_TP   = "#66BB6A"
C_FP   = "#EF5350"
C_FN   = "#FFA726"
C_VAL  = "#7E57C2"
BG     = "#FAFAFA"

# Palette for prompt evolution bars (cycles if >3 iterations)
BAR_COLORS = ["#90CAF9", "#CE93D8", "#80CBC4", "#FFE082", "#EF9A9A",
              "#A5D6A7", "#B39DDB", "#81D4FA"]


def load_history(opt_dir):
    """Load optimization_history.json from the given directory."""
    path = os.path.join(opt_dir, "optimization_history.json")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found"); sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Visualize prompt optimization results")
    parser.add_argument("--opt-dir", required=True,
                        help="Directory containing optimization_history.json")
    parser.add_argument("--structure-type", default=None,
                        help="Structure type label (auto-detected from dir name if omitted)")
    args = parser.parse_args()

    history = load_history(args.opt_dir)

    # Auto-detect structure type from dir name
    stype = args.structure_type
    if not stype:
        dirname = os.path.basename(args.opt_dir.rstrip("/"))
        stype = dirname.replace("_optimization", "").replace("_", " ").title()

    iterations = history["iterations"]
    n_iters = len(iterations)
    iters = list(range(n_iters))

    provider = history.get("provider", "unknown")
    model = history.get("model", "")
    threshold = history.get("threshold", 0.7)
    best_iter = history.get("best_iteration", n_iters - 1)

    n_train = len(history.get("train_paper_ids", []))
    n_val = len(history.get("val_paper_ids", []))

    # ── Extract per-iteration metrics ────────────────────────────────
    precision = [it["train_metrics"]["precision"] for it in iterations]
    recall    = [it["train_metrics"]["recall"]    for it in iterations]
    f1        = [it["train_metrics"]["f1"]        for it in iterations]
    tp        = [it["train_metrics"]["true_positives"]  for it in iterations]
    fp        = [it["train_metrics"]["false_positives"] for it in iterations]
    fn        = [it["train_metrics"]["false_negatives"] for it in iterations]
    num_gold  = [it["train_metrics"].get("num_gold", 0) for it in iterations]

    # Prompt word counts
    prompt_words = [len(it["prompt"].split()) for it in iterations]

    # Validation metrics (from best prompt)
    val = history.get("validation_metrics")
    has_val = val is not None and val.get("f1") is not None

    # Best iteration train metrics
    best = iterations[best_iter]["train_metrics"]

    # ── Figure ───────────────────────────────────────────────────────
    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    gs = gridspec.GridSpec(
        2, 3, hspace=0.38, wspace=0.32,
        left=0.07, right=0.95, top=0.88, bottom=0.08,
    )

    fig.suptitle(
        f"{stype} Prompt Optimization  ({provider} {model})",
        fontsize=15, fontweight="bold", y=0.96,
    )

    # Subtitle with paper/gold counts
    gold_total = num_gold[best_iter] if num_gold else "?"
    val_gold = val.get("num_gold", "?") if has_val else "?"
    subtitle_parts = [f"Train: {n_train} papers ({gold_total} gold)"]
    if has_val:
        subtitle_parts.append(f"Val: {n_val} papers ({val_gold} gold)")
    subtitle_parts.append(f"Jaccard threshold: {threshold}")
    fig.text(0.5, 0.915, "     ".join(subtitle_parts),
             ha="center", fontsize=10.5, color="#666")

    iter_labels = [f"Iter {i}" for i in iters]

    # ── 1. P / R / F1 lines (train) ─────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(BG)
    ax1.plot(iters, precision, "o-", color=C_PREC, lw=2, ms=8, label="Precision")
    ax1.plot(iters, recall,    "s-", color=C_REC,  lw=2, ms=8, label="Recall")
    ax1.plot(iters, f1,        "D-", color=C_F1,   lw=2.4, ms=9, label="F1")
    for i in iters:
        ax1.text(i, f1[i] - 0.04, f"{f1[i]:.3f}", ha="center", fontsize=8.5, color=C_F1)
    ax1.set_xticks(iters)
    ax1.set_xticklabels(iter_labels)
    all_vals = precision + recall + f1
    y_min = max(0, min(all_vals) - 0.15)
    y_max = min(1.05, max(all_vals) + 0.15)
    ax1.set_ylim(y_min, y_max)
    ax1.set_ylabel("Score")
    ax1.set_title("Train P / R / F1", fontweight="bold", fontsize=12)
    ax1.legend(fontsize=8.5, loc="best", framealpha=0.9)
    ax1.grid(axis="y", alpha=0.25)

    # ── 2. TP / FP / FN stacked bars (train) ────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(BG)
    x = np.array(iters)
    w = min(0.52, 0.8 / max(n_iters, 1))
    ax2.bar(x, tp, w, color=C_TP, label="TP", edgecolor="white", lw=0.7)
    ax2.bar(x, fp, w, bottom=tp, color=C_FP, label="FP", edgecolor="white", lw=0.7)
    ax2.bar(x, fn, w, bottom=[t + f for t, f in zip(tp, fp)],
            color=C_FN, label="FN", edgecolor="white", lw=0.7)
    for i in iters:
        ax2.text(i, tp[i] / 2, str(tp[i]), ha="center", va="center",
                 fontsize=10, fontweight="bold", color="white")
        if fp[i]:
            ax2.text(i, tp[i] + fp[i] / 2, str(fp[i]), ha="center", va="center",
                     fontsize=10, fontweight="bold", color="white")
        if fn[i]:
            ax2.text(i, tp[i] + fp[i] + fn[i] / 2, str(fn[i]), ha="center",
                     va="center", fontsize=10, fontweight="bold", color="white")
    ax2.set_xticks(iters)
    ax2.set_xticklabels(iter_labels)
    ax2.set_ylabel("Count")
    max_stack = max(t + f + n for t, f, n in zip(tp, fp, fn))
    ax2.set_ylim(0, max_stack * 1.25)
    ax2.set_title("Train TP / FP / FN", fontweight="bold", fontsize=12)
    ax2.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
    ax2.grid(axis="y", alpha=0.25)

    # ── 3. Prompt size evolution ─────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor(BG)
    colors_3 = [BAR_COLORS[i % len(BAR_COLORS)] for i in iters]
    bars3 = ax3.bar(iters, prompt_words, w, color=colors_3,
                    edgecolor="white", lw=0.7)
    for i, b in enumerate(bars3):
        ax3.text(i, b.get_height() + max(prompt_words) * 0.03,
                 str(prompt_words[i]),
                 ha="center", fontsize=10, fontweight="bold", color="#37474F")
    ax3.set_xticks(iters)
    ax3.set_xticklabels(iter_labels)
    ax3.set_ylabel("Word count")
    ax3.set_ylim(0, max(prompt_words) * 1.25)
    ax3.set_title("Prompt Evolution", fontweight="bold", fontsize=12)
    ax3.grid(axis="y", alpha=0.25)

    # ── 4. Train vs Val comparison (best prompt) ────────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor(BG)
    metrics = ["Precision", "Recall", "F1"]
    train_vals = [best["precision"], best["recall"], best["f1"]]

    if has_val:
        val_vals = [val["precision"], val["recall"], val["f1"]]
        xm = np.arange(len(metrics))
        w2 = 0.32
        b1 = ax4.bar(xm - w2 / 2, train_vals, w2, color=C_F1,
                      label="Train", edgecolor="white")
        b2 = ax4.bar(xm + w2 / 2, val_vals, w2, color=C_VAL,
                      label="Validation", edgecolor="white")
        for b in b1:
            ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                     f"{b.get_height():.3f}", ha="center", fontsize=9, color=C_F1)
        for b in b2:
            ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                     f"{b.get_height():.3f}", ha="center", fontsize=9, color=C_VAL)
        ax4.set_xticks(xm)
        ax4.set_xticklabels(metrics)
        ax4.set_ylim(0, 1.15)
        ax4.set_title(f"Best Prompt (Iter {best_iter}): Train vs Val",
                      fontweight="bold", fontsize=12)
        ax4.legend(fontsize=8.5, framealpha=0.9)
    else:
        xm = np.arange(len(metrics))
        b1 = ax4.bar(xm, train_vals, 0.45, color=C_F1, edgecolor="white")
        for b in b1:
            ax4.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                     f"{b.get_height():.3f}", ha="center", fontsize=9, color=C_F1)
        ax4.set_xticks(xm)
        ax4.set_xticklabels(metrics)
        ax4.set_ylim(0, 1.15)
        ax4.set_title(f"Best Prompt (Iter {best_iter}): Train Metrics",
                      fontweight="bold", fontsize=12)
    ax4.grid(axis="y", alpha=0.25)

    # ── 5. Val TP / FP / FN (horizontal bar) ────────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_facecolor(BG)

    if has_val:
        val_tp = val["true_positives"]
        val_fp = val["false_positives"]
        val_fn = val["false_negatives"]
        val_total = val_tp + val_fp + val_fn

        ax5.barh(0, val_tp, color=C_TP, edgecolor="white", lw=0.7, label="TP")
        ax5.barh(0, val_fp, left=val_tp, color=C_FP, edgecolor="white", lw=0.7, label="FP")
        ax5.barh(0, val_fn, left=val_tp + val_fp, color=C_FN,
                 edgecolor="white", lw=0.7, label="FN")
        if val_tp:
            ax5.text(val_tp / 2, 0, f"TP = {val_tp}", ha="center", va="center",
                     fontsize=11, fontweight="bold", color="white")
        if val_fp:
            ax5.text(val_tp + val_fp / 2, 0, f"FP = {val_fp}", ha="center",
                     va="center", fontsize=11, fontweight="bold", color="white")
        if val_fn:
            ax5.text(val_tp + val_fp + val_fn / 2, 0, f"FN = {val_fn}",
                     ha="center", va="center", fontsize=11, fontweight="bold",
                     color="white")
        ax5.set_xlim(0, val_total * 1.15)
        ax5.set_yticks([])
        ax5.set_xlabel("Count")
        ax5.set_title(f"Validation Counts (Iter {best_iter})",
                      fontweight="bold", fontsize=12)
        ax5.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
        ax5.grid(axis="x", alpha=0.25)
        # Gold reference line
        vg = val.get("num_gold", 0)
        if vg:
            ax5.axvline(vg, color="#333", ls="--", lw=1, alpha=0.5)
            ax5.text(vg, 0.35, f"gold = {vg}", ha="center", fontsize=8, color="#555")
    else:
        # No validation — show best-iteration train counts instead
        best_tp, best_fp, best_fn = best["true_positives"], best["false_positives"], best["false_negatives"]
        best_total = best_tp + best_fp + best_fn
        ax5.barh(0, best_tp, color=C_TP, edgecolor="white", lw=0.7, label="TP")
        ax5.barh(0, best_fp, left=best_tp, color=C_FP, edgecolor="white", lw=0.7, label="FP")
        ax5.barh(0, best_fn, left=best_tp + best_fp, color=C_FN,
                 edgecolor="white", lw=0.7, label="FN")
        if best_tp:
            ax5.text(best_tp / 2, 0, f"TP = {best_tp}", ha="center", va="center",
                     fontsize=11, fontweight="bold", color="white")
        if best_fp:
            ax5.text(best_tp + best_fp / 2, 0, f"FP = {best_fp}", ha="center",
                     va="center", fontsize=11, fontweight="bold", color="white")
        if best_fn:
            ax5.text(best_tp + best_fp + best_fn / 2, 0, f"FN = {best_fn}",
                     ha="center", va="center", fontsize=11, fontweight="bold",
                     color="white")
        ax5.set_xlim(0, best_total * 1.15)
        ax5.set_yticks([])
        ax5.set_xlabel("Count")
        ax5.set_title(f"Best Iteration (Iter {best_iter}) Counts",
                      fontweight="bold", fontsize=12)
        ax5.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
        ax5.grid(axis="x", alpha=0.25)

    # ── 6. F1 trajectory with best marker ────────────────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.set_facecolor(BG)
    ax6.fill_between(iters, f1, alpha=0.15, color=C_F1)
    ax6.plot(iters, f1, "D-", color=C_F1, lw=2.4, ms=10, zorder=5)
    # Best marker
    ax6.plot(best_iter, f1[best_iter], "*", ms=20, color="#D32F2F", zorder=6)
    ax6.text(best_iter - 0.25, f1[best_iter] + 0.02, "best",
             fontsize=9, color="#D32F2F", fontweight="bold")
    # Val F1 line
    if has_val:
        ax6.axhline(val["f1"], color=C_VAL, ls="--", lw=1.5, alpha=0.7)
        ax6.text(iters[-1] + 0.05, val["f1"] + 0.01,
                 f"Val F1 = {val['f1']:.3f}", fontsize=9,
                 color=C_VAL, fontweight="bold")
    for i in iters:
        ax6.text(i, f1[i] - 0.03, f"{f1[i]:.3f}", ha="center",
                 fontsize=9, color=C_F1)
    ax6.set_xticks(iters)
    ax6.set_xticklabels(iter_labels)
    f1_min = min(f1 + ([val["f1"]] if has_val else []))
    f1_max = max(f1 + ([val["f1"]] if has_val else []))
    ax6.set_ylim(max(0, f1_min - 0.1), min(1.05, f1_max + 0.1))
    ax6.set_ylabel("F1")
    ax6.set_title("F1 Trajectory + Validation", fontweight="bold", fontsize=12)
    ax6.grid(axis="y", alpha=0.25)

    # ── Save ─────────────────────────────────────────────────────────
    out_path = os.path.join(args.opt_dir, "optimization_viz.png")
    plt.savefig(out_path, dpi=180, facecolor=BG)
    plt.close()
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
