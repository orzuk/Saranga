#!/usr/bin/env python3
"""Figures and LaTeX tables from a distiller comparison (compare_distillers.py).

Reads <out>/results/ (metrics.csv, trajectory.csv, summary.json) and the
config, and writes

  results/figures/curve_effort.pdf|png   headline F1 against teacher calls and
                                         against dollars, per trained arm, one
                                         curve per training snapshot, with the
                                         base parser and the fixed arms as lines
  results/figures/curve_papers.pdf|png   final headline F1 against the number
                                         of training papers, per family of arms
                                         that differ only in that (repeats as
                                         separate points)
  results/tables/headline.tex            per arm: rules, P / R / F1 [95% CI],
                                         F1 - reference [paired CI], the other
                                         metrics' F1, teacher calls and cost,
                                         parse time per paper
  results/tables/strata.tex              headline F1 by stratum (env / prose / other)

The headline metric is the config's first ("metrics"); --split picks the
evaluation split (test by default).

    python scripts/plot_compare.py --config scripts/compare_configs/v6.json [--arms a,b]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import compare_distillers as C                       # noqa: E402


def rows(path: Path) -> list:
    return list(csv.DictReader(open(path, encoding="utf-8"))) if path.is_file() else []


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def family(arm: dict) -> str:
    """Arms that differ only in their number of training papers (or are repeats)."""
    return json.dumps([arm["alg"], arm.get("model"), arm.get("args", {})], sort_keys=True)


def n_train(cfg, arm) -> int:
    return len(C.train_papers(cfg, arm))


def label(name: str, arm: dict) -> str:
    return arm.get("label") or name


def curve_effort(cfg, traj, refs, arms, split, metric, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    by = defaultdict(list)
    for r in traj:
        if r["split"] == split and r["mode"] == metric and r["arm"] in arms:
            by[r["arm"]].append(r)
    for ax, x, xl in ((axes[0], "llm_calls", "teacher calls"), (axes[1], "cost_usd", "teacher cost (USD)")):
        for name, rs in sorted(by.items()):
            pts = sorted((num(r[x]) or 0.0, float(r["f1"])) for r in rs)
            ax.plot([p for p, _ in pts], [f for _, f in pts], marker=".", lw=1.2,
                    label=label(name, cfg["arms"][name]))
        for name, f1 in refs.items():
            ax.axhline(f1, ls="--", lw=0.9, color="grey" if name == "base" else None)
            ax.annotate(label(name, cfg["arms"][name]), (ax.get_xlim()[1], f1), fontsize=7,
                        ha="right", va="bottom")
        ax.set_xlabel(xl)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel(f"{split} F$_1$ ({metric})")
    axes[0].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(out / f"curve_effort.{ext}", dpi=200)
    plt.close(fig)


def curve_papers(cfg, final, refs, arms, split, metric, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fams = defaultdict(list)
    for name in arms:
        arm = cfg["arms"][name]
        if arm["alg"] in ("units", "merged") and (name, split, metric) in final:
            fams[family(arm)].append((n_train(cfg, arm), final[(name, split, metric)], name))
    fams = {k: v for k, v in fams.items() if len({n for n, _, _ in v}) > 1}
    if not fams:
        return
    fig, ax = plt.subplots(figsize=(5, 3.6))
    for k, pts in fams.items():
        pts.sort()
        names = sorted(n for _, _, n in pts)
        lab = min(names, key=len)
        ax.scatter([n for n, _, _ in pts], [f for _, f, _ in pts], s=18)
        means = defaultdict(list)
        for n, f, _ in pts:
            means[n].append(f)
        xs = sorted(means)
        ax.plot(xs, [sum(means[x]) / len(means[x]) for x in xs], lw=1.2, label=lab)
    for name, f1 in refs.items():
        ax.axhline(f1, ls="--", lw=0.9, color="grey" if name == "base" else None)
        ax.annotate(label(name, cfg["arms"][name]), (ax.get_xlim()[0], f1), fontsize=7,
                    ha="left", va="bottom")
    ax.set_xlabel("training papers")
    ax.set_ylabel(f"{split} F$_1$ ({metric})")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(out / f"curve_papers.{ext}", dpi=200)
    plt.close(fig)


def tex_escape(s: str) -> str:
    return s.replace("_", "\\_")


def tables(cfg, metrics, deltas, summary, arms, split, out: Path) -> None:
    head, others = cfg["metrics"][0], cfg["metrics"][1:]
    ref = cfg.get("reference_arm", "base")
    idx = {(m["arm"], m["split"], m["mode"], m["stratum"], m["type"]): m for m in metrics}
    dix = {(d["arm"], d["split"], d["mode"], d["stratum"]): d for d in deltas}
    meta = summary.get("arms", {})
    rt = {r["arm"]: r for r in summary.get("runtime", [])}
    cols = ["Arm", "Rules", f"P / R / F$_1$ [95\\% CI]", f"$\\Delta$F$_1$ vs {tex_escape(ref)}"] + \
        [f"{o} F$_1$" for o in others] + ["Calls", "USD", "s/paper"]
    lines = ["\\begin{tabular}{@{}l" + "r" * (len(cols) - 1) + "@{}}", "\\toprule",
             " & ".join(cols) + " \\\\", "\\midrule"]
    for a in arms:
        h = idx.get((a, split, head, "all", "all"))
        if not h:
            continue
        d = dix.get((a, split, head, "all"))
        m = meta.get(a, {})
        cells = [tex_escape(a), str(m.get("n_rules") or "--"),
                 f"{float(h['precision']):.3f} / {float(h['recall']):.3f} / \\textbf{{{float(h['f1']):.3f}}} "
                 f"[{float(h.get('f1_lo') or 0):.3f}, {float(h.get('f1_hi') or 0):.3f}]",
                 (f"{float(d['delta_f1']):+.3f} [{float(d['delta_lo']):+.3f}, {float(d['delta_hi']):+.3f}]"
                  if d else "--")]
        cells += [f"{float(idx[(a, split, o, 'all', 'all')]['f1']):.3f}"
                  if (a, split, o, "all", "all") in idx else "--" for o in others]
        cells += [str(m.get("llm_calls") or "--"),
                  f"{m['cost_usd']:.2f}" if m.get("cost_usd") else "--",
                  f"{float(rt[a]['seconds_per_paper']):.2f}" if a in rt else "--"]
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (out / "headline.tex").write_text(
        f"% {split} split, headline metric {head}; generated by scripts/plot_compare.py\n"
        + "\n".join(lines) + "\n", encoding="utf-8")

    lines = ["\\begin{tabular}{@{}lrrr@{}}", "\\toprule",
             "Arm & environments & prose & other \\\\", "\\midrule"]
    for a in arms:
        cells = [tex_escape(a)]
        for st in ("env", "prose", "other"):
            h = idx.get((a, split, head, st, "all"))
            cells.append(f"{float(h['f1']):.3f}" if h else "--")
        if len(cells) > 1 and any(c != "--" for c in cells[1:]):
            lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (out / "strata.tex").write_text(
        f"% {split} split, {head} F1 by stratum; generated by scripts/plot_compare.py\n"
        + "\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--arms", default="", help="comma list; default every arm with results")
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    cfg = C.load_config(args.config)
    res = cfg["out"] / "results"
    metric = cfg["metrics"][0]
    metrics, traj, deltas = rows(res / "metrics.csv"), rows(res / "trajectory.csv"), rows(res / "deltas.csv")
    summary = json.load(open(res / "summary.json", encoding="utf-8")) if (res / "summary.json").is_file() else {}
    have = {m["arm"] for m in metrics}
    arms = [a for a in (args.arms.split(",") if args.arms else cfg["arms"]) if a in have]
    final = {(m["arm"], m["split"], m["mode"]): float(m["f1"]) for m in metrics
             if m["stratum"] == "all" and m["type"] == "all"}
    trained = [a for a in arms if cfg["arms"][a]["alg"] in ("units", "merged")]
    refs = {a: final[(a, args.split, metric)] for a in arms
            if cfg["arms"][a]["alg"] in ("none", "fixed") and (a, args.split, metric) in final}
    figs, tabs = res / "figures", res / "tables"
    figs.mkdir(parents=True, exist_ok=True)
    tabs.mkdir(parents=True, exist_ok=True)
    curve_effort(cfg, traj, refs, trained, args.split, metric, figs)
    curve_papers(cfg, final, refs, trained, args.split, metric, figs)
    tables(cfg, metrics, deltas, summary, arms, args.split, tabs)
    print(f"[plot] figures in {figs}, tables in {tabs}")


if __name__ == "__main__":
    main()
