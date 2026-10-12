#!/usr/bin/env python3
"""A readable summary of an alg3 extractor: per node type, its threshold and the
clues that count most for and against it.

    python3 alg3/explain.py alg3/runs/v2b_fast [--top 15] [-o RULES.md]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SEC = {"intro": "Introduction", "prelim": "Preliminaries/Notation/Background", "main": "Main results",
       "proof": "Proofs", "example": "Examples/Applications", "open": "Open problems/Questions",
       "conclusion": "Conclusion/Discussion", "algorithm": "Algorithm/Method/Numerics",
       "model": "Model/Assumptions", "appendix": "Appendix", "none": "no section"}
CTX = {"p2": "two sentences before", "p1": "previous sentence", "s": "this sentence (1st pass)",
       "n1": "next sentence"}
BUCKET = {"1": "p≥0.10", "2": "p≥0.25", "3": "p≥0.50", "4": "p≥0.75"}


def words(s: str) -> str:
    return " ".join(s.split("_")).replace("<math>", "$…$").replace("<display>", "[display]") \
        .replace("<ref>", "\\ref").replace("<cite>", "\\cite").replace("<emph>", "\\emph") \
        .replace("<bold>", "\\textbf").replace("<item>", "\\item").replace("<quote>", "“")


def describe(name: str) -> str:
    k, _, v = name.partition("=")
    if name == "bias":
        return "(baseline)"
    if k in ("f1", "f2", "f3"):
        return f'starts with "{words(v)}"'
    if k == "w":
        return f'contains "{words(v)}"'
    if k == "b":
        return f'contains "{words(v)}"'
    if k == "last":
        return f'ends with "{words(v)}"'
    if k == "cue":
        return f"cue phrase: {v}"
    if k == "llm":
        return f"teacher clue: {v}"
    if k == "seck":
        return f"in a section about {SEC.get(v, v)}"
    if k == "secw":
        return f'section title contains "{v}"'
    if k.startswith("prev") and k[4:5].isdigit():
        return f'previous sentence starts with "{words(v)}"'
    if k.startswith("next") and k[4:5].isdigit():
        return f'next sentence starts with "{words(v)}"'
    if k == "env_before":
        return f"right after a {v} environment"
    if k == "env_after":
        return f"right before a {v} environment"
    if name.startswith("ctx:"):
        _, where, *rest = name.split(":")
        if rest == ["none"]:
            return f"{CTX.get(where, where)}: none (region edge)"
        t, b = rest
        return f"{CTX.get(where, where)} looks like {t} ({BUCKET.get(b, b)})"
    if name.startswith("x:"):
        return "combination: " + ", ".join(words(p) for p in name[2:].split("|"))
    flags = {"m:emph": "has italics/\\emph", "m:bold": "has bold", "m:bold_lead": "starts in bold",
             "m:item": "is a list item", "m:enum": "starts with (i)/1.", "m:colon": "ends with a colon",
             "m:question": "ends with ?", "m:cite": "has a citation", "m:ref": "has a \\ref",
             "m:display": "contains a displayed equation", "p:first": "first in its paragraph",
             "p:last": "last in its paragraph", "p:region_start": "first after a heading/environment",
             "prev:colon": "previous sentence ends with a colon", "prev:emph": "previous sentence has italics",
             "prev:none": "no previous sentence in the region", "next:none": "no next sentence in the region",
             "next:display": "next sentence starts with a display", "sec:none": "before any section"}
    if name in flags:
        return flags[name]
    m = re.match(r"(s:len|s:nmath|s:mfrac|p:plen|p:doc|d:reuse)(\d)", name)
    if m:
        what = {"s:len": "length bucket", "s:nmath": "inline-math count bucket",
                "s:mfrac": "share-of-math bucket", "p:plen": "paragraph-length bucket",
                "p:doc": "position-in-paper decile", "d:reuse": "emphasised term reused later, bucket"}
        return f"{what[m.group(1)]} {m.group(2)}"
    return name


def table(tab: dict, cls: str, top: int):
    j = tab["classes"].index(cls)
    ws = sorted(((w[j], n) for n, w in tab["weights"].items() if n != "bias"), reverse=True)
    return ws[:top], ws[::-1][:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    M = json.load(open(Path(a.model_dir) / "sentence_model.json"))
    A, B, tau, meta = M["anchor"], M.get("stage2"), M["tau"], M.get("meta", {})
    lines = [f"# alg3 extractor `{Path(a.model_dir).name}`: the strongest clues per type", "",
             f"A sentence starts a node of type T when, after the second pass, P(T) is its "
             f"highest type probability and at least the threshold τ_T. Weights are log-odds "
             f"contributions (positive = evidence for T). Trained on {len(meta.get('train_papers', []))} "
             f"papers; {len(A['weights'])} clues in pass 1"
             + (f", {len(B['weights'])} in pass 2" if B else "") + ".", ""]
    if "val" in meta:
        lines += [f"Validation (40 papers, overall F incl. base parser): **{meta['val']['F']}** "
                  f"(P {meta['val']['P']}, R {meta['val']['R']}); base {meta['val_base']['F']}.", ""]
    for cls in sorted(tau, key=lambda t: tau[t]):
        if cls not in A["classes"]:
            continue
        pos, neg = table(A, cls, a.top)
        lines += [f"## {cls}  (τ = {tau[cls]})", "", "| for (weight) | against (weight) |", "|---|---|"]
        for (wp, np_), (wn, nn) in zip(pos, neg):
            lines.append(f"| {describe(np_)} ({wp:+.2f}) | {describe(nn)} ({wn:+.2f}) |")
        if B and cls in B["classes"]:
            j = B["classes"].index(cls)
            ctx = sorted(((w[j], n) for n, w in B["weights"].items() if n.startswith("ctx:")),
                         reverse=True)[:6]
            lines += ["", "Second pass, strongest neighbour evidence: "
                      + "; ".join(f"{describe(n)} ({w:+.2f})" for w, n in ctx)]
        lines.append("")
    text = "\n".join(lines) + "\n"
    out = Path(a.out) if a.out else Path(a.model_dir) / "RULES.md"
    out.write_text(text, encoding="utf-8")
    print(f"written {out} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
