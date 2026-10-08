"""
Rendering check for the literal symbol rules in rules.py.

Every key -> value pair of the literal rule tables is typeset in math mode on
both sides with pdflatex, rasterised with pdftoppm, cropped and compared
pixel by pixel:

  SAFE          both sides print the same: the rule only changes spelling;
  MERGE         they print differently: the rule identifies two symbols and
                needs a justification (MERGE_JUSTIFIED below), otherwise it
                is listed as needing review;
  UNRENDERABLE  one side does not compile (the reason is recorded).

Author macros (\\R, \\reals, \\tg, \\notequal, ...) get a \\providecommand
fallback with their usual definition; a rule that relies on one is marked
`assumes_definition`.

Run (from the repo root):
    python3 -m scripts.canonicalize.verify_symbols [--out PATH] [--workers N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import rules as R

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "out" / "canonicalize_verify" / "symbols_report.json"

# Literal tables applied by core._apply_literal_rules on math text.
LITERAL_TABLES = ["RULES_SPACING", "RULES_BRACKETS", "RULES_GREEK_UNICODE_TO_COMMAND",
                  "RULES_GREEK_VARIANTS", "RULES_NUMBER_SETS", "RULES_OPERATORS",
                  "RULES_RELATIONS", "RULES_SET_RELATIONS", "RULES_ARROWS", "RULES_LOGIC",
                  "RULES_ELL", "RULES_FUNCTION_ALIASES", "RULES_ENVIRONMENTS",
                  "RULES_FRAC_ALIASES"]
# Not checked here, with the reason.
NOT_CHECKED = {
    "RULES_PROSE": "prose rewrites, not math symbols (off by default)",
    "RULES_INEQUALITY_FLIP": "documentation only: the flip swaps both operands (verify_meaning checks it)",
}

# Macros that are not standard LaTeX: rendered with their usual definition.
FALLBACKS = {
    r"\R": r"\mathbb{R}", r"\reals": r"\mathbb{R}", r"\Reals": r"\mathbb{R}",
    r"\N": r"\mathbb{N}", r"\Naturals": r"\mathbb{N}",
    r"\Z": r"\mathbb{Z}", r"\Integers": r"\mathbb{Z}",
    r"\Q": r"\mathbb{Q}", r"\Rationals": r"\mathbb{Q}",
    r"\C": r"\mathbb{C}", r"\Complexes": r"\mathbb{C}",
    r"\F": r"\mathbb{F}",
    r"\tg": r"\operatorname{tg}", r"\ctg": r"\operatorname{ctg}",
    r"\arctg": r"\operatorname{arctg}", r"\arcctg": r"\operatorname{arcctg}",
    r"\arccot": r"\operatorname{arccot}",
    r"\sh": r"\operatorname{sh}", r"\ch": r"\operatorname{ch}", r"\th": r"\operatorname{th}",
    r"\notequal": r"\neq",
}

PREAMBLE = r"""\documentclass[12pt]{article}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,dsfont,mathrsfs,bbm}
\pagestyle{empty}
""" + "".join(rf"\providecommand{{{k}}}{{{v}}}" + "\n" for k, v in FALLBACKS.items()) + "\n"

# Second engine for what pdflatex cannot typeset (Unicode input, \lparen):
# LuaLaTeX + unicode-math, whose own character table maps e.g. U+03C6 to
# \varphi -- an independent check of RULES_GREEK_UNICODE_TO_COMMAND.
PREAMBLE_UNICODE = r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\usepackage{unicode-math}
\pagestyle{empty}
""" + "".join(rf"\providecommand{{{k}}}{{{v}}}" + "\n" for k, v in FALLBACKS.items()) + "\n"

# MERGE rules that are legitimate, with the reason. Everything else that
# renders differently is reported as needing review.
MERGE_JUSTIFIED = {
    # Greek variants: core applies a variant merge only when the text does not
    # use both forms (core._greek_variants_for), so no two symbols collide.
    (r"\varepsilon", r"\epsilon"): "variant glyph; merged only when the text does not use both",
    (r"\vartheta", r"\theta"): "variant glyph; merged only when the text does not use both",
    (r"\varrho", r"\rho"): "variant glyph; merged only when the text does not use both",
    (r"\varsigma", r"\sigma"): "variant glyph; merged only when the text does not use both",
    (r"\varphi", r"\phi"): "variant glyph; merged only when the text does not use both",
    (r"\varkappa", r"\kappa"): "variant glyph; merged only when the text does not use both",
    # Conditional merges (rules.CONDITIONAL_MERGES): applied only when the text
    # does not also use the other form, and never when a rename map renames
    # either side, so no two symbols of one text collide.
    (r"\ell", "l"): "same letter (l_1 = \\ell_1); merged only when the text does not use l",
    (r"\Rightarrow", r"\implies"): "same double arrow, shorter; merged only when the text does not "
        "use \\implies or \\Longrightarrow (=> may then be weak convergence)",
    (r"\Leftrightarrow", r"\iff"): "same double arrow, shorter; merged only when the text does not "
        "use \\iff or \\Longleftrightarrow",
    # \quad is kept (it separates formulas); \qquad is the same separator, wider
    (r"\qquad", r"\quad"): "the same formula separator, only wider",
    # Font packages for the same blackboard letter
    (r"\mathds{R}", r"\mathbb{R}"): "same blackboard-bold set, different font package",
    (r"\mathds{N}", r"\mathbb{N}"): "same blackboard-bold set, different font package",
    (r"\mathds{Z}", r"\mathbb{Z}"): "same blackboard-bold set, different font package",
    (r"\mathds{Q}", r"\mathbb{Q}"): "same blackboard-bold set, different font package",
    (r"\mathds{C}", r"\mathbb{C}"): "same blackboard-bold set, different font package",
    (r"\mathds{F}", r"\mathbb{F}"): "same blackboard-bold set, different font package",
    # Sizing only
    (r"\dfrac", r"\frac"): "display-size fraction, same value",
    (r"\tfrac", r"\frac"): "text-size fraction, same value",
    (r"\cfrac", r"\frac"): "continued-fraction layout, same value",
    (r"\longrightarrow", r"\to"): "longer arrow, same meaning",
    (r"\longleftarrow", r"\leftarrow"): "longer arrow, same meaning",
    (r"\longleftrightarrow", r"\leftrightarrow"): "longer arrow, same meaning",
    (r"\longmapsto", r"\mapsto"): "longer arrow, same meaning",
    (r"\Longrightarrow", r"\implies"): "\\implies is \\Longrightarrow with extra space",
    (r"\Longleftrightarrow", r"\iff"): "\\iff is \\Longleftrightarrow with extra space",
    (r"\smallsetminus", r"\setminus"): "smaller glyph, same operation",
    (r"\div", "/"): "the same division, other glyph",
    (r"\tg", r"\tan"): "national notation for the tangent",
    (r"\ctg", r"\cot"): "national notation for the cotangent",
    (r"\arctg", r"\arctan"): "national notation for the arctangent",
    (r"\arcctg", r"\arccot"): "national notation for the arccotangent",
}
# Whole families that are layout only
_LAYOUT_TABLES = {"RULES_SPACING": "spacing only", "RULES_BRACKETS": "delimiter size only",
                  "RULES_ENVIRONMENTS": "equation numbering only"}
# ...except these, which separate formulas and are not mere layout
_LAYOUT_EXCEPTIONS = {
    r"\quad": "also separates two formulas (x>0 \\quad y>1); as a space the clauses fuse",
    r"\qquad": "also separates two formulas (x>0 \\qquad y>1); as a space the clauses fuse",
}


def snippet(table: str, key: str, value: str, side: str) -> str:
    """Math-mode LaTeX showing one side of a rule in a context where it can render."""
    tok = key if side == "key" else value
    if table == "RULES_ENVIRONMENTS":
        name = re.search(r"\{([^}]*)\}", tok)
        if not name:
            return ""
        # render a whole environment; the \end rules mirror the \begin rules
        env = name.group(1)
        return rf"\begin{{{env}}} x = y \end{{{env}}}"
    if table == "RULES_BRACKETS":
        if key.startswith(r"\left"):
            return rf"${tok} \dfrac{{a}}{{b}} \right.$" if side == "key" else rf"${tok} \dfrac{{a}}{{b}}$"
        if key.startswith(r"\right"):
            return (rf"$\left. \dfrac{{a}}{{b}} {tok}$" if side == "key" else rf"$\dfrac{{a}}{{b}} {tok}$")
        if re.fullmatch(r"\\[Bb]igg?[lr]?", key):
            return rf"${tok}( x$"
        return rf"$x {tok} y$"
    if key == r"\xrightarrow":
        return rf"$x {tok}{{f}} y$"
    if table == "RULES_FRAC_ALIASES":
        return rf"$x = {tok}{{a}}{{b}}$"
    if table == "RULES_FUNCTION_ALIASES":
        return rf"${tok} x$"
    return rf"$x {tok} y$"


def _compile(tex_body: str, workdir: Path, name: str, engine: str = "pdflatex"):
    """-> (PIL image | None, error)"""
    from PIL import Image
    d = workdir / name
    d.mkdir()
    pre = PREAMBLE if engine == "pdflatex" else PREAMBLE_UNICODE
    (d / "s.tex").write_text(pre + "\\begin{document}\n" + tex_body + "\n\\end{document}\n",
                             encoding="utf-8")
    p = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", "s.tex"],
                       cwd=d, capture_output=True, text=True, errors="replace", timeout=60)
    if p.returncode != 0 or not (d / "s.pdf").exists():
        err = next((l for l in p.stdout.splitlines() if l.startswith("!")), "pdflatex failed")
        return None, err
    subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", "-singlefile", "s.pdf", "s"],
                   cwd=d, check=True, capture_output=True)
    img = Image.open(d / "s.png").convert("L")
    return _crop(img), None


_UNICODE_PROBE: dict = {}
_UNICODE_LOCK = threading.Lock()


def _unicode_engine(workdir: Path):
    """Is LuaLaTeX + unicode-math usable here? (probed once)"""
    with _UNICODE_LOCK:
        if "ok" not in _UNICODE_PROBE:
            if not shutil.which("lualatex"):
                _UNICODE_PROBE.update(ok=False, why="no lualatex for a Unicode-capable rendering")
            else:
                img, err = _compile("$x$", workdir, "probeU", "lualatex")
                _UNICODE_PROBE.update(ok=img is not None,
                                      why=f"lualatex+unicode-math unusable here ({err})")
    return _UNICODE_PROBE["ok"], _UNICODE_PROBE["why"]


def _crop(img):
    from PIL import ImageOps
    box = ImageOps.invert(img).point(lambda v: 255 if v > 40 else 0).getbbox()
    return img.crop(box) if box else img.crop((0, 0, 1, 1))


def same_image(a, b) -> bool:
    if a.size != b.size:
        return False
    from PIL import ImageChops
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 64 else 0)
    hist = diff.histogram()
    return hist[255] <= 0.001 * a.size[0] * a.size[1]


def collect_rules():
    rows = []
    for t in LITERAL_TABLES:
        for k, v in getattr(R, t).items():
            if k == v:
                continue
            rows.append({"table": t, "key": k, "value": v})
    return rows


def _uses_fallback(s: str) -> list[str]:
    return [m for m in FALLBACKS if re.search(re.escape(m) + r"(?![A-Za-z])", s)]


def classify(rule: dict, workdir: Path, idx: int, render=None) -> dict:
    render = render or _compile
    t, k, v = rule["table"], rule["key"], rule["value"]
    out = dict(rule)
    sk, sv = snippet(t, k, v, "key"), snippet(t, k, v, "value")
    out["latex_key"], out["latex_value"] = sk, sv
    if t == "RULES_ENVIRONMENTS" and k.startswith(r"\end"):
        out.update(status="SAME_AS_BEGIN", reason="rendered with its \\begin rule")
        return out
    unicode_key = any(ord(ch) > 127 for ch in k)
    out["engine"] = "pdflatex"
    a = b = None
    ea = eb = None
    if not unicode_key:     # pdflatex cannot typeset Unicode input without restating the rule
        a, ea = render(sk, workdir, f"{idx}k")
        b, eb = render(sv, workdir, f"{idx}v")
    if a is None or b is None:
        if unicode_key:
            ea = "pdflatex: no glyph for Unicode input"
        ok, why = _unicode_engine(workdir)
        if not ok:
            out.update(status="UNRENDERABLE", reason=f"{ea or eb}; {why}")
            return out
        out["engine"] = "lualatex+unicode-math"
        a2, ea2 = render(sk, workdir, f"{idx}kU", "lualatex")
        b2, eb2 = render(sv, workdir, f"{idx}vU", "lualatex")
        if a2 is not None and b2 is not None:
            a, b = a2, b2
        else:
            ea = f"{ea or eb}; lualatex: {ea2 or eb2}"
    fb = _uses_fallback(k) + _uses_fallback(v)
    if fb:
        out["assumes_definition"] = {m: FALLBACKS[m] for m in fb}
    if a is None or b is None:
        out.update(status="UNRENDERABLE", reason=f"{'key' if a is None else 'value'}: {ea}")
        return out
    if same_image(a, b):
        out["status"] = "SAFE"
        return out
    out["status"] = "MERGE"
    just = MERGE_JUSTIFIED.get((k, v))
    if just is None and t in _LAYOUT_TABLES and k not in _LAYOUT_EXCEPTIONS:
        just = _LAYOUT_TABLES[t]
    if just:
        out["justification"] = just
    else:
        out["needs_review"] = True
        out["review_note"] = REVIEW_NOTES.get((k, v)) or _LAYOUT_EXCEPTIONS.get(k, "")
    return out


# Why the remaining merges are not obviously harmless (shown in the report).
REVIEW_NOTES = {
    ("⇒", r"\implies"): "=> also denotes weak convergence or a map; \\implies is only implication",
    ("⇔", r"\iff"): "<=> also denotes 'equivalent' between objects, not only statements",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    args = ap.parse_args(argv)
    for tool in ("pdflatex", "pdftoppm"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found")
    rules = collect_rules()
    with tempfile.TemporaryDirectory() as tmp:
        with ThreadPoolExecutor(args.workers) as ex:
            res = list(ex.map(lambda ir: classify(ir[1], Path(tmp), ir[0]), enumerate(rules)))
    # \end environment rules share their \begin rule's verdict
    by_begin = {(r["table"], r["key"].replace(r"\begin", r"\end")): r for r in res
                if r["table"] == "RULES_ENVIRONMENTS" and r["key"].startswith(r"\begin")}
    for r in res:
        if r.get("status") == "SAME_AS_BEGIN":
            src = by_begin.get((r["table"], r["key"]))
            if src:
                for f in ("status", "justification", "needs_review", "review_note", "reason"):
                    if f in src:
                        r[f] = src[f]
    from collections import Counter
    c = Counter(r["status"] for r in res)
    print(f"literal rules checked: {len(res)} (tables: {', '.join(LITERAL_TABLES)})")
    print(f"not checked: {NOT_CHECKED}")
    print(f"SAFE {c['SAFE']}  MERGE {c['MERGE']}  UNRENDERABLE {c['UNRENDERABLE']}")
    rev = [r for r in res if r.get("needs_review")]
    print(f"\nMERGE rules needing review ({len(rev)}):")
    for r in rev:
        print(f"  {r['table']:28s} {r['key']!s:22s} -> {r['value']!s:12s} {r.get('review_note', '')}")
    print("\nMERGE rules with a justification:")
    for r in res:
        if r["status"] == "MERGE" and not r.get("needs_review"):
            print(f"  {r['table']:28s} {r['key']!s:22s} -> {r['value']!s:12s} {r['justification']}")
    print("\nUNRENDERABLE:")
    for r in res:
        if r["status"] == "UNRENDERABLE":
            print(f"  {r['table']:28s} {r['key']!s:22s} -> {r['value']!s:12s} {r['reason'][:90]}")
    fbs = [r for r in res if r.get("assumes_definition")]
    print(f"\nrules that assume the usual definition of an author macro: {len(fbs)} "
          f"({', '.join(sorted({m for r in fbs for m in r['assumes_definition']}))})")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"counts": dict(c), "not_checked": NOT_CHECKED, "rules": res},
                                   indent=1, ensure_ascii=False))
    print(f"\nJSON report: {args.out}")
    return res


if __name__ == "__main__":
    main()
