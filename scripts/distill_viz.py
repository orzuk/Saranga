#!/usr/bin/env python3
"""Visual diagnostics for a distillation run, driven by trajectory/scores.jsonl.

The trajectory table answers "what is the F1 at state N". These plots answer
the questions the table makes hard to see: which papers the rules are actually
helping, whether a gain is recall or a precision give-back, when a rule started
costing parse time, and how much of the corpus the method structurally cannot
reach.

Everything here is read-only and derived from files the run already writes:

    trajectory/scores.jsonl   per paper x per state x per mode (m1 + m3),
                              with per_type counts and parse_seconds
    iteration_log.json        per-paper cost / FNs / rules / LLM calls
    groups/*/prune_log.jsonl  per-rule TP/FP and keep/prune verdicts

Usage:
    python scripts/distill_viz.py --eval-dir <eval-dir>
    python scripts/distill_viz.py --eval-dir <dir> --mode m3 --out /tmp/plots
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

REPO = Path(__file__).resolve().parent.parent

# One palette, used consistently: blue = train, orange = held-out, and a
# diverging red/blue for "did this get better or worse".
C_TRAIN, C_HELD, C_BASE = "#2b6cb0", "#dd6b20", "#718096"
DIVERGE = LinearSegmentedColormap.from_list(
    "gain", ["#b2182b", "#f7f7f7", "#2166ac"])


# ---------------------------------------------------------------- loading ---

def load_scores(eval_dir: Path, mode: str):
    """{state: {paper: row}} plus the state order the run produced them in."""
    path = eval_dir / "trajectory" / "scores.jsonl"
    if not path.exists():
        raise SystemExit(f"no scores.jsonl under {eval_dir}")
    by_state, order = defaultdict(dict), []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue                      # partial last line from a killed run
        if r.get("mode") != mode:
            continue
        if r["state"] not in by_state:
            order.append(r["state"])
        by_state[r["state"]][r["paper_id"]] = r
    return by_state, order


def state_index(state: str) -> int:
    return 0 if state == "base" else int(re.sub(r"\D", "", state) or 0)


def prf(tp, tpr, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tpr / (tpr + fn) if tpr + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def pooled(rows):
    """Pooled P/R/F1 over a set of per-paper rows (micro, never macro)."""
    tp = sum(r["tp"] for r in rows)
    tpr = sum(r.get("tp_recall", r["tp"]) for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    return prf(tp, tpr, fp, fn)


def splits(eval_dir: Path):
    f = REPO / "corpus/silver/split_opus5.csv"
    if not f.exists():
        return {}
    return {r["arxiv_id"]: r["split"] for r in csv.DictReader(open(f, encoding="utf-8"))}


def env_markers(paper_id: str, tex_dir: Path) -> int:
    """How many theorem-ish LaTeX anchors the paper actually contains.

    The single best predictor of whether a regex student can reach a paper at
    all -- a paper with no \\begin{theorem}/\\newtheorem has nothing to anchor on.
    """
    d = tex_dir / paper_id / "source"
    if not d.is_dir():
        return -1
    pat = re.compile(r"\\begin\{(theorem|lemma|proposition|corollary|definition"
                     r"|proof|claim|remark|example|conjecture|problem)\*?\}"
                     r"|\\newtheorem\*?\{", re.I)
    n = 0
    for f in d.glob("*.tex"):
        n += len(pat.findall(f.read_text(encoding="utf-8", errors="replace")))
    return n


# ------------------------------------------------------------------ plots ---

def plot_curves(by_state, order, sp, out: Path):
    """The headline: pooled P/R/F1 for train and held-out at every state."""
    xs = [state_index(s) for s in order]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharex=True)
    for ax, idx, name in zip(axes, range(3), ("Precision", "Recall", "F1")):
        for grp, colour in (("train", C_TRAIN), ("test", C_HELD)):
            ys = [pooled([r for pid, r in by_state[s].items()
                          if sp.get(pid) == grp])[idx] for s in order]
            ax.plot(xs, ys, "o-", ms=3, color=colour,
                    label="train" if grp == "train" else "held-out")
        ax.axhline(pooled([r for pid, r in by_state[order[0]].items()
                           if sp.get(pid) == "test"])[idx],
                   color=C_BASE, ls=":", lw=1, label="held-out base")
        ax.set_title(name); ax.set_xlabel("papers distilled")
        ax.grid(alpha=.25)
    axes[0].legend(fontsize=8)
    fig.suptitle("Pooled metrics across the run "
                 "(precision and recall move in opposite directions — that is the story)",
                 fontsize=10)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_paper_heatmap(by_state, order, sp, out: Path):
    """Per-paper F1 CHANGE from base. Red = the rules made this paper worse.

    A mean hides this completely: a run can look flat while helping half the
    papers and hurting the other half.
    """
    train = [p for p in by_state[order[0]] if sp.get(p) == "train"]
    base = {p: by_state[order[0]][p]["f1"] for p in train}
    train.sort(key=lambda p: base[p])
    M = [[by_state[s].get(p, {}).get("f1", 0) - base[p] for s in order]
         for p in train]
    if not M:
        return
    lim = max(1e-6, max(abs(v) for row in M for v in row))
    fig, ax = plt.subplots(figsize=(1.0 + 0.34 * len(order), 0.26 * len(train) + 2))
    im = ax.imshow(M, cmap=DIVERGE, aspect="auto",
                   norm=TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim))
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([s.replace("after ", "") for s in order], fontsize=7)
    ax.set_yticks(range(len(train)))
    ax.set_yticklabels([f"{p}  ({base[p]:.2f})" for p in train], fontsize=6)
    # the diagonal: the state at which each paper was itself distilled
    for i, p in enumerate(train):
        for j, s in enumerate(order):
            if state_index(s) == train.index(p) + 1:
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1,
                                           fill=False, ec="black", lw=1.4))
    fig.colorbar(im, ax=ax, label="F1 change vs base")
    ax.set_title("Per-paper F1 change from base (boxed = paper distilled at that state)",
                 fontsize=10)
    ax.set_xlabel("papers distilled")
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_precision_recall_path(by_state, order, sp, out: Path):
    """Held-out P vs R as a trajectory. Shows the trade, not two curves."""
    fig, ax = plt.subplots(figsize=(6, 5.4))
    pts = [pooled([r for pid, r in by_state[s].items() if sp.get(pid) == "test"])
           for s in order]
    P = [p for p, _, _ in pts]; R = [r for _, r, _ in pts]
    ax.plot(R, P, "-", color=C_HELD, lw=1, alpha=.7)
    sc = ax.scatter(R, P, c=[state_index(s) for s in order],
                    cmap="viridis", zorder=3, s=45)
    for s, r, p in zip(order, R, P):
        if s == order[0] or s == order[-1] or state_index(s) % 10 == 0:
            ax.annotate(s, (r, p), fontsize=7,
                        xytext=(4, 4), textcoords="offset points")
    # iso-F1 contours, so "is this actually better" is readable at a glance
    import numpy as np
    rr = np.linspace(max(1e-3, min(R) * .9), max(R) * 1.1, 200)
    for f in (0.5, 0.55, 0.6, 0.65, 0.7):
        pp = f * rr / (2 * rr - f)
        ok = (pp > 0) & (pp <= 1)
        ax.plot(rr[ok], pp[ok], ":", color="#cbd5e0", lw=.9, zorder=0)
        if ok.any():
            ax.annotate(f"F1={f}", (rr[ok][-1], pp[ok][-1]), fontsize=6,
                        color="#a0aec0")
    fig.colorbar(sc, ax=ax, label="papers distilled")
    ax.set_xlabel("recall"); ax.set_ylabel("precision")
    ax.set_title("Held-out precision/recall path\n"
                 "moving right-and-down means recall bought with precision", fontsize=10)
    ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_type_contribution(by_state, order, sp, out: Path):
    """Per-type recall over the run. Makes a silently dead type obvious."""
    first, last = by_state[order[0]], by_state[order[-1]]
    types = sorted({t for r in first.values() for t in (r.get("per_type") or {})})
    if not types:
        return
    rows = []
    for t in types:
        def rec(state):
            tp = sum((r.get("per_type") or {}).get(t, {}).get("tp_recall", 0)
                     for pid, r in state.items() if sp.get(pid) == "test")
            fn = sum((r.get("per_type") or {}).get(t, {}).get("fn", 0)
                     for pid, r in state.items() if sp.get(pid) == "test")
            return tp / (tp + fn) if tp + fn else 0.0
        gold = sum((r.get("per_type") or {}).get(t, {}).get("n_gold", 0)
                   for pid, r in last.items() if sp.get(pid) == "test")
        rows.append((t, rec(first), rec(last), gold))
    rows.sort(key=lambda x: -x[3])
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(rows) + 2))
    y = range(len(rows))
    for i, (t, b, f, g) in enumerate(rows):
        ax.plot([b, f], [i, i], color="#cbd5e0", lw=3, zorder=1,
                solid_capstyle="round")
        ax.scatter([b], [i], color=C_BASE, s=34, zorder=2)
        ax.scatter([f], [i], color=C_TRAIN if f >= b else "#b2182b", s=34, zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{t}  (n={g})" for t, _, _, g in rows], fontsize=8)
    ax.set_xlabel("held-out recall")
    ax.set_title("Per-type held-out recall: base (grey) -> final (blue)\n"
                 "a type that does not move is a type the rules never learned",
                 fontsize=10)
    ax.grid(alpha=.25, axis="x")
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_reachability(by_state, order, tex_dir: Path, out: Path):
    """Final F1 vs number of LaTeX anchors. The method's structural ceiling.

    Papers with no theorem environments have nothing for a regex to anchor to,
    so they sit near zero no matter how much is distilled. Worth separating
    from papers the rules simply have not learned yet.
    """
    last = by_state[order[-1]]
    xs, ys = [], []
    for pid, r in last.items():
        n = env_markers(pid, tex_dir)
        if n < 0:
            continue
        xs.append(n); ys.append(r["f1"])
    if not xs:
        return
    fig, ax = plt.subplots(figsize=(7.6, 5))
    ax.scatter([x + .5 for x in xs], ys, s=22, alpha=.65, color=C_TRAIN,
               edgecolor="none")
    ax.set_xscale("log")
    zero = [y for x, y in zip(xs, ys) if x == 0]
    if zero:
        ax.axvspan(.4, .95, color="#b2182b", alpha=.10)
        ax.annotate(f"no anchors at all\n{len(zero)} papers, mean F1={st.mean(zero):.3f}",
                    (.55, max(.05, st.mean(zero) + .25)), fontsize=8, color="#b2182b")
    ax.set_xlabel("theorem-like LaTeX anchors in the paper (log, 0 shown at left)")
    ax.set_ylabel("final F1")
    ax.set_title("Structural reachability: what the student can and cannot see",
                 fontsize=10)
    ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_cost_and_time(eval_dir: Path, by_state, order, out: Path):
    """Cost per paper, FNs remaining, and parse time — the run's health strip.

    Parse time per state is the series that exposes an expensive rule the
    moment it lands, which no accuracy metric will show you.
    """
    log_p = eval_dir / "iteration_log.json"
    log = json.load(open(log_p, encoding="utf-8")) if log_p.exists() else []
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.8))

    if log:
        idx = [e["paper_idx"] for e in log]
        axes[0].bar(idx, [e["total_cost_usd"] for e in log], color=C_TRAIN)
        axes[0].set_title(f"cost / paper  (total ${sum(e['total_cost_usd'] for e in log):.2f})",
                          fontsize=10)
        axes[0].set_xlabel("paper"); axes[0].set_ylabel("USD")
        axes[1].plot(idx, [e["total_fns"] for e in log], "o-", ms=3, color=C_HELD)
        axes[1].set_title("false negatives found per paper\n(falling = student improving)",
                          fontsize=10)
        axes[1].set_xlabel("paper")
    for a in axes[:2]:
        a.grid(alpha=.25)

    secs = [(state_index(s),
             sum(r.get("parse_seconds") or 0 for r in by_state[s].values()))
            for s in order]
    if any(v for _, v in secs):
        axes[2].plot([x for x, _ in secs], [v for _, v in secs], "o-", ms=3,
                     color="#805ad5")
        axes[2].set_title("total parse time per scoring pass\n"
                          "(a jump = a slow rule just landed)", fontsize=10)
        axes[2].set_xlabel("papers distilled"); axes[2].set_ylabel("seconds")
        axes[2].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_rule_economy(eval_dir: Path, out: Path):
    """Every rule as TP vs FP, from the prune logs. Shows what pruning removed."""
    pts = []
    for f in sorted((eval_dir / "groups").glob("*/prune_log.jsonl")):
        last = None
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                last = line
        if not last:
            continue
        try:
            d = json.loads(last)
        except json.JSONDecodeError:
            continue
        for x in d.get("decisions", []):
            pts.append((f.parent.name, x.get("rule", "?"), x.get("tp", 0),
                        x.get("fp", 0), x.get("verdict", "?")))
    if not pts:
        return
    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    for keep, colour, label in ((True, C_TRAIN, "kept"), (False, "#b2182b", "pruned")):
        sel = [p for p in pts if (p[4] == "keep") == keep]
        if sel:
            ax.scatter([p[3] for p in sel], [p[2] for p in sel], s=42, alpha=.75,
                       color=colour, label=f"{label} ({len(sel)})", edgecolor="none")
    hi = max([p[2] for p in pts] + [p[3] for p in pts] + [1])
    ax.plot([0, hi], [0, hi], ":", color="#a0aec0", lw=1)
    ax.annotate("FDR = 0.5", (hi * .82, hi * .86), fontsize=7, color="#a0aec0")
    for g, name, tp, fp, v in sorted(pts, key=lambda p: -(p[3]))[:6]:
        ax.annotate(name[:24], (fp, tp), fontsize=6,
                    xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("false positives"); ax.set_ylabel("true positives")
    ax.set_title("Rule economy: what each distilled rule earned, and what pruning cut",
                 fontsize=10)
    ax.legend(fontsize=8); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


def plot_mode_gap(eval_dir: Path, sp, out: Path):
    """M1 vs M3 side by side. The gap is the nesting/labelling tax."""
    m1, o1 = load_scores(eval_dir, "m1")
    m3, _ = load_scores(eval_dir, "m3")
    if not m3:
        return
    xs = [state_index(s) for s in o1]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for by, colour, label in ((m1, C_TRAIN, "M1 (strict)"),
                              (m3, C_HELD, "M3 (nesting-tolerant)")):
        ys = [pooled([r for pid, r in by[s].items() if sp.get(pid) == "test"])[2]
              for s in o1 if s in by]
        ax.plot(xs[:len(ys)], ys, "o-", ms=3, color=colour, label=label)
    ys1 = [pooled([r for pid, r in m1[s].items() if sp.get(pid) == "test"])[2] for s in o1]
    ys3 = [pooled([r for pid, r in m3[s].items() if sp.get(pid) == "test"])[2]
           for s in o1 if s in m3]
    n = min(len(ys1), len(ys3))
    ax.fill_between(xs[:n], ys1[:n], ys3[:n], color="#cbd5e0", alpha=.5)
    ax.annotate("gap = false positives that are really\nnesting / granularity mismatches",
                (xs[n // 2], (ys1[n // 2] + ys3[n // 2]) / 2), fontsize=8,
                color="#4a5568")
    ax.set_xlabel("papers distilled"); ax.set_ylabel("held-out F1")
    ax.set_title("How much of the 'error' is a labelling convention?", fontsize=10)
    ax.legend(fontsize=8); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(out, dpi=140); plt.close(fig)


# ------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-dir", required=True, type=Path)
    ap.add_argument("--tex-dir", type=Path,
                    default=REPO / "corpus/silver/tex_staged")
    ap.add_argument("--mode", default="m1", choices=["m1", "m3"])
    ap.add_argument("--out", type=Path, default=None,
                    help="output dir (default <eval-dir>/plots)")
    args = ap.parse_args()

    eval_dir = args.eval_dir.resolve()
    out = args.out or eval_dir / "plots"
    out.mkdir(parents=True, exist_ok=True)

    by_state, order = load_scores(eval_dir, args.mode)
    if not order:
        raise SystemExit(f"no rows for mode={args.mode} in scores.jsonl")
    sp = splits(eval_dir)
    print(f"{len(order)} states x {len(by_state[order[0]])} papers, mode={args.mode}")

    jobs = [
        ("01_curves.png",        lambda p: plot_curves(by_state, order, sp, p)),
        ("02_paper_heatmap.png", lambda p: plot_paper_heatmap(by_state, order, sp, p)),
        ("03_pr_path.png",       lambda p: plot_precision_recall_path(by_state, order, sp, p)),
        ("04_per_type.png",      lambda p: plot_type_contribution(by_state, order, sp, p)),
        ("05_reachability.png",  lambda p: plot_reachability(by_state, order, args.tex_dir, p)),
        ("06_cost_time.png",     lambda p: plot_cost_and_time(eval_dir, by_state, order, p)),
        ("07_rule_economy.png",  lambda p: plot_rule_economy(eval_dir, p)),
        ("08_m1_vs_m3.png",      lambda p: plot_mode_gap(eval_dir, sp, p)),
    ]
    for name, fn in jobs:
        try:
            fn(out / name)
            print(f"  wrote {name}")
        except Exception as e:                 # one bad plot must not kill the set
            print(f"  [skip] {name}: {type(e).__name__}: {e}")
    print(f"\n{out}")


if __name__ == "__main__":
    main()
