#!/usr/bin/env python3
"""Cross-paper analysis: foundation fingerprinting, clustering, and hidden connections.

Part A (no citations needed): cluster papers by foundation term usage.
Part B (needs citations): find similar-but-uncited paper pairs.

Usage:
    # Part A only (clustering):
    python scripts/cross_paper_analysis.py --out-dir /path/to/parsed_papers

    # Part B (with citations from Semantic Scholar):
    python scripts/cross_paper_analysis.py --out-dir /path/to/parsed_papers --fetch-citations

    # Part B with cached citations:
    python scripts/cross_paper_analysis.py --out-dir /path/to/parsed_papers --citations-json citations.json
"""
import json
import glob
import sys
import argparse
import time
import math
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np


def load_foundation_edges(out_dir):
    """Load foundation edges from all paper JSONs. Returns {arxiv_id: {term: idf_weight}}."""
    papers = {}
    for jp in sorted(glob.glob(str(Path(out_dir) / "**" / "*_manual.json"), recursive=True)):
        arxiv_id = Path(jp).stem.replace("_manual", "")
        terms = {}
        with open(jp) as f:
            data = json.load(f)
        for e in data.get("edges", []):
            if e.get("type") == "grounded_to":
                fname = e.get("source", "")
                is_generic = e.get("generic", False)
                idf = e.get("idf", 1.0)
                if fname and not is_generic:
                    # Use max IDF if same term matched multiple nodes
                    terms[fname] = max(terms.get(fname, 0), idf)
        if terms:
            papers[arxiv_id] = terms
    return papers


def build_tfidf_matrix(papers):
    """Build paper × term TF-IDF matrix.

    Returns (matrix, paper_ids, term_names).
    """
    # Collect all terms
    all_terms = sorted(set(t for terms in papers.values() for t in terms))
    term_idx = {t: i for i, t in enumerate(all_terms)}
    paper_ids = sorted(papers.keys())

    mat = np.zeros((len(paper_ids), len(all_terms)))
    for i, pid in enumerate(paper_ids):
        for term, idf in papers[pid].items():
            j = term_idx[term]
            mat[i, j] = idf  # already IDF-weighted

    # L2-normalize rows for cosine similarity
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1
    mat_normed = mat / norms

    return mat, mat_normed, paper_ids, all_terms


def cluster_papers(mat_normed, paper_ids, n_clusters=8):
    """Cluster papers by foundation fingerprint using k-means."""
    try:
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
    except ImportError:
        print("  [skip] sklearn not installed, skipping clustering")
        return None

    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(mat_normed)
    return labels


def find_top_terms_per_cluster(mat, labels, paper_ids, all_terms, top_k=10):
    """Find the most characteristic terms for each cluster."""
    n_clusters = max(labels) + 1
    cluster_profiles = []
    for c in range(n_clusters):
        mask = labels == c
        n_papers = mask.sum()
        if n_papers == 0:
            cluster_profiles.append([])
            continue
        # Mean TF-IDF vector for this cluster
        mean_vec = mat[mask].mean(axis=0)
        # Top terms by mean weight
        top_idx = np.argsort(mean_vec)[::-1][:top_k]
        top = [(all_terms[j], mean_vec[j], (mat[mask, j] > 0).sum()) for j in top_idx if mean_vec[j] > 0]
        cluster_profiles.append(top)
    return cluster_profiles


def compute_similarities(papers, paper_ids, top_k=50, min_shared=3):
    """Compute top-k most similar paper pairs by shared foundation terms.

    Ranks by number of shared terms (weighted by IDF), filtering out
    trivial pairs that share fewer than min_shared terms.
    """
    # Build sets for fast intersection
    paper_termsets = {pid: set(papers[pid].keys()) for pid in paper_ids}

    pairs = []
    n = len(paper_ids)
    for i in range(n):
        for j in range(i + 1, n):
            pid_a, pid_b = paper_ids[i], paper_ids[j]
            shared = paper_termsets[pid_a] & paper_termsets[pid_b]
            n_shared = len(shared)
            if n_shared < min_shared:
                continue
            # Jaccard similarity
            union = paper_termsets[pid_a] | paper_termsets[pid_b]
            jaccard = n_shared / len(union) if union else 0
            # IDF-weighted overlap: sum of IDF for shared terms
            idf_sum = sum(min(papers[pid_a].get(t, 0), papers[pid_b].get(t, 0))
                          for t in shared)
            pairs.append((pid_a, pid_b, n_shared, jaccard, idf_sum, sorted(shared)))

    # Sort by number of shared terms (primary), then IDF sum (secondary)
    pairs.sort(key=lambda x: (-x[2], -x[4]))
    return pairs[:top_k]


def fetch_citations_s2(paper_ids, output_path=None, api_key=None):
    """Fetch citation data from Semantic Scholar API.

    Returns {arxiv_id: {"references": [arxiv_ids], "citations": [arxiv_ids]}}.
    """
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print("ERROR: urllib not available")
        return {}

    citations = {}
    n = len(paper_ids)
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    for i, pid in enumerate(paper_ids):
        if i % 50 == 0:
            print(f"  Fetching citations: {i}/{n}...")

        url = (f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{pid}"
               f"?fields=externalIds,references.externalIds,citations.externalIds")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            refs = set()
            for r in data.get("references", []) or []:
                ext = (r or {}).get("externalIds", {}) or {}
                if ext.get("ArXiv"):
                    refs.add(ext["ArXiv"])
            cits = set()
            for c in data.get("citations", []) or []:
                ext = (c or {}).get("externalIds", {}) or {}
                if ext.get("ArXiv"):
                    cits.add(ext["ArXiv"])

            citations[pid] = {
                "references": sorted(refs),
                "citations": sorted(cits),
            }
        except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
            # Rate limit or not found
            if "429" in str(e):
                print(f"  Rate limited at {i}, sleeping 60s...")
                time.sleep(60)
                i -= 1  # retry
                continue
            citations[pid] = {"references": [], "citations": []}

        # Rate limiting: 1 request per second without API key
        if not api_key:
            time.sleep(1.1)
        else:
            time.sleep(0.05)

    if output_path:
        with open(output_path, "w") as f:
            json.dump(citations, f, indent=2)
        print(f"  Saved citations to {output_path}")

    return citations


def find_hidden_connections(similar_pairs, citations, top_k=30):
    """Find paper pairs that are similar but don't cite each other."""
    hidden = []
    for tup in similar_pairs:
        pid_a, pid_b = tup[0], tup[1]
        # Check if A cites B or B cites A
        refs_a = set(citations.get(pid_a, {}).get("references", []))
        refs_b = set(citations.get(pid_b, {}).get("references", []))
        cits_a = set(citations.get(pid_a, {}).get("citations", []))
        cits_b = set(citations.get(pid_b, {}).get("citations", []))

        a_cites_b = pid_b in refs_a or pid_b in cits_a
        b_cites_a = pid_a in refs_b or pid_a in cits_b

        if not a_cites_b and not b_cites_a:
            hidden.append(tup)
        if len(hidden) >= top_k:
            break
    return hidden


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True, help="Directory with extracted paper JSONs")
    parser.add_argument("--fetch-citations", action="store_true",
                        help="Fetch citation data from Semantic Scholar API")
    parser.add_argument("--citations-json", default=None,
                        help="Pre-fetched citations JSON (skip API calls)")
    parser.add_argument("--s2-api-key", default=None, help="Semantic Scholar API key (faster)")
    parser.add_argument("--n-clusters", type=int, default=8)
    parser.add_argument("--min-shared", type=int, default=3,
                        help="Minimum shared foundation terms for a pair to count")
    parser.add_argument("--top-k-pairs", type=int, default=100)
    args = parser.parse_args()

    # ── Load foundation edges ──
    print("Loading foundation edges...")
    papers_all = load_foundation_edges(args.out_dir)
    print(f"  {len(papers_all)} papers with foundation links")

    # Filter to papers with enough terms for meaningful comparison
    min_terms = 5
    papers = {pid: terms for pid, terms in papers_all.items() if len(terms) >= min_terms}
    print(f"  {len(papers)} papers with >= {min_terms} specific foundation terms")

    # Show distribution
    term_counts = sorted([len(t) for t in papers_all.values()])
    print(f"  Foundation terms per paper: "
          f"min={term_counts[0]}, median={term_counts[len(term_counts)//2]}, "
          f"max={term_counts[-1]}, mean={sum(term_counts)/len(term_counts):.1f}")

    if len(papers) < 10:
        print("ERROR: too few papers with enough foundation links")
        sys.exit(1)

    # ── Build TF-IDF matrix ──
    print("\nBuilding TF-IDF matrix...")
    mat, mat_normed, paper_ids, all_terms = build_tfidf_matrix(papers)
    print(f"  Matrix: {mat.shape[0]} papers x {mat.shape[1]} terms")
    print(f"  Non-zero entries: {(mat > 0).sum()} ({100*(mat > 0).mean():.1f}% dense)")

    # ── Part A: Clustering ──
    print(f"\n{'='*60}")
    print(f"PART A: Foundation Fingerprint Clustering ({args.n_clusters} clusters)")
    print(f"{'='*60}")

    labels = cluster_papers(mat_normed, paper_ids, n_clusters=args.n_clusters)
    if labels is not None:
        cluster_profiles = find_top_terms_per_cluster(mat, labels, paper_ids, all_terms)
        for c, profile in enumerate(cluster_profiles):
            n_papers = (labels == c).sum()
            print(f"\n  Cluster {c} ({n_papers} papers):")
            for term, weight, count in profile[:7]:
                print(f"    {weight:.3f}  {term}  (in {count}/{n_papers} papers)")

        # Save cluster assignments
        cluster_file = Path(args.out_dir) / "paper_clusters.json"
        clusters = {pid: int(labels[i]) for i, pid in enumerate(paper_ids)}
        with open(cluster_file, "w") as f:
            json.dump({"n_clusters": args.n_clusters, "assignments": clusters}, f, indent=2)
        print(f"\n  Saved cluster assignments to {cluster_file}")

    # ── Compute similarities ──
    print(f"\n{'='*60}")
    print(f"TOP SIMILAR PAPER PAIRS (by shared foundation terms, min {args.min_shared} shared)")
    print(f"{'='*60}")

    similar_pairs = compute_similarities(papers, paper_ids,
                                          top_k=args.top_k_pairs,
                                          min_shared=args.min_shared)
    print(f"\n  Found {len(similar_pairs)} pairs with >= {args.min_shared} shared terms")
    print(f"\n  Top 30 most similar pairs:")
    for pid_a, pid_b, n_shared, jaccard, idf_sum, shared_terms in similar_pairs[:30]:
        top5 = shared_terms[:5]
        more = f" +{len(shared_terms)-5} more" if len(shared_terms) > 5 else ""
        print(f"    {n_shared:>2} shared (J={jaccard:.2f})  {pid_a} <-> {pid_b}")
        print(f"       {', '.join(top5)}{more}")

    # Save similarities
    sim_file = Path(args.out_dir) / "paper_similarities.json"
    with open(sim_file, "w") as f:
        json.dump([{"paper_a": a, "paper_b": b, "n_shared": ns,
                     "jaccard": round(j, 4), "shared_terms": st}
                   for a, b, ns, j, _, st in similar_pairs], f, indent=2)
    print(f"\n  Saved to {sim_file}")

    # ── Part B: Hidden connections (if citations available) ──
    citations = None
    if args.citations_json:
        print(f"\nLoading cached citations from {args.citations_json}...")
        with open(args.citations_json) as f:
            citations = json.load(f)
        print(f"  {len(citations)} papers with citation data")
    elif args.fetch_citations:
        print(f"\nFetching citations from Semantic Scholar API...")
        cit_path = Path(args.out_dir) / "citations_s2.json"
        citations = fetch_citations_s2(paper_ids, output_path=str(cit_path),
                                        api_key=args.s2_api_key)

    if citations:
        print(f"\n{'='*60}")
        print(f"PART B: Hidden Connections (similar but uncited)")
        print(f"{'='*60}")

        hidden = find_hidden_connections(similar_pairs, citations, top_k=30)
        print(f"\n  Found {len(hidden)} similar-but-uncited pairs (of top {len(similar_pairs)}):")
        for pid_a, pid_b, n_shared, jaccard, idf_sum, shared_terms in hidden[:20]:
            top5 = shared_terms[:5]
            more = f" +{len(shared_terms)-5} more" if len(shared_terms) > 5 else ""
            print(f"    {n_shared:>2} shared (J={jaccard:.2f})  {pid_a} <-> {pid_b}")
            print(f"       {', '.join(top5)}{more}")

        # Save hidden connections
        hidden_file = Path(args.out_dir) / "hidden_connections.json"
        with open(hidden_file, "w") as f:
            json.dump([{"paper_a": a, "paper_b": b, "n_shared": ns,
                         "jaccard": round(j, 4), "shared_terms": st}
                       for a, b, ns, j, _, st in hidden], f, indent=2)
        print(f"\n  Saved to {hidden_file}")
    else:
        print("\n  [skip Part B] No citation data. Use --fetch-citations or --citations-json")


if __name__ == "__main__":
    main()
