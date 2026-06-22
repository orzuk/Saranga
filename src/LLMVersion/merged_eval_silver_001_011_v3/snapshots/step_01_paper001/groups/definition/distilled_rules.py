import re
from typing import List, Dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Very lightweight LaTeX → plain-text cleaner."""
    # Remove comments
    t = re.sub(r"%[^\n]*", "", text)
    # Remove common commands but keep their arguments
    t = re.sub(r"\\(?:textbf|textit|emph|textrm|text|mathrm|mathbf|mathit|"
               r"mathcal|mathbb|mathsf|underline|overline|widehat|widetilde|"
               r"hat|tilde|bar|vec|dot|ddot)\{([^}]*)\}", r"\1", t)
    # Remove \em, \bf etc inside groups
    t = re.sub(r"\{\\(?:em|bf|it|rm|tt|sc)\s+([^}]*)\}", r"\1", t)
    # Remove \label, \ref, \cite, \eqref, \pageref
    t = re.sub(r"\\(?:label|ref|eqref|pageref|cite[a-zA-Z]*)\{[^}]*\}", "", t)
    # Remove \begin{...} and \end{...}
    t = re.sub(r"\\(?:begin|end)\{[^}]*\}", "", t)
    # Remove display math environments
    t = re.sub(r"\\\[.*?\\\]", " <MATH> ", t, flags=re.DOTALL)
    t = re.sub(r"\$\$.*?\$\$", " <MATH> ", t, flags=re.DOTALL)
    # Remove inline math
    t = re.sub(r"\$[^$]*\$", " <MATH> ", t)
    # Remove remaining LaTeX commands
    t = re.sub(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})*", " ", t)
    # Collapse braces
    t = re.sub(r"[{}]", "", t)
    # Normalise whitespace
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# Environments whose content we must NOT mine for extra definitions
_EXCLUDED_ENV_RE = re.compile(
    r"\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|"
    r"prop|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|"
    r"problem|Problem|proof|Proof)\}.*?\\end\{\1\}",
    flags=re.DOTALL | re.IGNORECASE,
)

def _build_excluded_spans(text: str) -> List[tuple]:
    spans = []
    for m in _EXCLUDED_ENV_RE.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(start: int, end: int, excluded_spans: List[tuple]) -> bool:
    for (a, b) in excluded_spans:
        if start >= a and end <= b:
            return True
    return False


def _normalize_name(raw: str) -> str:
    """Strip LaTeX markup from a candidate name string."""
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", raw)
    s = re.sub(r"[{}$]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# C6: {\bf Term:} or {\bf Term} followed by definitional prose
# Ends at \\\\ newline, double-newline, \begin{, \section, \end{document}
# PRUNED — FP on paper001 | also 3 TP — review before uncommenting
# inline_bf_term_pattern = re.compile(
#     r"(?P<full>"
#     r"\{\\bf\s+(?P<name>[^}]{1,120}?)\s*\}"
#     r":?\s*"
#     r"(?P<prose>(?:(?!\{\\bf\s).){10,1200}?)"
#     r"(?=\\\\\s*\n|\n\s*\n|\\begin\{|\\(?:sub)*section\b|\\end\{document\})"
#     r")",
#     flags=re.DOTALL,
# )

# C7: parenthetical '(also called ALIAS)' or '(called ALIAS)' or '(known as ALIAS)'
# PRUNED — FP on paper001 | also 1 TP — review before uncommenting
# inline_also_called_pattern = re.compile(
#     r"(?P<full>"
#     r"(?:[A-Z][^.]{0,200}?)"
#     r"\((?:also\s+)?(?:called|known\s+as)\s+(?P<name>[^)]{1,80})\)"
#     r"[^.]{0,400}?\.)",
#     flags=re.DOTALL,
# )

# C6-plural: extend the C2 "are defined as" anchor (plural of "is defined as")
_c2_plural_anchor = re.compile(
    r"\bare\s+defined\s+(?:as|to\s+be)\b",
    flags=re.IGNORECASE,
)

# tail matcher: everything up to (and including) the next sentence-ending period
# that is NOT swallowed by display math
_c2_tail = re.compile(
    r"(?:\\\[.*?\\\]|\$\$.*?\$\$|[^.])*\.",
    flags=re.DOTALL,
)

# C5: paragraph right after \section/\subsection containing {\em ...} or \textit{...}
_section_heading_re = re.compile(
    r"\\(?:sub)*section\*?\{[^}]*\}",
    flags=re.DOTALL,
)
_em_term_re = re.compile(
    r"(?:\{\\em\s+(?P<name1>[^}]{2,80})\}|\\textit\{(?P<name2>[^}]{2,80})\})",
)
_next_block_re = re.compile(
    r"\n\s*\n|\\begin\{|\\(?:sub)*section\b|\\end\{document\}",
)

# Referential language that disqualifies a match
_referential = re.compile(
    r"\b(?:defined?\s+)?(?:below|above|"
    r"in\s+the\s+(?:next|previous|following|preceding)\s+"
    r"(?:section|chapter|subsection|paragraph))\b",
    flags=re.IGNORECASE,
)

# Negative filter for C6: names that are purely punctuation or very short
_bf_name_negative = re.compile(r"^\s*[\W\d]{0,2}\s*$")


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_definition(text: str) -> List[dict]:
    results: List[dict] = []
    excluded_spans = _build_excluded_spans(text)

    # ------------------------------------------------------------------
    # Mask definition / theorem-like environments so we don't re-mine them
    # ------------------------------------------------------------------
    _all_env_mask = re.compile(
        r"\\begin\{(theorem|Theorem|thm|lemma|Lemma|lem|proposition|Proposition|"
        r"prop|corollary|Corollary|cor|claim|Claim|conjecture|Conjecture|"
        r"problem|Problem|proof|Proof|definition|Definition|defn|dfn|Def|Defn|"
        r"example|Example|remark|Remark|rem)\}.*?\\end\{\1\}",
        flags=re.DOTALL | re.IGNORECASE,
    )
    masked_text = text
    for env_m in _all_env_mask.finditer(text):
        s, e = env_m.start(), env_m.end()
        masked_text = masked_text[:s] + " " * (e - s) + masked_text[e:]

    # ------------------------------------------------------------------
    # Rule C6: {\bf Term:} prose block
#     # ------------------------------------------------------------------
#     for m in inline_bf_term_pattern.finditer(masked_text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_spans):
#             continue
#         full_text = m.group("full")
#         name_raw = m.group("name") or ""
#         # Skip trivially short or punctuation-only names
#         if _bf_name_negative.match(name_raw):
#             continue
#         name_clean = _normalize_name(name_raw)
#         if not name_clean or len(name_clean) < 2:
#             continue
#         if _referential.search(full_text):
#             continue
#         results.append({
#             "raw_latex": full_text,
#             "clean_text": _clean_latex(full_text),
#             "name": name_clean,
#             "env_name": "distilled",
#             "rule_name": "inline_bf_term_pattern",
#             "structure_type": "definition",
#             "_source_pos": s,
#         })

    # ------------------------------------------------------------------
    # Rule C7: parenthetical '(also called ALIAS)' / '(known as ALIAS)'
#     # ------------------------------------------------------------------
#     for m in inline_also_called_pattern.finditer(masked_text):
#         s, e = m.start(), m.end()
#         if _inside_excluded_env(s, e, excluded_spans):
#             continue
#         full_text = m.group("full")
#         name_raw = m.group("name") or ""
#         name_clean = _normalize_name(name_raw)
#         if not name_clean or len(name_clean) < 2:
#             continue
#         if _referential.search(full_text):
#             continue
#         results.append({
#             "raw_latex": full_text,
#             "clean_text": _clean_latex(full_text),
#             "name": name_clean,
#             "env_name": "distilled",
#             "rule_name": "inline_also_called_pattern",
#             "structure_type": "definition",
#             "_source_pos": s,
#         })

    # ------------------------------------------------------------------
    # Rule C6-plural: "are defined as" anchor (plural extension of C2)
    # ------------------------------------------------------------------
    for anchor_m in _c2_plural_anchor.finditer(masked_text):
        s_anchor = anchor_m.start()
        if _inside_excluded_env(s_anchor, anchor_m.end(), excluded_spans):
            continue
        # Look back up to 120 chars for sentence boundary
        look_back = max(0, s_anchor - 120)
        prefix = masked_text[look_back:s_anchor]
        dot_pos = max(prefix.rfind("."), prefix.rfind("\n\n"))
        if dot_pos >= 0:
            name_start = look_back + dot_pos + 1
        else:
            name_start = look_back
        name_text = masked_text[name_start:s_anchor].strip()
        if not name_text or len(name_text) > 120:
            continue
        tail_m = _c2_tail.match(masked_text, anchor_m.end())
        if not tail_m:
            continue
        full_text = masked_text[name_start:tail_m.end()]
        if _referential.search(full_text):
            continue
        name_clean = _normalize_name(name_text)
        results.append({
            "raw_latex": full_text,
            "clean_text": _clean_latex(full_text),
            "name": name_clean or None,
            "env_name": "distilled",
            "rule_name": "_c2_plural_anchor",
            "structure_type": "definition",
            "_source_pos": name_start,
        })

    # ------------------------------------------------------------------
    # Rule C5: paragraph after \section/\subsection containing {\em ...}
    # ------------------------------------------------------------------
    for sec_m in _section_heading_re.finditer(masked_text):
        para_start = sec_m.end()
        # skip leading blank / comment lines
        skip = re.match(r"(?:\s|%[^\n]*\n)*", masked_text[para_start:])
        if skip:
            para_start += skip.end()
        nb = _next_block_re.search(masked_text, para_start)
        para_end = nb.start() if nb else len(masked_text)
        if para_end <= para_start:
            continue
        para_text = masked_text[para_start:para_end]
        if len(para_text.strip()) < 40:
            continue
        if _inside_excluded_env(para_start, para_end, excluded_spans):
            continue
        em_m = _em_term_re.search(para_text)
        if not em_m:
            continue
        name_raw = em_m.group("name1") or em_m.group("name2") or ""
        name_clean = _normalize_name(name_raw)
        if not name_clean or len(name_clean) < 2:
            continue
        if _referential.search(para_text):
            continue
        results.append({
            "raw_latex": para_text,
            "clean_text": _clean_latex(para_text),
            "name": name_clean,
            "env_name": "distilled",
            "rule_name": "_section_heading_re",
            "structure_type": "definition",
            "_source_pos": para_start,
        })

    # ------------------------------------------------------------------
    # Deduplicate overlapping matches (keep longest)
    # ------------------------------------------------------------------
    results.sort(key=lambda r: (r["_source_pos"], -len(r["raw_latex"])))
    deduped: List[dict] = []
    last_end = -1
    for r in results:
        s = r["_source_pos"]
        e = s + len(r["raw_latex"])
        if s < last_end:
            # Overlap: if this one is longer, replace the last
            if deduped and e > last_end:
                prev_s = deduped[-1]["_source_pos"]
                if s <= prev_s:
                    deduped.pop()
                    deduped.append(r)
                    last_end = e
            continue
        deduped.append(r)
        last_end = e

    # Remove internal helper key before returning
    for r in deduped:
        r.pop("_source_pos", None)

    for r in deduped:
        r.pop('_start', None)

    return deduped
