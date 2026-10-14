#!/usr/bin/env python3
"""Shared helpers of the distillation drivers (silver_distillation_merged.py,
compare_distillers.py, distill_units.py and others import them as `seq`).

The sequential driver that once lived here (one paper at a time, NtRED v1) is on the
archive/pre-v6 branch. What remains: the type -> gold-CSV file map (FNAME_MAP), the
silver-JSON -> gold-CSV conversion, main-.tex lookup, the match metric and the
SILVER-profile matcher, installing/uninstalling a rule set, and pattern counting.
"""

import csv
import json
import sys
from pathlib import Path

# Add src/LLMVersion to path for imports
REPO = Path(__file__).resolve().parent.parent
LLM_DIR = REPO / "src" / "LLMVersion"
sys.path.insert(0, str(LLM_DIR))
sys.path.insert(0, str(REPO / "src"))



# Match metric — set by --match-metric flag. "jaccard" preserves prior behavior;
# "containment" uses |A ∩ B| / min(|A|,|B|) which is forgiving on span asymmetry
# (rules fragments inside opus paragraphs match cleanly).
def set_match_metric(metric: str) -> str:
    """Set the run-wide match metric. THE way to configure matching.

    Both similarity wrappers (this module's SILVER-profile one and
    distillation_analysis's DISTILLATION-profile one) read a single variable in
    node_similarity, so they cannot end up on different metrics. Assigning a
    module global here does nothing — call this instead.
    """
    import node_similarity as _ns
    return _ns.set_match_metric(metric)


def jaccard_similarity(text1, text2):
    """Silver-profile match score; metric read from node_similarity.

    Implementation lives in src/node_similarity.py (Profile.SILVER): the same
    macro-collapsing cleanup as before, with "jaccard" and "containment"
    selectable. distillation_analysis.jaccard_similarity uses the same profile.
    """
    import node_similarity as _ns
    from node_similarity import Profile, text_sim
    return text_sim(text1, text2, profile=Profile.SILVER,
                    metric=_ns.MATCH_METRIC)


# ---------------------------------------------------------------------------
# T2 JSON → Gold CSV conversion
# ---------------------------------------------------------------------------

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


def convert_t2_to_gold_csv(t2_json_path: Path, structure_type: str,
                           out_dir: Path,
                           origin_filter: str | None = None) -> tuple[Path, int]:
    """Convert a single T2 JSON file into gold-CSV rows for `structure_type`.

    Appends to the CSV if it already exists.
    If `origin_filter` is set (e.g. "paper"), only nodes whose `origin` field
    matches are included. Returns (csv_path, n_items_added).
    """
    d = json.load(open(t2_json_path, encoding='utf-8'))
    # Use the filename stem as paper_id (e.g. "paper001") to stay consistent
    # with how pilot_papers are specified and how evaluate_single_paper looks up gold.
    pid = t2_json_path.stem

    rows = []
    for n in d.get("nodes", []):
        if n.get("type") != structure_type:
            continue
        # origin filter: match `origin_filter`, or accept nodes with no origin
        # tag (older v4 parses don't emit the field on every node).
        if origin_filter is not None:
            o = n.get("origin")
            if o is not None and o != origin_filter:
                continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        clean = n.get("statement_clean") or n.get("clean_text") or ""
        if raw.strip():
            rows.append({
                "paper_id": pid,
                "Gold_Standard_raw_latex": raw,
                "Gold_Standard_clean_text": clean,
            })

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / FNAME_MAP[structure_type]
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "Gold_Standard_raw_latex",
                                          "Gold_Standard_clean_text"])
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)

    return csv_path, len(rows)


# ---------------------------------------------------------------------------
# Build detailed_matches.csv for a single paper
# ---------------------------------------------------------------------------


def _find_main_tex(src_dir: Path) -> Path | None:
    """Find the main .tex file in a source directory."""
    if not src_dir.exists():
        return None
    tex_files = sorted(src_dir.glob("*.tex"))
    if not tex_files:
        return None
    for tf in tex_files:
        try:
            with open(tf, encoding="utf-8", errors="replace") as f:
                head = f.read(8000)
            if r"\documentclass" in head:
                return tf
        except OSError:
            continue
    return tex_files[0]


# ---------------------------------------------------------------------------
# Compute P/R/F1 for a single paper against its silver gold
# ---------------------------------------------------------------------------

def _install_silver_rules(eval_dir: Path, structure_type: str) -> tuple[Path, Path | None]:
    """Symlink silver distilled_rules.py into where PaperParser expects it.

    Returns (target_dir, backup_path_or_None) so caller can restore.
    """
    silver_rules = eval_dir / "distilled_rules.py"
    parser_dir = Path(LLM_DIR)
    target_dir = parser_dir / f"{structure_type}_eval"
    target_file = target_dir / "distilled_rules.py"

    backup = None
    if target_file.exists() or target_file.is_symlink():
        backup = target_file.with_suffix('.py.silver_bak')
        if backup.exists() or backup.is_symlink():
            # an earlier install was never undone: renaming over the backup would
            # destroy the production rules it holds
            raise RuntimeError(f"{backup} already exists: a previous silver install was "
                               f"not restored. Restore it by hand before continuing.")
        target_file.rename(backup)

    if silver_rules.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.symlink_to(silver_rules.resolve())

    return target_dir, backup


def _uninstall_silver_rules(structure_type: str, backup: Path | None):
    """Restore original distilled_rules.py after silver evaluation."""
    parser_dir = Path(LLM_DIR)
    target_file = parser_dir / f"{structure_type}_eval" / "distilled_rules.py"

    if target_file.is_symlink():
        target_file.unlink()

    if backup and backup.exists():
        backup.rename(target_file)


# ---------------------------------------------------------------------------
# Count rules in distilled_rules.py
# ---------------------------------------------------------------------------

def count_compiled_patterns(rules_path: Path) -> int:
    """Count compiled regex patterns in a distilled_rules.py file."""
    if not rules_path.exists():
        return 0
    text = rules_path.read_text(encoding='utf-8')
    # Count re.compile() calls that are not commented out
    count = 0
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 're.compile(' in stripped:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Main sequential loop
# ---------------------------------------------------------------------------
