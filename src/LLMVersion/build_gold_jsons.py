"""
Build per-paper gold-standard JSON files in the unified format (see
annotation_schema.md / math_classes.py::PaperGraph.to_unified_dict).

Reads every Gold_Standard_*.csv in the working directory, groups rows by
paper_id, and writes one gold_standard_jsons/{paper_id}.json per paper.

Each node is seeded from the CSV row (raw_latex + clean_text) and has
placeholder slots for the remaining unified-format fields (name, label,
env_name, assumptions/conclusions, proves, definiendum/genus/differentia,
etc.) so a human can later fill them in. An empty `edges` list is also
emitted so the annotator can add cross-references (uses / follows_from /
generalizes / equivalent_to).

CSV → structure-type mapping is taken from the filename suffix
(Definitions → definition, Theorems → theorem, ...).

Usage:
    python build_gold_jsons.py
    python build_gold_jsons.py --csv-dir . --out-dir gold_standard_jsons
"""

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


# Filename suffix (plural) -> unified singular type
CSV_TO_TYPE: Dict[str, str] = {
    "Definitions": "definition",
    "Theorems": "theorem",
    "Lemmas": "lemma",
    "Propositions": "proposition",
    "Corollaries": "corollary",
    "Claims": "claim",
    "Conjectures": "conjecture",
    "Problems": "problem",
    "Proofs": "proof",
    "Algorithms": "algorithm",
    "Tables": "table",
}

# Short id prefix per type
ID_PREFIX: Dict[str, str] = {
    "definition": "def",
    "theorem": "thm",
    "lemma": "lem",
    "proposition": "prop",
    "corollary": "cor",
    "claim": "clm",
    "conjecture": "conj",
    "problem": "prob",
    "proof": "prf",
    "algorithm": "alg",
    "table": "tbl",
    "equation": "eq",
}

THEOREM_LIKE = {
    "theorem", "lemma", "proposition", "corollary",
    "claim", "conjecture", "problem",
}


def _normalize_paper_id(pid: str) -> str:
    """
    Normalize a gold-CSV paper_id into the canonical form used for the
    output filename: underscores -> dots and trailing v\\d+ stripped so that
    `1204.0109v1` and `1204.0109` collapse to the same paper.
    """
    pid = pid.strip().replace("_", ".")
    pid = re.sub(r"v\d+$", "", pid)
    return pid


def _blank_node(node_type: str, node_id: str, index: int, row: Dict[str, str]) -> Dict[str, Any]:
    """
    Build a unified-format node with data from the CSV row and empty
    placeholders for everything else. Keys are kept in a stable order
    so the hand-editable JSON is pleasant to read.
    """
    raw_latex = (row.get("Gold_Standard_raw_latex") or "").strip()
    clean_text = (row.get("Gold_Standard_clean_text") or "").strip()
    label = (row.get("label") or "").strip() or None  # only Problems has this

    node: Dict[str, Any] = {
        # --- identity ---
        "id": node_id,
        "type": node_type,
        "index": index,

        # --- common human-editable fields ---
        "name": None,               # e.g. "Strong Law of Large Numbers"
        "label": label,             # \label{...}
        "env_name": None,           # e.g. "theorem", "definition"
        "section": None,            # enclosing section title, if known

        # --- content (seeded from CSV) ---
        "statement": clean_text,    # used by Jaccard eval
        "raw_latex": raw_latex,
        "clean_text": clean_text,

        # --- spans (optional, research) ---
        "spans": [],
    }

    # Type-specific placeholders
    if node_type in THEOREM_LIKE:
        node["assumptions"] = []          # List[str] — "Let / Suppose / Assume ..."
        node["conclusions"] = []          # List[str] — "Then ..."
        node["assumption_spans"] = []     # List[Span] (research)
        node["statement_spans"] = []      # List[Span] (research)

    if node_type == "proof":
        node["proves"] = ""               # id of the theorem-like node this proves
        node["proof_strategy"] = None     # "induction" / "contradiction" / ...
        node["strategy_tags"] = []
        node["steps"] = []                # List[Span]

    if node_type == "definition":
        node["definiendum"] = None        # Span: the thing being defined
        node["genus"] = None              # Span: "is a square matrix", ...
        node["differentia"] = []          # List[Span]: distinguishing conditions
        node["equivalences"] = []         # List[Span]: "equivalently, ..."
        node["notation_introduced"] = []  # List[Span]: new symbols

    if node_type == "algorithm":
        node["input"] = []                # List[str]: "name: description"
        node["output"] = []
        node["preconditions"] = []
        node["postconditions"] = []
        node["steps"] = []

    if node_type == "table":
        node["caption"] = None
        node["cells"] = []

    if node_type == "problem":
        # Problem extends TheoremLike with extra optional fields
        node["problem_type"] = None
        node["constraints"] = None
        node["objective"] = None

    return node


def _read_gold_csv(csv_path: Path, node_type: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Return {paper_id: [row_dict, row_dict, ...]} for a single gold CSV.
    Paper IDs are normalized to dot form.
    """
    out: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    with csv_path.open("r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        # Strip whitespace + BOM on header names
        reader.fieldnames = [name.strip().lstrip("\ufeff") for name in reader.fieldnames]
        for row in reader:
            row = {(k.strip() if k else k): (v if v is not None else "") for k, v in row.items()}
            pid = row.get("paper_id", "").strip()
            if not pid:
                continue
            pid = _normalize_paper_id(pid)
            # Skip empty-content rows (headers sometimes repeat, or blank lines)
            if not row.get("Gold_Standard_raw_latex") and not row.get("Gold_Standard_clean_text"):
                continue
            out[pid].append(row)
    return out


def build(csv_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # paper_id -> list of nodes (accumulated across all structure types)
    papers: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    # per-paper running index per type
    counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    csv_files = sorted(csv_dir.glob("Gold_Standard_*.csv"))
    if not csv_files:
        print(f"No Gold_Standard_*.csv files found in {csv_dir}")
        return

    print(f"Found {len(csv_files)} gold CSV files")

    for csv_path in csv_files:
        m = re.match(r"Gold_Standard_(.+)\.csv$", csv_path.name)
        if not m:
            continue
        suffix = m.group(1)
        node_type = CSV_TO_TYPE.get(suffix)
        if node_type is None:
            print(f"  [skip] unknown structure type: {csv_path.name}")
            continue

        per_paper = _read_gold_csv(csv_path, node_type)
        total_rows = sum(len(v) for v in per_paper.values())
        print(f"  {csv_path.name}: {total_rows} rows across {len(per_paper)} papers")

        for pid, rows in per_paper.items():
            for row in rows:
                counters[pid][node_type] += 1
                idx = counters[pid][node_type]
                node_id = f"{ID_PREFIX[node_type]}_{idx}"
                papers[pid].append(_blank_node(node_type, node_id, idx, row))

    # Write one JSON per paper
    for pid, nodes in sorted(papers.items()):
        doc: Dict[str, Any] = {
            "metadata": {
                "paper_id": pid,
                "source": "gold_standard_csvs",
                "note": (
                    "Seeded from Gold_Standard_*.csv. Fill in name/label/env_name, "
                    "split assumptions/conclusions for theorem-like nodes, set "
                    "`proves` on proofs, and add edges for cross-references."
                ),
            },
            "nodes": nodes,
            # Placeholder for human-annotated cross-references. Each edge:
            #   {"source": <node_id>, "target": <node_id>,
            #    "type": "uses" | "follows_from" | "generalizes" | "equivalent_to" | "dependency",
            #    "confidence": <optional float>}
            "edges": [],
        }
        out_path = out_dir / f"{pid}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"  wrote {out_path} ({len(nodes)} nodes)")

    print(f"\nDone. {len(papers)} gold-standard JSONs in {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv-dir", type=Path, default=Path("."),
                    help="Directory containing Gold_Standard_*.csv files.")
    ap.add_argument("--out-dir", type=Path, default=Path("gold_standard_jsons"),
                    help="Output directory for per-paper gold JSONs.")
    args = ap.parse_args()
    build(args.csv_dir, args.out_dir)


if __name__ == "__main__":
    main()
