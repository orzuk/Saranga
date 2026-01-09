#!/usr/bin/env python3
"""
proofwiki_scraper.py

Scrape mathematical definitions, theorems, and proofs from ProofWiki.

Usage:
    # Scrape a specific category (e.g., Graph Theory)
    python proofwiki_scraper.py --category "Graph_Theory" --out graph_theory_proofwiki.json

    # Scrape multiple categories
    python proofwiki_scraper.py --category "Graph_Theory" "Linear_Algebra" --out math_corpus.json

    # List available top-level math categories
    python proofwiki_scraper.py --list-categories
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import quote

import requests

# Import config for data paths
try:
    from config import PROOFWIKI_DIR, ensure_data_dirs
except ImportError:
    # Fallback if run standalone
    PROOFWIKI_DIR = Path(".")
    def ensure_data_dirs():
        pass

PROOFWIKI_API = "https://proofwiki.org/w/api.php"
PROOFWIKI_BASE = "https://proofwiki.org/wiki/"

DEFAULT_HEADERS = {
    "User-Agent": "Authomathics/1.0 (math corpus builder; educational use)",
}

# Categories that contain actual mathematical content
MATH_CATEGORIES = [
    "Definitions",
    "Theorems",
    "Lemmas",
    "Corollaries",
    "Axioms",
    "Conjectures",
    "Proofs",
]

# Page types we want to extract
PAGE_TYPES = {
    "Definition": "definition",
    "Theorem": "theorem",
    "Lemma": "lemma",
    "Corollary": "corollary",
    "Axiom": "axiom",
    "Conjecture": "conjecture",
    "Proposition": "proposition",
}


@dataclass
class MathItem:
    """A mathematical item (theorem, definition, etc.) from ProofWiki."""
    title: str
    page_id: int
    item_type: str  # theorem, definition, lemma, etc.
    statement: Optional[str] = None
    proof: Optional[str] = None
    categories: List[str] = None
    also_known_as: List[str] = None
    source_url: str = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "page_id": self.page_id,
            "item_type": self.item_type,
            "statement": self.statement,
            "proof": self.proof,
            "categories": self.categories or [],
            "also_known_as": self.also_known_as or [],
            "source_url": self.source_url,
            "source": "proofwiki",
        }


def api_request(params: dict, max_retries: int = 3) -> dict:
    """Make a request to the ProofWiki API with retry logic."""
    params["format"] = "json"

    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(PROOFWIKI_API, params=params, headers=DEFAULT_HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(1 * attempt)
    return {}


# ProofWiki custom namespaces
PROOFWIKI_NAMESPACES = {
    "Axiom": 100,
    "Definition": 102,
    "Symbols": 104,
    "Mathematician": 106,
    "Book": 108,
}


def get_definitions_by_topic(topic_keywords: List[str], limit: int = 200) -> List[dict]:
    """
    Get definition pages from namespace 102, filtered by topic keywords.
    """
    params = {
        "action": "query",
        "list": "allpages",
        "apnamespace": 102,  # Definition namespace
        "aplimit": 500,
        "format": "json",
    }

    all_pages = []
    continue_token = None

    while len(all_pages) < limit * 2:  # Fetch extra since we'll filter
        if continue_token:
            params["apcontinue"] = continue_token

        data = api_request(params)
        batch = data.get("query", {}).get("allpages", [])
        all_pages.extend(batch)

        if "continue" in data:
            continue_token = data["continue"].get("apcontinue")
        else:
            break

    # Filter by keywords
    filtered = []
    for p in all_pages:
        title_lower = p["title"].lower()
        if any(kw.lower() in title_lower for kw in topic_keywords):
            filtered.append(p)
            if len(filtered) >= limit:
                break

    return filtered


def get_category_members(category: str, namespace: int = 0, limit: int = 500) -> List[dict]:
    """
    Get all pages in a category (handles pagination).
    namespace=0 for articles, namespace=14 for subcategories.
    """
    members = []
    continue_token = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmnamespace": namespace,
            "cmlimit": min(limit, 500),
        }
        if continue_token:
            params["cmcontinue"] = continue_token

        data = api_request(params)

        batch = data.get("query", {}).get("categorymembers", [])
        members.extend(batch)

        # Check for more pages
        if "continue" in data:
            continue_token = data["continue"].get("cmcontinue")
        else:
            break

        if len(members) >= limit:
            break

    return members[:limit]


def get_subcategories(category: str) -> List[str]:
    """Get all subcategories of a category."""
    members = get_category_members(category, namespace=14, limit=500)
    # Extract category names without "Category:" prefix
    return [m["title"].replace("Category:", "") for m in members]


def get_page_content(title: str) -> Optional[str]:
    """Get the wikitext content of a page."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
    }

    data = api_request(params)
    pages = data.get("query", {}).get("pages", {})

    for page_id, page_data in pages.items():
        if page_id == "-1":
            return None
        revisions = page_data.get("revisions", [])
        if revisions:
            return revisions[0].get("slots", {}).get("main", {}).get("*", "")
    return None


def get_page_categories(title: str) -> List[str]:
    """Get categories a page belongs to."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "categories",
        "cllimit": 50,
    }

    data = api_request(params)
    pages = data.get("query", {}).get("pages", {})

    categories = []
    for page_data in pages.values():
        for cat in page_data.get("categories", []):
            cat_name = cat["title"].replace("Category:", "")
            categories.append(cat_name)
    return categories


def extract_statement(wikitext: str) -> Optional[str]:
    """Extract the theorem/definition statement from wikitext."""
    # ProofWiki uses templates like {{:Definition:...}} or has sections

    # Try to find statement in common patterns
    patterns = [
        # {{begin-eqn}} ... {{end-eqn}} blocks
        r'\{\{begin-eqn\}\}(.*?)\{\{end-eqn\}\}',
        # :{{Definition ... }} patterns
        r':\'\'\'Definition\'\'\'[:\s]*(.*?)(?=\n\n|\n==|\Z)',
        # == Definition == section
        r'==\s*Definition\s*==\s*(.*?)(?=\n==|\Z)',
        # == Theorem == or == Theorem Statement == section
        r'==\s*Theorem(?:\s+Statement)?\s*==\s*(.*?)(?=\n==|\Z)',
        # == Statement == section
        r'==\s*Statement\s*==\s*(.*?)(?=\n==|\Z)',
        # Let/Then patterns (common in theorems)
        r'(Let.*?(?:Then|Hence|Therefore).*?)(?=\n==|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, wikitext, re.DOTALL | re.IGNORECASE)
        if match:
            statement = match.group(1).strip()
            # Clean up wiki markup
            statement = clean_wikitext(statement)
            if len(statement) > 20:  # Minimum viable statement
                return statement

    # Fallback: take first substantial paragraph
    lines = wikitext.split('\n\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('{{') and not line.startswith('==') and len(line) > 50:
            return clean_wikitext(line)

    return None


def extract_proof(wikitext: str) -> Optional[str]:
    """Extract the proof from wikitext."""
    # Look for == Proof == section
    patterns = [
        r'==\s*Proof\s*==\s*(.*?)(?=\n==|\Z)',
        r'==\s*Proof\s+\d+\s*==\s*(.*?)(?=\n==|\Z)',
    ]

    for pattern in patterns:
        match = re.search(pattern, wikitext, re.DOTALL | re.IGNORECASE)
        if match:
            proof = match.group(1).strip()
            return clean_wikitext(proof)

    return None


def extract_also_known_as(wikitext: str) -> List[str]:
    """Extract alternative names for the concept."""
    aliases = []

    # Look for "Also known as" or "Also see" sections
    patterns = [
        r'==\s*Also [Kk]nown [Aa]s\s*==\s*(.*?)(?=\n==|\Z)',
        r'\{\{[Aa]lso[Kk]nown[Aa]s\|(.*?)\}\}',
        r"[Aa]lso (?:known|called|referred to) as[:\s]+['\"]*(.*?)['\"]",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, wikitext, re.DOTALL)
        for match in matches:
            # Split by common delimiters
            for alias in re.split(r'[,;]|\bor\b|\band\b', match):
                alias = clean_wikitext(alias.strip())
                if alias and len(alias) > 2 and alias not in aliases:
                    aliases.append(alias)

    return aliases


def clean_wikitext(text: str) -> str:
    """Clean up wikitext markup to plain text."""
    if not text:
        return ""

    # Remove templates (but try to keep their content)
    text = re.sub(r'\{\{[^}]*\}\}', '', text)

    # Convert wiki links [[Link|Display]] -> Display, [[Link]] -> Link
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)

    # Remove external links [http://... text] -> text
    text = re.sub(r'\[https?://[^\s\]]+ ([^\]]+)\]', r'\1', text)
    text = re.sub(r'\[https?://[^\]]+\]', '', text)

    # Remove bold/italic markup
    text = re.sub(r"'''?", '', text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Remove category links
    text = re.sub(r'\[\[Category:[^\]]+\]\]', '', text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def classify_page_type(title: str, categories: List[str], wikitext: str) -> str:
    """Determine what type of mathematical item this page is."""
    title_lower = title.lower()
    cats_lower = [c.lower() for c in categories]

    # Check title first
    for keyword, item_type in PAGE_TYPES.items():
        if keyword.lower() in title_lower:
            return item_type

    # Check categories
    for cat in cats_lower:
        if "theorem" in cat:
            return "theorem"
        elif "definition" in cat:
            return "definition"
        elif "lemma" in cat:
            return "lemma"
        elif "corollary" in cat:
            return "corollary"
        elif "axiom" in cat:
            return "axiom"
        elif "conjecture" in cat:
            return "conjecture"

    # Check wikitext for clues
    if "== Proof ==" in wikitext or "==Proof==" in wikitext:
        return "theorem"  # Has a proof, likely a theorem/lemma

    return "concept"  # Default


def scrape_page(title: str, page_id: int) -> Optional[MathItem]:
    """Scrape a single ProofWiki page."""
    wikitext = get_page_content(title)
    if not wikitext:
        return None

    categories = get_page_categories(title)
    item_type = classify_page_type(title, categories, wikitext)

    statement = extract_statement(wikitext)
    proof = extract_proof(wikitext) if item_type in ["theorem", "lemma", "corollary", "proposition"] else None
    aliases = extract_also_known_as(wikitext)

    return MathItem(
        title=title,
        page_id=page_id,
        item_type=item_type,
        statement=statement,
        proof=proof,
        categories=categories,
        also_known_as=aliases,
        source_url=PROOFWIKI_BASE + quote(title.replace(" ", "_")),
    )


def scrape_category_recursive(category: str, max_depth: int = 2, limit: int = 1000) -> List[MathItem]:
    """Recursively scrape all pages in a category and its subcategories."""
    items = []
    visited_categories = set()
    visited_pages = set()

    def _scrape(cat: str, depth: int):
        if depth > max_depth or cat in visited_categories or len(items) >= limit:
            return

        visited_categories.add(cat)
        print(f"  {'  ' * depth}Scraping category: {cat}")

        # Get pages in this category
        pages = get_category_members(cat, namespace=0, limit=500)

        for page in pages:
            if len(items) >= limit:
                break
            if page["pageid"] in visited_pages:
                continue

            visited_pages.add(page["pageid"])

            try:
                item = scrape_page(page["title"], page["pageid"])
                if item and item.statement:  # Only keep items with actual content
                    items.append(item)
                    if len(items) % 10 == 0:
                        print(f"    Scraped {len(items)} items...")
                time.sleep(0.2)  # Be nice to the server
            except Exception as e:
                print(f"    Warning: Failed to scrape {page['title']}: {e}")

        # Recurse into subcategories
        if depth < max_depth:
            subcats = get_subcategories(cat)
            for subcat in subcats:
                if len(items) >= limit:
                    break
                _scrape(subcat, depth + 1)

    _scrape(category, 0)
    return items


def list_math_categories() -> List[str]:
    """List top-level mathematical categories in ProofWiki."""
    # Get subcategories of the main Mathematics category
    top_cats = get_subcategories("Proven_Results")
    return sorted(top_cats)


# Topic-specific keywords for filtering definitions
TOPIC_KEYWORDS = {
    "Graph_Theory": [
        "graph", "vertex", "edge", "path", "cycle", "tree", "forest",
        "connected", "bridge", "circuit", "walk", "trail", "degree",
        "adjacent", "incident", "planar", "bipartite", "complete",
        "clique", "coloring", "chromatic", "eulerian", "hamiltonian",
        "spanning", "subgraph", "digraph", "directed", "undirected",
        "matching", "network", "flow", "cut", "minor", "embedding",
    ],
    "Linear_Algebra": [
        "matrix", "vector", "linear", "eigenvalue", "eigenvector",
        "determinant", "rank", "null", "span", "basis", "dimension",
        "orthogonal", "transpose", "inverse", "trace", "diagonal",
    ],
    "Number_Theory": [
        "prime", "divisor", "congruence", "modular", "integer",
        "factorial", "gcd", "lcm", "coprime", "residue",
    ],
    "Topology": [
        "topology", "open", "closed", "compact", "connected",
        "continuous", "homeomorphism", "metric", "neighborhood",
    ],
}


def scrape_definitions_for_topic(topic: str, limit: int = 100) -> List[MathItem]:
    """Scrape definition pages for a specific topic."""
    keywords = TOPIC_KEYWORDS.get(topic, [topic.lower().replace("_", " ")])

    print(f"  Fetching definitions with keywords: {keywords[:5]}...")
    pages = get_definitions_by_topic(keywords, limit=limit * 2)

    items = []
    for page in pages[:limit]:
        try:
            item = scrape_page(page["title"], page["pageid"])
            if item and item.statement:
                item.item_type = "definition"
                items.append(item)
                if len(items) % 10 == 0:
                    print(f"    Scraped {len(items)} definitions...")
            time.sleep(0.2)
        except Exception as e:
            print(f"    Warning: Failed to scrape {page['title']}: {e}")

    return items


def main():
    # Default output path uses config
    default_out = PROOFWIKI_DIR / "proofwiki_corpus.json"

    parser = argparse.ArgumentParser(description="Scrape ProofWiki for mathematical content")
    parser.add_argument("--category", "-c", nargs="+", help="Category(ies) to scrape for theorems")
    parser.add_argument("--definitions", "-D", nargs="+", help="Topic(s) to scrape for definitions")
    parser.add_argument("--out", "-o", default=str(default_out), help=f"Output JSON file (default: {default_out})")
    parser.add_argument("--limit", "-l", type=int, default=500, help="Max items to scrape per category")
    parser.add_argument("--depth", "-d", type=int, default=2, help="Max subcategory depth")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")

    args = parser.parse_args()

    if args.list_categories:
        print("Top-level ProofWiki categories:")
        for cat in list_math_categories():
            print(f"  - {cat}")
        print("\nSupported definition topics:")
        for topic in TOPIC_KEYWORDS.keys():
            print(f"  - {topic}")
        return

    if not args.category and not args.definitions:
        print("Error: Please specify --category and/or --definitions")
        print("Examples:")
        print("  python proofwiki_scraper.py --category Graph_Theory --limit 50")
        print("  python proofwiki_scraper.py --definitions Graph_Theory --limit 50")
        print("  python proofwiki_scraper.py --category Graph_Theory --definitions Graph_Theory --limit 50")
        return

    all_items = []

    # Scrape theorems from categories
    if args.category:
        for category in args.category:
            print(f"\nScraping theorems from category: {category}")
            items = scrape_category_recursive(category, max_depth=args.depth, limit=args.limit)
            all_items.extend(items)
            print(f"  Found {len(items)} theorems in {category}")

    # Scrape definitions
    if args.definitions:
        for topic in args.definitions:
            print(f"\nScraping definitions for topic: {topic}")
            items = scrape_definitions_for_topic(topic, limit=args.limit)
            all_items.extend(items)
            print(f"  Found {len(items)} definitions for {topic}")

    # Deduplicate by page_id
    seen_ids = set()
    unique_items = []
    for item in all_items:
        if item.page_id not in seen_ids:
            seen_ids.add(item.page_id)
            unique_items.append(item)

    # Ensure output directory exists
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to JSON
    output = {
        "schema": "authomathics.proofwiki_corpus.v1",
        "metadata": {
            "categories": args.category or [],
            "definitions": args.definitions or [],
            "total_items": len(unique_items),
        },
        "items": [item.to_dict() for item in unique_items],
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Saved {len(unique_items)} items to {args.out}")

    # Print summary by type
    type_counts = {}
    for item in unique_items:
        type_counts[item.item_type] = type_counts.get(item.item_type, 0) + 1
    print("\nBy type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
