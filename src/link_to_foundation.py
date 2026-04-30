#!/usr/bin/env python3
"""Link extracted chapter/paper JSONs to a foundation knowledge graph.

Usage:
    python link_to_foundation.py \
        --paper-json chapter2_extracted.json \
        --foundation-json naturalproofs_stacks.json \
        --output linked_chapter2.json

For each node in the paper JSON, searches for known theorem/definition names
from the foundation data. Reports matches and optionally adds grounded_to edges.

Works directly on student-format JSONs (nodes + edges), no PaperGraph needed.
Can also use a simple built-in index of well-known results if no foundation
JSON is available.
"""
import json
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict


# Built-in index of well-known mathematical results (fallback if no foundation JSON).
# These are single-word or abbreviation entries that wouldn't survive the
# ≥2-word filter in the clean foundation index.
WELL_KNOWN = {
    "markov": {"name": "Markov's Inequality", "field": "probability"},
    "chebyshev": {"name": "Chebyshev's Inequality", "field": "probability"},
    "chernoff": {"name": "Chernoff Bound", "field": "probability"},
    "hoeffding": {"name": "Hoeffding's Inequality", "field": "probability"},
    "cauchy-schwarz": {"name": "Cauchy-Schwarz Inequality", "field": "linear algebra"},
    "cauchy schwarz": {"name": "Cauchy-Schwarz Inequality", "field": "linear algebra"},
    "johnson-lindenstrauss": {"name": "Johnson-Lindenstrauss Lemma", "field": "dimensionality reduction"},
    "johnson lindenstrauss": {"name": "Johnson-Lindenstrauss Lemma", "field": "dimensionality reduction"},
    "singular value decomposition": {"name": "SVD", "field": "linear algebra"},
    "spectral theorem": {"name": "Spectral Theorem", "field": "linear algebra"},
    "law of large numbers": {"name": "Law of Large Numbers", "field": "probability"},
    "central limit theorem": {"name": "Central Limit Theorem", "field": "probability"},
    "bayes": {"name": "Bayes' Rule", "field": "probability"},
    "perceptron": {"name": "Perceptron Algorithm", "field": "machine learning"},
    "vc dimension": {"name": "VC Dimension", "field": "learning theory"},
    "vc-dimension": {"name": "VC Dimension", "field": "learning theory"},
    "vapnik-chervonenkis": {"name": "VC Dimension", "field": "learning theory"},
    "pagerank": {"name": "PageRank", "field": "graph theory"},
    "metropolis": {"name": "Metropolis-Hastings", "field": "MCMC"},
    "gibbs sampling": {"name": "Gibbs Sampling", "field": "MCMC"},
    "erdos-renyi": {"name": "Erdos-Renyi Model", "field": "random graphs"},
    "erdos renyi": {"name": "Erdos-Renyi Model", "field": "random graphs"},
    "ramsey": {"name": "Ramsey Theory", "field": "combinatorics"},
    "stirling": {"name": "Stirling's Approximation", "field": "analysis"},
    "jensen": {"name": "Jensen's Inequality", "field": "analysis"},
    "holder": {"name": "Holder's Inequality", "field": "analysis"},
    "young": {"name": "Young's Inequality", "field": "analysis"},
    "triangle inequality": {"name": "Triangle Inequality", "field": "analysis"},
    "arithmetic.*geometric": {"name": "AM-GM Inequality", "field": "analysis"},
    "sauer": {"name": "Sauer's Lemma", "field": "learning theory"},
    "occam": {"name": "Occam's Razor", "field": "learning theory"},
    "boosting": {"name": "Boosting", "field": "machine learning"},
    "lloyd": {"name": "Lloyd's Algorithm", "field": "clustering"},
    "k-means": {"name": "k-Means Clustering", "field": "clustering"},
    "laplacian": {"name": "Graph Laplacian", "field": "spectral graph theory"},
    "viterbi": {"name": "Viterbi Algorithm", "field": "HMMs"},
    "baum-welch": {"name": "Baum-Welch Algorithm", "field": "HMMs"},
    "belief propagation": {"name": "Belief Propagation", "field": "graphical models"},
    "compressed sensing": {"name": "Compressed Sensing", "field": "signal processing"},
    "haar wavelet": {"name": "Haar Wavelet", "field": "wavelets"},
    "fourier": {"name": "Fourier Transform", "field": "analysis"},
    "gamma function": {"name": "Gamma Function", "field": "analysis"},
    "max-cut": {"name": "Max-Cut Problem", "field": "optimization"},
    "goemans-williamson": {"name": "Goemans-Williamson Algorithm", "field": "approximation"},
    "ellipsoid": {"name": "Ellipsoid Algorithm", "field": "optimization"},
    "count-min": {"name": "Count-Min Sketch", "field": "streaming"},
    "non-negative matrix factorization": {"name": "NMF", "field": "linear algebra"},
    "dirichlet": {"name": "Dirichlet Distribution", "field": "probability"},
    "latent dirichlet": {"name": "LDA (Latent Dirichlet Allocation)", "field": "topic models"},
    "hidden markov": {"name": "Hidden Markov Model", "field": "sequence models"},
    "radon": {"name": "Radon's Theorem", "field": "geometry"},
    "cayley": {"name": "Cayley's Formula", "field": "graph theory"},
    "prufer": {"name": "Prufer Sequence", "field": "graph theory"},
}

# Abbreviation aliases: map common abbreviations to their full foundation names.
# These are added to the index so that papers using "CLT" match "Central Limit Theorem".
ALIASES = {
    "clt": {"name": "Central Limit Theorem", "field": "probability"},
    "lln": {"name": "Law of Large Numbers", "field": "probability"},
    "slln": {"name": "Strong Law of Large Numbers", "field": "probability"},
    "wlln": {"name": "Weak Law of Large Numbers", "field": "probability"},
    "svd": {"name": "Singular Value Decomposition", "field": "linear algebra"},
    "nmf": {"name": "Non-Negative Matrix Factorization", "field": "linear algebra"},
    "nnmf": {"name": "Non-Negative Matrix Factorization", "field": "linear algebra"},
    "am-gm": {"name": "AM-GM Inequality", "field": "analysis"},
    "am gm": {"name": "AM-GM Inequality", "field": "analysis"},
    "lda": {"name": "Latent Dirichlet Allocation", "field": "topic models"},
    "hmm": {"name": "Hidden Markov Model", "field": "sequence models"},
    "hmms": {"name": "Hidden Markov Model", "field": "sequence models"},
    "pca": {"name": "Principal Component Analysis", "field": "linear algebra"},
    "iff": {"name": "If and Only If", "field": "logic"},
    "wlog": {"name": "Without Loss of Generality", "field": "logic"},
    "rhs": {"name": "Right-Hand Side", "field": "general"},
    "lhs": {"name": "Left-Hand Side", "field": "general"},
    "ode": {"name": "Ordinary Differential Equation", "field": "analysis"},
    "pde": {"name": "Partial Differential Equation", "field": "analysis"},
    "iid": {"name": "Independent and Identically Distributed", "field": "probability"},
    "i.i.d": {"name": "Independent and Identically Distributed", "field": "probability"},
    "mgf": {"name": "Moment Generating Function", "field": "probability"},
    "pdf": {"name": "Probability Density Function", "field": "probability"},
    "cdf": {"name": "Cumulative Distribution Function", "field": "probability"},
    "dag": {"name": "Directed Acyclic Graph", "field": "graph theory"},
    "bfs": {"name": "Breadth-First Search", "field": "algorithms"},
    "dfs": {"name": "Depth-First Search", "field": "algorithms"},
    "mle": {"name": "Maximum Likelihood Estimation", "field": "statistics"},
    "map estimate": {"name": "Maximum a Posteriori Estimation", "field": "statistics"},
    "kl divergence": {"name": "Kullback-Leibler Divergence", "field": "information theory"},
    "em algorithm": {"name": "Expectation-Maximization Algorithm", "field": "statistics"},
}


def build_foundation_index(foundation_paths=None):
    """Build a name index from foundation data.

    Args:
        foundation_paths: single path (str), list of paths, or None.
            If a path points to clean_foundation.json (from clean_foundation.py),
            loads the pre-built index directly. Otherwise parses raw NaturalProofs.
            If None, only the built-in WELL_KNOWN dict (53 terms) is used.

    Handles three formats:
        - Clean foundation: {"index": {"term": {"name": ...}, ...}}
        - Flat list: {"dataset": [{"title": ...}, ...]}
        - Nested dict: {"dataset": {"theorems": [...], "definitions": [...], "others": [...]}}
    """
    index = dict(WELL_KNOWN)  # start with built-in
    index.update(ALIASES)     # add abbreviation aliases

    if foundation_paths is None:
        foundation_paths = []
    elif isinstance(foundation_paths, (str, Path)):
        foundation_paths = [foundation_paths]

    for fp in foundation_paths:
        fp = Path(fp)
        if not fp.exists():
            print(f"[link] WARNING: foundation file not found: {fp}")
            continue

        with open(fp) as f:
            data = json.load(f)

        # Check if this is a clean_foundation.json (pre-built index)
        if "index" in data and isinstance(data["index"], dict):
            clean_index = data["index"]
            n_added = 0
            for key, entry in clean_index.items():
                if key not in index:
                    index[key] = entry
                    n_added += 1
            print(f"[link] Loaded {n_added} terms from clean index {fp.name} "
                  f"({len(clean_index)} entries)")
            continue

        # Raw NaturalProofs format
        ds = data if isinstance(data, list) else data.get("dataset", data.get("theorems", []))

        items = []
        if isinstance(ds, list):
            items = ds
        elif isinstance(ds, dict):
            for category_name, category_items in ds.items():
                if isinstance(category_items, list):
                    items.extend(category_items)

        n_added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("name", "")
            if not title or len(title) < 5:
                continue

            # Normalize: strip leading articles, possessives, for deduplication
            key = title.strip().lower()
            for prefix in ("the ", "a ", "an ", "definition:", "definition: "):
                if key.startswith(prefix):
                    key = key[len(prefix):]
                    break
            key = re.sub(r"'s\b", "", key)
            key = key.strip()

            # Skip single-word terms after normalization
            words = [w for w in key.split() if len(w) > 2]
            if len(words) < 2:
                continue

            if key not in index:
                index[key] = {
                    "name": title,
                    "id": item.get("id", ""),
                    "type": item.get("type", ""),
                    "field": item.get("categories", [""])[0] if item.get("categories") else "",
                    "source": str(fp.stem),
                }
                n_added += 1
        print(f"[link] Loaded {n_added} terms from {fp.name} ({len(items)} items total)")

    print(f"[link] Index has {len(index)} searchable terms")
    return index


def _build_automaton(index, min_term_len=5):
    """Build an Aho-Corasick automaton from the foundation index.

    Returns (automaton, term_to_entry_map) or (None, None) if pyahocorasick
    is not installed (falls back to slow per-term regex in link_paper).
    """
    try:
        import ahocorasick
    except ImportError:
        return None, None

    A = ahocorasick.Automaton()
    term_map = {}  # normalized_term -> entry
    for term, entry in index.items():
        if len(term) < min_term_len:
            continue
        A.add_word(term, term)
        term_map[term] = entry
        # Also add hyphen↔space variant so "cauchy-schwarz" matches "cauchy schwarz"
        if '-' in term:
            alt = term.replace('-', ' ')
            if alt not in term_map:
                A.add_word(alt, alt)
                term_map[alt] = entry
        elif ' ' in term:
            alt = term.replace(' ', '-')
            if alt not in term_map:
                A.add_word(alt, alt)
                term_map[alt] = entry
    A.make_automaton()
    return A, term_map


def link_paper(nodes, index, min_term_len=5, automaton=None, term_map=None):
    """Find matches between paper nodes and foundation index.

    If automaton + term_map are provided (from _build_automaton), uses
    Aho-Corasick for O(text_length) matching across all terms simultaneously.
    Otherwise falls back to O(n_terms × text_length) per-term regex search.
    """
    matches = []
    use_ac = automaton is not None and term_map is not None

    for node in nodes:
        # Build searchable text
        texts = []
        for field in ["name", "statement", "clean_text"]:
            if node.get(field):
                texts.append(str(node[field]))
        for field in ["assumptions", "conclusions"]:
            if node.get(field):
                texts.extend([str(x) for x in node[field]])

        search_text = " ".join(texts).lower()
        # Normalize search text to match index conventions:
        # 1. Strip possessives ("Markov's" → "markov")
        search_text = re.sub(r"['']s\b", "", search_text)
        # 2. Strip common LaTeX commands (keep the content)
        search_text = re.sub(r'\\(?:mathrm|mathbb|mathcal|operatorname|text|textit|textbf|emph)\s*\{([^}]*)\}', r'\1', search_text)
        search_text = re.sub(r'\\(?:cite|ref|label|eqref)\s*\{[^}]*\}', ' ', search_text)
        search_text = re.sub(r'\\[a-zA-Z]+', ' ', search_text)  # remaining commands
        search_text = re.sub(r'[{}$\\]', ' ', search_text)       # braces and dollar signs
        # 3. Normalize hyphens: add space-variant so "cauchy-schwarz" also matches "cauchy schwarz"
        #    We expand "x-y" to "x-y x y" so both forms are searchable
        hyphenated = re.findall(r'\b(\w+(?:-\w+)+)\b', search_text)
        for h in hyphenated:
            search_text += " " + h.replace("-", " ")
        # 4. Collapse whitespace
        search_text = re.sub(r'\s+', ' ', search_text).strip()
        if not search_text:
            continue

        node_matches = []

        if use_ac:
            # Single-pass Aho-Corasick: find all matching terms at once
            seen_terms = set()
            for end_pos, term in automaton.iter(search_text):
                if term in seen_terms:
                    continue
                # Word-boundary check: ensure we matched a whole word/phrase,
                # not a substring (e.g., "stein" inside "einstein")
                start_pos = end_pos - len(term) + 1
                if start_pos > 0 and search_text[start_pos - 1].isalnum():
                    continue  # not a word boundary on the left
                if end_pos + 1 < len(search_text) and search_text[end_pos + 1].isalnum():
                    continue  # not a word boundary on the right
                seen_terms.add(term)
                entry = term_map[term]
                node_matches.append({
                    "node_id": node["id"],
                    "node_type": node.get("type", ""),
                    "node_name": node.get("name", ""),
                    "matched_term": term,
                    "foundation_name": entry["name"],
                    "foundation_field": entry.get("field", ""),
                    "foundation_source": entry.get("source", ""),
                    "foundation_book_label": entry.get("book_label", ""),
                })
        else:
            # Fallback: per-term regex search (slow for large indices)
            for term, entry in index.items():
                if len(term) < min_term_len:
                    continue
                # Use word boundaries for literal terms; regex terms (.*+?) used as-is
                if any(c in term for c in '.*+?'):
                    pattern = term
                else:
                    pattern = r'\b' + re.escape(term) + r'\b'
                if re.search(pattern, search_text):
                    node_matches.append({
                        "node_id": node["id"],
                        "node_type": node.get("type", ""),
                        "node_name": node.get("name", ""),
                        "matched_term": term,
                        "foundation_name": entry["name"],
                        "foundation_field": entry.get("field", ""),
                        "foundation_source": entry.get("source", ""),
                        "foundation_book_label": entry.get("book_label", ""),
                    })

        matches.extend(node_matches)

    return matches


def compute_idf(all_matches, n_papers):
    """Compute IDF (inverse document frequency) for each foundation term.

    Args:
        all_matches: list of match dicts from link_paper, across all papers.
            Each has 'node_id' and 'foundation_name'.
        n_papers: total number of papers in the corpus.

    Returns:
        dict: foundation_name -> {"df": int, "df_frac": float, "idf": float}
        where df = number of papers containing the term,
        df_frac = df/n_papers, idf = log(n_papers/df).
    """
    import math

    # Group matches by paper (use node_id prefix as paper identifier)
    # In practice, caller should pass per-paper match lists; here we use
    # a simpler approach: each unique (paper_file, foundation_name) pair counts once.
    # Since we don't have paper_file in matches, we rely on the caller.
    # This function takes paper_term_counts: {term: set_of_paper_indices}.

    term_papers = defaultdict(set)
    for m in all_matches:
        paper_id = m.get("_paper_idx", m.get("node_id", "").split("_")[0])
        term_papers[m["foundation_name"]].add(paper_id)

    idf = {}
    for term, papers in term_papers.items():
        df = len(papers)
        idf[term] = {
            "df": df,
            "df_frac": df / n_papers if n_papers > 0 else 0,
            "idf": math.log(n_papers / df) if df > 0 and n_papers > 0 else 0,
        }
    return idf


def filter_by_idf(matches, idf_scores, max_df_frac=0.10):
    """Remove matches for terms that appear in too many papers.

    Args:
        matches: list of match dicts from link_paper.
        idf_scores: output of compute_idf.
        max_df_frac: maximum document frequency fraction (default 10%).
            Terms matching more than this fraction of papers are dropped.

    Returns:
        (kept_matches, dropped_terms): kept matches and set of dropped term names.
    """
    dropped_terms = {
        term for term, scores in idf_scores.items()
        if scores["df_frac"] > max_df_frac
    }
    kept = [m for m in matches if m["foundation_name"] not in dropped_terms]
    return kept, dropped_terms


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paper-json", required=True, help="Paper/chapter JSON")
    parser.add_argument("--foundation-json", default=None,
                        help="NaturalProofs JSON (optional; built-in index used if omitted)")
    parser.add_argument("--output", default=None, help="Output JSON with grounded_to edges")
    parser.add_argument("--min-term-len", type=int, default=5)
    args = parser.parse_args()

    # Load paper
    with open(args.paper_json) as f:
        data = json.load(f)
    nodes = data.get("nodes", [])

    # Build index
    index = build_foundation_index(args.foundation_json)

    # Link
    matches = link_paper(nodes, index, min_term_len=args.min_term_len)

    # Report
    print(f"\n{'='*60}")
    print(f"Found {len(matches)} matches across {len(set(m['node_id'] for m in matches))} nodes")
    print(f"{'='*60}")

    # Group by node
    by_node = defaultdict(list)
    for m in matches:
        by_node[m["node_id"]].append(m)

    for node_id, node_matches in sorted(by_node.items()):
        node_name = node_matches[0]["node_name"] or node_id
        node_type = node_matches[0]["node_type"]
        foundations = [f"{m['foundation_name']} ({m['foundation_field']})" for m in node_matches]
        print(f"  {node_id} ({node_type}): {node_name}")
        for f_name in foundations:
            print(f"    -> {f_name}")

    # Optionally add edges to output
    if args.output:
        new_edges = []
        seen = set()
        for m in matches:
            key = (m["node_id"], m["foundation_name"])
            if key not in seen:
                new_edges.append({
                    "source": m["node_id"],
                    "target": f"FG:{m['foundation_name']}",
                    "type": "grounded_to",
                    "note": f"matched term: '{m['matched_term']}', field: {m['foundation_field']}"
                })
                seen.add(key)

        data["edges"].extend(new_edges)
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to {args.output} with {len(new_edges)} new grounded_to edges")


if __name__ == "__main__":
    main()
