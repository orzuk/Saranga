"""Meeting brief: what changed in Appendix F (NERDS) between the two versions.

    python discovery_suite/report/make_apxF_diff_pdf.py

Seven slides. The previous version is _local_reference/appendixF_build/appendixF_new.pdf
(6 pages); the current one is saranga_arxiv.pdf pages 30-40 (11 pages). Every
number is read off an artifact of the merged_eval_v51_train60_v2 run or off the
held-out scoring pass in heldout_eval_selected146/heldout_scores.jsonl.

Layout helpers follow make_sep01_pdf.py so the decks read as a series.
"""
from __future__ import annotations
import textwrap
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update({"font.size": 13, "axes.titlesize": 15, "axes.titleweight": "bold",
                     "figure.dpi": 150, "savefig.dpi": 150})
FIG = (13.33, 7.5)
NAVY, GREY = "#12324f", "#555"
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
RED, GREEN, PURPLE, BROWN = "#cb2d2d", "#2ca25f", "#7b4fa8", "#8a5a2b"
BLUE, ORANGE = "#2c6fbb", "#e6820e"      # verdict hues on the download table

_SECTIONS = [(1, 1, "WHAT CHANGED"), (2, 3, "SPEC vs WHAT RAN"),
             (4, 4, "SELECTION"), (5, 6, "EVIDENCE"), (7, 7, "HOUSEKEEPING"),
             (8, 8, "CORPUS STATUS")]

def _title(fig, t, sub=None):
    fig.text(0.06, 0.905, t, fontsize=24, fontweight="bold", color=NAVY)
    if sub: fig.text(0.06, 0.848, sub, fontsize=14, color=GREY)
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.828, 0.828], color=NAVY, lw=2))

def _notes(fig, text):
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.135, 0.135], color="#c9c9c9", lw=1))
    fig.text(0.06, 0.108, "▶ SAY", fontsize=10.5, fontweight="bold", color="#a3a3a3")
    fig.text(0.115, 0.117, textwrap.fill(text, width=130), fontsize=10.8, color=GREY, va="top")

def _chip(fig, x, y, text, color):
    fig.text(x, y, text, fontsize=9.5, fontweight="bold", color="w",
             bbox=dict(boxstyle="round,pad=0.34", fc=color, ec="none"))


def _panel(fig, x, y, w, h, color, alpha=0.075):
    ax = fig.add_axes([x, y, w, h]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.004, 0.004), 0.992, 0.992,
                 boxstyle="round,pad=0.004,rounding_size=0.02",
                 fc=color, alpha=alpha, ec=color, lw=1.5))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); return ax

def _statbox(fig, x, y, w, h, big, lbl, sub, col):
    ax = _panel(fig, x, y, w, h, col)
    ax.text(.5, .70, big, ha="center", va="center", fontsize=30, fontweight="bold", color=col)
    ax.text(.5, .36, lbl, ha="center", va="center", fontsize=11.5, fontweight="bold", color=INK)
    if sub: ax.text(.5, .15, sub, ha="center", va="center", fontsize=9.5, color=GREY)

def _rows(ax, items, y0=0.94, dy=0.235, fs=12.5, bullet="–"):
    for i, (head, body) in enumerate(items):
        y = y0 - i * dy
        ax.text(0.045, y, bullet, fontsize=fs, color=MUTED, va="top")
        ax.text(0.10, y, head, fontsize=fs, fontweight="bold", color=INK, va="top")
        if body:
            ax.text(0.10, y - 0.062, textwrap.fill(body, 52), fontsize=10.5,
                    color=GREY, va="top", linespacing=1.45)


def _why_rows(ax, items, y0=0.95, dy=0.245, fs=12.0):
    """head / what it was / why it went, the last one colour-coded."""
    for i, (head, what, why) in enumerate(items):
        y = y0 - i * dy
        ax.text(0.02, y, "–", fontsize=fs, color=MUTED, va="top")
        ax.text(0.075, y, head, fontsize=fs, fontweight="bold", color=INK, va="top")
        ax.text(0.075, y - 0.055, textwrap.fill(what, 56), fontsize=10.0,
                color=GREY, va="top", linespacing=1.4)
        ax.text(0.075, y - 0.125, "why:  " + textwrap.fill(why, 52).replace("\n", "\n          "),
                fontsize=10.2, color=RED, va="top", linespacing=1.4)


def _slide(pp, fn, say):
    fig = plt.figure(figsize=FIG); fig.patch.set_facecolor("white")
    fn(fig); _notes(fig, say)
    pp.savefig(fig); plt.close(fig)


# ── measured inputs ──────────────────────────────────────────────────────────
HELD = {"base": 0.6865, "full": 0.7538, "sel": 0.7563}      # M3, 140 held-out papers
POOL = {"kept": 146, "dropped": 111, "excluded": 43}         # of 300 selectable units
SHARE_N = [49, 37, 14]                                       # % of rules
SHARE_T = [42, 29, 29]                                       # % of parsing time

# The FP-judge queue, off the same held-out scoring pass. M3 leaves 1,889
# unmatched extractions against 8,772 that count as hits; the M1 lens leaves
# 4,299, but most of that extra is nesting and span boundaries the ladder
# already prices, so the panel is pointed at the M3 residual only.
FPJ = {"m3_fp": 1889, "m1_fp": 4299, "m3_tp": 8772, "papers": 140,
       "judges": 4, "quorum": 3}
FPJ_TYPES = [("remark", 1126), ("claim", 259), ("definition", 232),
             ("assumption", 64), ("open problem", 53), ("theorem", 51),
             ("example", 30), ("proposition", 29), ("all others", 45)]
JUDGES = [("qwen3-32b-awq", "Alibaba"), ("mistral-small-24b", "Mistral"),
          ("gemma-3-27b-it", "Google"), ("llama-3.3-70b", "Meta")]

# ── regex complexity of the released rules ───────────────────────────────────
# Static verdicts: regexploit over all 388 live patterns in
# merged_eval_v51_train60_v2/groups/*/distilled_rules.py. Timings: one
# finditer pass of every pattern over the 17 tier-2 .tex sources
# (1,631,502 chars), 10 s cap per pattern-paper pair.
RX = {"live": 388, "compiled": 527, "pruned": 139,
      "linear": 370, "cubic": 2, "quartic": 1, "exponential": 15,
      "total_s": 533.3, "papers": 17, "per_paper": 31.4,
      "top20_share": 66.9, "exp_share": 2.7, "core_years": 2.98,
      "slowest": ("R9_IS_EQUATION", 71.4)}
# 0-based ranks of the flagged rules once all 388 are sorted by measured time
RX_EXP_RANK = [35, 38, 39, 51, 57, 134, 141, 146, 248, 252, 284, 288, 289, 291, 345]
RX_POLY_RANK = [33, 64, 94]
# _C2_TAIL_ENV against a run of '$' with no closing period: input chars → seconds
RX_BLOWUP = [(24, 0.037), (28, 0.29), (32, 1.56), (36, 7.59)]
# median structure of the 20 slowest measured vs the other 368
RX_PRED = [("DOTALL set", "100%", "77%", True),
           ("pattern length", "311", "178", True),
           ("unbounded quantifiers", "10", "7", True),
           ("star height", "2", "2", False)]


def slide_overview(fig):
    _title(fig, "Appendix F, rewritten",
           "From a specification of the method to a description of the run that produced the released rules")
    _statbox(fig, 0.06, 0.55, 0.26, 0.20, "6 → 11", "pages", "and a different job", NAVY)
    _statbox(fig, 0.37, 0.55, 0.26, 0.20, "6", "components removed", "specified, never ran", RED)
    _statbox(fig, 0.68, 0.55, 0.26, 0.20, "1 → 8", "results exhibits", "figures and tables", GREEN)

    ax = _panel(fig, 0.06, 0.19, 0.42, 0.32, RED)
    ax.text(.5, .90, "BEFORE", ha="center", fontsize=12, fontweight="bold", color=RED)
    ax.text(.06, .70, "“The released rule set was produced by an\n"
                      "earlier configuration of the same loop …\n"
                      "re-running distillation under the\n"
                      "specification above is in progress.”",
            fontsize=11, color=INK, style="italic", va="top")
    ax.text(.06, .20, "A spec the numbers did not come from.", fontsize=10.5, color=GREY)

    ax = _panel(fig, 0.52, 0.19, 0.42, 0.32, GREEN)
    ax.text(.5, .90, "NOW", ha="center", fontsize=12, fontweight="bold", color=GREEN)
    ax.text(.06, .70, "Every equation, figure and table is\n"
                      "backed by an artifact of the 40-paper\n"
                      "v5.1 run — and the outer numbers are\n"
                      "real parses on held-out papers.",
            fontsize=11, color=INK, va="top")
    ax.text(.06, .20, "No disclaimer needed.", fontsize=10.5, color=GREY)


def slide_removed(fig):
    _title(fig, "Removed — specified, never executed",
           "Each was written as part of the method; none of it ran")
    ax = fig.add_axes([0.05, 0.17, 0.44, 0.64]); ax.axis("off")
    _why_rows(ax, [
        ("Graded type compatibility  κ",
         "sim = a·κ(τ,τ′), plus a full κ table as its own subsection.",
         "Real code, but only cross-paper alignment calls it. Distillation matches inside a type bucket — a hard gate."),
        ("Group alignment",
         "Three passes: unambiguous pairs, splits, merges, with overlap guards.",
         "Never implemented. M₃ addresses the same granularity problem by a different mechanism."),
        ("Rule registry",
         "Immutable ids, active/retired status, rule file as a projection.",
         "Built in distill_registry.py, but the merged runner never imports it."),
    ])
    ax = fig.add_axes([0.52, 0.17, 0.44, 0.64]); ax.axis("off")
    _why_rows(ax, [
        ("Recycling + attribution",
         "Revive a retired rule that fires on a new miss; charge each output to one rule.",
         "Recycling never ran. Attribution exists only in the post-hoc subset search."),
        ("λ-penalised objective",
         "argmax F₁(Θ) − λ|Θ| by backward elimination, reporting a λ-frontier.",
         "No λ anywhere in the run. The size came from cross-validation instead."),
        ("The five-item ablation list",
         "κ→identity, group alignment, recycling, λ=0, add-only.",
         "All five ablate components that never ran, so none could be performed."),
    ])
    fig.text(0.06, 0.155,
             "Common thread: the appendix described a method we intended, not the one that produced the released rules.",
             fontsize=11.5, color=NAVY, fontweight="bold")


def slide_added(fig):
    _title(fig, "Added — what actually ran",
           "Mechanisms that are in the code and left traces in the run")
    ax = fig.add_axes([0.05, 0.22, 0.44, 0.58]); ax.axis("off")
    _rows(ax, [("M₁ / M₂ / M₃ matching ladder",
                "Each rung drops one requirement, so the score gap prices that "
                "disagreement. Replaces κ as the answer to “how strictly do we match”."),
               ("Hardest-first ordering",
                "Papers ranked by dark knowledge exposed, not by score (OHEM)."),
               ("Two properties of PatternMine",
                "Incremental — the inspector extends the current file; and shown the "
                "rules that already failed.")])
    ax = fig.add_axes([0.52, 0.22, 0.44, 0.58]); ax.axis("off")
    _rows(ax, [("Time budget, as a constraint",
                "t_call ≤ T_call and max_P t_doc ≤ T_doc inside Eq. 7. The reason is "
                "scale: the student must run over millions of papers."),
               ("Judge panel, four organisations",
                "qwen3-32b, mistral-small-24b, gemma-3-27b-it, llama-3.3-70b. "
                "No judge shares a lab with the teacher; verdict by consensus."),
               ("Train / test discipline",
                "Held-out papers enter no stage of the loop.")])


def slide_selection(fig):
    _title(fig, "Selection: a different mechanism",
           "Same goal — judge rules as a set, not one at a time — reached a different way")
    ax = _panel(fig, 0.06, 0.44, 0.41, 0.34, RED)
    ax.text(.5, .88, "BEFORE", ha="center", fontsize=12, fontweight="bold", color=RED)
    ax.text(.5, .62, r"$\arg\max_\Theta\ F_1(\mathcal{R}_\Theta) - \lambda|\Theta|$",
            ha="center", fontsize=17, color=INK)
    ax.text(.5, .34, "backward elimination from the full set\nreport the λ-frontier",
            ha="center", fontsize=11, color=GREY)
    ax = _panel(fig, 0.53, 0.44, 0.41, 0.34, GREEN)
    ax.text(.5, .88, "NOW", ha="center", fontsize=12, fontweight="bold", color=GREEN)
    ax.text(.5, .62, r"$\arg\max_{|\Theta|=k}\ F_1(\mathcal{R}_\Theta)$   s.t. time caps",
            ha="center", fontsize=15, color=INK)
    ax.text(.5, .34, "greedy forward + backward pass\nsize k by 5-fold cross-validation",
            ha="center", fontsize=11, color=GREY)
    _statbox(fig, 0.06, 0.18, 0.20, 0.20, "300", "selectable rules", "the pool  ℬ", NAVY)
    _statbox(fig, 0.30, 0.18, 0.20, 0.20, "146", "kept", "49% of the pool", S1)
    _statbox(fig, 0.54, 0.18, 0.20, 0.20, "111", "dropped", "add nothing", MUTED)
    _statbox(fig, 0.78, 0.18, 0.16, 0.20, "43", "over budget", "never scored", RED)


def slide_evidence(fig):
    _title(fig, "The evidence base",
           "One in-sample table → six figures and two tables, all from the 40-paper v5.1 run")
    ax = _panel(fig, 0.06, 0.30, 0.40, 0.48, RED)
    ax.text(.5, .93, "BEFORE", ha="center", fontsize=12, fontweight="bold", color=RED)
    for i, s in enumerate(["one table: 17 papers, 0.71 → 0.81",
                           "explicitly in-sample",
                           "a sub-linearity figure",
                           "one paper's graph, before / after"]):
        ax.text(.08, .76 - i*.14, "–  " + s, fontsize=11.5, color=INK)
    ax = _panel(fig, 0.52, 0.30, 0.42, 0.48, GREEN)
    ax.text(.5, .93, "NOW", ha="center", fontsize=12, fontweight="bold", color=GREEN)
    for i, s in enumerate(["train vs held-out curves",
                           "per-type recall, both regimes  (fig + table)",
                           "rule growth vs pruning; parse cost vs count",
                           "the 40 × 34 per-paper trajectory table",
                           "CV selection curve; rules → time → F₁ flow"]):
        ax.text(.06, .78 - i*.135, "–  " + s, fontsize=11.5, color=INK)
    fig.text(0.06, 0.20, "All real parses. Nothing carried over from the 17-paper run.",
             fontsize=12.5, color=NAVY, fontweight="bold")
    fig.text(0.06, 0.163, "Worth knowing: the search's own scores are estimates composed from per-rule solo runs, "
             "and run ≈0.03 optimistic against a real parse.", fontsize=10.5, color=GREY)


def slide_heldout(fig):
    _title(fig, "New result: the selected rules, on held-out papers",
           "140 papers that entered no stage of distillation or selection · pooled M₃ F₁ · one real parse each")
    ax = fig.add_axes([0.09, 0.30, 0.46, 0.46])
    labels = ["base\nparser", "all\nrules", "selected\n146"]
    vals = [HELD["base"], HELD["full"], HELD["sel"]]
    cols = [BROWN, PURPLE, GREEN]
    b = ax.bar(range(3), vals, 0.55, color=cols)
    for r, v in zip(b, vals):
        ax.text(r.get_x()+r.get_width()/2, v+0.004, f"{v:.4f}", ha="center",
                fontsize=13, fontweight="bold", color=INK)
    ax.set_xticks(range(3)); ax.set_xticklabels(labels, fontsize=11.5)
    ax.set_ylim(0.60, 0.80); ax.set_ylabel("pooled M₃ F₁")
    ax.grid(alpha=.25, axis="y"); ax.spines[["top", "right"]].set_visible(False)
    ax = _panel(fig, 0.60, 0.30, 0.34, 0.46, GREEN)
    ax.text(.5, .88, "Half the rules can go", ha="center", fontsize=15,
            fontweight="bold", color=GREEN)
    ax.text(.07, .68, "Selection used the distillation papers\n"
                      "only. On papers it never saw, the\n"
                      "smaller set scores marginally higher:\n"
                      "0.7563 against 0.7538.",
            fontsize=11.5, color=INK, va="top")
    ax.text(.07, .30, "The claim is that dropping half the\n"
                      "pool costs nothing out of sample —\n"
                      "not that fewer rules are better.",
            fontsize=10.8, color=GREY, va="top")


def slide_housekeeping(fig):
    _title(fig, "Also worth a minute",
           "Three changes that are small in the text and easy to miss on the page")
    ax = _panel(fig, 0.06, 0.46, 0.27, 0.32, S1)
    ax.text(.5, .87, "Pipeline figure", ha="center", fontsize=13, fontweight="bold", color=S1)
    ax.text(.07, .66, "Was a generic three-phase\ndiagram (prompt tuning /\nbenchmarking / distillation).\n\n"
                      "Now the actual silver pipeline,\nwith the held-out set drawn\noutside every stage.",
            fontsize=10.8, color=INK, va="top")
    ax = _panel(fig, 0.365, 0.46, 0.27, 0.32, S4)
    ax.text(.5, .87, "Ablations section", ha="center", fontsize=13, fontweight="bold", color="#a06f00")
    ax.text(.07, .66, "Was five ablations promised,\nnone run.\n\n"
                      "Now “Separability and\nablations”: the two separations\nactually measured, and the\nrest named as not ablated.",
            fontsize=10.8, color=INK, va="top")
    ax = _panel(fig, 0.67, 0.46, 0.27, 0.32, PURPLE)
    ax.text(.5, .87, "Main text", ha="center", fontsize=13, fontweight="bold", color=PURPLE)
    ax.text(.07, .66, "§4 still quotes 0.71 → 0.81\nfrom the 17-paper run, and\ndescribes a complexity-\npenalised objective.\n\n"
                      "Both now disagree with the\nappendix.",
            fontsize=10.8, color=INK, va="top")
    ax = _panel(fig, 0.06, 0.17, 0.88, 0.23, NAVY)
    ax.text(.5, .80, "Open questions for the meeting", ha="center", fontsize=13,
            fontweight="bold", color=NAVY)
    for i, s in enumerate([
        "Do we re-run the results in §4 against the v5.1 run, or keep the 17-paper numbers and label them?",
        "Do the removed components (κ, group alignment, registry, recycling) go back on the roadmap, or out?",
        "The held-out set has now been spent once. Anything else we want measured on it before it stops being clean?"]):
        ax.text(.04, .56 - i*.20, "•  " + s, fontsize=11.3, color=INK)


# ── 8. corpus status: the per-year download table ────────────────────────────
# Same rendering as slide 2 of make_sep01_pdf.py, re-counted 8 Sep 2026 and now
# carrying 2025. Two rows moved since 1 Sep: 2024 finished, and 2025 appeared.
#: year, downloaded, attempted, metadata, err_pdf, err_404, err_403, err_other
_DL_TABLE = """
1991 353 353 353 0 0 0 0
1992 3177 3189 3190 0 9 0 3
1993 6655 6722 6729 11 16 0 40
1994 9861 10036 10078 2 30 12 131
1995 12606 12922 13006 3 24 3 286
1996 15298 15766 15872 5 38 7 418
1997 18938 19422 19610 24 72 9 379
1998 23198 23958 24170 151 88 22 499
1999 26361 27510 27700 302 129 74 644
2000 29259 30656 30671 600 114 64 619
2001 31217 33134 33140 1120 100 78 619
2002 33892 36108 36107 1348 131 142 595
2003 36794 39393 39392 1838 171 90 500
2004 40266 43713 43714 2509 215 286 437
2005 42661 46871 46881 2997 271 427 515
2006 45622 50295 50314 3366 285 579 443
2007 50175 55728 55752 4184 319 559 491
2008 52723 58827 58810 4584 373 754 393
2009 57533 64072 64071 4968 458 691 422
2010 62275 70250 70288 6173 708 397 697
2011 68299 76202 76602 6171 728 309 695
2012 74052 84358 84374 8740 833 419 314
2013 81768 92872 92875 10091 742 6 265
2014 86822 97597 97590 9861 687 19 208
2015 94383 104927 105130 9627 738 1 178
2016 102289 113477 113440 10275 713 0 200
2017 111738 123746 123781 11178 645 0 185
2018 126053 140381 140377 13439 681 2 206
2019 140024 155698 155917 14776 771 0 127
2020 159694 178321 178275 17686 810 0 131
2021 162901 181523 181599 17342 791 1 488
2022 168863 185947 185987 16019 804 0 261
2023 190151 209017 209223 17780 793 0 293
2024 222783 243781 243781 20224 658 36 80
2025 237505 258705 288705 20140 945 0 115
"""
# 2025 metadata is not harvested yet; 288,705 is attempted + 30k, a placeholder.
# It is the only estimated cell on the slide, and the only reason 2025's
# "% attempted" reads below 99%.
_DL_ESTIMATED_MD = {2025}

_DL_KEYS = ("y", "dl", "at", "md", "pdf", "e404", "e403", "eo")


def _dl_rows():
    out = []
    for line in _DL_TABLE.strip().splitlines():
        d = dict(zip(_DL_KEYS, (int(v) for v in line.split())))
        # metadata sits a few papers below attempted in some years (metadata
        # refreshed after the fetch); clamp so the gap never goes negative.
        d["gap"] = max(0, d["md"] - d["at"])
        d["err"] = d["e404"] + d["e403"] + d["eo"]
        out.append(d)
    return out


DR = _dl_rows()
DS = {k: sum(d[k] for d in DR)
      for k in ("dl", "at", "md", "pdf", "e404", "e403", "eo", "err", "gap")}

#: the same three totals as they stood at the 1 Sep 2026 meeting (1991-2024),
#: so the slide can show the move rather than just the level.
DL_PREV = dict(dl=2379467, at=2613614, md=2644759)


#: Cell shading. Each returns a colour for the value, or None for "no opinion".
def _c_pct(v, good, ok):
    return GREEN if v >= good else (ORANGE if v >= ok else RED)


def _c_err(v, good, ok):
    return GREEN if v < good else (ORANGE if v < ok else RED)


def slide_corpus(fig):
    _title(fig, "The whole-arXiv download",
           "1991–2025, every arXiv paper, LaTeX source. Counted 8 September 2026.")

    # headline funnel
    ax = fig.add_axes([0.06, 0.615, 0.88, 0.185]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    stages = [
        (f"{DS['md']:,}", "papers on arXiv\n(metadata harvested)", GREY),
        (f"{DS['at']:,}", f"we asked for the source\n({100*DS['at']/DS['md']:.1f}%)", BLUE),
        (f"{DS['dl']:,}", f"LaTeX source in hand\n({100*DS['dl']/DS['md']:.1f}% of all arXiv)", GREEN),
    ]
    for i, (big, small, col) in enumerate(stages):
        x = i * 0.345
        ax.add_patch(FancyBboxPatch((x, 0.08), 0.295, 0.86,
                                    boxstyle="round,pad=0.006,rounding_size=0.04",
                                    fc=col, alpha=0.12, ec=col, lw=1.6))
        ax.text(x + 0.147, 0.60, big, ha="center", fontsize=25, fontweight="bold", color=col)
        ax.text(x + 0.147, 0.27, small, ha="center", fontsize=10.5, color=GREY)
        if i < 2:
            ax.annotate("", xy=(x + 0.338, 0.51), xytext=(x + 0.300, 0.51),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, lw=2))

    # per-year stacked bars
    cx = fig.add_axes([0.075, 0.235, 0.865, 0.325])
    ys = [d["y"] for d in DR]
    dl = np.array([d["dl"] for d in DR]) / 1000
    er = np.array([d["pdf"] + d["err"] for d in DR]) / 1000
    gp = np.array([d["gap"] for d in DR]) / 1000
    cx.bar(ys, dl, color=GREEN, alpha=0.88, zorder=3)
    cx.bar(ys, er, bottom=dl, color=ORANGE, alpha=0.85, zorder=3)
    cx.bar(ys, gp, bottom=dl + er, color="#d8dde2", zorder=3,
           hatch=["//" if y in _DL_ESTIMATED_MD else "" for y in ys],
           edgecolor="#aab2ba", linewidth=0)
    cx.set_ylabel("papers  (thousands)", fontsize=10, color=GREY)
    cx.set_xticks([1991, 1995, 2000, 2005, 2010, 2015, 2020, 2025])
    cx.tick_params(labelsize=10, colors=GREY, length=0)
    cx.grid(axis="y", color="#ececec", zorder=0)
    for side in ("top", "right", "left"):
        cx.spines[side].set_visible(False)
    cx.spines["bottom"].set_color("#cccccc")
    cx.set_ylim(0, 340)
    cx.annotate("", xy=(2025, 296), xytext=(2025, 328),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.6,
                                shrinkA=0, shrinkB=0))
    cx.text(2024.4, 333, "2025 backlog is the 30k placeholder", fontsize=10.5,
            color=MUTED, fontweight="bold", ha="right")
    for i, (lbl, col) in enumerate([("source in hand", GREEN),
                                    ("attempted, no source", ORANGE),
                                    ("not fetched yet", "#b6bec6")]):
        fig.text(0.10 + i * 0.16, 0.575, "■ " + lbl, fontsize=10,
                 fontweight="bold", color=col)

    # what moved since the last meeting
    d_dl = DS["dl"] - DL_PREV["dl"]
    fig.text(0.06, 0.183,
             f"+{d_dl:,} papers since 1 Sep — 2024 closed out and 2025 came in whole.",
             fontsize=14.5, fontweight="bold", color=NAVY)
    fig.text(0.06, 0.152,
             "Outside 2025 the never-fetched backlog is 2,141 papers across 35 years. The 30,000 shown on 2025 is the "
             "metadata placeholder, not a counted shortfall.",
             fontsize=10, color=GREY)
    _chip(fig, 0.755, 0.905, "MEASURED · download log", GREEN)


def slide_download(fig):
    _title(fig, "Where the corpus stands, 1991–2025",
           "One row per year, counted 8 September 2026. "
           "Colour is the verdict on that cell, not a second number.")

    cols = ["year", "downloaded", "attempted", "metadata", "err PDF",
            "404", "403", "other", "% attempted", "% downloaded"]
    w = [0.058, 0.113, 0.113, 0.113, 0.100, 0.083, 0.083, 0.092, 0.116, 0.129]
    xs = [sum(w[:j]) for j in range(len(w))]

    ax = fig.add_axes([0.045, 0.205, 0.912, 0.602]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    rh = 0.0255
    ytop = 0.962
    for j, (c, ww) in enumerate(zip(cols, w)):
        ax.text(xs[j] if j == 0 else xs[j] + ww - 0.006, ytop + 0.028, c,
                fontsize=8.0, fontweight="bold", color=GREY,
                ha="left" if j == 0 else "right")
    ax.add_patch(plt.Rectangle((0, ytop + 0.019), 1.0, 0.0035, fc="#bbbbbb", ec="none"))

    rows = DR + [dict(y="TOTAL", dl=DS["dl"], at=DS["at"], md=DS["md"],
                      pdf=DS["pdf"], e404=DS["e404"], e403=DS["e403"], eo=DS["eo"])]

    for i, d in enumerate(rows):
        y = ytop - i * rh
        total = d["y"] == "TOTAL"
        pa = 100 * min(d["at"], d["md"]) / d["md"]      # of arXiv, we asked for
        pd_ = 100 * d["dl"] / d["at"]                   # of what we asked for, we got
        if total:
            ax.add_patch(plt.Rectangle((0, y - 0.009), 1.0, 0.0035, fc="#bbbbbb", ec="none"))
        elif i % 2 == 0:
            ax.add_patch(plt.Rectangle((0, y - 0.008), 1.0, rh - 0.003,
                                       fc="#f5f8fa", ec="none", zorder=0))

        e_pdf = 100 * d["pdf"] / d["at"]
        e_404 = 100 * d["e404"] / d["at"]
        e_403 = 100 * d["e403"] / d["at"]
        e_oth = 100 * d["eo"] / d["at"]
        est = d["y"] in _DL_ESTIMATED_MD
        cells = [
            (str(d["y"]), None),
            (f"{d['dl']:,}", None),
            (f"{d['at']:,}", None),
            (f"{d['md']:,}" + ("*" if est else ""), None),
            (f"{d['pdf']:,}", _c_err(e_pdf, 2, 8)),
            (f"{d['e404']:,}", _c_err(e_404, 0.4, 1.0)),
            (f"{d['e403']:,}", _c_err(e_403, 0.1, 0.6)),
            (f"{d['eo']:,}", _c_err(e_oth, 0.4, 1.5)),
            (f"{pa:.1f}%" + ("*" if est else ""), _c_pct(pa, 99, 90)),
            (f"{pd_:.1f}%", _c_pct(pd_, 95, 85)),
        ]
        for j, ((txt, col), ww) in enumerate(zip(cells, w)):
            if col is not None:
                ax.add_patch(FancyBboxPatch((xs[j] + 0.006, y - 0.0062),
                                            ww - 0.012, rh - 0.008,
                                            boxstyle="round,pad=0.0005,rounding_size=0.004",
                                            fc=col, alpha=0.16, ec="none", zorder=1))
            ax.text(xs[j] if j == 0 else xs[j] + ww - 0.006, y, txt,
                    fontsize=7.6, ha="left" if j == 0 else "right", zorder=3,
                    color=(col if col and total else (NAVY if j == 0 or total else "#333")),
                    fontweight="bold" if (total or j == 0 or j == 9) else "normal")

    keys = [
        (GREEN, "healthy", "≥99% attempted · ≥95% downloaded"),
        (ORANGE, "watch", "90–99% · 85–95%"),
        (RED, "gap", "<90% · <85% — the years to re-run"),
    ]
    fig.text(0.045, 0.185, "COLOUR KEY", fontsize=8.8, fontweight="bold", color="#a3a3a3")
    for i, (col, name, gloss) in enumerate(keys):
        x = 0.128 + i * 0.268
        fig.text(x, 0.183, "■", fontsize=12, color=col, alpha=0.55)
        fig.text(x + 0.019, 0.185, name, fontsize=9.2, fontweight="bold", color=col)
        fig.text(x + 0.019 + 0.053, 0.185, gloss, fontsize=8.6, color=GREY)

    d_dl = DS["dl"] - DL_PREV["dl"]
    fig.text(0.045, 0.163,
             f"+{d_dl:,} papers since 1 Sep — 2024 finished and 2025 is in. "
             f"‘% attempted’ is attempted/metadata; ‘% downloaded’ is downloaded/attempted.",
             fontsize=10.5, color=NAVY, fontweight="bold")
    fig.text(0.045, 0.146,
             "*  2025 metadata is not harvested yet — 288,705 is attempted + 30k, a placeholder. It is the only "
             "estimated cell here, and the only reason 2025 reads below 99% attempted.",
             fontsize=8.8, color=GREY)
    _chip(fig, 0.755, 0.905, "MEASURED · download log", GREEN)


def slide_fp_judge(fig):
    _title(fig, "Last stage: the false-positive judge panel",
           "Every M₃ false positive on the 140 held-out papers, re-read by four open-weight judges · "
           "3 of 4 must agree · read-only")

    _statbox(fig, 0.06, 0.615, 0.26, 0.155, f"{FPJ['m3_fp']:,}", "false positives to judge",
             f"against {FPJ['m3_tp']:,} that already count as hits", ORANGE)
    _statbox(fig, 0.37, 0.615, 0.26, 0.155, f"{FPJ['judges'] * FPJ['m3_fp']:,}", "verdicts to collect",
             f"{FPJ['judges']} judges × every false positive", PURPLE)
    _statbox(fig, 0.68, 0.615, 0.26, 0.155, f"{FPJ['quorum']} of {FPJ['judges']}", "consensus to call it",
             "below quorum is a split, not a resolution", GREEN)

    # Where the work actually is: three types carry six sevenths of the queue.
    fig.text(0.115, 0.573, "Remark, claim and definition are 86% of the queue",
             fontsize=10.2, fontweight="bold", color=NAVY)
    ax = fig.add_axes([0.115, 0.325, 0.335, 0.225])
    names = [t for t, _ in FPJ_TYPES][::-1]
    vals = [c for _, c in FPJ_TYPES][::-1]
    cols = [ORANGE if v >= 200 else (S1 if v >= 50 else MUTED) for v in vals]
    ax.barh(range(len(vals)), vals, 0.68, color=cols)
    for i, v in enumerate(vals):
        ax.text(v + 20, i, f"{v:,}", va="center", fontsize=9.0,
                fontweight="bold" if v >= 200 else "normal", color=INK)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9.2)
    ax.set_xlim(0, 1330)
    ax.tick_params(axis="x", labelsize=8.2)
    ax.grid(alpha=.22, axis="x")
    ax.spines[["top", "right"]].set_visible(False)

    ax = _panel(fig, 0.50, 0.325, 0.44, 0.225, NAVY)
    ax.text(.5, .89, "What each judge is asked", ha="center", fontsize=12.5,
            fontweight="bold", color=NAVY)
    ax.text(.045, .695, "GENUINE", fontsize=10.5, fontweight="bold", color=GREEN)
    ax.text(.30, .725, "a real instance the silver corpus missed —\nthe rule was right, the reference is thin",
            fontsize=9.8, color=INK, va="top")
    ax.text(.045, .455, "FALSE POSITIVE", fontsize=10.5, fontweight="bold", color=RED)
    ax.text(.30, .485, "not an instance at all — the parser grabbed\nprose, boilerplate or a fragment",
            fontsize=9.8, color=INK, va="top")
    ax.add_artist(plt.Line2D([.045, .955], [.305, .305], color="#c9c9c9", lw=1))
    ax.text(.045, .235, "Four organisations, none of them the one that wrote the silver corpus,",
            fontsize=9.0, color=GREY, va="top")
    ax.text(.045, .155, "so no model reviews its own output:", fontsize=9.0, color=GREY, va="top")
    ax.text(.045, .072, " · ".join(m for m, _ in JUDGES), fontsize=8.8,
            color=NAVY, fontweight="bold", va="top")

    ax = _panel(fig, 0.06, 0.150, 0.88, 0.135, ORANGE)
    ax.text(.014, .80, "OPEN ISSUE", fontsize=9.5, fontweight="bold", color=ORANGE)
    ax.text(.105, .80, "Context and answer budget — to fix before the run",
            fontsize=11, fontweight="bold", color=INK)
    ax.text(.014, .56, textwrap.fill(
        "Batching several spans into one prompt is what makes 7,556 verdicts affordable, but a batch of long remark "
        "and proof spans plus a JSON reply overruns the answer budget and the array comes back truncated. Items the "
        "model never answered are recorded as unanswered rather than folded into a verdict — so the cost today is "
        "lost coverage, not wrong numbers.", 148),
        fontsize=9.6, color=GREY, va="top", linespacing=1.5)


def slide_regex_cost(fig):
    _title(fig, "What actually makes a rule slow",
           "All 388 live rules · static worst-case (regexploit) against measured time on the 17 tier-2 papers")

    _statbox(fig, 0.06, 0.632, 0.26, 0.148, f"{RX['live']}", "live rules",
             f"{RX['compiled']} compiled, {RX['pruned']} already pruned out", NAVY)
    _statbox(fig, 0.37, 0.632, 0.26, 0.148,
             f"{RX['exponential'] + RX['cubic'] + RX['quartic']}", "flagged non-linear",
             f"{RX['exponential']} exponential — every one in definition", RED)
    _statbox(fig, 0.68, 0.632, 0.26, 0.148, f"{RX['per_paper']:.0f} s", "regex time per paper",
             f"≈{RX['core_years']:.1f} core-years to parse 3M", PURPLE)

    # ── every rule as a dot, ordered by the time it actually cost ────────────
    fig.text(0.06, 0.588, "Every rule, ordered by the time it actually cost — slowest first",
             fontsize=10.4, fontweight="bold", color=NAVY)
    fig.text(0.06, 0.564, f"nothing static analysis flagged is expensive; the first flagged rule "
                          f"ranks {min(RX_EXP_RANK) + 1}th", fontsize=9.4, color=GREY)

    cols = 36
    ax = fig.add_axes([0.06, 0.318, 0.50, 0.232]); ax.axis("off")
    ax.set_xlim(-1.1, cols + 0.1)
    ax.set_ylim(-(RX["live"] // cols) - 1.2, 1.5)
    exp, poly = set(RX_EXP_RANK), set(RX_POLY_RANK)
    for i in range(RX["live"]):
        x, y = i % cols, -(i // cols)
        if i < 20:
            ax.plot(x, y, "o", ms=6.2, mfc=S1, mec="none", zorder=3)
        elif i in exp:
            ax.plot(x, y, "o", ms=6.2, mfc=RED, mec="none", zorder=3)
        elif i in poly:
            ax.plot(x, y, "o", ms=5.8, mfc="white", mec=RED, mew=1.6, zorder=3)
        else:
            ax.plot(x, y, "o", ms=5.4, mfc="#dcdcd6", mec="none", zorder=2)

    ax.plot([-0.45, 19.45], [0.85, 0.85], color=S1, lw=1.4, zorder=4)
    for xx in (-0.45, 19.45):
        ax.plot([xx, xx], [0.63, 0.85], color=S1, lw=1.4, zorder=4)
    ax.text(9.5, 1.06, f"these 20 rules are {RX['top20_share']:.0f}% of all runtime",
            ha="center", fontsize=9.6, fontweight="bold", color=S1)

    for i, (lbl, mfc, mec) in enumerate([
            ("20 slowest measured", S1, "none"),
            (f"exponential ({RX['exponential']})", RED, "none"),
            (f"polynomial ({RX['cubic'] + RX['quartic']})", "white", RED),
            (f"linear and cheap ({RX['linear'] - 20})", "#dcdcd6", "none")]):
        x = 0.062 + i * 0.122
        fig.add_artist(plt.Line2D([x], [0.302], marker="o", ms=6.2, mfc=mfc, mec=mec,
                                  mew=1.6, ls="none", transform=fig.transFigure))
        fig.text(x + 0.012, 0.298, lbl, fontsize=8.6, color=GREY)

    fig.text(0.06, 0.274, "Star height — the metric you would reach for first — is identical in both "
                          "groups (median 2).", fontsize=9.0, color=GREY)
    fig.text(0.06, 0.256, "What separates the slow twenty: DOTALL (100% of them vs 77%), pattern "
                          "length (311 vs 178), unbounded quantifiers (10 vs 7).",
             fontsize=9.0, color=GREY)

    # ── flagged share vs measured share ─────────────────────────────────────
    fig.text(0.615, 0.588, "Share of rules against share of cost", fontsize=10.4,
             fontweight="bold", color=NAVY)
    fig.text(0.615, 0.564, "static analysis picks the wrong fifteen", fontsize=9.4, color=GREY)

    pairs = [(0.443, "20 slowest measured", S1, 100 * 20 / RX["live"], RX["top20_share"]),
             (0.330, f"{RX['exponential']} flagged exponential", RED,
              100 * RX["exponential"] / RX["live"], RX["exp_share"])]
    for k, (y0, name, col, pr, pt) in enumerate(pairs):
        a = fig.add_axes([0.715, y0, 0.225, 0.072])
        a.barh([1, 0], [pr, pt], 0.62, color=[MUTED, col])
        for yy, v, c in ((1, pr, MUTED), (0, pt, col)):
            a.text(v + 2.5, yy, f"{v:.1f}%", va="center", fontsize=9.0,
                   fontweight="normal" if c is MUTED else "bold",
                   color=INK if c is MUTED else c)
        a.set_yticks([1, 0]); a.set_yticklabels(["of rules", "of runtime"], fontsize=8.8)
        a.set_xlim(0, 100); a.set_ylim(-0.55, 1.55)
        a.grid(alpha=.22, axis="x")
        a.spines[["top", "right"]].set_visible(False)
        if k == 0:
            a.set_xticklabels([])
            a.tick_params(axis="x", length=0)
            a.spines["bottom"].set_color("#cfcfcf")
        else:
            a.tick_params(axis="x", labelsize=8.0)
        fig.text(0.715, y0 + 0.079, name, fontsize=9.2, fontweight="bold", color=col)

    # ── the one idiom behind all fifteen ────────────────────────────────────
    ax = _panel(fig, 0.06, 0.146, 0.60, 0.094, RED)
    ax.text(.012, .82, "ONE IDIOM, ALL FIFTEEN", fontsize=9.2, fontweight="bold", color=RED)
    ax.text(.012, .50, r"(?: \begin{..}.*?\end{..} | $$.*?$$ | \[.*?\] | [^.] )*\.",
            fontsize=10.0, family="monospace", color=INK, va="center", parse_math=False)
    ax.text(.012, .16, "the catch-all [^.] overlaps the math branches, so the star can split the "
                       "same text many ways", fontsize=8.8, color=GREY, va="center")

    ax = _panel(fig, 0.68, 0.146, 0.26, 0.094, ORANGE)
    ax.text(.03, .82, "MEASURED BLOW-UP", fontsize=9.2, fontweight="bold", color=ORANGE)
    ax.text(.03, .50, "  ".join(f"{c}ch {s}s" for c, s in RX_BLOWUP),
            fontsize=8.6, family="monospace", color=INK, va="center")
    ax.text(.03, .16, "×5 per 2 characters · 2 rules hit the 10 s cap on real papers",
            fontsize=8.5, color=GREY, va="center")

    _chip(fig, 0.762, 0.905, "MEASURED · 17 tier-2 papers", GREEN)


def main():
    out = Path(__file__).with_name("apxF_changes_brief.pdf")
    with PdfPages(out) as pp:
        _slide(pp, slide_overview,
               "The appendix went from six pages to eleven, but the real change is what it is for. The old one opened by "
               "admitting the method it described was not the method that produced the numbers. This one describes the run "
               "that produced the released rules, so that admission is gone.")
        _slide(pp, slide_removed,
               "Six things came out. Every one of them was written as part of the method and none of them ever ran. Kappa is "
               "real code but only the cross-paper alignment uses it; the registry is built but the runner never imports it; "
               "group alignment was never implemented at all. The five ablations were promised and never done.")
        _slide(pp, slide_added,
               "And this is what went in — all of it in the code and visible in the run. The matching ladder is the one to "
               "look at: it replaces kappa as the answer to how strictly we match, and each rung drops exactly one "
               "requirement so the gap between two rungs prices that kind of disagreement.")
        _slide(pp, slide_selection,
               "Selection changed shape. Before: subtract a penalty on rule count and eliminate backwards. Now: greedy "
               "forward with a backward pass, the size chosen by cross-validation, and a hard time cap per rule. Three "
               "hundred candidates in, a hundred and forty-six kept, forty-three thrown out for cost alone.")
        _slide(pp, slide_evidence,
               "The evidence base is the biggest visible change. One in-sample table became six figures and two tables, all "
               "from the forty-paper run and all real parses. One caveat to carry: the search scores subsets by composing "
               "per-rule runs, and that estimate sits about three points of a percent optimistic against a real parse.")
        _slide(pp, slide_heldout,
               "This is the new result. We took the hundred and forty-six selected rules and parsed the hundred and forty "
               "held-out papers with them — papers that entered no stage of distillation or selection. The smaller set "
               "matches the full one, in fact a hair above. So half the rules can be dropped and nothing that generalises "
               "goes with them.")
        _slide(pp, slide_housekeeping,
               "Three smaller things, and then what I want your call on. The pipeline figure now shows our actual pipeline. "
               "The ablations section says what we measured instead of what we promised. And section four of the main text "
               "still quotes the old numbers and the old objective — that is the piece that still needs a decision.")
        _slide(pp, slide_corpus,
               "And then, not Appendix F at all: where the corpus stands as of this morning. Two-point-nine-three million "
               "papers exist on arXiv, we asked for the source of two-point-nine, and two-point-six-three million are in "
               "hand — ninety per cent of everything arXiv has ever published. Two rows moved since we last looked. Twenty "
               "twenty-four closed out, and twenty twenty-five came in whole. The hatched block on the last bar is not a "
               "backlog we measured, it is the thirty-thousand placeholder standing in for metadata we have not harvested.")
        _slide(pp, slide_download,
               "And the same thing year by year, if anyone wants to check a row. Twenty twenty-four finished at a hundred "
               "per cent attempted, two hundred and twenty-three thousand papers; twenty twenty-five brought two hundred "
               "and thirty-seven thousand more. Ninety-one per cent of everything we asked for came back as source, and "
               "that ratio has been flat since about twenty ten — the loss is almost all PDF-only submissions, the orange "
               "column. The one asterisk is the twenty twenty-five metadata, which we have not harvested yet, so read that "
               "row’s per cent attempted as unknown rather than low.")
        _slide(pp, slide_fp_judge,
               "Last thing, and it is the stage we are on now. Distillation and selection are done; what is left is the "
               "post-hoc audit of the false positives. On the hundred and forty held-out papers the selected rules produce "
               "one thousand eight hundred and eighty-nine false positives under M three, and the question for every one of "
               "them is whether it is a real extraction error or a real instance the silver corpus simply never labelled. We "
               "do not want one model deciding that, so four open-weight judges each read all of them — seven and a half "
               "thousand verdicts — and a span is only called a miss in the reference when three of the four agree. Where "
               "they split we record the split rather than break the tie. Note where the work actually is: remark, claim and "
               "definition are eighty-six per cent of the queue. The one thing to fix first is the batching — we send "
               "several spans per prompt to keep the cost down, and on the long ones the reply runs past its budget and comes "
               "back cut off. That loses us answers rather than corrupting them, but it needs sorting before the real run.")
        _slide(pp, slide_regex_cost,
               "One more, and it is the question Or raised: can we tell from a rule's shape whether it will be slow. There is a real "
               "answer — regex ambiguity analysis, which reads the pattern without running it and returns linear, polynomial or "
               "exponential. We ran it over all three hundred and eighty-eight live rules. Eighteen come back non-linear, fifteen of "
               "them exponential, and every single one is in the definition group. But here is the thing worth taking away. Those "
               "fifteen cost us under three per cent of actual parsing time. The twenty rules that do cost us sixty-seven per cent of "
               "it are all flagged linear — not one of them is on the static list. So the two metrics answer different questions: the "
               "static verdict tells you whether a rule can ever hang, and it found a real one — fifteen rules share a single bad "
               "idiom that goes five times slower for every two characters of input, and two of them actually hit our ten-second cap "
               "on real papers. One edit to that idiom fixes all fifteen. But if you want the parse to be faster, the static verdict "
               "is not the ranking to use — sort by measured time. And note what does not predict cost: star height, the thing you "
               "would intuitively reach for, is identical in both groups.")
    print("wrote", out)


if __name__ == "__main__":
    main()
