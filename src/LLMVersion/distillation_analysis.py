#!/usr/bin/env python3
"""
NtRED Distillation Analysis Pipeline
=====================================
Subcommands:
  dark-knowledge  Identify gold items missed by manual but caught by LLMs
  discovery       Find LLM-consensus structures not in manual extractions
  analyze         Mine LaTeX patterns from missed structures
  validate        Check if manual parser now catches previously missed items
"""

import argparse
import csv
import glob as globmod
import inspect
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import FULL_PAPERS_DIR

# ---------------------------------------------------------------------------
# Shared utilities (reused from evaluate_definitions.py for consistency)
# ---------------------------------------------------------------------------

def normalize_latex(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\\textit\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textbf\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\emph\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\cite\{[^}]+\}', '', text)
    text = re.sub(r'~\\cite\{[^}]+\}', '', text)
    return text.strip().lower()


def tokenize_latex(text):
    if not text:
        return set()
    return set(re.findall(r'\\[a-zA-Z]+|[a-zA-Z]+|[0-9]+|\$|[{}()[\]]', text))


def jaccard_similarity(text1, text2):
    t1 = tokenize_latex(normalize_latex(text1))
    t2 = tokenize_latex(normalize_latex(text2))
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def _find_local_tex(paper_id: str) -> Optional[Tuple[str, str]]:
    """Find local .tex file for paper_id. Returns (tex_path, versioned_id) or None."""
    pattern = os.path.join(FULL_PAPERS_DIR, "**", f"{paper_id}*.tex")
    matches = globmod.glob(pattern, recursive=True)
    if not matches:
        return None
    tex_path = matches[0]
    versioned_id = Path(tex_path).stem
    return tex_path, versioned_id


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
                            threshold: float = 0.7) -> List[dict]:
    """Distillation mode: gold=exists AND manual=FN AND any_LLM=TP.

    Returns list of dicts with:
      paper_id, gold_index, gold_text, found_by_llms, manual_best_similarity
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

            manual_matched = manual_best_sim >= threshold

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

def identify_discovery_candidates(eval_dir: str, structure_type: str,
                                  threshold: float = 0.7) -> List[dict]:
    """Discovery mode: manual=FN AND LLM_agreement >= 2 (no gold needed).

    Returns list of dicts with:
      paper_id, representative_text, providers, cluster_size,
      manual_best_similarity, avg_cluster_similarity
    """
    rows = _load_detailed_matches(eval_dir)
    if not rows:
        print(f"ERROR: No detailed_matches.csv found in {eval_dir}")
        return []

    # Group extractions by (paper_id, provider)
    extractions: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for r in rows:
        text = r.get('definition_text', '').strip()
        if text:
            extractions[(r['paper_id'].strip(), r['provider'].strip())].append(text)

    # Get all paper_ids
    paper_ids = set(pid for pid, _ in extractions)

    candidates = []

    for paper_id in sorted(paper_ids):
        # Gather manual extractions
        manual_texts = extractions.get((paper_id, 'manual'), [])

        # Gather LLM extractions with provider tags
        llm_items = []  # [(provider, text)]
        for llm in sorted(LLM_PROVIDERS):
            for text in extractions.get((paper_id, llm), []):
                llm_items.append((llm, text))

        if not llm_items:
            continue

        # For each LLM extraction, check if manual missed it
        manual_missed = []  # [(provider, text, manual_best_sim)]
        for prov, text in llm_items:
            best_sim = 0.0
            for mt in manual_texts:
                best_sim = max(best_sim, jaccard_similarity(text, mt))
            if best_sim < threshold:
                manual_missed.append((prov, text, best_sim))

        if len(manual_missed) < 2:
            continue  # Need at least 2 LLM extractions manual missed

        # Cluster manual-missed LLM extractions by pairwise Jaccard
        # Greedy: for each item, find best match among existing clusters
        clusters: List[List[Tuple[str, str, float]]] = []  # [[items]]
        for item in manual_missed:
            prov, text, msim = item
            best_cluster = None
            best_csim = 0.0
            for ci, cluster in enumerate(clusters):
                # Check against all items in cluster
                for cprov, ctext, _ in cluster:
                    sim = jaccard_similarity(text, ctext)
                    if sim >= threshold and sim > best_csim:
                        best_csim = sim
                        best_cluster = ci

            if best_cluster is not None:
                clusters[best_cluster].append(item)
            else:
                clusters.append([item])

        # Filter clusters: need 2+ different providers
        for cluster in clusters:
            providers_in_cluster = set(prov for prov, _, _ in cluster)
            if len(providers_in_cluster) < 2:
                continue

            # Compute avg pairwise similarity within cluster
            sims = []
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    sims.append(jaccard_similarity(cluster[i][1], cluster[j][1]))
            avg_sim = sum(sims) / len(sims) if sims else 0.0

            # Pick representative text (from first item)
            rep_text = cluster[0][1]
            manual_best = max(item[2] for item in cluster)

            candidates.append({
                'paper_id': paper_id,
                'representative_text': rep_text[:200] + '...' if len(rep_text) > 200 else rep_text,
                'providers': ','.join(sorted(providers_in_cluster)),
                'cluster_size': len(cluster),
                'manual_best_similarity': f'{manual_best:.3f}',
                'avg_cluster_similarity': f'{avg_sim:.3f}',
            })

    return candidates


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
}


def _read_extraction_method(structure_type: str) -> str:
    """Read the source code of the relevant extraction method from math_paper_parser.py.

    Also includes BASE_ENV_KIND_MAP and _extract_envs as shared context.
    """
    from math_paper_parser import PaperParser

    method_name = STRUCTURE_EXTRACT_METHODS.get(structure_type)
    if not method_name:
        return f"# Unknown structure type: {structure_type}"

    parts = []

    # 1) BASE_ENV_KIND_MAP
    try:
        src_lines = inspect.getsource(PaperParser).split('\n')
        in_map = False
        map_lines = []
        brace_depth = 0
        for line in src_lines:
            if 'BASE_ENV_KIND_MAP' in line and '=' in line and not in_map:
                in_map = True
            if in_map:
                map_lines.append(line)
                brace_depth += line.count('{') - line.count('}')
                if brace_depth <= 0 and len(map_lines) > 1:
                    break
        if map_lines:
            parts.append('\n'.join(map_lines))
    except Exception:
        pass

    # 2) _extract_envs (shared infrastructure)
    try:
        envs_method = getattr(PaperParser, '_extract_envs')
        parts.append(inspect.getsource(envs_method))
    except Exception:
        pass

    # 3) The target extraction method
    try:
        target_method = getattr(PaperParser, method_name)
        parts.append(inspect.getsource(target_method))
    except Exception:
        parts.append(f"# Could not read method {method_name}")

    return '\n\n'.join(parts)


def _call_llm_for_rule(gold_text: str, latex_context: str,
                       extraction_method_source: str, structure_type: str,
                       model: str) -> dict:
    """Call LLM to suggest a concrete regex rule for catching a missed structure.

    Returns {'reasoning': str, 'suggested_code': str} or fallback on error.
    """
    import anthropic

    prompt = f"""You are a Python regex engineer for a LaTeX math structure parser.

## Current extraction method for "{structure_type}"

```python
{extraction_method_source}
```

## Missed structure (gold standard)

The following {structure_type} was NOT extracted by the above code but SHOULD have been:

```
{gold_text[:1500]}
```

## LaTeX source context (where this structure appears in the .tex file)

```latex
{latex_context[:2000]}
```

## Task

Analyze WHY the current extraction method missed this structure, and output the MINIMAL Python code change needed to catch it. This should be one of:
- A new regex pattern to add
- A new environment name to add to BASE_ENV_KIND_MAP
- A new branch or condition in the extraction method
- A new textual marker pattern

Do NOT rewrite the entire method. Output ONLY the minimal addition/change.

Respond with JSON (no markdown fences):
{{"reasoning": "Brief explanation of why current code misses this and what pattern is needed", "suggested_code": "The exact Python code to add or modify (copy-pasteable)"}}"""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()

        # Parse JSON — handle markdown fences if present
        text = response_text
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        parsed = json.loads(text)
        return {
            'reasoning': parsed.get('reasoning', ''),
            'suggested_code': parsed.get('suggested_code', ''),
        }
    except json.JSONDecodeError:
        # Try to salvage partial JSON
        reasoning_m = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', response_text)
        code_m = re.search(r'"suggested_code"\s*:\s*"((?:[^"\\]|\\.)*)"', response_text)
        return {
            'reasoning': reasoning_m.group(1) if reasoning_m else response_text[:500],
            'suggested_code': code_m.group(1) if code_m else '',
        }
    except Exception as e:
        return {
            'reasoning': f'LLM call failed: {e}',
            'suggested_code': '',
        }


def analyze_patterns(items: List[dict], tex_dir: str = None,
                     structure_type: str = None, model: str = None) -> List[dict]:
    """Analyze LaTeX source around missed structures to classify patterns.

    When structure_type and model are provided, uses an LLM to suggest concrete
    regex rules. Otherwise falls back to rule-based classification.

    Parameters
    ----------
    items : list of dicts with at least 'paper_id' and 'gold_text'
    tex_dir : directory to search for .tex files (defaults to FULL_PAPERS_DIR)
    structure_type : e.g. 'proof', 'theorem' — needed for LLM analysis
    model : Anthropic model ID (e.g. 'claude-sonnet-4-20250514')

    Returns list of dicts with:
      paper_id, gold_index, pattern_type, latex_context,
      llm_suggested_rule, llm_reasoning  (when LLM enabled)
      suggested_regex_hint               (when LLM disabled / fallback)
    """
    if tex_dir is None:
        tex_dir = FULL_PAPERS_DIR

    use_llm = structure_type is not None and model is not None
    method_source = None
    if use_llm:
        print(f"Reading extraction method source for '{structure_type}'...")
        method_source = _read_extraction_method(structure_type)
        print(f"  Method source: {len(method_source)} chars")

    results = []
    tex_cache: Dict[str, str] = {}
    llm_call_count = 0

    for item in items:
        paper_id = item['paper_id']
        gold_text = item.get('gold_text', '')
        gold_index = item.get('gold_index', '')

        if not gold_text.strip():
            continue

        # Load TeX source (cached)
        if paper_id not in tex_cache:
            found = _find_local_tex(paper_id)
            if found is None:
                stripped = re.sub(r'v\d+$', '', paper_id)
                found = _find_local_tex(stripped)
            if found:
                try:
                    with open(found[0], 'r', encoding='utf-8', errors='replace') as f:
                        tex_cache[paper_id] = f.read()
                except OSError:
                    tex_cache[paper_id] = ''
            else:
                tex_cache[paper_id] = ''

        tex_source = tex_cache[paper_id]
        if not tex_source:
            row = {
                'paper_id': paper_id,
                'gold_index': gold_index,
                'pattern_type': 'tex_not_found',
                'latex_context': '',
            }
            if use_llm:
                row['llm_reasoning'] = 'TeX source not found'
                row['llm_suggested_rule'] = ''
            else:
                row['suggested_regex_hint'] = ''
            results.append(row)
            continue

        # Find gold text in TeX source via fuzzy matching + rule-based classification
        context, pattern_type, hint = _classify_pattern(gold_text, tex_source)

        row = {
            'paper_id': paper_id,
            'gold_index': gold_index,
            'pattern_type': pattern_type,
            'latex_context': context[:2000] if context else '',
        }

        if use_llm and context:
            # Call LLM for a concrete rule suggestion
            llm_call_count += 1
            print(f"  [{llm_call_count}] LLM analyzing {paper_id} gold_index={gold_index} "
                  f"(rule-based: {pattern_type})...")
            llm_result = _call_llm_for_rule(
                gold_text, context, method_source, structure_type, model)
            row['llm_reasoning'] = llm_result['reasoning']
            row['llm_suggested_rule'] = llm_result['suggested_code']
        elif use_llm:
            row['llm_reasoning'] = f'No context found ({pattern_type})'
            row['llm_suggested_rule'] = ''
        else:
            row['suggested_regex_hint'] = hint

        results.append(row)

    if use_llm:
        print(f"\nTotal LLM calls: {llm_call_count}")

    return results


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
                    f'Add "{env}" to BASE_ENV_KIND_MAP (from \\newtheorem)')

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
                'Inline phrasing — may need broader regex in _extract_definitions_textual')

    # 5) Fallback
    return (context, 'unclassified', 'Manual inspection needed')


# ---------------------------------------------------------------------------
# Function 4: validate_rules
# ---------------------------------------------------------------------------

def validate_rules(paper_ids: List[str], structure_type: str,
                   expected_items: List[dict], threshold: float = 0.7) -> List[dict]:
    """Run manual parser on papers and check if previously missed items are now caught.

    Parameters
    ----------
    paper_ids : list of paper IDs to parse
    structure_type : e.g. 'definition', 'theorem'
    expected_items : list of dicts with 'paper_id' and 'gold_text'
    threshold : Jaccard threshold for match

    Returns list of dicts with:
      paper_id, gold_index, gold_text, status (caught/missed), best_match_sim, best_match_text
    """
    from math_paper_parser import PaperParser

    # Run manual parser on each paper
    parsed: Dict[str, List[str]] = {}  # paper_id -> [extracted texts]

    for paper_id in paper_ids:
        found = _find_local_tex(paper_id)
        if found is None:
            stripped = re.sub(r'v\d+$', '', paper_id)
            found = _find_local_tex(stripped)
        if found is None:
            print(f"  WARNING: TeX not found for {paper_id}, skipping")
            parsed[paper_id] = []
            continue

        tex_path, versioned_id = found
        print(f"  Parsing {paper_id} ({tex_path})...")
        try:
            parser = PaperParser(
                paper_id=versioned_id,
                definition_mode='manual',
                structure_types=[structure_type],
            )
            graph = parser.parse_file(tex_path)
            graph_dict = graph.to_dict()

            # objects is {obj_id: {kind, raw_latex, statement, ...}}
            texts = []
            for obj_id, obj in graph_dict.get('objects', {}).items():
                if obj.get('kind') != structure_type:
                    continue
                raw = obj.get('raw_latex', '') or obj.get('statement', '')
                if raw.strip():
                    texts.append(raw)
            parsed[paper_id] = texts
            print(f"    Extracted {len(texts)} {structure_type}(s)")
        except Exception as e:
            print(f"    ERROR parsing {paper_id}: {e}")
            parsed[paper_id] = []

    # Check each expected item
    results = []
    caught_count = 0

    for item in expected_items:
        paper_id = item['paper_id']
        gold_text = item.get('gold_text', '')
        gold_index = item.get('gold_index', '')
        extracted = parsed.get(paper_id, [])

        best_sim = 0.0
        best_text = ''
        for ext in extracted:
            sim = jaccard_similarity(ext, gold_text)
            if sim > best_sim:
                best_sim = sim
                best_text = ext

        status = 'caught' if best_sim >= threshold else 'missed'
        if status == 'caught':
            caught_count += 1

        results.append({
            'paper_id': paper_id,
            'gold_index': gold_index,
            'gold_text': gold_text,
            'status': status,
            'best_match_similarity': f'{best_sim:.3f}',
            'best_match_text': best_text,
        })

    total = len(expected_items)
    print(f"\nValidation: {caught_count}/{total} previously-missed items now caught "
          f"({caught_count/total*100:.1f}%)" if total else "No items to validate")

    return results


# ---------------------------------------------------------------------------
# CSV I/O helpers
# ---------------------------------------------------------------------------

def _write_csv(rows: List[dict], path: str) -> None:
    if not rows:
        print(f"No results to write to {path}")
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def _read_items_csv(path: str) -> List[dict]:
    """Read a CSV previously output by dark-knowledge or discovery."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='NtRED Distillation Analysis Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest='command')

    # -- dark-knowledge --
    dk = sub.add_parser('dark-knowledge',
                        help='Identify gold items missed by manual but caught by LLMs')
    dk.add_argument('--eval-dir', required=True, help='Directory with detailed_matches.csv')
    dk.add_argument('--gold-csv', required=True, help='Gold standard CSV (e.g. Gold_Standard_Theorems.csv)')
    dk.add_argument('--structure-type', required=True, help='Structure type (e.g. theorem)')
    dk.add_argument('--threshold', type=float, default=0.7, help='Jaccard match threshold (default: 0.7)')
    dk.add_argument('--output', default=None, help='Output CSV path (default: <eval-dir>/dark_knowledge.csv)')

    # -- discovery --
    disc = sub.add_parser('discovery',
                          help='Find LLM-consensus structures not in manual extractions')
    disc.add_argument('--eval-dir', required=True, help='Directory with detailed_matches.csv')
    disc.add_argument('--structure-type', required=True, help='Structure type')
    disc.add_argument('--threshold', type=float, default=0.7, help='Jaccard threshold (default: 0.7)')
    disc.add_argument('--output', default=None, help='Output CSV path')

    # -- analyze --
    ana = sub.add_parser('analyze',
                         help='Mine LaTeX patterns from missed structures')
    ana.add_argument('--input', required=True,
                     help='CSV from dark-knowledge or discovery (needs paper_id + gold_text columns)')
    ana.add_argument('--structure-type', required=True,
                     help='Structure type (e.g. proof, theorem) — determines which extraction method to show LLM')
    ana.add_argument('--model', default='claude-sonnet-4-20250514',
                     help='Anthropic model for LLM analysis (default: claude-sonnet-4-20250514)')
    ana.add_argument('--tex-dir', default=None, help=f'TeX directory (default: {FULL_PAPERS_DIR})')
    ana.add_argument('--output', default=None, help='Output CSV path')

    # -- validate --
    val = sub.add_parser('validate',
                         help='Check if manual parser now catches previously missed items')
    val.add_argument('--paper-ids', required=True, help='Comma-separated paper IDs')
    val.add_argument('--structure-type', required=True, help='Structure type')
    val.add_argument('--expected', required=True,
                     help='CSV of expected items (from dark-knowledge output)')
    val.add_argument('--threshold', type=float, default=0.7, help='Jaccard threshold')
    val.add_argument('--output', default=None, help='Output CSV path')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == 'dark-knowledge':
        items = identify_dark_knowledge(
            args.eval_dir, args.gold_csv, args.structure_type, args.threshold)
        out = args.output or os.path.join(args.eval_dir, 'dark_knowledge.csv')

        # Print summary
        print(f"\n{'='*60}")
        print(f"DARK KNOWLEDGE SUMMARY ({args.structure_type})")
        print(f"{'='*60}")
        print(f"Total items: {len(items)}")
        if items:
            llm_counts = defaultdict(int)
            for it in items:
                for llm in it['found_by_llms'].split(','):
                    llm_counts[llm] += 1
            for llm, cnt in sorted(llm_counts.items()):
                print(f"  Found by {llm}: {cnt}")
            papers = set(it['paper_id'] for it in items)
            print(f"  Across {len(papers)} paper(s): {', '.join(sorted(papers))}")

        _write_csv(items, out)

    elif args.command == 'discovery':
        items = identify_discovery_candidates(
            args.eval_dir, args.structure_type, args.threshold)
        out = args.output or os.path.join(args.eval_dir, 'discovery_candidates.csv')

        print(f"\n{'='*60}")
        print(f"DISCOVERY CANDIDATES SUMMARY ({args.structure_type})")
        print(f"{'='*60}")
        print(f"Total candidates: {len(items)}")
        if items:
            papers = set(it['paper_id'] for it in items)
            print(f"  Across {len(papers)} paper(s)")
            for it in items:
                print(f"  [{it['paper_id']}] providers={it['providers']} "
                      f"sim={it['avg_cluster_similarity']} "
                      f"manual_best={it['manual_best_similarity']}")

        _write_csv(items, out)

    elif args.command == 'analyze':
        items = _read_items_csv(args.input)
        results = analyze_patterns(
            items, args.tex_dir,
            structure_type=args.structure_type,
            model=args.model,
        )
        out = args.output or args.input.replace('.csv', '_patterns.csv')

        print(f"\n{'='*60}")
        print(f"PATTERN ANALYSIS SUMMARY ({args.structure_type})")
        print(f"{'='*60}")
        type_counts = defaultdict(int)
        for r in results:
            type_counts[r['pattern_type']] += 1
        for ptype, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  {ptype}: {cnt}")
        llm_populated = sum(1 for r in results if r.get('llm_suggested_rule', '').strip())
        print(f"  LLM suggestions with code: {llm_populated}/{len(results)}")

        _write_csv(results, out)

    elif args.command == 'validate':
        paper_ids = [p.strip() for p in args.paper_ids.split(',')]
        expected_items = _read_items_csv(args.expected)
        results = validate_rules(paper_ids, args.structure_type, expected_items, args.threshold)
        out = args.output or args.expected.replace('.csv', '_validation.csv')

        caught = sum(1 for r in results if r['status'] == 'caught')
        total = len(results)
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY ({args.structure_type})")
        print(f"{'='*60}")
        print(f"Caught: {caught}/{total} ({caught/total*100:.1f}%)" if total else "No items")

        _write_csv(results, out)


if __name__ == '__main__':
    main()
