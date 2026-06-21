#!/usr/bin/env python3
"""Per-structure F1 + FP chart (read-only).
Bars = F1 (base parser vs base+distilled, left axis); markers = #FP (right axis).
Pooled tp/fp/fn over the distilled papers, base = step_00 snapshot, distilled =
final snapshot. Writes <eval_dir>/per_type_f1_fp.png.

Usage:
    python scripts/plot_type_f1_fp.py --eval-dir <dir> \
        --tex-dir /Users/.../alignment/papers --match-metric containment
"""
import argparse
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))


def build_chart(eval_dir, tex_dir, match_metric="containment", threshold=0.7):
    import silver_distillation_sequential as seq
    seq._MATCH_METRIC = match_metric
    from silver_distillation_merged import parse_buckets, metrics, load_gold_texts, FNAME_MAP
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    eval_dir = Path(eval_dir); tex_dir = Path(tex_dir)
    papers = [e["paper_id"] for e in
              json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))]
    types = list(FNAME_MAP.keys())
    snaps = sorted(glob.glob(str(eval_dir / "snapshots" / "step_*")))
    step00 = next(s for s in snaps if "step_00" in s)
    final = snaps[-1]
    gold = {t: load_gold_texts(eval_dir / "silver_gold" / FNAME_MAP[t]) for t in types}

    agg = {t: {"base": {"tp": 0, "fp": 0, "fn": 0},
               "dist": {"tp": 0, "fp": 0, "fn": 0}} for t in types}
    for pid in papers:
        b = parse_buckets(pid, tex_dir, types, eval_dir=Path(step00))
        d = parse_buckets(pid, tex_dir, types, eval_dir=Path(final))
        for t in types:
            g = gold[t].get(pid, [])
            mb = metrics(b[t], g, threshold); md = metrics(d[t], g, threshold)
            for k in ("tp", "fp", "fn"):
                agg[t]["base"][k] += mb[k]; agg[t]["dist"][k] += md[k]

    # Optional post-judge adjustment of the DISTILLED FPs only (base stays
    # raw — fp_judge only judges the final snapshot). A GENUINE verdict means
    # the silver gold missed a real instance, so that FP is removed; recall/
    # gold (and thus tp/fn) are unchanged.
    import csv as _csv
    from collections import Counter as _Counter
    fj = eval_dir / "fp_judge.csv"
    judged = fj.exists()
    rescued = (_Counter(r["type"] for r in _csv.DictReader(open(fj, encoding="utf-8"))
                        if r.get("verdict") == "GENUINE") if judged else _Counter())

    def _f1(tp, fp, fn):
        return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0

    rows = []
    for t in types:
        b, d = agg[t]["base"], agg[t]["dist"]
        tg = b["tp"] + b["fn"]
        if tg == 0:
            continue
        dfp = max(0, d["fp"] - rescued.get(t, 0))   # post-judge distilled FP
        rows.append((t, tg, _f1(b["tp"], b["fp"], b["fn"]),
                     _f1(d["tp"], dfp, d["fn"]),
                     b["fp"], dfp))
    rows.sort(key=lambda r: -r[1])
    dist_tag = " (post-judge)" if judged else ""

    labels = [r[0].replace("_", "\n") for r in rows]
    x = np.arange(len(rows)); w = 0.38
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.bar(x - w / 2, [r[2] for r in rows], w, label="F1 base parser",
           color="#9ecae1", edgecolor="#3182bd")
    ax.bar(x + w / 2, [r[3] for r in rows], w, label=f"F1 base+distilled{dist_tag}",
           color="#fdae6b", edgecolor="#e6550d")
    ax.set_ylabel("F1 score", fontsize=12); ax.set_ylim(0, 1.05)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_xlabel("structure type (n = gold count below)", fontsize=12)
    for i, r in enumerate(rows):
        ax.annotate(f"n={r[1]}", (i, -0.07), ha="center", va="top",
                    fontsize=7, color="gray", annotation_clip=False)
    ax2 = ax.twinx()
    ax2.set_ylabel("# False Positives", fontsize=12, color="#444")
    ax2.plot(x - w / 2, [r[4] for r in rows], "D", color="#3182bd", ms=8,
             label="FP base parser")
    ax2.plot(x + w / 2, [r[5] for r in rows], "X", color="#e6550d", ms=9,
             label=f"FP base+distilled{dist_tag}")
    maxfp = max((max(r[4], r[5]) for r in rows), default=1)
    ax2.set_ylim(0, maxfp * 1.25 or 1)
    for i, r in enumerate(rows):
        if r[4]:
            ax2.annotate(str(r[4]), (i - w / 2, r[4]), ha="center", va="bottom",
                         fontsize=7, color="#3182bd")
        if r[5]:
            ax2.annotate(str(r[5]), (i + w / 2, r[5]), ha="center", va="bottom",
                         fontsize=7, color="#e6550d")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=10, framealpha=0.95)
    _judge_note = ("; orange = post-judge (genuine-but-unlabeled FPs removed)"
                   if judged else "")
    ax.set_title(f"{eval_dir.name}: per-structure F1 and False Positives — "
                 f"base parser vs base+distilled\n(silver gold = Opus tier2, "
                 f"{len(papers)} papers, {match_metric} matching{_judge_note})",
                 fontsize=13)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out = eval_dir / "per_type_f1_fp.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    p = argparse.ArgumentParser(description="Per-structure F1/FP chart")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"])
    p.add_argument("--threshold", type=float, default=0.7)
    args = p.parse_args()
    out = build_chart(args.eval_dir, args.tex_dir, args.match_metric, args.threshold)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
