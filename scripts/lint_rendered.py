#!/usr/bin/env python3
"""Catch LaTeX that leaked into rendered output, before a human has to.

Every display defect found in the v5.1 render was found by a person reading a
page: `\\textsf{Push}{}` printed verbatim, `{\\em ...}` printed verbatim,
`\\geq\\underline{C}` welded into the unknown command `\\geqC` and set as the
literal text "geqC", `\\ensuremath` surviving past the 8th occurrence in a
statement. Several were introduced by a fix to a neighbouring problem. Unit
tests (tests/test_latex_macros.py) pin the cases we already know; this pins the
CORPUS, which is where the unknown ones live.

Two modes, because they answer different questions:

  --source   run the text pipeline over the corpus JSON. Fast (no rendering),
             catches anything normalisation fails to resolve. Use in a loop.
  --html     scan rendered pages. Slower and needs a render, but it is the only
             check that sees text reaching the reader through a path the
             pipeline does not own — a field nobody normalises, a JS payload
             built from an unnormalised copy. That class is exactly how
             origin_citation/input/output were missed.

Exit code is 1 when anything is found, so it can gate a release.

Usage:
    python3 scripts/lint_rendered.py --source
    python3 scripts/lint_rendered.py --html /tmp/render200
    python3 scripts/lint_rendered.py --source --html /tmp/render200 --show 5
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

# Environments MathJax actually defines; anything else reaching a page is an
# "unknown environment" error that REPLACES the content it wraps.
from latex_macros import _MATH_ENVS                      # noqa: E402
from latex_macros import normalize_for_mathtext          # noqa: E402

# ── What counts as a leak ────────────────────────────────────────────────
# Each rule is (name, compiled pattern, why it matters). Patterns are written
# against the RESOLVED text, so a hit means normalisation did not handle it.
RULES = [
    ("font-selector",
     re.compile(r"\\(?:textsf|textbf|textit|texttt|textsc|emph|textrm|"
                r"textnormal|textup|uppercase)\s*\{"),
     "renders as the command name; should map to \\math* or unwrap"),
    ("font-declaration",
     re.compile(r"\\(?:em|it|bf|rm|sf|tt|sc|sl|bfseries|itshape|normalfont)"
                r"(?![A-Za-z])"),
     "old-style {\\em ...}; renders verbatim"),
    ("transparent-wrapper",
     re.compile(r"\\(?:ensuremath|mbox|hbox|underline|norm|abs)\s*\{"),
     "mathtext does not implement it; a resolved macro still fails"),
    ("cross-reference",
     re.compile(r"\\(?:cite[a-z]*|eqref|cref|Cref|autoref|pageref|ref|label)\s*\{"),
     "MathJax renders an undefined \\ref as the literal string ???"),
    ("control-space",
     re.compile(r"(?<!\\)\\[ \t]"),
     "`(resp.\\ x)` leaks the backslash; `\\\\ ` is a row break, not this"),
    ("style-switch",
     re.compile(r"\\(?:text|display|script)style(?![A-Za-z])"),
     "argument-less switch; both renderers reject it"),
    ("glued-token",
     # `\geqC`, `\inX`: a control word welded to an alphanumeric by a splice.
     # Only flag KNOWN operators followed by more letters, so real commands
     # (\geqslant, \included) are not reported.
     re.compile(r"\\(?:in|geq|leq|ge|le|to|cup|cap|subset|subseteq|equiv|sim|"
                r"times|cdot|rightarrow|leftarrow)[A-Z]"),
     "token boundary lost during substitution; renders as literal text"),
]

_ENV = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_TEXT_FIELDS = ("statement", "statement_short", "name", "clean_text",
                "raw_latex", "genus", "definiendum", "proof_strategy",
                "origin_citation", "assumptions", "conclusions",
                "differentia", "input", "output")


def _strings(node):
    for f in _TEXT_FIELDS:
        v = node.get(f)
        for s in (v if isinstance(v, list) else [v] if isinstance(v, str) else []):
            if isinstance(s, str) and s:
                yield f, s


def lint_source(corpus_dir, show=0):
    """Run the text pipeline over the corpus and report what survives."""
    hits = Counter()
    where = defaultdict(set)
    samples = {}
    n_papers = n_strings = 0

    for p in sorted(glob.glob(os.path.join(corpus_dir, "*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        n_papers += 1
        pid = os.path.basename(p)[:-5]
        macros = (d.get("metadata") or {}).get("macros") or {}
        for node in (d.get("nodes") or []):
            for field, s in _strings(node):
                n_strings += 1
                out = normalize_for_mathtext(s, macros)
                for name, pat, _why in RULES:
                    m = pat.search(out)
                    if m:
                        hits[name] += 1
                        where[name].add(pid)
                        samples.setdefault(
                            name, "%s %s: ...%s..."
                            % (pid, field,
                               out[max(0, m.start() - 30):m.start() + 40]))
                for env in _ENV.findall(out):
                    if env not in _MATH_ENVS:
                        hits["unknown-environment"] += 1
                        where["unknown-environment"].add(pid)
                        samples.setdefault("unknown-environment",
                                           "%s %s: \\begin{%s}" % (pid, field, env))
    return hits, where, samples, n_papers, n_strings


def lint_html(html_dir, show=0):
    """Scan rendered pages — the only check that sees paths the pipeline
    does not own (an unnormalised field, a JS payload built from a stale copy).

    Patterns are matched against both the raw text and its JSON-escaped form,
    since the interactive panel embeds node text through json.dumps.
    """
    hits = Counter()
    where = defaultdict(set)
    samples = {}
    n_pages = 0
    for f in sorted(glob.glob(os.path.join(html_dir, "*.html"))):
        base = os.path.basename(f)
        if base.startswith("_") or base == "index.html":
            continue
        n_pages += 1
        try:
            h = open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for name, pat, _why in RULES:
            # `\\textsf{` in the page is `\textsf{` inside a JSON string
            esc = re.compile(pat.pattern.replace(r"\\", r"\\\\"))
            m = pat.search(h) or esc.search(h)
            if m:
                hits[name] += 1
                where[name].add(base[:-5])
                samples.setdefault(name, "%s: ...%s..."
                                   % (base[:-5],
                                      h[max(0, m.start() - 30):m.start() + 40]))
    return hits, where, samples, n_pages, 0


def report(title, hits, where, samples, n_a, n_b, show):
    print("\n%s" % title)
    if not hits:
        print("  clean")
        return 0
    print("  %-22s %8s %8s" % ("leak", "hits", "papers"))
    for name, n in hits.most_common():
        print("  %-22s %8d %8d" % (name, n, len(where[name])))
        if show:
            print("      %s" % samples.get(name, "")[:110])
    return sum(hits.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="store_true",
                    help="lint the corpus JSON through the text pipeline")
    ap.add_argument("--html", metavar="DIR", default=None,
                    help="lint rendered HTML in DIR")
    ap.add_argument("--corpus",
                    default=os.path.join(REPO, "corpus/silver/opus-5__v5.1"))
    ap.add_argument("--show", type=int, default=1, help="show a sample per leak")
    a = ap.parse_args()
    if not a.source and not a.html:
        a.source = True

    total = 0
    if a.source:
        h, w, s, na, nb = lint_source(a.corpus, a.show)
        print("SOURCE  %d papers, %d strings through the text pipeline" % (na, nb))
        total += report("leaks surviving normalisation:", h, w, s, na, nb, a.show)
    if a.html:
        h, w, s, na, nb = lint_html(a.html, a.show)
        print("\nHTML    %d rendered pages" % na)
        total += report("leaks reaching the page:", h, w, s, na, nb, a.show)

    print("\n%s" % ("FAIL: %d leak categories" % total if total else "PASS"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
