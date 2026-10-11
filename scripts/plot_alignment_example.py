#!/usr/bin/env python3
"""One paper's scoring, drawn: the reference nodes (LLM silver) on the left,
the distilled rules' nodes on the right, a line for every matched pair of the
headline metric (graded one-to-one span matching, node_metrics.m1g), and the
unmatched nodes marked as misses (FN) and false alarms (FP).

    python3 scripts/plot_alignment_example.py 1306.6362v2 -o <out.png>
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
import node_metrics as NM          # noqa: E402
import match_modes as mm           # noqa: E402
import node_similarity as ns       # noqa: E402

COLORS = {"definition": "#4ea862", "theorem": "#d04848", "lemma": "#e08a3c", "proposition": "#e6c84a",
          "corollary": "#f0c878", "proof": "#8a8a8a", "claim": "#e6a8c4", "conjecture": "#d97aa8",
          "remark": "#46b5c4", "example": "#46b5c4", "assumption": "#c2a878", "open_problem": "#7ab6e0",
          "problem": "#3f7fbf", "algorithm": "#3aa39a"}


def words(t, n=7):
    import re
    t = re.sub(r"\\label\s*\{[^}]*\}", " ", t)
    t = re.sub(r"\\[A-Za-z]+\*?|[{}$\\]|\s+", " ", t)
    w = t.split()
    return " ".join(w[:n]) + (" …" if len(w) > n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid")
    ap.add_argument("--run", default="runs/compare/v6_6-2-2")
    ap.add_argument("--arm", default="g_units_haiku_f1")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    run = REPO / a.run
    gold = json.load(open(run / "_gold_texts.json"))
    golds = [(t, g) for t in gold for g in gold[t].get(a.pid, [])]
    preds = None
    for line in open(run / a.arm / "eval/parses/final.jsonl"):
        d = json.loads(line)
        if d.get("pid") == a.pid:
            preds = [(t, raw) for t, raw, *_ in d["objects"]]
    if preds is None:
        sys.exit("paper not in the stored parses")
    # document order: position of each text in the paper's source
    tex = next((REPO / "corpus/silver/tex_staged" / a.pid / "source").glob("*.tex"), None)
    src = open(tex, errors="replace").read() if tex else ""
    import re as _re
    def pos(x):
        x = _re.sub(r"\\label\s*\{[^}]*\}", "", x).strip()
        for probe in (x[:60], x[:30], x[len(x) // 2:len(x) // 2 + 30]):
            k = src.find(probe) if probe else -1
            if k >= 0:
                return k
        return None
    silver = json.load(open(REPO / "corpus/silver/opus-5.5__v6" / f"{a.pid}.json"))
    order = {}
    for i, n in enumerate(silver["nodes"]):
        order.setdefault((n.get("statement") or "").strip()[:80], i)
    G = [(t, mm.tokens(x)) for t, x in golds]
    P = [(t, mm.tokens(x)) for t, x in preds]
    match = NM._one_to_one(P, G, ns.type_compat, NM.THRESHOLD)      # {pred i: (gold j, credit)}
    gi = sorted(range(len(golds)), key=lambda j: order.get(golds[j][1].strip()[:80], 10**6))
    grank = {j: k for k, j in enumerate(gi)}
    # rule nodes: a matched one sits level with its reference node; an
    # unmatched one goes just after the matched node that precedes it in the paper
    ppos = {i: pos(preds[i][1]) for i in range(len(preds))}
    by_src = sorted(range(len(preds)), key=lambda i: (ppos[i] is None, ppos[i] or 0))
    key, last = {}, -1.0
    for i in by_src:
        if i in match:
            last = grank[match[i][0]]
            key[i] = last
        else:
            last += 0.01
            key[i] = last
    pi = sorted(range(len(preds)), key=lambda i: key[i])
    tp = sum(c for _, c in match.values())
    Pr, Rc = tp / len(preds), tp / len(golds)
    F = 2 * Pr * Rc / (Pr + Rc)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    n = max(len(gi), len(pi))
    H = 0.19 * n + 1.0
    fig, ax = plt.subplots(figsize=(11, H))
    ax.set_xlim(0, 11); ax.set_ylim(-n - 0.7, 1.9); ax.axis("off")
    yg = {j: -k * n / len(gi) for k, j in enumerate(gi)}
    yp = {i: -k * n / len(pi) for k, i in enumerate(pi)}
    matched_g = {j for j, _ in match.values()}
    def box(x, y, t, text, bad, edge):
        ax.add_patch(FancyBboxPatch((x, y - 0.38), 3.9, 0.76, boxstyle="round,pad=0,rounding_size=0.08",
                                    fc=COLORS.get(t, "#bbb"), ec=edge if bad else "white", lw=2.2 if bad else 0.5, alpha=0.9))
        ax.text(x + 0.08, y, f"{t.replace('_', ' ')}: {words(text)}", fontsize=6.2, va="center", clip_on=True)
    for j in gi:
        box(0.2, yg[j], golds[j][0], golds[j][1], j not in matched_g, "#c0392b")
    for i in pi:
        box(6.9, yp[i], preds[i][0], preds[i][1], i not in match, "#e67e22")
    for i, (j, c) in match.items():
        ax.plot([4.1, 6.9], [yg[j], yp[i]], ls="--", lw=1.0, color="#2c3e50" if c >= 0.99 else "#7f8c8d", alpha=0.85)
    ax.text(2.15, 1.05, f"LLM (reference): {len(golds)} nodes", ha="center", fontsize=10, weight="bold")
    ax.text(8.85, 1.05, f"distilled rules: {len(preds)} nodes", ha="center", fontsize=10, weight="bold")
    ax.text(5.5, 1.45, f"{len(match)} matched  (dashed)", ha="center", fontsize=9, color="#2c3e50")
    ax.text(5.5, 0.95, f"P {Pr:.2f}   R {Rc:.2f}   F$_1$ {F:.2f}", ha="center", fontsize=9.5, color="#2c3e50", weight="bold")
    ax.text(2.15, -n - 0.3, "red frame: missed by the rules (FN)", ha="center", fontsize=8, color="#c0392b")
    ax.text(8.85, -n - 0.3, "orange frame: not in the reference (FP)", ha="center", fontsize=8, color="#e67e22")
    fig.tight_layout()
    fig.savefig(a.out, dpi=200)
    print(f"{a.pid}: {len(golds)} reference, {len(preds)} predicted, {len(match)} matched (credit {tp:.1f}); "
          f"FN {len(golds) - len(matched_g)}, FP {len(preds) - len(match)}; P {Pr:.3f} R {Rc:.3f} F1 {F:.3f}")


if __name__ == "__main__":
    main()
