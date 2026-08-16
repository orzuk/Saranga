"""Plain-language meeting brief: teaching a computer to match MEANING, not words.

Written to be understood by someone who has not seen the code. Every technical
term is either avoided or explained on the slide where it first appears. Jargon
that is banned here on purpose: bi-encoder, GEMM, RRF, fp16, shard, map-reduce,
canonicalization, average precision, cross-encoder, ANN. Where the underlying
idea matters, it is explained in words instead.

    python discovery_suite/report/make_semantic_pdf.py

Provenance rules for every number on these slides:
    MEASURED   observed on the cluster (L40S GPU — the 2,000-paper benchmark
               slice for the ablation, the full 100k corpus for the run itself)
    EARLIER    from the previous word-matching run on the 100k corpus
    STATUS     where a thread stands as of the date on the chip, not a result
The full 100,000-paper run IS done (MiniLM only, Aug 2026); the stronger model
roster is not. The Erdős arm's word-matching pass is done, its meaning-matching
pass is running.
"""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update({
    "font.size": 13, "axes.titlesize": 15, "axes.titleweight": "bold",
    "figure.dpi": 150, "savefig.dpi": 150,
})
FIG = (13.33, 7.5)
BLUE, GREEN, ORANGE, RED, GREY = "#2c6fbb", "#2ca25f", "#e6820e", "#cb2d2d", "#555"
NAVY, PURPLE, LIGHT = "#12324f", "#7b4fa8", "#8a8a8a"


# ── scaffolding ──────────────────────────────────────────────────────────────

#: Which section each slide belongs to, as (first, last, label) over 1-based
#: slide numbers. The deck covers three unrelated threads and readers lose track
#: of which one they are in; a faded eyebrow re-orients them without competing
#: with the title.
_SECTIONS = [
    (1, 12, "OPEN PROBLEM TASK"),
    (13, 14, "DISTILLATION METRICS"),
    (15, 17, "ERDŐS TASK"),
]


def _section_of(n: int) -> str:
    for lo, hi, label in _SECTIONS:
        if lo <= n <= hi:
            return label
    return ""


def _eyebrow(fig, n: int) -> None:
    """Faded section label + hairline above the title."""
    label = _section_of(n)
    if not label:
        return
    # matplotlib has no letter-spacing; padding with thin spaces fakes the
    # tracked-out look this sits best at.
    fig.text(0.06, 0.952, " ".join(label), fontsize=8.6, fontweight="bold",
             color="#c3ccd6")
    fig.text(0.94, 0.952, f"{n}/{_SECTIONS[-1][1]}", fontsize=8.6,
             color="#d3dae1", ha="right")
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.942, 0.942],
                              color="#e6ebef", lw=1))


def _slide(pp, draw, notes=None):
    fig = plt.figure(figsize=FIG)
    _slide.n = getattr(_slide, "n", 0) + 1
    draw(fig)
    _eyebrow(fig, _slide.n)
    if notes:
        _notes(fig, notes)
    pp.savefig(fig)
    plt.close(fig)


def _title(fig, t, sub=None):
    fig.text(0.06, 0.905, t, fontsize=24, fontweight="bold", color=NAVY)
    if sub:
        fig.text(0.06, 0.848, sub, fontsize=14, color=GREY)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.828, 0.828], color=NAVY, lw=2))


def _notes(fig, text):
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.135, 0.135], color="#c9c9c9", lw=1))
    fig.text(0.06, 0.108, "▶ SAY", fontsize=10.5, fontweight="bold", color="#a3a3a3")
    fig.text(0.115, 0.117, textwrap.fill(text, width=130), fontsize=10.8,
             color=GREY, va="top")


def _chip(fig, x, y, text, color):
    fig.text(x, y, text, fontsize=9.5, fontweight="bold", color="w",
             bbox=dict(boxstyle="round,pad=0.34", fc=color, ec="none"))


def _panel(fig, x, y, w, h, color, alpha=0.075):
    ax = fig.add_axes([x, y, w, h]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.004, 0.004), 0.992, 0.992,
                                boxstyle="round,pad=0.004,rounding_size=0.02",
                                fc=color, alpha=alpha, ec=color, lw=1.5))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return ax


def _paper_card(ax, x, y, w, h, year, title, body, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.03",
                                fc="white", ec=color, lw=2))
    ax.text(x + 0.03, y + h - 0.09, year, fontsize=11, fontweight="bold", color=color)
    ax.text(x + 0.03, y + h - 0.22, title, fontsize=12.5, fontweight="bold", color=NAVY)
    ax.text(x + 0.03, y + h - 0.36, body, fontsize=11.5, va="top", color="#333")


# ── 1. what we are trying to do ──────────────────────────────────────────────
def slide_goal(fig):
    _title(fig, "What we are trying to find",
           "An old paper asks a question. A later paper answers it — and nobody noticed.")

    ax = fig.add_axes([0.06, 0.40, 0.88, 0.38]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    _paper_card(ax, 0.00, 0.30, 0.36, 0.62, "PAPER A   ·   2015", "states an open problem",
                "“It remains unknown whether\nevery 3-connected cubic graph\nhas a Hamiltonian cycle.”", BLUE)
    _paper_card(ax, 0.55, 0.30, 0.36, 0.62, "PAPER B   ·   2019", "proves a theorem",
                "“Such graphs always contain\na closed walk visiting every\nvertex exactly once.”", GREEN)

    ax.annotate("", xy=(0.545, 0.61), xytext=(0.365, 0.61),
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=3))
    ax.text(0.455, 0.68, "same statement", ha="center", fontsize=12.5,
            fontweight="bold", color=ORANGE)
    ax.text(0.455, 0.50, "different words", ha="center", fontsize=12.5,
            fontweight="bold", color=ORANGE)
    ax.text(0.455, 0.36, "B never cites A", ha="center", fontsize=11, color=GREY, style="italic")

    fig.text(0.06, 0.335, "If neither author knows, the answer exists but nobody has connected it.",
             fontsize=15.5, fontweight="bold", color=NAVY)
    fig.text(0.06, 0.275,
             "Finding those connections automatically, across all of arXiv, is the goal. Our papers are already stored as a\n"
             "typed knowledge graph — nodes are theorems / definitions / open problems, edges are uses / proves / grounded_to —\n"
             "so the machine can compare a question node in one paper against every theorem node in every later paper.",
             fontsize=12.5, color=GREY, va="top")


# ── 2. where we are today ────────────────────────────────────────────────────
def slide_today(fig):
    _title(fig, "What we did so far — and why it stalled",
           "We matched by counting shared words  (lexical retrieval — token Jaccard).  It only finds near-copies.")

    ax = fig.add_axes([0.06, 0.505, 0.88, 0.27]); ax.axis("off")
    stages = [
        ("15,143", "open questions\n(query nodes)", BLUE),
        ("1,589,327", "theorems they could\nbe checked against", BLUE),
        ("300,204", "pairs sharing enough\nwords (Jaccard ≥ 0.10)", ORANGE),
        ("166", "judged by the LLM\n(Claude Opus)", RED),
    ]
    for i, (big, small, col) in enumerate(stages):
        x = i * 0.25
        ax.add_patch(FancyBboxPatch((x, 0.10), 0.215, 0.82,
                                    boxstyle="round,pad=0.006,rounding_size=0.04",
                                    fc=col, alpha=0.12, ec=col, lw=1.6))
        ax.text(x + 0.107, 0.66, big, ha="center", fontsize=17, fontweight="bold", color=col)
        ax.text(x + 0.107, 0.33, small, ha="center", fontsize=10.5, color=GREY)
        if i < 3:
            ax.annotate("", xy=(x + 0.246, 0.51), xytext=(x + 0.220, 0.51),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, lw=2))
    ax.set_xlim(-0.005, 1.0); ax.set_ylim(0, 1)

    a = _panel(fig, 0.06, 0.20, 0.42, 0.265, RED)
    a.text(0.04, 0.87, "The verdict on those 166", fontsize=13, fontweight="bold", color=RED)
    a.text(0.04, 0.63, "7", fontsize=22, fontweight="bold", color=RED)
    a.text(0.11, 0.66, "were genuine solutions", fontsize=12, va="center")
    a.text(0.04, 0.32, "0", fontsize=22, fontweight="bold", color=RED)
    a.text(0.11, 0.35, "were new discoveries — in every\ncase the later paper already\ncited the earlier one",
           fontsize=11.5, va="center", color="#333")

    b = _panel(fig, 0.52, 0.20, 0.42, 0.265, ORANGE)
    b.text(0.04, 0.87, "Why: counting words is literal", fontsize=13, fontweight="bold", color=ORANGE)
    b.text(0.04, 0.62, "“the cat sat on the mat”", fontsize=12, family="monospace", color=NAVY)
    b.text(0.04, 0.44, "“the cat sat on a mat”", fontsize=12, family="monospace", color=GREEN)
    b.text(0.66, 0.44, "✓ found", fontsize=12, color=GREEN, fontweight="bold")
    b.text(0.04, 0.20, "“the feline rested on the rug”", fontsize=12, family="monospace", color=RED)
    b.text(0.66, 0.20, "✗ missed", fontsize=12, color=RED, fontweight="bold")

    fig.text(0.06, 0.192,
             "So we are only ever finding rephrased copies — never a genuinely new connection.\n"
             "The bottleneck is the FIRST step, not the AI's judgement at the end.",
             fontsize=12.5, color=NAVY, fontweight="bold", va="top")
    _chip(fig, 0.80, 0.905, "EARLIER RUN · 100k papers", BLUE)


# ── 3. the idea ──────────────────────────────────────────────────────────────
def slide_idea(fig):
    _title(fig, "The idea: compare meaning instead of words",
           "Semantic (dense) retrieval — an EMBEDDING MODEL turns each statement into a point in high-dimensional space")

    # Axes box is 6.67in x 3.75in; matching the data ranges to that ratio makes
    # plt.Circle draw as an actual circle instead of a flat ellipse.
    ax = fig.add_axes([0.06, 0.235, 0.50, 0.50])
    ax.set_xlim(0, 16); ax.set_ylim(0, 9)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#dddddd")
    ax.set_title("embedding space   (really 384–2560 dimensions; drawn here as 2)",
                 fontsize=11.5, color=GREY, pad=8)

    qx, qy = 5.6, 5.0
    # word counting only reaches near-copies; meaning reaches the reworded one too
    ax.add_patch(plt.Circle((qx, qy), 1.7, fill=False, ec=ORANGE, lw=2, ls="--", zorder=2))
    ax.add_patch(plt.Circle((qx, qy), 3.2, fill=False, ec=GREEN, lw=2.2, zorder=2))

    # Labels are parked around the edges with leader lines so none of them sits
    # on top of a circle, a point, or each other.
    pts = [
        (qx, qy, BLUE, "the open question\nfrom paper A", (0.4, 6.9), True),
        (6.9, 5.9, GREEN, "a near-copy of it", (11.4, 6.9), True),
        (3.7, 3.4, GREEN, "the same idea,\nreworded", (0.4, 1.2), True),
        (13.2, 2.0, GREY, "an unrelated theorem\nabout matrices", (13.0, 3.6), False),
    ]
    for x, y, col, lab, (lx, ly), leader in pts:
        ax.plot(x, y, "o", ms=13, color=col, zorder=6)
        if leader:
            ax.annotate(lab, xy=(x, y), xytext=(lx, ly), fontsize=10.3,
                        ha="left", va="center", color="#333",
                        arrowprops=dict(arrowstyle="-", color="#c4c4c4", lw=1,
                                        shrinkA=2, shrinkB=9))
        else:
            ax.text(lx, ly, lab, fontsize=10.3, ha="center", color="#333")
    ax.text(qx, qy - 2.45, "lexical match\nreaches only here", fontsize=9.8,
            color=ORANGE, ha="center", va="center", fontweight="bold", zorder=7)
    ax.text(qx, qy + 3.55, "nearest neighbours in embedding space", fontsize=9.8,
            color=GREEN, ha="center", va="center", fontweight="bold", zorder=7)

    p = _panel(fig, 0.60, 0.50, 0.34, 0.28, BLUE)
    p.text(0.05, 0.88, "What an embedding model does", fontsize=13, fontweight="bold", color=BLUE)
    p.text(0.05, 0.69,
           "It reads a sentence and outputs a\nvector — a list of a few hundred to a\n"
           "few thousand numbers.\n\n"
           "Sentences that MEAN the same thing\nget vectors pointing the same way\n"
           "(high cosine similarity), even with\nno words in common.",
           fontsize=11, va="top", color="#333")

    q = _panel(fig, 0.60, 0.235, 0.34, 0.235, GREEN)
    q.text(0.05, 0.87, "Why this should help us", fontsize=13, fontweight="bold", color=GREEN)
    q.text(0.05, 0.66,
           "A solution written in a different\nsubfield's vocabulary now lands near\n"
           "the question it answers — exactly\nthe case lexical matching cannot see.",
           fontsize=11, va="top", color="#333")

    fig.text(0.06, 0.185,
             "These are open-weight embedding models (bi-encoders) from HuggingFace — free, and hosted on the lab's GPUs.",
             fontsize=12, color=NAVY, fontweight="bold")


# ── 4. the toolbox ───────────────────────────────────────────────────────────
def slide_tools(fig):
    _title(fig, "The tools — six embedding models (bi-encoders), compared",
           "Nobody knows in advance which embedding model understands mathematics best, so we benchmark all of them")

    rows = [
        ["MiniLM", "all-MiniLM-L6-v2", "22M · 384-d", "laptop", "The cheap baseline. CPU-viable — runs on Yaron's Mac."],
        ["DistilBERT", "distilbert-base-uncased", "66M · 768-d", "GPU", "Raw BERT, mean-pooled, NOT sentence-tuned. The naive baseline."],
        ["SPECTER2", "allenai/specter2_base", "110M · 768-d", "GPU", "Trained on scientific papers + citation signal."],
        ["BGE-M3", "BAAI/bge-m3", "568M · 1024-d", "GPU", "Strong general retriever. 8k-token context window."],
        ["Qwen3-Embed", "Qwen/Qwen3-Embedding-0.6B", "0.6B · 1024-d", "GPU", "Instruction-aware: query and document encoded asymmetrically."],
        ["Qwen3-Embed", "Qwen/Qwen3-Embedding-4B", "4B · 2560-d", "GPU", "The ceiling. Benchmark-only unless it wins outright."],
    ]
    ax = fig.add_axes([0.06, 0.415, 0.88, 0.36]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    heads = ["model", "size · vector dim", "runs on", "why it is in the comparison"]
    xs = [0.005, 0.215, 0.325, 0.405]
    ax.add_patch(plt.Rectangle((0, 0.885), 1, 0.115, fc=NAVY))
    for h, x in zip(heads, [xs[0], xs[1], xs[2], xs[3]]):
        ax.text(x + 0.008, 0.943, h, fontsize=10.5, fontweight="bold", color="w", va="center")
    for i, (name, hf, size, dev, why) in enumerate(rows):
        y = 0.885 - (i + 1) * 0.1475
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0, y), 1, 0.1475, fc="#f2f5f8"))
        ax.text(xs[0] + 0.008, y + 0.098, name, fontsize=10.6, va="center",
                fontweight="bold", color=NAVY)
        ax.text(xs[0] + 0.008, y + 0.042, hf, fontsize=7.6, va="center",
                family="monospace", color=LIGHT)
        for v, x in zip((size, dev, why), xs[1:]):
            ax.text(x + 0.008, y + 0.074, v, fontsize=10.2, va="center", color="#333")

    p = _panel(fig, 0.06, 0.185, 0.42, 0.19, PURPLE)
    p.text(0.04, 0.85, "Then a cross-encoder re-ranker", fontsize=12.5, fontweight="bold", color=PURPLE)
    p.text(0.04, 0.63,
           "bge-reranker-v2-m3 · Qwen3-Reranker-0.6B\n"
           "Reads the question and one candidate theorem\nJOINTLY (not as two separate vectors) — more\n"
           "accurate, far slower, so it only sees the top 20.",
           fontsize=10.6, va="top", color="#333")

    q = _panel(fig, 0.52, 0.185, 0.42, 0.19, RED)
    q.text(0.04, 0.85, "And the LLM judge we already use", fontsize=12.5, fontweight="bold", color=RED)
    q.text(0.04, 0.63,
           "Claude Opus, with the surrounding .tex context.\n"
           "The only component with a per-call cost, so\neverything above it exists to keep its input\n"
           "list short and worth reading.",
           fontsize=10.6, va="top", color="#333")


# ── 5. the three questions ───────────────────────────────────────────────────
def slide_questions(fig):
    _title(fig, "Three things we are testing — not just “which model”",
           "Two of these three were Or's suggestions")

    cards = [
        ("QUESTION 1  ·  which encoder", "Which embedding model?", BLUE,
         "Six bi-encoders, from a 22M model\nthat runs on a laptop to a 4B one.\n\n"
         "Same benchmark, same data, one\nrow each — a controlled ablation,\nnot a vibe check."),
        ("QUESTION 2  ·  what goes in the vector", "How much context?", GREEN,
         "Embed the theorem alone?\n\nOr the theorem WITH the definitions\nit `uses` and its grounded concepts\n"
         "— context taken from the graph,\nnot from nearby prose.\n\n"
         "Two ways: one string in one pass\n(graph-context embedding), or mix\nthe neighbours' vectors afterwards\n(late interaction — costs nothing)."),
        ("QUESTION 3  ·  input normalisation", "Canonicalize notation?", ORANGE,
         "One paper's G is another's H.\nSame maths, different symbols.\n\n"
         "α-renaming + normalised fractions,\nbinomials and inequalities before\nembedding.\n\n"
         "Tested raw vs canonical, and the\ntwo fused at score level (never by\nconcatenating vectors)."),
    ]
    for i, (tag, head, col, body) in enumerate(cards):
        x = 0.06 + i * 0.30
        p = _panel(fig, x, 0.315, 0.275, 0.465, col)
        p.text(0.05, 0.93, tag, fontsize=9, fontweight="bold", color=col)
        p.text(0.05, 0.845, head, fontsize=13.5, fontweight="bold", color=NAVY)
        p.text(0.05, 0.735, body, fontsize=10.3, va="top", color="#333")

    fig.text(0.06, 0.265, "We also test combinations — the honest answer may be “use both retrievers together”.",
             fontsize=13, fontweight="bold", color=NAVY)
    fig.text(0.06, 0.22,
             "Hybrid retrieval: keep the lexical (Jaccard) ranking AND the dense (embedding) ranking, merged by Reciprocal\n"
             "Rank Fusion — rank-based, so the two scores need no calibration. Lexical is good at shared symbols and\n"
             "formulas, dense at rewording; our first test already shows the fusion beating dense alone.",
             fontsize=11.2, color=GREY, va="top")


# ── 6. speed ─────────────────────────────────────────────────────────────────
def slide_speed(fig):
    _title(fig, "“Won't this be far too slow?”",
           "The main worry — 15,000 questions × 1.6 million theorems = 24 billion possible pairs")

    labels = ["Cross-encoder on\nevery single pair",
              "Lexical (Jaccard) sweep\n— what we ran",
              "Dense retrieval\n(embeddings)",
              "Cross-encoder re-rank\nof the top 20"]
    secs = [24.07e9 / 250, 3429, 250.0, 15143 * 20 / 250]
    cols = [RED, ORANGE, GREEN, BLUE]
    human = ["3 years", "57 minutes", "4 minutes", "20 minutes"]

    ax = fig.add_axes([0.175, 0.375, 0.44, 0.39])
    bars = ax.barh(range(4), secs, color=cols, alpha=0.88)
    ax.set_xscale("log")
    ax.set_yticks(range(4)); ax.set_yticklabels(labels, fontsize=10.5)
    ax.invert_yaxis()
    ax.set_xlabel("time to process the whole 100,000-paper collection", fontsize=10.5)
    # Clear minor ticks too: a log axis keeps drawing them, and the decade marks
    # are meaningless here — the human-readable durations are the labels.
    ax.set_xticks([]); ax.set_xticks([], minor=True)
    ax.grid(axis="x", alpha=0.25, ls=":")
    for b, h, c in zip(bars, human, cols):
        ax.text(b.get_width() * 1.4, b.get_y() + b.get_height() / 2, h,
                va="center", fontsize=12, fontweight="bold", color=c)
    ax.set_xlim(30, 4e9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    p = _panel(fig, 0.645, 0.375, 0.295, 0.39, GREEN)
    p.text(0.05, 0.93, "Measured on the cluster", fontsize=12.5, fontweight="bold", color=GREEN)
    p.text(0.05, 0.79,
           "2,000-paper pilot, 1x L40S:\n\n"
           "  encoding    1,040 texts/s\n"
           "  text prep     153 min\n"
           "  encoding       68 min\n"
           "  retrieval       4 min\n"
           "  (per one task, at 100k)\n\n"
           "Both prep and encoding split\nacross array tasks, so with 32/8\n"
           "tasks the wall time is ~15 min.",
           fontsize=10.4, va="top", color="#333", family="monospace")

    fig.text(0.06, 0.315,
             "Full run: ~3.5 GPU-hours of compute for the three-arm configuration, ~15 min of wall time once spread across\n"
             "array tasks, and no money — the embedding models are open-weight. Only the Claude judge has a per-call cost.",
             fontsize=12.5, color=NAVY, fontweight="bold", va="top")
    fig.text(0.06, 0.225,
             "The one quadratic component — the cross-encoder, which reads question and theorem jointly — is confined to\n"
             "the top 20 candidates per question: ~300k pairs, about one in every hundred thousand possible.",
             fontsize=11.5, color=GREY, va="top")
    _chip(fig, 0.775, 0.905, "MEASURED · 2,000-paper pilot", GREEN)


# ── 7. results ───────────────────────────────────────────────────────────────
def slide_results(fig, rows):
    _title(fig, "The result — yes, but only in combination",
           "2,000 papers · 200 planted answers · reworded by an LLM · five encoders · 101 arms · on the cluster")

    names = [r[0] for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    cols = [RED if n.startswith("old word") else
            (GREEN if n.startswith("old + new") else BLUE) for n in names]
    # Only the plain half of each two-line label is emphasised; the technical
    # name underneath is there for Or, not for the glance.

    ax = fig.add_axes([0.335, 0.445, 0.595, 0.325])
    ax.barh(range(len(vals)), vals, color=cols, alpha=0.88)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(names, fontsize=9.2)
    ax.set_xlabel("Average Precision — longer = the correct answer ranked nearer the top "
                  " (1.0 = perfect)", fontsize=10.5)
    ax.grid(axis="x", alpha=0.25, ls=":")
    for i, v in enumerate(vals):
        ax.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=10.5, fontweight="bold",
                color=cols[i])
    ax.set_xlim(0, 0.95)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    for i, (lab, col) in enumerate([("lexical baseline", RED),
                                    ("hybrid (lexical + dense)", GREEN),
                                    ("dense retrieval alone", BLUE)]):
        fig.text(0.345 + i * 0.20, 0.353, "■", fontsize=13, color=col)
        fig.text(0.363 + i * 0.20, 0.355, lab, fontsize=10.5, color=GREY)

    fig.text(0.06, 0.295, "What this shows:", fontsize=13, fontweight="bold", color=NAVY)
    fig.text(0.06, 0.255,
             "1.  The two TOGETHER beat word counting alone — 0.74 vs 0.65, and 22% more hidden answers reach the top 100.\n"
             "2.  Meaning-matching ALONE is worse (0.57). The value is in fusing them, not in replacing.\n"
             "3.  Word counting still ranks its FIRST correct hit highest: precise but narrow, where the embedder is\n"
             "     broader but noisier. They fail differently — which is exactly why combining them wins.",
             fontsize=11.2, color=GREY, va="top")
    _chip(fig, 0.755, 0.905, "MEASURED · cluster · L40S GPU", GREEN)


# ── 7b. the ablation panels ──────────────────────────────────────────────────
def _bench_frame(path: Path):
    """Benchmark CSV split into model / view / canon / fusion columns."""
    import pandas as pd
    if path is None or not Path(path).exists():
        return None
    d = pd.read_csv(path)

    def parts(a):
        if a == "lexical-jaccard":
            return ("lexical", "-", "-", "lexical")
        fus = ("hybrid" if "+lexical" in a
               else "raw+canon" if "+canon-rrf" in a else "dense")
        q = a.split("+")[0].split("/")
        return (q[0], q[1] if len(q) > 1 else "-", q[2] if len(q) > 2 else "-", fus)

    d[["model", "view", "canon", "fusion"]] = d.arm.apply(
        lambda a: pd.Series(parts(a)))
    return d


def slide_ablation(fig, d):
    _title(fig, "What the 101 experiments say",
           "Every bar is a measured run on the cluster. Four questions, four answers.")
    if d is None:
        fig.text(0.5, 0.5, "bench CSV not found", ha="center", color=GREY)
        return

    dense_raw = d[(d.fusion == "dense") & (d.canon == "raw")]
    # Older benchmark CSVs predate the per-problem curve; degrade rather than crash.
    lv = [c for c in ("L0@10", "L1@10", "L2@10", "L3@10") if c in d.columns]
    xs = [0, 1, 2, 3]

    # ── panel 1: the obfuscation curve ──────────────────────────────────────
    ax = fig.add_axes([0.065, 0.505, 0.185, 0.25])
    for arm, lab, col, mk in (
            ("lexical-jaccard", "word counting", RED, "o"),
            ("qwen3-0.6b/node/raw+lexical-rrf", "both combined", GREEN, "s"),
            ("bge-m3/node/raw", "meaning alone", BLUE, "^")):
        row = d[d.arm == arm]
        if len(row) and lv:
            ax.plot(xs, [float(row.iloc[0][c]) for c in lv], mk + "-",
                    color=col, lw=2, ms=6, label=lab)
    ax.set_xticks(xs); ax.set_xticklabels(["none", "light", "LLM", "LLM+"], fontsize=9)
    ax.set_ylim(0, 1.08); ax.set_ylabel("found in top 10", fontsize=9.5)
    ax.tick_params(labelsize=9); ax.grid(alpha=0.25, ls=":")
    ax.legend(fontsize=8, loc="lower left", frameon=False)
    ax.set_title("1 · Is our test hard enough?", fontsize=11.5, color=NAVY)

    # ── panel 2: cost vs quality ────────────────────────────────────────────
    ax2 = fig.add_axes([0.305, 0.505, 0.185, 0.25])
    pts = dense_raw[(dense_raw.view == "node") & dense_raw.texts_per_s.notna()]
    for _, r in pts.iterrows():
        ax2.scatter(r.texts_per_s, r.AP, s=90, color=BLUE, zorder=4)
        ax2.annotate(r.model, (r.texts_per_s, r.AP), fontsize=8,
                     xytext=(0, 8), textcoords="offset points", ha="center", color="#333")
    ax2.set_xlabel("statements / second", fontsize=8.5)
    ax2.set_ylabel("quality (AP)", fontsize=9.5)
    ax2.tick_params(labelsize=9); ax2.grid(alpha=0.25, ls=":")
    ax2.set_ylim(0.2, 0.68); ax2.set_xlim(0, 4200)
    ax2.set_title("2 · Which model is worth it?", fontsize=11.5, color=NAVY)

    # ── panel 3: how much context ───────────────────────────────────────────
    ax3 = fig.add_axes([0.545, 0.505, 0.185, 0.25])
    order = ["node", "ctx-late", "ctx-concat", "concepts-only"]
    names = ["stmt\nonly", "+ctx\ncheap", "+ctx\nfull", "concepts\nonly"]
    vals = [float(dense_raw[dense_raw.view == v].AP.mean()) for v in order]
    ax3.bar(range(4), vals, color=[GREEN] + [BLUE] * 3, alpha=0.88)
    ax3.set_xticks(range(4)); ax3.set_xticklabels(names, fontsize=7.5)
    ax3.set_ylabel("quality (AP)", fontsize=9.5)
    ax3.tick_params(labelsize=9); ax3.grid(axis="y", alpha=0.25, ls=":")
    for i, v in enumerate(vals):
        ax3.text(i, v + 0.012, f"{v:.2f}", ha="center", fontsize=9)
    ax3.set_ylim(0, 0.56)
    ax3.set_title("3 · Does graph context help?", fontsize=11.5, color=NAVY)

    # ── panel 4: raw vs canonical ───────────────────────────────────────────
    ax4 = fig.add_axes([0.785, 0.505, 0.185, 0.25])
    nd = d[(d.fusion == "dense") & (d.view == "node")]
    piv = nd.pivot_table(index="model", columns="canon", values="AP")
    piv = piv.sort_values("raw", ascending=False)
    idx = np.arange(len(piv))
    ax4.bar(idx - 0.19, piv["raw"], 0.38, label="as written", color=GREEN, alpha=0.88)
    ax4.bar(idx + 0.19, piv["canon"], 0.38, label="standardised", color=ORANGE, alpha=0.88)
    ax4.set_xticks(idx); ax4.set_xticklabels(piv.index, fontsize=7, rotation=30, ha="right")
    ax4.set_ylabel("quality (AP)", fontsize=9.5)
    ax4.tick_params(labelsize=9); ax4.grid(axis="y", alpha=0.25, ls=":")
    ax4.legend(fontsize=8, frameon=False)
    ax4.set_ylim(0, 0.68)
    ax4.set_title("4 · Standardise the notation?", fontsize=11.5, color=NAVY)

    # ── takeaways ───────────────────────────────────────────────────────────
    notes = [
        ("No — word counting already finds\nevery planted answer at every level.\nThe test cannot show what\nmeaning-matching adds.", RED),
        ("The cheapest one. MiniLM is 3x\nfaster than Qwen3 and, once fused\nwith word counting, just as good.", GREEN),
        ("Not here — and it is not the\ncontext window: the long-context\nmodels lost too. Planted problems\ncarry no graph edges.", ORANGE),
        ("No — worse for every model, and\nby a lot. Suspect the canonicaliser\nmangles the text before the model\never reads it.", ORANGE),
    ]
    for i, (txt, col) in enumerate(notes):
        fig.text(0.065 + i * 0.24, 0.415, txt, fontsize=9.2, color="#333", va="top")
        fig.add_artist(plt.Line2D([0.065 + i * 0.24, 0.065 + i * 0.24 + 0.185],
                                  [0.437, 0.437], color=col, lw=2.5))

    fig.text(0.065, 0.255,
             "The one unambiguous win is fusion: word counting AND meaning together, 0.74 vs 0.65.\n"
             "Panels 3 and 4 are not verdicts on Or's two ideas — they are verdicts on a test that "
             "cannot currently separate them from noise.",
             fontsize=11.5, color=NAVY, fontweight="bold", va="top")
    _chip(fig, 0.755, 0.905, "MEASURED · cluster · L40S GPU", GREEN)


# ── 8. caveats ───────────────────────────────────────────────────────────────
def slide_caveats(fig):
    _title(fig, "Two surprises, and one thing still unmeasured",
           "The results contradicted two of my own predictions — both are recorded here rather than smoothed over")

    items = [
        ("1", "Graph context HURT — and not for the reason I expected",
         "ctx-concat lost to the plain statement for EVERY encoder: bge-m3 0.57 → 0.49, Qwen3 0.43 → 0.35. I had\n"
         "predicted this was MiniLM's 256-token window truncating the context; bge-m3 (8k) and Qwen3 (32k) rule that\n"
         "out. Likeliest remaining cause: a planted problem is a bare node with NO edges, so context enriches only\n"
         "the theorem side and makes the two texts LESS alike. That is a flaw in the test, not a verdict on the idea.", RED),
        ("2", "Canonicalizing the notation HURT, consistently and by a lot",
         "Qwen3 0.43 → 0.29, bge-m3 0.57 → 0.32, across every view. Likeliest cause: the canonicaliser mangles the\n"
         "text (output like `bigcup_i=1^V2mathcal V1_i`), which damages an embedder far more than it damages token\n"
         "matching. Worth inspecting the canonical strings before drawing a conclusion about the idea.", ORANGE),
        ("3", "The obfuscation curve is not yet measurable",
         "Every fused arm read 1.00 at all four levels — because the metric counted a hidden answer as found if it\n"
         "appeared ANYWHERE in ~33k returned pairs. Fixed to measure the top-10 of each problem's own list, which is\n"
         "what a truncated shortlist actually shows the judge. One re-run (~20 min, no extra cost) will produce it.", PURPLE),
    ]
    for i, (n, head, body, col) in enumerate(items):
        y = 0.615 - i * 0.185
        ax = fig.add_axes([0.06, y, 0.88, 0.16]); ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.004, 0.004), 0.992, 0.992,
                                    boxstyle="round,pad=0.004,rounding_size=0.02",
                                    fc=col, alpha=0.07, ec=col, lw=1.4))
        ax.text(0.022, 0.75, n, ha="center", va="center", color="w",
                fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="circle,pad=0.34", fc=col, ec="none"))
        ax.text(0.055, 0.75, head, va="center", fontsize=13, fontweight="bold", color=col)
        ax.text(0.055, 0.53, body, va="top", fontsize=10.6, color="#333")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    fig.text(0.06, 0.215,
             "None of this touches the headline — fusing the two retrievers beats word counting alone, 0.74 vs 0.65. What is\n"
             "unresolved is whether the two ideas that LOST here lost on their merits, or on the way we tested them.",
             fontsize=11.8, color=NAVY, fontweight="bold", va="top")


# ── 9. status ────────────────────────────────────────────────────────────────
def slide_metric_why(fig):
    _title(fig, "Three disagreements, one score",
           "Every example below is a structure the parser found CORRECTLY — and every one is counted as an error today")

    # Three real cases from the 77-paper audit, lightly de-LaTeXed to stay readable.
    cases = [
        (BLUE, "GRANULARITY", "47% of errors",
         "we define the outer product\nu ⊗ v = u vᵀ",
         "parser  →  definition\nsilver  →  part of a proof",
         "A correct definition. Opus kept the\nwhole proof as one piece, so pulling\nthe definition out of it scores wrong."),
        (ORANGE, "SPAN BOUNDARY", "26% of errors",
         "define the Procustes distance\nbetween the datasets d_P(X, Y)",
         "parser  →  definition\nsilver  →  definition\noverlap 0.60, bar is 0.70",
         "The same definition, cut a few words\ndifferently. Falls just under the\nthreshold, so it counts as wrong."),
        (PURPLE, "CLASSIFICATION", "11% of errors",
         "Let f₁, …, f_T be an arbitrary\nsequence of functions",
         "parser  →  definition\nsilver  →  lemma",
         "Same statement, same span. Only\nthe label differs — the structure\nitself was found perfectly."),
    ]
    for i, (col, tag, share, snippet, verdict, why) in enumerate(cases):
        x = 0.06 + i * 0.305
        ax = _panel(fig, x, 0.375, 0.28, 0.40, col)
        ax.text(0.05, 0.93, tag, fontsize=11.5, fontweight="bold", color=col)
        ax.text(0.95, 0.93, share, fontsize=10.5, color=GREY, ha="right")
        ax.add_patch(FancyBboxPatch((0.05, 0.53), 0.90, 0.30,
                                    boxstyle="round,pad=0.01,rounding_size=0.03",
                                    fc="white", ec="#d8d8d8", lw=1))
        ax.text(0.09, 0.68, snippet, fontsize=10, color="#222",
                family="monospace", va="center")
        ax.text(0.05, 0.45, verdict, fontsize=10, color=NAVY,
                fontweight="bold", va="top")
        ax.text(0.05, 0.235, why, fontsize=9.8, color="#333", va="top")

    # Composition of every base-parser "false positive" on the 77 papers.
    ax = fig.add_axes([0.06, 0.235, 0.88, 0.085]); ax.axis("off")
    ax.set_xlim(0, 395); ax.set_ylim(0, 1)
    segs = [("nested in a bigger piece", 186, BLUE),
            ("span boundary", 103, ORANGE),
            ("duplicate", 55, GREY),
            ("wrong label", 42, PURPLE),
            ("genuinely wrong", 9, RED)]
    left = 0
    for lbl, n, col in segs:
        ax.add_patch(plt.Rectangle((left, 0.30), n, 0.55, fc=col,
                                   ec="white", lw=1.5, alpha=0.85))
        if n > 30:
            ax.text(left + n / 2, 0.575, f"{lbl}\n{n}", ha="center", va="center",
                    fontsize=9.5, color="white", fontweight="bold")
        left += n
    ax.annotate("only 9", xy=(390, 0.30), xytext=(370, -0.35),
                fontsize=11, fontweight="bold", color=RED, ha="center",
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))

    fig.text(0.06, 0.175, "395 things the parser was marked wrong for.  9 of them are actually wrong.",
             fontsize=15, fontweight="bold", color=NAVY)
    _chip(fig, 0.735, 0.905, "MEASURED · 77 papers, no LLM", GREEN)


def slide_metric_ladder(fig):
    _title(fig, "Report a ladder, not one number",
           "One worked example, scored four ways. Each rung drops exactly one requirement — and the verdict flips.")

    # ── the running example ────────────────────────────────────────────────
    exl = _panel(fig, 0.06, 0.615, 0.40, 0.195, GREEN)
    exl.text(0.04, 0.88, "WHAT OPUS LABELLED  (silver)", fontsize=10.5,
             fontweight="bold", color=GREEN)
    exl.add_patch(FancyBboxPatch((0.04, 0.10), 0.92, 0.68,
                                 boxstyle="round,pad=0.01,rounding_size=0.04",
                                 fc="white", ec=GREEN, lw=1.8))
    exl.text(0.07, 0.68, "proof", fontsize=10, fontweight="bold", color=GREEN)
    exl.text(0.07, 0.54, "Proof.  Fix any u, v in the unit ball.",
             fontsize=9.3, family="monospace", color="#444")
    exl.add_patch(plt.Rectangle((0.06, 0.30), 0.88, 0.16, fc=BLUE, alpha=0.16, ec="none"))
    exl.text(0.07, 0.375, "we define the outer product u \u2297 v = u v\u1d40",
             fontsize=9.3, family="monospace", color=NAVY, va="center")
    exl.text(0.07, 0.19, "\u2026 hence the bound follows.  \u25a1",
             fontsize=9.3, family="monospace", color="#444")
    exl.text(0.06, 0.015, "ONE node", fontsize=9, color=GREY, style="italic")

    exr = _panel(fig, 0.54, 0.615, 0.40, 0.195, BLUE)
    exr.text(0.04, 0.88, "WHAT THE PARSER FOUND", fontsize=10.5,
             fontweight="bold", color=BLUE)
    exr.add_patch(FancyBboxPatch((0.04, 0.47), 0.92, 0.31,
                                 boxstyle="round,pad=0.01,rounding_size=0.06",
                                 fc="white", ec=GREEN, lw=1.8))
    exr.text(0.07, 0.68, "proof", fontsize=10, fontweight="bold", color=GREEN)
    exr.text(0.07, 0.55, "Proof.  Fix any u, v \u2026 hence the bound follows.",
             fontsize=9.3, family="monospace", color="#444")
    exr.add_patch(FancyBboxPatch((0.04, 0.10), 0.92, 0.28,
                                 boxstyle="round,pad=0.01,rounding_size=0.06",
                                 fc="white", ec=BLUE, lw=1.8))
    exr.text(0.07, 0.30, "definition", fontsize=10, fontweight="bold", color=BLUE)
    exr.text(0.07, 0.17, "we define the outer product u \u2297 v = u v\u1d40",
             fontsize=9.3, family="monospace", color=NAVY)
    exr.text(0.06, 0.015, "TWO nodes \u2014 it also pulled the definition out",
             fontsize=9, color=GREY, style="italic")

    fig.add_artist(plt.Line2D([0.462, 0.532], [0.760, 0.760], color=GREEN, lw=2))
    fig.text(0.497, 0.772, "pairs", fontsize=9, color=GREEN, ha="center", fontweight="bold")
    fig.text(0.497, 0.668, "?", fontsize=17, color=RED, ha="center", fontweight="bold")
    fig.text(0.06, 0.578,
             "The proof pairs off cleanly. The question every metric below answers differently: what do we do with the definition?",
             fontsize=11, color=NAVY, fontweight="bold")

    # ── the ladder ─────────────────────────────────────────────────────────
    rungs = [
        (NAVY, "M1  strict", "today",
         r"match if  type(e)=type(g)  and  $\frac{|e\,\cap\,g|}{\min(|e|,|g|)}\geq0.7$,  one-to-one",
         False, "labels differ (definition vs proof) \u2192 no match", 0.739),
        (PURPLE, "M2  any-label", "ignore the label",
         r"match if  $\frac{|e\,\cap\,g|}{\min(|e|,|g|)}\geq0.7$,  one-to-one",
         False, "the proof node already used up the gold proof \u2192 nothing left to pair", 0.797),
        (BLUE, "M3  nested-ok", "allow pieces inside pieces",
         r"$P=\frac{\#\{e\,:\,\exists g,\ |e\cap g|/|e|\geq0.7\}}{|E|}$      $R=\frac{\#\{g\,:\,|g\cap\bigcup E|/|g|\geq0.7\}}{|G|}$",
         True, "the definition IS part of something real, and the proof is covered", 0.933),
        (LIGHT, "M4  coverage", "appendix",
         r"$P=\frac{|\bigcup E\,\cap\,\bigcup G|}{|\bigcup E|}$      $R=\frac{|\bigcup E\,\cap\,\bigcup G|}{|\bigcup G|}$",
         True, "forget nodes entirely \u2014 counts content, not structure, so it is NOT on the chart below", 0.803),
    ]

    y0, h = 0.487, 0.062
    for i, (col, name, tag, formula, ok, why, val) in enumerate(rungs):
        y = y0 - i * (h + 0.006)
        ax = _panel(fig, 0.06, y, 0.755, h, col, alpha=0.07)
        ax.text(0.016, 0.70, name, fontsize=11.5, fontweight="bold", color=col)
        ax.text(0.27, 0.68, formula, fontsize=9.2, color="#222", va="center")
        ax.text(0.016, 0.15, f"{tag} \u2014 {why}", fontsize=8.8, color="#444")
        bx = fig.add_axes([0.825, y, 0.115, h]); bx.axis("off")
        bx.set_xlim(0, 1); bx.set_ylim(0, 1)
        bx.text(0.0, 0.40, "\u2713 RIGHT" if ok else "\u2717 WRONG", fontsize=11,
                fontweight="bold", color=GREEN if ok else RED)

    fig.text(0.825, 0.572, "verdict on this example", fontsize=8.6, color=GREY, style="italic")
    # ── the same three metrics across all three splits ─────────────────────
    scores = {
        "M1 strict":    (0.711, 0.739, 0.679),
        "M2 any-label": (0.751, 0.797, 0.733),
        "M3 nested-ok": (0.822, 0.933, 0.828),
    }
    cols = {"M1 strict": NAVY, "M2 any-label": PURPLE, "M3 nested-ok": BLUE}
    groups = ["train\n17 papers", "test · pure maths\n20 papers", "test · ML\n40 papers"]

    cx = fig.add_axes([0.085, 0.098, 0.83, 0.142])
    xs = np.arange(len(groups))
    w = 0.26
    for i, (name, vals) in enumerate(scores.items()):
        pos = xs + (i - 1) * w
        cx.bar(pos, vals, width=w * 0.9, color=cols[name], label=name,
               alpha=0.9, zorder=3)
        for x, v in zip(pos, vals):
            cx.text(x, v + 0.018, f"{v:.3f}", ha="center", fontsize=9,
                    fontweight="bold", color=cols[name])
    cx.set_xticks(xs); cx.set_xticklabels(groups, fontsize=10.5, color=NAVY)
    cx.set_ylim(0.60, 1.0); cx.set_yticks([0.7, 0.8, 0.9])
    cx.set_yticklabels(["0.7", "0.8", "0.9"], fontsize=9, color=GREY)
    cx.grid(axis="y", color="#e3e3e3", zorder=0)
    for side in ("top", "right", "left"):
        cx.spines[side].set_visible(False)
    cx.spines["bottom"].set_color("#cccccc")
    cx.tick_params(length=0)
    for i, (name, col) in enumerate(cols.items()):
        fig.text(0.085 + i * 0.135, 0.262, "\u25a0 " + name, fontsize=10,
                 fontweight="bold", color=col)
    fig.text(0.915, 0.262, "pooled F1, base rules", fontsize=9,
             color=GREY, style="italic", ha="right")
    _chip(fig, 0.755, 0.905, "MEASURED \u00b7 no LLM", GREEN)


def slide_status(fig):
    _title(fig, "Where this stands — and what to launch",
           "The 100,000-paper run is done, on the smallest reading model. What is left is making it find "
           "something NEW.")

    ax = fig.add_axes([0.06, 0.645, 0.88, 0.135]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.004, 0.004), 0.992, 0.992,
                                boxstyle="round,pad=0.004,rounding_size=0.02",
                                fc=GREEN, alpha=0.09, ec=GREEN, lw=2))
    ax.text(0.5, 0.70, "100,000-PAPER RUN DONE  —  with the smallest of the six reading models",
            ha="center", fontsize=15.5, fontweight="bold", color=GREEN)
    ax.text(0.5, 0.27,
            "All five stages end to end on an L40S: 99,996 papers, 1.57M statements, cross-subfield matches confirmed. "
            "Not yet done:\nthe stronger models, and any real test of whether a match the machine finds is already known to the field.",
            ha="center", fontsize=11, color=GREY, va="center")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    done = ["the full 100k run: 99,996 papers → 1.57M statements →\n   20 pairs judged by Claude",
            "re-reading beat similarity alone on the SAME candidates:\n   2 genuine matches versus 0",
            "281,829 candidate pairs that word counting never produced",
            "correctness: CPU and GPU agree exactly, split-up equals\n   single-process, encoding is repeatable"]
    p = _panel(fig, 0.06, 0.29, 0.42, 0.315, GREEN)
    p.text(0.05, 0.90, "Done", fontsize=13.5, fontweight="bold", color=GREEN)
    for i, d in enumerate(done):
        p.text(0.05, 0.735 - i * 0.185, "✓", fontsize=12, fontweight="bold", color=GREEN)
        p.text(0.10, 0.74 - i * 0.185, d, fontsize=10.6, va="top", color="#333")

    todo = [("1", "The stronger reading models + re-readers",
             "we ran the smallest of six; re-reading is what moved the result."),
            ("2", "A real test of “is this already known?”",
             "we only ask whether B cites A — the famous pair passed that."),
            ("3", "Erdős problems: meaning vs words",
             "word-matching done; the comparison is on the cluster now."),
            ("4", "A few dozen matches labelled by hand",
             "nothing above can be scored until ground truth exists.")]
    q = _panel(fig, 0.52, 0.29, 0.42, 0.315, BLUE)
    q.text(0.05, 0.90, "Next", fontsize=13.5, fontweight="bold", color=BLUE)
    for i, (n, h, b) in enumerate(todo):
        y = 0.735 - i * 0.19
        q.text(0.06, y, n, ha="center", va="center", color="w", fontsize=9,
               fontweight="bold", bbox=dict(boxstyle="circle,pad=0.32", fc=BLUE, ec="none"))
        q.text(0.11, y + 0.055, h, fontsize=11, fontweight="bold", color=NAVY, va="top")
        q.text(0.11, y - 0.015, b, fontsize=9.8, color=GREY, va="top")

    fig.text(0.06, 0.235,
             "Question for the meeting:  scale up to the whole of arXiv, or first fix “is it already known?” — right now\n"
             "the pipeline cannot tell a real discovery from a famous theorem it has rediscovered.",
             fontsize=12.5, color=NAVY, fontweight="bold", va="top")


# ── 9b. the 100k run ─────────────────────────────────────────────────────────
def slide_corpus_run(fig):
    _title(fig, "The full run — 100,000 papers, end to end",
           "Every stage measured on the cluster. The last rung is where it got interesting.")

    # funnel
    ax = fig.add_axes([0.06, 0.50, 0.88, 0.25]); ax.axis("off")
    stages = [("99,996", "papers\nprocessed", BLUE),
              ("1.57M", "statements\nembedded", BLUE),
              ("297,860", "candidate pairs\n(meaning-based)", GREEN),
              ("281,829", "pairs word counting\nNEVER had", ORANGE),
              ("20", "sent to\nClaude", RED)]
    for i, (big, small, col) in enumerate(stages):
        x = i * 0.202
        ax.add_patch(FancyBboxPatch((x, 0.10), 0.176, 0.82,
                                    boxstyle="round,pad=0.006,rounding_size=0.05",
                                    fc=col, alpha=0.12, ec=col, lw=1.6))
        ax.text(x + 0.088, 0.64, big, ha="center", fontsize=15.5,
                fontweight="bold", color=col)
        ax.text(x + 0.088, 0.31, small, ha="center", fontsize=9.8, color=GREY)
        if i < 4:
            ax.annotate("", xy=(x + 0.198, 0.51), xytext=(x + 0.180, 0.51),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, lw=2))
    ax.set_xlim(-0.005, 1.0); ax.set_ylim(0, 1)

    # overlap: the two methods barely agree
    ax2 = fig.add_axes([0.155, 0.275, 0.175, 0.185])
    vals = [300.2, 297.9, 16.0]
    ax2.barh([0, 1, 2], vals, color=[RED, GREEN, GREY], alpha=0.88)
    ax2.set_yticks([0, 1, 2])
    ax2.set_yticklabels(["word\ncounting", "meaning\nbased", "BOTH\nagree"], fontsize=8.5)
    ax2.invert_yaxis(); ax2.tick_params(labelsize=8)
    ax2.set_xlabel("thousand candidate pairs", fontsize=8.5)
    ax2.grid(axis="x", alpha=0.25, ls=":")
    for i, v in enumerate(vals):
        ax2.text(v + 12, i, f"{v:,.0f}k", va="center", fontsize=8.5)
    ax2.set_xlim(0, 430)
    for sp in ("top", "right"):
        ax2.spines[sp].set_visible(False)
    ax2.set_title("They almost never agree", fontsize=11, color=NAVY, pad=6)

    fig.text(0.075, 0.225,
             "Only 5% of what the new method finds was ever\nseen by the old one.",
             fontsize=10, color="#333", va="top")

    # the ranking result
    ax3 = fig.add_axes([0.445, 0.275, 0.155, 0.185])
    ax3.bar([0, 1], [0, 2], color=[GREY, GREEN], alpha=0.88, width=0.55)
    ax3.set_xticks([0, 1])
    ax3.set_xticklabels(["by\nsimilarity", "after\nre-reading"], fontsize=8.5)
    ax3.set_ylabel("real matches\nin top 20", fontsize=8.5)
    ax3.set_ylim(0, 2.7); ax3.tick_params(labelsize=8)
    ax3.grid(axis="y", alpha=0.25, ls=":")
    for i, v in enumerate([0, 2]):
        ax3.text(i, v + 0.1, str(v), ha="center", fontsize=13,
                 fontweight="bold", color=GREY if v == 0 else GREEN)
    for sp in ("top", "right"):
        ax3.spines[sp].set_visible(False)
    ax3.set_title("Ranking was the bottleneck", fontsize=11, color=NAVY, pad=6)

    fig.text(0.415, 0.225,
             "Same 20 Claude calls, same candidates —\nonly the ORDER changed.",
             fontsize=10, color="#333", va="top")

    pn = _panel(fig, 0.715, 0.245, 0.225, 0.215, GREEN)
    pn.text(0.06, 0.88, "Why", fontsize=12, fontweight="bold", color=GREEN)
    pn.text(0.06, 0.74,
            "Similarity alone says\n“same research area”.\n\n"
            "Its own top 20 gave 0/20.\n\n"
            "Reading both statements\nTOGETHER tells same-object\nfrom same-subject.",
            fontsize=9.5, va="top", color="#333")

    _chip(fig, 0.735, 0.905, "MEASURED · full 100k corpus", GREEN)


# ── 9c. what it found ────────────────────────────────────────────────────────
#: The pair every chart on this slide highlights.
_PAIR_COS, _PAIR_RR, _COS_CUT = 0.7075, 0.9417, 0.7837


def _load_rerank_scores():
    """The 200 candidates the 100k dense run judged, scored both ways.

    Returns (cosine, rerank) arrays or None. Read from the committed run output
    so the chart cannot drift from the numbers it claims to show.
    """
    p = (Path(__file__).resolve().parents[1] / "open_problems" / "runs" /
         "dense_100k" / "triage_reranked.csv")
    if not p.exists():
        return None
    import csv
    cos, rr = [], []
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                cos.append(float(r["retrieval_score"]))
                rr.append(float(r["rerank_score"]))
            except (KeyError, ValueError):
                return None
    return (np.array(cos), np.array(rr)) if cos else None


def _strip(ax, vals, pair_val, title, cut=None):
    """One method's 200 scores as a jittered dot strip, the true pair picked out.

    Two panels rather than one shared axis: the two scores live on different
    scales, and forcing them onto one axis would be the dual-axis mistake.
    """
    rng = np.random.default_rng(7)             # fixed: same picture every build
    y = rng.uniform(-1, 1, size=len(vals))
    ax.scatter(vals, y, s=13, color="#c2ccd6", edgecolors="none", zorder=2)
    if cut is not None:
        ax.axvline(cut, color=GREY, lw=1.4, ls="--", zorder=3)
        # Label sits beside the rule, not on it — the line runs the full height.
        ax.text(cut, 1.9, "top-20 cut  ", fontsize=8.6, color=GREY, ha="right")
    # 2px surface ring so the highlight reads on top of the crowd.
    ax.scatter([pair_val], [0], s=170, color=GREEN, edgecolors="white",
               linewidths=2, zorder=5)
    ax.annotate(f"{pair_val:.3f}", xy=(pair_val, 0), xytext=(pair_val, -2.35),
                ha="center", fontsize=9.6, fontweight="bold", color=GREEN)
    ax.set_title(title, fontsize=11, pad=6, loc="left")
    ax.set_ylim(-3.1, 2.5)
    ax.set_yticks([])
    ax.tick_params(labelsize=9, colors=GREY)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#d7dee5")


def slide_finding(fig):
    _title(fig, "Why only the re-reader found it",
           "The same pair, scored by both methods over the same 200 candidates")

    # Left column mirrors the two charts on the right, row for row.
    pa = _panel(fig, 0.06, 0.66, 0.41, 0.115, BLUE)
    pa.text(0.04, 0.80, "PAPER A  ·  1004.5010  ·  2010", fontsize=10,
            fontweight="bold", color=BLUE)
    pa.text(0.04, 0.46, "states the open problem", fontsize=9.5, color=GREY,
            style="italic")
    pa.text(0.04, 0.16, "The Feder–Vardi CSP Dichotomy Conjecture.",
            fontsize=10, color="#222")

    pb = _panel(fig, 0.06, 0.455, 0.41, 0.115, GREEN)
    pb.text(0.04, 0.80, "PAPER B  ·  1803.07465  ·  2018", fontsize=10,
            fontweight="bold", color=GREEN)
    pb.text(0.04, 0.46, "proves it (Zhuk) — and never cites A", fontsize=9.5,
            color=GREY, style="italic")
    pb.text(0.04, 0.16, "CSP(Γ) is polynomial-time iff a WNU preserves Γ.",
            fontsize=10, color="#222")

    fig.text(0.265, 0.617, "▼  8 years apart, different subfields", fontsize=9,
             color=GREY, ha="center")

    data = _load_rerank_scores()
    if data is not None:
        cos, rr = data
        a1 = fig.add_axes([0.53, 0.675, 0.41, 0.10])
        _strip(a1, cos, _PAIR_COS, "MEANING alone (bi-encoder cosine)", cut=_COS_CUT)
        a2 = fig.add_axes([0.53, 0.455, 0.41, 0.10])
        _strip(a2, rr, _PAIR_RR, "RE-READ together (cross-encoder)")
        fig.text(0.53, 0.408, "each dot = one of the 200 candidate pairs the run judged",
                 fontsize=8.8, color=LIGHT)

    fig.text(0.06, 0.385,
             "Cosine buried it at 0.708 — a third of the unrelated pairs scored higher, and it fell below the 0.784\n"
             "cut-off. Re-reading put it first of all 200, at 0.942.",
             fontsize=11.5, color=NAVY, fontweight="bold", va="top", linespacing=1.45)

    a = _panel(fig, 0.06, 0.163, 0.42, 0.165, GREEN)
    a.text(0.05, 0.83, "Why re-reading wins", fontsize=12, fontweight="bold", color=GREEN)
    a.text(0.05, 0.56,
           "It sees both statements at once, so it can line\n“a WNU preserving Γ exists” up against “either\n"
           "NP-complete or polynomial-time” and see that one\nis the answer to the other. The first method had to\n"
           "sum each up before ever seeing the other.",
           fontsize=9.8, va="top", color="#333")

    b = _panel(fig, 0.52, 0.163, 0.42, 0.165, RED)
    b.text(0.05, 0.83, "But it is NOT a discovery", fontsize=12, fontweight="bold", color=RED)
    b.text(0.05, 0.56,
           "Zhuk's proof is one of the most celebrated results\nin theoretical CS. Our novelty check only asks\n"
           "“does B cite A?”, which cannot tell that the whole\nfield already knows. Replacing it with a real test —\n"
           "does a third paper cite both? — is the next job.",
           fontsize=9.8, va="top", color="#333")

    _chip(fig, 0.755, 0.905, "MEASURED · verified by hand", GREEN)


#: Best-match score histogram from the full 100k Erdős run (21 shards, merged).
#: 20 bins of width 0.03 spanning 0 to the observed maximum of 0.600.
_ERDOS_BINS = [0, 0, 0, 8, 37, 87, 120, 141, 154, 177,
               181, 89, 41, 15, 4, 2, 4, 1, 1, 1]          # sums to 1,063
_ERDOS_P50, _ERDOS_P99, _ERDOS_MAX = 0.268, 0.440, 0.600

#: Corpus nodes that came out "best match" for the most Erdős problems.
_ERDOS_HUBS = [("1603.05233::Cj2", 31), ("1907.07712::Cj4", 20),
               ("1111.1993::DIST_O1", 18), ("1604.06903::Cj1", 13),
               ("1602.02788::Cj1", 13)]


def slide_erdos(fig):
    _title(fig, "Erdős problems: are they in our corpus?",
           "1,217 catalogued Erdős problems checked against all 100,000 parsed papers — "
           "and why the headline number is a trap")

    # ── left: the score distribution ─────────────────────────────────────────
    ax = fig.add_axes([0.06, 0.475, 0.505, 0.315])
    width = _ERDOS_MAX / len(_ERDOS_BINS)
    centres = [(i + 0.5) * width for i in range(len(_ERDOS_BINS))]
    colors = [GREEN if c > 0.55 else ORANGE if c >= _ERDOS_P99 else "#b9c6d4"
              for c in centres]
    ax.bar(centres, _ERDOS_BINS, width=width * 0.92, color=colors)
    ax.axvline(0.15, color=RED, lw=2, ls="--")
    ax.text(0.152, max(_ERDOS_BINS) * 0.93, " cut-off we\n guessed first",
            fontsize=9.5, color=RED, fontweight="bold", va="top")
    ax.annotate("the one match we\nverified by hand:\nErdős–Gallai",
                xy=(0.585, 6), xytext=(0.40, 108),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.8),
                fontsize=9.5, color=GREEN, fontweight="bold")
    ax.set_xlabel("share of words the two statements have in common", fontsize=10.5)
    ax.set_ylabel("Erdős problems", fontsize=10.5)
    ax.set_title("Every problem finds something — one smooth hump, no gap",
                 fontsize=12, pad=8)
    ax.tick_params(labelsize=9.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # ── right: the numbers ───────────────────────────────────────────────────
    p = _panel(fig, 0.605, 0.475, 0.335, 0.315, NAVY, alpha=0.06)
    p.text(0.06, 0.90, "What came back", fontsize=12.5, fontweight="bold", color=NAVY)
    facts = [
        ("1,217", "Erdős problems catalogued", GREY),
        ("1,063", "usable (rest too short to match)", GREY),
        ("95.8%", "“found” at our first cut-off  ← wrong", RED),
        ("584", "corpus statements absorb all 1,063", ORANGE),
        ("31", "problems matched by ONE statement", ORANGE),
        ("1", "match confirmed correct, ranked 1st", GREEN),
        ("0", "matches judged by the AI yet", GREY),
    ]
    y = 0.75
    for big, small, col in facts:
        p.text(0.09, y, big, fontsize=14, fontweight="bold", color=col, ha="right")
        p.text(0.13, y, small, fontsize=10.3, color="#333")
        y -= 0.115

    # ── bottom: the three things to note ─────────────────────────────────────
    issues = [
        (RED, "The 95.8% is an illusion",
         "We keep each problem's single best match out\nof ~100,000 statements. Search a big enough\n"
         "pile and something always looks similar: the\ntypical score rose from 0.15 on a tiny test set\n"
         "to 0.27 on the real corpus. No cut-off works —\nthe chart has no gap to cut at."),
        (ORANGE, "A few statements match everything",
         "One conjecture node is the “best match” for 31\nunrelated Erdős problems; it can be right about\n"
         "at most one. These are long, generic sentences.\nSome are machine-extracted boilerplate rather\n"
         "than real conjectures — worth fixing upstream\nin the parser, not here."),
        (GREEN, "But the ranking does work",
         "Top of the list is a real hit: Erdős–Gallai,\nstated word-for-word in a 2013 paper. The\n"
         "lesson is to rank and let the AI judge the top\nslice — not to draw a line and call everything\n"
         "above it found. Same recipe the open-problem\npipeline already uses."),
    ]
    for i, (col, head, body) in enumerate(issues):
        a = _panel(fig, 0.06 + i * 0.305, 0.155, 0.275, 0.265, col)
        a.text(0.055, 0.885, head, fontsize=12, fontweight="bold", color=col)
        a.text(0.055, 0.735, body, fontsize=9.9, va="top", color="#333")

    _chip(fig, 0.735, 0.905, "MEASURED · full 100k corpus", GREEN)


#: Five rows from the merged 100k run, chosen to span the full quality range:
#: one correct match, one same-family pair, two sentence-frame collisions and one
#: node whose text is broken. Statements are lightly shortened for the slide;
#: the corpus side is re-typeset from the stripped-down text the matcher sees.
_ERDOS_PAIRS = [
    (0.60, "#184", GREEN, "SAME PROBLEM",
     "Any graph on n vertices can be decomposed\ninto O(n) edge-disjoint cycles and edges.",
     "“Erdős–Gallai: every graph on n vertices can\nbe decomposed into O(n) cycles and edges.”",
     "arXiv 1310.0632", "correct — verified by hand"),
    (0.53, "#574", ORANGE, "SAME FAMILY",
     "Is it true that, for k ≥ 2,\nex(n; {C₂ₖ₋₁, C₂ₖ}) = (1+o(1))(n/2)^(1+1/k)?",
     "“For all k ≥ 2, ex(n; C₂ₖ) = O(n^(1+1/k)).”",
     "arXiv 1609.08212", "related, not identical — needs a judge"),
    (0.55, "#972", RED, "COINCIDENCE",
     "Let α>1 be irrational. Are there infinitely\nmany primes p with ⌊pα⌋ also prime?",
     "“There are infinitely many primes p such\nthat p+2 is also a prime.”  (twin primes)",
     "arXiv 1806.09034", "same sentence frame, different problem"),
    (0.50, "#1080", RED, "COINCIDENCE",
     "Bipartite G on n vertices, one part of size\n⌊n^(2/3)⌋ — does cn edges force a subgraph?",
     "“There exists c>0 such that a triangle-free\nplanar G on n vertices has 2^(cn) 3-colorings.”",
     "arXiv 1007.1430", "matched on shared boilerplate only"),
    (0.50, "#714", PURPLE, "BROKEN TEXT",
     "Is it true that ex(n; K_{r,r}) ≫ n^(2−1/r)?",
     "“is it true that ucflkv k n 1 sqsubseteq\nrefcflkvk n”",
     "arXiv 1610.07175", "unexpanded LaTeX macro — a parser bug"),
]


def slide_erdos_examples(fig):
    _title(fig, "What the matches actually look like",
           "Five of the highest-scoring pairs, top to bottom — one is right, one is close, three are not")

    ax = fig.add_axes([0.06, 0.245, 0.88, 0.56]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    ax.text(0.075, 0.975, "THE ERDŐS PROBLEM", fontsize=9.5, fontweight="bold",
            color=LIGHT)
    ax.text(0.475, 0.975, "CLOSEST STATEMENT IN OUR CORPUS", fontsize=9.5,
            fontweight="bold", color=LIGHT)
    ax.text(0.875, 0.975, "VERDICT", fontsize=9.5, fontweight="bold", color=LIGHT)

    row_h, top = 0.185, 0.935
    for i, (score, num, col, tag, erdos, match, arxiv, note) in enumerate(_ERDOS_PAIRS):
        y = top - (i + 1) * row_h
        ax.add_patch(FancyBboxPatch((0.0, y), 1.0, row_h * 0.88,
                                    boxstyle="round,pad=0.004,rounding_size=0.02",
                                    fc=col, alpha=0.055, ec=col, lw=1.1))
        ax.text(0.028, y + row_h * 0.60, f"{score:.2f}", fontsize=13,
                fontweight="bold", color=col, ha="center")
        ax.text(0.028, y + row_h * 0.32, num, fontsize=8.5, color=GREY, ha="center")
        ax.text(0.075, y + row_h * 0.66, erdos, fontsize=9.6, va="center", color="#222")
        ax.annotate("", xy=(0.468, y + row_h * 0.44), xytext=(0.432, y + row_h * 0.44),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6))
        ax.text(0.475, y + row_h * 0.66, match, fontsize=9.6, va="center", color="#222")
        ax.text(0.475, y + row_h * 0.16, arxiv, fontsize=8.2, color=LIGHT)
        ax.text(0.875, y + row_h * 0.62, tag, fontsize=9.6, fontweight="bold",
                color=col, ha="center")
        ax.text(0.875, y + row_h * 0.30, textwrap.fill(note, 26), fontsize=8.2,
                color=GREY, ha="center", va="top")

    fig.text(0.06, 0.208,
             "The twin-primes statement in row 3 is the “best match” for FIVE different Erdős problems; one corpus statement wins\n"
             "thirty-one. Counting shared words rewards a shared sentence shape — so the final call belongs to the judge, not a cut-off.",
             fontsize=10.8, color=NAVY, va="top", linespacing=1.5)
    _chip(fig, 0.735, 0.905, "MEASURED · full 100k corpus", GREEN)


def slide_erdos_next(fig):
    _title(fig, "Erdős: where it stands and what happens next",
           "Word-matching is done and understood. Meaning-matching is on the cluster now.")

    col_w, gap = 0.275, 0.03
    cols = [
        (GREEN, "DONE", "word-matching, full 100k", [
            "All 1,217 problems matched\nagainst the corpus.",
            "Ranking works — Erdős–Gallai\ncame first of 1,063.",
            "Cut-offs do not work.",
            "Two bugs found and fixed.",
        ]),
        (BLUE, "RUNNING NOW", "meaning-matching", [
            "Same problems, matched by\nmeaning, not shared words.",
            "Reuses coordinates already\nbuilt — minutes, not a rebuild.",
            "Small test: correct matches\npulled clear, 0.63 → 0.79.",
        ]),
        (ORANGE, "NEXT", "in order", [
            "1.  Drop the statements that match\n     everything; judge the top by AI.",
            "2.  Try the stronger reading models.",
            "3.  Let the AI search the corpus\n     itself for a solution.",
            "4.  Then: can a corpus theorem\n     RESOLVE an Erdős problem?",
            "5.  Fix the parser cases exposed.",
        ]),
    ]
    for i, (col, head, sub, items) in enumerate(cols):
        x = 0.06 + i * (col_w + gap)
        a = _panel(fig, x, 0.375, col_w, 0.415, col)
        a.text(0.055, 0.935, head, fontsize=13, fontweight="bold", color=col)
        a.text(0.055, 0.855, sub, fontsize=9.5, color=GREY, style="italic")
        # Step is per-item so a two-line entry does not push the tail of a long
        # column (the NEXT list is five deep) out through the panel floor.
        y = 0.755
        for it in items:
            a.text(0.055, y, it, fontsize=10, va="top", color="#333")
            y -= 0.098 + 0.062 * it.count("\n")

    b = _panel(fig, 0.06, 0.163, 0.88, 0.185, RED)
    b.text(0.022, 0.83, "The thing that limits all of it", fontsize=12,
           fontweight="bold", color=RED)
    b.text(0.022, 0.56,
           "Exactly ONE Erdős match is confirmed by hand, so no coverage figure from either method can be checked.\n"
           "We can rank methods against each other — we cannot yet say how right any of them is.",
           fontsize=10.6, va="top", color="#333", linespacing=1.6)

    _chip(fig, 0.755, 0.905, "STATUS · 4 Aug 2026", BLUE)


# ── data ─────────────────────────────────────────────────────────────────────

#: How each internal experiment name is described to a non-technical reader, and
#: the order the chart should tell the story in.
#: Plain label on the first line, the technical name in parentheses on the second,
#: so the chart is readable at a glance and still says what was actually run.
_PLAIN_NAMES = [
    ("lexical-jaccard", "old word-counting method\n(lexical · token Jaccard)"),
    ("+lexical", "old + new, combined\n(hybrid · reciprocal rank fusion)"),
    ("node", "new: statement only\n(dense · node embedding)"),
    ("ctx-late", "new: + context, cheap way\n(late interaction · vector mixing)"),
    ("ctx-concat", "new: + context, full way\n(graph-context embedding)"),
    ("concepts-only", "new: key concepts only\n(concept-grounding embedding)"),
]

#: Cluster benchmark, 2,000 papers, 200 planted twins, LLM paraphrase at L2-L3,
#: five encoders. Best arm of each family.
_FALLBACK = sorted(
    ((lbl, v) for (_k, lbl), v in
     zip(_PLAIN_NAMES, (0.647, 0.745, 0.572, 0.567, 0.485, 0.184))),
    key=lambda x: -x[1])


def _load_bench(path: Path):
    """Six clearly-named bars, not the raw 25-arm table.

    The full factorial contains ten near-identical variants of the same winner;
    charting them tells a non-technical reader nothing. We take one bar per
    IDEA — the old method, the two combined, and the best of each "how much
    context" setting — and label each in plain words.
    """
    if path is None or not Path(path).exists():
        return _FALLBACK
    import pandas as pd
    df = pd.read_csv(path).sort_values("AP", ascending=False).drop_duplicates("arm")

    out: list[tuple[str, float]] = []
    for key, label in _PLAIN_NAMES:
        if key == "lexical-jaccard":
            hit = df[df["arm"] == key]
        elif key == "+lexical":
            hit = df[df["arm"].str.contains(r"\+lexical", regex=True)]
        else:
            # plain (unfused) arms only, matching this context setting
            hit = df[~df["arm"].str.contains(r"\+") & df["arm"].str.contains(f"/{key}/")]
        if len(hit):
            out.append((label, float(hit.iloc[0]["AP"])))
    out.sort(key=lambda x: -x[1])
    return out or _FALLBACK


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bench", default=str(
        Path(__file__).resolve().parents[1] / "open_problems" / "runs" / "bench_curve.csv"))
    ap.add_argument("--out", default=str(
        Path(__file__).resolve().parent / "saranga_semantic_brief.pdf"))
    args = ap.parse_args()

    rows = _load_bench(Path(args.bench))
    bench = _bench_frame(Path(args.bench))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    _slide.n = 0  # slide numbering drives the section eyebrow
    with PdfPages(out) as pp:
        _slide(pp, slide_goal,
               "The thing we are hunting for is a paper that quietly answers an older paper's open question without "
               "either author realising. Our papers are already broken into labelled pieces — theorems, definitions, "
               "open problems — so a machine can compare a question in one paper against every theorem written after it.")
        _slide(pp, slide_today,
               "Here is what we ran before. Fifteen thousand open questions against 1.6 million theorems, narrowed by "
               "shared words down to 166 pairs that Claude then judged. Seven were real solutions — but every single one "
               "was already known, because the later paper cited the earlier one. We are finding rephrased copies, not "
               "discoveries, because counting shared words is literal: it spots 'a mat' for 'the mat' but never 'the rug'.")
        _slide(pp, slide_idea,
               "The fix is to compare meaning instead. A reading model turns each statement into coordinates on a map, "
               "and statements that mean the same thing land near each other even with no words in common. On this "
               "picture, word counting only reaches the dashed circle; meaning reaches the whole green area, including "
               "the reworded version — which is exactly the case we care about.")
        _slide(pp, slide_tools,
               "These are the tools. Six reading models, from a tiny one that runs on a laptop up to the strongest we "
               "can host — all free and open source, running on university machines. Plus a slower 're-reader' for the "
               "final shortlist, and Claude, which we already use, as the judge. Claude is the only thing that costs "
               "money, so everything else exists to make sure it only reads pairs worth reading.")
        _slide(pp, slide_questions,
               "We are not just asking which model is best. Two of the three questions came from Or. Should the model "
               "read the theorem alone, or the theorem together with the definitions it relies on? And does "
               "standardising the notation first — one paper's G is another paper's H — make matching better? We also "
               "test combinations, because the honest answer may be to use the old and new methods together.")
        _slide(pp, slide_speed,
               "The obvious worry is speed: 24 billion possible pairs. The trick is that we never ask the AI about a "
               "pair. We ask it once per statement to get its coordinates, and after that comparing is just arithmetic, "
               "which computers do billions of times per second. Asking the AI about every pair would take three years; "
               "our approach takes under a minute, and the whole run is about three hours of free GPU time.")
        _slide(pp, lambda f: slide_results(f, rows),
               "For a first test we hid 40 known answers in the data and measured how near the top each method put "
               "them. Two readings. Combining old and new always beats the new method alone, so we should keep both. "
               "And the old method still wins overall — but that is our test being too easy, not the old method being "
               "better. That is the next slide.")
        _slide(pp, lambda f: slide_ablation(f, bench),
               "This is the whole experiment on one page. Panel one is the important one: word counting already "
               "finds every planted answer at every level of rewording, so our test cannot show what meaning-matching "
               "adds — that is a limit of the test, not a result. Panel two says use the cheapest model. Panels three "
               "and four are the two ideas that lost, and both lost for reasons that look like test artefacts.")
        _slide(pp, slide_caveats,
               "Three flaws, all fixable, none of them about the idea. Our reworded test cases were barely reworded, so "
               "word counting had an unfair advantage. We only ran the weakest model, and it is too small to read the "
               "extra context — so Or's context idea has genuinely not been tested yet. And forty test cases is too few "
               "to trust small gaps. The machinery works; what it is worth is still open.")
        _slide(pp, slide_corpus_run,
               "The full corpus run. Five stages, all measured. The overlap chart is the striking one: the two methods share "
               "only five percent of their candidates, so the semantic arm really is looking somewhere new. And the middle "
               "chart is the lesson — judging by similarity alone found nothing, while re-reading the SAME candidates with a "
               "second model found two real matches. Ranking, not retrieval, was the bottleneck.")
        _slide(pp, slide_finding,
               "This is the pair it found. A 2010 paper states the Feder-Vardi dichotomy conjecture as its open problem; a "
               "2018 paper proves it and never cites the first. Different subfields, no shared wording, and the old method "
               "never produced this pair. But it is not a discovery: that proof is famous. Our novelty check only asks "
               "whether B cites A, which cannot tell us whether the field already knows. Fixing that is the next job.")
        _slide(pp, slide_status,
               "So where does that leave us. The hundred-thousand-paper run is done and it works: five stages end to "
               "end, a quarter of a million candidate pairs word counting never had, and re-reading beating similarity "
               "alone on the same shortlist. But we ran the smallest of six reading models, and — more importantly — we "
               "still cannot tell whether a match the machine finds is genuinely unnoticed or simply famous. The one "
               "real pair we found was a celebrated theorem. So the question for today is whether we scale this up to "
               "all of arXiv, or first build the check that separates a discovery from a rediscovery. My view is the "
               "second: scaling a pipeline that cannot recognise what the field already knows just produces more "
               "famous theorems.")

        _slide(pp, slide_metric_why,
               "A separate thread, on the parser rather than retrieval. We score the parser by asking whether each piece "
               "it pulled out matches a piece Opus labelled, with the same label and roughly the same start and end. "
               "That one rule is quietly punishing three unrelated things. Every example here is a structure the parser "
               "found correctly and is still marked wrong: a definition living inside a proof, a definition cut a few "
               "words differently, and a statement we called a definition and Opus called a lemma. Of 395 supposed "
               "mistakes on 77 papers, nine are genuinely wrong.")
        _slide(pp, slide_metric_ladder)

        _slide(pp, slide_erdos,
               "Last thread. We took the published list of 1,217 Erdős problems and asked which of them appear anywhere "
               "in our hundred thousand papers. The first answer was 95.8 percent, which is nonsense — if you keep the "
               "single closest of a hundred thousand statements, something always looks close. The distribution is one "
               "smooth hump with no gap, so there is no cut-off that separates real from coincidence. Two things are "
               "genuinely wrong underneath: a handful of long generic statements get matched to dozens of unrelated "
               "problems, and some of those are extraction junk rather than real conjectures. But the top of the ranking "
               "is a real hit — Erdős–Gallai, word for word — so the fix is to rank and let Claude judge the top slice, "
               "exactly as the open-problem pipeline does. Do not quote a coverage percentage from this run.")
        _slide(pp, slide_erdos_examples,
               "Here is what those matches look like, so you can judge for yourself. Row one is the machine getting it "
               "right: the Erdős–Gallai conjecture, stated almost word for word in a 2013 paper, and it came out top of "
               "all 1,063. Row two is the same area of mathematics but not the same statement — that is exactly the case "
               "a human or Claude has to settle. Rows three and four are the failure mode: the sentences have the same "
               "shape, so counting shared words scores them high, but one is about twin primes and the other about "
               "graph colourings. Row five is not a matching failure at all — the text on our side is a LaTeX macro we "
               "never expanded, which is a bug in the parser worth fixing regardless of this task.")
        _slide(pp, slide_erdos_next,
               "Where this goes. The word-matching pass is finished and we understand exactly why its headline number is "
               "meaningless. The meaning-matching pass is on the cluster now, reusing coordinates we already paid for, so "
               "it is minutes rather than a rebuild. After that the order matters: first clean up the statements that "
               "match everything and let Claude judge the top of the list, then try the stronger reading models, and only "
               "then ask whether one of our theorems actually resolves an Erdős problem — that is a different question "
               "and it needs coverage to work first. Step three is the new one and worth flagging: instead of us "
               "building the search, hand Claude the corpus and the tools and let it hunt for a solution the way a "
               "person would — follow a citation, look up a definition, try a related theorem. Everything else here "
               "ranks candidates for a human; that would let the machine do the looking. The honest limit is on the red "
               "bar: one confirmed match is not enough to score any of this.")

    print(f"[report] wrote {out}")


if __name__ == "__main__":
    main()
