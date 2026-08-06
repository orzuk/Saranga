#!/usr/bin/env python3
"""
Extract each paper's macro glossary from its staged .tex. Pure regex — no LLM.

Why a glossary and not expansion
--------------------------------
Measured over 120 staged papers, normalising macros away is lossy in BOTH
directions, so the raw spans must stay raw:

  * 341 expansions collide across papers — `\\mathcal{C}` is written as `Casimir`
    in one paper and `Cir` in another. Expanding both asserts that a Casimir
    element is a circle.
  * 473 macro NAMES collide — `\\e` means `\\begin{equation}`, `\\epsilon`,
    `\\eta` and `\\mathbb{E}` in different papers, so the name alone is no better.

The (name, expansion) PAIR is the unit of meaning: `Intw -> \\mathcal{M}` is
effectively an author-written definition. This script captures those pairs as a
side artifact, leaving every extracted `statement` untouched.

It also classifies each macro, because the two classes want opposite treatment:

  structural   expansion contains LaTeX markup (`\\be -> \\begin{equation}`).
               SAFE and useful to expand before REGEX RULES run — a distilled
               rule anchored on `\\begin{equation}` silently never fires on a
               paper that writes `\\be`, which looks like low recall rather than
               a bug.
  notational   math symbols (`\\Z -> \\mathbb{Z}`). Must NOT be expanded; that is
               what manufactures the false positives above.

Usage:
    python scripts/build_macro_glossary.py                    # all staged tex
    python scripts/build_macro_glossary.py --ids 1409.3255v2
    python scripts/build_macro_glossary.py --out-dir <dir>
"""

import argparse
import json
import os
import re
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX_DIR = os.path.join(REPO, "corpus/silver/tex_pool")
OUT_DIR = os.path.join(REPO, "corpus/silver/macros")

# Definition forms. Each yields (name, rest-of-string-index) and we then read a
# brace-balanced body, because expansions routinely contain nested braces and a
# length-capped regex would truncate them.
FORMS = [
    # \newcommand{\foo}[2][opt]{body} / \newcommand\foo{body}
    re.compile(r'\\(?:new|renew|provide)command\*?\s*\{?\\([A-Za-z@]+)\}?\s*'
               r'(?:\[\d+\])?\s*(?:\[[^\]]*\])?\s*\{'),
    # \def\foo{body}  /  \def\foo#1{body}
    re.compile(r'\\(?:e|g|x)?def\s*\\([A-Za-z@]+)\s*(?:#\d)*\s*\{'),
    # \DeclareMathOperator{\foo}{body}
    re.compile(r'\\DeclareMathOperator\*?\s*\{\\([A-Za-z@]+)\}\s*\{'),
    # \newenvironment{foo}{begin}{end} — name has no backslash
    re.compile(r'\\(?:new|renew)environment\*?\s*\{([A-Za-z@*]+)\}\s*'
               r'(?:\[\d+\])?\s*\{'),
]

STRUCT = re.compile(r'\\(label|index|textbf|emph|textit|section|subsection|'
                    r'paragraph|begin|end|item|footnote|caption|ref|eqref|cite|'
                    r'ignorespaces|noindent|medskip|smallskip|vspace)\b')
PRESENT = re.compile(r'\\(textcolor|color|colorbox|hl|st|sout|uline)\b')


def strip_comments(src):
    """Drop % comments (respecting \\%) so definitions inside comments are ignored."""
    return re.sub(r'(?<!\\)%.*', '', src)


def balanced_body(src, open_idx):
    """Read a brace-balanced body starting at the '{' at open_idx."""
    depth, i, n = 0, open_idx, len(src)
    while i < n:
        c = src[i]
        if c == '\\':                      # skip escaped char
            i += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return src[open_idx + 1:i], i + 1
        i += 1
    return None, n                          # unbalanced — give up on this one


def classify(expansion):
    if PRESENT.search(expansion):
        return "presentational"
    if STRUCT.search(expansion):
        return "structural"
    return "notational"


def extract(src):
    """name -> {expansion, kind, arity}. Later definitions win (\\renewcommand)."""
    src = strip_comments(src)
    out = {}
    for form in FORMS:
        for m in form.finditer(src):
            name = m.group(1)
            body, _ = balanced_body(src, m.end() - 1)
            if body is None:
                continue
            arity = len(set(re.findall(r'#(\d)', body)))
            out[name] = {
                "expansion": re.sub(r'\s+', ' ', body).strip(),
                "kind": classify(body),
                "arity": arity,
            }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex-dir", default=TEX_DIR)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--ids", default=None, help="comma list; default = all staged")
    ap.add_argument("--merge", action="store_true",
                    help="after building, merge each glossary into the paper's "
                         "metadata.macros (see merge_macros.py)")
    ap.add_argument("--extract-dir", default=None,
                    help="extraction dir for --merge; default = merge_macros.py's")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    else:
        ids = sorted(f[:-4] for f in os.listdir(args.tex_dir) if f.endswith(".tex"))

    kinds, per_paper, unbalanced = Counter(), {}, 0
    for aid in ids:
        p = os.path.join(args.tex_dir, aid + ".tex")
        if not os.path.isfile(p):
            print(f"  skip {aid} (no .tex)")
            continue
        src = open(p, encoding="utf-8", errors="replace").read()
        macros = extract(src)
        for v in macros.values():
            kinds[v["kind"]] += 1
        per_paper[aid] = len(macros)
        payload = {
            "arxiv_id": aid,
            "n_macros": len(macros),
            "by_kind": dict(Counter(v["kind"] for v in macros.values())),
            "macros": macros,
        }
        with open(os.path.join(args.out_dir, aid + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False)

    tot = sum(kinds.values())
    print("papers processed : %d" % len(per_paper))
    print("macros captured  : %d" % tot)
    for k, c in kinds.most_common():
        print("   %-15s %5d (%.0f%%)" % (k, c, 100 * c / tot if tot else 0))
    if per_paper:
        vals = sorted(per_paper.values())
        print("per paper        : median %d, max %d, papers with none %d"
              % (vals[len(vals) // 2], vals[-1], sum(1 for v in vals if v == 0)))

    if args.merge:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import merge_macros
        extract_dir = args.extract_dir or merge_macros.EXTRACT_DIR
        print("\nmerging into %s" % extract_dir)
        written = unchanged = 0
        for aid in sorted(per_paper):
            paper = os.path.join(extract_dir, aid + ".json")
            if not os.path.isfile(paper):
                continue          # glossary built ahead of extraction; fine
            status, _ = merge_macros.merge_one(
                paper, os.path.join(args.out_dir, aid + ".json"))
            written += status == "written"
            unchanged += status == "unchanged"
        print("  merged %d, already current %d" % (written, unchanged))
    print("\nwrote -> %s" % os.path.relpath(args.out_dir, REPO))
    print("\nNOTE: statements are NOT modified. This is a side artifact.")
    print("      Structural macros are the ones safe to expand before regex rules;")
    print("      notational ones must be left alone (see module docstring).")


if __name__ == "__main__":
    main()
