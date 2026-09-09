try:
    from latex_clean import clean_latex_to_text as _clean_latex
except Exception:
    _clean_latex = lambda s: s

import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is nested inside a proof, example,
    or remark environment (we do not want to tag those as additional proofs)."""
    excluded = re.compile(
        r'\\begin\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
        re.IGNORECASE
    )
    end_env = re.compile(
        r'\\end\{(proof|Proof|example|Example|remark|Remark|rem|note)\}',
        re.IGNORECASE
    )
    depth = 0
    pos = 0
    while pos < start:
        bm = excluded.search(text, pos, start)
        em = end_env.search(text, pos, start)
        if bm and (not em or bm.start() < em.start()):
            depth += 1
            pos = bm.end()
        elif em:
            depth = max(0, depth - 1)
            pos = em.end()
        else:
            break
    return depth > 0


# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Interstitial prose blocks between \end{...} and \begin{...}
# PRUNED — FP on 1512.05406v1 | also 4 TP — review before uncommenting
# INTERSTITIAL_PROOF_PATTERN = re.compile(
#     r'\\end\{[^}]+\}'
#     r'[ \t]*\n?'
#     r'((?:(?!\\begin\{|\\end\{|\\section|\\subsection|\\subsubsection|\\chapter|\\paragraph).)+?)'
#     r'(?=\\begin\{)',
#     re.DOTALL
# )

# \proof ... \proofend (plain TeX / AMS shorthand, no \begin/\end wrapper)
# Also handles \proof ... \endproof as an alternative terminator.
PROOF_PROOFEND_PATTERN = re.compile(
    r'\\proof\b'
    r'(?:\[(?P<opt>[^\]]*)\])?'
    r'\s*'
    r'(?P<body>.*?)'
    r'(?:\\proofend\b|\\endproof\b)',
    re.DOTALL
)

# \subsection or \subsubsection whose title begins with 'Proof' (case-insensitive),
# body runs until next sectioning command or end of document.
SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:subsection|subsubsection)\*?\s*\{\s*[Pp]roof[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*'
    r'(.*?)'
    r'(?=\\(?:section|subsection|subsubsection)\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# \section, \subsection, or \subsubsection whose title contains 'Proof'
# (case-sensitive, to catch "Proof of Theorem X" subsections).
# Body runs until next sectioning command or end of document.
SUBSECTION_PROOF_OF_PATTERN = re.compile(
    r'\\(?:section|subsection|subsubsection)\*?\s*\{(?:[^}]*\bProof\b[^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*'
    r'(?P<body>.*?)'
    r'(?=\\(?:section|subsection|subsubsection)\b|\\end\{document\}|\Z)',
    re.DOTALL
)

# Subsection with proof-related keywords in title (broader than SUBSECTION_PROOF_OF_PATTERN).
# Catches titles like 'Verification of ...', 'We prove ...', 'Sketch of ...' etc.
# Body runs until next sectioning command or end of document.
SUBSECTION_PROOF_KEYWORD_PATTERN = re.compile(
    r'\\(?:subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*'
    r'(?P<body>.*?)'
    r'(?=\\(?:section|subsection|subsubsection)\b|\\end\{document\}|\Z)',
    re.DOTALL
)

_PROOF_TITLE_KEYWORDS = re.compile(
    r'\b(?:proof|verification|verif|sketch)\b',
    re.IGNORECASE
)

# \paragraph{...} blocks — named paragraphs acting as implicit proof/derivation blocks.
# Extracts body until next \paragraph, any \(sub)section, \end{document}, or end of string.
# PRUNED — FP on 1502.03482v2, 1711.00418v8, 1803.04122v2 | also 7 TP — review before uncommenting
# PARAGRAPH_BODY_PATTERN = re.compile(
#     r'\\paragraph\*?\s*\{(?P<title>[^}]*)\}'
#     r'\s*'
#     r'(?P<body>.*?)'
#     r'(?='
#     r'\\paragraph\*?\s*\{'
#     r'|\\(?:sub)*section\*?\s*[\[{]'
#     r'|\\end\{document\}'
#     r'|\Z'
#     r')',
#     re.DOTALL
# )

# Paragraph-level proof openers: sentences beginning with phrases like
# 'Next we prove', 'We first show', 'We now prove', etc., running until
# a \qed, the next such opener, a sectioning command, or end of document.
# PRUNED — FP on 1111.3171v5, 1210.4765v1, 1404.7475v3 +6 more | also 13 TP — review before uncommenting
# PARAGRAPH_PROOF_PATTERN = re.compile(
#     r'(?:(?:^|\n)[ \t]*)'
#     r'(?:Next\s+we\s+prove|Now\s+we\s+prove|'
#     r'We\s+(?:first|next|now|also)?\s*prove|'
#     r'We\s+(?:first|next|now)?\s*show|'
#     r'Finally(?:,)?\s+we\s+prove|'
#     r'It\s+remains\s+to\s+prove)'
#     r'[^\n]*\n'
#     r'(.*?)'
#     r'(?='
#     r'(?:(?:^|\n)[ \t]*)(?:Next\s+we\s+prove|Now\s+we\s+prove|'
#     r'We\s+(?:first|next|now|also)?\s*prove|'
#     r'We\s+(?:first|next|now)?\s*show|'
#     r'Finally(?:,)?\s+we\s+prove|'
#     r'It\s+remains\s+to\s+prove)'
#     r'|\\qed\b|\\subsection\b|\\section(?!\w)|\\end\{document\}|\Z'
#     r')',
#     re.DOTALL | re.MULTILINE
# )

# Prose blocks that end with a canonical proof-concluding phrase.
# Anchored to paragraph boundaries; runs until the concluding phrase.
CONCLUDING_PROOF_PATTERN = re.compile(
    r'(?:(?<=\n\n)|(?<=\n)|(?:^))'
    r'((?:[^\n]|\n(?!\n))*?'
    r'(?:'
    r'concludes?\s+the\s+(?:argument|proof)'
    r'|completes?\s+the\s+proof'
    r'|this\s+(?:proves?|completes?|concludes?)\b'
    r'|which\s+proves?\b'
    r'|ends?\s+the\s+proof'
    r'|finishing\s+the\s+proof'
    r'|\\(?:qed|QED)\b'
    r')'
    r'[^\n]*)',
    re.DOTALL
)

# Prose proof blocks introduced by summarising / computation-sketch phrases
# at the start of a paragraph. Body runs until a sectioning command, spacing
# macro, or end of document.
# PRUNED — FP on 1502.03482v2, 1601.01819v1 | also 1 TP — review before uncommenting
# PROOF_INTRO_PATTERN = re.compile(
#     r'(?:(?:^|\n)[ \t]*)'
#     r'(?:'
#     r'We\s+(?:summaris[e]|sketch|outline|prove|show|compute|demonstrat\w*|deriv\w*|establish)\b'
#     r'|The\s+(?:proof|argument|computation|derivation)\s+(?:goes|proceeds|follows|is\s+as\s+follows|runs\s+as\s+follows)\b'
#     r'|We\s+present\s+the\s+(?:proof|computation|derivation)\b'
#     r')'
#     r'(?:(?!\\(?:section|subsection|subsubsection|paragraph|chapter)\b).){100,}?'
#     r'(?=\\(?:section|subsection|subsubsection|paragraph|chapter|bigskip|medskip)\b|\\end\{document\}|\Z)',
#     re.DOTALL | re.IGNORECASE
# )

# Inline proofs introduced by {\it Proof.} or \textit{Proof.} or {\em Proof.}
# (common plain-TeX / older LaTeX idiom for proofs without a formal environment).
# Body runs until the next theorem-like environment, sectioning command, or
# end of document.
IT_PROOF_PATTERN = re.compile(
    r'(?:'
    r'\{\\(?:it|em)\s+Proof\.?\}'          # {\it Proof.} or {\em Proof.}
    r'|\\textit\{Proof\.?\}'               # \textit{Proof.}
    r'|\\emph\{Proof\.?\}'                 # \emph{Proof.}
    r')'
    r'[ \t]*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\begin\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
    r'|definition|defn|example|remark|claim|assumption|conjecture'
    r'|problem|algorithm|figure|table)\}'
    r'|\\end\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
    r'|definition|defn|example|remark|claim|assumption|conjecture'
    r'|problem|algorithm|document)\}'
    r'|\{\\it\s+Proof\.?\}'
    r'|\\textit\{Proof\.?\}'
    r'|\\emph\{Proof\.?\}'
    r'|\\section\b|\\subsection\b|\\subsubsection\b'
    r'|\Z'
    r')',
    re.DOTALL
)

# Prose proof blocks introduced by \textbf{Proof...}, \textit{Proof...}, or
# \textsl{Proof...} at the start of a paragraph / after spacing macros.
# Body runs until the next \begin{...}, another such proof marker, a
# sectioning command, or end of document.
TEXTBF_PROOF_PATTERN = re.compile(
    r'(?:^|\\par\b|\\medskip\b|\\bigskip\b|\\noindent\b)\s*'
    r'\\(?:textbf|textit|textsl)\{Proof[^}]*\}'
    r'\s*\.?\s*'
    r'(?:\\newline)?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\begin\{'
    r'|\\par\s*\\noindent\s*\\(?:textbf|textit|emph)\{'
    r'|\\section\b|\\subsection\b|\\subsubsection\b'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL | re.MULTILINE
)

# Inline proofs introduced by \textbf{Proof} or \textit{Proof} at the start
# of a paragraph (after \par or \noindent), not already covered by TEXTBF_PROOF_PATTERN.
# This generalizes the \emph{Proof} inline handler from the base extractor.
INLINE_TEXTBF_TEXTIT_PROOF_PATTERN = re.compile(
    r'(?:^|\\par)\s*(?:\\noindent\s*)?'
    r'\\(?:textbf|textit)\{Proof\}'
    r'\s*\.?\s*(?:\\newline)?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\begin\{'
    r'|\\par\s*(?:\\noindent\s*)?\\(?:textbf|textit)\{'
    r'|\\section\b|\\subsection\b|\\subsubsection\b'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL | re.MULTILINE
)

# Prose proof blocks introduced by summarising / computation-sketch phrases
# at the start of a paragraph. Body runs until a sectioning command, spacing
# macro, or end of document.
INTRO_CONCLUDING_PROOF_PATTERN = re.compile(
    r'(?:(?:^|\n\n)[ \t]*)'
    r'(?:'
    r'[Tt]his\s+is\s+established\s+by\s+the\s+following'
    r'|[Tt]he\s+(?:proof|argument|reasoning)(?:\s+of\s+[^.]{0,80})?\s+(?:is|follows|goes|proceeds)'
    r'|[Ww]e\s+(?:now\s+)?prove(?:\s+this)?(?:\s+as\s+follows)?'
    r'|[Pp]roceeding\s+by\s+(?:contradiction|induction|construction)'
    r'|[Bb]y\s+(?:the\s+following\s+(?:reasoning|argument)|contradiction|reductio\s+ad\s+absurdum|induction)'
    r'|[Ww]e\s+(?:argue|reason|show(?:\s+that)?)\s+as\s+follows'
    r'|[Ii]t\s+follows\s+(?:immediately\s+)?(?:that|from)'
    r')'
    r'.{30,4000}?'
    r'(?:'
    r'reductio\s+ad\s+absurdum'
    r'|[Tt]his\s+completes?\s+the\s+proof'
    r'|[Tt]he\s+proof\s+is\s+(?:complete|now\s+complete)'
    r'|[Ww]hich\s+is\s+a\s+contradiction'
    r'|[Tt]his\s+is\s+a\s+contradiction'
    r'|[Aa]\s+contradiction'
    r'|\\qed\b'
    r'|\\square\b'
    r'|[Qq]\s*\.\s*[Ee]\s*\.\s*[Dd]\s*\.'
    r')'
    r'[^.]*\.'
    r'(?=\s*(?:\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\end\{document\}|\Z|\n\n))',
    re.DOTALL
)

# Inline proof introduced by 'To (check|show|see|verify|prove) that' or
# 'It (suffices|remains) to (show|prove|check|verify)' in running text.
# Body runs until the next sectioning command, theorem-like environment, or
# end of document.
# PRUNED — FP on 1111.3171v5, 1412.0216v2 | also 1 TP — review before uncommenting
# INLINE_CLAIM_PROOF_PATTERN = re.compile(
#     r'(?:^|(?<=\n))'
#     r'(?:To\s+(?:check|show|see|verify|prove)\s+that'
#     r'|It\s+(?:suffices|remains)\s+to\s+(?:show|prove|check|verify))'
#     r'(?P<body>.+?)'
#     r'(?='
#     r'\\(?:sub)*section\b'
#     r'|\\section(?!\w)'
#     r'|\\begin\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
#     r'|definition|defn|example|remark|claim|assumption|conjecture'
#     r'|problem|algorithm|figure|table|proof)\}'
#     r'|\\end\{document\}'
#     r'|\Z'
#     r')',
#     re.DOTALL | re.IGNORECASE
# )

# Inline proof introduced by 'Let us show/prove that', 'We (now) show/prove that',
# 'We show/prove that' in running text.
# Body runs until next sectioning command, theorem-like environment, or end of doc.
# PRUNED — FP on 1210.4765v1, 1404.7475v3, 1502.03482v2 +4 more | also 2 TP — review before uncommenting
# LET_US_SHOW_PATTERN = re.compile(
#     r'(?:^|\n)[ \t]*'
#     r'(?:Let\s+us\s+(?:show|prove|check|verify)'
#     r'|We\s+(?:now\s+)?(?:show|prove|check|verify))'
#     r'\s+that\b'
#     r'(?P<body>.+?)'
#     r'(?='
#     r'\\(?:sub)*section\b'
#     r'|\\section(?!\w)'
#     r'|\\begin\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
#     r'|definition|defn|example|remark|claim|assumption|conjecture'
#     r'|problem|algorithm|figure|table|proof)\}'
#     r'|\\end\{document\}'
#     r'|\Z'
#     r')',
#     re.DOTALL | re.IGNORECASE
# )

# Inline proof introduced by 'We can now prove/show', 'We are now ready to prove/show',
# 'We now prove/show' (without 'that'), appearing after \end{proof} or section headings.
# PRUNED — FP on 1508.06062v1 | also 1 TP — review before uncommenting
# WE_CAN_NOW_PROVE_PATTERN = re.compile(
#     r'(?:^|\n)[ \t]*'
#     r'(?:We\s+(?:are\s+now\s+ready\s+to\s+(?:prove|show)'
#     r'|can\s+now\s+(?:prove|show|check|verify)'
#     r'|now\s+(?:prove|show)))'
#     r'(?:\s+that\b)?'
#     r'(?P<body>.+?)'
#     r'(?='
#     r'\\(?:sub)*section\b'
#     r'|\\section(?!\w)'
#     r'|\\begin\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
#     r'|definition|defn|example|remark|claim|assumption|conjecture'
#     r'|problem|algorithm|figure|table|proof)\}'
#     r'|\\end\{document\}'
#     r'|\Z'
#     r')',
#     re.DOTALL | re.IGNORECASE
# )

# Proof-by-contradiction opener: 'By contradiction, suppose that',
# 'Suppose for contradiction', 'Assume for contradiction', etc.
CONTRADICTION_PROOF_PATTERN = re.compile(
    r'(?:^|\n)[ \t]*'
    r'(?:By\s+contradiction[,.]?\s+suppose\s+that'
    r'|Suppose\s+(?:for\s+(?:a\s+)?contradiction|by\s+way\s+of\s+contradiction)'
    r'|Assume\s+(?:for\s+(?:a\s+)?contradiction|by\s+way\s+of\s+contradiction)'
    r'|For\s+(?:a\s+)?contradiction[,.]?\s+suppose'
    r'|For\s+the\s+sake\s+of\s+contradiction)'
    r'(?P<body>.+?)'
    r'(?='
    r'\\(?:sub)*section\b'
    r'|\\section(?!\w)'
    r'|\\begin\{(?:theorem|lemma|proposition|corollary|cor|thm|lem|prop'
    r'|definition|defn|example|remark|claim|assumption|conjecture'
    r'|problem|algorithm|figure|table|proof)\}'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL | re.IGNORECASE
)

# \noindent followed by an optional parenthesized item label and \emph{...proof...}
# as a paragraph-level proof-step heading. Body runs until the next \begin{...},
# another such heading, a sectioning command, or end of document.
# Catches patterns like: \noindent (iv) \emph{Conclusion of the proof ...}
NOINDENT_EMPH_PROOF_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:\([^)]{1,15}\)\s*)?'           # optional item label like (i), (iv), (a), (Step 1)
    r'\\emph\{[^}]*[Pp]roof[^}]*\}'     # \emph{...proof...} heading
    r'[^\n]*\n?'                         # rest of heading line
    r'(?P<body>.*?)'
    r'(?='
    r'\\begin\{'
    r'|\\noindent\s*(?:\([^)]{1,15}\)\s*)?\\emph\{[^}]*[Pp]roof'
    r'|\\(?:section|subsection|subsubsection)\b'
    r'|\\end\{document\}'
    r'|\Z'
    r')',
    re.DOTALL
)

# \noindent followed by a proof label in {\em ...} or \textit{...} or \emph{...}
# with optional 'of <something>' text, then body ending at \qed, \blacksquare,
# or a structural boundary.
# Catches patterns like: \noindent{\em Proof of Claim~\ref{...}}.\quad ...body... \qed
NOINDENT_EM_PROOF_PATTERN = re.compile(
    r'\\noindent\s*'
    r'(?:'
    r'\{\\(?:it|em)\s+[Pp]roof[^}]*\}'   # {\em Proof...} or {\it Proof...}
    r'|\\textit\{[Pp]roof[^}]*\}'         # \textit{Proof...}
    r'|\\emph\{[Pp]roof[^}]*\}'           # \emph{Proof...}
    r')'
    r'[.\s]*(?:\\quad)?\s*'
    r'(?P<body>.*?)'
    r'(?='
    r'\\qed\b'
    r'|\\blacksquare\b'
    r'|\\begin\{'
    r'|\\noindent\s*(?:\{\\(?:it|em)\s+[Pp]roof|\\textit\{[Pp]roof|\\emph\{[Pp]roof)'
    r'|\\(?:section|subsection|subsubsection)\b'
    r'|\\end\{document\}'
    r'|\\bigskip\b'
    r'|\\medskip\b'
    r'|\Z'
    r')',
    re.DOTALL
)

# Inline proofs introduced by proof-keywords like 'In fact,', 'Indeed,', 'To see this,'
# These have NO structural LaTeX delimiter; we anchor on leading keywords only.
# Only triggered when the block ends with a clear proof-concluding signal to reduce FPs.
INLINE_KEYWORD_PROOF_PATTERN = re.compile(
    r'(?:^|(?<=\n\n))[ \t]*'
    r'(?:In\s+fact|Indeed|To\s+see\s+this|Observe\s+that)'
    r'[,.][ \t]*'
    r'(?P<body>(?:(?!\\begin\{|\\end\{|\\section\b|\\subsection\b|\\subsubsection\b).)+?)'
    r'(?:'
    r'a\s+contradiction\b'
    r'|[Tt]his\s+completes?\s+the\s+proof'
    r'|[Ww]hich\s+(?:proves?|shows?|is\s+a\s+contradiction)\b'
    r'|\\qed\b'
    r'|\\square\b'
    r'|[Qq]\s*\.\s*[Ee]\s*\.\s*[Dd]\s*\.'
    r')'
    r'[^.]*\.',
    re.DOTALL | re.MULTILINE
)

# Inline proofs introduced by connective words (Indeed, Conversely, etc.)
# immediately after a display math block ($$...$$, \[...\], or named math envs).
# Only triggered when followed by prose before the next major structural element.
# Body capped at 3000 chars to avoid swallowing whole sections.
# PRUNED — FP on 1003.1038v1, 1102.4533v1, 1103.5544v1 +8 more | also 7 TP — review before uncommenting
# AFTER_DISPLAY_CONNECTIVE_PROOF_PATTERN = re.compile(
#     r'(?:'
#     r'\\end\{(?:align|equation|gather|multline|flalign|alignat)\*?\}'
#     r'|\\\]'
#     r'|\$\$'
#     r')'
#     r'[ \t]*\n?[ \t]*'
#     r'(?P<body>'
#     r'(?:Indeed|Conversely|Therefore|Hence|Thus|It\s+follows|Note\s+that|Observe\s+that|This\s+follows)[,.]?\s+'
#     r'(?:(?!\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\end\{document\}).){20,2999}?'
#     r')'
#     r'(?=\\begin\{|\\section\b|\\subsection\b|\\subsubsection\b|\\end\{document\}|\n\n|\Z)',
#     re.DOTALL
# )

# No minimal regex addition is feasible for the 'We claim that...' prose-only pattern.
# The missed proof in 1610.03950v1 is pure prose with no LaTeX structural markers
# (no \begin{proof}, no \emph{Proof}, no \textbf{Proof.}, etc.).
# The closest general (but high false-positive) pattern would be:
#
# WE_CLAIM_PROOF_PATTERN = re.compile(
#     r'(?:We\s+claim|We\s+argue|We\s+assert|It\s+is\s+(?:easy\s+to\s+see|straightforward))[^.]*\.'
#     r'\s*((?:(?!\\section|\\subsection|\\paragraph|\\begin\{).)+?)'
#     r'(?=\\section|\\subsection|\\paragraph|\\begin\{|\Z)',
#     re.DOTALL
# )
#
# This is NOT recommended for production use due to excessive false positives.
# Structural extraction is not possible here without semantic/NLP methods.

# ---------------------------------------------------------------------------
# Post-theorem informal proof patterns (Rules 1, 2, 3)
# ---------------------------------------------------------------------------

# Theorem-like environment names used in post/pre-thm patterns.
_THM_ENV_NAMES = [
    "theorem", "Theorem", "thm",
    "lemma", "Lemma", "lem",
    "proposition", "Proposition", "prop",
    "corollary", "Corollary", "cor",
    "claim", "Claim",
    "conjecture", "Conjecture",
]
_THM_ENV_ALTS = "|".join(map(re.escape, _THM_ENV_NAMES))

# Text block appearing after \end{<thm-env>} and before the next \begin{<thm-env>}
# or \section/\subsection command or end of document.
# Captures informal proof paragraphs that follow theorem-like environments.
# The block may itself contain nested display math environments (gather*, align*, etc.).
POST_THM_PROOF_PATTERN = re.compile(
    r'\\end\{(?:' + _THM_ENV_ALTS + r')\}'
    r'\s*'
    r'(?P<body>(?:(?!\\begin\{(?:' + _THM_ENV_ALTS + r')\})'
    r'(?!\\(?:sub)*section\b)'
    r'(?!\\end\{document\})'
    r'.)+?)'
    r'(?=\\begin\{(?:' + _THM_ENV_ALTS + r')\}'
    r'|\\(?:sub)*section\b'
    r'|\\end\{document\}'
    r'|\Z)',
    re.DOTALL
)

# Text block appearing between \end{<any-env>} and \begin{<thm-env>}.
# Captures informal proof paragraphs / justifications that precede a theorem-like
# environment (e.g., motivation or sketch before a lemma).
# PRUNED — FP on 1103.5544v1, 1111.3171v5, 1207.0773v2 +7 more | also 1 TP — review before uncommenting
# PRE_THM_PROOF_PATTERN = re.compile(
#     r'\\end\{[^}]+\}'
#     r'\s*'
#     r'(?P<body>(?:(?!\\begin\{[^}]+\})'
#     r'(?!\\(?:sub)*section\b)'
#     r'(?!\\end\{document\})'
#     r'.){40,}?)'
#     r'\s*(?=\\begin\{(?:' + _THM_ENV_ALTS + r')\})',
#     re.DOTALL
# )


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_proof(text: str) -> List[Dict]:
    results: List[Dict] = []
    seen_spans = []  # list of (start, end) to deduplicate

    def _overlaps(start: int, end: int) -> bool:
        for s, e in seen_spans:
            if start < e and end > s:
                return True
        return False

    # --- Rule: PRUNED interstitial proof blocks ---
    # pass  # PRUNED: body commented out

    # --- Rule: \proof ... \proofend / \endproof (plain TeX command-style proofs) ---
    for match in PROOF_PROOFEND_PATTERN.finditer(text):
        opt_name = match.group('opt')
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 10:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 2:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": opt_name.strip() if opt_name else None,
            "env_name": "distilled",
            "rule_name": "PROOF_PROOFEND_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: subsection/subsubsection whose title begins with 'Proof' ---
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        body = match.group(1).strip()
        span_start = match.start(1)
        span_end = match.end(1)

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: section/subsection/subsubsection whose title contains 'Proof' ---
    for match in SUBSECTION_PROOF_OF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start('body')
        span_end = match.end('body')

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        # Extract the section title for use as name
        header_m = re.match(
            r'\\(?:section|subsection|subsubsection)\*?\s*\{([^}]*)\}',
            match.group(0)
        )
        opt_name = header_m.group(1).strip() if header_m else None

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": opt_name,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_OF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: subsection/subsubsection with proof-related keywords in title ---
    for match in SUBSECTION_PROOF_KEYWORD_PATTERN.finditer(text):
        title = match.group(1).strip()
        body = match.group('body').strip()
        span_start = match.start('body')
        span_end = match.end('body')

        if not body:
            continue
        if not _PROOF_TITLE_KEYWORDS.search(title):
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": title if title else None,
            "env_name": "distilled",
            "rule_name": "SUBSECTION_PROOF_KEYWORD_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: \paragraph{...} blocks as implicit proof/derivation blocks ---
#     for match in PARAGRAPH_BODY_PATTERN.finditer(text):
#         title = match.group('title').strip()
#         body = match.group('body').strip()
#         span_start = match.start('body')
#         span_end = match.end('body')

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         # Must be substantive
#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 30:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 5:
#             continue

#         # Must contain some prose, not just commands
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": title if title else None,
#             "env_name": "distilled",
#             "rule_name": "PARAGRAPH_BODY_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: paragraph-level proof openers ---
#     for match in PARAGRAPH_PROOF_PATTERN.finditer(text):
#         full_body = match.group(0).strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not full_body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         # Must be substantive
#         stripped = re.sub(r'%[^\n]*\n', '', full_body).strip()
#         if len(stripped) < 30:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 5:
#             continue

#         # Skip blocks that are purely LaTeX commands with no prose
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 10:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = full_body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "PARAGRAPH_PROOF_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: prose blocks ending with a canonical proof-concluding phrase ---
    for match in CONCLUDING_PROOF_PATTERN.finditer(text):
        body = match.group(0).strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 50:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 8:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 20:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "CONCLUDING_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: prose proof blocks introduced by summarising/computation-sketch phrases ---
#     for match in PROOF_INTRO_PATTERN.finditer(text):
#         body = match.group(0).strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 100:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 10:
#             continue

#         # Must contain some prose, not just commands
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 30:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "PROOF_INTRO_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out

    # --- Rule: inline proofs introduced by {\it Proof.}, \textit{Proof.}, \emph{Proof.} ---
    for match in IT_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 10:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "IT_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: inline proofs introduced by \textbf{Proof...}, \textit{Proof...}, \textsl{Proof...} ---
    for match in TEXTBF_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 10:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "TEXTBF_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: inline proofs introduced by \textbf{Proof} or \textit{Proof}
    #           at paragraph start (after \par or \noindent), generalising the
    #           base extractor's \emph{Proof} inline handler ---
    for match in INLINE_TEXTBF_TEXTIT_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 20:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 3:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 10:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "INLINE_TEXTBF_TEXTIT_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: prose proof blocks with proof-introducing phrase + concluding signal ---
    for match in INTRO_CONCLUDING_PROOF_PATTERN.finditer(text):
        body = match.group(0).strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 50:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 8:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 20:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "INTRO_CONCLUDING_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: inline proof introduced by 'To (check|show|see|verify|prove) that'
    #           or 'It (suffices|remains) to (show|prove|check|verify)' ---
#     for match in INLINE_CLAIM_PROOF_PATTERN.finditer(text):
#         body = match.group(0).strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 40:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 6:
#             continue

#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "INLINE_CLAIM_PROOF_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: inline proof introduced by 'Let us show/prove that',
    #           'We (now) show/prove that' ---
#     for match in LET_US_SHOW_PATTERN.finditer(text):
#         body = match.group(0).strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 40:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 6:
#             continue

#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "LET_US_SHOW_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: inline proof introduced by 'We can now prove/show',
    #           'We are now ready to prove/show', 'We now prove/show' ---
#     for match in WE_CAN_NOW_PROVE_PATTERN.finditer(text):
#         body = match.group(0).strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 40:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 6:
#             continue

#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "WE_CAN_NOW_PROVE_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: proof-by-contradiction opener ---
    for match in CONTRADICTION_PROOF_PATTERN.finditer(text):
        body = match.group(0).strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 40:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 6:
            continue

        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 15:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "CONTRADICTION_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: \noindent + optional item label + \emph{...proof...} heading ---
    for match in NOINDENT_EMPH_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 30:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 5:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 10:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "NOINDENT_EMPH_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: \noindent{\em Proof...} or \noindent\textit{Proof...} or
    #           \noindent\emph{Proof...} (with optional 'of <something>') ---
    for match in NOINDENT_EM_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 10:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 2:
            continue

        # Must contain some prose, not just commands
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 5:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "NOINDENT_EM_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: \noindent{\bf <proof/step/...>:} or \noindent\textbf{<proof/step/...>} ---
#     for match in NOINDENT_BF_PROOF_PATTERN.finditer(text):
#         body = match.group('body').strip()
#         span_start = match.start()
#         span_end = match.end()

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         # Must be substantive
#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 30:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 5:
#             continue

#         # Must contain some prose, not just commands
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 10:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "NOINDENT_BF_PROOF_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out

    # --- Rule: inline proofs introduced by 'In fact,', 'Indeed,', 'To see this,',
    #           'Observe that,' — only when block ends with a proof-concluding signal ---
    for match in INLINE_KEYWORD_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        full_match = match.group(0).strip()
        span_start = match.start()
        span_end = match.end()

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', full_match).strip()
        if len(stripped) < 40:
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 6:
            continue

        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 15:
            continue

        seen_spans.append((span_start, span_end))

        raw = full_match
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "INLINE_KEYWORD_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: connective proof paragraphs immediately after display math blocks ---
    # Catches paragraphs that begin with proof-indicative connectives (Indeed, Conversely,
    # Therefore, etc.) immediately after a display math environment or $$ block.
#     for match in AFTER_DISPLAY_CONNECTIVE_PROOF_PATTERN.finditer(text):
#         body = match.group('body').strip()
#         span_start = match.start('body')
#         span_end = match.end('body')

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         # Cap body length to avoid swallowing whole sections
#         if len(body) > 3000:
#             continue

#         # Must be substantive
#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 30:
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 5:
#             continue

#         # Must contain some prose, not just commands
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "AFTER_DISPLAY_CONNECTIVE_PROOF_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    # --- Rule: informal proof text appearing after \end{<thm-env>} and before
    #           the next \begin{<thm-env>} or sectioning command.
    #           Catches proof paragraphs (possibly with nested display math) that
    #           appear between two formal theorem-like environments. ---
    for match in POST_THM_PROOF_PATTERN.finditer(text):
        body = match.group('body').strip()
        span_start = match.start('body')
        span_end = match.end('body')

        if not body:
            continue
        if _overlaps(span_start, span_end):
            continue
        if _inside_excluded_env(text, span_start, span_end):
            continue

        # Must be substantive
        stripped = re.sub(r'%[^\n]*\n', '', body).strip()
        if len(stripped) < 30:
            continue
        if not re.search(r'[A-Za-z]', stripped):
            continue
        word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
        if len(word_matches) < 4:
            continue

        # Must contain some prose, not just commands or whitespace
        non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
        if len(non_command) < 15:
            continue

        seen_spans.append((span_start, span_end))

        raw = body
        clean = _clean_latex(raw)

        results.append({
            "raw_latex": raw,
            "clean_text": clean,
            "name": None,
            "env_name": "distilled",
            "rule_name": "POST_THM_PROOF_PATTERN",
            "structure_type": "proof",
        })

    # --- Rule: informal proof/justification text appearing between \end{<any-env>}
    #           and \begin{<thm-env>}. Catches motivation or sketch paragraphs that
    #           precede a theorem-like environment. ---
#     for match in PRE_THM_PROOF_PATTERN.finditer(text):
#         body = match.group('body').strip()
#         span_start = match.start('body')
#         span_end = match.end('body')

#         if not body:
#             continue
#         if _overlaps(span_start, span_end):
#             continue
#         if _inside_excluded_env(text, span_start, span_end):
#             continue

#         # Must be substantive
#         stripped = re.sub(r'%[^\n]*\n', '', body).strip()
#         if len(stripped) < 30:
#             continue
#         if not re.search(r'[A-Za-z]', stripped):
#             continue
#         word_matches = re.findall(r'[a-zA-Z]{3,}', stripped)
#         if len(word_matches) < 4:
#             continue

#         # Must contain some prose, not just commands or whitespace
#         non_command = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})*', '', stripped).strip()
#         if len(non_command) < 15:
#             continue

#         seen_spans.append((span_start, span_end))

#         raw = body
#         clean = _clean_latex(raw)

#         results.append({
#             "raw_latex": raw,
#             "clean_text": clean,
#             "name": None,
#             "env_name": "distilled",
#             "rule_name": "PRE_THM_PROOF_PATTERN",
#             "structure_type": "proof",
#         })

    pass  # PRUNED: body commented out
    return results
