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


# Built-in index of well-known mathematical results (fallback if no foundation JSON)
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


def build_foundation_index(foundation_path):
    """Build a name index from a NaturalProofs JSON file."""
    index = dict(WELL_KNOWN)  # start with built-in

    if foundation_path and Path(foundation_path).exists():
        with open(foundation_path) as f:
            data = json.load(f)

        # NaturalProofs format: {"dataset": [...items...]}
        items = data if isinstance(data, list) else data.get("dataset", data.get("theorems", []))
        for item in items:
            title = item.get("title", "")
            if title and len(title) >= 5:
                key = title.strip().lower()
                index[key] = {
                    "name": title,
                    "id": item.get("id", ""),
                    "field": item.get("categories", [""])[0] if item.get("categories") else "",
                    "source": "naturalproofs",
                }
        print(f"Loaded {len(items)} entries from {foundation_path}")

    print(f"Index has {len(index)} searchable terms")
    return index


def link_paper(nodes, index, min_term_len=5):
    """Find matches between paper nodes and foundation index."""
    matches = []

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
        if not search_text:
            continue

        node_matches = []
        for term, entry in index.items():
            if len(term) < min_term_len:
                continue
            # Use regex for terms with special chars
            if re.search(r'\b' + re.escape(term) if not any(c in term for c in '.*+?') else term,
                         search_text):
                node_matches.append({
                    "node_id": node["id"],
                    "node_type": node.get("type", ""),
                    "node_name": node.get("name", ""),
                    "matched_term": term,
                    "foundation_name": entry["name"],
                    "foundation_field": entry.get("field", ""),
                })

        matches.extend(node_matches)

    return matches


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
