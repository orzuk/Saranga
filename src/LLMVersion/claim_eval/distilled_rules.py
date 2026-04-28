import re
from typing import List, Dict

# Environment names that map to "claim" kind
CLAIM_ENV_NAMES = [
    "claim",
    "Claim",
    "mclaim",
    "Mclaim",
    "mainclaim",
    "Mainclaim",
    "subclaim",
    "Subclaim",
    "counterclaim",
    "Counterclaim",
    "cclaim",
    "Cclaim",
]

# Build a pattern that matches \begin{<env>} ... \end{<env>} for all claim-like environments
_env_names_pattern = "|".join(re.escape(name) for name in CLAIM_ENV_NAMES)

# Pattern to match claim-like environments
# Captures: group 1 = env name, group 2 = full body including \begin and \end
CLAIM_ENV_RE = re.compile(
    r'(\\begin\s*\{(' + _env_names_pattern + r')\}'
    r'(?:\s*\[(?P<optarg>[^\]]*)\])?'  # optional argument like \begin{claim}[name]
    r'.*?'
    r'\\end\s*\{\2\})',
    re.DOTALL
)

# Pattern to extract \label{...}
LABEL_RE = re.compile(r'\\label\s*\{([^}]*)\}')

# Excluded environments: proof, theorem, lemma, remark, example, etc.
# We check if a match is inside one of these
EXCLUDED_ENV_NAMES = [
    "proof",
    "theorem",
    "lemma",
    "remark",
    "example",
    "corollary",
    "proposition",
    "definition",
]

_excluded_env_pattern = "|".join(re.escape(name) for name in EXCLUDED_ENV_NAMES)

EXCLUDED_BEGIN_RE = re.compile(
    r'\\begin\s*\{(' + _excluded_env_pattern + r')\}',
    re.DOTALL
)

EXCLUDED_END_RE = re.compile(
    r'\\end\s*\{(' + _excluded_env_pattern + r')\}',
    re.DOTALL
)

# Patterns for cleaning LaTeX
LATEX_CMD_RE = re.compile(r'\\(?:begin|end)\s*\{[^}]*\}')
LATEX_LABEL_RE = re.compile(r'\\label\s*\{[^}]*\}')
LATEX_COMMAND_RE = re.compile(r'\\(?:emph|textbf|textit|textrm|mathrm|mathsf|mathbb|mathcal|operatorname)\s*\{([^}]*)\}')
LATEX_SIMPLE_CMD_RE = re.compile(r'\\(?:par|noindent|newline|bigskip|medskip|smallskip|\\)\b')
LATEX_GENERIC_CMD_RE = re.compile(r'\\([a-zA-Z]+)')
MULTI_SPACE_RE = re.compile(r'\s+')


def _clean_latex(text: str) -> str:
    """Strip LaTeX commands to produce a simplified plain text version."""
    result = text
    # Remove \begin{...} and \end{...}
    result = LATEX_CMD_RE.sub('', result)
    # Remove \label{...}
    result = LATEX_LABEL_RE.sub('', result)
    # Unwrap formatting commands like \emph{...} -> ...
    for _ in range(3):  # multiple passes for nested commands
        result = LATEX_COMMAND_RE.sub(r'\1', result)
    # Remove simple commands
    result = LATEX_SIMPLE_CMD_RE.sub(' ', result)
    # Remove dollar signs (inline math delimiters) but keep content
    result = result.replace('$', '')
    # Remove remaining backslash commands but keep their names as readable text
    result = LATEX_GENERIC_CMD_RE.sub(r'\1', result)
    # Remove braces
    result = result.replace('{', '').replace('}', '')
    # Collapse whitespace
    result = MULTI_SPACE_RE.sub(' ', result).strip()
    return result


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """Check if the region [start, end) is inside an excluded environment (proof, theorem, etc.)."""
    # Look for \begin{excluded} before start that doesn't have a matching \end{excluded} before start
    prefix = text[:start]
    
    for env_name in EXCLUDED_ENV_NAMES:
        begin_pattern = re.compile(r'\\begin\s*\{' + re.escape(env_name) + r'\}')
        end_pattern = re.compile(r'\\end\s*\{' + re.escape(env_name) + r'\}')
        
        begins = list(begin_pattern.finditer(prefix))
        ends = list(end_pattern.finditer(prefix))
        
        # Count nesting: if more begins than ends in prefix, we're inside
        if len(begins) > len(ends):
            return True
    
    return False


def extract_distilled_claim(text: str) -> List[Dict]:
    """Extract claim-like structures from LaTeX source text."""
    results = []
    seen_spans = []
    
    for match in CLAIM_ENV_RE.finditer(text):
        raw_latex = match.group(1)
        match_start = match.start()
        match_end = match.end()
        
        # Check if inside excluded environment
        if _inside_excluded_env(text, match_start, match_end):
            continue
        
        # Check for overlap with existing matches
        overlapping = False
        for (s, e) in seen_spans:
            if match_start < e and match_end > s:
                overlapping = True
                break
        if overlapping:
            continue
        
        seen_spans.append((match_start, match_end))
        
        # Extract name from optional argument or label
        name = None
        optarg = match.group('optarg')
        if optarg:
            name = optarg.strip()
        else:
            label_match = LABEL_RE.search(raw_latex)
            if label_match:
                name = label_match.group(1).strip()
        
        clean_text = _clean_latex(raw_latex)
        
        results.append({
            'raw_latex': raw_latex,
            'clean_text': clean_text,
            'name': name if name else None,
            'env_name': 'distilled',
        })
    
    return results
