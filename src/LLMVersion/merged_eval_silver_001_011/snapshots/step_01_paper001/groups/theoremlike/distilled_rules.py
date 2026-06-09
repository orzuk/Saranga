import re
from typing import List, Dict

# ---------------------------------------------------------------------------
# Module-level compiled patterns
# ---------------------------------------------------------------------------

# Pattern: free-text paragraph followed by \ba...\ea display block
# Anchored on known problem-signaling keywords in the preamble
# PRUNED — FP on paper001 | also 6 TP — review before uncommenting
# FREETEXT_BA_PROBLEM = re.compile(
#     r'(?P<preamble>'
#         r'(?:[^\n]|\n(?!\n)){20,800}?'           # up to 800 chars, no blank line
#         r'(?:'
#             r'mincut|cut|partition|objective\s+function|criterion|'
#             r'RatioCut|Ratiocut|\\Ratiocut|Ncut|\\Ncut|MinmaxCut|\\MinmaxCut|'
#             r'minimize|maximiz|balancing|balanced|clusters?'
#         r')'
#         r'(?:[^\n]|\n(?!\n)){0,400}?'            # trailing context before \ba
#     r')'
#     r'[^\n]{0,80}?'                              # possible short connector
#     r'\\ba\s*'
#     r'(?P<body>.*?)'
#     r'\\ea',
#     re.DOTALL | re.IGNORECASE,
# )

# Excluded environments — matches we must discard if inside these
_EXCLUDED_ENV_RE = re.compile(
    r'\\begin\{(proof|example|remark|rem|note|exam|ex|Exercise|exercise)\}',
    re.IGNORECASE,
)

_EXCLUDED_ENV_CLOSE_RE = re.compile(
    r'\\end\{(proof|example|remark|rem|note|exam|ex|Exercise|exercise)\}',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_latex(text: str) -> str:
    """Strip common LaTeX commands to produce readable plain text."""
    # Remove comments
    t = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}, \ref{...}, \cite... etc.
    t = re.sub(r'\\(label|ref|eqref|citeA|citeNP|citealt|citep|citet|cite)\{[^}]*\}', '', t)
    # Remove display math environments \ba...\ea  \[ \]
    t = re.sub(r'\\ba\b', '', t)
    t = re.sub(r'\\ea\b', '', t)
    t = re.sub(r'\\\[', '', t)
    t = re.sub(r'\\\]', '', t)
    # Remove \begin{...} \end{...}
    t = re.sub(r'\\(?:begin|end)\{[^}]*\}', '', t)
    # Inline math: keep content, remove $
    t = re.sub(r'\$\$?(.*?)\$\$?', lambda m: ' ' + m.group(1) + ' ', t, flags=re.DOTALL)
    # Remove remaining LaTeX commands with arguments
    t = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', t)
    # Remove remaining LaTeX commands (no arg)
    t = re.sub(r'\\[a-zA-Z]+\*?', ' ', t)
    # Remove leftover braces
    t = re.sub(r'[{}]', '', t)
    # Collapse whitespace
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Return True if the span [start, end) is inside a proof/example/remark env."""
    # Look for the nearest unclosed excluded \begin before `start`
    prefix = text[:start]
    opens = list(_EXCLUDED_ENV_RE.finditer(prefix))
    closes = list(_EXCLUDED_ENV_CLOSE_RE.finditer(prefix))
    depth = len(opens) - len(closes)
    return depth > 0


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _deduplicate(matches: List[dict]) -> List[dict]:
    """Remove overlapping matches, keeping the one with longer raw_latex."""
    if not matches:
        return matches
    # Sort by start position
    matches.sort(key=lambda m: m['_start'])
    result = []
    last_end = -1
    for m in matches:
        s, e = m['_start'], m['_end']
        if s >= last_end:
            result.append(m)
            last_end = e
        else:
            # Overlap: keep longer
            if e - s > result[-1]['_end'] - result[-1]['_start']:
                result[-1] = m
                last_end = e
    return result


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_distilled_theoremlike(text: str) -> List[dict]:
    """
    Extract theorem-like structures NOT caught by the base _extract_envs method.

    Targets free-text paragraph + \\ba...\\ea display math blocks that
    describe graph-cut / optimization problems in plain prose (no
    \\begin{problem}...\\end{problem} environment).
    """
    results: List[dict] = []

    # --- Rule: FREETEXT_BA_PROBLEM ---
#     for m in FREETEXT_BA_PROBLEM.finditer(text):
#         start = m.start()
#         end = m.end()

#         # Skip if inside an excluded environment
#         if _inside_excluded_env(text, start, end):
#             continue

#         preamble = m.group('preamble') or ''
#         body = m.group('body') or ''
#         raw = (preamble.strip() + '\n\\ba\n' + body.strip() + '\n\\ea').strip()
#         clean = _clean_latex(raw)

#         # Determine structure_type from content
#         structure_type = 'problem'  # default for this rule

#         results.append({
#             'raw_latex': raw,
#             'clean_text': clean,
#             'name': None,
#             'env_name': 'distilled',
#             'rule_name': 'FREETEXT_BA_PROBLEM',
#             'structure_type': structure_type,
#             '_start': start,
#             '_end': end,
#         })

    # Deduplicate overlapping matches
    results = _deduplicate(results)

    # Remove internal bookkeeping keys before returning
    for r in results:
        r.pop('_start', None)
        r.pop('_end', None)

    return results
