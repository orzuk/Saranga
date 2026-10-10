#!/usr/bin/env python3
"""Prose units: the candidate spans a rule-based extractor may emit as prose nodes.

A prose node of the extraction spec is a run of whole sentences outside the
paper's environments, within one section (checked by extraction_finalize). This
module cuts the prepared source the same way, so that a rule only has to decide
WHETHER a unit is a node and of which type, never where it starts and ends:

  regions    the document body minus environment facts (results, proofs,
             algorithms), floats, the abstract, verbatim code and the
             bibliography; a heading also ends a region
  sentences  each region split at sentence ends (outside inline math, not after
             an abbreviation), at paragraph breaks, at \\item and at list
             environments; a display belongs to the sentence it continues
  units      every run of 1..max_sentences consecutive sentences in one region,
             optionally across paragraph breaks

Offsets are into `fx["source"]`, the prepared source of latex_facts.

    python3 src/prose_units.py paper.tex          # sentence and unit counts
"""
from __future__ import annotations

import bisect
import re
import sys
from dataclasses import dataclass

# environments whose content is never a prose node (besides the facts themselves)
_SKIP_ENVS = re.compile(r"(?:abstract|figure|table|tabular|tabularx|longtable|tikzpicture|"
                        r"thebibliography|verbatim|lstlisting|minted|code|comment|keywords|"
                        r"acknowledg\w*|titlepage)\*?$")
_LIST_ENVS = re.compile(r"(?:enumerate|itemize|description|compactenum|compactitem|"
                        r"inparaenum|asparaenum)\*?$")
_HEADING = re.compile(r"\\(?:part|chapter|(?:sub)*section|paragraph|subparagraph)\*?\s*"
                      r"(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}")
_BIB = re.compile(r"\\bibliography\s*\{|\\begin\s*\{thebibliography\}|\\printbibliography")
# a period after these words does not end a sentence
_ABBREV = re.compile(r"(?:\b(?:e\.g|i\.e|cf|etc|resp|vs|al|Fig|Figs|Eq|Eqs|Thm|Thms|Prop|Lem|"
                     r"Cor|Def|Sec|Secs|Ch|Chap|No|Nos|pp|vol|Rem|Ex|Exer|Alg|Ref|Refs|Th|"
                     r"Prob|Conj|resp|approx|ca|St|Dr|Mr|Ms|Prof)|\b[A-Z])\.$")


def _math_spans(src: str, start: int) -> list[tuple[int, int]]:
    """Inline and $$ math from `start` on: a left-to-right scan, so an escaped \\$
    is skipped and $$ ... $$ is never mistaken for two inline formulas. \\( \\) too."""
    out, i, n, open_at, kind = [], start, len(src), None, None
    while i < n:
        c = src[i]
        if c == "\\":
            if open_at is None and src.startswith("\\(", i):
                j = src.find("\\)", i + 2)
                if j < 0:
                    break
                out.append((i, j + 2)); i = j + 2; continue
            i += 2; continue
        if c == "$":
            two = src.startswith("$$", i)
            if open_at is None:
                open_at, kind = i, ("$$" if two else "$")
                i += 2 if two else 1
            elif kind == "$$" and two or kind == "$" and not two:
                out.append((open_at, i + len(kind))); i += len(kind); open_at = None
            elif kind == "$" and two:             # "$x$$y$": close, then reopen
                out.append((open_at, i + 1)); open_at, kind = i + 1, "$"; i += 2
            else:
                i += 1
            continue
        if c == "\n" and open_at is not None and kind == "$" and src.startswith("\n\n", i):
            open_at = None                         # an unclosed $ does not cross a paragraph
        i += 1
    return out


@dataclass
class Sentence:
    start: int
    end: int
    region: int          # units never cross a region
    para: int            # paragraph within the region


@dataclass
class Unit:
    start: int
    end: int
    first: int           # index of its first sentence
    n: int               # number of sentences


def _masked(source: str, spans: list[tuple[int, int]]) -> str:
    """`source` with each span blanked (same length, offsets kept)."""
    chars = list(source)
    for a, b in spans:
        for i in range(max(a, 0), min(b, len(chars))):
            chars[i] = " "               # line breaks too: a display is not a paragraph break
    return "".join(chars)


def _excluded(fx: dict) -> list[tuple[int, int]]:
    """Spans that are not prose: environment facts, floats and other skipped
    environments, and everything from the bibliography on."""
    out = [(f["outer_start"], f["outer_end"]) for f in fx["facts"]
           if f["kind"] in ("theorem_env", "proof", "algorithm")]
    out += [(e["outer_start"], e["outer_end"]) for e in fx["environments"]
            if _SKIP_ENVS.match(e["env"])]
    src = fx["source"]
    m = _BIB.search(src)
    if m:
        out.append((m.start(), len(src)))
    return sorted(out)


def sentences(fx: dict) -> list[Sentence]:
    """The prose of a paper, as sentences in document order."""
    src = fx["source"]
    body = src.find("\\begin{document}")
    body = body + len("\\begin{document}") if body >= 0 else 0
    excl = _excluded(fx)
    # Region boundaries: excluded spans and headings. Inside a region, break points:
    # paragraph breaks, \item, list openers/closers, and sentence ends.
    cuts: list[tuple[int, int, str]] = []          # (start, end, kind) of non-prose pieces
    cuts += [(a, b, "excluded") for a, b in excl]
    cuts += [(m.start(), m.end(), "heading") for m in _HEADING.finditer(src, body)]
    cuts = sorted(c for c in cuts if c[1] > body)
    merged: list[list] = []
    for a, b, k in cuts:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b, k])
    regions, pos = [], body
    for a, b, _ in merged:
        if a > pos:
            regions.append((pos, a))
        pos = max(pos, b)
    if pos < len(src):
        regions.append((pos, len(src)))

    # math is masked so that a period inside it is not a sentence end; a display
    # stays inside the sentence it continues
    displays = [(d["outer_start"], d["outer_end"]) for d in fx["displays"]]
    inline = _math_spans(src, body)
    plain = _masked(src, displays + inline)

    out: list[Sentence] = []
    for r, (a, b) in enumerate(regions):
        para, start = 0, a
        for kind, p, q in _breaks(src, plain, a, b, displays):
            seg = src[start:p]
            if seg.strip() and re.search(r"[A-Za-z]{2}", seg):
                s0 = start + len(seg) - len(seg.lstrip())
                out.append(Sentence(s0, start + len(seg.rstrip()), r, para))
            if kind == "para":
                para += 1
            start = q
        seg = src[start:b]
        if seg.strip() and re.search(r"[A-Za-z]{2}", seg):
            s0 = start + len(seg) - len(seg.lstrip())
            out.append(Sentence(s0, start + len(seg.rstrip()), r, para))
    return out


def _breaks(src: str, plain: str, a: int, b: int, displays):
    """Break points in src[a:b], in order: (kind, end of the piece before, start
    of the next). Kinds: "para" (blank line, list environment, \\item) and "sent"."""
    found = []
    starts = {d0 for d0, _ in displays}
    ends = {d1 for _, d1 in displays}
    for m in re.finditer(r"\n[ \t]*\n\s*", src[a:b]):
        p, q = a + m.start(), a + m.end()
        if plain[p:q] != src[p:q]:
            continue                          # inside math
        # blank lines around a display inside one sentence ("the result\n\n\[..\]\n\n
        # indicates that"): not a paragraph break
        if q in starts or (src[:p].rstrip() and len(src[:p].rstrip()) in ends
                           and re.match(r"[a-z,;.]", src[q:q + 1])):
            continue
        found.append(("para", p, q))
    for m in re.finditer(r"\\item\b|\\(?:begin|end)\s*\{([^}]*)\}", plain[a:b]):
        if m.group(0).startswith("\\item") or _LIST_ENVS.match(m.group(1) or ""):
            j = a + m.end()
            if m.group(0).startswith("\\item"):
                j = a + m.start()                       # the item text keeps its \item
            found.append(("para", a + m.start(), j))
    for m in re.finditer(r"[.!?](?=[\s})\]$]|$)", plain[a:b]):
        e = a + m.end()
        if _ABBREV.search(plain[max(a, e - 8):e]):
            continue
        nxt = re.match(r"[\s})\]$]*", plain[e:b])
        q = e + (nxt.end() if nxt else 0)
        if q >= b or re.match(r"[A-Z\\(\[]|\n\s*\n", src[q:q + 2]) or src[q:q + 1] in "\\":
            found.append(("sent", e, q))
    for d0, d1 in displays:                             # a display followed by a new sentence
        if a <= d1 < b:
            m = re.match(r"\s*", src[d1:b])
            q = d1 + m.end()
            if q < b and re.match(r"[A-Z]", src[q:q + 1]):
                found.append(("sent", d1, q))
    found.sort(key=lambda x: (x[1], x[2]))
    out, last = [], a
    for kind, p, q in found:
        if p < last:
            continue
        out.append((kind, p, q))
        last = q
    return out


def units(sents: list[Sentence], max_sentences: int = 4,
          cross_paragraphs: bool = False) -> list[Unit]:
    """Every run of 1..max_sentences consecutive sentences in one region."""
    out = []
    for i, s in enumerate(sents):
        for k in range(1, max_sentences + 1):
            j = i + k - 1
            if j >= len(sents) or sents[j].region != s.region:
                break
            if not cross_paragraphs and sents[j].para != s.para:
                break
            out.append(Unit(s.start, sents[j].end, i, k))
    return out


# ---- where a node is: environment body, prose, or neither ------------------------

_SEP = "\\saranganodesep"
_ENV_KINDS = ("theorem_env", "proof", "algorithm")


def _sq(s: str) -> str:
    """Text without \\label/\\index and whitespace (the key _norm_map searches by)."""
    return re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", s or ""))


class Locator:
    """Finds node statements in a paper's prepared source and says which stratum
    each is in:

        env    the body of a LaTeX environment (theorem-like, proof, algorithm)
        prose  in the running prose (overlapping a sentence of sentences())
        other  neither: inside an environment without being it (a definition in
               a proof), in a float or the abstract, or not found

    Silver statements quote the RAW source, with the author's macros; the
    prepared source has them expanded (\\gr -> \\Gamma). So statements are first
    prepared like the source (prepare()), with the paper's own preamble."""

    def __init__(self, tex: str, fx: dict | None = None):
        import latex_facts as L
        from proof_structure import _norm_map
        self.tex = tex
        self.fx = fx if fx is not None else L.extract_facts(tex)
        src = self.fx["source"]
        self.norm, self.idx = _norm_map(src)
        self.sents = sentences(self.fx)
        self.envs = sorted((f["start"], f["end"]) for f in self.fx["facts"]
                           if f["kind"] in _ENV_KINDS)
        self._starts = [s.start for s in self.sents]

    def prepare(self, snippets: list[str]) -> list[str]:
        """Snippets of the raw source as prepare_source makes them: one pass for
        all, with the paper's preamble (its macro definitions)."""
        import latex_facts as L
        if not snippets:
            return []
        b = self.tex.find("\\begin{document}")
        pre = self.tex[:b] if b >= 0 else ""
        doc = (pre + "\\begin{document}\n" + ("\n" + _SEP + "\n").join(snippets)
               + "\n\\end{document}\n")
        out = L.prepare_source(doc)
        body = out[out.find("\\begin{document}") + len("\\begin{document}"):]
        e = body.rfind("\\end{document}")
        parts = (body[:e] if e >= 0 else body).split(_SEP)
        return [x.strip() for x in parts] if len(parts) == len(snippets) else list(snippets)

    def locate(self, prepared: str):
        """(start, end) in fx["source"] of a prepared statement, or None. Exact
        match first, else its first 60 characters (the end then estimated)."""
        k = _sq(prepared)
        if not k:
            return None
        i = self.norm.find(k)
        if i < 0 and len(k) > 60:
            i = self.norm.find(k[:60])
        if i < 0:
            return None
        j = min(i + len(k), len(self.idx)) - 1
        return self.idx[i], self.idx[j] + 1

    def stratum(self, span) -> str:
        if span is None:
            return "other"
        a, b = span
        for s, e in self.envs:
            ov = min(b, e) - max(a, s)
            if ov <= 0:
                continue
            if ov >= 0.8 * (e - s) and ov >= 0.8 * (b - a):
                return "env"
            if ov >= 0.8 * (b - a):
                return "other"                       # nested inside an environment
        return "prose" if self.sentence_range(span) else "other"

    def sentence_range(self, span):
        """Indices of the sentences a span overlaps (empty if none)."""
        if span is None:
            return []
        a, b = span
        k = bisect.bisect_right(self._starts, b - 1)
        out = []
        while k > 0 and self.sents[k - 1].end > a:
            k -= 1
            out.append(k)
        return out[::-1]


def main():
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import latex_facts as L
    fx = L.extract_facts(L.read_tex(sys.argv[1]))
    ss = sentences(fx)
    print(f"sentences {len(ss)}  regions {len({s.region for s in ss})}  "
          f"units(4) {len(units(ss))}  units(4, across paragraphs) {len(units(ss, 4, True))}")
    for s in ss[:8]:
        print("  |", re.sub(r"\s+", " ", fx["source"][s.start:s.end])[:110])


if __name__ == "__main__":
    main()
