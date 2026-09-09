try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Excluded environments: matches inside these are skipped
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_NAMES = [
    "proof", "figure", "table", "tabular", "algorithm", "lstlisting",
    "verbatim", "tikzpicture", "equation", "equation*", "align", "align*",
    "eqnarray", "eqnarray*", "gather", "gather*", "multline", "multline*",
    "displaymath",
]

_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(' + '|'.join(re.escape(e) for e in _EXCLUDED_ENV_NAMES) + r')\}'
    r'.*?'
    r'\\end\{\1\}',
    re.DOTALL | re.IGNORECASE,
)


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Helper: determine structure_type from environment / keyword
# ---------------------------------------------------------------------------
_REMARK_WORDS = re.compile(r'\b(remark)\b', re.IGNORECASE)
_EXAMPLE_WORDS = re.compile(r'\b(example|experiment|illustration|case\s+study|application)\b', re.IGNORECASE)
_ASSUMPTION_WORDS = re.compile(r'\b(assumption|assume|suppose|require|posit)\b', re.IGNORECASE)


def _subtype_from_env(env_name: str, body: str = "") -> str:
    env_lower = re.sub(r'\*$', '', env_name.strip().lower())
    if 'remark' in env_lower or 'rem' == env_lower or 'note' == env_lower or 'rmk' == env_lower:
        return 'remark'
    if 'example' in env_lower or 'exam' == env_lower or 'ex' == env_lower:
        return 'example'
    if 'assumption' in env_lower or 'assump' in env_lower:
        return 'assumption'
    # Fall back to body scan
    if _ASSUMPTION_WORDS.search(body):
        return 'assumption'
    if _REMARK_WORDS.search(body):
        return 'remark'
    if _EXAMPLE_WORDS.search(body):
        return 'example'
    return 'remark'  # default for this family


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern 1: explicit remark/example/assumption environments not in base map
PATTERN_EXPLICIT_ENV = re.compile(
    r'\\begin\{(?P<env>'
    r'(?:my)?(?:remark|Remark|rem|rmk|Rmk|note|Note)'
    r'|(?:my)?(?:example|Example|exam|ex)'
    r'|(?:my)?(?:assumption|Assumption|assump|Assump|assumptions|Assumptions)'
    r')\*?\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\*?\}',
    re.DOTALL,
)

# Pattern 2: \mypar{<heading>} paragraphs
# PRUNED — FP on 1512.05406v1 | also 2 TP — review before uncommenting
# PATTERN_MYPAR = re.compile(
#     r'\\mypar\{(?P<title>[^}]+)\}'
#     r'(?P<body>.*?)'
#     r'(?=\\mypar\{|\\(?:sub)*section\*?\{|\\(?:sub)*section\s|\\begin\{|\Z)',
#     re.DOTALL,
# )

# Pattern 3: \noindent\textbf{Remark/Example/Assumption ...} headed paragraph blocks
PATTERN_TEXTBF_HEADING = re.compile(
    r'\\noindent\s*\\textbf\{(?P<title>[^}]*(?:remark|example|assumption|note)[^}]*)\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\noindent|\\begin\{|\\end\{|\\(?:sub)*section).){20,}?)'
    r'(?=\\noindent|\\begin\{|\\(?:sub)*section|\n\n\n|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 4: \textbf{Remark/Example/Assumption} (without \noindent) heading blocks
PATTERN_TEXTBF_PLAIN = re.compile(
    r'(?:^|\n\n)'
    r'\\textbf\{(?P<title>[^}]*(?:remark|example|assumption|note)[^}]*)\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\textbf\{|\\begin\{|\\end\{|\\(?:sub)*section).){20,}?)'
    r'(?=\\textbf\{[^}]*(?:remark|example|assumption|note)|\\begin\{|\\(?:sub)*section|\n\n\n|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 5: \emph{Remark}/\emph{Example}/\emph{Assumption} at paragraph start
PATTERN_EMPH_HEADING = re.compile(
    r'(?:^|\n\n)'
    r'\\emph\{(?P<title>[^}]*(?:remark|example|assumption|note)[^}]*)\}'
    r'[.\s]*'
    r'(?P<body>(?:(?!\\emph\{[^}]*(?:remark|example|assumption)|\\begin\{|\\end\{|\\(?:sub)*section).){20,}?)'
    r'(?=\\emph\{[^}]*(?:remark|example|assumption|note)|\\begin\{|\\(?:sub)*section|\n\n\n|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 6: inline assumption sentences
# PRUNED — FP on 1508.06062v1, 1512.05406v1, 1712.00232v3 | also 2 TP — review before uncommenting
# PATTERN_INLINE_ASSUMPTION = re.compile(
#     r'(?:^|(?<=[.\n]))'
#     r'[ \t]*'
#     r'(?:[A-Z][^.\n]{0,60},\s*)?'
#     r'(?:we\s+(?:assume|suppose|require|posit)|[Tt]hroughout[^,]*,\s*we\s+(?:assume|suppose|require))'
#     r'[^.\n]*[.]',
#     re.MULTILINE,
# )

# Pattern 7: inter-environment prose blocks (after \end{...}, before \begin{...} or section)
# PRUNED — FP on 1512.05406v1 | also 12 TP — review before uncommenting
# PATTERN_INTERENV_PROSE = re.compile(
#     r'\\end\{(?P<prev_env>[^}]+)\}'
#     r'[ \t]*\n'
#     r'(?P<body>'
#     r'(?:(?!\\begin\{|\\end\{|\\(?:sub)*section\*?\{|\\(?:sub)*section\s|\\mypar\{|\\paragraph\{|\$\$).){80,}?'
#     r')'
#     r'(?=\\begin\{|\\end\{|\\(?:sub)*section\*?\{|\\(?:sub)*section\s|\\mypar\{|\\paragraph\{|\$\$|\Z)',
#     re.DOTALL,
# )

# Pattern 8: \paragraph{Remark/Example/Assumption ...} headed paragraph blocks
PATTERN_PARAGRAPH_HEADING = re.compile(
    r'\\paragraph\{(?P<title>[^}]*(?:remark|example|assumption|note|observation)[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\paragraph\{|\\(?:sub)*section|\\begin\{|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 9: \begin{remark*} style star variants (includes rmk*)
PATTERN_STAR_ENV = re.compile(
    r'\\begin\{(?P<env>(?:remark|rmk|example|assumption|rem|note)\*)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 10: Free-standing remark paragraphs triggered by leading remark-signal phrases.
# PRUNED — FP on 1003.1038v1, 1103.5544v1, 1207.0773v2 +12 more | also 24 TP — review before uncommenting
# PATTERN_FREESTANDING_REMARK = re.compile(...)

# Pattern 11: Free-standing example paragraphs triggered by leading example-signal phrases.
# PRUNED — FP on 1210.4765v1, 1304.5152v1, 1705.02177v2 +3 more | also 4 TP — review before uncommenting
# PATTERN_FREESTANDING_EXAMPLE = re.compile(...)

# Pattern 12: \footnote{...} contents beginning with remark-signaling phrases.
PATTERN_FOOTNOTE_REMARK = re.compile(
    r'\\footnote\{'
    r'[ \t\n]*'
    r'(?:We\s+(?:remark|note|observe|mention|point\s+out)\s+that\b'
    r'|Notice\s+that\b'
    r'|Remark\s*[:.]\s*'
    r')'
    r'(?P<body>[^{}]*(?:\{[^{}]*\}[^{}]*)*)'
    r'\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 12b: \footnote{...} contents beginning with assumption-signaling phrases.
PATTERN_FOOTNOTE_ASSUMPTION = re.compile(
    r'\\footnote\{'
    r'[ \t\n]*'
    r'(?:As\s+pointed\s+out\b'
    r'|As\s+(?:noted|mentioned|discussed|described)\b'
    r'|(?:The\s+logic\s+of|By\s+(?:the\s+)?(?:assumption|definition|convention))\b'
    r'|(?:This\s+(?:assumes|requires|follows\s+from))\b'
    r')'
    r'(?P<body>[^{}]*(?:\{[^{}]*\}[^{}]*)*)'
    r'\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 13: Free-standing prose paragraphs after display-math environments.
# PRUNED — FP on 1512.05406v1, 1601.01819v1, 1705.02177v2 | also 22 TP — review before uncommenting
# PATTERN_POST_DISPLAYMATH_PROSE = re.compile(...)

# Pattern 14: \rem or \remark bare macro (not \begin{remark}) introducing a remark paragraph.
PATTERN_REM_MACRO = re.compile(
    r'(?:^|(?<=\n))'
    r'[ \t]*\\rem(?:ark)?\b(?!\s*\{)'   # \rem or \remark NOT followed by {
    r'[ \t]*'
    r'(?P<body>.*?)'
    r'(?='
        r'\n[ \t]*\n[ \t]*\n'           # 2+ blank lines
        r'|\n[ \t]*\n[ \t]*(?=\\(?:begin|end|section|subsection|rem(?:ark)?)\b)'
        r'|\\begin\s*\{'
        r'|\\end\s*\{'
        r'|\\section\b'
        r'|\\subsection\b'
        r'|\\subsubsection\b'
        r'|\\proof(?:end)?\b'
        r'|\\rem(?:ark)?\b(?!\s*\{)'
        r'|\Z'
    r')',
    re.DOTALL,
)

# Pattern 15: Section/subsection opening paragraphs starting with assumption-like phrases.
# PRUNED — FP on 1111.3171v5, 1209.2510v1, 1304.5152v1 +6 more | also 2 TP — review before uncommenting
# PATTERN_SECTION_OPENING_ASSUMPTION = re.compile(...)

# Pattern 16: \subsubsection{...} delimited example/remark/assumption blocks.
PATTERN_SUBSUBSECTION_BLOCK = re.compile(
    r'\\subsubsection\*?\{(?P<title>[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'(?P<body>.*?)'
    r'(?=\\subsubsection|\\subsection|\\section|\Z)',
    re.DOTALL,
)

# Pattern 17: \noindent{\bf ...}: or \noindent\textbf{...}: note/assumption blocks
# PRUNED — FP on 1103.5544v1
# PATTERN_NOINDENT_BF_HEADING = re.compile(...)

# Pattern 18: Prose assumption paragraphs opening a section/subsection.
# PRUNED — FP on 1103.5544v1, 1209.2510v1, 1301.1423v2 +3 more | also 6 TP — review before uncommenting
# PATTERN_PROSE_SECTION_ASSUMPTION = re.compile(...)

# Pattern 19: Inter-environment prose blocks between known theorem-like environments.
_INTERENV_KNOWN = (
    'theorem', 'lemma', 'proposition', 'corollary', 'definition', 'defn',
    'example', 'remark', 'rmk', 'proof', 'claim', 'conjecture', 'corollary',
    'assumption', 'exercise', 'problem', 'notation', 'convention',
)
_INTERENV_PAT = (
    r'\\end\{(?:' + '|'.join(re.escape(e) for e in _INTERENV_KNOWN) + r')\*?\}'
    r'(?P<prose>'
    r'(?:(?!\\begin\{|\\end\{|\\(?:sub)*section\*?\s*\{|\\paragraph\s*\{).){20,800}?'
    r')'
    r'(?=\\begin\{(?:' + '|'.join(re.escape(e) for e in _INTERENV_KNOWN) + r')\*?\}'
    r'|\\(?:sub)*section\*?\s*\{'
    r'|\\paragraph\s*\{'
    r'|\Z)'
)
# PRUNED — FP on 1103.5544v1, 1502.03482v2, 1512.05406v1 +1 more | also 21 TP — review before uncommenting
# PATTERN_INTERENV_SHORT_PROSE = re.compile(_INTERENV_PAT, re.DOTALL | re.IGNORECASE)

# Pattern 20: "We now ..." paragraphs that introduce or follow up on examples/results.
# PRUNED — FP on 1207.0773v2, 1502.03482v2 | also 2 TP — review before uncommenting
# PATTERN_WE_NOW_INTRO = re.compile(...)

# Pattern 21: Conclusion/Discussion section opening paragraph as a remark-like summary.
# PRUNED — FP on 1301.1423v2, 1510.04064v1, 1512.05406v1 +4 more | also 5 TP — review before uncommenting
# PATTERN_CONCLUSION_SECTION = re.compile(...)

# Pattern 22: Paragraph immediately after \end{<theorem-like env>} beginning with
# remark/intuition lead-in words. Catches post-theorem inline remarks.
PATTERN_POST_ENV_REMARK = re.compile(
    r'\\end\{(?:theorem|lemma|proposition|corollary|claim|thm|lem|prop|cor'
    r'|theorem\*|lemma\*|proposition\*|corollary\*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'[ \t]*\n[ \t]*\n?[ \t]*'
    r'(?P<body>'
    r'(?:The\s+(?:O|o)-notation\b'
    r'|The\s+(?:above|previous|following|stated|presented)\b'
    r'|Note\s+that\b'
    r'|Remark\s*[:.]\s*'
    r'|Observe\s+that\b'
    r'|Notice\s+that\b'
    r'|Recall\s+that\b'
    r'|We\s+(?:remark|note|observe|stress|emphasize|highlight|point\s+out)\b'
    r'|We\s+should\s+(?:note|remark|observe|mention|point\s+out)\b'
    r'|We\s+would\s+like\s+to\s+(?:point\s+out|note|remark|mention|highlight|stress|emphasize)\b'
    r'|It\s+is\s+worth\s+(?:noting|remarking|pointing\s+out|mentioning)\b'
    r'|To\s+give\s+an?\s+(?:intuition|interpretation)\b'
    r'|Intuitively(?:\s+speaking)?\b'
    r'|In\s+particular\b'
    r'|In\s+other\s+words\b'
    r'|Informally\b'
    r'|It\s+should\s+be\s+(?:noted|remarked|observed|mentioned)\b'
    r'|Let\s+us\s+(?:observe|note|remark|recall|mention|point\s+out)\b'
    r'|We\s+have\s+seen\s+that\b'
    r'|This\s+shows\s+that\b'
    r'|Nevertheless\b'
    r'|The\s+(?:algorithm|input)\s+(?:maintains?|for\s+which)\b'
    r'|Here\s+\S'
    r'|In\s+particular\b'
    r'|Although\b'
    r'|However\b'
    r'|Now\s+consider\b'
    r'|The\s+derivation\b'
    r'|Potentially\b'
    r'|A\s+(?:typical|simple|concrete|natural|basic|standard)\s+example\b'
    r'|Another\s+(?:typical|simple|concrete|natural|basic|standard)?\s*example\b'
    r'|Assuming\b'
    r'|We\s+should\s+mention\b'
    r'|For\s+(?:completeness|clarity|the\s+reader)\b'
    r'|The\s+(?:LLL|lemma|theorem|result|bound|estimate|constant|proof)\s+was\b'
    r'|The\s+(?:LLL|lemma|theorem|result|bound|estimate|constant|proof)\s+(?:introduced|proven|stated|improved|established)\b'
    r')'
    r'[^\n]{5,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 22b: Paragraph after \end{<theorem-like env>} that begins with a capital letter
# and contains remark-signal words within the first two sentences.
# PRUNED — FP on 1111.3171v5, 1207.0773v2, 1209.2510v1 +9 more | also 3 TP — review before uncommenting
# PATTERN_POST_ENV_REMARK_GENERAL = re.compile(...)

# Pattern 23: Inline remark paragraphs (between double blank lines) starting with
# intuition/remark lead-in phrases not covered by other patterns.
PATTERN_INLINE_REMARK_LEADIN = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:To\s+give\s+an?\s+(?:intuition|interpretation|overview|sketch)\b'
    r'|Intuitively(?:\s+speaking)?\b'
    r'|The\s+(?:key\s+)?(?:idea|intuition|insight)\s+(?:is|here)\b'
    r'|In\s+other\s+words\b'
    r'|Informally(?:\s+speaking)?\b'
    r'|To\s+see\s+why\b'
    r'|To\s+understand\s+(?:this|why|the)\b'
    r'|The\s+intuition\s+(?:is|behind)\b'
    r')'
    r'[^\n]{5,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 24: Paragraph immediately after \end{itemize/enumerate/description} that
# reads as a clarifying remark.
# PRUNED — FP on 1705.02177v2, 1708.00522v2 | also 2 TP — review before uncommenting
# PATTERN_POST_LIST_REMARK = re.compile(...)

# Pattern 25: Standalone inline assumption paragraphs with assumption lead-ins.
# PRUNED — FP on 1207.0773v2
# PATTERN_INLINE_ASSUMPTION_LEADIN = re.compile(...)

# Pattern 26: Post-proof free-standing remark paragraph.
# PRUNED — FP on 1003.1038v1, 1207.0773v2, 1409.6258v2 +11 more | also 16 TP — review before uncommenting
# PATTERN_POST_PROOF_REMARK = re.compile(...)

# Pattern 27: Keyword-anchored remark paragraphs between double blank lines.
# PRUNED — FP on 1207.0773v2, 1210.4765v1, 1502.03482v2 +4 more | also 6 TP — review before uncommenting
# PATTERN_KEYWORD_ANCHORED_REMARK = re.compile(...)

# Pattern 28: Section-opening remark paragraphs (before the first \begin{} in a section).
# PRUNED — FP on 1103.5544v1, 1207.0773v2, 1210.4765v1 +4 more | also 8 TP — review before uncommenting
# PATTERN_SECTION_OPENING_REMARK = re.compile(...)

# Pattern 29: General \footnote{...} extractor with brace-balanced body.
PATTERN_FOOTNOTE_GENERAL_START = re.compile(r'\\footnote\{')

# Pattern 30: Free-standing prose between environment boundaries with remark-signal phrases.
# PRUNED — FP on 1111.3171v5, 1210.4765v1, 1301.1423v2 +6 more | also 8 TP — review before uncommenting
# PATTERN_INTERENV_REMARK_PROSE = re.compile(...)

# Pattern 31: "Remark:" or "Note:" inline keyword at paragraph start (not inside \begin).
PATTERN_INLINE_KEYWORD_REMARK = re.compile(
    r'(?:^|\n\n)'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:Remark|Note|Observation|Comment)\s*(?:\d+\.?)?\s*[.:\-]\s*'
    r'[^\n]{10,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 32: remark paragraph after theorem-like env, immediately before \subsection ---
PATTERN_PRE_SUBSECTION_REMARK = re.compile(
    r'\\end\{(?:theorem|lemma|proposition|corollary|claim|thm|lem|prop|cor'
    r'|theorem\*|lemma\*|proposition\*|corollary\*|proof|Proof)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'[ \t]*\n[ \t]*\n?[ \t]*'
    r'(?P<body>'
    r'(?:It\s+should\s+be\s+(?:noted|remarked|observed|mentioned)\b'
    r'|Thus\b'
    r'|Therefore\b'
    r'|Hence\b'
    r'|In\s+particular\b'
    r'|In\s+other\s+words\b'
    r'|Note\s+that\b'
    r'|Observe\s+that\b'
    r'|Notice\s+that\b'
    r'|Recall\s+that\b'
    r'|We\s+(?:remark|note|observe|stress|emphasize|highlight|point\s+out|mention)\b'
    r'|It\s+is\s+worth\s+(?:noting|remarking|pointing\s+out|mentioning)\b'
    r'|Intuitively(?:\s+speaking)?\b'
    r'|Informally\b'
    r'|The\s+(?:above|previous|following|stated|presented)\b'
    r'|Let\s+us\s+(?:observe|note|remark|recall|mention|point\s+out)\b'
    r')'
    r'[^\n]{5,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')'
    r'(?=[ \t]*\n[ \t]*\\(?:sub)*section)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 33: Post-algorithm/table/figure remark paragraphs starting with remark-signal phrases.
PATTERN_POST_BLOCK_NOTE = re.compile(
    r'\\end\{(?:algorithm|algorithm\*|table|table\*|figure|figure\*|tabular|tabular\*|lstlisting|verbatim)\}'
    r'(?:[ \t]*(?:\\vspace\{[^}]*\}|\\caption\{[^}]*\}|\\label\{[^}]*\}|\\vspace\*\{[^}]*\}|\\bigskip\b|\\medskip\b|\\smallskip\b|\[[^\]]*\]))*'
    r'[ \t]*\n[ \t]*\n?[ \t]*'
    r'(?P<body>'
    r'(?:Note\s+that\b'
    r'|We\s+(?:should\s+)?(?:note|remark|observe|point\s+out|mention)\s+that\b'
    r'|Observe\s+that\b'
    r'|Notice\s+that\b'
    r'|Recall\s+that\b'
    r'|It\s+is\s+worth\s+(?:noting|remarking)\b'
    r'|In\s+particular\b'
    r'|The\s+(?:above|following|results?|data|table|figure|algorithm)\b'
    r'|It\s+is\s+worth\s+to\s+(?:mention|note|remark)\b'
    r')'
    r'[^\n]{10,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 34: Inline "we assume" / "Since ... we assume" assumption sentences embedded
# in running prose (not at paragraph start).
PATTERN_INLINE_WE_ASSUME = re.compile(
    r'(?:^|(?<=[.\n]))'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:Since\b[^.\n]{0,120},\s*)?'
    r'we\s+assume\b'
    r'[^.\n]*'
    r'(?:\.[^.\n]*(?:we\s+(?:use|adopt|employ|apply)\b[^.\n]*))?'
    r'\.'
    r')',
    re.MULTILINE | re.IGNORECASE,
)

# Pattern 35: Paragraph-level "Comparing ..." / "Similarly, ..." comparative remark
# paragraphs that appear between list environments and before a section boundary.
# PRUNED — FP on 1811.04151v1
# PATTERN_COMPARATIVE_REMARK = re.compile(...)

# Pattern 36: Numbered/titled italic remarks formatted as '{\it N. Title}. Body\\\\'
# outside any LaTeX environment.
PATTERN_ITALIC_NUMBERED_REMARK = re.compile(
    r'\{\\it\s+'
    r'(?P<num>\d+)'
    r'(?:[.\s]+(?P<title>[^}]*?))?'
    r'\}'
    r'[ \t]*\.?[ \t]*'
    r'(?P<body>[^\n]{10,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*)'
    r'(?=\\\\[ \t]*\n|\n[ \t]*\n|\{\\it\s+\d+|\\noindent|\\section|\\subsection|\Z)',
    re.DOTALL,
)

# Pattern 37: \noindent{\bf <Title>.} headed comment/remark blocks (alternative bold style).
# PRUNED — FP on 1906.04768v3
# PATTERN_NOINDENT_BF_COMMENT = re.compile(...)

# Pattern 38: Free-standing 'We assume that' / 'Assume \be...\ee' assumption blocks
# in running text not wrapped in a \begin{assumption} environment.
PATTERN_WE_ASSUME_BLOCK = re.compile(
    r'(?:^|(?<=\n\n))'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:We\s+assume\s+that\b'
    r'|Assume\s+that\b'
    r'|We\s+suppose\s+that\b'
    r'|Suppose\s+that\b'
    r')'
    r'[^\n]{5,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 39: Implicit assumption paragraphs in running prose using WLOG-style phrases.
# PRUNED — FP on 1103.5544v1, 1207.0773v2, 1409.6258v2 +3 more
# PATTERN_IMPLICIT_PROSE_ASSUMPTION = re.compile(...)

# Pattern 40: \begin{compactitem} / \begin{compactenum} environments — split on \item
PATTERN_COMPACTITEM_ENV = re.compile(
    r'\\begin\{(?P<env>compactitem|compactenum|compactdesc)\}'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 41: "We have N remarks / observations" lead-in followed by compactitem/itemize
# PRUNED — FP on 1610.03950v1
# PATTERN_REMARK_LIST_LEADIN = re.compile(...)

# Pattern 42: Prose paragraphs containing assumption keywords at paragraph start.
PATTERN_PROSE_ASSUMPTION_PARAGRAPH = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:'
    r'It\s+is\s+assumed\b'
    r'|[Ww]e\s+(?:are\s+)?assum(?:e|ing)\b'
    r'|[Aa]ccording\s+to\s+(?:the\s+)?(?:standard|usual|classical|conventional)\b[^\n]{0,80}(?:assum(?:e|ing|ption)|methodolog)\b'
    r'|[Ii]n\s+(?:our|this)\s+(?:work|paper|model|study|analysis|simulation)\s*,\s*we\s+assum\w*\b'
    r')'
    r'[^\n]{5,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 43: Paragraph-level prose that describes model/simulation parameter settings.
PATTERN_PARAM_SETTING_ASSUMPTION = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:'
    r'It\s+is\s+assumed\s+that\b[^\n]{0,120}(?:fixed|constant|given)\b'
    r'|[Tt]he\s+(?:initial\s+(?:values?|conditions?)|parameters?|weights?)\b[^\n]{0,80}(?:are\s+given|are\s+(?:taken|fixed|set)\s+(?:to\s+be|as)|follow)\b'
    r'|[Tt]herefore\s*,\s*using\s+the\s+information\b'
    r'|[Aa]ssuming\s+that\s+(?:only\s+)?(?:one|all|each)\b'
    r')'
    r'[^\n]{5,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 44: Post-figure prose paragraphs that explain/interpret results shown in figures.
# PRUNED — FP on 1512.05406v1, 1811.04151v1 | also 1 TP — review before uncommenting
# PATTERN_POST_FIGURE_EXPLANATION = re.compile(...)

# Pattern 45: \noindent\textbf{<title>}: headed paragraph blocks (general, colon-terminated).
PATTERN_NOINDENT_TEXTBF_COLON = re.compile(
    r'\\noindent\s*\\textbf\{(?P<title>[^}]+)\}\s*:'
    r'(?P<body>.*?)'
    r'(?=\\noindent\s*\\textbf\{|\\(?:sub)*section\*?\s*\{|\\(?:sub)*section\b|\\begin\{|\Z)',
    re.DOTALL,
)

# Pattern 46: Inline {\em assume} / \textit{assume} / \emph{assume} markers in prose.
PATTERN_INLINE_EMPH_ASSUME = re.compile(
    r'(?:^|(?<=\n\n)|(?<=\n))'
    r'[ \t]*'
    r'(?P<body>'
    r'[^\n]{0,200}'
    r'(?:\\emph\{assum\w*\}|\\textit\{assum\w*\}|\{\\em\s+assum\w*\}|\\emph\{suppose\w*\}|\\textit\{suppose\w*\}|\{\\em\s+suppose\w*\})'
    r'[^\n]{0,400}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 47: Free-standing prose paragraphs between double blank lines that start with
# discourse connectives signaling a follow-up remark or observation.
PATTERN_DISCOURSE_FOLLOWUP_REMARK = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:In\s+this\s+sense\b'
    r'|An\s+instance\s+is\b'
    r'|As\s+was\s+(?:observed|noted|mentioned|remarked|shown|proved|established)\b'
    r'|As\s+(?:we\s+(?:have\s+)?(?:seen|observed|noted|mentioned|shown|proved)|noted|mentioned|remarked|discussed|observed)\b'
    r'|This\s+shows\s+that\b'
    r'|This\s+implies\s+that\b'
    r'|This\s+means\s+that\b'
    r'|We\s+have\s+seen\s+that\b'
    r'|We\s+have\s+(?:shown|proved|established|observed)\s+that\b'
    r'|Nevertheless\b'
    r'|Before\s+we\s+(?:prove|show|establish|state|present|give|describe|define)\b'
    r'|In\s+(?:the\s+)?(?:above|what\s+follows|what\s+precedes)\b'
    r'|It\s+is\s+easy\s+to\s+(?:check|see|verify)\s+that\b'
    r'|It\s+is\s+(?:clear|immediate|straightforward)\s+(?:that|from)\b'
    r'|We\s+leave\s+(?:the\s+)?(?:proof|verification|details?|rest)\b'
    r'|Of\s+course\b'
    r')'
    r'[^\n]{10,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')'
    r'(?=\n{2,}|\\(?:begin|section|subsection|subsubsection|paragraph)|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 48: Prose paragraphs immediately following \end{comment} or \end{comment*}.
PATTERN_POST_COMMENT_REMARK = re.compile(
    r'\\end\{comment\*?\}'
    r'[ \t]*\n[ \t]*\n?[ \t]*'
    r'(?P<body>'
    r'(?:[A-Z][^\n]{20,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')'
    r')'
    r'(?=\n{2,}|[ \t]*\\begin\{|[ \t]*\\(?:sub)*section|[ \t]*\\paragraph|\Z)',
    re.DOTALL,
)

# Pattern 49: Bold keyword assumption/convention blocks.
PATTERN_BOLD_CONVENTION_ASSUMPTION = re.compile(
    r'(?:\\textbf\{|\{\\bf\s*)'
    r'(?P<title>'
    r'(?:Convention|Conventions|Assumption|Assumptions|Notation|Notations'
    r'|Setup|Standing\s+[Aa]ssumption|Hypothesis|Hypotheses'
    r'|Prerequisites?|Framework|[Ss]etting)'
    r's?'
    r')'
    r'(?:\.?\}|\.?\s*\})'
    r'\.?\s*'
    r'(?P<body>'
    r'(?:(?!\\textbf\{|\{\\bf\s|\\(?:sub)*section\b|\\begin\{|\\end\{).){20,}'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 50: Inline "Throughout this section/paper X is Y" assumption paragraphs.
PATTERN_THROUGHOUT_ASSUMPTION = re.compile(
    r'(?:(?<=\n\n)|(?<=\n\})\s*\n|(?:^))'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:'
    r'Throughout\s+(?:this|the)\s+(?:paper|section|chapter|article|work|rest\s+of\s+(?:the\s+)?(?:paper|section|chapter|article))\b[^\n]*'
    r'|Throughout\s*,\s*[^\n]+'
    r'|Starting\s+from\s+(?:this|now)\b[^\n]*\bwe\s+(?:assume|work|consider|suppose)\b[^\n]*'
    r'|In\s+(?:this|the\s+(?:following|remaining|rest\s+of\s+the))\s+(?:section|paper|chapter|article)\b[^\n]*\bwe\s+(?:assume|work|consider|suppose)\b[^\n]*'
    r'|From\s+now\s+on\b[^\n]*\bwe\s+(?:assume|work|consider|suppose)\b[^\n]*'
    r'|For\s+the\s+(?:remainder|rest)\s+of\s+(?:this\s+)?(?:section|paper|chapter)\b[^\n]*'
    r')'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 51: \item blocks inside \begin{enumerate}...\end{enumerate} as candidate
# remark/observation items.
# PRUNED — FP on 1508.06062v1, 1510.04064v1, 1512.05406v1 +3 more | also 3 TP — review before uncommenting
# PATTERN_ENUMERATE_ITEMS = re.compile(...)

# Pattern 52: \item blocks inside \begin{itemize}...\end{itemize} as candidate
# example/scenario items.
# PRUNED — FP on 1207.0773v2, 1409.6258v2, 1512.05406v1 +3 more | also 4 TP — review before uncommenting
# PATTERN_ITEMIZE_ITEMS = re.compile(...)

# Pattern 53: Prose paragraph immediately after \end{<any theorem-like or block env>}
# that begins with a capital letter and has remark-like signal words.
# PRUNED — FP on 1003.1038v1, 1103.5544v1, 1111.3171v5 +16 more | also 14 TP — review before uncommenting
# PATTERN_POST_BLOCK_GENERAL_REMARK = re.compile(...)

# Pattern 54: Subsection body opening paragraph (before first \begin{} in the subsection).
# PRUNED — FP on 1207.0773v2, 1209.2510v1, 1412.0216v2 +5 more | also 8 TP — review before uncommenting
# PATTERN_SUBSECTION_OPENING_EXAMPLE = re.compile(...)

# Pattern 55: Prose paragraphs containing "For identifiability" / "we impose the constraint"
# / constraint-setting phrases that signal an inline assumption.
PATTERN_CONSTRAINT_ASSUMPTION = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'[^\n]{0,100}'
    r'(?:For\s+identifiab\w+\b'
    r'|we\s+impose\s+(?:the\s+)?constraint\b'
    r'|we\s+impose\s+(?:the\s+)?condition\b'
    r'|we\s+impose\s+(?:the\s+)?restriction\b'
    r'|subject\s+to\s+the\s+constraint\b'
    r'|subject\s+to\s+the\s+condition\b'
    r'|the\s+(?:constraint|condition|restriction)\s+that\b'
    r'|to\s+ensure\s+identifiab\w+\b'
    r'|to\s+ensure\s+uniqueness\b'
    r')'
    r'[^\n]{5,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 56: First paragraph of a \section{...} with a title matching example/experiment
# keywords — catches numerical experiment sections, illustration sections, etc.
# PRUNED — FP on 1304.5152v1, 1412.0216v2, 1510.04064v1 +1 more | also 2 TP — review before uncommenting
# PATTERN_SECTION_EXAMPLE_OPENING = re.compile(...)

# Pattern 57: Inline assumption sentences in running prose anchored on
# "is assumed to be" / "assumed to have" / "assumed to satisfy" constructions.
PATTERN_IS_ASSUMED_TO = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'[^\n]*\b(?:is\s+assumed\s+to\s+(?:be|have|satisfy|hold|extend|exist|denote)'
    r'|are\s+assumed\s+to\s+(?:be|have|satisfy|hold|extend|exist)'
    r'|assumed\s+to\s+(?:be|have|satisfy|hold)\b'
    r')\b'
    r'[^\n]{0,500}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 58: Section-opening remark paragraphs where the section title does NOT match
# example/assumption keywords, targeting narrative intro prose that reviews context,
# states contributions, or describes the paper structure.
# PRUNED — FP on 1111.3171v5, 1207.0773v2, 1301.1423v2 +6 more | also 7 TP — review before uncommenting
# PATTERN_SECTION_REMARK_OPENING = re.compile(...)

# Pattern 59: Inline bold/italic keyword-introduced theorem-like blocks outside \begin{}.
# Catches {\bf Example}, \textbf{Example}, {\it Remark}, etc. at paragraph start,
# followed by body up to the next structural boundary.
PATTERN_INLINE_BOLD_KEYWORD_ENV = re.compile(
    r'(?:^|\n\n)'
    r'[ \t]*'
    r'(?:'
    r'\{\\(?:bf|it|em)\s+(?P<kw1>(?:[Ee]xample|[Rr]emark|[Aa]ssumption|[Dd]efinition|[Ll]emma|[Tt]heorem|[Pp]roposition|[Cc]orollary|[Cc]laim|[Cc]onjecture|[Pp]roblem|[Ee]xercise|[Nn]ote|[Oo]bservation)s?)\}'
    r'|\\(?:textbf|textit|emph)\{(?P<kw2>(?:[Ee]xample|[Rr]emark|[Aa]ssumption|[Dd]efinition|[Ll]emma|[Tt]heorem|[Pp]roposition|[Cc]orollary|[Cc]laim|[Cc]onjecture|[Pp]roblem|[Ee]xercise|[Nn]ote|[Oo]bservation)s?)\}'
    r')'
    r'(?:\s*\d*\.?\s*)?'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'[ \t]*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\(?:sub)*section\b).){10,}?)'
    r'(?=\n\n|\n[ \t]*\n|\\begin\{|\\(?:sub)*section\b|'
    r'\{\\(?:bf|it|em)\s+(?:[A-Z][a-z]+)|\\(?:textbf|textit|emph)\{(?:[A-Z][a-z]+)|\Z)',
    re.DOTALL,
)

# Pattern 60: \item entries inside \begin{enumerate} with a leading bold/italic name
# (condition name pattern), classified as assumptions.
PATTERN_ENUMERATE_NAMED_ITEM = re.compile(
    r'\\begin\{enumerate\}'
    r'(?P<body>.*?)'
    r'\\end\{enumerate\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 61: Prose paragraph starting with "Here, ..." or "Here we ..." that describes
# properties/conditions of mathematical objects — common assumption-like statements.
PATTERN_HERE_PROSE_ASSUMPTION = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'Here[,\s]+'
    r'(?:the\s+|we\s+|it\s+is\s+)?'
    r'[^\n]{10,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')'
    r'(?=\n{2,}|[ \t]*\\begin\{|[ \t]*\\(?:sub)*section|[ \t]*\\paragraph|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 62: Assumption-signaling choice/model paragraphs: "we choose/select/adopt/opt for"
# a particular model or approach. Common in math/CS papers that fix a model before analysis.
# PRUNED — FP on 1111.3171v5, 1409.6258v2, 1510.04064v1 +7 more | also 3 TP — review before uncommenting
# PATTERN_WE_CHOOSE_MODEL = re.compile(...)

# Pattern 63: Subsection/section opening paragraphs under headings that do NOT contain
# example/assumption keywords, where the paragraph body contains a remark-signal phrase.
# PRUNED — FP on 1103.5544v1, 1207.0773v2, 1210.4765v1 +4 more | also 3 TP — review before uncommenting
# PATTERN_SUBSECTION_REMARK_OPENING = re.compile(...)

# Pattern 64: \paragraph{<any heading>} blocks where body contains remark/assumption/example signals.
# PRUNED — FP on 1502.03482v2, 1803.04122v2 | also 2 TP — review before uncommenting
# PATTERN_PARAGRAPH_GENERIC = re.compile(...)

_PARAGRAPH_GENERIC_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|however|moreover|'
    r'furthermore|in\s+particular|in\s+fact|it\s+is\s+worth|this\s+shows|this\s+implies|'
    r'we\s+(?:remark|note|observe|emphasize|stress|mention|point\s+out|sketched|underline)|'
    r'we\s+expect|we\s+anticipate|we\s+believe|let\s+us\s+(?:mention|recall|note|briefly)|'
    r'again\s*,\s*we|one\s+immediately|the\s+(?:infra.red|crucial|key|main)\s+'
    r'(?:difference|connection|consequence|observation|point)|'
    r'can\s+be\s+readily|can\s+be\s+(?:generalized|extended)|'
    r'(?:carries?|carry)\s+over|pfaffian\s+point\s+process|'
    r'has\s+drastic\s+consequences|do\s+not\s+expect)\b',
    re.IGNORECASE,
)

_PARAGRAPH_GENERIC_ASSUMPTION_SIGNAL_RE = re.compile(
    r'\b(?:assume|assumed|assuming|suppose|throughout|fix|fixed|require|required|'
    r'given\s+that|it\s+is\s+assumed|we\s+work\s+(?:over|in|with)|'
    r'let\s+\S+\s+(?:be|denote))\b',
    re.IGNORECASE,
)

_PARAGRAPH_GENERIC_EXAMPLE_SIGNAL_RE = re.compile(
    r'\b(?:simulation|experiment|dataset|data\s+generating|scenario|benchmark|'
    r'for\s+example|for\s+instance|as\s+an\s+example|consider\s+the)\b',
    re.IGNORECASE,
)

# Pattern 65: Paragraphs ending with \url{...} — dataset/source description remarks
# (common in ML/CV/NLP papers that describe experimental datasets).
PATTERN_URL_TERMINATED_PARAGRAPH = re.compile(
    r'(?:\n\n|(?<=\}\n\n))'
    r'(?P<body>'
    r'[A-Z][^\n]{20,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r'[^\n]*\\url\{[^}]+\}'
    r')'
    r'(?=[ \t]*\n)',
    re.DOTALL,
)

# Pattern 66: {\bfseries <heading>} introduced paragraphs (inline bold heading style).
# Common in ML/CV papers for named sub-paragraphs like training parameters, network details.
PATTERN_BFSERIES_HEADING_PARAGRAPH = re.compile(
    r'(?:^|\n\n)'
    r'[ \t]*'
    r'\{\\bfseries\s+(?P<heading>[^}]+)\}'
    r'[ \t]+'
    r'(?P<body>'
    r'(?:(?!\{\\bfseries|\\(?:sub)*section\b|\\begin\{|\\end\{).){20,}?'
    r')'
    r'(?=\n\n|\{\\bfseries|\\(?:sub)*section\b|\\begin\{|\Z)',
    re.DOTALL,
)

# Pattern 67: Standing-assumption block — lead-in sentence (e.g. "For the rest of the
# paper we fix the following.") immediately followed by \begin{itemize}...\end{itemize}
# containing \item Let / \item Fix clauses.  Catches the pattern where authors list
# global notations/fixings as a bulleted list after a lead-in.
PATTERN_STANDING_ASSUMPTION_ITEMIZE = re.compile(
    r'(?:^|\n\n)'
    r'[ \t]*'
    r'(?P<leadin>'
    r'(?:For\s+the\s+(?:rest|remainder)\s+of\s+(?:this\s+)?(?:paper|section|chapter|article)\b[^.\n]*\.'
    r'|Throughout\s+(?:this|the)\s+(?:paper|section|chapter|article|work)\b[^.\n]*\.'
    r'|In\s+(?:this|the\s+(?:following|rest\s+of\s+the))\s+(?:paper|section|chapter|article)\b[^.\n]*\.'
    r'|We\s+(?:fix|adopt|use)\s+the\s+following\b[^.\n]*\.'
    r'|We\s+(?:fix|make|introduce|recall|set\s+up)\s+(?:the\s+following\s+)?(?:notation|conventions?|definitions?|assumptions?)\b[^.\n]*\.'
    r')'
    r')'
    r'[ \t]*\n[ \t]*'
    r'\\begin\{itemize\}'
    r'(?P<body>.*?)'
    r'\\end\{itemize\}',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 68: Inline subsection/section-local assumption sentence.
# Catches "In this subsection/section, we assume that ..." or
# "Throughout this subsection, we ..." as standalone assumption statements.
PATTERN_INLINE_SUBSECTION_ASSUMPTION = re.compile(
    r'(?:^|\n\n)'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:In\s+this\s+(?:subsection|section|paragraph)\b[^,.\n]{0,60},\s*we\s+(?:assume|suppose|fix|work)\b'
    r'|Throughout\s+this\s+(?:subsection|section|paragraph)\b[^,.\n]{0,60},\s*we\b'
    r'|In\s+this\s+(?:subsection|section|paragraph)\s+we\s+(?:assume|suppose|fix|work)\b'
    r')'
    r'[^\n]{5,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 69: {\bf <Title>} or \textbf{<Title>} bold header (possibly after \noindent
# or \\ or blank line) immediately followed by \begin{enumerate}...\end{enumerate}.
# Catches named axiom/assumption blocks like "{\bf Geometric axioms for X}\n\begin{enumerate}...".
PATTERN_BOLD_ENUM_BLOCK = re.compile(
    r'(?:^|\n)'
    r'[ \t]*(?:\\noindent\s*|\\newline\s*|\\\\[ \t]*\n[ \t]*|\\bigskip\s*\\newline\s*)?'
    r'(?:\{\\bf\s+(?P<title1>[^}]+)\}|\\textbf\{(?P<title2>[^}]+)\})'
    r'[ \t]*\n[ \t]*'
    r'\\begin\{enumerate\}'
    r'(?P<body>.*?)'
    r'\\end\{enumerate\}',
    re.DOTALL,
)

# Pattern 70: \par-prefixed prose paragraphs between structural boundaries that contain
# remark/observation/assumption signal phrases. Targets the \par paragraph style common
# in older LaTeX documents. Only fires when a strong signal word is present.
PATTERN_PAR_PROSE_SIGNAL = re.compile(
    r'\\par\b[ \t]*'
    r'(?P<body>'
    r'(?:(?!\\par\b|\\begin\{|\\end\{|\\(?:sub)*section\b|\\paragraph\b).){20,}?'
    r')'
    r'(?=\\par\b|\\begin\{|\\end\{|\\(?:sub)*section\b|\\paragraph\b|\n{2,}|\Z)',
    re.DOTALL,
)

# Pattern 71: Inter-environment prose blocks containing example-signal phrases.
# Catches prose paragraphs between \end{...} and \begin{...} that contain
# example-signaling phrases like "A typical example", "For instance", etc.
# More conservative than the pruned PATTERN_INTERENV_PROSE — requires explicit
# example-signal anchor in the matched body.
PATTERN_INTERENV_EXAMPLE_PROSE = re.compile(
    r'\\end\{(?:[^}]{1,40})\}'
    r'(?P<body>'
    r'(?:(?!\\begin\{|\\end\{|\\(?:sub)*section\*?\s*\{|\\paragraph\s*\{).){10,1200}?'
    r')'
    r'(?=\\begin\{(?:[^}]{1,40})\}'
    r'|\\(?:sub)*section\*?\s*\{'
    r'|\\paragraph\s*\{'
    r'|\Z)',
    re.DOTALL,
)

# Signal phrases for inter-environment example prose
_INTERENV_EXAMPLE_SIGNAL_RE = re.compile(
    r'(?:'
    r'[Aa]\s+(?:typical|simple|concrete|natural|basic|standard|key|first|second|further)\s+example\b'
    r'|[Aa]nother\s+(?:typical|simple|concrete|natural|basic|standard)?\s*example\b'
    r'|[Ff]or\s+(?:example|instance)\b'
    r'|[Aa]s\s+an?\s+(?:example|illustration|application)\b'
    r'|[Oo]ne\s+(?:(?:important|key|typical|natural|simple|basic|concrete|standard)\s+)?example\b'
    r'|[Cc]onsider\s+(?:the\s+(?:following\s+)?)?example\b'
    r'|[Tt]he\s+following\s+example\b'
    r'|[Tt]o\s+illustrate\b'
    r'|[Ww]e\s+illustrate\b'
    r'|[Ii]t\s+is\s+easy\s+to\s+(?:see|check|verify)\s+that\b'
    r'|[Ww]ithout\s+loss\s+of\s+generality\b'
    r'|[Ww][Ll][Oo][Gg]\b'
    r'|[Ww]e\s+can\s+(?:take|choose|consider|verify|check)\b'
    r'|[Oo]ne\s+can\s+(?:check|verify|show|see)\b'
    r')',
    re.IGNORECASE,
)

# Pattern 72: Post-theorem/lemma prose paragraph beginning with "We should mention" /
# "We should note" / "The [result/lemma/theorem] was introduced/proven by..." —
# captures historical/bibliographic remarks that appear after theorem environments.
PATTERN_POST_ENV_HISTORICAL_REMARK = re.compile(
    r'\\end\{(?:theorem|lemma|proposition|corollary|claim|thm|lem|prop|cor'
    r'|theorem\*|lemma\*|proposition\*|corollary\*|theo|Theo)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'[ \t]*\n[ \t]*\n?[ \t]*'
    r'(?P<body>'
    r'(?:We\s+should\s+mention\b'
    r'|We\s+should\s+note\b'
    r'|We\s+should\s+point\s+out\b'
    r'|We\s+mention\s+that\b'
    r'|We\s+note\s+that\b'
    r'|The\s+(?:above\s+)?(?:result|theorem|lemma|proposition|corollary|bound|estimate|inequality|proof)\s+(?:was|were|is|has\s+been)\s+(?:introduced|proven|proved|established|obtained|shown|improved|generalized|first\s+proved)\b'
    r'|The\s+(?:constant|exponent|bound)\s+(?:was|were)\s+(?:subsequently|later|first|originally)\b'
    r'|(?:The\s+)?(?:first|original|earlier)\s+(?:proof|version|result)\s+(?:of\s+(?:this|the)|was|appeared)\b'
    r'|For\s+(?:completeness|clarity|the\s+sake\s+of\s+completeness|the\s+reader)\b'
    r'|(?:This|The)\s+(?:result|theorem|lemma|proposition)\s+(?:is\s+due\s+to|was\s+(?:first\s+)?(?:proved|proven|established|obtained)\s+by)\b'
    r'|(?:Second|Third|Finally|Also)\s*,\s*(?:there\s+is|we\s+(?:note|mention|remark|should\s+mention|should\s+note))\b'
    r'|Second\s*,\s*\S'
    r'|Third\s*,\s*\S'
    r'|Finally\s*,\s*\S'
    r')'
    r'[^\n]{5,}(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|paragraph))[^\n]*)*'
    r')',
    re.DOTALL | re.IGNORECASE,
)

# Pattern 73: Paragraphs between double blank lines beginning with "Notice that" /
# "Observe that" / "Note that" — catches inline observation remarks not preceded by
# a theorem environment (which Pattern 22 requires).
PATTERN_NOTICE_THAT_REMARK = re.compile(
    r'(?:^|\n{2,})'
    r'[ \t]*'
    r'(?P<body>'
    r'(?:Notice\s+that\b'
    r'|Observe\s+that\b'
    r'|Note\s+that\b'
    r'|Recall\s+that\b'
    r'|We\s+(?:remark|note|observe|mention|point\s+out)\s+that\b'
    r'|It\s+is\s+worth\s+(?:noting|remarking|pointing\s+out|mentioning)\s+that\b'
    r'|It\s+should\s+be\s+(?:noted|remarked|observed|mentioned)\s+that\b'
    r'|Let\s+us\s+(?:note|remark|observe|recall|mention|point\s+out)\s+that\b'
    r')'
    r'[^\n]{10,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph))[^\n]*)*'
    r')'
    r'(?=\n{2,}|[ \t]*\\(?:begin|section|subsection|subsubsection|paragraph)|\Z)',
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 74: Free-standing prose paragraphs between structural LaTeX boundaries
# (\\end{...}, \\begin{...}, \\section, \\medskip/bigskip/smallskip, double blank
# lines) that are substantial enough (>= 60 chars) and contain a remark-signal word.
# Targets the class of remarks that appear as plain paragraphs with no environment
# wrapper, e.g. after \end{thm} and before \subsection or \medskip.
# Conservative: requires an explicit remark-signal phrase so as not to match
# arbitrary prose.
# ---------------------------------------------------------------------------
PATTERN_STRUCTURAL_BOUNDARY_PROSE = re.compile(
    r'(?:'
    r'\\end\{[^}]{1,60}\}'
    r'|\\(?:medskip|bigskip|smallskip)\b'
    r'|\\(?:sub)*section\*?\{[^}]*\}'
    r'|\n{2,}'
    r')'
    r'[ \t\n]*'
    r'(?P<body>'
    r'(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph|medskip|bigskip|smallskip)\b)'
    r'(?![ \t]*\n)'
    r'[A-Z][^\n]{30,}'
    r'(?:\n(?![ \t]*\n)(?![ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph|medskip|bigskip|smallskip))[^\n]*)*'
    r')'
    r'(?='
    r'[ \t]*\n[ \t]*\n'
    r'|[ \t]*\\(?:begin|end|section|subsection|subsubsection|paragraph|medskip|bigskip|smallskip)\b'
    r'|\Z'
    r')',
    re.DOTALL,
)

# Signal words required for PATTERN_STRUCTURAL_BOUNDARY_PROSE to fire
_STRUCTURAL_BOUNDARY_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:'
    r'however\b|moreover\b|furthermore\b|nevertheless\b|unlike\b|indeed\b'
    r'|note\s+that\b|observe\s+that\b|notice\s+that\b|recall\s+that\b'
    r'|we\s+(?:remark|note|observe|mention|point\s+out|emphasize|stress|highlight)\b'
    r'|it\s+is\s+(?:worth|tempting|natural|important|easy\s+to\s+see)\b'
    r'|it\s+should\s+be\s+(?:noted|remarked|observed|mentioned)\b'
    r'|in\s+particular\b|in\s+other\s+words\b|in\s+fact\b'
    r'|this\s+(?:shows|means|implies|follows|is\s+impossible|cannot)\b'
    r'|analogous(?:ly)?\b|similarly\b|by\s+analogy\b'
    r'|for\s+compact\s+operators\b|the\s+analogous\s+result\b'
    r'|was\s+(?:shown|proved|established|obtained)\s+in\b'
    r'|it\s+was\s+(?:shown|proved|established|obtained)\b'
    r'|related\s+to\b|is\s+related\s+to\b'
    r'|the\s+following\s+(?:submajorization|result|lemma|theorem|proposition|corollary)\b'
    r'|we\s+will\s+(?:use|need|not\s+need|employ|apply)\b'
    r'|we\s+will\s+not\b'
    r'|differ(?:s|ent|ence)?\s+from\b'
    r'|unlike\s+in\b'
    r'|as\s+in\b'
    r'|can\s+(?:be\s+regarded|take\s+large\s+jumps|be\s+obtained)\b'
    r')',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Brace-balanced footnote extractor helper
# ---------------------------------------------------------------------------

def _extract_all_footnotes(text: str):
    """
    Yield (body_str, match_start, match_end) for every \\footnote{...} in text,
    using a brace-depth scanner to handle nested braces.
    """
    for m in PATTERN_FOOTNOTE_GENERAL_START.finditer(text):
        start = m.start()
        pos = m.end()  # position after opening brace
        depth = 1
        while pos < len(text) and depth > 0:
            ch = text[pos]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            pos += 1
        body = text[m.end():pos - 1]
        yield body, start, pos


# ---------------------------------------------------------------------------
# Footnote content classifiers
# ---------------------------------------------------------------------------

_FOOTNOTE_REMARK_RE = re.compile(
    r'(?:We\s+(?:remark|note|observe|mention|point\s+out)\s+that\b'
    r'|Notice\s+that\b'
    r'|Remark\s*[:.]\s*'
    r'|Note\s+that\b'
    r'|It\s+is\s+worth\s+(?:noting|remarking)\b'
    r'|Observe\s+that\b'
    r'|To\s+avoid\s+\w+'
    r'|A\s+(?:formal|rigorous)\s+\w+'
    r'|This\s+(?:observation|remark|note)\b'
    r')',
    re.IGNORECASE,
)

_FOOTNOTE_ASSUMPTION_RE = re.compile(
    r'(?:As\s+pointed\s+out\b'
    r'|As\s+(?:noted|mentioned|discussed|described)\b'
    r'|The\s+logic\s+of\b'
    r'|By\s+(?:the\s+)?(?:assumption|definition|convention)\b'
    r'|This\s+(?:assumes|requires)\b'
    r'|Only\s+one\s+\w+\b'
    r'|(?:each|every)\s+(?:respondent|participant|subject)\b'
    r')',
    re.IGNORECASE,
)

_FOOTNOTE_EXAMPLE_RE = re.compile(
    r'(?:For\s+(?:example|instance)\b'
    r'|As\s+an\s+example\b'
    r'|An\s+example\s+of\b'
    r')',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Item splitter helper
# ---------------------------------------------------------------------------

def _split_list_items(body: str) -> List[str]:
    """Split a list environment body into individual \\item texts."""
    parts = re.split(r'\\item\b', body)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Named item splitter: extracts (name, body) pairs from \item entries
# ---------------------------------------------------------------------------

_ITEM_NAMED_PREFIX_RE = re.compile(
    r'^\s*'
    r'(?:'
    r'\{\\(?:bf|it|em)\s*(?P<name1>[^}]+)\}'
    r'|\\(?:textbf|textit|emph)\{(?P<name2>[^}]+)\}'
    r')'
    r'[\s.]*',
    re.DOTALL,
)


def _split_named_items(body: str) -> List[tuple]:
    """
    Split enumerate body into (name, item_body) pairs.
    name is None if no leading bold/italic prefix found.
    """
    raw_items = re.split(r'\\item\b', body)
    results = []
    for part in raw_items[1:]:
        part = part.strip()
        if not part:
            continue
        nm = _ITEM_NAMED_PREFIX_RE.match(part)
        name = None
        item_body = part
        if nm:
            name = (nm.group('name1') or nm.group('name2') or '').strip().rstrip('.')
            item_body = part[nm.end():]
        results.append((name, item_body.strip()))
    return results


# ---------------------------------------------------------------------------
# Remark/example signal regexes for item content classification
# ---------------------------------------------------------------------------

_ITEM_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:observe|note\s+that|notice\s+that|remark|however|moreover|furthermore|'
    r'in\s+particular|in\s+other\s+words|interestingly|it\s+(?:can|should)\s+be\s+(?:seen|noted|observed)|'
    r'we\s+(?:observed?|noted?|remark|see|found|obtain)|'
    r'empirical|simulation|test|rejection|nominal|power|performance)\b',
    re.IGNORECASE,
)

_ITEM_EXAMPLE_SIGNAL_RE = re.compile(
    r'\b(?:scenario|case|example|instance|situation|setting|model|data\s+(?:were|was)\s+generated|'
    r'generated\s+according|given\s+by|specified\s+by|defined\s+as|'
    r'Scenario\s+\d|Case\s+\d)\b',
    re.IGNORECASE,
)

_ITEM_ASSUMPTION_SIGNAL_RE = re.compile(
    r'\b(?:assume|assumed|assuming|suppose|supposed|throughout|fix|fixed|'
    r'require|required|given\s+that|it\s+is\s+assumed|'
    r'ellipticity|inf.sup|stability|condition|property|bound|estimate|exists|'
    r'there\s+exists|independent\s+of|uniformly|positive\s+constant|constant\s+[A-Z])\b',
    re.IGNORECASE,
)

# Named item assumption: item has a leading bold name (condition name)
_ITEM_HAS_NAMED_PREFIX_RE = re.compile(
    r'^\s*(?:\{\\(?:bf|it|em)\s*[^}]+\}|\\(?:textbf|textit|emph)\{[^}]+\})',
    re.DOTALL,
)

# Signal words for general post-env remark classification
_POST_ENV_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|'
    r'however|although|moreover|furthermore|in\s+particular|in\s+fact|'
    r'it\s+is\s+worth|this\s+shows|this\s+implies|we\s+(?:remark|note|observe|'
    r'emphasize|stress|mention|point\s+out)|it\s+should\s+be\s+(?:noted|remarked|'
    r'observed|mentioned)|intuitively|informally|the\s+(?:above|previous|following)|'
    r'the\s+derivation|potentially|now\s+consider|condition\s+\S+\s+(?:requires|assumes|'
    r'places|implies)|can\s+be\s+(?:strengthened|relaxed|extended|improved|verified)|'
    r'can\s+be\s+(?:satisfied|achieved|computed|obtained|shown)|'
    r'relates\s+to|depends\s+on|assumes\s+that|the\s+(?:bound|estimate|error|result|'
    r'approach|algorithm|method))\b',
    re.IGNORECASE,
)

# Signal words for subsection opening example classification
_SUBSECTION_EXAMPLE_SIGNAL_RE = re.compile(
    r'\b(?:simulation|simulations|experiment|experiments|dataset|data\s+set|'
    r'data\s+generating|generated|scenario|scenarios|setting|settings|'
    r'benchmark|benchmarks|comparison|comparisons|evaluation|evaluations|'
    r'we\s+(?:generated|examined|consider|compare|evaluate|test|use|apply)|'
    r'our\s+(?:dataset|data|experiment|simulation|approach|method|goal)|'
    r'the\s+goal|in\s+this\s+(?:section|subsection)\s+we|'
    r'we\s+(?:first|now|next|then)\s+(?:generated?|examined?|consider|compare))\b',
    re.IGNORECASE,
)

_SUBSECTION_EXAMPLE_TITLE_RE = re.compile(
    r'\b(?:simulation|experiment|example|data|dataset|application|'
    r'illustration|case\s+study|benchmark|evaluation|numerical|empirical)\b',
    re.IGNORECASE,
)

# Signal for section-opening remark
_SECTION_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|however|moreover|'
    r'furthermore|in\s+particular|in\s+fact|it\s+is\s+worth|it\s+is\s+reasonable|'
    r'it\s+is\s+important|it\s+is\s+natural|no\s+previous|there\s+has\s+been\s+no|'
    r'there\s+is\s+no|to\s+our\s+knowledge|we\s+(?:remark|note|observe|emphasize|stress|'
    r'mention|point\s+out|give|provide|obtain|prove|show|present|introduce|develop|extend|'
    r'improve|generalize|combine|compare|discuss|analyze|study|examine|consider|establish)|'
    r'we\s+also\s+(?:give|prove|show|present|introduce|develop|extend|improve|obtain)|'
    r'in\s+addition|in\s+contrast|on\s+the\s+other\s+hand|this\s+(?:shows|implies|means|'
    r'gives|yields|follows|completes|concludes|establishes|proves)|as\s+a\s+(?:result|'
    r'consequence|corollary|byproduct)|with\s+the\s+(?:quasi-optimal|optimal|sharp|improved)'
    r')\b',
    re.IGNORECASE,
)

# Signal for is_assumed_to pattern
_IS_ASSUMED_ANCHOR_RE = re.compile(
    r'\b(?:is\s+assumed\s+to\s+(?:be|have|satisfy|hold|extend|exist|denote)'
    r'|are\s+assumed\s+to\s+(?:be|have|satisfy|hold|extend|exist)'
    r'|assumed\s+to\s+(?:be|have|satisfy|hold)\b'
    r')',
    re.IGNORECASE,
)

# Inline bold keyword subtype mapping
_INLINE_BOLD_KW_SUBTYPE_RE = re.compile(
    r'^(?P<kw>[A-Za-z]+)',
)

_INLINE_BOLD_KW_MAP = {
    'example': 'example', 'examples': 'example',
    'remark': 'remark', 'remarks': 'remark',
    'note': 'remark', 'notes': 'remark',
    'observation': 'remark', 'observations': 'remark',
    'assumption': 'assumption', 'assumptions': 'assumption',
    'definition': 'remark',   # not in our family but map to remark if needed
    'lemma': 'remark',
    'theorem': 'remark',
    'proposition': 'remark',
    'corollary': 'remark',
    'claim': 'remark',
    'conjecture': 'remark',
    'problem': 'remark',
    'exercise': 'remark',
}

# "Here, ..." assumption signal
_HERE_ASSUMPTION_SIGNAL_RE = re.compile(
    r'\b(?:bounded|symmetric|positive\s+definite|uniformly|square.integrable|'
    r'measurable|integrable|continuous|differentiable|smooth|compact|'
    r'is\s+(?:a|an|the)\s+(?:\w+\s+)?(?:tensor|matrix|operator|function|space|map|constant|coefficient)|'
    r'characteriz|properti|satisf|defined|denot|given\s+by|corresponds\s+to|'
    r'compliance|stiffness|elasticity|material)\b',
    re.IGNORECASE,
)

# Signal for we-choose-model assumption paragraphs
_WE_CHOOSE_MODEL_ANCHOR_RE = re.compile(
    r'\b(?:(?:we|I)\s+(?:will\s+)?(?:choose|select|adopt|opt\s+for|fix|use|work\s+with)\b'
    r'|unless\s+otherwise\s+(?:stated|noted|specified|indicated)\b'
    r'|henceforth\b'
    r')',
    re.IGNORECASE,
)

# Signal for subsection opening remark
_SUBSECTION_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|however|moreover|'
    r'furthermore|in\s+particular|in\s+fact|it\s+is\s+worth|it\s+is\s+reasonable|'
    r'it\s+is\s+important|it\s+is\s+natural|we\s+(?:remark|note|observe|emphasize|stress|'
    r'mention|point\s+out|make\s+(?:frequent|extensive|use)|do\s+not\s+work|work\s+in|'
    r'never\s+use|use\s+only|use\s+a|always|predominantly|almost\s+exclusively)|'
    r'our\s+perspective|throughout\s+this|nonetheless\b|exclusively\b|'
    r'it\s+may\s+be\s+worth|it\s+should\s+be\s+noted|we\s+do\s+not|'
    r'the\s+(?:tools|principal\s+tools|main\s+tools|key\s+ingredients|key\s+tools))\b',
    re.IGNORECASE,
)

# Signal for {\bfseries} heading paragraph classification
_BFSERIES_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|however|moreover|'
    r'furthermore|in\s+particular|in\s+fact|it\s+is\s+worth|this\s+shows|this\s+implies|'
    r'we\s+(?:remark|note|observe|emphasize|stress|mention|point\s+out)|'
    r'dataset|consists?\s+of|comprises?|obtained\s+from|captured\s+by|'
    r'contains?|includes?|has\s+(?:a\s+)?(?:size|resolution|total)|'
    r'randomly\s+selected|widely\s+known|pathological|segmentation|'
    r'training|testing|hardware|implementation|learning\s+rate|'
    r'iterations?|epochs?|framework|GPU|CPU|graphics\s+card)\b',
    re.IGNORECASE,
)

# Signal for standing assumption itemize lead-in
_STANDING_ASSUMPTION_ITEM_SIGNAL_RE = re.compile(
    r'\\item\s+(?:Let|Fix|Set|Assume|Suppose|Denote|Write|Define)\b',
    re.IGNORECASE,
)

# Signal for bold enum block classification
_BOLD_ENUM_ASSUMPTION_TITLE_RE = re.compile(
    r'\b(?:axiom|axioms|geometric\s+axiom|assumption|assumptions|'
    r'condition|conditions|hypothesis|hypotheses|setup|setting|'
    r'convention|conventions|notation|notations|definition|definitions|'
    r'properties|property|framework|standing)\b',
    re.IGNORECASE,
)

# Signal for \par prose paragraphs — require strong remark/assumption/example words
_PAR_PROSE_REMARK_SIGNAL_RE = re.compile(
    r'\b(?:note\s+that|observe\s+that|notice\s+that|recall\s+that|remark|'
    r'in\s+particular|in\s+other\s+words|it\s+is\s+worth|'
    r'we\s+(?:remark|note|observe|emphasize|stress|mention|point\s+out)|'
    r'it\s+should\s+be\s+(?:noted|remarked|observed|mentioned)|'
    r'intuitively|informally)\b',
    re.IGNORECASE,
)

_PAR_PROSE_ASSUMPTION_SIGNAL_RE = re.compile(
    r'\b(?:we\s+assume\s+that|assume\s+that|we\s+suppose\s+that|suppose\s+that|'
    r'throughout\s+(?:this|the)\s+(?:paper|section|chapter|article)\b|'
    r'it\s+is\s+assumed\s+that|we\s+(?:fix|require)\s+that)\b',
    re.IGNORECASE,
)

_PAR_PROSE_EXAMPLE_SIGNAL_RE = re.compile(
    r'\b(?:for\s+example|for\s+instance|as\s+an\s+example|'
    r'we\s+illustrate|to\s+illustrate|consider\s+the\s+(?:following\s+)?example)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex spans overlap with an already-kept result."""
    kept: List[dict] = []
    for r in sorted(results, key=lambda x: x.get('_start', 0)):
        r_start = r.get('_start', 0)
        r_end = r.get('_end', r_start + len(r['raw_latex']))
        overlaps = any(
            _intervals_overlap(r_start, r_end, k.get('_start', 0),
                               k.get('_end', k.get('_start', 0) + len(k['raw_latex'])))
            for k in kept
        )
        if not overlaps:
            kept.append(r)
    # Remove internal keys
    for r in kept:
        r.pop('_start', None)
        r.pop('_end', None)
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_simpleenv(text: str) -> List[dict]:
    results: List[dict] = []

    # --- Rule 1: explicit named environments (includes rmk, rmk*) ---
    for m in PATTERN_EXPLICIT_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        raw = body.strip()
        if not raw:
            continue
        stype = _subtype_from_env(env, raw)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_EXPLICIT_ENV',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 9: star environments (includes rmk*) ---
    for m in PATTERN_STAR_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        env = m.group('env')
        opt = m.group('opt')
        body = m.group('body')
        raw = body.strip()
        if not raw:
            continue
        stype = _subtype_from_env(env, raw)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_STAR_ENV',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 2: \mypar{} blocks ---
    # PRUNED: body commented out
    pass

    # --- Rule 3: \noindent\textbf{Remark/Example/Assumption} blocks ---
    for m in PATTERN_TEXTBF_HEADING.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        stype = _subtype_from_env(title, body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_TEXTBF_HEADING',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 4: \textbf{Remark/Example/Assumption} plain (no \noindent) ---
    for m in PATTERN_TEXTBF_PLAIN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        stype = _subtype_from_env(title, body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_TEXTBF_PLAIN',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 5: \emph{Remark/Example/Assumption} heading blocks ---
    for m in PATTERN_EMPH_HEADING.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        stype = _subtype_from_env(title, body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_EMPH_HEADING',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 8: \paragraph{Remark/Example/Assumption} heading blocks ---
    for m in PATTERN_PARAGRAPH_HEADING.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        stype = _subtype_from_env(title, body)
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PARAGRAPH_HEADING',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 6: inline assumption sentences ---
    pass  # PRUNED: body commented out

    # --- Rule 7: inter-environment prose blocks ---
    # PRUNED: body commented out
    pass

    # --- Rule 10: free-standing remark paragraphs with signal phrases ---
    pass  # PRUNED: body commented out

    # --- Rule 11: free-standing example paragraphs with signal phrases ---
    pass  # PRUNED: body commented out

    # --- Rule 12: \footnote{...} contents with remark-signal phrases ---
    for m in PATTERN_FOOTNOTE_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_FOOTNOTE_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 12b: \footnote{...} contents with assumption-signal phrases ---
    for m in PATTERN_FOOTNOTE_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_FOOTNOTE_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 29: general brace-balanced \footnote{...} extractor ---
    for body, start, end in _extract_all_footnotes(text):
        if _inside_excluded_env(text, start, end):
            continue
        raw = body.strip()
        if not raw or len(raw) < 30:
            continue
        if _FOOTNOTE_ASSUMPTION_RE.search(raw):
            stype = 'assumption'
        elif _FOOTNOTE_REMARK_RE.search(raw):
            stype = 'remark'
        elif _FOOTNOTE_EXAMPLE_RE.search(raw):
            stype = 'example'
        else:
            continue  # No clear signal — skip to avoid FP
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_FOOTNOTE_GENERAL_START',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 13: prose paragraphs following display-math environments ---
    # PRUNED: body commented out
    pass

    # --- Rule 14: \rem / \remark bare macro (not \begin{remark}) ---
    for m in PATTERN_REM_MACRO.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_REM_MACRO',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 15: section/subsection opening assumptions ---
    pass  # PRUNED: body commented out

    # --- Rule 16: \subsubsection{...} delimited example/remark/assumption blocks ---
    _EXAMPLE_TITLE_RE = re.compile(
        r'\b(?:example|examples|illustration|case\s+study|application|experiment)\b',
        re.IGNORECASE,
    )
    _REMARK_TITLE_RE = re.compile(
        r'\b(?:remark|note|observation|comment)\b',
        re.IGNORECASE,
    )
    _ASSUMPTION_TITLE_RE = re.compile(
        r'\b(?:assumption|setup|setting|notation|convention|hypothesis)\b',
        re.IGNORECASE,
    )
    _ENCLOSING_SUBSECTION_RE = re.compile(
        r'\\subsection\*?\{(?P<sub>[^}]*)\}',
        re.IGNORECASE,
    )

    _subsection_positions = [
        (m.start(), m.group('sub'))
        for m in _ENCLOSING_SUBSECTION_RE.finditer(text)
    ]

    def _enclosing_subsection_title(pos: int) -> str:
        title = ''
        for sub_start, sub_title in _subsection_positions:
            if sub_start <= pos:
                title = sub_title
            else:
                break
        return title

    for m in PATTERN_SUBSUBSECTION_BLOCK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 30:
            continue

        if _EXAMPLE_TITLE_RE.search(title):
            stype = 'example'
        elif _REMARK_TITLE_RE.search(title):
            stype = 'remark'
        elif _ASSUMPTION_TITLE_RE.search(title):
            stype = 'assumption'
        else:
            enclosing = _enclosing_subsection_title(start)
            if _EXAMPLE_TITLE_RE.search(enclosing):
                stype = 'example'
            elif _REMARK_TITLE_RE.search(enclosing):
                stype = 'remark'
            elif _ASSUMPTION_TITLE_RE.search(enclosing):
                stype = 'assumption'
            else:
                continue

        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_SUBSUBSECTION_BLOCK',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 17: \noindent{\bf ...}: note/assumption blocks ---
    # PRUNED: body commented out
    pass

    # --- Rule 18: prose assumption paragraphs opening a section/subsection ---
    pass  # PRUNED: body commented out

    # --- Rule 19: inter-environment short prose between known theorem-like environments ---
    _INTERENV_SIGNAL_RE = re.compile(
        r'\b(?:note|remark|observe|notice|recall|we\s+have|we\s+see|we\s+point|'
        r'it\s+is\s+worth|in\s+particular|in\s+fact|consequently|therefore|thus|'
        r'however|moreover|furthermore|as\s+a\s+(?:result|consequence|corollary)|'
        r'this\s+(?:shows|means|implies|tells)|from\s+(?:this|the\s+above)|'
        r'example\s+\d|for\s+example|for\s+instance|as\s+an\s+example)\b',
        re.IGNORECASE,
    )
    # PRUNED: body commented out
    pass

    # --- Rule 20: "We now ..." / "We have shown that ..." / "Recall that ..." paragraphs ---
    # PRUNED: body commented out
    pass

    # --- Rule 21: Conclusion/Discussion section opening paragraph ---
    pass  # PRUNED: body commented out

    # --- Rule 22: paragraph immediately after \end{<theorem-like env>} with remark lead-in ---
    for m in PATTERN_POST_ENV_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        # Classify: check if example-signal present, then assumption, then remark
        if _INTERENV_EXAMPLE_SIGNAL_RE.search(raw[:200]):
            stype = 'example'
        elif _ASSUMPTION_WORDS.search(raw[:100]):
            stype = 'assumption'
        else:
            stype = 'remark'
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_POST_ENV_REMARK',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 22b: general paragraph after \end{<theorem-like or block env>} with remark signals ---
    pass  # PRUNED: body commented out

    # --- Rule 23: inline remark paragraphs with intuition/informality lead-ins ---
    for m in PATTERN_INLINE_REMARK_LEADIN.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_REMARK_LEADIN',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 24: paragraph immediately after \end{itemize/enumerate/description} ---
    pass  # PRUNED: body commented out

    # --- Rule 25: standalone inline assumption paragraphs with assumption lead-ins ---
    # PRUNED: body commented out
    pass

    # --- Rule 26: post-proof free-standing remark paragraphs ---
    pass  # PRUNED: body commented out

    # --- Rule 27: keyword-anchored remark paragraphs between structural boundaries ---
    pass  # PRUNED: body commented out

    # --- Rule 28: section-opening remark paragraphs ---
    # PRUNED: body commented out
    pass

    # --- Rule 30: free-standing prose between environment boundaries with remark-signal phrases ---
    pass  # PRUNED: body commented out

    # --- Rule 31: inline keyword remark paragraphs (bare "Remark:", "Note:", etc.) ---
    for m in PATTERN_INLINE_KEYWORD_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_KEYWORD_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 32: remark paragraph after theorem-like env, immediately before \subsection ---
    for m in PATTERN_PRE_SUBSECTION_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PRE_SUBSECTION_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 33: post-algorithm/table/figure remark paragraphs ---
    for m in PATTERN_POST_BLOCK_NOTE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_POST_BLOCK_NOTE',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 34: inline "we assume" / "Since ... we assume" assumption sentences ---
    for m in PATTERN_INLINE_WE_ASSUME.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_WE_ASSUME',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 35: comparative remark paragraphs after list/table environments ---
    pass  # PRUNED: body commented out

    # --- Rule 36: numbered/titled italic remark blocks '{\it N. Title}. Body\\' ---
    for m in PATTERN_ITALIC_NUMBERED_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = (m.group('title') or '').strip()
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_ITALIC_NUMBERED_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 37: \noindent{\bf <Title>.} headed comment/remark blocks ---
    _BF_COMMENT_TITLE_RE = re.compile(
        r'\b(?:remark|note|observation|comment|discussion|comment|warning|claim)\b',
        re.IGNORECASE,
    )
    pass  # PRUNED: body commented out

    # --- Rule 38: free-standing 'We assume that' / 'Assume that' assumption blocks ---
    for m in PATTERN_WE_ASSUME_BLOCK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_WE_ASSUME_BLOCK',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 39: implicit prose assumption paragraphs (WLOG / "we may assume" / etc.) ---
    pass  # PRUNED: body commented out

    # --- Rule 40: compactitem/compactenum environments — each \item is a remark ---
    _COMPACTITEM_CONTEXT_RE = re.compile(
        r'(?:remark|note|observation|comment|point\s+out|mention|highlight|stress)\b',
        re.IGNORECASE,
    )
    for m in PATTERN_COMPACTITEM_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        body = m.group('body')
        context_before = text[max(0, start - 200):start]
        is_remark_context = _COMPACTITEM_CONTEXT_RE.search(context_before)
        items = _split_list_items(body)
        if not items:
            continue
        for item_text in items:
            raw = item_text.strip()
            if not raw or len(raw) < 15:
                continue
            if is_remark_context or _REMARK_WORDS.search(raw):
                stype = 'remark'
            elif _EXAMPLE_WORDS.search(raw):
                stype = 'example'
            elif _ASSUMPTION_WORDS.search(raw):
                stype = 'assumption'
            else:
                stype = 'remark'
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(raw),
                'name': None,
                'env_name': 'distilled',
                'rule_name': 'PATTERN_COMPACTITEM_ENV',
                'structure_type': stype,
                '_start': start,
                '_end': end,
            })

    # --- Rule 41: "We have N remarks" / "The following remarks" lead-in paragraph ---
    pass  # PRUNED: body commented out

    # --- Rule 42: prose paragraphs with explicit assumption keywords at paragraph start ---
    _PROSE_ASSUMPTION_ANCHOR_RE = re.compile(
        r'\b(?:it\s+is\s+assumed\b'
        r'|we\s+(?:are\s+)?assum(?:e|ing)\b'
        r'|according\s+to\s+(?:the\s+)?(?:standard|usual|classical|conventional)\b'
        r'|in\s+(?:our|this)\s+(?:work|paper|model|study|analysis|simulation)\s*,\s*we\s+assum\w*\b'
        r')',
        re.IGNORECASE,
    )
    for m in PATTERN_PROSE_ASSUMPTION_PARAGRAPH.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        if not _PROSE_ASSUMPTION_ANCHOR_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PROSE_ASSUMPTION_PARAGRAPH',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 43: parameter-setting / initial-condition assumption paragraphs ---
    _PARAM_SETTING_ANCHOR_RE = re.compile(
        r'\b(?:it\s+is\s+assumed\s+that\b'
        r'|the\s+(?:initial\s+(?:values?|conditions?)|parameters?|weights?)\b'
        r'|therefore\s*,\s*using\s+the\s+information\b'
        r'|assuming\s+that\s+(?:only\s+)?(?:one|all|each)\b'
        r')',
        re.IGNORECASE,
    )
    for m in PATTERN_PARAM_SETTING_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        if not _PARAM_SETTING_ANCHOR_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PARAM_SETTING_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 44: post-figure explanation paragraphs (remark-type) ---
    pass  # PRUNED: body commented out

    # --- Rule 45: \noindent\textbf{<title>}: headed paragraph blocks (general, colon-terminated) ---
    _NOINDENT_TEXTBF_COLON_REMARK_RE = re.compile(
        r'\b(?:note|remark|observe|notice|recall|however|moreover|furthermore|'
        r'therefore|consequently|thus|hence|in\s+particular|in\s+fact|in\s+other\s+words|'
        r'it\s+is\s+worth|this\s+(?:shows|means|implies)|for\s+example|for\s+instance|'
        r'can\s+be\s+extended|one\s+can|we\s+can|it\s+is\s+clear|it\s+follows)\b',
        re.IGNORECASE,
    )
    for m in PATTERN_NOINDENT_TEXTBF_COLON.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 30:
            continue
        stype = _subtype_from_env(title, body)
        title_lower = title.lower()
        title_has_signal = any(kw in title_lower for kw in (
            'remark', 'note', 'observation', 'comment', 'example', 'assumption',
            'discussion', 'warning', 'extension', 'generalization',
        ))
        if not title_has_signal and not _NOINDENT_TEXTBF_COLON_REMARK_RE.search(body):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_NOINDENT_TEXTBF_COLON',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 46: inline {\em assume} / \emph{assume} / \textit{assume} markers ---
    for m in PATTERN_INLINE_EMPH_ASSUME.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_EMPH_ASSUME',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 47: discourse follow-up remark paragraphs ---
    for m in PATTERN_DISCOURSE_FOLLOWUP_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 40:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_DISCOURSE_FOLLOWUP_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 48: prose paragraphs immediately following \end{comment} ---
    for m in PATTERN_POST_COMMENT_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 40:
            continue
        if not _INTERENV_SIGNAL_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_POST_COMMENT_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 49: bold convention/assumption keyword headers ---
    _BOLD_CONVENTION_TITLE_RE = re.compile(
        r'\b(?:convention|conventions|assumption|assumptions|notation|notations'
        r'|setup|standing\s+assumption|hypothesis|hypotheses|prerequisites?|framework|setting)\b',
        re.IGNORECASE,
    )
    for m in PATTERN_BOLD_CONVENTION_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = m.group('title').strip()
        body = m.group('body').strip()
        if not body or len(body) < 30:
            continue
        if not _BOLD_CONVENTION_TITLE_RE.search(title):
            continue
        stype = _subtype_from_env(title, body)
        if stype not in ('assumption', 'remark', 'example'):
            stype = 'assumption'
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_BOLD_CONVENTION_ASSUMPTION',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 50: "Throughout this section/paper X is Y" standing assumption paragraphs ---
    _THROUGHOUT_ANCHOR_RE = re.compile(
        r'\b(?:throughout\s+(?:this|the)\s+(?:paper|section|chapter|article|work|rest)\b'
        r'|throughout\s*,'
        r'|starting\s+from\s+(?:this|now)\b'
        r'|from\s+now\s+on\b'
        r'|for\s+the\s+(?:remainder|rest)\s+of\s+(?:this\s+)?(?:section|paper|chapter)\b'
        r'|in\s+(?:this|the\s+(?:following|remaining))\s+(?:section|paper|chapter|article)\b'
        r')',
        re.IGNORECASE,
    )
    for m in PATTERN_THROUGHOUT_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        if not _THROUGHOUT_ANCHOR_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_THROUGHOUT_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 51: \item blocks inside \begin{enumerate}...\end{enumerate} ---
    pass  # PRUNED: body commented out

    # --- Rule 52: \item blocks inside \begin{itemize}...\end{itemize} ---
    pass  # PRUNED: body commented out

    # --- Rule 53: broad post-block remark paragraphs ---
    pass  # PRUNED: body commented out

    # --- Rule 54: subsection opening example/simulation/data paragraphs ---
    pass  # PRUNED: body commented out

    # --- Rule 55: constraint/identifiability assumption paragraphs ---
    _CONSTRAINT_ANCHOR_RE = re.compile(
        r'\b(?:for\s+identifiab\w+\b'
        r'|we\s+impose\s+(?:the\s+)?(?:constraint|condition|restriction)\b'
        r'|subject\s+to\s+the\s+(?:constraint|condition)\b'
        r'|the\s+(?:constraint|condition|restriction)\s+that\b'
        r'|to\s+ensure\s+(?:identifiab\w+|uniqueness)\b'
        r')',
        re.IGNORECASE,
    )
    for m in PATTERN_CONSTRAINT_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        if not _CONSTRAINT_ANCHOR_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_CONSTRAINT_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 56: first paragraph of a \section{} whose title matches example/experiment keywords ---
    pass  # PRUNED: body commented out

    # --- Rule 57: "is assumed to be/have/satisfy" inline assumption paragraphs ---
    for m in PATTERN_IS_ASSUMED_TO.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        if not _IS_ASSUMED_ANCHOR_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_IS_ASSUMED_TO',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 58: section-opening remark paragraphs (non-example, non-assumption sections) ---
    _SECTION_EXAMPLE_TITLE_RE = re.compile(
        r'\b(?:experiment|example|illustration|numerical|simulation|application|'
        r'benchmark|case\s+stud|evaluation|empirical)\b',
        re.IGNORECASE,
    )
    _SECTION_ASSUMPTION_TITLE_RE = re.compile(
        r'\b(?:assumption|setup|setting|notation|convention|hypothesis|prerequisite|framework)\b',
        re.IGNORECASE,
    )
    _CONCLUSION_TITLE_RE = re.compile(
        r'\b(?:conclusion|conclusions|discussion|summary|concluding)\b',
        re.IGNORECASE,
    )
    pass  # PRUNED: body commented out

    # --- Rule 59: inline {\bf Example}/\textbf{Example} etc. keyword blocks outside \begin{} ---
    for m in PATTERN_INLINE_BOLD_KEYWORD_ENV.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        kw = (m.group('kw1') or m.group('kw2') or '').strip().lower().rstrip('s')
        body = m.group('body').strip()
        opt = m.group('opt')
        if not body or len(body) < 10:
            continue
        # Determine subtype from keyword
        stype = _INLINE_BOLD_KW_MAP.get(kw, None)
        if stype is None:
            stype = _INLINE_BOLD_KW_MAP.get(kw + 's', None)
        if stype is None:
            stype = _subtype_from_env(kw, body)
        # Only keep subtypes in our family
        if stype not in ('remark', 'example', 'assumption'):
            # Try to classify by body content
            stype = _subtype_from_env(kw, body)
            if stype not in ('remark', 'example', 'assumption'):
                continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_BOLD_KEYWORD_ENV',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 60: \item entries in enumerate with named (bold/italic) condition prefix ---
    for m in PATTERN_ENUMERATE_NAMED_ITEM.finditer(text):
        env_start, env_end = m.start(), m.end()
        if _inside_excluded_env(text, env_start, env_end):
            continue
        body = m.group('body')
        named_items = _split_named_items(body)
        if not named_items:
            continue
        for name, item_body in named_items:
            raw = item_body.strip()
            if not raw or len(raw) < 15:
                continue
            # Only process items that have a leading named prefix (condition names)
            if name is None:
                continue
            # Classify: named conditions in enumerate are assumption-like by default;
            # but check body signals too.
            if _ITEM_EXAMPLE_SIGNAL_RE.search(raw):
                stype = 'example'
            elif _ITEM_REMARK_SIGNAL_RE.search(raw):
                stype = 'remark'
            else:
                stype = 'assumption'
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(raw),
                'name': name if name else None,
                'env_name': 'distilled',
                'rule_name': 'PATTERN_ENUMERATE_NAMED_ITEM',
                'structure_type': stype,
                '_start': env_start,
                '_end': env_end,
            })

    # --- Rule 61: "Here, <description of mathematical object>" assumption-like paragraphs ---
    for m in PATTERN_HERE_PROSE_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        # Require a signal indicating mathematical property description
        if not _HERE_ASSUMPTION_SIGNAL_RE.search(raw):
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_HERE_PROSE_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 62: "we choose/select/adopt/opt for" model/assumption paragraphs ---
    pass  # PRUNED: body commented out

    # --- Rule 63: subsection/subsubsection opening remark paragraphs ---
    _SUBSECTION_EXAMPLE_TITLE_RE2 = re.compile(
        r'\b(?:simulation|experiment|example|data|dataset|application|'
        r'illustration|case\s+study|benchmark|evaluation|numerical|empirical)\b',
        re.IGNORECASE,
    )
    _SUBSECTION_ASSUMPTION_TITLE_RE2 = re.compile(
        r'\b(?:assumption|setup|setting|notation|convention|hypothesis|prerequisite|framework)\b',
        re.IGNORECASE,
    )
    pass  # PRUNED: body commented out

    # --- Rule 64: \paragraph{<generic heading>} blocks with remark/assumption/example signals ---
    # PRUNED: body commented out
    pass

    # --- Rule 65: paragraphs ending with \url{...} — dataset/source description remarks ---
    for m in PATTERN_URL_TERMINATED_PARAGRAPH.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_URL_TERMINATED_PARAGRAPH',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 66: {\bfseries <heading>} introduced paragraphs ---
    for m in PATTERN_BFSERIES_HEADING_PARAGRAPH.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        heading = m.group('heading').strip()
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        # Require some content signal to reduce false positives
        if not _BFSERIES_REMARK_SIGNAL_RE.search(raw):
            continue
        # Classify by heading keyword if possible, else default to remark
        stype = _subtype_from_env(heading, raw)
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': heading if heading else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_BFSERIES_HEADING_PARAGRAPH',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 67: Standing-assumption itemize blocks (lead-in sentence + \begin{itemize}) ---
    for m in PATTERN_STANDING_ASSUMPTION_ITEMIZE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        leadin = m.group('leadin').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        # Require at least one \item Let/Fix/Assume etc. to confirm it's a fixings list
        if not _STANDING_ASSUMPTION_ITEM_SIGNAL_RE.search(body):
            continue
        # The raw_latex includes both the lead-in and the itemize body
        raw = (leadin + '\n\\begin{itemize}\n' + body + '\n\\end{itemize}').strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_STANDING_ASSUMPTION_ITEMIZE',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 68: Inline subsection/section-local assumption sentences ---
    for m in PATTERN_INLINE_SUBSECTION_ASSUMPTION.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INLINE_SUBSECTION_ASSUMPTION',
            'structure_type': 'assumption',
            '_start': start,
            '_end': end,
        })

    # --- Rule 69: {\bf Title} / \textbf{Title} bold header + \begin{enumerate} blocks ---
    for m in PATTERN_BOLD_ENUM_BLOCK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        title = (m.group('title1') or m.group('title2') or '').strip()
        body = m.group('body').strip()
        if not body or len(body) < 20:
            continue
        # Classify: if title mentions axioms/assumptions/conditions, treat as assumption;
        # if it mentions examples, treat as example; else try body signals
        if _BOLD_ENUM_ASSUMPTION_TITLE_RE.search(title):
            stype = 'assumption'
        elif _EXAMPLE_WORDS.search(title):
            stype = 'example'
        elif _REMARK_WORDS.search(title):
            stype = 'remark'
        else:
            # Fall back to body signals
            if _ITEM_ASSUMPTION_SIGNAL_RE.search(body):
                stype = 'assumption'
            elif _ITEM_EXAMPLE_SIGNAL_RE.search(body):
                stype = 'example'
            else:
                stype = 'assumption'  # Default for structured list blocks
        raw = body
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': title if title else None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_BOLD_ENUM_BLOCK',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 70: \par-prefixed prose paragraphs with strong remark/assumption/example signals ---
    for m in PATTERN_PAR_PROSE_SIGNAL.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        # Require a strong signal word to avoid false positives
        if _PAR_PROSE_ASSUMPTION_SIGNAL_RE.search(raw):
            stype = 'assumption'
        elif _PAR_PROSE_REMARK_SIGNAL_RE.search(raw):
            stype = 'remark'
        elif _PAR_PROSE_EXAMPLE_SIGNAL_RE.search(raw):
            stype = 'example'
        else:
            continue  # No clear signal — skip
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_PAR_PROSE_SIGNAL',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 71: inter-environment prose blocks containing example-signal phrases ---
    # Catches prose paragraphs between \end{...} and \begin{...} that explicitly
    # signal an example with a leading phrase. More conservative than the pruned
    # PATTERN_INTERENV_PROSE — requires an explicit example-signal anchor.
    for m in PATTERN_INTERENV_EXAMPLE_PROSE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 30:
            continue
        # Require an explicit example-signal phrase
        if not _INTERENV_EXAMPLE_SIGNAL_RE.search(raw):
            continue
        # Classify subtype
        if _INTERENV_EXAMPLE_SIGNAL_RE.search(raw):
            # Check first 300 chars for example signal — if present, classify as example
            first_part = raw[:300]
            if re.search(
                r'(?:[Aa]\s+(?:typical|simple|concrete|natural|basic|standard|key|first|second|further)\s+example\b'
                r'|[Aa]nother\s+(?:typical|simple|concrete|natural|basic|standard)?\s*example\b'
                r'|[Ff]or\s+(?:example|instance)\b'
                r'|[Aa]s\s+an?\s+(?:example|illustration|application)\b'
                r'|[Oo]ne\s+(?:(?:important|key|typical|natural|simple|basic|concrete|standard)\s+)?example\b'
                r'|[Cc]onsider\s+(?:the\s+(?:following\s+)?)?example\b'
                r'|[Tt]he\s+following\s+example\b'
                r'|[Tt]o\s+illustrate\b'
                r'|[Ww]e\s+illustrate\b)',
                first_part,
                re.IGNORECASE,
            ):
                stype = 'example'
            elif re.search(
                r'(?:[Ii]t\s+is\s+easy\s+to\s+(?:see|check|verify)\s+that\b'
                r'|[Ww]ithout\s+loss\s+of\s+generality\b'
                r'|[Ww][Ll][Oo][Gg]\b'
                r'|[Aa]ssuming\b)',
                first_part,
                re.IGNORECASE,
            ):
                stype = 'example'
            else:
                stype = 'example'
        else:
            stype = 'example'
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_INTERENV_EXAMPLE_PROSE',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # --- Rule 72: post-theorem historical/bibliographic remarks ("We should mention",
    # "The result was introduced by", "Second, ...", etc.) ---
    for m in PATTERN_POST_ENV_HISTORICAL_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_POST_ENV_HISTORICAL_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 73: standalone "Notice that" / "Observe that" / "Note that" paragraphs
    # (not preceded by a theorem env — those are caught by Pattern 22) ---
    for m in PATTERN_NOTICE_THAT_REMARK.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 20:
            continue
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_NOTICE_THAT_REMARK',
            'structure_type': 'remark',
            '_start': start,
            '_end': end,
        })

    # --- Rule 74: Free-standing prose paragraphs between structural LaTeX boundaries
    # that contain an explicit remark-signal word. Targets unwrapped remark paragraphs
    # appearing between \end{...}/\medskip/\bigskip and the next structural element.
    # Conservative: requires minimum length (60 chars) and a strong signal phrase. ---
    for m in PATTERN_STRUCTURAL_BOUNDARY_PROSE.finditer(text):
        start, end = m.start(), m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group('body').strip()
        if not raw or len(raw) < 60:
            continue
        # Require a strong remark-signal word to avoid false positives
        if not _STRUCTURAL_BOUNDARY_REMARK_SIGNAL_RE.search(raw):
            continue
        # Classify: if starts with or strongly signals assumption, classify accordingly
        if _ASSUMPTION_WORDS.search(raw[:150]):
            stype = 'assumption'
        elif _INTERENV_EXAMPLE_SIGNAL_RE.search(raw[:150]):
            stype = 'example'
        else:
            stype = 'remark'
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PATTERN_STRUCTURAL_BOUNDARY_PROSE',
            'structure_type': stype,
            '_start': start,
            '_end': end,
        })

    # Deduplicate and return
    return _deduplicate(results)


# --- realise the selected subset: non-selected PRODUCING rules made inert ---
_SUBSET_NEVER = re.compile(r'(?!x)x')
PATTERN_DISCOURSE_FOLLOWUP_REMARK = _SUBSET_NEVER
PATTERN_FOOTNOTE_ASSUMPTION = _SUBSET_NEVER
PATTERN_FOOTNOTE_REMARK = _SUBSET_NEVER
PATTERN_INLINE_REMARK_LEADIN = _SUBSET_NEVER
PATTERN_INLINE_SUBSECTION_ASSUMPTION = _SUBSET_NEVER
PATTERN_INTERENV_EXAMPLE_PROSE = _SUBSET_NEVER
PATTERN_IS_ASSUMED_TO = _SUBSET_NEVER
PATTERN_POST_ENV_HISTORICAL_REMARK = _SUBSET_NEVER
PATTERN_WE_ASSUME_BLOCK = _SUBSET_NEVER
