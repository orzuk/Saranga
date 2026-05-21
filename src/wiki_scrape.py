#!/usr/bin/env python3
"""
wiki_scrape.py — unified MediaWiki-based foundation-graph scraper.

Single CLI entry point for scraping any MediaWiki-style math reference into the
NaturalProofs JSON format consumed by scripts/clean_foundation.py. Each source
is plugged in via the SITES registry below.

Supports two scrape strategies, configurable per-pass:
  - "list":     walk every wikilink target out of a seed page (e.g. List_of_X).
  - "category": recursively walk a Wikipedia category and its subcategories,
                collecting article titles up to a max depth.

Usage:

    # Pass A — walk curated `List of X` pages on Wikipedia.
    python src/wiki_scrape.py --site wikipedia --pass A

    # Pass B — recursively walk top-level math Categories on Wikipedia.
    python src/wiki_scrape.py --site wikipedia --pass B

    # Run both passes (one CLI invocation per pass; trivial to chain in shell):
    python src/wiki_scrape.py --site wikipedia --pass A
    python src/wiki_scrape.py --site wikipedia --pass B

    # Smoke test on a single seed (Pass A list or Pass B category):
    python src/wiki_scrape.py --site wikipedia --pass A \\
        --only List_of_conjectures --max-articles 10
    python src/wiki_scrape.py --site wikipedia --pass B \\
        --only Conjectures --max-articles 50

Output:

    Writes one JSON file per `--site / seed` pair into NATURALPROOFS_DIR/raw/.
    Pass A files are named `naturalproofs_<source>_<list_slug>.json`.
    Pass B files are named `naturalproofs_<source>_cat_<category_slug>.json`.
    Existing output files are SKIPPED on re-run unless --force.

Per-item schema:

    {
        "title": "Hodge conjecture",
        "name":  "Hodge conjecture",
        "type":  "conjecture",
        "contents_preview": "<lead paragraph, capped 800 chars>",
        "categories": ["Conjectures", "Algebraic geometry", "Hodge theory"],
        "msc_codes":  ["14C30"],            # may be null
        "arxiv_categories": ["math.AG"],    # may be null
        "url":  "https://en.wikipedia.org/wiki/Hodge_conjecture",
        "_source": "wikipedia",
        "_seed_page": "List_of_conjectures" or "Category:Conjectures",
        "_strategy": "list" or "category",
    }

Note: matches the existing proofwiki_scraper.py pattern in spirit (generic
MediaWiki API client + per-site config) but unified across sites so we don't
re-implement the API loop for every new source (OPG, nLab, EOM) we add later.
proofwiki_scraper.py is left alone for now; can be migrated into SITES later.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import requests

# Project config — resolves NATURALPROOFS_DIR across local/cluster layouts.
try:
    from config import NATURALPROOFS_DIR
except ImportError:
    NATURALPROOFS_DIR = Path(".") / "naturalproofs"


# ============================================================================
# Wikipedia-category -> taxonomies mapping.
# Each Wikipedia category we recognize maps to (MSC codes, arXiv categories).
# Used only for site=wikipedia; other sites carry their own mappings if needed.
# Coverage target: top ~50 math/CS Wikipedia categories.
# Entries that don't match any key stay with msc_codes=None, arxiv_categories=None.
# ============================================================================

WIKI_CAT_TO_TAXONOMIES: Dict[str, Dict[str, List[str]]] = {
    # Algebra
    "Algebra":                          {"msc": ["08", "13", "16", "20"], "arxiv": ["math.RA"]},
    "Abstract algebra":                 {"msc": ["08"],            "arxiv": ["math.RA"]},
    "Commutative algebra":              {"msc": ["13"],            "arxiv": ["math.AC"]},
    "Ring theory":                      {"msc": ["13", "16"],      "arxiv": ["math.RA", "math.AC"]},
    "Group theory":                     {"msc": ["20"],            "arxiv": ["math.GR"]},
    "Representation theory":            {"msc": ["20G", "22E"],    "arxiv": ["math.RT"]},
    "Lie groups":                       {"msc": ["22E"],           "arxiv": ["math.RT", "math.DG"]},
    "Field theory":                     {"msc": ["12"],            "arxiv": ["math.AC"]},
    "Galois theory":                    {"msc": ["12F"],           "arxiv": ["math.AC", "math.NT"]},
    "Linear algebra":                   {"msc": ["15"],            "arxiv": ["math.RA"]},
    "Module theory":                    {"msc": ["16D"],           "arxiv": ["math.RA"]},
    "Homological algebra":              {"msc": ["18G"],           "arxiv": ["math.AC", "math.AT"]},
    "Category theory":                  {"msc": ["18"],            "arxiv": ["math.CT"]},
    # Geometry
    "Algebraic geometry":               {"msc": ["14"],            "arxiv": ["math.AG"]},
    "Arithmetic geometry":              {"msc": ["14G"],           "arxiv": ["math.AG", "math.NT"]},
    "Differential geometry":            {"msc": ["53"],            "arxiv": ["math.DG"]},
    "Riemannian geometry":              {"msc": ["53C"],           "arxiv": ["math.DG"]},
    "Symplectic geometry":              {"msc": ["53D"],           "arxiv": ["math.SG"]},
    "Euclidean geometry":               {"msc": ["51"],            "arxiv": ["math.MG"]},
    "Convex geometry":                  {"msc": ["52A"],           "arxiv": ["math.MG"]},
    "Discrete geometry":                {"msc": ["52C"],           "arxiv": ["math.CO", "math.MG"]},
    # Topology
    "Topology":                         {"msc": ["54", "55"],      "arxiv": ["math.GN", "math.AT"]},
    "General topology":                 {"msc": ["54"],            "arxiv": ["math.GN"]},
    "Point-set topology":               {"msc": ["54"],            "arxiv": ["math.GN"]},
    "Algebraic topology":               {"msc": ["55"],            "arxiv": ["math.AT"]},
    "Geometric topology":               {"msc": ["57"],            "arxiv": ["math.GT"]},
    "Homotopy theory":                  {"msc": ["55P"],           "arxiv": ["math.AT"]},
    "Knot theory":                      {"msc": ["57K"],           "arxiv": ["math.GT"]},
    # Analysis
    "Mathematical analysis":            {"msc": ["26", "28"],      "arxiv": ["math.CA"]},
    "Real analysis":                    {"msc": ["26"],            "arxiv": ["math.CA"]},
    "Complex analysis":                 {"msc": ["30"],            "arxiv": ["math.CV"]},
    "Functional analysis":              {"msc": ["46", "47"],      "arxiv": ["math.FA"]},
    "Operator theory":                  {"msc": ["47"],            "arxiv": ["math.OA", "math.FA"]},
    "Harmonic analysis":                {"msc": ["42"],            "arxiv": ["math.CA"]},
    "Fourier analysis":                 {"msc": ["42"],            "arxiv": ["math.CA"]},
    "Measure theory":                   {"msc": ["28"],            "arxiv": ["math.CA"]},
    "Calculus":                         {"msc": ["26A"],           "arxiv": ["math.CA"]},
    "Calculus of variations":           {"msc": ["49"],            "arxiv": ["math.OC", "math.AP"]},
    # PDEs / ODEs / dynamical
    "Partial differential equations":   {"msc": ["35"],            "arxiv": ["math.AP"]},
    "Ordinary differential equations":  {"msc": ["34"],            "arxiv": ["math.CA", "math.DS"]},
    "Dynamical systems":                {"msc": ["37"],            "arxiv": ["math.DS"]},
    "Ergodic theory":                   {"msc": ["37A"],           "arxiv": ["math.DS"]},
    # Number theory
    "Number theory":                    {"msc": ["11"],            "arxiv": ["math.NT"]},
    "Analytic number theory":           {"msc": ["11M", "11N"],    "arxiv": ["math.NT"]},
    "Algebraic number theory":          {"msc": ["11R"],           "arxiv": ["math.NT"]},
    "Combinatorial number theory":      {"msc": ["11B"],           "arxiv": ["math.NT", "math.CO"]},
    "Diophantine geometry":             {"msc": ["11G"],           "arxiv": ["math.NT", "math.AG"]},
    # Combinatorics / discrete
    "Combinatorics":                    {"msc": ["05"],            "arxiv": ["math.CO"]},
    "Graph theory":                     {"msc": ["05C"],           "arxiv": ["math.CO", "cs.DM"]},
    "Enumerative combinatorics":        {"msc": ["05A"],           "arxiv": ["math.CO"]},
    "Order theory":                     {"msc": ["06"],            "arxiv": ["math.CO"]},
    "Lattice theory":                   {"msc": ["06"],            "arxiv": ["math.CO"]},
    # Probability / statistics
    "Probability theory":               {"msc": ["60"],            "arxiv": ["math.PR"]},
    "Stochastic processes":             {"msc": ["60G"],           "arxiv": ["math.PR"]},
    "Mathematical statistics":          {"msc": ["62"],            "arxiv": ["math.ST", "stat.TH"]},
    "Statistics":                       {"msc": ["62"],            "arxiv": ["math.ST", "stat.TH"]},
    "Bayesian statistics":              {"msc": ["62F15"],         "arxiv": ["stat.ML", "stat.ME"]},
    # Optimization / OR
    "Mathematical optimization":        {"msc": ["49", "90"],      "arxiv": ["math.OC"]},
    "Convex optimization":              {"msc": ["90C25"],         "arxiv": ["math.OC"]},
    "Operations research":              {"msc": ["90"],            "arxiv": ["math.OC"]},
    "Game theory":                      {"msc": ["91A"],           "arxiv": ["math.OC", "cs.GT"]},
    # Logic / foundations
    "Mathematical logic":               {"msc": ["03"],            "arxiv": ["math.LO"]},
    "Set theory":                       {"msc": ["03E"],           "arxiv": ["math.LO"]},
    "Model theory":                     {"msc": ["03C"],           "arxiv": ["math.LO"]},
    "Proof theory":                     {"msc": ["03F"],           "arxiv": ["math.LO"]},
    "Computability theory":             {"msc": ["03D"],           "arxiv": ["math.LO", "cs.LO"]},
    # Numerical
    "Numerical analysis":               {"msc": ["65"],            "arxiv": ["math.NA"]},
    "Numerical linear algebra":         {"msc": ["65F"],           "arxiv": ["math.NA"]},
    # Physics / math-ph
    "Mathematical physics":             {"msc": ["81", "82"],      "arxiv": ["math-ph"]},
    "Quantum mechanics":                {"msc": ["81P"],           "arxiv": ["math-ph", "quant-ph"]},
    "Quantum field theory":             {"msc": ["81T"],           "arxiv": ["math-ph", "hep-th"]},
    "Statistical mechanics":            {"msc": ["82B"],           "arxiv": ["math-ph", "cond-mat.stat-mech"]},
    # Theoretical CS
    "Theoretical computer science":     {"msc": ["68Q"],           "arxiv": ["cs.CC", "cs.DS"]},
    "Computational complexity theory":  {"msc": ["68Q15"],         "arxiv": ["cs.CC"]},
    "Algorithms":                       {"msc": ["68W"],           "arxiv": ["cs.DS"]},
    "Data structures":                  {"msc": ["68P"],           "arxiv": ["cs.DS"]},
    "Machine learning":                 {"msc": ["68T"],           "arxiv": ["cs.LG", "stat.ML"]},
    "Information theory":               {"msc": ["94A"],           "arxiv": ["cs.IT", "math.IT"]},
    "Coding theory":                    {"msc": ["94B"],           "arxiv": ["cs.IT", "math.IT"]},
    "Cryptography":                     {"msc": ["94A60"],         "arxiv": ["cs.CR"]},
}


MSC_INLINE_RE = re.compile(r"\b\d{2}[A-Z]\d{2}\b")


# ============================================================================
# Pass A — list-walking title filters.
# ============================================================================


def _wikipedia_conjecture_title_filter(title: str) -> bool:
    """Heuristic: keep a List_of_conjectures link if it plausibly names a conjecture.

    Drops the mathematician-name pages (e.g. 'Alexander Beilinson') and generic
    concept pages that appear on the list as cross-references. Permissive —
    final cleanup happens in clean_foundation.py's normalization pass.
    """
    t = title.lower()
    if "conjecture" in t or "hypothesis" in t:
        return True
    parts = title.split()
    if len(parts) == 2 and all(p[0].isupper() for p in parts):
        # Looks like a person's name — drop.
        return False
    return True


def _wikipedia_open_problem_title_filter(title: str) -> bool:
    t = title.lower()
    if any(k in t for k in ("problem", "hypothesis", "conjecture", "question")):
        return True
    parts = title.split()
    if len(parts) == 2 and all(p[0].isupper() for p in parts):
        return False
    return True


# ============================================================================
# Per-site configs. Pluggable: add OPG / nLab / EOM by extending this dict.
# ============================================================================


SITES: Dict[str, Dict[str, Any]] = {
    "wikipedia": {
        "api_url":  "https://en.wikipedia.org/w/api.php",
        "base_url": "https://en.wikipedia.org/wiki/",
        "user_agent": "SARANGA/1.0 (math foundation graph builder; or.zuk@mail.huji.ac.il)",
        "source_name": "wikipedia",
        "passes": {
            # Pass A — walk a handful of curated `List_of_*` pages.
            # Each seed is a List page; we follow every namespace=0 link.
            "A": {
                "strategy": "list",
                "seeds": {
                    "List_of_theorems":                           "theorem",
                    "List_of_conjectures":                        "conjecture",
                    "List_of_lemmas":                             "lemma",
                    "List_of_unsolved_problems_in_mathematics":   "open_problem",
                    "List_of_algorithms":                         "algorithm",
                    "List_of_NP-complete_problems":               "problem",
                },
                "title_filters": {
                    "List_of_conjectures":                        _wikipedia_conjecture_title_filter,
                    "List_of_unsolved_problems_in_mathematics":   _wikipedia_open_problem_title_filter,
                },
            },
            # Pass B — recursively walk top-level Wikipedia math Categories.
            # Each seed is a Category name (no "Category:" prefix). Per-seed
            # depth + cap control how far into the subcategory tree to go.
            #
            # Tunable: smaller depth = faster, less coverage. Mathematical_theorems
            # at depth=2 currently maxes out around ~5K articles after dedup.
            "B": {
                "strategy": "category",
                "seeds": {
                    "Mathematical_theorems":             {"type": "theorem",      "depth": 2, "max_articles": 6000},
                    "Conjectures":                       {"type": "conjecture",   "depth": 2, "max_articles": 2000},
                    "Lemmas":                            {"type": "lemma",        "depth": 2, "max_articles": 800},
                    "Mathematical_definitions":          {"type": "definition",   "depth": 2, "max_articles": 6000},
                    "Algorithms":                        {"type": "algorithm",    "depth": 2, "max_articles": 4000},
                    "Computational_problems":            {"type": "problem",      "depth": 2, "max_articles": 2000},
                    "Unsolved_problems_in_mathematics":  {"type": "open_problem", "depth": 1, "max_articles": 500},
                },
            },
        },
        "category_taxonomy_map": WIKI_CAT_TO_TAXONOMIES,
    },
    # Future:
    #   "proofwiki": { ... },
    #   "opg":       { ... },
    #   "nlab":      { ... },
    #   "eom":       { ... },
}


# ============================================================================
# Generic MediaWiki API primitives. Site-agnostic — pass api_url + headers.
# ============================================================================


def api_request(api_url: str, params: dict, headers: dict,
                sleep: float = 1.0, max_retries: int = 3) -> dict:
    """GET against a MediaWiki API with retries + rate-limit pause."""
    params = {**params, "format": "json"}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(api_url, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            time.sleep(sleep)
            return data
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(sleep * attempt)
    return {}


def list_links_in_page(api_url: str, page_title: str, headers: dict,
                       namespace: int = 0, sleep: float = 1.0) -> List[str]:
    """Get every namespace-N wikilink target inside a page (e.g. a List-of page)."""
    data = api_request(api_url, {
        "action": "parse",
        "page": page_title,
        "prop": "links",
    }, headers=headers, sleep=sleep)
    links = data.get("parse", {}).get("links", []) or []
    out: List[str] = []
    seen: set = set()
    for link in links:
        if link.get("ns") != namespace:
            continue
        title = link.get("*")
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(title)
    return out


def category_members(api_url: str, category: str, headers: dict,
                     namespace: int = 0, sleep: float = 1.0,
                     max_pages: int = 50) -> List[str]:
    """Get all members of a category in a given namespace.

    namespace=0  -> articles
    namespace=14 -> subcategories (titles still start with 'Category:')
    Walks the categorymembers API with cmcontinue pagination, capped at
    max_pages * 500 entries to bound runaway categories.
    """
    out: List[str] = []
    cont: Optional[str] = None
    pages = 0
    while pages < max_pages:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmnamespace": namespace,
            "cmlimit": 500,
        }
        if cont:
            params["cmcontinue"] = cont
        data = api_request(api_url, params, headers=headers, sleep=sleep)
        batch = (data.get("query") or {}).get("categorymembers") or []
        for m in batch:
            t = m.get("title")
            if t:
                out.append(t)
        cont = (data.get("continue") or {}).get("cmcontinue")
        pages += 1
        if not cont:
            break
    return out


def walk_category(api_url: str, category: str, headers: dict,
                  max_depth: int = 1, sleep: float = 1.0,
                  visited: Optional[Set[str]] = None,
                  _depth: int = 0) -> List[str]:
    """Recursively walk a Wikipedia category, collecting article titles.

    Articles are ns=0; subcategories are ns=14. Stops at max_depth. Avoids
    cycles via the `visited` set (categories form a DAG with cycles in
    practice).
    """
    if visited is None:
        visited = set()
    if category in visited:
        return []
    visited.add(category)

    # Direct articles in this category.
    articles = category_members(api_url, category, headers, namespace=0, sleep=sleep)

    if _depth >= max_depth:
        return articles

    # Recurse into subcategories.
    sub_titles = category_members(api_url, category, headers, namespace=14, sleep=sleep)
    sub_cats = [s[len("Category:"):] for s in sub_titles if s.startswith("Category:")]
    for sub in sub_cats:
        articles.extend(walk_category(api_url, sub, headers,
                                      max_depth=max_depth, sleep=sleep,
                                      visited=visited, _depth=_depth + 1))
    # Dedup, preserve order.
    return list(dict.fromkeys(articles))


def fetch_article_lead(api_url: str, title: str, headers: dict,
                       sleep: float = 1.0) -> Optional[dict]:
    """Fetch lead paragraph + categories of one article.

    Returns {title, lead, categories} or None on missing / empty.
    """
    data = api_request(api_url, {
        "action": "query",
        "titles": title,
        "prop": "extracts|categories",
        "exintro": True,
        "explaintext": True,
        "cllimit": 50,
        "redirects": True,
    }, headers=headers, sleep=sleep)
    pages = (data.get("query", {}) or {}).get("pages", {}) or {}
    if not pages:
        return None
    page = next(iter(pages.values()))
    if page.get("missing") is not None:
        return None
    extract = (page.get("extract") or "").strip()
    if not extract:
        return None
    cats: List[str] = []
    for c in page.get("categories") or []:
        ct = c.get("title", "")
        if ct.startswith("Category:"):
            cats.append(ct[len("Category:"):])
    return {
        "title": page.get("title", title),
        "lead": extract,
        "categories": cats,
    }


# ============================================================================
# Wikipedia-specific item builder. Other sites would have their own builder.
# ============================================================================


def _wiki_taxonomies(categories: List[str], lead: str) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """Map (article categories, lead) to (msc_codes, arxiv_categories)."""
    msc, arxiv = set(), set()
    msc.update(MSC_INLINE_RE.findall(lead[:3000]))
    for cat in categories:
        m = WIKI_CAT_TO_TAXONOMIES.get(cat)
        if m is None:
            continue
        msc.update(m["msc"])
        arxiv.update(m["arxiv"])
    return (sorted(msc) if msc else None,
            sorted(arxiv) if arxiv else None)


def _build_item_wikipedia(article: dict, default_type: str,
                          seed_page: str, strategy: str, site: dict) -> dict:
    msc, arxiv = _wiki_taxonomies(article["categories"], article["lead"])
    return {
        "title": article["title"],
        "name": article["title"],
        "type": default_type,
        "contents_preview": article["lead"][:800],
        "categories": article["categories"],
        "msc_codes": msc,
        "arxiv_categories": arxiv,
        "url": site["base_url"] + article["title"].replace(" ", "_"),
        "_source": site["source_name"],
        "_seed_page": seed_page,
        "_strategy": strategy,
    }


ITEM_BUILDERS: Dict[str, Callable[..., dict]] = {
    "wikipedia": _build_item_wikipedia,
    # add other sites' builders here
}


# ============================================================================
# Driver — orchestrates a pass for a given site.
# ============================================================================


def _seed_slug(seed: str, strategy: str) -> str:
    """Filename-safe slug from a seed name. Strategy distinguishes list/category."""
    s = seed.lower().replace(" ", "_").replace("/", "_")
    s = re.sub(r"[^a-z0-9_\-]", "", s)
    if strategy == "list":
        s = s.removeprefix("list_of_")
    if strategy == "category":
        s = f"cat_{s}"
    return s or "untitled"


def _normalize_seed_cfg(seed_cfg: Union[str, dict]) -> dict:
    """Normalize seed config to dict form. String value -> {'type': value}."""
    if isinstance(seed_cfg, str):
        return {"type": seed_cfg}
    return dict(seed_cfg)


def _collect_titles_list(site: dict, pass_cfg: dict, seed_page: str,
                         headers: dict, sleep: float) -> List[str]:
    """Pass A — get all wikilink targets out of a List-of page, with optional filter."""
    titles = list_links_in_page(site["api_url"], seed_page, headers, sleep=sleep)
    tf = (pass_cfg.get("title_filters") or {}).get(seed_page)
    if tf is not None:
        before = len(titles)
        titles = [t for t in titles if tf(t)]
        print(f"[wiki_scrape]   title-filter kept {len(titles)}/{before}")
    return titles


def _collect_titles_category(site: dict, seed_cat: str, seed_cfg: dict,
                             headers: dict, sleep: float) -> List[str]:
    """Pass B — walk a Wikipedia category recursively."""
    depth = int(seed_cfg.get("depth", 1))
    titles = walk_category(site["api_url"], seed_cat, headers,
                           max_depth=depth, sleep=sleep)
    return titles


def scrape_pass(site_name: str, pass_name: str,
                out_dir: Path,
                sleep: float = 1.0,
                max_articles: Optional[int] = None,
                only_seeds: Optional[List[str]] = None,
                force: bool = False) -> None:
    """Run one pass (e.g. Pass A or Pass B) for a configured site."""
    if site_name not in SITES:
        raise ValueError(f"unknown site: {site_name}. Available: {list(SITES)}")
    site = SITES[site_name]
    if pass_name not in site["passes"]:
        raise ValueError(f"site {site_name} has no pass {pass_name}. "
                         f"Available: {list(site['passes'])}")
    pass_cfg = site["passes"][pass_name]
    strategy = pass_cfg["strategy"]
    if strategy not in ("list", "category"):
        raise NotImplementedError(f"strategy={strategy} not implemented")

    builder = ITEM_BUILDERS.get(site_name)
    if builder is None:
        raise ValueError(f"no item builder registered for site {site_name}")

    headers = {"User-Agent": site["user_agent"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    seeds = pass_cfg["seeds"]
    if only_seeds:
        seeds = {k: v for k, v in seeds.items() if k in set(only_seeds)}
        if not seeds:
            print(f"[wiki_scrape] no seeds match --only {only_seeds}; exiting.")
            return

    print(f"[wiki_scrape] site={site_name} pass={pass_name} strategy={strategy} "
          f"seeds={len(seeds)} out={out_dir} sleep={sleep}s")

    for seed, seed_cfg_raw in seeds.items():
        seed_cfg = _normalize_seed_cfg(seed_cfg_raw)
        default_type = seed_cfg["type"]
        per_seed_cap = seed_cfg.get("max_articles")
        slug = _seed_slug(seed, strategy)
        out_file = out_dir / f"naturalproofs_{site['source_name']}_{slug}.json"
        if out_file.exists() and not force:
            print(f"[wiki_scrape] skip {out_file.name} (exists; use --force to overwrite)")
            continue

        seed_label = f"Category:{seed}" if strategy == "category" else seed
        print(f"\n[wiki_scrape] === {seed_label} -> {default_type} ===")
        t0 = time.time()

        try:
            if strategy == "list":
                titles = _collect_titles_list(site, pass_cfg, seed, headers, sleep)
            else:  # category
                titles = _collect_titles_category(site, seed, seed_cfg, headers, sleep)
        except Exception as e:
            print(f"[wiki_scrape] FATAL collecting {seed_label}: {e}")
            continue

        # Apply per-seed and CLI caps.
        if per_seed_cap is not None and len(titles) > per_seed_cap:
            print(f"[wiki_scrape]   per-seed cap: {len(titles)} -> {per_seed_cap}")
            titles = titles[:per_seed_cap]
        if max_articles is not None and len(titles) > max_articles:
            print(f"[wiki_scrape]   CLI --max-articles cap: {len(titles)} -> {max_articles}")
            titles = titles[:max_articles]

        print(f"[wiki_scrape]   {len(titles)} candidate articles")

        items: List[dict] = []
        for i, title in enumerate(titles, 1):
            if i % 25 == 0:
                rate = i / max(1.0, time.time() - t0)
                eta = (len(titles) - i) / max(0.01, rate)
                print(f"[wiki_scrape]   [{i}/{len(titles)}] {title} "
                      f"(rate={rate:.2f}/s, eta={eta:.0f}s)")
            try:
                art = fetch_article_lead(site["api_url"], title, headers, sleep=sleep)
            except Exception as e:
                print(f"[wiki_scrape]   WARN {title}: {e}")
                continue
            if art is None:
                continue
            items.append(builder(art, default_type, seed_label, strategy, site))

        meta = {
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "site": site_name,
            "pass": pass_name,
            "strategy": strategy,
            "seed": seed_label,
            "default_type": default_type,
            "depth": seed_cfg.get("depth"),
            "item_count": len(items),
            "elapsed_sec": round(time.time() - t0, 1),
        }
        payload = {
            "schema": f"saranga.{site['source_name']}_{pass_name.lower()}.v1",
            "metadata": meta,
            "dataset": items,
        }
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[wiki_scrape] wrote {len(items)} items to {out_file.name} "
              f"({meta['elapsed_sec']}s)")


def main():
    ap = argparse.ArgumentParser(description="Unified MediaWiki -> NaturalProofs scraper.")
    ap.add_argument("--site", required=True, choices=list(SITES.keys()),
                    help="Which site to scrape.")
    ap.add_argument("--pass", dest="pass_name", default="A",
                    help="Which pass to run within the site config (default: A).")
    ap.add_argument("--out-dir", default=None,
                    help="Output directory (default: NATURALPROOFS_DIR/raw).")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Seconds between API calls (rate-limit politeness). Default 1.0.")
    ap.add_argument("--max-articles", type=int, default=None,
                    help="Cap articles per seed (for testing).")
    ap.add_argument("--only", nargs="+", default=None, dest="only_seeds",
                    help="Restrict to specific seed names (e.g. List_of_conjectures or Conjectures).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing per-seed JSON files instead of skipping.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else NATURALPROOFS_DIR / "raw"

    scrape_pass(
        site_name=args.site,
        pass_name=args.pass_name,
        out_dir=out_dir,
        sleep=args.sleep,
        max_articles=args.max_articles,
        only_seeds=args.only_seeds,
        force=args.force,
    )


if __name__ == "__main__":
    main()
