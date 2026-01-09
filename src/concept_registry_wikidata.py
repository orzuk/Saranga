#!/usr/bin/env python3
"""
concept_registry_wikidata.py

Build + maintain a lightweight concept registry backed by Wikidata.

Usage examples
--------------
# 1) Find the Wikidata QID for a subject:
python concept_registry_wikidata.py search --query "graph theory"

# 2) Build a registry for graph theory (given its QID) with up to 300 items:
python concept_registry_wikidata.py build \
  --subjects Q134649 \
  --out concept_registry_graph_theory.json \
  --limit-per-subject 300

# 3) Merge/update an existing registry file:
python concept_registry_wikidata.py build \
  --subjects Q134649 \
  --out concept_registry_graph_theory.json \
  --merge-into concept_registry_graph_theory.json
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests

# Import config for data paths
try:
    from config import WIKIDATA_DIR
except ImportError:
    # Fallback if run standalone
    WIKIDATA_DIR = Path(".")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

DEFAULT_HEADERS = {
    "User-Agent": "Authomathics/1.0 (concept registry builder; contact: none)",
    "Accept": "application/sparql-results+json",
}

# Wikidata QIDs for mathematical concept types we want to include
MATH_CONCEPT_TYPES = {
    "Q24034552": "mathematical concept",
    "Q65943": "theorem",
    "Q108163": "conjecture",
    "Q176645": "lemma",
    "Q11348": "axiom",
    "Q1411246": "identity",  # mathematical identity
    "Q207961": "formula",
    "Q17736": "mathematical proof",
    "Q860609": "inequality",
    "Q5513202": "property",
    "Q35120": "mathematical object",
    "Q217413": "mathematical notation",
    "Q7754": "mathematical analysis concept",
    "Q246672": "mathematical structure",
    "Q1301940": "mathematical problem",
    "Q80083": "paradox",
}

# Types to EXCLUDE (papers, books, conferences, people, transportation, biology, etc.)
EXCLUDE_TYPES = {
    # Publications & Events
    "Q13442814": "scholarly article",
    "Q571": "book",
    "Q7725634": "literary work",
    "Q47461344": "written work",
    "Q3331189": "edition",
    "Q1143604": "proceedings",
    "Q2020153": "academic conference",
    "Q40444998": "workshop",
    "Q21191270": "TV episode",
    "Q5707594": "news article",
    "Q604733": "presentation",
    "Q2100278": "panel",
    "Q1980247": "chapter",
    "Q191067": "article",
    "Q732577": "publication",
    "Q49848": "document",
    "Q234460": "text",

    # People
    "Q5": "human",
    "Q901": "scientist",
    "Q170790": "mathematician",
    "Q1650915": "researcher",

    # Transportation & Infrastructure
    "Q728937": "rack railway",
    "Q1412403": "commuter rail",
    "Q2878855": "bus rapid transit",
    "Q55488": "railway station",
    "Q870": "transport",
    "Q83620": "thoroughfare",
    "Q34442": "road",
    "Q728937": "rack railway",
    "Q1311670": "logging railway",
    "Q1268865": "monorail",
    "Q15145593": "light rail line",
    "Q16858238": "public transport system type",
    "Q5503860": "rail transport",
    "Q55504191": "expressway network",
    "Q3965053": "transit line",
    "Q20202503": "transit system",
    "Q16917": "hospital",
    "Q3914": "school",

    # Biology & Chemistry
    "Q11173": "chemical compound",
    "Q36963": "organism",
    "Q7239": "organism",
    "Q8054": "protein",
    "Q37813": "ecosystem",
    "Q2996394": "biological process",
    "Q4915012": "biological pathway",
    "Q14860489": "molecular entity",
    "Q420927": "protein complex",
    "Q417841": "protein family",
    "Q7187": "gene",
    "Q37748": "chromosome",

    # Names & Linguistics
    "Q170877": "pseudonym type",
    "Q82799": "name",
    "Q27949697": "proper name type",
    "Q1084": "word",
    "Q8171": "word form",
    "Q33104279": "lexeme",
    "Q34770": "language",

    # Places & Geography
    "Q515": "city",
    "Q6256": "country",
    "Q35127": "website",
    "Q7397": "software",
    "Q40056": "software",

    # Chess & Games (not math)
    "Q11410": "game",
    "Q4381595": "heraldic charge",

    # Meta/Wikidata items
    "Q29654788": "Unicode character",
}

# -------------------------
# Small client helpers
# -------------------------

def _get_json(url: str, params: dict, headers: Optional[dict] = None, timeout: int = 30) -> dict:
    h = dict(headers or {})
    r = requests.get(url, params=params, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()

def wikidata_search_entities(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Uses wbsearchentities to find QIDs for a free-text query.
    """
    data = _get_json(
        WIKIDATA_API,
        params={
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "limit": limit,
        },
        headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]},
    )
    out = []
    for item in data.get("search", []):
        out.append({
            "qid": item.get("id"),
            "label": item.get("label"),
            "description": item.get("description"),
            "match": item.get("match", {}).get("text"),
        })
    return out

def sparql_query(query: str, max_retries: int = 5, sleep_s: float = 1.0) -> dict:
    """
    Runs a SPARQL query with basic retry/backoff (Wikidata endpoint throttles).
    """
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(
                SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers=DEFAULT_HEADERS,
                timeout=60,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(sleep_s * attempt)

# -------------------------
# Registry
# -------------------------

@dataclass
class RegistryItem:
    qid: str
    label: str
    description: Optional[str] = None
    aliases: List[str] = None
    main_subjects: List[str] = None
    instance_of: List[str] = None
    concept_type: str = "concept"  # theorem, conjecture, lemma, axiom, formula, etc.

    def to_dict(self) -> dict:
        return {
            "qid": self.qid,
            "label": self.label,
            "description": self.description,
            "aliases": self.aliases or [],
            "main_subjects": self.main_subjects or [],
            "instance_of": self.instance_of or [],
            "concept_type": self.concept_type,
            "source": "wikidata",
        }

class ConceptRegistry:
    """
    In-memory registry with fast-ish string matching.
    Stores:
      - items[qid] -> item dict
      - index: term(lower) -> list of qids
    """

    def __init__(self, items: Optional[Dict[str, dict]] = None):
        self.items: Dict[str, dict] = items or {}
        self._term_index: Dict[str, List[str]] = {}
        self.rebuild_index()

    @staticmethod
    def load(path: str | Path) -> "ConceptRegistry":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", {})
        return ConceptRegistry(items=items)

    def save(self, path: str | Path, metadata: Optional[dict] = None) -> None:
        p = Path(path)
        out = {
            "schema": "authomathics.concept_registry.v1",
            "metadata": metadata or {},
            "items": self.items,
        }
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    def rebuild_index(self) -> None:
        self._term_index.clear()
        for qid, it in self.items.items():
            label = (it.get("label") or "").strip()
            aliases = it.get("aliases") or []
            terms = [label] + list(aliases)
            for t in terms:
                t2 = " ".join(t.lower().split())
                if not t2:
                    continue
                self._term_index.setdefault(t2, []).append(qid)

    def upsert(self, item: RegistryItem) -> None:
        self.items[item.qid] = item.to_dict()
        # cheap incremental update
        self.rebuild_index()

    def match_text(self, text_lower: str, min_len: int = 4) -> List[Dict[str, Any]]:
        """
        Baseline matcher: find registry terms that appear as substrings.
        This is intentionally simple; you can later upgrade to token matching, Aho–Corasick, embeddings, etc.
        """
        hits = []
        # A cheap filter: only test terms that are long enough
        for term, qids in self._term_index.items():
            if len(term) < min_len:
                continue
            if term in text_lower:
                for qid in qids:
                    it = self.items[qid]
                    hits.append({
                        "qid": qid,
                        "label": it.get("label"),
                        "description": it.get("description"),
                        "aliases": it.get("aliases", []),
                        "matched_term": term,
                        "method": "substring",
                        "confidence": 0.5,
                    })
        return hits

# -------------------------
# Wikidata extraction
# -------------------------

def fetch_subject_items(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Pull actual mathematical concepts related to a subject using multiple strategies.
    Returns concepts, theorems, definitions - NOT papers/books/conferences.
    """
    all_items: Dict[str, RegistryItem] = {}

    # Strategy 1: Items that are "part of" (P361) or "studied in" (P2579) the subject
    # and are instances of mathematical concept types
    print(f"  [1/5] Fetching concepts by field...")
    items = _fetch_concepts_by_field(subject_qid, limit)
    for it in items:
        all_items[it.qid] = it
    print(f"        Found {len(items)} items, total unique: {len(all_items)}")

    # Strategy 2: Subclasses of concepts within the field
    print(f"  [2/5] Fetching subclass concepts...")
    items = _fetch_subclass_concepts(subject_qid, limit)
    for it in items:
        if it.qid not in all_items:
            all_items[it.qid] = it
    print(f"        Found {len(items)} items, total unique: {len(all_items)}")

    # Strategy 3: Items with the subject in their "field of this occupation" or direct links
    print(f"  [3/5] Fetching direct field concepts...")
    items = _fetch_direct_field_concepts(subject_qid, limit)
    for it in items:
        if it.qid not in all_items:
            all_items[it.qid] = it
    print(f"        Found {len(items)} items, total unique: {len(all_items)}")

    # Strategy 4: Directly fetch theorems, lemmas, conjectures
    print(f"  [4/5] Fetching theorems and results...")
    try:
        items = _fetch_theorems_and_results(subject_qid, limit)
        for it in items:
            if it.qid not in all_items:
                all_items[it.qid] = it
        print(f"        Found {len(items)} items, total unique: {len(all_items)}")
    except Exception as e:
        print(f"        Warning: Strategy 4 failed: {e}")

    # Strategy 5: Named theorems (by label pattern)
    print(f"  [5/5] Fetching named theorems by pattern...")
    try:
        items = _fetch_named_theorems(subject_qid, limit)
        for it in items:
            if it.qid not in all_items:
                all_items[it.qid] = it
        print(f"        Found {len(items)} items, total unique: {len(all_items)}")
    except Exception as e:
        print(f"        Warning: Strategy 5 failed: {e}")

    return list(all_items.values())


def _fetch_concepts_by_field(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Fetch items that are studied in / part of the subject field,
    filtering to only include actual mathematical concepts.
    """
    # Build exclusion filter for unwanted types
    exclude_filter = " ".join([f"FILTER(?type != wd:{qid})" for qid in EXCLUDE_TYPES.keys()])

    q = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel
           (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
           (GROUP_CONCAT(DISTINCT ?type; separator="|") AS ?types)
    WHERE {{
      # Items studied in or part of the subject field
      {{ ?item wdt:P2579 wd:{subject_qid} . }}  # studied in
      UNION
      {{ ?item wdt:P361 wd:{subject_qid} . }}   # part of
      UNION
      {{ ?item wdt:P361 ?parent . ?parent wdt:P361* wd:{subject_qid} . }}  # nested part-of

      # Must have a type
      ?item wdt:P31 ?type .

      # Exclude unwanted types (papers, books, etc.)
      {exclude_filter}

      OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?itemLabel ?itemDescription ?typeLabel
    LIMIT {int(limit)}
    """
    return _parse_sparql_results(sparql_query(q), subject_qid)


def _fetch_subclass_concepts(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Fetch mathematical concepts that are subclasses within the field.
    E.g., "Hamiltonian path" is a subclass of "path (graph theory)".
    """
    # Build list of good concept types to look for
    concept_type_values = " ".join([f"wd:{qid}" for qid in MATH_CONCEPT_TYPES.keys()])

    q = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel
           (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
           (GROUP_CONCAT(DISTINCT ?type; separator="|") AS ?types)
    WHERE {{
      # Find items that are subclasses of something in the field
      ?item wdt:P279+ ?parent .
      {{ ?parent wdt:P2579 wd:{subject_qid} . }}
      UNION
      {{ ?parent wdt:P361 wd:{subject_qid} . }}

      # Get the type
      OPTIONAL {{ ?item wdt:P31 ?type . }}

      # Must have an English label (filters out junk)
      ?item rdfs:label ?itemLabel FILTER(lang(?itemLabel) = "en") .

      OPTIONAL {{ ?item schema:description ?itemDescription FILTER(lang(?itemDescription) = "en") }}
      OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?itemLabel ?itemDescription ?typeLabel
    LIMIT {int(limit)}
    """
    return _parse_sparql_results(sparql_query(q), subject_qid)


def _fetch_direct_field_concepts(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Fetch items that are instances of mathematical concept types
    and have the subject as their field (P101) or are named after mathematicians in the field.
    """
    concept_type_values = " ".join([f"wd:{qid}" for qid in MATH_CONCEPT_TYPES.keys()])

    q = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel
           (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
           (GROUP_CONCAT(DISTINCT ?type; separator="|") AS ?types)
    WHERE {{
      VALUES ?conceptType {{ {concept_type_values} }}

      # Items that are instances of math concept types
      ?item wdt:P31/wdt:P279* ?conceptType .

      # And are related to our subject field
      {{
        ?item wdt:P101 wd:{subject_qid} .  # field of work
      }}
      UNION
      {{
        ?item wdt:P361 wd:{subject_qid} .  # part of
      }}
      UNION
      {{
        ?item wdt:P2579 wd:{subject_qid} . # studied in
      }}

      ?item wdt:P31 ?type .

      OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?itemLabel ?itemDescription ?typeLabel
    LIMIT {int(limit)}
    """
    return _parse_sparql_results(sparql_query(q), subject_qid)


def _fetch_theorems_and_results(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Strategy 4: Directly fetch theorems, lemmas, conjectures, axioms, etc.
    that are related to the subject via main subject (P921) or field (P101).
    This is more targeted than the other strategies.
    """
    # Types we specifically want to find
    theorem_types = [
        "Q65943",    # theorem
        "Q108163",   # conjecture
        "Q176645",   # lemma
        "Q11348",    # axiom
        "Q207961",   # formula
        "Q860609",   # inequality (mathematical)
        "Q1411246",  # mathematical identity
        "Q80083",    # paradox
        "Q1301940",  # mathematical problem
    ]
    type_values = " ".join([f"wd:{qid}" for qid in theorem_types])

    # Simplified query - removed the slow FILTER(CONTAINS...) clause
    q = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel
           (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
           (GROUP_CONCAT(DISTINCT ?type; separator="|") AS ?types)
    WHERE {{
      VALUES ?theoremType {{ {type_values} }}

      # Items that are instances of theorem types
      ?item wdt:P31 ?theoremType .

      # And are related to our subject field
      {{
        ?item wdt:P921 wd:{subject_qid} .  # main subject
      }}
      UNION
      {{
        ?item wdt:P101 wd:{subject_qid} .  # field of work
      }}
      UNION
      {{
        ?item wdt:P2579 wd:{subject_qid} . # studied in
      }}
      UNION
      {{
        ?item wdt:P361 wd:{subject_qid} .  # part of
      }}

      ?item wdt:P31 ?type .

      OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?itemLabel ?itemDescription ?typeLabel
    LIMIT {int(limit)}
    """
    return _parse_sparql_results(sparql_query(q), subject_qid)


def _fetch_named_theorems(subject_qid: str, limit: int = 200) -> List[RegistryItem]:
    """
    Strategy 5: Fetch items whose label ends with common theorem name patterns
    (e.g., "X theorem", "Y lemma", "Z conjecture") within the field.
    """
    q = f"""
    SELECT DISTINCT ?item ?itemLabel ?itemDescription ?typeLabel
           (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
           (GROUP_CONCAT(DISTINCT ?type; separator="|") AS ?types)
    WHERE {{
      # Items with names matching theorem patterns
      ?item rdfs:label ?itemLabel FILTER(lang(?itemLabel) = "en") .

      # Label must end with theorem/lemma/conjecture/etc
      FILTER(
        REGEX(?itemLabel, "(theorem|lemma|conjecture|axiom|formula|inequality|identity|paradox|law|principle|rule|criterion|condition)$", "i")
      )

      # Must have a type
      ?item wdt:P31 ?type .

      # Related to our subject
      {{
        ?item wdt:P921 wd:{subject_qid} .
      }}
      UNION
      {{
        ?item wdt:P2579 wd:{subject_qid} .
      }}
      UNION
      {{
        ?item wdt:P361 wd:{subject_qid} .
      }}
      UNION
      {{
        ?item wdt:P101 wd:{subject_qid} .
      }}

      OPTIONAL {{ ?item schema:description ?itemDescription FILTER(lang(?itemDescription) = "en") }}
      OPTIONAL {{ ?item skos:altLabel ?alias FILTER (lang(?alias)="en") }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?item ?itemLabel ?itemDescription ?typeLabel
    LIMIT {int(limit)}
    """
    return _parse_sparql_results(sparql_query(q), subject_qid)


def _is_excluded_type(instance_of_qids: List[str]) -> bool:
    """Check if any of the instance_of types are in our exclusion list."""
    for qid in instance_of_qids:
        if qid in EXCLUDE_TYPES:
            return True
    return False


def _is_valid_math_concept(label: str, description: str, instance_of_qids: List[str]) -> bool:
    """
    Validate that an item is likely a valid mathematical concept.
    Returns False for items that are clearly not math concepts.
    """
    label_lower = label.lower() if label else ""
    desc_lower = description.lower() if description else ""

    # Check for excluded types
    if _is_excluded_type(instance_of_qids):
        return False

    # Label-based exclusions (things that slipped through)
    label_exclusions = [
        "railway", "railroad", "rail line", "bus rapid", "expressway",
        "commuter", "transit", "tramway", "stadtbahn", "pendeltåg",
        "proastiakos", "monorack", "shuttle bus", "bus service",
        "highway", "motorway", "freeway",
    ]
    if any(excl in label_lower for excl in label_exclusions):
        return False

    # Description-based exclusions for things without proper types
    desc_exclusions = [
        "rail", "train", "bus", "transport", "highway", "expressway",
        "commuter", "transit", "tramway",
        "pseudonym", "alias", "pen name", "stage name",
        "heraldic", "chess", "coat of arms",
        "metabolic network", "biological", "protein", "enzyme",
        "active researcher", "mathematician", "scientist",
    ]
    if any(excl in desc_lower for excl in desc_exclusions):
        return False

    return True


def _parse_sparql_results(data: dict, subject_qid: str) -> List[RegistryItem]:
    """Parse SPARQL results into RegistryItem objects."""
    rows = data.get("results", {}).get("bindings", [])
    out: List[RegistryItem] = []
    seen_qids = set()

    for r in rows:
        item_uri = r["item"]["value"]
        qid = item_uri.rsplit("/", 1)[-1]

        # Skip duplicates
        if qid in seen_qids:
            continue
        seen_qids.add(qid)

        label = r.get("itemLabel", {}).get("value", qid)

        # Skip items where label is just the QID (no English label)
        if label == qid or label.startswith("Q") and label[1:].isdigit():
            continue

        desc = r.get("itemDescription", {}).get("value")

        # Skip items that look like papers/articles/non-math based on description
        if desc and any(skip in desc.lower() for skip in [
            # Publications
            "scientific article", "scholarly article", "paper published",
            "book published", "book edition", "academic conference",
            "episode of", "news article", "written work", "textbook",
            "proceedings", "chapter from", "published in", "journal",
            # Transportation
            "railway", "railroad", "rail service", "rail transport",
            "commuter", "transit", "bus service", "bus network",
            "expressway", "highway", "tramway", "monorail", "subway",
            "train service", "rail line", "transport system",
            # Biology/Chemistry
            "protein", "enzyme", "metabolic", "biological", "organism",
            "chemical", "molecule", "pathway", "gene", "chromosome",
            "species", "cell", "cellular",
            # People
            "mathematician", "researcher", "scientist", "professor",
            "ph.d", "academic", "born", "died",
            # Names/Linguistics
            "pseudonym", "alias", "pen name", "stage name", "nickname",
            "word", "term used", "name type",
            # Places/Other
            "city in", "country", "region", "province", "located in",
            "heraldic", "coat of arms", "chess",
        ]):
            continue

        aliases_raw = r.get("aliases", {}).get("value", "")
        aliases = [a.strip() for a in aliases_raw.split("|") if a.strip()]

        types_raw = r.get("types", {}).get("value", "")
        types = [x.strip().rsplit("/", 1)[-1] for x in types_raw.split("|") if x.strip()]

        # Final validation - skip items that are not valid math concepts
        if not _is_valid_math_concept(label, desc, types):
            continue

        # Classify the concept type
        concept_type = _classify_concept_type(types)

        out.append(RegistryItem(
            qid=qid,
            label=label,
            description=desc,
            aliases=aliases,
            main_subjects=[subject_qid],
            instance_of=types,
            concept_type=concept_type,
        ))

    return out


def _classify_concept_type(instance_of_qids: List[str]) -> str:
    """Classify what kind of mathematical concept this is."""
    for qid in instance_of_qids:
        if qid in MATH_CONCEPT_TYPES:
            return MATH_CONCEPT_TYPES[qid]

    # Check for subclass relationships
    type_priority = [
        ("Q65943", "theorem"),
        ("Q108163", "conjecture"),
        ("Q176645", "lemma"),
        ("Q11348", "axiom"),
        ("Q207961", "formula"),
        ("Q860609", "inequality"),
        ("Q24034552", "mathematical concept"),
    ]
    for qid, name in type_priority:
        if qid in instance_of_qids:
            return name

    return "concept"  # default

def build_registry(subject_qids: List[str], limit_per_subject: int = 200) -> ConceptRegistry:
    reg = ConceptRegistry()
    for sqid in subject_qids:
        items = fetch_subject_items(sqid, limit=limit_per_subject)
        for it in items:
            reg.upsert(it)
    return reg

# -------------------------
# CLI
# -------------------------

def cmd_search(args: argparse.Namespace) -> None:
    hits = wikidata_search_entities(args.query, limit=args.limit)
    print(json.dumps(hits, indent=2, ensure_ascii=False))

def cmd_build(args: argparse.Namespace) -> None:
    subject_qids = args.subjects
    reg_new = build_registry(subject_qids, limit_per_subject=args.limit_per_subject)

    # Ensure output directory exists
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # merge if requested
    if args.merge_into:
        base = ConceptRegistry.load(args.merge_into)
        # naive merge: new overwrites old on qid collision
        base.items.update(reg_new.items)
        base.rebuild_index()
        base.save(args.out, metadata={"subjects": subject_qids, "limit_per_subject": args.limit_per_subject})
    else:
        reg_new.save(args.out, metadata={"subjects": subject_qids, "limit_per_subject": args.limit_per_subject})

    print(f"[OK] Wrote registry: {args.out}")

def main() -> None:
    # Default output path uses config
    default_out = WIKIDATA_DIR / "concept_registry.json"

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_s = sub.add_parser("search", help="Search Wikidata for a QID by text")
    ap_s.add_argument("--query", required=True)
    ap_s.add_argument("--limit", type=int, default=10)
    ap_s.set_defaults(func=cmd_search)

    ap_b = sub.add_parser("build", help="Build a registry JSON from subject QIDs (P921 main subject)")
    ap_b.add_argument("--subjects", nargs="+", required=True, help="Subject QIDs, e.g. Q134649")
    ap_b.add_argument("--limit-per-subject", type=int, default=200)
    ap_b.add_argument("--out", default=str(default_out), help=f"Output file (default: {default_out})")
    ap_b.add_argument("--merge-into", default=None, help="If set, merge into existing registry JSON")
    ap_b.set_defaults(func=cmd_build)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
