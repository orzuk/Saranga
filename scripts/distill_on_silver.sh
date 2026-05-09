#!/bin/bash
# distill_on_silver.sh — run the distillation pipeline against the 250 T2
# (opus silver) extractions instead of the 10 hand-gold papers.
#
# Premise: Yaron's distillation pipeline (src/LLMVersion/distill.sh) is
# compute-light — it's API calls + regex, no GPU. It can run anywhere.
# This script does the local prep + invokes distill.sh against the larger
# silver corpus.
#
# Usage:
#   bash scripts/distill_on_silver.sh <structure_type>
# Example:
#   bash scripts/distill_on_silver.sh definition
#
# Prerequisites:
#   - $SARANGA_DATA_ROOT/tier2/paper*.json present (you already have these)
#   - $SARANGA_DATA_ROOT/alignment/papers/paper*/source/*.tex present
#     (rsync from cluster: alignment_benchmark/papers/ -> alignment/papers/)
#   - ANTHROPIC_API_KEY set in environment
#
# Output:
#   src/LLMVersion/<type>_eval_silver250/distilled_rules.py    — the new rules
#   src/LLMVersion/<type>_eval_silver250/dark_knowledge.csv    — items rules missed
#   src/LLMVersion/<type>_eval_silver250/dark_knowledge_validation.csv

set -euo pipefail

STYPE="${1:?Usage: bash scripts/distill_on_silver.sh <structure_type>}"
case "$STYPE" in
    definition|theorem|lemma|proof|proposition|corollary|claim|conjecture|problem) ;;
    *) echo "Error: invalid type '$STYPE'"; exit 1 ;;
esac

REPO=$(cd "$(dirname "$0")/.." && pwd)
LLM_DIR="$REPO/src/LLMVersion"
EVAL_DIR="$LLM_DIR/${STYPE}_eval_silver250"
SILVER_GOLD_DIR="$LLM_DIR/silver_t2"
SARANGA_DATA="${SARANGA_DATA_ROOT:-/mnt/c/Datasets/Saranga_data}"
T2_DIR="$SARANGA_DATA/tier2"
ALIGN_DIR="$SARANGA_DATA/alignment/papers"

mkdir -p "$EVAL_DIR" "$SILVER_GOLD_DIR"

# ---------------------------------------------------------------------------
# Step 0: convert the 250 T2 (opus) JSONs into the gold-CSV format the
# distillation pipeline expects, one CSV per type.
# ---------------------------------------------------------------------------
echo "[0/5] Converting T2 opus JSONs -> Gold_Standard_<Type>.csv ..."
python3 - <<PYEOF
import json, csv, glob, os
from collections import defaultdict
from pathlib import Path

T2 = Path("$T2_DIR")
OUT = Path("$SILVER_GOLD_DIR")
OUT.mkdir(parents=True, exist_ok=True)

# Group nodes by type
per_type = defaultdict(list)
for f in sorted(T2.glob("paper*.json")):
    d = json.load(open(f))
    pid_num = d.get("metadata", {}).get("paper_num")
    if pid_num is None:
        pid_num = f.stem.replace("paper", "").lstrip("0") or "1"
    pid = f"paper{int(pid_num)}"
    for n in d.get("nodes", []):
        t = n.get("type", "")
        if not t: continue
        per_type[t].append({
            "paper_id": pid,
            "gold_index": n.get("id", ""),
            "name":      n.get("name", "") or "",
            "raw_latex": n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or "",
            "clean_text": n.get("statement_clean") or n.get("clean_text") or "",
        })

# Map type -> filename (matches Yaron's plural style)
fname_map = {
    "definition": "Gold_Standard_Definitions.csv",
    "theorem":    "Gold_Standard_Theorems.csv",
    "lemma":      "Gold_Standard_Lemmas.csv",
    "proof":      "Gold_Standard_Proofs.csv",
    "proposition":"Gold_Standard_Propositions.csv",
    "corollary":  "Gold_Standard_Corollaries.csv",
    "claim":      "Gold_Standard_Claims.csv",
    "conjecture": "Gold_Standard_Conjectures.csv",
    "problem":    "Gold_Standard_Problems.csv",
}
for t, rows in per_type.items():
    fname = fname_map.get(t)
    if not fname: continue
    path = OUT / fname
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id","gold_index","name","raw_latex","clean_text"])
        w.writeheader()
        for r in rows: w.writerow(r)
    print(f"  {fname}: {len(rows)} items from {len({r['paper_id'] for r in rows})} papers")
PYEOF

# Map type to gold CSV filename
case "$STYPE" in
    definition) GOLD_CSV="Gold_Standard_Definitions.csv" ;;
    theorem)    GOLD_CSV="Gold_Standard_Theorems.csv" ;;
    lemma)      GOLD_CSV="Gold_Standard_Lemmas.csv" ;;
    proof)      GOLD_CSV="Gold_Standard_Proofs.csv" ;;
    proposition)GOLD_CSV="Gold_Standard_Propositions.csv" ;;
    corollary)  GOLD_CSV="Gold_Standard_Corollaries.csv" ;;
    claim)      GOLD_CSV="Gold_Standard_Claims.csv" ;;
    conjecture) GOLD_CSV="Gold_Standard_Conjectures.csv" ;;
    problem)    GOLD_CSV="Gold_Standard_Problems.csv" ;;
esac

if [ ! -f "$SILVER_GOLD_DIR/$GOLD_CSV" ]; then
    echo "Error: $SILVER_GOLD_DIR/$GOLD_CSV not generated. Aborting."
    exit 1
fi

N_ITEMS=$(($(wc -l < "$SILVER_GOLD_DIR/$GOLD_CSV") - 1))
echo "  -> ${N_ITEMS} ${STYPE} items in silver gold"

# ---------------------------------------------------------------------------
# Step 1: run the rule-parser on each of the 250 .tex sources to produce
# detailed_matches.csv that the distillation expects.
#
# This step needs the source .tex per paper. If you don't have all 250 .tex
# files locally yet, rsync them from cluster first:
#   rsync -avz --include='*/' --include='source/*.tex' --exclude='*' \
#       <user>@<cluster>:/sci/.../alignment_benchmark/papers/ \
#       $SARANGA_DATA_ROOT/alignment/papers/
# ---------------------------------------------------------------------------
echo
echo "[1/5] Running rule-parser on 250 silver papers (mode=rules) ..."
python3 - <<PYEOF
import sys, json, csv, os, glob
from pathlib import Path
sys.path.insert(0, "$LLM_DIR")
from math_paper_parser import PaperParser

ALIGN = Path("$ALIGN_DIR")
T2    = Path("$T2_DIR")
EVAL  = Path("$EVAL_DIR")
STYPE = "$STYPE"

EVAL.mkdir(parents=True, exist_ok=True)

# detailed_matches.csv is what distillation_analysis.py reads. Format:
#   paper_id,provider,raw_latex,...
# We write rows for both 'rules' (rule-parser) and 'opus' (silver gold)
# providers, so dark-knowledge can compute "rules missed AND opus caught".

rows = []
n_papers = 0; n_skipped = 0
for paper_dir in sorted(ALIGN.glob("paper*")):
    pid = paper_dir.name  # paperNNN
    if not pid.startswith("paper"): continue
    src_dir = paper_dir / "source"
    if not src_dir.exists():
        n_skipped += 1; continue
    tex_files = sorted(src_dir.glob("*.tex"))
    if not tex_files: continue

    # Find main tex by \documentclass; fall back to first .tex
    main_tex = None
    for tf in tex_files:
        try:
            with open(tf, encoding="utf-8", errors="replace") as f:
                head = f.read(8000)
            if r"\documentclass" in head:
                main_tex = tf; break
        except Exception:
            continue
    if main_tex is None: main_tex = tex_files[0]

    try:
        parser = PaperParser(paper_id=pid, extraction_mode="rules", structure_types=[STYPE])
        graph = parser.parse_file(str(main_tex))
        graph_dict = graph.to_dict()
        for obj_id, obj in graph_dict.get("objects", {}).items():
            if obj.get("kind") != STYPE: continue
            raw = obj.get("raw_latex") or obj.get("statement") or ""
            if raw.strip():
                rows.append({"paper_id": pid, "provider": "rules", "raw_latex": raw})
        n_papers += 1
    except Exception as e:
        print(f"  [warn] {pid}: parse failed ({e})"); n_skipped += 1

# Add the opus side: same papers, opus extractions are in T2_DIR/paperNNN.json
for f in sorted(T2.glob("paper*.json")):
    d = json.load(open(f))
    pid_num = d.get("metadata", {}).get("paper_num") or int(f.stem.replace("paper",""))
    pid = f"paper{int(pid_num)}"
    for n in d.get("nodes", []):
        if n.get("type") != STYPE: continue
        raw = n.get("statement_latex") or n.get("statement") or n.get("raw_latex") or ""
        if raw.strip():
            rows.append({"paper_id": pid, "provider": "opus", "raw_latex": raw})

out_csv = EVAL / "detailed_matches.csv"
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["paper_id","provider","raw_latex"])
    w.writeheader()
    for r in rows: w.writerow(r)
print(f"  wrote {out_csv}: {len(rows)} rows from {n_papers} papers ({n_skipped} skipped)")
PYEOF

# ---------------------------------------------------------------------------
# Steps 2-5: invoke the existing distillation pipeline against the silver gold.
# ---------------------------------------------------------------------------
cd "$LLM_DIR"
GOLD="$SILVER_GOLD_DIR/$GOLD_CSV"

echo
echo "[2/5] Identifying dark knowledge (rules missed AND opus caught) ..."
python3 distillation_analysis.py dark-knowledge \
    --eval-dir "$EVAL_DIR" \
    --gold-csv "$GOLD" \
    --structure-type "$STYPE"

DK="$EVAL_DIR/dark_knowledge.csv"
if [ ! -f "$DK" ] || [ "$(wc -l < "$DK")" -le 1 ]; then
    echo "No dark knowledge -- rule parser already catches what opus catches. Done."
    exit 0
fi
echo "  $(($(wc -l < "$DK") - 1)) dark-knowledge items"

echo
echo "[3/5] Analyzing patterns (LLM-powered, ~2 sec/item) ..."
python3 distillation_analysis.py analyze \
    --input "$DK" \
    --structure-type "$STYPE" \
    --output "$EVAL_DIR/analyze_patterns.csv"

echo
echo "[4/5] Aggregating into distilled_rules.py (one big LLM call) ..."
python3 distillation_analysis.py aggregate \
    --input "$EVAL_DIR/analyze_patterns.csv" \
    --structure-type "$STYPE" \
    --eval-dir "$EVAL_DIR"

echo
echo "[5/5] Skipping the validate step:"
echo "    Yaron's _find_local_tex uses FULL_PAPERS_DIR with arxiv-id naming,"
echo "    but our papers are paperNNN/source/<main>.tex. Validate would need"
echo "    a small patch to _find_local_tex to also search alignment/papers/."
echo "    The aggregated distilled_rules.py is the deliverable; rerun"
echo "    Yaron's existing validate or extraction.sh against the gold set"
echo "    once the new rules land if you want a P/R/F1 number."

echo
echo "============================================================"
echo "DISTILLATION ON SILVER 250 — DONE for type=$STYPE"
echo "============================================================"
echo "  dark_knowledge.csv:    $EVAL_DIR/dark_knowledge.csv"
echo "  analyze_patterns.csv:  $EVAL_DIR/analyze_patterns.csv"
echo "  distilled_rules.py:    $EVAL_DIR/distilled_rules.py"
echo
echo "Compare with the 10-paper version:"
echo "  diff $LLM_DIR/${STYPE}_eval/distilled_rules.py $EVAL_DIR/distilled_rules.py"
