#!/usr/bin/env python3
"""
NtRED Distillation Analysis Pipeline
=====================================
Subcommands:
  dark-knowledge  Identify gold items missed by manual but caught by LLMs
  discovery       Find LLM-consensus structures not in manual extractions
  analyze         Mine LaTeX patterns from missed structures
  aggregate       Aggregate LLM-suggested rules into distilled_rules.py
  validate        Check if manual parser now catches previously missed items
  prune           Comment out distilled rules that cause false positives
"""

import csv
import glob as globmod
import inspect
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import FULL_PAPERS_DIR

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

# Canonical implementations live in src/node_similarity.py; the DISTILLATION
# profile reproduces the behaviour this file used to define inline.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__)))))
from node_similarity import Profile as _Profile          # noqa: E402
from node_similarity import normalize_latex              # noqa: E402,F401
from node_similarity import text_sim as _text_sim        # noqa: E402
from node_similarity import tokenize as _ns_tokenize     # noqa: E402
import latex_facts as _latex_facts                         # noqa: E402

_TEXT_CACHE: Dict[str, str] = {}


def paper_text(path: str) -> str:
    """The text distilled rules run on in production: the document body of
    latex_facts' prepared source (\\input inlined, comments and disabled text
    removed, the paper's own macros expanded), exactly as PaperParser.parse_file
    hands it to the rules. Pruning, the speed guard and the teacher's context
    must see this text, not the raw file, or their verdicts are about a
    different string. Cached per path."""
    if path not in _TEXT_CACHE:
        source = _latex_facts.extract_facts(_latex_facts.read_tex(path))["source"]
        begin = source.find("\\begin{document}")
        _TEXT_CACHE[path] = source[begin + len("\\begin{document}"):] if begin != -1 else source
    return _TEXT_CACHE[path]


def tokenize_latex(text):
    return _ns_tokenize(text, _Profile.DISTILLATION)


# Match metric for every comparison in this module — most importantly the
# prune gate's TP/FP verdict. Callers select it (silver_distillation_merged /
# _sequential set it from --match-metric); "jaccard" keeps the historical
# default for anything that does not.
#
# This used to be hard-wired: `jaccard_similarity` passed no `metric=`, so
# --match-metric containment silently never reached the prune gate while the
# baseline-metrics path (silver_distillation_sequential.jaccard_similarity) did
# honour it. The two halves of a run were scored by different metrics.
def jaccard_similarity(text1, text2):
    """Match score used by the distillation (SILVER profile; metric read from node_similarity).

    The metric lives in ONE place (node_similarity.MATCH_METRIC) and is read at
    call time. The profile is SILVER, the one every distillation driver has used:
    until 2026-10-14 this function defined the DISTILLATION profile and
    silver_distillation_sequential replaced it at import time, so the
    DISTILLATION profile never ran in production. Now the two agree by
    construction rather than by monkey-patch.
    """
    import node_similarity as _ns
    return _text_sim(text1, text2, profile=_Profile.SILVER,
                     metric=_ns.MATCH_METRIC)


def _find_local_tex(paper_id: str, search_dirs: Optional[List[str]] = None) -> Optional[Tuple[str, str]]:
    """Find local .tex file for paper_id. Returns (tex_path, versioned_id) or None.

    Parameters
    ----------
    paper_id : arXiv-style ID (e.g. '1210.4634') or portal-style (e.g. 'paper001')
    search_dirs : additional directories to search (e.g. alignment/papers/paperNNN/source/)
    """
    # Search FULL_PAPERS_DIR first (default)
    pattern = os.path.join(FULL_PAPERS_DIR, "**", f"{paper_id}*.tex")
    matches = globmod.glob(pattern, recursive=True)
    if matches:
        tex_path = matches[0]
        versioned_id = Path(tex_path).stem
        return tex_path, versioned_id

    # Search additional dirs (e.g. alignment/papers/paperNNN/source/)
    # If a dir contains a path segment named after the paper_id, treat it as
    # belonging to that paper. Otherwise prefer files named like the paper_id;
    # fall back to any .tex when the dir is paper-specific by construction.
    if search_dirs:
        for d in search_dirs:
            if paper_id and paper_id not in d:
                # Skip cumulative dirs that don't belong to this paper
                continue
            for pat_glob in (f"{paper_id}*.tex", "*.tex"):
                pattern = os.path.join(d, "**", pat_glob)
                matches = globmod.glob(pattern, recursive=True)
                if not matches:
                    continue
                # Prefer files with \documentclass (main file)
                for m in matches:
                    try:
                        with open(m, 'r', encoding='utf-8', errors='replace') as f:
                            head = f.read(2000)
                        if '\\documentclass' in head:
                            return m, Path(m).stem
                    except OSError:
                        continue
                return matches[0], Path(matches[0]).stem

    return None


def _load_detailed_matches(eval_dir: str) -> List[dict]:
    """Load detailed_matches.csv from eval_dir, trying common subpaths."""
    candidates = [
        os.path.join(eval_dir, "detailed_matches.csv"),
    ]
    # Also look inside provider subdirs (the pipeline writes per-provider dirs)
    for entry in os.listdir(eval_dir) if os.path.isdir(eval_dir) else []:
        candidates.append(os.path.join(eval_dir, entry, "detailed_matches.csv"))

    all_rows = []
    seen_files = set()
    for path in candidates:
        if os.path.isfile(path) and path not in seen_files:
            seen_files.add(path)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))

    if not all_rows:
        # Try globbing recursively
        for path in globmod.glob(os.path.join(eval_dir, "**/detailed_matches.csv"), recursive=True):
            if path not in seen_files:
                seen_files.add(path)
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    reader = csv.DictReader(f)
                    all_rows.extend(list(reader))

    return all_rows


def _load_gold_csv(gold_csv: str) -> Dict[str, List[dict]]:
    """Load gold standard CSV. Returns {paper_id: [{raw_latex, clean_text}, ...]}."""
    gold_data: Dict[str, List[dict]] = {}
    with open(gold_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        for row in reader:
            row = {k.strip(): v for k, v in row.items()}
            paper_id = row['paper_id'].strip().replace('_', '.')
            if paper_id not in gold_data:
                gold_data[paper_id] = []
            gold_data[paper_id].append({
                'raw_latex': row.get('Gold_Standard_raw_latex', ''),
                'clean_text': row.get('Gold_Standard_clean_text', ''),
            })
    return gold_data


def _gold_for_paper(gold_data: Dict[str, List[dict]], paper_id: str) -> List[dict]:
    """Gold rows for `paper_id`, tolerant of the arXiv version suffix.

    Callers normalise ids with ``re.sub(r'v\\d+$', '', paper_id)``, but the gold
    CSV is keyed by the JSON filename stem — which for the v5.1 silver corpus IS
    versioned (``1504.01485v1``). Looking up only the stripped form missed every
    row, so every extraction scored as a false positive and the FDR gate pruned
    100% of distilled rules. That never surfaced on the v4.1 corpus because
    ``paperNNN`` ids carry no version suffix.

    Try the id as given first, then the stripped form, then a stripped-key scan.
    """
    if paper_id in gold_data:
        return gold_data[paper_id]
    stripped = re.sub(r'v\d+$', '', paper_id).replace('_', '.')
    if stripped in gold_data:
        return gold_data[stripped]
    for k, v in gold_data.items():
        if re.sub(r'v\d+$', '', k) == stripped:
            return v
    return []


LLM_PROVIDERS = {'anthropic', 'openai', 'huggingface'}

# ---------------------------------------------------------------------------
# Function 1: identify_dark_knowledge
# ---------------------------------------------------------------------------

def _load_extractions(eval_dir: str) -> Dict[Tuple[str, str], List[str]]:
    """Load full-length extraction texts from definitions.csv (wide format).

    Returns {(paper_id, provider): [text, ...]} with untruncated texts.
    Falls back to detailed_matches.csv if definitions.csv not found.
    """
    defs_path = os.path.join(eval_dir, "definitions.csv")
    result: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    if os.path.isfile(defs_path):
        with open(defs_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [n.strip() for n in reader.fieldnames]
            # Detect providers from column names: {provider}_raw_latex
            providers = []
            for col in reader.fieldnames:
                if col.endswith('_raw_latex'):
                    providers.append(col.replace('_raw_latex', ''))
            for row in reader:
                row = {k.strip(): v for k, v in row.items()}
                pid = row['paper_id'].strip()
                for prov in providers:
                    text = row.get(f'{prov}_raw_latex', '').strip()
                    if text:
                        result[(pid, prov)].append(text)
        return result

    # Fallback: detailed_matches.csv (may have truncated texts)
    rows = _load_detailed_matches(eval_dir)
    for r in rows:
        text = r.get('definition_text', '').strip()
        if text:
            result[(r['paper_id'].strip(), r['provider'].strip())].append(text)
    return result


def identify_dark_knowledge(eval_dir: str, gold_csv: str, structure_type: str,
                            threshold: float = 0.7,
                            match_mode: str = "m1",
                            cover: float = 0.7,
                            support_ext_by_paper: dict = None) -> List[dict]:
    """Distillation mode: gold=exists AND manual=FN AND any_LLM=TP.

    Returns list of dicts with:
      paper_id, gold_index, gold_text, found_by_llms, manual_best_similarity

    ``match_mode`` decides what "manual already caught it" means, and therefore
    what we pay the LLM to write rules for:
      m1  some single extraction matches the gold item (today's behaviour)
      m3  the UNION of extractions covers ``cover`` of it — several nodes
          jointly covering one gold node is decomposition, not a miss, so
          distilling a rule for it would only add a duplicate
    See ``match_modes`` for why.

    Coverage is judged WITHIN the type being scored, and that differs from the
    prune gate on purpose — do not "fix" the inconsistency. The gate asks "is
    the span I emitted real content anywhere?", so cross-type support is right
    there. This asks "must I still learn to extract this node AS this type?",
    and a span filed under another type does not answer that: a definition
    swallowed by a proof extraction is still a definition the parser cannot
    find. Measured on a 4-paper probe, cross-type scope here marked 79% of
    missed items as covered (124 -> 26), suppressing real learning while
    changing nothing about the parser's actual behaviour.

    ``support_ext_by_paper`` — optional {paper_id: [extraction, ...]} across
    every type, m3 only, for callers that deliberately want the cross-type
    question. Left unset by the pipeline. m1 ignores it entirely: it has no
    notion of support.
    """
    gold_data = _load_gold_csv(gold_csv)
    if not gold_data:
        print(f"ERROR: No gold data loaded from {gold_csv}")
        return []

    # Load full-length extractions (from definitions.csv, not truncated detailed_matches)
    by_paper_provider = _load_extractions(eval_dir)
    if not by_paper_provider:
        print(f"ERROR: No extraction data found in {eval_dir}")
        return []

    dark_knowledge_items = []

    for paper_id, gold_items in gold_data.items():
        # Also try versioned form for matching against extractions
        paper_id_stripped = re.sub(r'v\d+$', '', paper_id)
        possible_pids = {paper_id, paper_id_stripped}
        # Find which paper_id form appears in the extractions
        match_pid = None
        for pid in possible_pids:
            if any((pid, p) in by_paper_provider for p in ['manual'] + list(LLM_PROVIDERS)):
                match_pid = pid
                break
        # Also check versioned forms present in data
        if match_pid is None:
            for key_pid, _ in by_paper_provider:
                stripped = re.sub(r'v\d+$', '', key_pid)
                if stripped == paper_id_stripped:
                    match_pid = key_pid
                    break

        if match_pid is None:
            continue  # No eval data for this paper

        for gold_idx, gold_item in enumerate(gold_items):
            gold_text = gold_item['raw_latex']
            if not gold_text.strip():
                continue

            # Check manual: does it match this gold item?
            manual_texts = by_paper_provider.get((match_pid, 'manual'), [])
            manual_best_sim = 0.0
            for mt in manual_texts:
                sim = jaccard_similarity(mt, gold_text)
                manual_best_sim = max(manual_best_sim, sim)

            if match_mode == "m1":
                # Strict same-type: unchanged, and cross-type support does not
                # apply — m1 has no support concept.
                manual_matched = manual_best_sim >= threshold
            else:
                import match_modes as _mm
                # Cross-type when supplied, matching the prune gate's scope.
                cover_texts = manual_texts
                if support_ext_by_paper:
                    extra = support_ext_by_paper.get(match_pid) or []
                    if extra:
                        cover_texts = list(manual_texts) + list(extra)
                manual_matched = _mm.gold_is_found(
                    gold_text, cover_texts, threshold,
                    mode=match_mode, cover=cover)

            if manual_matched:
                continue  # Manual caught it — not dark knowledge

            # Check LLMs: does any match this gold item?
            found_by = []
            for llm in sorted(LLM_PROVIDERS):
                llm_texts = by_paper_provider.get((match_pid, llm), [])
                for lt in llm_texts:
                    sim = jaccard_similarity(lt, gold_text)
                    if sim >= threshold:
                        found_by.append(llm)
                        break

            if not found_by:
                continue  # No LLM caught it either — hard case, not dark knowledge

            dark_knowledge_items.append({
                'paper_id': paper_id,
                'gold_index': gold_idx,
                'gold_text': gold_text,
                'found_by_llms': ','.join(found_by),
                'num_llms': len(found_by),
                'manual_best_similarity': f'{manual_best_sim:.3f}',
            })

    return dark_knowledge_items


# ---------------------------------------------------------------------------
# Function 2: identify_discovery_candidates
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Function 3: analyze_patterns
# ---------------------------------------------------------------------------

# Known environments that the manual parser already handles
KNOWN_ENVS = {
    'theorem', 'Theorem', 'thm',
    'lemma', 'Lemma', 'lem',
    'proposition', 'Proposition', 'prop',
    'corollary', 'Corollary', 'cor',
    'claim', 'Claim',
    'definition', 'Definition', 'defn', 'dfn', 'Def', 'Defn',
    'proof', 'Proof',
    'algorithm', 'algorithm*', 'Algorithm', 'Algorithm*',
    'conjecture', 'Conjecture', 'conj',
    'problem', 'Problem', 'prob',
    'table', 'table*', 'tabular', 'tabular*',
    'example', 'Example', 'remark', 'Remark',
}


# ---------------------------------------------------------------------------
# LLM-powered analysis helpers
# ---------------------------------------------------------------------------

# List prices, USD per million tokens (input, output), by model-name prefix; the
# longest matching prefix wins. Estimates for reporting only: check the provider's
# current price list before quoting a cost.
PRICING = {
    'claude-opus':        (5.0, 25.0),
    'claude-opus-4-1':    (15.0, 75.0),
    'claude-opus-4-0':    (15.0, 75.0),
    'claude-sonnet':      (3.0, 15.0),
    'claude-haiku':       (1.0, 5.0),
    'claude-haiku-5-5':   (0.10, 0.50),
    'gpt-6.1-sol':        (2.0, 10.0),
}


def model_rates(model: str) -> Tuple[float, float]:
    """(input, output) USD per million tokens for `model`; Sonnet rates if unknown."""
    hits = [p for p in PRICING if p in (model or '')]
    return PRICING[max(hits, key=len)] if hits else PRICING['claude-sonnet']


def estimate_cost(usage: dict, model: str) -> float:
    """Cache-aware USD estimate for a usage dict (see _empty_usage).

    Anthropic reports non-cached input in ``input_tokens`` and bills cache reads
    at 0.1x and cache writes at 1.25x the input rate."""
    i_rate, o_rate = model_rates(model)
    inp = usage.get('input_tokens', 0) or 0
    cr = usage.get('cache_read_input_tokens', 0) or 0
    cw = usage.get('cache_creation_input_tokens', 0) or 0
    out = usage.get('output_tokens', 0) or 0
    return (inp * i_rate + cr * i_rate * 0.1 + cw * i_rate * 1.25 + out * o_rate) / 1_000_000


# The teacher model used when a caller does not name one (the drivers always do).
DEFAULT_TEACHER = 'claude-sonnet-4-6'

STRUCTURE_EXTRACT_METHODS = {
    "definition": "_extract_definitions_manual",
    "theorem": "_extract_theorem_like",
    "lemma": "_extract_theorem_like",
    "proposition": "_extract_theorem_like",
    "corollary": "_extract_theorem_like",
    "claim": "_extract_theorem_like",
    "conjecture": "_extract_theorem_like",
    "problem": "_extract_theorem_like",
    "proof": "_extract_proofs",
    "algorithm": "_extract_algorithms",
    "table": "_extract_tables",
    "open_problem": "_extract_theorem_like",
    "remark": "_extract_simple_envs",
    "example": "_extract_simple_envs",
    "assumption": "_extract_simple_envs",
    "exercise": "_extract_exercises",
}


def _read_extraction_method(structure_type: str) -> str:
    """Read the source code of the relevant extraction method from math_paper_parser.py.

    Also includes _extract_envs (environments come from latex_facts) as shared
    context.
    """
    from math_paper_parser import PaperParser

    method_name = STRUCTURE_EXTRACT_METHODS.get(structure_type)
    if not method_name:
        return f"# Unknown structure type: {structure_type}"

    parts = []

    # 1) _extract_envs (shared infrastructure)
    try:
        envs_method = getattr(PaperParser, '_extract_envs')
        parts.append(inspect.getsource(envs_method))
    except Exception:
        pass

    # 2) The target extraction method
    try:
        target_method = getattr(PaperParser, method_name)
        parts.append(inspect.getsource(target_method))
    except Exception:
        parts.append(f"# Could not read method {method_name}")

    return '\n\n'.join(parts)


def _classify_pattern(gold_text: str, tex_source: str) -> Tuple[str, str, str]:
    """Find gold_text in tex_source and classify the LaTeX pattern.

    Returns (context, pattern_type, suggested_regex_hint).
    """
    # Try to locate the gold text in the source
    # Use token overlap to find best-matching window
    gold_tokens = tokenize_latex(normalize_latex(gold_text))
    if not gold_tokens:
        return ('', 'empty_gold', '')

    # Slide a window over the source to find the best match
    best_pos = -1
    best_sim = 0.0
    window_size = max(len(gold_text) * 2, 500)
    step = max(window_size // 4, 100)

    for i in range(0, len(tex_source) - min(window_size, len(tex_source)) + 1, step):
        chunk = tex_source[i:i + window_size]
        chunk_tokens = tokenize_latex(normalize_latex(chunk))
        if not chunk_tokens:
            continue
        sim = len(gold_tokens & chunk_tokens) / len(gold_tokens | chunk_tokens)
        if sim > best_sim:
            best_sim = sim
            best_pos = i

    if best_sim < 0.3 or best_pos < 0:
        return ('', 'not_found_in_tex', f'gold_text not locatable (best_sim={best_sim:.2f})')

    # Extract context around the match
    ctx_start = max(0, best_pos - 200)
    ctx_end = min(len(tex_source), best_pos + window_size + 200)
    context = tex_source[ctx_start:ctx_end]

    # Classify the pattern
    # 1) Check for custom \newtheorem environments
    newtheorem_pattern = re.compile(r'\\newtheorem\s*\{([^}]+)\}')
    custom_envs = set()
    for m in newtheorem_pattern.finditer(tex_source):
        env_name = m.group(1).strip()
        if env_name not in KNOWN_ENVS:
            custom_envs.add(env_name)

    # Check if context is inside a custom environment
    for env in custom_envs:
        if re.search(rf'\\begin\{{{re.escape(env)}\}}', context):
            return (context, 'custom_newtheorem',
                    f'Custom environment "{env}" (from \\newtheorem)')

    # 2) Check for textual pattern (e.g., **Theorem 3.2.** or \textbf{Theorem 3.2.})
    textual_re = re.compile(
        r'(?:\\textbf\s*\{|\\noindent\s*\\textbf\s*\{|\\paragraph\s*\{|\\textsc\s*\{)'
        r'\s*(Definition|Theorem|Lemma|Proposition|Corollary|Claim|Conjecture|Problem)'
        r'\s*[\d.]*\s*[.}]',
        re.IGNORECASE
    )
    m_textual = textual_re.search(context)
    if m_textual:
        return (context, 'textual_bold_marker',
                f'Textual marker: {m_textual.group(0)[:80]}')

    # 3) Check for environments not in known set
    env_begin = re.compile(r'\\begin\{([^}]+)\}')
    for m in env_begin.finditer(context):
        env_name = m.group(1).strip().rstrip('*')
        if env_name not in KNOWN_ENVS and env_name not in (
                'document', 'equation', 'align', 'gather', 'multline',
                'enumerate', 'itemize', 'figure', 'abstract', 'center',
                'array', 'cases', 'matrix', 'pmatrix', 'bmatrix',
        ):
            return (context, 'unknown_environment',
                    f'Unknown env: \\begin{{{m.group(1)}}}')

    # 4) Check for inline definition patterns the parser might miss
    inline_re = re.compile(
        r'(?:we\s+(?:define|say|call)|is\s+(?:defined|called|said))',
        re.IGNORECASE
    )
    if inline_re.search(context):
        return (context, 'inline_definition',
                'Inline phrasing — may need a broader textual definition pattern')

    # 5) Fallback
    return (context, 'unclassified', 'Manual inspection needed')


# ---------------------------------------------------------------------------
# Function 4: validate_rules
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Function 5: aggregate_rules
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MERGED (multi-structure) distillation helpers
# ---------------------------------------------------------------------------
# These power scripts/silver_distillation_merged.py: a single pass distills
# *all* requested structure types per paper instead of re-running the whole
# pipeline once per type.  Two levers cut cost vs the per-type path:
#   1. Items are grouped by their shared base extraction method (the 7
#      theorem-like types collapse to ONE "theoremlike" group), so the base
#      method context is sent once per group, not once per type.
#   2. analyze_patterns_batched sends B missed structures per LLM call (not 1)
#      and marks the static base-method source with cache_control so it bills at
#      the cache-read rate on every batch + the aggregate within a paper.
# The originals analyze_patterns / aggregate_rules are left untouched.

# Base extraction method name -> short group key used for extract_distilled_<group>.
_METHOD_GROUP_KEY = {
    "_extract_definitions_manual": "definition",
    "_extract_theorem_like": "theoremlike",
    "_extract_proofs": "proof",
    "_extract_algorithms": "algorithm",
    "_extract_tables": "table",
    "_extract_simple_envs": "simpleenv",
}


def base_method_groups(structure_types: List[str]) -> Dict[str, List[str]]:
    """Group structure types by the base parser method they share.

    Returns {group_key: [types...]} preserving input order.  Types whose method
    is unknown fall back to a singleton group keyed by the type itself.
    """
    groups: Dict[str, List[str]] = {}
    for st in structure_types:
        method = STRUCTURE_EXTRACT_METHODS.get(st)
        gkey = _METHOD_GROUP_KEY.get(method, st)
        groups.setdefault(gkey, []).append(st)
    return groups


def _empty_usage() -> dict:
    return {'input_tokens': 0, 'output_tokens': 0,
            'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0,
            'llm_calls': 0}


def _acc_usage(dst: dict, msg_usage) -> None:
    """Accumulate an Anthropic message.usage into dst (cache-token aware)."""
    dst['input_tokens'] += getattr(msg_usage, 'input_tokens', 0) or 0
    dst['output_tokens'] += getattr(msg_usage, 'output_tokens', 0) or 0
    dst['cache_read_input_tokens'] += getattr(msg_usage, 'cache_read_input_tokens', 0) or 0
    dst['cache_creation_input_tokens'] += getattr(msg_usage, 'cache_creation_input_tokens', 0) or 0


_CLIENT = None


def reply_text(message) -> str:
    """The text of a reply. Newer models may send a thinking block first, so the
    text is every text block joined, never content[0]."""
    return "".join(getattr(b, "text", "") for b in message.content
                   if getattr(b, "type", "text") == "text")


KEY_FILE = os.path.expanduser("~/.anthropic_env")


def ensure_api_key() -> None:
    """Make ANTHROPIC_API_KEY available, or stop before any work is done.

    A run started from a shell that never sourced the key file used to prepare
    every paper and then fail on its first teacher call. If the variable is not
    set, its `export ANTHROPIC_API_KEY=...` line is read from KEY_FILE (the
    value is never printed)."""
    import anthropic
    if os.environ.get("ANTHROPIC_API_KEY") or getattr(anthropic, "STUB", False):
        return
    if os.path.isfile(KEY_FILE):
        for line in open(KEY_FILE, encoding="utf-8"):
            m = re.match(r"\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
            if m:
                os.environ["ANTHROPIC_API_KEY"] = m.group(1)
                return
    raise SystemExit(f"ANTHROPIC_API_KEY is not set and {KEY_FILE} does not define it")


def _client():
    """One Anthropic client per process."""
    global _CLIENT
    if _CLIENT is None:
        import anthropic
        ensure_api_key()
        # long runs make thousands of calls, several at a time: ride out transient
        # overload/rate-limit errors (the SDK backs off) before a call counts as failed
        _CLIENT = anthropic.Anthropic(max_retries=8)
    return _CLIENT


# Run-wide request options (set_llm_options), the cost levers of a teacher run:
#   effort    low | medium | high | xhigh | max: how much the model thinks before
#             answering (thinking is billed as output); None = the model's default
#   thinking  "disabled" turns thinking off (Haiku 5.5 allows it, Sonnet 5.5 does
#             not); None = the model's default (adaptive)
LLM_OPTIONS: dict = {"effort": None, "thinking": None}


def set_llm_options(effort: str | None = None, thinking: str | None = None) -> dict:
    LLM_OPTIONS.update(effort=effort or None, thinking=thinking or None)
    return dict(LLM_OPTIONS)


def call_llm(model: str, system: str, user: str, max_tokens: int,
             usage: dict | None = None, stream: bool = False):
    """One teacher call: `system` is sent as a cached block (the part that repeats
    across calls), `user` as the message. Returns (text, stop_reason).

    If the cached request is rejected, the same request is retried once without
    cache_control, and the first error is printed rather than swallowed. Token
    use (including cache reads and writes) and the call itself are added to
    `usage` (see _empty_usage)."""
    client = _client()
    kw = dict(model=model, max_tokens=max_tokens,
              messages=[{"role": "user", "content": user}])
    if LLM_OPTIONS.get("effort"):
        kw["output_config"] = {"effort": LLM_OPTIONS["effort"]}
    if LLM_OPTIONS.get("thinking") == "disabled":
        kw["thinking"] = {"type": "disabled"}

    def send(**extra):
        if stream:                    # large outputs: avoids the SDK's HTTP timeout
            with client.messages.stream(**kw, **extra) as st:
                return st.get_final_message()
        return client.messages.create(**kw, **extra)
    try:
        msg = send(system=[{"type": "text", "text": system,
                            "cache_control": {"type": "ephemeral"}}])
    except Exception as e:
        print(f"  [llm] cached request failed ({type(e).__name__}: {e}); "
              f"retrying without cache")
        msg = send(system=system)
    if usage is not None:
        usage['llm_calls'] += 1
        _acc_usage(usage, msg.usage)
    return reply_text(msg), getattr(msg, "stop_reason", None)


_JSON_VALID_ESCAPE = set('"\\/bfnrtu')
# \b \f \r \t before a letter, and \n before the rest of a LaTeX command, are LaTeX
# written with one backslash (\textbf, \frac, \begin, \neq), not JSON escapes:
# json.loads would accept them and silently turn them into control characters.
_LATEX_NOT_ESCAPE = re.compile(r"[bfrt][A-Za-z]|n(?:ewcommand|eq\b|abla|oindent|onumber|ewline"
                               r"|ot\b|u\b|e\b|ormalsize|exists|ewpage|i\b)")


def _repair_json_escapes(text: str) -> str:
    """Double invalid backslash escapes occurring INSIDE JSON string literals.

    The model embeds LaTeX/regex in its JSON strings and escapes inconsistently:
    it writes ``{\\it Label.}`` with a single backslash, and ``\\i`` is not a
    valid JSON escape, so json.loads rejects the whole document. JSON has no
    structural backslashes outside strings, so doubling them there is safe.
    """
    out, in_str, i, n = [], False, 0, len(text)
    while i < n:
        c = text[i]
        if not in_str:
            if c == '"':
                in_str = True
            out.append(c)
            i += 1
            continue
        if c == '\\':
            nxt = text[i + 1] if i + 1 < n else ''
            if nxt in _JSON_VALID_ESCAPE and not (
                    nxt == 'u' and not re.match(r'[0-9a-fA-F]{4}', text[i + 2:i + 6])) \
                    and not _LATEX_NOT_ESCAPE.match(text, i + 1):
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                out.append('\\\\')
                i += 1
            continue
        if c == '"':
            in_str = False
        out.append(c)
        i += 1
    return ''.join(out)


def _salvage_json_objects(t: str) -> list:
    """Every COMPLETE top-level {...} object in a possibly-truncated array.

    A response cut off at max_tokens used to cost the ENTIRE batch: json.loads
    raised, [] came back, and all N items were written blank. Scanning for
    balanced objects (respecting string state) and parsing each one separately
    means a truncated response costs only its unfinished last item.
    """
    objs, depth, start, in_str, esc = [], 0, None, False, False
    for i, c in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(t[start:i + 1])
                start = None
    out = []
    for o in objs:
        for cand in (o, _repair_json_escapes(o)):
            try:
                d = json.loads(cand)
                if isinstance(d, dict):
                    out.append(d)
                break
            except json.JSONDecodeError:
                continue
    return out


def _parse_json_array(text: str) -> list:
    """Parse a JSON array from an LLM response.

    Tolerates code fences, a single object, invalid LaTeX/regex escapes, and
    truncation. Returning [] here silently blanks a whole analyze batch, so
    every recoverable case is recovered before giving up.
    """
    t = (text or "").strip()
    if t.startswith("```"):
        t = "\n".join(l for l in t.split("\n") if not l.strip().startswith("```"))

    def _coerce(d):
        return [d] if isinstance(d, dict) else (d if isinstance(d, list) else [])

    # repaired first: unrepaired text with \textbf in it also parses, wrongly
    for cand in (_repair_json_escapes(t), t):
        try:
            return _coerce(json.loads(cand))
        except json.JSONDecodeError:
            continue
    m = re.search(r'\[.*\]', t, re.DOTALL)
    if m:
        for cand in (_repair_json_escapes(m.group(0)), m.group(0)):
            try:
                return _coerce(json.loads(cand))
            except json.JSONDecodeError:
                continue
    return _salvage_json_objects(t)      # truncated: keep the complete objects


def _analyze_row(item: dict, context: str, pattern_type: str, group_key: str,
                 code: str, reasoning: str) -> dict:
    """Build one analyze-CSV row, matching analyze_patterns' schema + type tags."""
    return {
        'paper_id': item['paper_id'],
        'gold_index': item.get('gold_index', ''),
        'gold_text': item.get('gold_text', ''),
        'pattern_type': pattern_type,
        'latex_context': context[:2000] if context else '',
        'llm_reasoning': reasoning,
        'llm_suggested_rule': code,
        'structure_type': item.get('structure_type', group_key),
        'structure_group': group_key,
    }


# Output cap for the batched analyze call. 4096 truncated a batch of 8
# regex-heavy items mid-string, which made the JSON unparseable and blanked
# the ENTIRE batch (36 such rows across the historical eval dirs). Generated
# rule code is verbose; give it room.
ANALYZE_MAX_TOKENS = 16384

#: How many of the MOST RECENT papers keep their full evidence (gold_text,
#: latex_context, reasoning) in the aggregate prompt. Older papers contribute
#: their suggested code only. Set high (e.g. 999) to restore the old
#: send-everything behaviour; see the age-out block in aggregate_rules_merged
#: for why this exists and what it costs.
#: Output ceiling for one aggregate call. Not a model limit -- sonnet-4-6
#: allows 128K -- but large values require streaming, which the aggregate call
#: now uses. Generous on purpose: a truncated rule file is worse than a slow
#: one, and truncation is silent (it compiles, it is callable, it returns None).
AGGREGATE_MAX_TOKENS = 64000

#: Escape hatch: re-derive the rule file from the FULL analyze CSV instead of
#: extending the existing file. Off by design -- the CSV is an append-only
#: archive (498 rows / 1.08 MB at paper 27 for a 32 KB rule file), so sending
#: all of it is the wrong shape and truncates output. Turn on only to rebuild a
#: group from scratch, e.g. after its rule file has been lost or corrupted.
AGGREGATE_FORCE_FULL = False

AGGREGATE_FULL_EVIDENCE_PAPERS = 2


def analyze_patterns_batched(items: List[dict], tex_dir: str = None,
                             group_key: str = None,
                             types_in_group: Optional[List[str]] = None,
                             model: str = DEFAULT_TEACHER,
                             search_dirs: Optional[List[str]] = None,
                             batch_size: int = 8) -> Tuple[List[dict], dict]:
    """Batched, cache-aware analyze for ONE base-method group.

    `items` are dark-knowledge dicts (paper_id, gold_index, gold_text, plus an
    added `structure_type` naming the exact subtype, e.g. 'lemma'); all must
    share the same base-method `group_key` (e.g. 'theoremlike').  One LLM call
    handles up to `batch_size` items: the shared base-method source sits in a
    cache_control'd system block, the user turn lists the missed structures, and
    the model returns a JSON array of per-item rule suggestions.

    Returns (rows, usage); rows match analyze_patterns' CSV schema plus
    `structure_type` and `structure_group`.
    """
    if tex_dir is None:
        tex_dir = FULL_PAPERS_DIR
    types_in_group = types_in_group or [group_key]
    rep_type = types_in_group[0]
    method_source = _read_extraction_method(rep_type)

    usage = _empty_usage()
    rows: List[dict] = []
    tex_cache: Dict[str, str] = {}
    pending: List[tuple] = []   # (item, context, pattern_type)

    for item in items:
        paper_id = item['paper_id']
        gold_text = item.get('gold_text', '')
        if not gold_text.strip():
            continue
        if paper_id not in tex_cache:
            found = _find_local_tex(paper_id, search_dirs=search_dirs)
            if found is None:
                found = _find_local_tex(re.sub(r'v\d+$', '', paper_id),
                                        search_dirs=search_dirs)
            tex_cache[paper_id] = ''
            if found:
                try:
                    tex_cache[paper_id] = paper_text(found[0])
                except OSError:
                    pass
        tex_source = tex_cache[paper_id]
        if not tex_source:
            rows.append(_analyze_row(item, '', 'tex_not_found', group_key,
                                     '', 'TeX source not found'))
            continue
        context, pattern_type, _hint = _classify_pattern(gold_text, tex_source)
        if not context:
            rows.append(_analyze_row(item, '', pattern_type, group_key,
                                     '', f'No context found ({pattern_type})'))
            continue
        pending.append((item, context, pattern_type))

    if not pending:
        return rows, usage

    sys_text = (
        "You are a Python regex engineer for a LaTeX math structure parser.\n\n"
        f"## Base extraction method for the \"{group_key}\" family\n\n"
        f"```python\n{method_source}\n```\n"
    )

    for b in range(0, len(pending), batch_size):
        batch = pending[b:b + batch_size]
        parts = [
            f"Below are {len(batch)} {group_key} structures the base method FAILED "
            f"to extract but SHOULD have. For EACH, give the MINIMAL Python addition "
            f"(a new regex / env name / branch) needed to catch it.\n\n"
            "## GENERALIZATION REQUIREMENT (critical)\n"
            "Each item is ONE EXAMPLE of a recurring structural pattern, NOT a "
            "target to memorize. Your regex MUST generalize to ANY math paper:\n"
            "- Do NOT copy author names, paper-specific terminology, theorem "
            "names, equation/section labels, specific variable names, or custom "
            "macro names from the example (e.g. no 'Marchenko', 'Sinkhorn', "
            "'\\defeq', '(P_k)').\n"
            "- Anchor on STRUCTURE, not content: environment names, "
            "\\begin/\\end, \\textbf/\\emph/\\textit markers, sectioning, "
            "leading keywords ('Definition', 'Algorithm', etc.).\n"
            "- Prefer a small, bounded pattern. If catching the example would "
            "require hardcoding instance-specific text, say so in `reasoning` "
            "and propose the closest GENERAL rule instead (or none).\n"
        ]
        for k, (item, context, pattern_type) in enumerate(batch):
            gtype = item.get('structure_type', group_key)
            parts.append(
                f"\n### Item {k} — type: {gtype} (rule-based guess: {pattern_type})\n"
                f"MISSED {gtype} (gold):\n```\n{item.get('gold_text', '')[:1500]}\n```\n"
                f"LATEX CONTEXT:\n```latex\n{context[:2000]}\n```\n"
            )
        parts.append(
            "\n## Output\nRespond with ONLY a JSON array (no markdown fences), one "
            "object per item, in the SAME order:\n"
            '[{"index": <int matching Item k>, "reasoning": "...", '
            '"suggested_code": "minimal copy-pasteable Python"}]\n'
            "Do NOT rewrite the whole method; output only the minimal addition per item."
        )
        user_text = "".join(parts)
        try:
            reply, _stop = call_llm(model, sys_text, user_text, ANALYZE_MAX_TOKENS, usage)
        except Exception as e2:
            print(f"  [{group_key}] batched analyze call failed: {e2}")
            for k, (item, context, pattern_type) in enumerate(batch):
                rows.append(_analyze_row(item, context, pattern_type,
                                         group_key, '', f'LLM call failed: {e2}'))
            continue
        by_index = {}
        for obj in _parse_json_array(reply):
            try:
                by_index[int(obj.get('index'))] = obj
            except (TypeError, ValueError):
                continue
        # A short response means teacher signal was LOST, not that the model
        # declined (a decline still carries `reasoning`). This used to be
        # completely silent: the batch was written blank and the run reported
        # success, so a group could learn nothing while looking healthy.
        if len(by_index) < len(batch):
            missing = [k for k in range(len(batch)) if k not in by_index]
            stop = _stop
            print(f"  [WARN] {group_key}: recovered {len(by_index)}/{len(batch)} "
                  f"suggestion(s) from this analyze call "
                  f"(stop_reason={stop}); LOST items {missing} for "
                  f"{sorted({batch[k][0]['paper_id'] for k in missing})}. "
                  f"Truncation? raise ANALYZE_MAX_TOKENS or lower --batch-size.")

        for k, (item, context, pattern_type) in enumerate(batch):
            obj = by_index.get(k, {})
            rows.append(_analyze_row(
                item, context, pattern_type, group_key,
                obj.get('suggested_code', ''), obj.get('reasoning', '')))

    print(f"  [{group_key}] batched analyze: {usage['llm_calls']} call(s), "
          f"{usage['input_tokens']} in / {usage['output_tokens']} out "
          f"(cache_read {usage['cache_read_input_tokens']})")
    return rows, usage


def aggregate_rules_merged(input_csv: str, group_key: str,
                           types_in_group: List[str], eval_dir: str,
                           model: str = DEFAULT_TEACHER,
                           new_paper_ids: Optional[List[str]] = None
                           ) -> Tuple[str, dict]:
    """Aggregate analyze rows for ONE base-method group into
    eval_dir/distilled_rules.py exposing ``extract_distilled_<group_key>``.

    For multi-type groups (theoremlike) every returned dict must carry a
    ``structure_type`` field naming the precise subtype, decided from the matched
    environment / marker.  The base-method source is cache_control'd.  On a
    syntax error or missing entry function the previous file is kept (fault
    isolation) and that group's last-good rules survive.

    INCREMENTAL MODE (``new_paper_ids`` given and a rule file already exists):
    the prompt carries the CURRENT distilled_rules.py plus only the rows from
    those papers, and asks the model to extend/correct the file it is shown.

    Otherwise (first paper of a group, no file yet) it falls back to the
    original "aggregate all suggestions from scratch" prompt.

    Why: the CSV is an append-only archive of every FN ever analysed, and
    re-sending all of it to regenerate a much smaller file is the wrong shape.
    Measured on the v5.1 run at paper 27 -- theoremlike had 498 rows / 1.08 MB
    of CSV producing a 32 KB rule file with 11 rules, a 33x ratio, and the
    150-odd distinct names the CSV proposed had ZERO overlap with the 11 the
    model actually kept. definition passed 144k input tokens and truncated its
    16k output for 8 consecutive papers, leaving a file with no `return` that
    silently produced nothing.

    Sending the file instead makes the prompt roughly constant, and it closes
    the loop that was missing entirely: pruned rules are commented out in that
    file with their FP/TP counts, so the model finally sees which of its own
    rules were rejected and why. Pruning now shrinks the prompt instead of
    leaving dead suggestions in it forever.

    The cost: the model no longer sees all raw suggestions side by side, so it
    loses some ability to notice that several papers' variants should merge
    into one general pattern. It was already doing that consolidation and then
    being handed the same rows again next paper.
    """
    rows = _read_items_csv(input_csv)
    rules = []
    for r in rows:
        code = (r.get('llm_suggested_rule') or '').strip()
        if not code:
            continue
        rules.append({
            'paper_id': r.get('paper_id', ''),
            'gold_index': r.get('gold_index', ''),
            'structure_type': r.get('structure_type', group_key),
            'reasoning': (r.get('llm_reasoning') or '').strip(),
            'suggested_code': code,
            'latex_context': (r.get('latex_context') or '').strip(),
            'gold_text': (r.get('gold_text') or '').strip(),
        })

    out_path = os.path.join(eval_dir, 'distilled_rules.py')
    if not rules:
        print(f"  [{group_key}] no non-empty suggestions to aggregate.")
        return (out_path if os.path.isfile(out_path) else ''), _empty_usage()

    rep_type = types_in_group[0]
    base_method_source = _read_extraction_method(rep_type)
    multi = len(types_in_group) > 1
    func_name = f"extract_distilled_{group_key}"

    current_src = ''
    if os.path.isfile(out_path):
        try:
            current_src = open(out_path, encoding='utf-8').read()
        except Exception:
            current_src = ''
    # Incremental is the DEFAULT whenever a rule file exists. A caller that
    # forgets new_paper_ids must not silently fall back to re-sending the whole
    # CSV -- that is the 33x prompt-to-artifact path that truncated definition
    # for 8 papers, and it fails invisibly (bigger prompt, same API, no error).
    # With the argument omitted we infer "new" as the rows of the LAST paper in
    # the CSV, which is append-ordered by paper.
    if new_paper_ids is None and current_src.strip() and not AGGREGATE_FORCE_FULL:
        _last = next((r['paper_id'] for r in reversed(rules) if r['paper_id']), None)
        if _last:
            new_paper_ids = [_last]
            print(f"  [{group_key}] new_paper_ids not given; defaulting to the "
                  f"most recent paper in the CSV ({_last})")
    incremental = (bool(new_paper_ids) and bool(current_src.strip())
                   and not AGGREGATE_FORCE_FULL)
    if incremental:
        _want = set(new_paper_ids)
        _new_rules = [r for r in rules if r['paper_id'] in _want]
        if not _new_rules:
            print(f"  [{group_key}] no NEW suggestions this paper; keeping "
                  f"existing rules.")
            return out_path, _empty_usage()
        rules = _new_rules

    # ---- Age-out: full evidence for recent papers, code-only for older ones --
    # This prompt carries EVERY accumulated row, so it grows with the run: the
    # per-paper cost is linear and the run total quadratic. Measured on the
    # v5.1 corpus, definition reached 62k tokens by paper 2 (+35k/paper) and
    # would have exceeded a 200k context around paper 6.
    #
    # The rows are not equally useful, though. gold_text, latex_context and
    # reasoning exist so the model can DERIVE a rule; once derived, the rule
    # itself is the thing that must survive into the next regeneration. So old
    # rows keep their code and drop their evidence, while rows from the most
    # recent papers — the ones still being turned into rules — keep everything.
    # Nothing is forgotten: every suggestion is still listed, so the model can
    # still merge variants and retract rules that later evidence contradicts.
    # Those three fields are 55-70% of the payload, so this cuts the prompt by
    # roughly 70% once past the recent window.
    recent_pids = []
    for rule in reversed(rules):
        pid = rule['paper_id']
        if pid and pid not in recent_pids:
            recent_pids.append(pid)
        if len(recent_pids) >= AGGREGATE_FULL_EVIDENCE_PAPERS:
            break
    recent = set(recent_pids)
    n_aged = sum(1 for r in rules if r['paper_id'] not in recent)

    rules_text = ""
    for i, rule in enumerate(rules, 1):
        rules_text += (f"\n--- Rule {i} (paper {rule['paper_id']}, "
                       f"type {rule['structure_type']}, gold_index {rule['gold_index']}) ---\n")
        if rule['paper_id'] in recent and rule['reasoning']:
            rules_text += f"Reasoning: {rule['reasoning']}\n"
        rules_text += f"Code:\n{rule['suggested_code']}\n"
    gold_tests_text = ""
    for i, rule in enumerate(rules, 1):
        if rule['paper_id'] not in recent:
            continue          # evidence aged out; the rule itself is above
        gold_tests_text += (f"\n--- Example {i} (paper {rule['paper_id']}, "
                            f"type {rule['structure_type']}) ---\n")
        if rule['gold_text']:
            gold_tests_text += ("EXAMPLE INSTANCE (representative of the class — "
                                "do NOT hardcode its literal tokens):\n"
                                f"{rule['gold_text']}\n")
        if rule['latex_context']:
            gold_tests_text += f"SURROUNDING LATEX CONTEXT:\n{rule['latex_context'][:1500]}\n"
    if n_aged:
        gold_tests_text += (
            f"\n--- ({n_aged} earlier suggestion(s) from previous papers are "
            f"listed under 'Individual rule suggestions' as code only; their "
            f"worked examples are omitted for length. Keep the rules they "
            f"represent unless a rule is wrong or now redundant.) ---\n")

    if multi:
        subtype_block = (
            "## Subtype tagging (REQUIRED)\n\n"
            f"This family covers these subtypes: {', '.join(types_in_group)}.\n"
            "Every result dict MUST include a `structure_type` field set to the "
            "correct subtype, decided from the matched environment or textual "
            "marker (case-insensitive, strip trailing '*'):\n"
            + "".join(f"  - \\begin{{{t}}} or the word '{t.capitalize()}' -> '{t}'\n"
                      for t in types_in_group)
            + "If the subtype is ambiguous, default to 'theorem'.\n")
        st_key_req = "`structure_type` (str, the subtype), "
    else:
        only_type = types_in_group[0]
        subtype_block = (f"## Subtype tagging\n\nEvery result dict MUST include "
                         f"`structure_type` set to '{only_type}'.\n")
        st_key_req = "`structure_type` (str), "

    if incremental:
        task_block = f"""## Task

You are MAINTAINING an existing rule file. Below is the CURRENT file, followed by {len(rules)} NEW rule suggestion(s) for structures the current rules still miss.

Return the COMPLETE updated file. Keep every rule that is still useful, add rules for the new misses, and merge a new suggestion into an existing rule when they overlap rather than adding a near-duplicate.

Lines marked `# PRUNED` were disabled because they produced false positives — the marker records how many. Do NOT reinstate them, and do NOT write a new rule that would match the same thing in the same way. Leave them commented where they are.

## CURRENT RULE FILE (this is what you are editing)

```python
{current_src}
```
"""
    else:
        task_block = f"""## Task

Below are {len(rules)} individual rule suggestions for extracting "{group_key}" structures from LaTeX source. Aggregate them into a SINGLE, clean, self-contained Python file that runs IN ADDITION to the base parser shown in the system context. Do NOT duplicate what the base method already catches — only fill the gaps.
"""

    prompt = f"""You are a Python engineer consolidating regex extraction rules for a LaTeX math paper parser.

{task_block}
{subtype_block}
## EXAMPLE INSTANCES (representative of the pattern class — NOT literal targets)
These show the KINDS of structures to catch. Write rules that capture the
general class; it is acceptable to NOT match an example if matching it would
require hardcoding instance-specific content.
{gold_tests_text}

## {"NEW rule suggestions to incorporate" if incremental else "Individual rule suggestions (for reference)"}
{rules_text}

## Key challenges
1. Multi-sentence statements with display math contain periods; use paragraph boundaries (`\\n\\n`), never `[^.]*\\.`.
2. Precision: every FP is costly. Require a real anchor (env name or bold/emph marker) in the FIRST sentence. Skip matches inside proof/example/remark environments.
3. GENERALIZATION (critical): patterns MUST work on ANY math paper, not just these examples. Do NOT hardcode author names, paper-specific terminology, theorem/section/equation labels, specific variable names, or custom macro names (e.g. no `Marchenko`, `Sinkhorn`, `\\defeq`, `(P_k)`, `\\ulesalgorithm`). Anchor on STRUCTURE (environment names, `\\begin`/`\\end`, `\\textbf`/`\\emph`, sectioning, leading keywords), never on content tokens. Reject any suggested rule above that only works by matching literal instance text.

## Output requirements
1. At the top only `import re`, `from typing import List, Dict`, and the guarded
   latex_clean import of requirement 6
2. A single function: `{func_name}(text: str) -> List[dict]`
3. Each returned dict has keys: `raw_latex` (str), `clean_text` (str), `name` (str or None), `env_name` (str), `rule_name` (str), {st_key_req}
4. `env_name` is `"distilled"`; `rule_name` is the module-level compiled-pattern variable name that produced the match — it MUST equal that variable's name (the prune step keys off it)
5. Use compiled regex patterns at module level; include `_inside_excluded_env(text, start, end)` helper
6. For `clean_text`, do NOT write your own cleaner. Start the file with exactly:
   `try:\n    from latex_clean import clean_latex_to_text as _clean_latex\nexcept Exception:\n    _clean_latex = lambda s: s`
   then use `_clean_latex(raw)`. Never replace math with a `[MATH]` placeholder and never
   delete math content — the base parser preserves math as words, and a cleaner that
   disagrees makes identical statements look different and produces duplicate nodes.
7. Deduplicate overlapping matches
- Apart from that one guarded import, do NOT import any project module; stdlib `re` only
- Output ONLY the Python code, no fences, no explanation"""

    print(f"  [{group_key}] {'extending existing rules with' if incremental else 'aggregating'} "
          f"{len(rules)} suggestion(s)"
          + (f" (current file {len(current_src):,} chars)" if incremental else "")
          + "...")
    sys_block = ("## EXISTING BASE EXTRACTION METHOD (already runs — do NOT "
                 f"duplicate)\n```python\n{base_method_source}\n```")
    # Large max_tokens needs streaming, or the request hits the SDK's HTTP timeout.
    usage = _empty_usage()
    generated_code, stop = call_llm(model, sys_block, prompt, AGGREGATE_MAX_TOKENS,
                                    usage, stream=True)
    # Truncation is a FAILURE, not a result. A cut-off file can still compile
    # (a trailing comment is valid Python) and still expose a callable, so
    # every downstream guard passed it. Keep the previous rules instead.
    if stop == "max_tokens":
        print(f"  [{group_key}] TRUNCATED at max_tokens="
              f"{AGGREGATE_MAX_TOKENS}: generated file is incomplete; "
              f"keeping previous rules. Raise AGGREGATE_MAX_TOKENS or shrink "
              f"the prompt.")
        return (out_path if os.path.isfile(out_path) else ''), usage
    generated_code = generated_code.strip()
    if generated_code.startswith("```"):
        lines = generated_code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        generated_code = "\n".join(lines)

    # Same dedup-bug fixups as aggregate_rules (LLMs reliably reproduce them).
    generated_code = generated_code.replace(
        "if not overlap:\n            del r['_start']\n            deduped.append(r)",
        "if not overlap:\n            deduped.append(r)")
    if "for r in deduped:\n        r.pop('_start', None)" not in generated_code:
        generated_code = generated_code.replace(
            "return deduped",
            "for r in deduped:\n        r.pop('_start', None)\n\n    return deduped")

    os.makedirs(eval_dir, exist_ok=True)
    try:
        compile(generated_code, out_path, 'exec')
    except SyntaxError as e:
        print(f"  [{group_key}] WARNING: syntax error in generated code: {e}; "
              f"keeping previous {out_path}")
        return (out_path if os.path.isfile(out_path) else ''), usage
    if func_name not in generated_code:
        print(f"  [{group_key}] WARNING: {func_name} not found; keeping previous file")
        return (out_path if os.path.isfile(out_path) else ''), usage

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(generated_code)
        f.write('\n')
    print(f"  [{group_key}] wrote {out_path} "
          f"({usage['input_tokens']} in / {usage['output_tokens']} out, "
          f"cache_read {usage['cache_read_input_tokens']})")
    return out_path, usage


# ---------------------------------------------------------------------------
# Function 6: prune_rules
# ---------------------------------------------------------------------------

def _code_paren_delta(line: str) -> int:
    """Net '(' minus ')' on a line, ignoring parens inside string literals.

    Regex rule bodies are string literals full of unbalanced parens (e.g.
    ``r'(?P<name>...)'``); counting those would close the re.compile(...) span
    early and leave trailing ``flags=...,``/``)`` lines uncommented (→ orphaned
    indent → SyntaxError). Blanking quoted spans first fixes that.
    """
    stripped = re.sub(
        r'''(?:[rRbBuUfF]{0,2})('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")''',
        '', line)
    return stripped.count('(') - stripped.count(')')


def _comment_out_rule_block(lines: List[str], pattern_name: str,
                            fp_papers: List[str], tp_count: int,
                            reason: Optional[str] = None,
                            comment_usage: bool = True) -> List[str]:
    """Comment out a compiled pattern's definition and its usage block.

    Prefixes affected lines with ``# `` and inserts a ``PRUNED`` marker so the
    manual parser ignores them while keeping a record they once existed.

    ``reason`` overrides the default FP-based marker text (used by the
    time-guard, which prunes for slowness rather than false positives).

    ``comment_usage=False`` leaves the code that uses the pattern in place: the
    name is rebound to a pattern that never matches, so that code finds
    nothing. _prune_rule_safely falls back to it when commenting the usage out
    would leave the file broken.
    """
    result: List[str] = []
    i = 0
    if reason is not None:
        marker = f"# PRUNED — {reason}"
    else:
        fp_info = ', '.join(fp_papers[:3])
        if len(fp_papers) > 3:
            fp_info += f' +{len(fp_papers) - 3} more'
        tp_note = f" | also {tp_count} TP — review before uncommenting" if tp_count else ""
        marker = f"# PRUNED — FP on {fp_info}{tp_note}"

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # ---- Pattern definition block: _NAME = re.compile(...) ----
        if re.match(rf'^{re.escape(pattern_name)}\s*=\s*re\.compile\(', stripped):
            indent = len(line) - len(stripped)
            result.append(' ' * indent + marker + '\n')
            paren_depth = 0
            while i < len(lines):
                l = lines[i]
                if not l.lstrip().startswith('#'):
                    paren_depth += _code_paren_delta(l)
                result.append('# ' + l)
                i += 1
                if paren_depth <= 0:
                    break
            # Rebind the name to a pattern that never matches: a rule file may
            # also list the pattern by name (a table of (name, pattern, group)),
            # and with the definition gone that reference raises NameError on
            # import, losing the whole group (rule_guard.comment_out_rule does
            # the same for slow rules).
            result.append(' ' * indent + f"{pattern_name} = re.compile(r'(?!x)x')  # PRUNED\n")
            continue

        # ---- Usage block in extract function ----
        if (comment_usage
                and re.search(rf'(?<![A-Za-z0-9_]){re.escape(pattern_name)}(?![A-Za-z0-9_])', stripped)
                and not stripped.startswith('#')
                and any(kw in stripped for kw in
                        ('finditer', 'findall', 'search', 'match('))):
            indent = len(line) - len(stripped)
            # Also comment the section header above (e.g. # ---- P1: ... ----)
            if result and result[-1].strip().startswith('# ----'):
                result[-1] = '# ' + result[-1]
            result.append('# ' + line)
            i += 1
            # Comment out the indented body below
            while i < len(lines):
                l = lines[i]
                s = l.lstrip()
                ind = len(l) - len(s)
                if s == '':
                    result.append(l)  # blank line — pass through
                    i += 1
                elif ind > indent:
                    result.append('# ' + l)
                    i += 1
                else:
                    break
            # Keep the enclosing block syntactically valid. When the usage
            # block IS the whole body of its function (a one-rule extractor,
            # which the aggregate writes often), commenting it out leaves
            # `def f(...):` with nothing under it and the module dies with
            # IndentationError on import -- taking every other rule in the
            # group with it. That killed a 60-paper run at paper 27 after
            # $41 of work. `pass` is legal wherever the statement we just
            # removed was legal, so this is safe unconditionally and costs a
            # line when it is not needed.
            result.append(' ' * indent + 'pass  # PRUNED: body commented out\n')
            continue

        result.append(line)
        i += 1

    return result


def _undefined_names(src: str) -> Optional[set]:
    """Names a module reads but binds nowhere (None if it does not parse).

    Over-approximates bindings: a name bound in any scope counts as bound
    everywhere, so a real binding is never reported. Enough to catch what a
    comment-out breaks: a variable whose only assignment was commented out."""
    import ast as _ast
    import builtins as _builtins
    try:
        tree = _ast.parse(src)
    except SyntaxError:
        return None
    bound, loads = set(), set()
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            bound.add(node.name)
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.Lambda)):
            a = node.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                bound.add(arg.arg)
            for extra in (a.vararg, a.kwarg):
                if extra is not None:
                    bound.add(extra.arg)
        elif isinstance(node, (_ast.Import, _ast.ImportFrom)):
            for al in node.names:
                bound.add((al.asname or al.name).split('.')[0])
        elif isinstance(node, _ast.Name):
            (bound if isinstance(node.ctx, (_ast.Store, _ast.Del)) else loads).add(node.id)
        elif isinstance(node, _ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (_ast.Global, _ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, (_ast.MatchAs, _ast.MatchStar)) and node.name:
            bound.add(node.name)
    return loads - bound - set(dir(_builtins)) - {"__name__", "__file__", "__doc__",
                                                 "__builtins__"}


def _prune_rule_safely(lines: List[str], pattern_name: str, fp_papers: List[str],
                       tp_count: int, reason: Optional[str] = None) -> tuple:
    """Prune one rule without breaking its file. Returns (lines, how).

    Commenting out a usage line can strand the code after it: a rule computed
    `distinct = {... _STEP_REF.findall(para)}` and tested `len(distinct)` on the
    next line, so commenting the first left `distinct` undefined. The file then
    failed the post-prune check, which restored the whole pre-prune file, and
    every rule pruned in that step came back (one of them with 322 FP to 5 TP).

    So each prune is checked on its own: the full comment-out if the file still
    parses and reads no new undefined name; else the definition alone, rebound
    to a never-matching pattern with the usage left in place; else nothing
    (the rule is kept and reported), never a broken file.
      how: "commented" | "rebound" | "skipped"
    """
    before = _undefined_names("".join(lines))
    if before is None:
        return lines, "skipped"
    for how, usage in (("commented", True), ("rebound", False)):
        new = _comment_out_rule_block(lines, pattern_name, fp_papers, tp_count,
                                      reason=reason, comment_usage=usage)
        after = _undefined_names("".join(new))
        if after is not None and not (after - before):
            return new, how
    print(f"  [warn] could not prune {pattern_name} without breaking its file: kept")
    return lines, "skipped"


def prune_slow_rules(rules_path: str, paper_texts: Dict[str, str],
                     max_rule_seconds: float = 10.0,
                     hard_cap: Optional[float] = None) -> Dict[str, float]:
    """Comment out compiled patterns with catastrophic-backtracking runtime.

    Times each compiled ``_NAME`` pattern's ``findall`` over every paper text;
    any whose *worst* per-paper time exceeds ``max_rule_seconds`` is commented
    out (same mechanism as the FP prune). This catches overfit/pathological
    LLM-generated regexes that match little or nothing yet cost seconds per
    document — the FP gate never sees them because a zero-match rule is not a
    false positive.

    A SIGALRM hard cap (default ``max(2.0, 6*max_rule_seconds)``) bounds each
    individual ``findall`` so a truly exponential pattern can't hang the guard
    itself; if the cap trips the pattern is treated as infinitely slow. SIGALRM
    is only armed on the main thread; off-thread it degrades to plain timing.

    Returns ``{pattern_name: worst_seconds}`` for the patterns it pruned.
    """
    import importlib.util
    import time as _time
    import threading as _threading
    import signal as _signal

    spec = importlib.util.spec_from_file_location('distilled_slowguard', rules_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Collect every module-level compiled pattern. Unlike the FP-prune slow
    # path, we do NOT require a leading underscore: LLM codegen names patterns
    # inconsistently (``NAMED_OPT_ENV_RE`` vs ``_PROSE_STEP_RE``), and the worst
    # backtrackers tend to be the un-underscored ones. Skip masking/exclusion
    # patterns (``*EXCL*``) since commenting those out changes filtering logic.
    patterns: Dict[str, re.Pattern] = {}
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, re.Pattern) and 'EXCL' not in name.upper():
            patterns[name] = obj
    if not patterns or not paper_texts:
        return {}

    hard_cap = hard_cap or max(2.0, max_rule_seconds * 6)
    use_alarm = _threading.current_thread() is _threading.main_thread()

    class _PatTimeout(Exception):
        pass

    def _on_alarm(signum, frame):
        raise _PatTimeout()

    old_handler = _signal.signal(_signal.SIGALRM, _on_alarm) if use_alarm else None
    slow: Dict[str, float] = {}
    try:
        for name, pat in patterns.items():
            worst = 0.0
            for txt in paper_texts.values():
                if use_alarm:
                    _signal.setitimer(_signal.ITIMER_REAL, hard_cap)
                t0 = _time.time()
                try:
                    pat.findall(txt)
                except _PatTimeout:
                    worst = float('inf')
                    break
                finally:
                    if use_alarm:
                        _signal.setitimer(_signal.ITIMER_REAL, 0)
                worst = max(worst, _time.time() - t0)
            if worst > max_rule_seconds:
                slow[name] = worst
    finally:
        if use_alarm:
            _signal.signal(_signal.SIGALRM, old_handler)

    if not slow:
        return {}

    print(f"\nTime-guard (cap {max_rule_seconds:.2f}s/paper): pruning "
          f"{len(slow)} slow pattern(s)")
    with open(rules_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for name, secs in sorted(slow.items(), key=lambda kv: -kv[1]):
        shown = "TIMEOUT" if secs == float('inf') else f"{secs:.2f}s"
        print(f"  SLOW  {name}: {shown}")
        lines, how = _prune_rule_safely(
            lines, name, [], 0,
            reason=f"SLOW backtracking ({shown} > {max_rule_seconds:.2f}s/paper cap)")
        if how == "skipped":
            slow.pop(name)
    with open(rules_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return slow


def _run_extract_fn_guarded(extract_fn, text: str, paper_id: str,
                            timeout: float):
    """Run a generated extract_fn under a wall-clock cap. None == give up.

    Returns the extraction list, or None if it raised or blew the cap (the
    caller then skips this paper for this group). SIGALRM can interrupt a
    regex spinning in C, which is the whole point — a plain try/except cannot.

    Only armed on the main thread; SIGALRM is process-global and setting it
    from a worker would both fail and stomp on the main thread's handler. Off
    the main thread this degrades to an unguarded call, which is the current
    behaviour everywhere and no worse than before.
    """
    import signal as _signal
    import threading as _threading

    use_alarm = (_threading.current_thread() is _threading.main_thread()
                 and timeout and timeout > 0)

    class _ExtractTimeout(Exception):
        pass

    def _on_alarm(signum, frame):
        raise _ExtractTimeout()

    old = _signal.signal(_signal.SIGALRM, _on_alarm) if use_alarm else None
    if use_alarm:
        _signal.setitimer(_signal.ITIMER_REAL, timeout)
    try:
        return extract_fn(text)
    except _ExtractTimeout:
        print(f"  [WARN] extract_fn exceeded {timeout:.0f}s on {paper_id} "
              f"(runaway regex) — skipping paper for this group")
        return None
    except Exception as e:
        print(f"  [WARN] extract_fn raised on {paper_id}: {e} — skipping paper")
        return None
    finally:
        if use_alarm:
            _signal.setitimer(_signal.ITIMER_REAL, 0)
            _signal.signal(_signal.SIGALRM, old)


def prune_rules(paper_ids: List[str], structure_type: str,
                gold_csv: str, eval_dir: str,
                threshold: float = 0.7,
                require_fp_majority: bool = False,
                max_fdr: Optional[float] = None,
                tex_search_dirs: Optional[List[str]] = None,
                max_rule_seconds: Optional[float] = 10.0,
                match_mode: str = "m1",
                cover: float = 0.7,
                support_gold_csv: Optional[str] = None,
                extract_timeout: Optional[float] = None) -> int:
    """Identify FP-causing distilled rules and comment them out.

    ``extract_timeout`` — wall-clock cap per paper on the generated
    ``extract_fn``. Defaults to ``max(30, 6*max_rule_seconds)``: generous
    enough that a merely slow group is not skipped, hard enough that a
    runaway regex cannot stall the run indefinitely.

    Calls the distilled extraction function *directly* (bypassing the full
    parser) so we isolate distilled-rule output.  Each FP is attributed to the
    compiled regex pattern that produced it, and that pattern's definition +
    usage block is commented out with a ``# PRUNED`` marker.

    Parameters
    ----------
    require_fp_majority : legacy flag kept for backward compat. Only consulted
        when ``max_fdr`` is None: True -> alpha 0.5 (prune when FP > TP), False
        -> alpha 0.0 (original aggressive behavior, any FP -> prune).
    max_fdr : per-rule false-discovery tolerance ``alpha`` in [0, 1]. A rule is
        pruned when its local FDR ``FP / (FP + TP) > alpha``. Lower alpha is
        stricter. ``alpha=0.5`` reproduces the FP-majority gate; ``alpha=0.0``
        prunes any rule with a single FP. Takes precedence over
        ``require_fp_majority`` when set.
    tex_search_dirs : extra directories to search for paper .tex sources
        (passed to ``_find_local_tex``). Useful when papers live outside
        ``FULL_PAPERS_DIR`` (e.g., the alignment-benchmark layout).
    match_mode : "m1" (default, unchanged behaviour) or "m3". Under m3 an
        extraction contained in ANY gold node is not a false discovery, so the
        gate stops killing rules over nesting / labels / span boundaries. Only
        ~2% of what m1 calls a false positive is content the silver lacks, so
        m1's alpha is tuned against mostly-noise; use a much tighter alpha with
        m3 (``match_modes.DEFAULT_ALPHA``) or the gate will never trip.
    support_gold_csv : gold across ALL types, for m3's containment test. The
        dominant nesting case crosses groups (a definition inside a proof), so
        scoping support to this group's gold would miss exactly what m3 is for.

    Returns the number of rules pruned.
    """
    import importlib.util

    # Resolve the per-rule FDR tolerance (alpha). Explicit max_fdr wins;
    # otherwise fall back to the legacy boolean (0.5 majority / 0.0 aggressive).
    if max_fdr is None:
        max_fdr = 0.5 if require_fp_majority else 0.0
    max_fdr = max(0.0, min(1.0, float(max_fdr)))

    rules_path = os.path.join(eval_dir, 'distilled_rules.py')
    if not os.path.isfile(rules_path):
        print(f"ERROR: No distilled rules file at {rules_path}")
        return 0

    func_name = f'extract_distilled_{structure_type}'

    # 1. Load the distilled-rules module
    spec = importlib.util.spec_from_file_location(
        f'distilled_rules_prune_{structure_type}', rules_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    extract_fn = getattr(mod, func_name, None)
    if extract_fn is None:
        print(f"ERROR: {rules_path} does not define {func_name}()")
        return 0

    # 2. Load gold standard
    gold_data = _load_gold_csv(gold_csv)

    # m3 support set: gold across ALL types, keyed by paper. Falls back to this
    # group's gold when no all-type CSV was supplied, which makes m3 degrade to
    # "nesting within the group" rather than failing.
    support_texts_by_paper: Dict[str, List[str]] = {}
    if match_mode != "m1":
        src = support_gold_csv or gold_csv
        for pid_key, items in _load_gold_csv(src).items():
            support_texts_by_paper[pid_key] = [
                (g.get('raw_latex') or g.get('clean_text') or '')
                for g in items
                if (g.get('raw_latex') or g.get('clean_text') or '').strip()
            ]

    # Default the runaway-regex cap off max_rule_seconds so one knob tunes both.
    if extract_timeout is None:
        extract_timeout = max(30.0, 6.0 * (max_rule_seconds or 10.0))

    # 3. Extract from each paper and classify TP / FP
    all_results: List[tuple] = []  # (paper_id, result_dict, is_tp)

    for paper_id in paper_ids:
        found = _find_local_tex(paper_id, search_dirs=tex_search_dirs)
        if found is None:
            found = _find_local_tex(re.sub(r'v\d+$', '', paper_id),
                                    search_dirs=tex_search_dirs)
        if found is None:
            print(f"  WARNING: TeX not found for {paper_id}, skipping")
            continue

        tex_path, versioned_id = found
        print(f"  Extracting from {paper_id}...")
        text = paper_text(tex_path)

        # Defensive: LLM-generated extract_fn can raise on specific inputs
        # (e.g. a buggy sort key). The parser path already swallows this; mirror
        # it here so one bad codegen degrades the group instead of killing the
        # whole run.
        #
        # try/except is NOT sufficient on its own: a catastrophically
        # backtracking regex does not raise, it spins inside C code where no
        # Python exception handler can reach it. Observed live — one generated
        # pattern burned a core for 12 minutes on a single findall and stalled
        # the entire run with no output and no way to bound it from outside.
        # prune_slow_rules already guards its per-pattern timings with SIGALRM;
        # extract_fn composes those patterns and was left unguarded, so the
        # composed path could hang even when each pattern passed in isolation.
        # Same mechanism, applied where it was missing.
        results = _run_extract_fn_guarded(extract_fn, text, paper_id,
                                          extract_timeout)
        if results is None:
            continue
        extracted_texts = [r.get('raw_latex', '') for r in results]

        # Gold items for this paper
        norm_pid = re.sub(r'v\d+$', '', paper_id).replace('_', '.')
        gold_items = _gold_for_paper(gold_data, paper_id)
        gold_texts = [
            g['raw_latex'] or g['clean_text']
            for g in gold_items
            if (g.get('raw_latex') or g.get('clean_text', '')).strip()
        ]

        # Greedy matching (same logic as validate_rules)
        matched_gold: Set[int] = set()
        matched_ext: Set[int] = set()
        pairs = []
        for ei, ext in enumerate(extracted_texts):
            for gi, gt in enumerate(gold_texts):
                sim = jaccard_similarity(ext, gt)
                if sim >= threshold:
                    pairs.append((sim, ei, gi))
        pairs.sort(reverse=True)
        for sim, ei, gi in pairs:
            if ei not in matched_ext and gi not in matched_gold:
                matched_ext.add(ei)
                matched_gold.add(gi)

        if match_mode == "m1":
            is_tp = [ei in matched_ext for ei in range(len(results))]
        else:
            # m3: also accept anything contained in a gold node of ANY type.
            # Strictly a superset of the m1 verdicts above, so the gate can only
            # loosen — it can never newly condemn a rule m1 accepted.
            import match_modes as _mm
            # Same versioned-id trap as the gold lookup above: this map is keyed
            # by the gold CSV's paper_id, which is versioned for the v5.1 corpus.
            support = (support_texts_by_paper.get(paper_id)
                       or support_texts_by_paper.get(norm_pid)
                       or gold_texts)
            is_tp = [
                (ei in matched_ext) or any(
                    _mm.coverage(_mm.tokens(ext), _mm.tokens(s)) >= cover
                    for s in support)
                for ei, ext in enumerate(extracted_texts)
            ]

        for ei, r in enumerate(results):
            all_results.append((paper_id, r, is_tp[ei]))

    fp_results = [(pid, r) for pid, r, is_tp in all_results if not is_tp]
    tp_results = [(pid, r) for pid, r, is_tp in all_results if is_tp]

    if not fp_results:
        print("\nNo false positives detected. Nothing to prune.")
        # Still record the pass: "the gate ran and cleared everything" is a
        # different fact from "the gate never ran", and the trace needs to be
        # able to tell them apart.
        try:
            with open(os.path.join(eval_dir, "prune_log.jsonl"), "a",
                      encoding="utf-8") as _f:
                _f.write(json.dumps({
                    "structure_type": structure_type,
                    "papers_scored": list(paper_ids),
                    "decisions": [],
                    "note": f"no false positives; {len(tp_results)} TP(s), "
                            f"nothing pruned"}) + "\n")
        except Exception as _e:
            print(f"  [warn] could not write prune_log.jsonl: {_e}")
        return 0

    print(f"\nFound {len(fp_results)} FP(s), {len(tp_results)} TP(s)")

    # 4. Attribute FPs (and TPs) to specific compiled patterns
    fp_by_rule: Dict[str, List[str]] = defaultdict(list)
    tp_by_rule: Dict[str, List[str]] = defaultdict(list)

    has_rule_names = all(r.get('rule_name') for _, r in fp_results)

    if has_rule_names:
        # Fast path — rule_name already in results
        for pid, r in fp_results:
            fp_by_rule[r['rule_name']].append(pid)
        for pid, r in tp_results:
            if r.get('rule_name'):
                tp_by_rule[r['rule_name']].append(pid)
    else:
        # Slow path — attribute by testing each pattern individually
        print("  (rule_name not in results — attributing via pattern matching)")
        patterns: Dict[str, re.Pattern] = {}
        for name in dir(mod):
            obj = getattr(mod, name)
            if (isinstance(obj, re.Pattern)
                    and name.startswith('_')
                    and 'EXCLUDED' not in name.upper()
                    and 'EXCL' not in name.upper()):
                patterns[name] = obj

        # Cache paper texts
        paper_texts: Dict[str, str] = {}
        for paper_id in paper_ids:
            found = _find_local_tex(paper_id, search_dirs=tex_search_dirs)
            if found is None:
                found = _find_local_tex(re.sub(r'v\d+$', '', paper_id),
                                        search_dirs=tex_search_dirs)
            if found:
                paper_texts[paper_id] = paper_text(found[0])

        def _attribute(pid: str, raw: str) -> Optional[str]:
            text = paper_texts.get(pid, '')
            if not text:
                return None
            for pat_name, pat in patterns.items():
                for m in pat.finditer(text):
                    matched = (m.group('full')
                               if 'full' in m.groupdict()
                               else m.group(0))
                    if jaccard_similarity(matched.strip(), raw.strip()) >= threshold:
                        return pat_name
            return None

        for pid, r in fp_results:
            rule = _attribute(pid, r.get('raw_latex', ''))
            if rule:
                fp_by_rule[rule].append(pid)
            else:
                fp_by_rule['<unattributed>'].append(pid)
        for pid, r in tp_results:
            rule = _attribute(pid, r.get('raw_latex', ''))
            if rule:
                tp_by_rule[rule].append(pid)

    # 5. Report
    print(f"\nFP-causing rules:")
    for rule_name, fps in sorted(fp_by_rule.items()):
        tps = tp_by_rule.get(rule_name, [])
        print(f"  {rule_name}: {len(fps)} FP, {len(tps)} TP")
        for pid in sorted(set(fps)):
            print(f"    FP paper: {pid}")

    # 6. Comment out FP-causing rules in the source file
    with open(rules_path, 'r', encoding='utf-8') as f:
        source_lines = f.readlines()

    pruned_count = 0
    kept_count = 0
    decisions = []      # persisted: stdout is otherwise the only record
    for rule_name, fp_papers in fp_by_rule.items():
        if rule_name == '<unattributed>':
            print(f"\n  WARNING: {len(fp_papers)} FP(s) could not be attributed "
                  f"to a specific pattern — skipping")
            continue
        tp_count = len(tp_by_rule.get(rule_name, []))
        fp_count = len(fp_papers)
        fdr = fp_count / (fp_count + tp_count) if (fp_count + tp_count) else 1.0
        decisions.append({
            "rule": rule_name, "fp": fp_count, "tp": tp_count,
            "fdr": round(fdr, 4), "alpha": max_fdr,
            "verdict": "keep" if fdr <= max_fdr else "prune",
            "fp_papers": sorted(set(fp_papers)),
            "n_papers_scored": len(paper_ids),
        })
        if fdr <= max_fdr:
            print(f"  KEEP  {rule_name}: {fp_count} FP, {tp_count} TP "
                  f"(FDR={fdr:.2f} <= alpha={max_fdr:.2f})")
            kept_count += 1
            continue
        unique_papers = sorted(set(fp_papers))
        source_lines, how = _prune_rule_safely(
            source_lines, rule_name, unique_papers, tp_count)
        decisions[-1]["applied"] = how
        if how != "skipped":
            pruned_count += 1

    # Append rather than overwrite: prune runs once per paper, and the history of
    # WHEN a rule died (and on how much evidence) is the interesting part.
    try:
        with open(os.path.join(eval_dir, "prune_log.jsonl"), "a",
                  encoding="utf-8") as _f:
            _f.write(json.dumps({"structure_type": structure_type,
                                 "papers_scored": list(paper_ids),
                                 "decisions": decisions}) + "\n")
    except Exception as _e:
        print(f"  [warn] could not write prune_log.jsonl: {_e}")
    print(f"  (FDR gate alpha={max_fdr:.2f}: kept {kept_count} rule(s) with "
          f"FDR <= alpha)")

    with open(rules_path, 'w', encoding='utf-8') as f:
        f.writelines(source_lines)

    print(f"\nPruned {pruned_count} rule(s) in {rules_path}")
    print("Commented-out rules preserved with '# PRUNED' markers.")

    # 7. Time guard — prune catastrophic-backtracking patterns (slowness, not
    #    FPs). A zero-match overfit regex never trips the FDR gate but can cost
    #    seconds per document, so guard it here over the same paper set.
    if max_rule_seconds is not None and max_rule_seconds > 0:
        guard_texts: Dict[str, str] = {}
        for paper_id in paper_ids:
            found = (_find_local_tex(paper_id, search_dirs=tex_search_dirs)
                     or _find_local_tex(re.sub(r'v\d+$', '', paper_id),
                                        search_dirs=tex_search_dirs))
            if found:
                guard_texts[paper_id] = paper_text(found[0])
        slow = prune_slow_rules(rules_path, guard_texts, max_rule_seconds)
        pruned_count += len(slow)

    return pruned_count


# ---------------------------------------------------------------------------
# CSV I/O helpers
# ---------------------------------------------------------------------------


def _read_items_csv(path: str) -> List[dict]:
    """Read a CSV previously output by dark-knowledge or discovery."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
