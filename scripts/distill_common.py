#!/usr/bin/env python3
"""Shared helpers of the distillation drivers (silver_distillation_merged.py,
distill_units.py, compare_distillers.py): the scored node types and their gold-CSV
files, the silver-JSON -> gold-CSV conversion, the train/val/test split, rule
snapshots, and parsing a paper with the rule set in a given directory.

Callers put src/ and src/LLMVersion/ on sys.path first.
"""

import csv
import json
import re
from pathlib import Path

from latex_facts import find_main_tex

REPO = Path(__file__).resolve().parent.parent

# the 14 node types distillation scores, and the gold CSV of each
FNAME_MAP = {
    "definition":  "Gold_Standard_Definitions.csv",
    "theorem":     "Gold_Standard_Theorems.csv",
    "lemma":       "Gold_Standard_Lemmas.csv",
    "proof":       "Gold_Standard_Proofs.csv",
    "proposition": "Gold_Standard_Propositions.csv",
    "corollary":   "Gold_Standard_Corollaries.csv",
    "claim":       "Gold_Standard_Claims.csv",
    "conjecture":  "Gold_Standard_Conjectures.csv",
    "problem":     "Gold_Standard_Problems.csv",
    "remark":      "Gold_Standard_Remarks.csv",
    "algorithm":   "Gold_Standard_Algorithms.csv",
    "example":     "Gold_Standard_Examples.csv",
    "assumption":  "Gold_Standard_Assumptions.csv",
    "open_problem":"Gold_Standard_OpenProblems.csv",
}
TYPES = list(FNAME_MAP)


def convert_t2_to_gold_csv(t2_json_path: Path, structure_type: str,
                           out_dir: Path) -> tuple[Path, int]:
    """Append the `structure_type` nodes of one silver JSON to that type's gold CSV.
    Returns (csv_path, n_items_added)."""
    d = json.load(open(t2_json_path, encoding='utf-8'))
    # the filename stem is the paper_id, as in --pilot-papers
    pid = t2_json_path.stem
    rows = []
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
            continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        clean = n.get("statement_clean") or n.get("clean_text") or ""
        if raw.strip():
            rows.append({"paper_id": pid, "Gold_Standard_raw_latex": raw,
                         "Gold_Standard_clean_text": clean})
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / FNAME_MAP[structure_type]
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "Gold_Standard_raw_latex",
                                          "Gold_Standard_clean_text"])
        if write_header:
            w.writeheader()
        w.writerows(rows)
    return csv_path, len(rows)


def load_gold_texts(gold_csv: Path) -> dict:
    """Return {paper_id: [raw_latex, ...]} for one type's gold CSV."""
    out = {}
    if not gold_csv.exists():
        return out
    with open(gold_csv, encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            pid = (row.get('paper_id') or '').strip()
            raw = (row.get('Gold_Standard_raw_latex') or '').strip()
            if pid and raw:
                out.setdefault(pid, []).append(raw)
    return out


# ---------------------------------------------------------------------------
# Train/val/test split
# ---------------------------------------------------------------------------

SILVER_METADATA = REPO / "corpus" / "silver" / "metadata.csv"


def load_splits(metadata_csv: Path = SILVER_METADATA) -> dict:
    """{paper_id: split} from the silver corpus index — the one source of truth.

    The split lives in metadata.csv, not in the directory tree, precisely so it
    can be redrawn. Everything that selects papers should consult it rather than
    hardcoding lists.
    """
    # A paper has ONE row per extraction, so every train/test paper ALSO has a
    # `pool` row (its older v3 extraction). Taking the first row seen would
    # label the whole train set "pool" and silently defeat the split guard, so
    # the specific splits win over the catch-all.
    precedence = {"train": 3, "test": 3, "val": 3, "pool": 1}
    out, rank = {}, {}
    if not Path(metadata_csv).exists():
        return out
    with open(metadata_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # metadata.csv names papers by paper_id, a split file (split_v6.csv) by arxiv_id
            pid, split = row.get("paper_id") or row.get("arxiv_id"), row.get("split")
            if not (pid and split):
                continue
            r = precedence.get(split, 2)
            if r > rank.get(pid, 0):
                out[pid], rank[pid] = split, r
    return out


def split_file(args) -> Path:
    """Where the train/val/test split is read from: --splits, else the corpus index."""
    if getattr(args, "splits", None):
        return Path(args.splits)
    return Path(args.metadata) if args.metadata else SILVER_METADATA


def assert_no_test_leak(papers, splits: dict) -> None:
    """Refuse to distil on anything the corpus marks as test.

    Distillation writes rules FROM these papers, so a test paper here is
    training on the test set — it would silently invalidate every held-out
    number we report. Fail loudly rather than warn: a warning in a long run
    scrolls past.
    """
    leaked = [p for p in papers if splits.get(p) == "test"]
    if leaked:
        raise SystemExit(
            f"ABORT: {len(leaked)} test-split paper(s) in the distillation set: "
            f"{', '.join(sorted(leaked))}\n"
            f"Distillation writes rules from these papers; including test "
            f"papers trains on the test set. Fix --pilot-papers, or pass "
            f"--allow-test-papers if you genuinely intend this.")
    unknown = [p for p in papers if p not in splits]
    if unknown:
        print(f"  [split] {len(unknown)} paper(s) not in metadata.csv "
              f"(no split recorded): {', '.join(sorted(unknown)[:5])}"
              f"{' ...' if len(unknown) > 5 else ''}")


# ---------------------------------------------------------------------------
# Rule sets and parsing
# ---------------------------------------------------------------------------

def snapshot_dirs(eval_dir: Path) -> list:
    """<eval_dir>/snapshots/step_NN_* in step order (numeric: step_100 after step_99)."""
    def step(p):
        m = re.match(r"step_(\d+)", p.name)
        return int(m.group(1)) if m else -1
    return sorted((Path(eval_dir) / "snapshots").glob("step_*"), key=step)


def parse_objects(pid: str, tex_dir: Path, types, rules_dir) -> list:
    """[(type, raw latex, environment)] of the `types` nodes the rule parser finds in
    one paper, with the rule set in `rules_dir` (None: the parser's default)."""
    from math_paper_parser import PaperParser
    main = find_main_tex(Path(tex_dir) / pid / "source")
    if not main:
        return []
    try:
        g = PaperParser(paper_id=pid, extraction_mode="rules", structure_types=list(types),
                        rules_dir=rules_dir).parse_file(str(main)).to_dict()
    except Exception as e:                                    # noqa: BLE001
        print(f"  [warn] parse failed for {pid}: {type(e).__name__}: {e}", flush=True)
        return []
    return [(o["kind"], raw, o.get("env_name") or "") for o in g.get("objects", {}).values()
            if o.get("kind") in types and (raw := o.get("raw_latex") or o.get("statement") or "").strip()]


def parse_buckets(pid: str, tex_dir: Path, types, rules_dir) -> dict:
    """{type: [raw latex, ...]} of one paper (parse_objects)."""
    out = {t: [] for t in types}
    for t, raw, _ in parse_objects(pid, tex_dir, types, rules_dir):
        out[t].append(raw)
    return out
