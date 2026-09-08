import re
from typing import List, Dict

# Module-level compiled patterns

SUBSECTION_PROOF_PATTERN = re.compile(
    r'\\(?:sub)*section\s*\*?\s*\{\s*Proof[^}]*\}'
    r'(?:\s*\\label\{[^}]*\})?'
    r'\s*(?P<body>.*?)'
    r'(?=\\(?:sub)*section|\\end\s*\{\s*document\s*\}|\Z)',
    re.DOTALL | re.IGNORECASE
)

# Environments to exclude (proof-like content inside these is already captured or not desired)
EXCLUDED_ENVS = re.compile(
    r'\\begin\{(proof|Proof|example|Example|remark|Remark)\}',
    re.DOTALL
)


def _clean_latex(text: str) -> str:
    """Remove common LaTeX commands and return cleaner plain text."""
    # Remove comments
    text = re.sub(r'%[^\n]*', '', text)
    # Remove \label{...}
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    # Remove display math environments (replace with placeholder)
    text = re.sub(r'\\begin\{(equation|align|gather|multline|flalign|eqnarray)\*?\}.*?\\end\{\1\*?\}', ' [MATH] ', text, flags=re.DOTALL)
    # Remove inline math
    text = re.sub(r'\$\$.*?\$\$', ' [MATH] ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]*\$', ' [MATH] ', text)
    # Remove common LaTeX commands
    text = re.sub(r'\\(?:emph|textbf|textit|mathrm|mathbf|mathit|text|underline|overline)\{([^}]*)\}', r'\1', text)
    # Remove remaining commands with arguments
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^}]*\}', '', text)
    # Remove remaining commands
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _inside_excluded_env(text: str, start: int, end: int) -> bool:
    """
    Check if the span [start, end) is inside an excluded environment
    (proof, example, remark) that was already handled by the base parser.
    """
    # Find all begin positions of excluded envs before start
    for m in EXCLUDED_ENVS.finditer(text):
        env_name = m.group(1)
        env_begin = m.start()
        if env_begin > start:
            break
        # Find the corresponding \end{env_name}
        end_pattern = re.compile(re.escape(r'\end{' + env_name + '}'))
        end_match = end_pattern.search(text, env_begin + len(m.group(0)))
        if end_match:
            env_end = end_match.end()
            # If the match span overlaps with excluded env
            if env_begin <= start and end <= env_end:
                return True
    return False


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove results with duplicate or fully overlapping raw_latex content."""
    seen = set()
    deduped = []
    for r in results:
        key = r['raw_latex'].strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
    for r in deduped:
        r.pop('_start', None)

    return deduped


def extract_distilled_proof(text: str) -> List[dict]:
    """
    Extract proof structures not captured by the base parser.
    Specifically targets proofs written as subsections/sections with
    a title beginning with 'Proof'.
    """
    results = []

    # Rule: subsection/section whose title starts with "Proof"
    for match in SUBSECTION_PROOF_PATTERN.finditer(text):
        body = match.group('body')
        if body is None:
            continue
        body = body.strip()
        if not body:
            continue

        match_start = match.start()
        match_end = match.end()

        # Skip if inside an excluded environment
        if _inside_excluded_env(text, match_start, match_end):
            continue

        # Extract optional name from the section title
        title_match = re.match(
            r'\\(?:sub)*section\s*\*?\s*\{\s*(Proof[^}]*)\}',
            match.group(0),
            re.IGNORECASE
        )
        name = title_match.group(1).strip() if title_match else None

        clean_text = _clean_latex(body)

        results.append({
            'raw_latex': body,
            'clean_text': clean_text,
            'name': name,
            'env_name': 'distilled',
            'rule_name': 'SUBSECTION_PROOF_PATTERN',
            'structure_type': 'proof',
        })

    results = _deduplicate(results)
    return results
