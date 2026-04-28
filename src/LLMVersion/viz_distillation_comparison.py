#!/usr/bin/env python3
"""
Compare manual parser before vs after distillation.

Reads existing evaluation from --eval-dir (the "before"), re-runs the
manual parser on the same papers, evaluates, and produces a 6-panel
comparison figure.

Usage:
    python viz_distillation_comparison.py --eval-dir proof_eval
    python viz_distillation_comparison.py --eval-dir proof_eval --structure-type proof
"""

import argparse
import csv
import os
import subprocess
import sys
import tempfile
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict

# ── Colours ────────────────────────────────────────────────────────────
C_BEFORE = "#EF5350"
C_AFTER  = "#66BB6A"
C_TP     = "#66BB6A"
C_FP     = "#EF5350"
C_FN     = "#FFA726"
C_GOLD   = "#37474F"
BG       = "#FAFAFA"

LABELS = {"before": "Before Distillation", "after": "After Distillation"}
COLORS = {"before": C_BEFORE, "after": C_AFTER}

PLURAL = {
    "definition": "Definitions", "theorem": "Theorems", "lemma": "Lemmas",
    "proposition": "Propositions", "corollary": "Corollaries", "claim": "Claims",
    "conjecture": "Conjectures", "problem": "Problems", "proof": "Proofs",
    "algorithm": "Algorithms", "table": "Tables",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_summary(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in ("num_gold_standards", "num_extracted", "true_positives",
                       "false_positives", "false_negatives"):
                r[k] = int(r[k])
            for k in ("precision", "recall", "f1_score"):
                r[k] = float(r[k])
            rows.append(r)
    return rows


def load_detailed(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["similarity"] = float(r["similarity"])
            r["threshold"] = float(r["threshold"])
            rows.append(r)
    return rows


def filter_manual(rows):
    return [r for r in rows if r["provider"] == "manual"]


def run_pipeline(paper_ids, structure_type, work_dir):
    """Re-run manual parsing + evaluation in work_dir, return paths."""
    gold_csv = os.path.join(SCRIPT_DIR, f"Gold_Standard_{PLURAL[structure_type]}.csv")
    if not os.path.exists(gold_csv):
        print(f"ERROR: gold CSV not found: {gold_csv}"); sys.exit(1)

    # 1. Extract each paper with manual parser
    for pid in paper_ids:
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, "parse_batch.py"),
               "--regex-id", f"^{pid}",
               "--out-dir", work_dir,
               "--extraction-mode", "manual",
               "--structure-types", structure_type]
        print(f"  Parsing {pid} ...")
        subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)

    # 2. JSON → CSV
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "definitions_from_json_to_csv.py"),
           "--structure-type", structure_type,
           "--out-dir", work_dir,
           "--output-csv", os.path.join(work_dir, "definitions.csv")]
    for pid in paper_ids:
        cmd += ["--paper-id", pid]
    subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)

    # 3. Merge gold standard
    merged = os.path.join(work_dir, "MergedGoldAndDef.csv")
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "add_gold_standard.py"),
           "--input-csv", os.path.join(work_dir, "definitions.csv"),
           "--gold-csv", gold_csv,
           "--output-csv", merged]
    subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)

    # 4. Evaluate
    eval_csv = os.path.join(work_dir, "evaluation_results.csv")
    detail_csv = os.path.join(work_dir, "detailed_matches.csv")
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "evaluate_definitions.py"),
           "--input-csv", merged,
           "--threshold", "0.7",
           "--output-csv", eval_csv,
           "--detailed-csv", detail_csv]
    subprocess.run(cmd, check=True, cwd=SCRIPT_DIR)

    return eval_csv, detail_csv


def aggregate(summary_rows):
    a = {"tp": 0, "fp": 0, "fn": 0, "gold": 0, "ext": 0}
    for r in summary_rows:
        a["tp"]   += r["true_positives"]
        a["fp"]   += r["false_positives"]
        a["fn"]   += r["false_negatives"]
        a["gold"] += r["num_gold_standards"]
        a["ext"]  += r["num_extracted"]
    a["precision"] = a["tp"] / (a["tp"] + a["fp"]) if (a["tp"] + a["fp"]) > 0 else 0
    a["recall"]    = a["tp"] / (a["tp"] + a["fn"]) if (a["tp"] + a["fn"]) > 0 else 0
    pr = a["precision"] + a["recall"]
    a["f1"] = 2 * a["precision"] * a["recall"] / pr if pr > 0 else 0
    return a


def main():
    ap = argparse.ArgumentParser(description="Before/after distillation comparison")
    ap.add_argument("--eval-dir", required=True, help="Dir with pre-distillation eval results")
    ap.add_argument("--structure-type", default=None,
                    help="Structure type (auto-detected from dir name if omitted)")
    ap.add_argument("--output", default=None, help="Output PNG path")
    args = ap.parse_args()

    eval_dir = args.eval_dir
    before_summary_path = os.path.join(eval_dir, "evaluation_results.csv")
    before_detail_path  = os.path.join(eval_dir, "detailed_matches.csv")

    if not os.path.exists(before_summary_path):
        print(f"ERROR: {before_summary_path} not found"); sys.exit(1)

    # Detect structure type
    stype = args.structure_type
    if not stype:
        dirname = os.path.basename(eval_dir.rstrip("/"))
        stype = dirname.replace("_eval", "").replace("_", " ").lower().strip()
    if stype not in PLURAL:
        print(f"ERROR: unknown structure type '{stype}'. Use --structure-type."); sys.exit(1)

    # Load before data (manual only)
    before_all = load_summary(before_summary_path)
    before_summary = filter_manual(before_all)
    before_detailed = filter_manual(load_detailed(before_detail_path))

    if not before_summary:
        print("ERROR: no manual rows in before evaluation_results.csv"); sys.exit(1)

    # Get paper list from before (all papers that had manual rows)
    paper_ids = sorted(set(r["paper_id"] for r in before_summary))
    print(f"Structure type: {stype}")
    print(f"Papers: {', '.join(paper_ids)}")

    # Re-run manual pipeline
    work_dir = tempfile.mkdtemp(prefix=f"{stype}_distill_")
    print(f"\nRe-running manual parser → {work_dir}")
    after_eval_csv, after_detail_csv = run_pipeline(paper_ids, stype, work_dir)

    after_summary  = filter_manual(load_summary(after_eval_csv))
    after_detailed = filter_manual(load_detailed(after_detail_csv))

    if not after_summary:
        print("ERROR: no manual rows in after evaluation_results.csv"); sys.exit(1)

    # ── Aggregate ─────────────────────────────────────────────────────
    phases = ["before", "after"]
    agg = {"before": aggregate(before_summary), "after": aggregate(after_summary)}

    papers_all = set(r["paper_id"] for r in before_summary) | \
                 set(r["paper_id"] for r in after_summary)
    n_papers = len(papers_all)
    paper_ids_all = sorted(papers_all)

    phase_sims = {
        "before": [r["similarity"] for r in before_detailed],
        "after":  [r["similarity"] for r in after_detailed],
    }

    paper_f1 = {}
    for r in before_summary:
        paper_f1[("before", r["paper_id"])] = r["f1_score"]
    for r in after_summary:
        paper_f1[("after", r["paper_id"])] = r["f1_score"]

    threshold = 0.7
    for det in (before_detailed, after_detailed):
        if det:
            threshold = det[0]["threshold"]
            break

    stype_title = stype.title()
    n_ph = len(phases)

    # ── Figure ────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(18, 10), facecolor=BG)
    gs = gridspec.GridSpec(2, 3, hspace=0.38, wspace=0.34,
                           left=0.06, right=0.96, top=0.87, bottom=0.07)

    fig.suptitle(
        f"{stype_title} Extraction — Manual Parser: Before vs After Distillation",
        fontsize=16, fontweight="bold", y=0.96)
    fig.text(0.5, 0.915,
             f"{n_papers} paper{'s' if n_papers > 1 else ''}  |  "
             f"Gold: {agg['before']['gold']}  |  "
             f"Jaccard threshold: {threshold}",
             ha="center", fontsize=11, color="#666")

    # 1. P / R / F1
    ax1 = fig.add_subplot(gs[0, 0]); ax1.set_facecolor(BG)
    metrics = ["Precision", "Recall", "F1"]
    x = np.arange(len(metrics)); w = 0.7 / n_ph
    for i, ph in enumerate(phases):
        a = agg[ph]
        vals = [a["precision"], a["recall"], a["f1"]]
        bars = ax1.bar(x + (i - n_ph / 2 + 0.5) * w, vals, w,
                       color=COLORS[ph], label=LABELS[ph], edgecolor="white", lw=0.7)
        for b, v in zip(bars, vals):
            ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02,
                     f"{v:.2f}", ha="center", fontsize=8, fontweight="bold", color=COLORS[ph])
    ax1.set_xticks(x); ax1.set_xticklabels(metrics, fontsize=10)
    ax1.set_ylim(0, 1.22)
    ax1.set_title("Precision / Recall / F1", fontweight="bold", fontsize=12)
    ax1.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
    ax1.grid(axis="y", alpha=0.25)

    # 2. TP / FP / FN
    ax2 = fig.add_subplot(gs[0, 1]); ax2.set_facecolor(BG)
    xp = np.arange(n_ph)
    tps = [agg[ph]["tp"] for ph in phases]
    fps = [agg[ph]["fp"] for ph in phases]
    fns = [agg[ph]["fn"] for ph in phases]
    bw = 0.55
    ax2.bar(xp, tps, bw, color=C_TP, label="TP", edgecolor="white", lw=0.7)
    ax2.bar(xp, fps, bw, bottom=tps, color=C_FP, label="FP", edgecolor="white", lw=0.7)
    ax2.bar(xp, fns, bw, bottom=[t + f for t, f in zip(tps, fps)],
            color=C_FN, label="FN", edgecolor="white", lw=0.7)
    for i in range(n_ph):
        if tps[i]:
            ax2.text(i, tps[i] / 2, str(tps[i]), ha="center", va="center",
                     fontsize=11, fontweight="bold", color="white")
        if fps[i]:
            ax2.text(i, tps[i] + fps[i] / 2, str(fps[i]), ha="center", va="center",
                     fontsize=11, fontweight="bold", color="white")
        if fns[i]:
            ax2.text(i, tps[i] + fps[i] + fns[i] / 2, str(fns[i]), ha="center",
                     va="center", fontsize=11, fontweight="bold", color="white")
    ax2.set_xticks(xp)
    ax2.set_xticklabels([LABELS[ph] for ph in phases], fontsize=9)
    ax2.set_ylabel("Count")
    ax2.set_title("TP / FP / FN", fontweight="bold", fontsize=12)
    ax2.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
    ax2.grid(axis="y", alpha=0.25)

    # 3. Extracted vs Gold
    ax3 = fig.add_subplot(gs[0, 2]); ax3.set_facecolor(BG)
    gold_count = agg["before"]["gold"]
    ext_counts = [agg[ph]["ext"] for ph in phases]
    colors = [COLORS[ph] for ph in phases]
    bars3 = ax3.bar(xp, ext_counts, bw, color=colors, edgecolor="white", lw=0.7)
    ax3.axhline(gold_count, color=C_GOLD, ls="--", lw=2, alpha=0.7)
    ax3.text(n_ph - 0.5, gold_count + 0.3, f"Gold = {gold_count}",
             fontsize=9.5, color=C_GOLD, fontweight="bold", ha="right")
    for i, b in enumerate(bars3):
        ax3.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3,
                 str(ext_counts[i]), ha="center", fontsize=10, fontweight="bold",
                 color=colors[i])
    ax3.set_xticks(xp)
    ax3.set_xticklabels([LABELS[ph] for ph in phases], fontsize=9)
    ax3.set_ylabel("Count"); ax3.set_title("Extracted vs Gold Standard", fontweight="bold", fontsize=12)
    ax3.grid(axis="y", alpha=0.25)

    # 4. Similarity box plots
    ax4 = fig.add_subplot(gs[1, 0]); ax4.set_facecolor(BG)
    sim_data = [phase_sims.get(ph, []) for ph in phases]
    if any(s for s in sim_data):
        bp = ax4.boxplot(sim_data, patch_artist=True, widths=0.5,
                         medianprops=dict(color="black", lw=2))
        for patch, ph in zip(bp["boxes"], phases):
            patch.set_facecolor(COLORS[ph]); patch.set_alpha(0.7)
        for i, (ph, sims) in enumerate(zip(phases, sim_data)):
            if sims:
                jitter = np.random.normal(0, 0.04, len(sims))
                ax4.scatter(np.full(len(sims), i + 1) + jitter, sims,
                           color=COLORS[ph], alpha=0.5, s=20, zorder=3)
        ax4.axhline(threshold, color="#D32F2F", ls="--", lw=1.5, alpha=0.7)
        ax4.text(n_ph + 0.3, threshold + 0.02, f"threshold = {threshold}",
                 fontsize=8.5, color="#D32F2F", fontweight="bold")
        ax4.set_xticklabels([LABELS[ph] for ph in phases], fontsize=9)
        ax4.set_ylabel("Jaccard Similarity"); ax4.set_ylim(-0.05, 1.1)
    ax4.set_title("Similarity Score Distribution", fontweight="bold", fontsize=12)
    ax4.grid(axis="y", alpha=0.25)

    # 5. Per-paper F1 heatmap / match breakdown
    ax5 = fig.add_subplot(gs[1, 1]); ax5.set_facecolor(BG)
    if n_papers > 1:
        matrix = np.zeros((len(paper_ids_all), n_ph))
        for pi, pid in enumerate(paper_ids_all):
            for pj, ph in enumerate(phases):
                matrix[pi, pj] = paper_f1.get((ph, pid), 0)
        im = ax5.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        ax5.set_xticks(range(n_ph))
        ax5.set_xticklabels([LABELS[ph] for ph in phases], fontsize=8, rotation=30, ha="right")
        ax5.set_yticks(range(len(paper_ids_all)))
        ax5.set_yticklabels([pid[:12] for pid in paper_ids_all], fontsize=8)
        for pi in range(len(paper_ids_all)):
            for pj in range(n_ph):
                val = matrix[pi, pj]
                ax5.text(pj, pi, f"{val:.2f}", ha="center", va="center",
                         fontsize=9, color="white" if val < 0.5 else "black", fontweight="bold")
        plt.colorbar(im, ax=ax5, fraction=0.046, pad=0.04)
        ax5.set_title("F1 per Paper", fontweight="bold", fontsize=12)
    else:
        for i, ph in enumerate(phases):
            sims = phase_sims.get(ph, [])
            if not sims:
                continue
            matches = [s for s in sims if s >= threshold]
            misses  = [s for s in sims if s < threshold]
            ax5.barh(i, len(matches), 0.5, color=C_TP, edgecolor="white", lw=0.7,
                     label="Match" if i == 0 else "")
            ax5.barh(i, len(misses), 0.5, left=len(matches), color=C_FP,
                     edgecolor="white", lw=0.7, label="No match" if i == 0 else "")
            if matches:
                ax5.text(len(matches) / 2, i, str(len(matches)),
                         ha="center", va="center", fontsize=10, fontweight="bold", color="white")
            if misses:
                ax5.text(len(matches) + len(misses) / 2, i, str(len(misses)),
                         ha="center", va="center", fontsize=10, fontweight="bold", color="white")
        ax5.set_yticks(range(n_ph))
        ax5.set_yticklabels([LABELS[ph] for ph in phases], fontsize=9)
        ax5.set_xlabel("Extractions")
        ax5.set_title("Match vs No-Match Count", fontweight="bold", fontsize=12)
        ax5.legend(fontsize=8.5, loc="upper right", framealpha=0.9)
        ax5.grid(axis="x", alpha=0.25)

    # 6. F1 ranking
    ax6 = fig.add_subplot(gs[1, 2]); ax6.set_facecolor(BG)
    f1_vals = [(ph, agg[ph]["f1"]) for ph in phases]
    f1_vals.sort(key=lambda x: x[1], reverse=True)
    y_pos = np.arange(len(f1_vals))
    f1_colors = [COLORS[p] for p, _ in f1_vals]
    f1_scores = [v for _, v in f1_vals]
    f1_names  = [LABELS[p] for p, _ in f1_vals]

    bars6 = ax6.barh(y_pos, f1_scores, 0.55, color=f1_colors, edgecolor="white", lw=0.7)
    for i, (b, score) in enumerate(zip(bars6, f1_scores)):
        ax6.text(b.get_width() + 0.02, b.get_y() + b.get_height() / 2,
                 f"{score:.3f}", va="center", fontsize=11, fontweight="bold", color=f1_colors[i])
    ax6.set_yticks(y_pos); ax6.set_yticklabels(f1_names, fontsize=10)
    ax6.set_xlim(0, 1.18); ax6.set_xlabel("F1 Score")
    ax6.set_title("F1 Ranking", fontweight="bold", fontsize=12)
    ax6.invert_yaxis(); ax6.grid(axis="x", alpha=0.25)

    delta = agg["after"]["f1"] - agg["before"]["f1"]
    sign = "+" if delta >= 0 else ""
    ax6.text(0.5, 1.08, f"Delta F1: {sign}{delta:.3f}",
             transform=ax6.transAxes, ha="center", fontsize=11,
             fontweight="bold", color="#1565C0",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#E3F2FD", edgecolor="#1565C0"))

    # ── Save ──────────────────────────────────────────────────────────
    out_path = args.output or os.path.join(eval_dir, "distillation_comparison.png")
    plt.savefig(out_path, dpi=180, facecolor=BG)
    plt.close()
    print(f"\nSaved {out_path}")

    # ── Summary table ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  {stype_title} — Manual Parser Distillation Summary")
    print(f"{'='*60}")
    print(f"  {'Metric':<12} {'Before':>10} {'After':>10} {'Delta':>10}")
    print(f"  {'-'*42}")
    for m in ("precision", "recall", "f1"):
        bv, av = agg["before"][m], agg["after"][m]
        d = av - bv
        print(f"  {m.title():<12} {bv:>10.3f} {av:>10.3f} {'+' if d >= 0 else ''}{d:>9.3f}")
    print(f"  {'-'*42}")
    for m in ("tp", "fp", "fn", "ext"):
        label = m.upper() if len(m) <= 2 else "Extracted"
        bv, av = agg["before"][m], agg["after"][m]
        d = av - bv
        print(f"  {label:<12} {bv:>10} {av:>10} {'+' if d >= 0 else ''}{d:>9}")
    print(f"  {'Gold':<12} {agg['before']['gold']:>10}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
