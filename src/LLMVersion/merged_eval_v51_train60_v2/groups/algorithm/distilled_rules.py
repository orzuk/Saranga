try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helper: detect whether a span falls inside an excluded environment
# ---------------------------------------------------------------------------
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|Proof|Example|Remark)\}.*?\\end\{\1\}',
    flags=re.DOTALL
)

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    for m in _EXCLUDED_ENV_RE.finditer(text):
        if m.start() <= start and end <= m.end():
            return True
    return False


# ---------------------------------------------------------------------------
# Rule 1: \mypar{Algorithm} – capture the paragraph that follows
# ---------------------------------------------------------------------------
MYPAR_ALGORITHM_RE = re.compile(
    r'\\mypar\s*\{Algorithm\}\s*([\s\S]*?)(?=\\mypar\s*\{|\\subsubsection\s*\{|\\subsection\s*\{|\\section\s*\{|\Z)',
    flags=re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 2: \mypar{<keyword-label>} – algorithmic paragraph labels beyond
#         just "Algorithm" (Construction, Method, Procedure, Recovery, …)
# ---------------------------------------------------------------------------
MYPAR_GENERAL_RE = re.compile(
    r'\\mypar\s*\{([^}]+)\}\s*([\s\S]*?)(?=\\mypar\s*\{|\\subsubsection\s*\{|\\subsection\s*\{|\\section\s*\{|\Z)',
    flags=re.IGNORECASE
)

_ALGO_MYPAR_KEYWORDS_RE = re.compile(
    r'\b(?:algorithm|construction|procedure|method|approach|recovery|sampling|scheme|framework)\b',
    flags=re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 3: Ordinal method paragraphs – "The first/second/… one is based on …"
# ---------------------------------------------------------------------------
ORDINAL_METHOD_RE = re.compile(
    r'(?:(?<=\n\n)|(?<=\A))\s*'
    r'(The\s+(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\w+)\s+one\s+is\s+(?:based\s+on|inspired\s+by|uses?)\b'
    r'[\s\S]*?)'
    r'(?=\n\s*The\s+(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\w+)\s+one\s+is\s+(?:based\s+on|inspired\s+by|uses?)\b'
    r'|\\mypar\s*\{'
    r'|\\subsubsection\s*\{'
    r'|\\subsection\s*\{'
    r'|\\section\s*\{'
    r'|\Z)',
    flags=re.IGNORECASE | re.DOTALL
)

# ---------------------------------------------------------------------------
# Rule 4: Remark/note environments with procedural body
#         (e.g., \begin{remark}...\end{remark} whose body contains a
#          parenthetical title + procedural step sequence)
# ---------------------------------------------------------------------------
REMARK_ENV_RE = re.compile(
    r'\\begin\{(remark|Remark|rem|note|Note)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL
)

_PROCEDURAL_KEYWORDS_RE = re.compile(
    r'\b(first|then|next|finally|step|in order to|start with|compute|use\b.{0,60}to\b|summarize)\b',
    flags=re.IGNORECASE
)

def _is_procedural_body(body: str, min_hits: int = 3) -> bool:
    hits = _PROCEDURAL_KEYWORDS_RE.findall(body)
    return len(hits) >= min_hits

# ---------------------------------------------------------------------------
# Rule 5: Bold-headed procedural paragraphs
#         \noindent{\bf Title} or \textbf{Title} at paragraph start
#         followed by prose with procedural step keywords
# ---------------------------------------------------------------------------
# PRUNED — FP on 1906.04768v3
# BOLD_PARA_ALGORITHM_RE = re.compile(
#     r'(?:(?:\\noindent\s*)\{\\bf\s+([^}]*)\}'
#     r'|(?:\\noindent\s*)?\\textbf\s*\{([^}]*)\})'
#     r'\s*(?P<body>(?:(?!\\(?:section|subsection|chapter)\s*\{|\\begin\s*\{|\\noindent\s*(?:\{\\bf|\{\\textbf|\\textbf)).)+)',
#     flags=re.DOTALL
# )

_BOLD_PARA_STEP_RE = re.compile(
    r'\b(start with|then|next|finally|first|step|in order to|add all|compute|use\b.{0,40}to\b)\b',
    flags=re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 6: Free-standing procedural paragraphs following theorem-like envs
#         Beginning with "To compute/apply/use/find/..." + step keywords
# ---------------------------------------------------------------------------
PROCEDURAL_PARA_RE = re.compile(
    r'(?:(?:\\end\{(?:theorem|Theorem|thm|lemma|Lemma|corollary|Corollary|cor|proposition|Proposition|prop)\})\s*)'
    r'(?P<body>To\s+(?:compute|apply|use|find|determine|construct|verify|obtain)\b'
    r'(?:(?!\n\n|\\begin\s*\{|\\(?:section|subsection|chapter)\s*\{).)*)',
    flags=re.DOTALL
)

_STEP_KW_RE = re.compile(
    r'\b(then|next|finally|first|having|record|define|denot(?:e|ing)|use|reduce|compute|let|choose)\b',
    flags=re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Rule 7: algorithm2e and related environments
#         Covers \begin{algorithm2e}...\end{algorithm2e} and variants,
#         which are produced by the algorithm2e LaTeX package.
# ---------------------------------------------------------------------------
ALGORITHM2E_ENV_RE = re.compile(
    r'\\begin\{(algorithm2e\*?|Algorithm2e\*?|Algorithm2E\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL
)

# ---------------------------------------------------------------------------
# Rule 8 (NUMBERED_STEP_PROSE_RE): numbered-step prose sequences
#         Paragraphs containing 3 or more consecutive parenthesised step
#         markers "(1) ... (2) ... (3) ..." as informal algorithm descriptions.
#
#         NOTE: This heuristic has moderate false-positive risk on any paper
#         that uses numbered lists for non-algorithmic purposes (e.g. data
#         descriptions, related-work enumerations).  The guard conditions
#         below reduce FPs:
#           • The paragraph must contain at least steps (1), (2), (3).
#           • Each step span must contain at least one "action" verb.
#           • The match must NOT fall inside a proof/example/remark env.
#           • Matches overlapping already-accepted spans are deduplicated.
# ---------------------------------------------------------------------------
NUMBERED_STEP_PROSE_RE = re.compile(
    r'(?P<lead>[^\n]{0,300}(?:following\s+steps?|do\s+the\s+following|steps?\s+are|procedure\s+is)[^:\n]{0,100}:?\s*)?'
    r'(?P<body>'
    r'\(1\)\s*[^(]{5,}'
    r'\(2\)\s*[^(]{5,}'
    r'\(3\)\s*[^(]{5,}'
    r'(?:\(\d+\)\s*[^(]{5,})*'
    r')',
    flags=re.DOTALL | re.IGNORECASE
)

_NUMBERED_STEP_ACTION_VERB_RE = re.compile(
    r'\b(?:place|route|legalize|check|extract|compute|apply|run|perform|use|generate|build|'
    r'construct|initialize|select|add|remove|update|determine|verify|obtain|process|execute|'
    r'send|produce|train|test|evaluate|optimize|solve|estimate|sample|assign|set|define)\b',
    flags=re.IGNORECASE
)

def _numbered_step_is_algorithmic(body: str, min_verbs: int = 2) -> bool:
    """Return True if the numbered-step block contains enough action verbs."""
    return len(_NUMBERED_STEP_ACTION_VERB_RE.findall(body)) >= min_verbs

# ---------------------------------------------------------------------------
# Rule 8 (suggested, disabled): plain-prose algorithm paragraphs
#         Items 0 and 1 from paper 1711.00418v8 are unmarked running prose
#         with no LaTeX structural anchor. Any pattern broad enough to catch
#         them reliably would produce massive false positives across arbitrary
#         papers. The illustrative pattern below is left disabled.
#
# prose_alg_pattern = re.compile(
#     r'(?:(?:^|\n)[ \t]*(?:Algorithm|Procedure|Method)\s*[:\-]\s*)'
#     r'(?P<body>.+?)'
#     r'(?=\n{2,}|\\begin|\\section|\\subsection|$)',
#     flags=re.DOTALL | re.IGNORECASE
# )
# Use only if your pipeline already filters by section type.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 9 stubs (not wired in): purely-prose inline algorithm constructions
#         from paper 1508.06062v1. All four items (gold_index 0-3) are
#         multi-paragraph prose blocks with no LaTeX structural anchor.
#         Any pattern broad enough to catch them reliably would produce
#         massive false positives. The stubs below are recorded for
#         documentation purposes only and are NOT wired into
#         extract_distilled_algorithm.
#
# Item 0: No safe generalizable regex exists for purely-prose inline
#         algorithm constructions introduced by 'We define inductively the ...'.
# INLINE_ALGO_PROSE_PATTERN = re.compile(
#     r'(?:We define(?:\s+\w+){0,4}\s+(?:inductively\s+)?the\b[^.]*?(?:as follows|as)'
#     r'[\s\S]{100,2000}?(?=\\(?:sub)?section|\\begin\{(?:lemma|theorem|proof|algorithm)\}|$))',
#     re.IGNORECASE
# )
#
# Item 1: Prose inline algorithm with no LaTeX environment.
# INLINE_ALGO_DEFINE_SHORTCUTS = re.compile(
#     r'(?:We define the [^.\n]{0,60}(?:at level|inductively)[^.\n]{0,60}as)\s*\\\[',
#     re.IGNORECASE
# )
#
# Item 2: Prose inline algorithm introduced by 'Let us define ... as'.
# INLINE_ALGO_LET_DEFINE = re.compile(
#     r'Let us define [^.\n]{0,80}(?:shortcuts|construction|algorithm|procedure)[^.\n]{0,80}as\b'
#     r'[\s\S]{0,2000}?(?=\\(?:sub)?section|\\begin\{(?:lemma|theorem|proof)\})',
#     re.IGNORECASE
# )
#
# Item 3: Prose inline algorithm introduced by 'Define the level n ... as'.
# INLINE_ALGO_DEFINE_LEVEL = re.compile(
#     r'Define the level[^.\n]{0,80}as[^.\n]{0,40}\\\[',
#     re.IGNORECASE
# )
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 10: pseudocode environments (from the pseudocode LaTeX package)
#          Covers \begin{pseudocode}...\end{pseudocode} and variants.
#          The pseudocode package uses:
#            \begin{pseudocode}[style]{Name}{params} ... \end{pseudocode}
#          where [style] is optional (e.g. [ruled], [display]) and
#          {Name}{params} are mandatory braced arguments.
# ---------------------------------------------------------------------------
PSEUDOCODE_ENV_RE = re.compile(
    r'\\begin\{(pseudocode\*?|Pseudocode\*?)\}'
    r'(?:\[(?P<style>[^\]]*)\])?'           # optional [style]
    r'(?:\{(?P<name>[^}]*)\})?'             # optional {Name}
    r'(?:\{(?P<params>[^}]*)\})?'           # optional {params}
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL
)

# ---------------------------------------------------------------------------
# Note on Rule suggestion 2 (paper 1301.1423v2, gold_index 1):
#   Item 1 is a plain-text prose mention of an algorithm by name inside a
#   running paragraph with no enclosing LaTeX environment. Catching arbitrary
#   algorithm mentions in free text requires NLP/semantic understanding and
#   cannot be done with a structural regex without massive false positives.
#   No rule is added for this case.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 11: \item \textbf{<label>} entries inside list environments
#          (itemize, enumerate, compactitem, compactenum, description, …)
#          that describe model variants, methods, or baselines.
#
#          Guard conditions to reduce false positives:
#            • The containing list environment must appear inside a section
#              whose body contains at least one "algorithm-context" keyword
#              (method, model, approach, baseline, system, variant, …).
#              We approximate this by checking a window around the list.
#            • Each \item body must be non-trivial (>= 20 chars after cleaning).
#            • The match must NOT fall inside a proof/example/remark env.
#
#          NOTE: this rule is intentionally conservative. It will miss items
#          that do not follow the \item \textbf{...} structural pattern.
# ---------------------------------------------------------------------------
BOLDITEM_LIST_ENV_RE = re.compile(
    r'\\begin\{(itemize|enumerate|compactitem|compactenum|description)'
    r'(?:\[[^\]]*\])?'
    r'(?:\{[^}]*\})?'
    r'\}'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL | re.IGNORECASE
)

BOLDITEM_ITEM_RE = re.compile(
    r'\\item\s*(?:\[[^\]]*\]\s*)?'
    r'\\textbf\s*\{(?P<label>[^}]+)\}'
    r'(?P<body>.*?)'
    r'(?=\\item|\Z)',
    flags=re.DOTALL
)

# Keywords that suggest the surrounding context is about methods/algorithms
_ALGO_CONTEXT_WINDOW_RE = re.compile(
    r'\b(?:algorithm|method|model|approach|baseline|system|variant|procedure|'
    r'technique|framework|scheme|strategy|implementation|train|compress|'
    r'language model|neural|network)\b',
    flags=re.IGNORECASE
)

_CONTEXT_WINDOW = 600  # characters to look at before the list env

def _list_env_in_algo_context(text: str, list_start: int, min_hits: int = 2) -> bool:
    """Return True if the text window before the list env has enough algo-context keywords."""
    window_start = max(0, list_start - _CONTEXT_WINDOW)
    window = text[window_start:list_start]
    hits = _ALGO_CONTEXT_WINDOW_RE.findall(window)
    return len(hits) >= min_hits

# ---------------------------------------------------------------------------
# Note on new Rule suggestions for paper 1707.03500v1 (gold_index 0 and 1):
#   Both missed items are plain prose paragraphs with no structural LaTeX
#   markers. Item 0 describes a Monte Carlo simulation methodology inside a
#   \section. Item 1 describes numerical solution of an optimal control
#   problem between two \begin{equation}/\end{equation} blocks. Neither has
#   a \begin{algorithm}, \begin{algorithmic}, \caption, \mypar, or any other
#   structural anchor that can be generalized. Any pattern anchored on
#   content tokens ('solver names, variable names, domain terms) would be
#   paper-specific and violate the generalization requirement. No viable
#   general structural regex can be added for these cases.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 12: \section / \subsection whose title contains the word "algorithm"
#          (case-insensitive). The section body is extracted up to the next
#          section/subsection of equal or higher rank, or end of document.
#
#          Guard conditions to reduce false positives:
#            • The section title must contain the literal word "algorithm".
#            • The body must contain at least one action verb from
#              _NUMBERED_STEP_ACTION_VERB_RE (reused from Rule 8).
#            • The body must NOT be empty or trivially short (< 100 chars).
#            • The match must NOT fall inside a proof/example/remark env.
#
#          NOTE: This rule will fire on survey sections titled e.g.
#          "Related Algorithms" that merely discuss algorithms. The action-verb
#          guard reduces but does not eliminate such FPs. The deduplication
#          step ensures that bodies already covered by a \begin{algorithm}
#          environment are not double-counted.
# ---------------------------------------------------------------------------
SECTION_ALGORITHM_TITLE_RE = re.compile(
    r'\\((?:sub)*section)\*?\s*\{([^}]*\balgorithm\b[^}]*)\}'
    r'(?P<body>.*?)'
    r'(?=\\(?:sub)*section\*?\s*\{|\\end\s*\{document\}|\Z)',
    flags=re.IGNORECASE | re.DOTALL
)

# Minimum body length (chars) required before we accept a section-title match
_SECTION_ALGO_MIN_BODY = 100

# Minimum number of action verbs required in the body
_SECTION_ALGO_MIN_VERBS = 2

# ---------------------------------------------------------------------------
# Note on new Rule suggestions for paper 1909.06098v1 (gold_index 0 and 1):
#   Both missed items are plain prose paragraphs with no structural LaTeX
#   markers. Item 0 describes a statistical test procedure (hypothesis
#   rejection rule) interspersed with equation/align environments. Item 1
#   describes a Bonferroni correction procedure as running prose between
#   equation environments and a \begin{comment} block. Neither has a
#   \begin{algorithm}, \begin{algorithmic}, \caption, \mypar, or any other
#   structural anchor that can be generalized. Any pattern anchored on
#   content tokens ('rejected whenever', 'null hypothesis', 'Bonferroni',
#   'eigenfunction', etc.) would be paper-specific and violate the
#   generalization requirement. No viable general structural regex can be
#   added for these cases. Consider a separate NLP/semantic pass for
#   prose-described statistical procedures.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Note on new Rule suggestions for paper 1510.04064v1 (gold_index 2, 3, 4):
#   All three missed items (gold_index 2, 3, 4) are plain prose paragraphs
#   describing competing methods in a comparison section. They have no
#   enclosing LaTeX environment, no \begin{algorithm}, no \caption, no
#   \mypar, no \textbf{Algorithm}, and no other structural LaTeX anchor.
#   The paragraphs open with ordinal or named-method phrases such as
#   "The first was ...", "Our second approach ...", "The final method, ...".
#   Any regex general enough to catch these without hardcoding content tokens
#   (method names, domain vocabulary) would match arbitrary comparison or
#   related-work paragraphs throughout any paper, producing massive false
#   positives. The ordinal-phrase patterns below are documented for reference
#   but are NOT wired in, consistent with the reasoning in the suggestions.
#
# COMPETING_METHOD_PROSE_RE = re.compile(
#     r'(?:(?:The\s+(?:first|second|third|fourth|fifth|final|last)\s+'
#     r'(?:method|approach|algorithm|technique|way|baseline)\b'
#     r'|Our\s+(?:first|second|third|fourth|fifth|final|last)\s+'
#     r'(?:method|approach|algorithm|technique|baseline)\b'
#     r'|The\s+(?:first|second|third|fourth|fifth|final|last)\s+was\b)'
#     r'[\s\S]{80,2000}?)'
#     r'(?=\n\n(?:The\s+(?:first|second|third|fourth|fifth|final|last)\s+'
#     r'(?:method|approach|algorithm|technique|way|baseline)\b'
#     r'|Our\s+(?:first|second|third|fourth|fifth|final|last)\s+'
#     r'(?:method|approach|algorithm|technique|baseline)\b)'
#     r'|\\(?:sub)*section\s*\{|\\begin\s*\{|\\mypar\s*\{|\Z)',
#     flags=re.IGNORECASE | re.DOTALL
# )
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 13: Bold heading ({\bf ...} or \textbf{...}) containing the word
#          "algorithm" (case-insensitive) followed immediately by a
#          \begin{enumerate}...\end{enumerate} block.
#
#          This catches the pattern used in older LaTeX papers that do not
#          use algorithm packages: a bold label names the algorithm and the
#          steps are given as a numbered list.
#
#          Guard conditions to reduce false positives:
#            • The bold heading must contain the literal word "algorithm".
#            • The enumerate block must contain at least 2 \item entries.
#            • The match must NOT fall inside a proof/example/remark env.
# ---------------------------------------------------------------------------
BOLD_HEADING_ENUMERATE_RE = re.compile(
    r'(?:\{\s*\\bf\s+(?P<name1>[^}]*?\balgorithm\b[^}]*?)\}'
    r'|\\textbf\s*\{(?P<name2>[^}]*?\balgorithm\b[^}]*?)\})'
    r'\s*'
    r'(?P<body>\\begin\{enumerate\}.*?\\end\{enumerate\})',
    flags=re.DOTALL | re.IGNORECASE
)

# Minimum number of \item entries required in the enumerate block
_BOLD_ENUM_MIN_ITEMS = 2

def _enumerate_item_count(body: str) -> int:
    """Count the number of \\item entries in an enumerate body."""
    return len(re.findall(r'\\item\b', body))


# ---------------------------------------------------------------------------
# Rule 14: \section / \subsection / \subsubsection whose title contains
#          construction/procedural keywords (construct, procedure, method,
#          computation, build, scheme, routine — but NOT "algorithm" which
#          is already covered by Rule 12).
#
#          This is the generalised version of the pattern described for
#          paper 1412.0216v2: a section titled "The added face bubble
#          functions" or "Construction of X" or "Numerical procedure" etc.
#          whose body contains procedural / constructive mathematics.
#
#          Guard conditions to reduce false positives:
#            • The section title must contain at least one keyword from
#              _SECTION_PROCEDURAL_TITLE_KW_RE.
#            • The body must be non-trivial (>= 150 chars).
#            • The body must contain at least _SECTION_PROC_MIN_VERBS action
#              verbs from _NUMBERED_STEP_ACTION_VERB_RE (reused from Rule 8).
#            • The match must NOT fall inside a proof/example/remark env.
#            • Matches overlapping Rule 12 hits are removed by deduplication.
#
#          NOTE: "method", "scheme", and "procedure" are common English words
#          that appear in many section titles unrelated to algorithms (e.g.
#          "Experimental setup", "Evaluation method"). The action-verb count
#          guard and minimum body length reduce but do not eliminate FPs.
# ---------------------------------------------------------------------------
_SECTION_PROCEDURAL_TITLE_KW_RE = re.compile(
    r'\b(?:construct(?:ion)?|procedure|computation(?:al)?|build(?:ing)?|'
    r'scheme|routine|derivation|formulation|discretization|assembly|'
    r'synthesis|generation|enumeration)\b',
    flags=re.IGNORECASE
)

# PRUNED — FP on 1210.4765v1, 1301.1423v2
# SECTION_PROCEDURAL_TITLE_RE = re.compile(
#     r'\\((?:sub)*section)\*?\s*\{(?P<title>[^}]*)\}'
#     r'(?P<body>.*?)'
#     r'(?=\\(?:sub)*section\*?\s*\{|\\end\s*\{document\}|\Z)',
#     flags=re.IGNORECASE | re.DOTALL
# )

# Minimum body length for Rule 14
_SECTION_PROC_MIN_BODY = 150

# Minimum number of action verbs for Rule 14 (slightly higher than Rule 12
# because the title keyword is weaker evidence)
_SECTION_PROC_MIN_VERBS = 3

# ---------------------------------------------------------------------------
# Note on new Rule suggestions for paper 1804.04206v1 (gold_index 0-15):
#
#   Items 0-8 are plain prose sentences/paragraphs in running text or
#   related-work sections, following the pattern "[Author] et al. [verb] ...
#   [citation]". There is no structural LaTeX anchor (no \begin/\end, no
#   \caption, no \mypar, no environment boundary). Any general regex anchored
#   on "et al." + citation would fire on every related-work sentence in any
#   paper and produce massive false positives. No viable minimal addition
#   is possible for these items.
#
#   Items 9-10 are plain prose paragraphs under \subsection{} with no
#   structural algorithm marker. A subsection-body extractor would be too
#   broad. No viable minimal addition is possible.
#
#   Items 11-15 follow the {\bfseries <label>} paragraph pattern. While
#   this is a structural anchor, it is used for definitions, remarks,
#   methods, and many other purposes throughout arbitrary papers. The
#   pattern alone cannot reliably distinguish algorithm descriptions from
#   other content types without content-specific heuristics that would
#   not generalize. Items 13 and 14 contain "First...Then...Finally" step
#   sequences, but these also appear in proofs and explanations.
#
#   Rule 15a below captures {\bfseries <label>} paragraphs ONLY when the
#   label contains an algorithm-indicative keyword AND the body contains
#   enough action verbs. This is conservative but avoids the false-positive
#   problem noted in the PRUNED Rule 5.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 15a: {\bfseries <label>} or {\bf <label>} paragraphs where the label
#           contains an algorithm-indicative keyword AND the body contains
#           enough action verbs.
#
#           This targets patterns like:
#             {\bfseries Algorithm description} prose...
#             {\bfseries Training procedure} prose...
#             {\bfseries Multi-scale feature extraction} prose...
#
#           Guard conditions:
#             • The label must match _BFSERIES_ALGO_LABEL_KW_RE.
#             • The body must contain >= 2 action verbs.
#             • Body length >= 40 chars.
#             • Must NOT fall inside excluded env.
#
#           NOTE: This is intentionally more conservative than the PRUNED
#           Rule 5 (BOLD_PARA_ALGORITHM_RE). It requires the label itself
#           to be algorithm-indicative, not just the body prose.
# ---------------------------------------------------------------------------
# PRUNED — FP on 1712.00232v3, 1804.04206v1
# BFSERIES_ALGO_PARA_RE = re.compile(
#     r'(?:'
#     r'\{\\bfseries\s+(?P<label1>[^}]+)\}'
#     r'|\{\\bf\s+(?P<label2>[^}]+)\}'
#     r'|\\textbf\s*\{(?P<label3>[^}]+)\}'
#     r')'
#     r'[ \t]*(?P<body>(?:(?!\\(?:sub)*section\s*\*?\s*\{|\\begin\s*\{|'
#     r'\{\\bfseries\s|\{\\bf\s|\\textbf\s*\{).){40,})',
#     flags=re.DOTALL
# )

_BFSERIES_ALGO_LABEL_KW_RE = re.compile(
    r'\b(?:algorithm|procedure|method|approach|training|inference|'
    r'preprocessing|augmentation|prediction|extraction|detection|'
    r'construction|computation|generation|estimation|optimization|'
    r'sampling|initialization|evaluation|processing|architecture|'
    r'network|model|framework|scheme|pipeline|protocol|routine|strategy)\b',
    flags=re.IGNORECASE
)

_BFSERIES_MIN_BODY = 40
_BFSERIES_MIN_VERBS = 2

# ---------------------------------------------------------------------------
# Rule 16: \begin{mdframed}...\end{mdframed} environments that contain
#          algorithmic/protocol content.
#
#          The mdframed environment is commonly used in CS/quantum-info papers
#          to typeset boxed protocol or algorithm descriptions that do not use
#          the algorithm package.  A box is accepted as algorithmic when its
#          body satisfies AT LEAST ONE of:
#            (a) Contains a \begin{enumerate}...\end{enumerate} block with
#                >= 2 \item entries  (structured step list), OR
#            (b) Contains >= 3 procedural keywords (Rule 4's
#                _PROCEDURAL_KEYWORDS_RE test), OR
#            (c) Contains a \textbf{Input} or \textbf{Output} label
#                (common in protocol descriptions).
#
#          Guard conditions to reduce false positives:
#            • Must NOT fall inside a proof/example/remark env.
#            • Body must be non-trivial (>= 40 chars).
#            • The weaker heuristics (b) and (c) each require the body to
#              also contain >= 1 action verb.
#
#          Variant environment names also handled: mdframed*, boxed,
#          tcolorbox, framed — all used for the same purpose.
# ---------------------------------------------------------------------------
MDFRAMED_ENV_RE = re.compile(
    r'\\begin\{(mdframed\*?|Mdframed\*?|tcolorbox|framed|Framed|boxed)\}'
    r'(?:\[[^\]]*\])?'          # optional key=value options
    r'(?:\{[^}]*\})?'           # optional braced argument
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL
)

_MDFRAMED_INPUT_OUTPUT_RE = re.compile(
    r'\\textbf\s*\{(?:Input|Output|Inputs?|Outputs?|Input:|Output:)[^}]*\}'
    r'|\\textbf\s*\{\s*(?:Input|Output)\s*\}',
    flags=re.IGNORECASE
)

def _mdframed_is_algorithmic(body: str) -> bool:
    """Return True if the mdframed body looks like a protocol/algorithm description."""
    if len(body.strip()) < 40:
        return False
    # Condition (a): enumerate with >= 2 items
    enum_m = re.search(r'\\begin\{enumerate\}(.*?)\\end\{enumerate\}', body, flags=re.DOTALL)
    if enum_m and _enumerate_item_count(enum_m.group(0)) >= 2:
        return True
    # Condition (c): Input/Output textbf labels + at least 1 action verb
    if _MDFRAMED_INPUT_OUTPUT_RE.search(body):
        if _NUMBERED_STEP_ACTION_VERB_RE.search(body):
            return True
    # Condition (b): >= 3 procedural keywords + at least 1 action verb
    if _is_procedural_body(_clean_latex(body), min_hits=3):
        if _NUMBERED_STEP_ACTION_VERB_RE.search(body):
            return True
    return False

# ---------------------------------------------------------------------------
# Note on Rule suggestion for paper 1608.03959v1 (gold_index 0):
#   The missed item is free-form prose in the document body (between \par
#   and a \subsection) describing an iterative algorithm method. There is no
#   LaTeX environment wrapping it, no \begin{algorithm}, no \caption, no
#   \mypar, no \textbf{Algorithm}, and no other structural LaTeX anchor.
#   Any pattern broad enough to catch arbitrary free-prose algorithm
#   descriptions would produce massive false positives across arbitrary
#   papers. No viable minimal general structural regex can be added for this
#   case without content-level understanding. Documented here for reference;
#   not wired in.
#
# No minimal general regex can reliably catch free-prose algorithm descriptions
# without a structural LaTeX anchor (\begin{...}...\end{...}, \caption, etc.).
# If the paper uses a custom \newtheorem-like environment (e.g. \begin{algo}...\end{algo}),
# add its name to env_names. Otherwise, a paragraph-level heuristic would be needed.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rule 17: Custom construction/construct environments
#          Covers \begin{construct}...\end{construct},
#          \begin{construction}...\end{construction}, and case variants.
#          These are used in math/CS papers (especially algebra, topology,
#          combinatorics) to typeset step-by-step constructions analogous
#          to algorithms, often defined via \newtheorem or \newenvironment.
#
#          Guard conditions to reduce false positives:
#            • Body must be non-trivial (>= 30 chars).
#            • Must NOT fall inside a proof/example/remark env.
#
#          NOTE: Unlike the base algorithm extractor, we deliberately do NOT
#          require action verbs here because mathematical constructions often
#          use imperative "Set X to ...", "Let Y be ...", "Define Z as ..."
#          phrasing that may not match the action-verb list.
# ---------------------------------------------------------------------------
CONSTRUCT_ENV_RE = re.compile(
    r'\\begin\{(construct\*?|Construct\*?|construction\*?|Construction\*?)\}'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'(?P<body>.*?)'
    r'\\end\{\1\}',
    flags=re.DOTALL
)

_CONSTRUCT_MIN_BODY = 30


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------
def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results whose raw_latex span overlaps an already-accepted one."""
    kept: List[dict] = []
    kept_spans: List[tuple] = []
    for r in results:
        s = r['_start']
        e = r['_end']
        overlaps = any(_spans_overlap(s, e, ks, ke) for ks, ke in kept_spans)
        if not overlaps:
            kept.append(r)
            kept_spans.append((s, e))
    return kept


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------
def extract_distilled_algorithm(text: str) -> List[dict]:
    results: List[dict] = []

    # -- Rule 1: \mypar{Algorithm} ------------------------------------------
    for m in MYPAR_ALGORITHM_RE.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': 'Algorithm',
            'env_name': 'distilled',
            'rule_name': 'MYPAR_ALGORITHM_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 2: \mypar{<keyword-label>} -------------------------------------
    for m in MYPAR_GENERAL_RE.finditer(text):
        par_label = m.group(1).strip()
        if par_label.lower() == 'algorithm':
            continue
        if not _ALGO_MYPAR_KEYWORDS_RE.search(par_label):
            continue
        body = m.group(2).strip()
        if not body:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': par_label,
            'env_name': 'distilled',
            'rule_name': 'MYPAR_GENERAL_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 3: Ordinal method paragraphs -----------------------------------
    for m in ORDINAL_METHOD_RE.finditer(text):
        body = m.group(1).strip()
        if not body:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'ORDINAL_METHOD_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 4: Remark/note environments with procedural body ---------------
    for m in REMARK_ENV_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        opt = m.group('opt')
        clean = _clean_latex(body)
        if not _is_procedural_body(clean, min_hits=3):
            continue
        start = m.start()
        end = m.end()
        results.append({
            'raw_latex': body.strip(),
            'clean_text': clean,
            'name': opt.strip() if opt else None,
            'env_name': 'distilled',
            'rule_name': 'REMARK_ENV_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 5: Bold-headed procedural paragraphs ---------------------------
#     for m in BOLD_PARA_ALGORITHM_RE.finditer(text):
#         title = m.group(1) or m.group(2) or ''
#         body = m.group('body').strip()
#         if not body:
#             continue
#         if len(_BOLD_PARA_STEP_RE.findall(body)) < 2:
#             continue
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         results.append({
#             'raw_latex': body,
#             'clean_text': _clean_latex(body),
#             'name': title.strip() if title.strip() else None,
#             'env_name': 'distilled',
#             'rule_name': 'BOLD_PARA_ALGORITHM_RE',
#             'structure_type': 'algorithm',
#             '_start': start,
#             '_end': end,
#         })

    pass  # PRUNED: body commented out
    # -- Rule 6: Free-standing procedural paragraphs after theorem-like envs -
    for m in PROCEDURAL_PARA_RE.finditer(text):
        body = m.group('body').strip()
        if not body:
            continue
        if len(_STEP_KW_RE.findall(body)) < 3:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body,
            'clean_text': _clean_latex(body),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'PROCEDURAL_PARA_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 7: algorithm2e and related environments ------------------------
    for m in ALGORITHM2E_ENV_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        opt = m.group('opt')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Extract \caption{...} as name if present
        name = None
        caption_m = re.search(r'\\caption\s*\{([^}]*)\}', body)
        if caption_m:
            name = caption_m.group(1).strip() or None
        if name is None and opt:
            name = opt.strip() or None
        results.append({
            'raw_latex': body.strip(),
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'ALGORITHM2E_ENV_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 8 (NUMBERED_STEP_PROSE_RE): numbered-step prose sequences ------
    for m in NUMBERED_STEP_PROSE_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        body = body.strip()
        if not _numbered_step_is_algorithmic(body, min_verbs=2):
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Build a richer raw_latex that includes the lead-in sentence if present
        lead = m.group('lead') or ''
        raw = (lead + body).strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': None,
            'env_name': 'distilled',
            'rule_name': 'NUMBERED_STEP_PROSE_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 10: pseudocode environments ------------------------------------
    for m in PSEUDOCODE_ENV_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Name: prefer the {Name} braced argument, fall back to [style]
        name = None
        name_grp = m.group('name')
        if name_grp:
            name = name_grp.strip() or None
        if name is None:
            style_grp = m.group('style')
            if style_grp:
                name = style_grp.strip() or None
        results.append({
            'raw_latex': body.strip(),
            'clean_text': _clean_latex(body),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'PSEUDOCODE_ENV_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 11: \item \textbf{<label>} entries inside list environments ----
    for env_m in BOLDITEM_LIST_ENV_RE.finditer(text):
        env_start = env_m.start()
        env_end = env_m.end()
        if _inside_excluded_env(text, env_start, env_end):
            continue
        # Check that the surrounding context suggests an algorithmic setting
        if not _list_env_in_algo_context(text, env_start, min_hits=2):
            continue
        env_body = env_m.group('body')
        for item_m in BOLDITEM_ITEM_RE.finditer(env_body):
            label = item_m.group('label').strip()
            item_body = item_m.group('body').strip()
            if not item_body or len(item_body) < 20:
                continue
            # Compute absolute positions within the full text
            item_start = env_start + item_m.start()
            item_end = env_start + item_m.end()
            raw = r'\textbf{' + label + '}' + item_m.group('body')
            raw = raw.strip()
            results.append({
                'raw_latex': raw,
                'clean_text': _clean_latex(raw),
                'name': label,
                'env_name': 'distilled',
                'rule_name': 'BOLDITEM_LIST_ENV_RE',
                'structure_type': 'algorithm',
                '_start': item_start,
                '_end': item_end,
            })

    # -- Rule 12: \section/\subsection with "algorithm" in title -------------
    for m in SECTION_ALGORITHM_TITLE_RE.finditer(text):
        section_title = m.group(2).strip()
        body = m.group('body')
        if not body:
            continue
        body_stripped = body.strip()
        if len(body_stripped) < _SECTION_ALGO_MIN_BODY:
            continue
        if len(_NUMBERED_STEP_ACTION_VERB_RE.findall(body_stripped)) < _SECTION_ALGO_MIN_VERBS:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        results.append({
            'raw_latex': body_stripped,
            'clean_text': _clean_latex(body_stripped),
            'name': section_title,
            'env_name': 'distilled',
            'rule_name': 'SECTION_ALGORITHM_TITLE_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 13: Bold heading with "algorithm" followed by enumerate block --
    for m in BOLD_HEADING_ENUMERATE_RE.finditer(text):
        name = m.group('name1') or m.group('name2') or ''
        name = name.strip()
        body = m.group('body')
        if not body:
            continue
        if _enumerate_item_count(body) < _BOLD_ENUM_MIN_ITEMS:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        raw = m.group(0).strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name if name else None,
            'env_name': 'distilled',
            'rule_name': 'BOLD_HEADING_ENUMERATE_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 14: \section/\subsection/\subsubsection with procedural/
    #             constructive keyword in title (generalised from 1412.0216v2)
#     for m in SECTION_PROCEDURAL_TITLE_RE.finditer(text):
#         section_title = m.group('title').strip()
#         # Skip if title also matches "algorithm" — Rule 12 covers that
#         if re.search(r'\balgorithm\b', section_title, flags=re.IGNORECASE):
#             continue
#         # Must contain a procedural keyword in the title
#         if not _SECTION_PROCEDURAL_TITLE_KW_RE.search(section_title):
#             continue
#         body = m.group('body')
#         if not body:
#             continue
#         body_stripped = body.strip()
#         if len(body_stripped) < _SECTION_PROC_MIN_BODY:
#             continue
#         if len(_NUMBERED_STEP_ACTION_VERB_RE.findall(body_stripped)) < _SECTION_PROC_MIN_VERBS:
#             continue
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         results.append({
#             'raw_latex': body_stripped,
#             'clean_text': _clean_latex(body_stripped),
#             'name': section_title,
#             'env_name': 'distilled',
#             'rule_name': 'SECTION_PROCEDURAL_TITLE_RE',
#             'structure_type': 'algorithm',
#             '_start': start,
#             '_end': end,
#         })

    pass  # PRUNED: body commented out

    # -- Rule 15a: {\bfseries <label>} / {\bf <label>} / \textbf{<label>}
    #              paragraphs where label is algorithm-indicative -------------
#     for m in BFSERIES_ALGO_PARA_RE.finditer(text):
#         label = (m.group('label1') or m.group('label2') or m.group('label3') or '').strip()
#         if not label:
#             continue
#         if not _BFSERIES_ALGO_LABEL_KW_RE.search(label):
#             continue
#         body = m.group('body')
#         if not body:
#             continue
#         body_stripped = body.strip()
#         if len(body_stripped) < _BFSERIES_MIN_BODY:
#             continue
#         if len(_NUMBERED_STEP_ACTION_VERB_RE.findall(body_stripped)) < _BFSERIES_MIN_VERBS:
#             continue
#         start = m.start()
#         end = m.end()
#         if _inside_excluded_env(text, start, end):
#             continue
#         raw = m.group(0).strip()
#         results.append({
#             'raw_latex': raw,
#             'clean_text': _clean_latex(raw),
#             'name': label,
#             'env_name': 'distilled',
#             'rule_name': 'BFSERIES_ALGO_PARA_RE',
#             'structure_type': 'algorithm',
#             '_start': start,
#             '_end': end,
#         })

    pass  # PRUNED: body commented out

    # -- Rule 16: \begin{mdframed}...\end{mdframed} and similar box envs -----
    for m in MDFRAMED_ENV_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        if not _mdframed_is_algorithmic(body):
            continue
        # Attempt to extract a name from \textbf{...} label at the start,
        # or from a \caption{...} if present.
        name = None
        caption_m = re.search(r'\\caption\s*\{([^}]*)\}', body)
        if caption_m:
            name = caption_m.group(1).strip() or None
        if name is None:
            # Look for a leading bold label (e.g. \textbf{Protocol X})
            bold_m = re.search(
                r'\\textbf\s*\{([^}]{3,60})\}',
                body[:300]
            )
            if bold_m:
                candidate = bold_m.group(1).strip()
                # Only use it as a name if it looks like a title (not a field label)
                if not re.match(
                    r'^(?:Input|Output|Inputs?|Outputs?|Input:|Output:)$',
                    candidate,
                    flags=re.IGNORECASE
                ):
                    name = candidate
        raw = body.strip()
        results.append({
            'raw_latex': raw,
            'clean_text': _clean_latex(raw),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'MDFRAMED_ENV_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Rule 17: \begin{construct}...\end{construct} and construction variants
    for m in CONSTRUCT_ENV_RE.finditer(text):
        body = m.group('body')
        if not body:
            continue
        body_stripped = body.strip()
        if len(body_stripped) < _CONSTRUCT_MIN_BODY:
            continue
        opt = m.group('opt')
        start = m.start()
        end = m.end()
        if _inside_excluded_env(text, start, end):
            continue
        # Attempt to extract a name from \caption{...} inside the body,
        # or fall back to the optional argument.
        name = None
        caption_m = re.search(r'\\caption\s*\{([^}]*)\}', body)
        if caption_m:
            name = caption_m.group(1).strip() or None
        if name is None and opt:
            name = opt.strip() or None
        results.append({
            'raw_latex': body_stripped,
            'clean_text': _clean_latex(body_stripped),
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'CONSTRUCT_ENV_RE',
            'structure_type': 'algorithm',
            '_start': start,
            '_end': end,
        })

    # -- Deduplicate overlapping spans ---------------------------------------
    results = _deduplicate(results)

    # -- Strip internal keys -------------------------------------------------
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
