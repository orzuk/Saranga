#!/bin/bash
# Usage: bash distill.sh <structure_type>
# Example: bash distill.sh definition
#          bash distill.sh theorem
#
# Runs the full NtRED distillation loop:
#   1. dark-knowledge  — find gold items missed by manual but caught by LLMs
#   2. analyze         — LLM suggests per-item regex rules from TeX source
#   3. aggregate       — meta-LLM consolidates into distilled_rules.py
#   4. validate        — re-run manual parser to check if missed items are now caught
#
# Prerequisite: run extraction.sh first to populate {type}_eval/ with evaluation results.
# Valid types: definition theorem lemma proof proposition corollary claim conjecture problem

set -euo pipefail

STYPE="${1:?Usage: bash distill.sh <structure_type>}"

case "$STYPE" in
    definition)  GOLD_CSV="Gold_Standard_Definitions.csv" ;;
    theorem)     GOLD_CSV="Gold_Standard_Theorems.csv" ;;
    lemma)       GOLD_CSV="Gold_Standard_Lemmas.csv" ;;
    proof)       GOLD_CSV="Gold_Standard_Proofs.csv" ;;
    proposition) GOLD_CSV="Gold_Standard_Propositions.csv" ;;
    corollary)   GOLD_CSV="Gold_Standard_Corollaries.csv" ;;
    claim)       GOLD_CSV="Gold_Standard_Claims.csv" ;;
    conjecture)  GOLD_CSV="Gold_Standard_Conjectures.csv" ;;
    problem)     GOLD_CSV="Gold_Standard_Problems.csv" ;;
    *)
        echo "Error: unknown structure type '$STYPE'"
        echo "Valid types: definition theorem lemma proof proposition corollary claim conjecture problem"
        exit 1
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-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}"

EVAL_DIR="${STYPE}_eval"
ALL_PAPERS="1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1"

# Check prerequisite
if [ ! -f "${EVAL_DIR}/detailed_matches.csv" ]; then
    echo "Error: ${EVAL_DIR}/detailed_matches.csv not found."
    echo "Run 'bash extraction.sh ${STYPE}' first to generate evaluation results."
    exit 1
fi

echo "============================================================"
echo "NtRED DISTILLATION: ${STYPE}"
echo "============================================================"

# Step 1: Identify dark knowledge
echo ""
echo "[Step 1/4] Identifying dark knowledge..."
python distillation_analysis.py dark-knowledge \
    --eval-dir "$EVAL_DIR" \
    --gold-csv "$GOLD_CSV" \
    --structure-type "$STYPE"

DK_CSV="${EVAL_DIR}/dark_knowledge.csv"
if [ ! -f "$DK_CSV" ]; then
    echo "No dark knowledge found — manual parser already catches everything LLMs catch."
    echo "Nothing to distill."
    exit 0
fi

# Check if dark_knowledge.csv has any data rows
DK_LINES=$(wc -l < "$DK_CSV")
if [ "$DK_LINES" -le 1 ]; then
    echo "No dark knowledge items found (empty CSV). Nothing to distill."
    exit 0
fi

# Step 2: Analyze patterns in TeX source
echo ""
echo "[Step 2/4] Analyzing patterns (LLM-powered)..."
python distillation_analysis.py analyze \
    --input "$DK_CSV" \
    --structure-type "$STYPE" \
    --output "${EVAL_DIR}/analyze_patterns.csv"

# Step 3: Aggregate into distilled_rules.py
echo ""
echo "[Step 3/4] Aggregating rules (LLM-powered)..."
python distillation_analysis.py aggregate \
    --input "${EVAL_DIR}/analyze_patterns.csv" \
    --structure-type "$STYPE" \
    --eval-dir "$EVAL_DIR"

if [ ! -f "${EVAL_DIR}/distilled_rules.py" ]; then
    echo "Error: aggregate failed to produce distilled_rules.py"
    exit 1
fi

# Step 4: Validate — re-run manual parser with distilled rules
echo ""
echo "[Step 4/4] Validating distilled rules..."
python distillation_analysis.py validate \
    --paper-ids "$ALL_PAPERS" \
    --structure-type "$STYPE" \
    --expected "$DK_CSV" \
    --gold-csv "$GOLD_CSV"

echo ""
echo "============================================================"
echo "DISTILLATION COMPLETE: ${STYPE}"
echo "============================================================"
echo "  Dark knowledge:   ${DK_CSV}"
echo "  Patterns:         ${EVAL_DIR}/analyze_patterns.csv"
echo "  Distilled rules:  ${EVAL_DIR}/distilled_rules.py"
echo "  Validation:       ${EVAL_DIR}/dark_knowledge_validation.csv"
echo ""
echo "Next: review distilled_rules.py, then re-run 'bash extraction.sh ${STYPE}' for full P/R/F1."
