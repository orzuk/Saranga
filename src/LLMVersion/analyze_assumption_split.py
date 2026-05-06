"""
Scan parsed JSONs from the 1000-paper run and extract all theorem-like nodes
with their assumption/conclusion splits into a single analysis JSON.

Usage (on cluster):
    python analyze_assumption_split.py /path/to/parsed_math_CO_manual_1000

Usage (local, if you copied some JSONs):
    python analyze_assumption_split.py /path/to/parsed_dir

Output: assumption_split_analysis.json in the same directory.
"""

import json
import sys
from pathlib import Path

THEOREM_LIKE_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim", "conjecture", "problem"}


def analyze(parsed_dir: str):
    parsed_path = Path(parsed_dir)
    json_files = sorted(parsed_path.rglob("*_manual.json"))
    print(f"Found {len(json_files)} JSON files")

    results = {"empty_conclusions": [], "has_conclusions": [], "summary": {}}

    for jf in json_files:
        with open(jf) as f:
            data = json.load(f)

        paper_id = data.get("metadata", {}).get("paper_id", jf.stem)

        for node in data.get("nodes", []):
            ntype = node.get("type", "").lower()
            if ntype not in THEOREM_LIKE_TYPES:
                continue

            assumptions = node.get("assumptions", [])
            conclusions = node.get("conclusions", [])
            statement = node.get("statement", "")

            entry = {
                "paper_id": paper_id,
                "node_id": node.get("id", ""),
                "type": ntype,
                "name": node.get("name", ""),
                "assumptions": assumptions,
                "conclusions": conclusions,
                "statement": statement,
            }

            if not conclusions:
                results["empty_conclusions"].append(entry)
            else:
                results["has_conclusions"].append(entry)

    n_empty = len(results["empty_conclusions"])
    n_has = len(results["has_conclusions"])
    total = n_empty + n_has
    results["summary"] = {
        "total_theorem_like": total,
        "empty_conclusions": n_empty,
        "has_conclusions": n_has,
        "pct_empty": round(100 * n_empty / total, 1) if total else 0,
    }

    out_path = Path.home() / "assumption_split_analysis.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Total theorem-like: {total}")
    print(f"Empty conclusions:  {n_empty} ({results['summary']['pct_empty']}%)")
    print(f"Has conclusions:    {n_has}")
    print(f"Written to: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <parsed_dir>")
        sys.exit(1)
    analyze(sys.argv[1])
