#!/usr/bin/env python3
"""Predict which LaTeX in the corpus will not render under matplotlib mathtext.

Rendering failures were being discovered one crashed paper at a time. They are
predictable: take every text field, resolve the paper's own macros exactly as
the renderer does, pull out the math blocks, and hand each to mathtext's parser
in-process. Whatever raises would have crashed or mis-rendered a figure.

Two classes of problem, and the second is the one you cannot see from a
traceback:

  HARD  mathtext raises -> the render dies (or the block is dropped)
  SOFT  mathtext accepts it but the output is wrong. The main source is
        \\DeclareMathOperator{\\eq}{eq}, which the glossary records as
        `eq`; in math mode a bare `eq` sets as the *product of two italic
        variables* e·q, not an upright operator name. It parses fine and looks
        wrong, so only a scan like this finds it.

Usage:
    python3 scripts/audit_mathtext.py                     # whole silver corpus
    python3 scripts/audit_mathtext.py --dir <d> --limit 20
    python3 scripts/audit_mathtext.py --show-samples
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

import matplotlib                                    # noqa: E402
matplotlib.use("Agg")
from matplotlib import mathtext                      # noqa: E402

from latex_macros import normalize_for_mathtext      # noqa: E402

# Measure what the RENDERER actually does, not a subset of it. An earlier
# version called only latex_macros, missing visualize_annotation's
# _LATEX_FIXES / _LATEX_REGEX_FIXES / unknown-command fallback — so it reported
# \le and \ge as top offenders when the renderer had been rewriting them to
# \leq / \geq all along.
import visualize_annotation as _viz                  # noqa: E402


def render_pipeline(text, macros):
    return _viz._sanitize_math(normalize_for_mathtext(text, macros))

TEXT_FIELDS = ("statement", "statement_short", "name", "clean_text",
               "raw_latex", "genus", "definiendum")
LIST_FIELDS = ("assumptions", "conclusions", "differentia")

# $...$ or \(...\); non-greedy, tolerating escaped dollars.
_MATH = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_CMD = re.compile(r"\\([A-Za-z]+)")
# An expansion that is just letters/digits: DeclareMathOperator's shape.
_BARE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

_parser = mathtext.MathTextParser("agg")


def _texts(node):
    for f in TEXT_FIELDS:
        v = node.get(f)
        if isinstance(v, str) and v:
            yield f, v
    for f in LIST_FIELDS:
        v = node.get(f)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x:
                    yield f, x


def check_block(block):
    """Return the offending command, or None if mathtext accepts it.

    Only mathtext's own "Unknown symbol: \\x" is trusted for attribution.
    Guessing the first command in the block instead — as an earlier version did
    — blamed \\le, \\ge and \\frac, which mathtext supports perfectly well;
    the real cause was elsewhere in the block. Unattributable failures are
    bucketed honestly rather than pinned on an innocent command.
    """
    try:
        _parser.parse("$%s$" % block, dpi=72, prop=None)
        return None
    except Exception as e:
        msg = str(e)
        m = re.search(r"Unknown symbol: \\([A-Za-z]+)", msg)
        if m:
            return m.group(1)
        m = re.search(r"Unknown symbol: (\S+)", msg)
        if m:
            return "(symbol %s)" % m.group(1)[:12]
        for pat, label in ((r"unclosed|Expected|expected", "(malformed)"),
                           (r"double superscript|double subscript", "(double sub/sup)"),
                           (r"\\left.*\\right|Expected \\right", "(unbalanced delimiter)")):
            if re.search(pat, msg):
                return label
        return "(other)"


def audit(paths, show_samples=False):
    hard = Counter()                 # command -> occurrences
    hard_papers = defaultdict(set)   # command -> papers
    soft = Counter()
    soft_papers = defaultdict(set)
    samples = {}
    n_papers = n_blocks = n_bad = 0

    for p in paths:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        n_papers += 1
        pid = os.path.basename(p)[:-5]
        macros = (d.get("metadata") or {}).get("macros") or {}

        # SOFT: operator-style macros whose expansion is a bare name
        for name, spec in macros.items():
            exp = (spec or {}).get("expansion", "") if isinstance(spec, dict) else ""
            if _BARE_NAME.match(exp or ""):
                soft[name] += 1
                soft_papers[name].add(pid)
                samples.setdefault("SOFT:" + name, r"\%s -> %s" % (name, exp))

        for node in (d.get("nodes") or []):
            for _f, txt in _texts(node):
                resolved = render_pipeline(txt, macros)
                for block in _MATH.findall(resolved):
                    n_blocks += 1
                    bad = check_block(block)
                    if bad:
                        n_bad += 1
                        hard[bad] += 1
                        hard_papers[bad].add(pid)
                        samples.setdefault("HARD:" + bad, block.strip()[:70])
    return dict(hard=hard, hard_papers=hard_papers, soft=soft,
                soft_papers=soft_papers, samples=samples,
                n_papers=n_papers, n_blocks=n_blocks, n_bad=n_bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(REPO, "corpus/silver/opus-5__v5.1"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--show-samples", action="store_true")
    a = ap.parse_args()

    paths = sorted(os.path.join(a.dir, f) for f in os.listdir(a.dir)
                   if f.endswith(".json"))
    if a.limit:
        paths = paths[:a.limit]

    r = audit(paths, a.show_samples)
    print("papers %d   math blocks %d   blocks mathtext REJECTS %d (%.2f%%)"
          % (r["n_papers"], r["n_blocks"], r["n_bad"],
             100.0 * r["n_bad"] / max(1, r["n_blocks"])))

    print("\nHARD — mathtext raises; these break or drop a figure")
    print("  %-22s %8s %8s  %s" % ("command", "occurs", "papers", "sample"))
    for cmd, n in r["hard"].most_common(a.top):
        print("  \\%-21s %8d %8d  %s"
              % (cmd, n, len(r["hard_papers"][cmd]),
                 r["samples"].get("HARD:" + cmd, "")[:52] if a.show_samples else ""))

    print("\nSOFT — parses but renders wrong (operator name set as italic variables)")
    print("  %-22s %8s %8s  %s" % ("macro", "papers", "", "expansion"))
    for cmd, n in r["soft"].most_common(a.top):
        print("  \\%-21s %8d %8s  %s"
              % (cmd, len(r["soft_papers"][cmd]), "",
                 r["samples"].get("SOFT:" + cmd, "")[:52] if a.show_samples else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
