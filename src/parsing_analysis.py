#!/usr/bin/env python3
import json
import argparse
import csv
import sys
from pathlib import Path
from collections import Counter, defaultdict

# Resolve math_classes from src/LLMVersion/ (single source of truth)
_LLMV = Path(__file__).resolve().parent / 'LLMVersion'
if str(_LLMV) not in sys.path:
    sys.path.insert(0, str(_LLMV))

from math_classes import PaperGraph, TheoremLike, Proof


def analyze_graph(pg: PaperGraph) -> dict:
    """
    Return a dict with diagnostic stats for one parsed paper.

    Orphan proofs: Proofs whose `parent_id` is None or not a theorem-like id.
    Orphan theorems: Theorem-like objects with no proof pointing to them via parent_id.
    """
    objects = list(pg.objects.values())
    relations = pg.relations

    # --- basic counts ---
    kinds = Counter(obj.kind for obj in objects)
    rel_types = Counter(r.relation_type for r in relations)

    # --- isolated objects: no relation touching them at all ---
    ids_with_edges = set()
    for r in relations:
        ids_with_edges.add(r.source_id)
        ids_with_edges.add(r.target_id)
    isolated_ids = [obj_id for obj_id in pg.objects.keys() if obj_id not in ids_with_edges]

    # --- theorem-like + proofs ---
    theorems = [o for o in objects if isinstance(o, TheoremLike)]
    proofs = [o for o in objects if isinstance(o, Proof)]

    theorem_ids = {t.id for t in theorems}
    theorem_has_proof = {t.id: False for t in theorems}

    orphan_proofs = []
    for p in proofs:
        parent = getattr(p, "parent_id", None)
        # If the parent is a theorem-like object (by id), mark it as having a proof
        if parent in theorem_ids:
            theorem_has_proof[parent] = True
        else:
            orphan_proofs.append(p.id)

    orphan_theorems = [tid for tid, has in theorem_has_proof.items() if not has]

    stats = {
        "paper_id": pg.paper_id,
        "num_objects": len(objects),
        "kinds": dict(kinds),
        "num_relations": len(relations),
        "relations_by_type": dict(rel_types),
        "num_isolated_objects": len(isolated_ids),
        "isolated_object_ids": isolated_ids,
        "num_theorems": len(theorems),
        "num_proofs": len(proofs),
        "num_orphan_proofs": len(orphan_proofs),
        "orphan_proof_ids": orphan_proofs,
        "num_orphan_theorems": len(orphan_theorems),
        "orphan_theorem_ids": orphan_theorems,
    }
    return stats


def load_papergraph_from_json(path: Path) -> PaperGraph:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PaperGraph.from_dict(data)


def flatten_rows_for_csv(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Take list of analysis dicts and flatten into CSV-ready rows.

    - Expands 'kinds' into columns kind_<kind>
    - Expands 'relations_by_type' into columns rel_<type>
    - Keeps key meta columns (paper_id, num_*, orphan_* ids as semicolon-joined strings)
    """
    # Collect all possible kinds and relation types across all papers
    all_kinds = set()
    all_rel_types = set()
    for r in rows:
        all_kinds.update(r.get("kinds", {}).keys())
        all_rel_types.update(r.get("relations_by_type", {}).keys())

    all_kinds = sorted(all_kinds)
    all_rel_types = sorted(all_rel_types)

    flat_rows = []
    for r in rows:
        fr = {
            "paper_id": r["paper_id"],
            "num_objects": r["num_objects"],
            "num_relations": r["num_relations"],
            "num_isolated_objects": r["num_isolated_objects"],
            "num_theorems": r["num_theorems"],
            "num_proofs": r["num_proofs"],
            "num_orphan_proofs": r["num_orphan_proofs"],
            "num_orphan_theorems": r["num_orphan_theorems"],
            # join IDs so they fit in a single CSV cell
            "orphan_proof_ids": ";".join(r.get("orphan_proof_ids", [])),
            "orphan_theorem_ids": ";".join(r.get("orphan_theorem_ids", [])),
            "isolated_object_ids": ";".join(r.get("isolated_object_ids", [])),
        }

        # add kind_<kind> columns
        kinds = r.get("kinds", {})
        for k in all_kinds:
            fr[f"kind_{k}"] = kinds.get(k, 0)

        # add rel_<type> columns
        rels = r.get("relations_by_type", {})
        for t in all_rel_types:
            fr[f"rel_{t}"] = rels.get(t, 0)

        flat_rows.append(fr)

    # Column order
    base_cols = [
        "paper_id",
        "num_objects",
        "num_relations",
        "num_isolated_objects",
        "num_theorems",
        "num_proofs",
        "num_orphan_proofs",
        "num_orphan_theorems",
        "orphan_proof_ids",
        "orphan_theorem_ids",
        "isolated_object_ids",
    ]
    kind_cols = [f"kind_{k}" for k in all_kinds]
    rel_cols = [f"rel_{t}" for t in all_rel_types]
    fieldnames = base_cols + kind_cols + rel_cols

    return flat_rows, fieldnames


def main(json_dir: str, out_csv: str | None):
    json_path = Path(json_dir)
    if not json_path.is_dir():
        raise SystemExit(f"{json_dir} is not a directory")

    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON files found in {json_dir}")

    rows = []

    for jf in json_files:
        try:
            pg = load_papergraph_from_json(jf)
        except Exception as e:
            print(f"[WARN] Failed to load {jf}: {e}")
            continue

        stats = analyze_graph(pg)
        rows.append(stats)

        # crude on-screen summary
        print(f"\n=== {stats['paper_id']} ===")
        print("  #objects:", stats["num_objects"])
        print("  kinds:", stats["kinds"])
        print("  #relations:", stats["num_relations"],
              "   relations_by_type:", stats["relations_by_type"])
        print("  #isolated objects:", stats["num_isolated_objects"])
        print("  #theorems:", stats["num_theorems"],
              "  #proofs:", stats["num_proofs"])
        print("  #orphan proofs:", stats["num_orphan_proofs"],
              "  ids:", stats["orphan_proof_ids"])
        print("  #orphan theorems:", stats["num_orphan_theorems"],
              "  ids:", stats["orphan_theorem_ids"])

    print(f"\n[INFO] Analyzed {len(rows)} papers.")

    if out_csv:
        flat_rows, fieldnames = flatten_rows_for_csv(rows)
        out_path = Path(out_csv)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in flat_rows:
                writer.writerow(r)
        print(f"[INFO] Wrote CSV summary to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Post-processing analysis for parsed arXiv papers (JSON -> stats + CSV)."
    )
    parser.add_argument(
        "json_dir",
        help="Directory containing *.json files produced by run_pipeline.py (or LLMVersion/run_parse_papers.py)",
    )
    parser.add_argument(
        "--out-csv",
        default=None,
        help="Path to CSV file for paper-level statistics (optional).",
    )
    args = parser.parse_args()
    main(args.json_dir, args.out_csv)
