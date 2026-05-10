import re
from typing import List
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from latex_clean import clean_latex_to_text as _clean_latex


# ============================================================
# Helper: check if a position is inside an excluded environment
# ============================================================

_EXCLUDED_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>'
    r'proof|Proof|theorem|Theorem|thm|theo|'
    r'lemma|Lemma|lem|'
    r'proposition|Proposition|prop|'
    r'corollary|Corollary|cor|'
    r'claim|Claim|'
    r'conjecture|Conjecture|'
    r'problem|Problem|'
    r'example|Example|remark|Remark|result|Result'
    r')\}'
    r'(?:\[[^\]]*\])?\s*'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)


def _build_excluded_spans(text: str):
    """Build exclusion spans from hardcoded + \\newtheorem-defined envs."""
    _newtheorem_pat = re.compile(
        r'\\newtheorem\s*\{([^}]+)\}(?:\[[^\]]+\])?\s*\{([^}]+)\}',
        re.DOTALL,
    )
    _theorem_like_keywords = {
        'theorem', 'lemma', 'proposition', 'corollary', 'claim',
        'conjecture', 'problem', 'remark', 'example',
    }
    extra_envs = set()
    for env_name, printed in _newtheorem_pat.findall(text):
        printed_clean = re.sub(r'[^a-z]', '', printed.lower())
        for kw in _theorem_like_keywords:
            if kw in printed_clean:
                extra_envs.add(env_name.strip())
                break

    spans = []
    for m in _EXCLUDED_ENV_PATTERN.finditer(text):
        spans.append((m.start(), m.end()))
    for env in extra_envs:
        pat = re.compile(
            r'\\begin\{' + re.escape(env) + r'\}'
            r'(?:\[[^\]]*\])?\s*'
            r'(?P<body>.*?)'
            r'\\end\{' + re.escape(env) + r'\}',
            re.DOTALL,
        )
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
    return spans


def _inside_excluded_env(text: str, start: int, end: int, _cache={}):
    """Return True if span [start, end) is fully inside a proof/theorem/etc."""
    text_id = id(text)
    if text_id not in _cache:
        _cache.clear()
        _cache[text_id] = _build_excluded_spans(text)
    for env_start, env_end in _cache[text_id]:
        if start >= env_start and end <= env_end:
            return True
    return False


# ============================================================
# Notation/convention environment pattern
# ============================================================

_NOTATION_ENV_PATTERN = re.compile(
    r'\\begin\{(?P<env>notation|Notation|convention|Convention|terminology|Terminology)\}'
    r'(?:\[(?P<title>[^\]]*)\])?\s*'
    r'(?P<body>.*?)'
    r'\\end\{(?P=env)\}',
    re.DOTALL
)

# ============================================================
# Inline patterns — only high-precision ones
# ============================================================

# P1: \textit{X} is a/an/the ... (term introduction via emphasis)
_P1_TEXTIT_IS = re.compile(
    r'(?P<full>'
    r'(?:\\textit|\\textbf|\\emph)\{(?P<name>[^}]{1,100})\}'
    r'(?:\s*\([^)]{1,80}\))?'
    r'(?:\s*~?\\cite\{[^}]*\})?'
    r'\s+is\s+(?:a|an|the)\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P2: "defined as follows:" + equation environment
_P2_DEFINED_AS_FOLLOWS = re.compile(
    r'(?P<full>'
    r'(?P<preamble>(?:(?!\n\n).){1,300}?)'
    r'\s+(?:can\s+be\s+|is\s+)?defined\s+as\s+follows\s*:\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\})'
    r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
    r')',
    re.DOTALL
)

# P3: "is defined by/as:" + equation environment
_P3_DEFINED_BY_EQ = re.compile(
    r'(?P<full>'
    r'(?P<preamble>(?:(?!\n\n).){1,300}?)'
    r'(?:,\s*which\s+is|\s+is|\s+are)\s+defined\s+'
    r'(?:(?:for|in)\s+(?:(?!\n\n).){1,150}?\s+)?'
    r'(?:by|as)\s*:?\s*'
    r'(?P<eq>\\begin\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\}'
    r'.*?'
    r'\\end\{(?:equation|align|gather|multline|displaymath|eqnarray)\*?\})'
    r'(?:\s*,?\s*where\s+(?:(?!\n\n).)*)?'
    r')',
    re.DOTALL
)

# P4: "A/An \emph{X} ... consists of / is a ..."
_P4_EMPH_DEF = re.compile(
    r'(?P<full>'
    r'(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*'
    r'(?:A|An|The)\s+'
    r'(?P<name>\\(?:emph|textit|textbf)\{[^}]+\}'
    r'(?:\s*\$[^$]*\$)?)'
    r'(?:(?!\n\n).){0,500}?'
    r'(?:consists?\s+of|is\s+(?:a\s+|an\s+|the\s+|obtained\s+|defined\s+)?)'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL | re.MULTILINE
)

# P5: "X is/are \emph{Y} if/when ..."
_P5_IS_EMPH_IF = re.compile(
    r'(?P<full>'
    r'(?:(?:^|(?<=\n)|(?<=\.\s)|(?<=\.\n))\s*)?'
    r'(?P<subject>(?:(?!\n\n).){1,200}?)'
    r'\s+(?:is|are)\s+'
    r'\\(?:emph|textit|textbf)\{(?P<name>[^}]{1,80}?)\}\s*'
    r'(?:if|when|whenever|provided)\s+'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)

# P6: "is called/said to be a \emph{Y}"
_P6_IS_CALLED = re.compile(
    r'(?P<full>'
    r'(?P<subject>(?:(?!\n\n).){1,200}?)'
    r'\s+is\s+(?:called|said\s+to\s+be)\s+'
    r'(?:a\s+|an\s+|the\s+)?'
    r'(?:'
    r'\{\\(?:em|it|bf)\s+(?P<name1>[^}]+)\}'
    r'|'
    r'\\(?:emph|textit|textbf)\{(?P<name2>[^}]+)\}'
    r')'
    r'(?:(?!\n\n).)*'
    r')',
    re.DOTALL
)


# ============================================================
# Main extraction function
# ============================================================

def extract_distilled_definition(text: str) -> List[dict]:
    """Extract definition structures from LaTeX source text.

    Simplified rule set: only high-precision patterns that require
    explicit definitional language (\emph, "defined as", "is called")
    or dedicated notation environments.
    """
    results = []
    used_spans = []

    def _overlaps(start: int, end: int) -> bool:
        for s, e in used_spans:
            overlap_start = max(start, s)
            overlap_end = min(end, e)
            if overlap_start < overlap_end:
                overlap_len = overlap_end - overlap_start
                span_len = end - start
                existing_len = e - s
                if overlap_len > 0.5 * span_len or overlap_len > 0.5 * existing_len:
                    return True
        return False

    def _add_result(match_obj, start_offset: int, name: str = None, raw: str = None):
        if raw is None:
            raw = match_obj.group('full')

        if match_obj is not None:
            abs_start = start_offset + match_obj.start()
            abs_end = start_offset + match_obj.end()
        else:
            abs_start = start_offset
            abs_end = start_offset + len(raw)

        if _inside_excluded_env(text, abs_start, abs_end):
            return False
        if _overlaps(abs_start, abs_end):
            return False

        stripped = raw.strip()
        if len(stripped) < 30:
            return False

        used_spans.append((abs_start, abs_end))
        results.append({
            'raw_latex': stripped,
            'clean_text': _clean_latex(raw),
            'name': name.strip() if name else None,
            'env_name': 'distilled',
        })
        return True

    def _extract_name(m, keys=('name', 'name1', 'name2')):
        for k in keys:
            try:
                val = m.group(k)
                if val:
                    return val.strip()
            except IndexError:
                continue
        return None

    # ---- Notation/Convention environments ----
    for m in _NOTATION_ENV_PATTERN.finditer(text):
        _add_result(None, m.start(), name=m.group('title'), raw=m.group(0))

    # ---- P1: \textit{X} is a/an/the ... ----
    for m in _P1_TEXTIT_IS.finditer(text):
        _add_result(m, 0, name=m.group('name'))

    # ---- P2: "defined as follows:" + equation ----
    for m in _P2_DEFINED_AS_FOLLOWS.finditer(text):
        _add_result(m, 0)

    # ---- P3: "is defined by/as:" + equation ----
    for m in _P3_DEFINED_BY_EQ.finditer(text):
        _add_result(m, 0)

    # ---- P4: "A/An \emph{X} ... consists of / is a ..." ----
    for m in _P4_EMPH_DEF.finditer(text):
        name = _extract_name(m)
        if name:
            name = re.sub(r'\\(?:emph|textit|textbf)\{([^}]+)\}', r'\1', name).strip()
        _add_result(m, 0, name=name)

    # ---- P5: "X is/are \emph{Y} if ..." ----
    for m in _P5_IS_EMPH_IF.finditer(text):
        _add_result(m, 0, name=m.group('name'))

    # ---- P6: "is called a \emph{Y}" ----
    for m in _P6_IS_CALLED.finditer(text):
        _add_result(m, 0, name=_extract_name(m, ('name1', 'name2')))

    # ---- Final dedup: keep longer match when overlapping text ----
    if len(results) > 1:
        deduped = []
        results_sorted = sorted(results, key=lambda r: len(r['raw_latex']), reverse=True)
        kept_texts = []
        for r in results_sorted:
            is_dup = False
            for kept in kept_texts:
                if r['raw_latex'] in kept or kept in r['raw_latex']:
                    is_dup = True
                    break
                shorter = min(len(r['raw_latex']), len(kept))
                longer = max(len(r['raw_latex']), len(kept))
                if shorter > 0.7 * longer:
                    common = 0
                    for c1, c2 in zip(r['raw_latex'], kept):
                        if c1 == c2:
                            common += 1
                        else:
                            break
                    if common > 0.5 * shorter:
                        is_dup = True
                        break
            if not is_dup:
                deduped.append(r)
                kept_texts.append(r['raw_latex'])
        results = deduped

    return results
