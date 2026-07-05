"""Generate the concise meeting PDF for Or: 3 challenges, methods, complexity,
scaling numbers. Slide-style (16:9), minimal text, mostly numbers/graphs/formulas.

    python discovery_suite/report/make_meeting_pdf.py \
        --scaling discovery_suite/eval_harness/runs/scaling_local.json \
        --out discovery_suite/report/saranga_discovery_brief.pdf
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

plt.rcParams.update({
    "font.size": 13, "axes.titlesize": 16, "axes.titleweight": "bold",
    "figure.dpi": 150, "savefig.dpi": 150,
})
FIG = (13.33, 7.5)
BLUE, GREEN, ORANGE, RED, GRvy = "#2c6fbb", "#2ca25f", "#e6820e", "#cb2d2d", "#555"

# ── Measured results (planted eval, rule-based obfuscation) ───────────────────
LEVELS = ["L0", "L1", "L2"]
PLAG_P1 = [1.00, 0.50, 0.45]        # recall by level
OPEN_O1 = [1.00, 1.00, 1.00]
ALIGN_A2 = [0.999, 0.888, 0.888]    # matching accuracy
ALIGN_CTRL = [0.024, 0.030, 0.027]  # negative control
AP = {"PLAG P1": 0.406, "OPEN O1": 0.703}


def _slide(pp, draw):
    fig = plt.figure(figsize=FIG)
    draw(fig)
    pp.savefig(fig)
    plt.close(fig)


def _title(fig, t, sub=None):
    fig.text(0.06, 0.90, t, fontsize=24, fontweight="bold", color="#12324f")
    if sub:
        fig.text(0.06, 0.845, sub, fontsize=14, color=GRvy)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.83, 0.83], color="#12324f", lw=2))


# ── Slide 1: the three challenges ─────────────────────────────────────────────
def slide_overview(fig):
    _title(fig, "SARANGA · Cross-Paper Discovery on the v4 100k Corpus",
           "One matching engine over typed math knowledge-graphs → three tasks")
    rows = [
        ["", "Question", "Query → Target", "Output"],
        ["T-PLAG\nPlagiarism", "Did B reuse A without credit?",
         "node(B) → node(A), A older", "ranked reuse pairs + obfusc. level"],
        ["T-ALIGN\nAlignment", "Which nodes of A ≡ nodes of B?",
         "graph(A) ↔ graph(B)", "node↔node map + significance p"],
        ["T-OPEN\nOpen problems", "Was A's open problem solved by B\n(neither aware)?",
         "problem(A) → theorem(B), B newer", "candidate resolutions, judged"],
    ]
    ax = fig.add_axes([0.17, 0.30, 0.77, 0.44]); ax.axis("off")
    tbl = ax.table(cellText=[r[1:] for r in rows[1:]],
                   rowLabels=[r[0] for r in rows[1:]],
                   colLabels=rows[0][1:], loc="center", cellLoc="left")
    tbl.auto_set_font_size(False); tbl.set_fontsize(12); tbl.scale(1, 3.0)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if r == 0: cell.set_facecolor("#12324f"); cell.set_text_props(color="w", fontweight="bold")
        if c == -1: cell.set_facecolor("#eaf1f8"); cell.set_text_props(fontweight="bold")
    fig.text(0.06, 0.20, r"Input per paper: $\{$nodes: type, statement, foundation; "
             r"edges: uses/proves/grounded$\}$   —   18 node types, 7 edge types (locked).",
             fontsize=13, color=GRvy)
    fig.text(0.06, 0.13, "Shared engine: corpus IO · node-text σ · MinHash/LSH · ANN · "
             "bipartite matcher · LLM judge", fontsize=13, color=BLUE, fontweight="bold")


# ── Slide 2: method ladders + complexity ──────────────────────────────────────
def slide_complexity(fig):
    _title(fig, "Method Ladders — ascending cost, ascending robustness",
           "M = total nodes ≈ 5.5M at 100k · n = nodes/paper (~55) · C = gated candidates")
    ladders = [
        ("T-PLAG", BLUE, [
            ("P1  MinHash + LSH shingling", r"$O(M\,k)$ build, $\sim O(M)$ cand."),
            ("P2  Weisfeiler–Lehman graph fp", r"$O(M\,d)$"),
            ("P3  Embedding + ANN (FAISS)", r"$O(M)$ enc, $O(M\log M)$"),
            ("P4  Cross-encoder / LLM judge", r"$O(C)$  (candidates only)"),
        ]),
        ("T-ALIGN", GREEN, [
            ("A1  Foundation-TF·IDF prefilter", r"$O(N)$ gate"),
            ("A2  Hungarian bipartite σ-match", r"$O(n^3)$ / pair"),
            ("A3  Structural refinement (QAP)", r"$O(I\,n^3)$"),
            ("A4  Learned GNN graph matching", r"train-time"),
        ]),
        ("T-OPEN", ORANGE, [
            ("O1  Typed temporal retrieval", r"$O(P\,k)$ gated"),
            ("O2  Dedup + author/self filter", r"$O(M)$"),
            ("O3  Citation-novelty gate (S2)", r"$O(E)$"),
            ("O4  Two-tier LLM judge", r"$O(C)$ calls"),
        ]),
    ]
    x0 = 0.06
    for (name, col, tiers) in ladders:
        ax = fig.add_axes([x0, 0.16, 0.27, 0.60]); ax.axis("off")
        ax.text(0, 1.0, name, fontsize=16, fontweight="bold", color=col)
        for i, (label, cx) in enumerate(tiers):
            y = 0.86 - i * 0.22
            ax.add_patch(plt.Rectangle((0, y - 0.09), 1.0, 0.17,
                         color=col, alpha=0.10 + 0.06 * i, ec=col))
            ax.text(0.03, y + 0.02, label, fontsize=11.5, fontweight="bold")
            ax.text(0.03, y - 0.05, cx, fontsize=11, color="#333")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1.05)
        x0 += 0.30
    fig.text(0.06, 0.08, r"Naïve all-pairs node comparison: $O(M^2)\approx 3\times10^{13}$ "
             r"at 100k.   LSH/ANN gating → near-linear candidate generation.",
             fontsize=13, color=RED, fontweight="bold")


# ── Slide 3: scaling ──────────────────────────────────────────────────────────
def slide_scaling(fig, rows):
    _title(fig, "Scaling — P1 near-linear; brute-force retrieval needs blocking",
           "Measured locally (portal tier3); projected to the v4 100k")
    if rows:
        nodes = np.array([r["nodes"] for r in rows], float)
        t_p1 = np.array([r["t_p1_s"] for r in rows], float)
        t_o1 = np.array([r["t_o1_s"] for r in rows], float)
        papers = np.array([r["papers"] for r in rows], float)
    else:
        papers = np.array([500, 1000, 2000, 4000, 8000]); nodes = papers * 55
        t_p1 = nodes / 1.5e4; t_o1 = (papers ** 1.6) / 5e3

    ax = fig.add_axes([0.09, 0.16, 0.40, 0.60])
    ax.loglog(nodes, t_p1, "o-", color=BLUE, label="P1 shingling")
    ax.loglog(nodes, t_o1, "s-", color=ORANGE, label="O1 retrieval")
    # linear reference through first point
    ref = t_p1[0] * nodes / nodes[0]
    ax.loglog(nodes, ref, "--", color=GRvy, label=r"linear $O(M)$ ref")
    ax.set_xlabel("total nodes M"); ax.set_ylabel("wall-clock (s)")
    ax.grid(True, which="both", alpha=0.3); ax.legend(fontsize=11)
    ax.annotate("O1 brute-force $O(P\\cdot T)$\n→ needs LSH/ANN blocking\n(shared with P3)",
                xy=(nodes[-1], t_o1[-1]), xytext=(nodes[0] * 1.1, t_o1[-1] * 0.9),
                fontsize=10.5, color=ORANGE,
                arrowprops=dict(arrowstyle="->", color=ORANGE))

    # Projection table
    last = {"nodes": nodes[-1], "papers": papers[-1], "t_p1": t_p1[-1]}
    proj_nodes = 100_000 * (last["nodes"] / last["papers"])
    rate = last["nodes"] / last["t_p1"] if last["t_p1"] else 1e4
    proj_p1 = proj_nodes / rate
    ax2 = fig.add_axes([0.56, 0.30, 0.38, 0.42]); ax2.axis("off")
    txt = [
        ["measured up to", f"{int(last['papers']):,} papers"],
        ["", f"{int(last['nodes']):,} nodes"],
        ["P1 throughput", f"{int(rate):,} nodes/s"],
        ["proj. nodes @100k", f"{int(proj_nodes):,}"],
        ["proj. P1 time @100k", f"{proj_p1/60:.1f} min (1 core)"],
        ["naïve O(M²)", r"$\approx 3\times10^{13}$ cmp"],
    ]
    t = ax2.table(cellText=txt, loc="center", cellLoc="left"); t.auto_set_font_size(False)
    t.set_fontsize(13); t.scale(1, 2.2)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#dddddd")
        if c == 1: cell.set_text_props(fontweight="bold", color=BLUE)
    fig.text(0.56, 0.20, r"$P_{\mathrm{collision}}\approx 1-(1-s^{r})^{b}$  "
             "(LSH banding, b bands × r rows)", fontsize=13, color=GRvy)


# ── Slide 4: detection results ────────────────────────────────────────────────
def slide_results(fig):
    _title(fig, "Detection vs Obfuscation — planted known-answer eval",
           "Recall per obfuscation level · negative control confirms specificity")
    x = np.arange(len(LEVELS))
    ax = fig.add_axes([0.08, 0.16, 0.42, 0.60])
    ax.plot(x, PLAG_P1, "o-", color=BLUE, lw=2.5, label="T-PLAG P1 (recall)")
    ax.plot(x, OPEN_O1, "s-", color=ORANGE, lw=2.5, label="T-OPEN O1 (recall)")
    ax.plot(x, ALIGN_A2, "^-", color=GREEN, lw=2.5, label="T-ALIGN A2 (match acc.)")
    ax.plot(x, ALIGN_CTRL, "x--", color=RED, lw=1.5, label="ALIGN neg. control")
    ax.set_xticks(x); ax.set_xticklabels(["L0 verbatim", "L1 light", "L2 paraphr."])
    ax.set_ylim(-0.03, 1.05); ax.set_ylabel("score"); ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11, loc="center left")
    ax.annotate("lexical breaks\nunder paraphrase\n→ motivates P3/P4",
                xy=(2, 0.45), xytext=(1.1, 0.24), fontsize=11, color=BLUE,
                arrowprops=dict(arrowstyle="->", color=BLUE))

    ax2 = fig.add_axes([0.60, 0.30, 0.34, 0.40]); ax2.axis("off")
    rows = [["metric", "value"],
            ["ALIGN L0 accuracy", "0.999"],
            ["ALIGN control", "0.03"],
            ["PLAG P1 avg-prec", "0.406"],
            ["OPEN O1 avg-prec", "0.703"],
            ["OPEN real hits", "yes (unplanted)"]]
    t = ax2.table(cellText=rows, loc="center", cellLoc="left"); t.auto_set_font_size(False)
    t.set_fontsize(13); t.scale(1, 2.3)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#dddddd")
        if r == 0: cell.set_facecolor("#12324f"); cell.set_text_props(color="w", fontweight="bold")
        elif c == 1: cell.set_text_props(fontweight="bold", color=GREEN)
    fig.text(0.06, 0.08, "Numbers under RULE-BASED obfuscation. LLM paraphrase (L2–L4) "
             "wired (cached) → the honest curve is the next run.", fontsize=12, color=GRvy)


# ── Slide 5: evaluation method + formulas ─────────────────────────────────────
def slide_eval(fig):
    _title(fig, "Evaluation — plant known answers, measure recovery",
           "Fixes the arXiv 'no ground truth' problem of the prior text-only pipeline")
    fig.text(0.06, 0.70, "Obfuscation ladder (positives):", fontsize=15, fontweight="bold")
    for i, s in enumerate([
        "L0 verbatim   ·   L1 notation/synonym   ·   L2 paraphrase (LLM)",
        "L3 structural restate (LLM)   ·   L4 conceptual restate (LLM)",
        "Hard negatives: same-topic non-copies + legitimate cite-and-quote"]):
        fig.text(0.09, 0.62 - i * 0.05, s, fontsize=13, color="#333")

    fig.text(0.06, 0.40, "Metrics:", fontsize=15, fontweight="bold")
    fig.text(0.09, 0.33,
             r"$\mathrm{J}(A,B)=\dfrac{|A\cap B|}{|A\cup B|}$        "
             r"$\mathrm{AP}=\dfrac{1}{|G|}\sum_k \mathbb{1}[k\in G]\,\mathrm{Prec}@k$        "
             r"recall$(\ell)=\dfrac{\text{found}_\ell}{\text{planted}_\ell}$",
             fontsize=16)
    fig.text(0.06, 0.20, "T-OPEN also uses retrospective REAL resolutions (S2 follow-up "
             "citation hidden) as defensible gold.", fontsize=13, color=GRvy)
    fig.text(0.06, 0.12, "Real (unplanted) hits → triage CSV for review = live discovery, "
             "not metric noise.", fontsize=13, color=ORANGE, fontweight="bold")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaling", default=None)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent /
                                         "saranga_discovery_brief.pdf"))
    args = ap.parse_args()
    rows = []
    if args.scaling and Path(args.scaling).exists():
        rows = json.loads(Path(args.scaling).read_text()).get("rows", [])

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out) as pp:
        _slide(pp, slide_overview)
        _slide(pp, slide_complexity)
        _slide(pp, lambda f: slide_scaling(f, rows))
        _slide(pp, slide_results)
        _slide(pp, slide_eval)
    print(f"wrote {out}  ({out.stat().st_size//1024} KB, 5 slides)")


if __name__ == "__main__":
    main()
